import csv
import re
import shutil
from pathlib import Path
from typing import Optional

from common.config import (
    EXTRACT_YINDIAN_DIR,
    WORD_EXTRACT_DIR,
)


BOX_CHARS = frozenset("□■⬜⬛☐☑☒▯▢▣█�")
HANZI_HEADERS = frozenset({"漢字", "汉字"})
NOTE_HEADERS = frozenset({"解釋", "解释", "注釋", "注释", "notes", "note"})
CHARACTER_TABLE_HEADERS = frozenset({"#漢字", "#汉字"})
WORD_SOURCE_EXCLUDE_TERMS = (
    "1925",
    "中原音韻",
    "中原音韵",
    "洪武正韻",
    "洪武正韵",
    "盛唐",
    "中唐",
    "北宋",
    "日語",
    "日语",
    "普通話",
    "普通话",
    "國語",
    "国语",
    "清末",
    "漢大",
    "康熙",
    "說文",
    "说文",
    "廣韻",
    "广韵",
    "集韻",
    "集韵",
    "匯纂",
    "汇纂",
    "蒙古字韻",
    "蒙古字韵",
    "分韻撮要",
    "分韵撮要",
    "西儒耳目資",
    "西儒耳目资",
    "日語近世唐音",
    "日语近世唐音",
    "鄭張上古",
    "郑张上古",
    "白－沙上古",
    "白-沙上古",
    "新最小上古",
    "上古",
    "中古",
    "古音",
    "歷史",
    "历史",
    "字典",
    "韻",
    "韵",
    "固原",
)
WORD_OUTPUT_HEADER = [
    "标准词",
    "方言词",
    "音标",
    "注释",
    "type",
    "原始汉字",
    "来源文件",
    "原始行号",
]
NON_WORD_TILDE_PATTERNS = (
    r"(?:西元|公元|民國|民国)?前?\d{2,4}年?[~～](?:西元|公元|民國|民国)?前?\d{2,4}年?",
    r"[A-Za-z]?\d{1,4}[~～][A-Za-z]?\d{1,4}",
)


def _normalize_header(value: str) -> str:
    return value.lstrip("\ufeff#").strip().casefold()


def _find_column_index(header: list[str], names: frozenset[str]) -> Optional[int]:
    normalized_names = {_normalize_header(name) for name in names}
    for index, value in enumerate(header):
        if _normalize_header(value) in normalized_names:
            return index
    return None


def _cell(row: list[str], index: Optional[int]) -> str:
    if index is None or index >= len(row):
        return ""
    return row[index]


def _is_character_table(header: list[str], hanzi_index: Optional[int]) -> bool:
    if hanzi_index is None or hanzi_index >= len(header):
        return False
    return header[hanzi_index].lstrip("\ufeff").strip() in CHARACTER_TABLE_HEADERS


def _is_excluded_word_source(source_path: Path) -> bool:
    return (
        bool(re.match(r"^\d{4}", source_path.stem))
        or any(term in source_path.stem for term in WORD_SOURCE_EXCLUDE_TERMS)
    )


def _reconstruct_dialect_words(hanzi: str, note_value: str) -> list[str]:
    replaced = note_value.replace("~", hanzi).replace("～", hanzi)
    candidates = []
    for clause in re.split(r"[;；]", replaced):
        candidate = re.split(r"[:：,，。]", clause, maxsplit=1)[0].strip()
        if candidate:
            candidates.append(candidate)
    return candidates or [replaced.strip()]


def _contains_word_marker(note_value: str) -> bool:
    cleaned = note_value
    for pattern in NON_WORD_TILDE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    return "~" in cleaned or "～" in cleaned


def _clear_output_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_rows(
    output_dir: Path,
    source_path: Path,
    header: list[str],
    rows: list[list[str]],
) -> int:
    if not rows:
        return 0

    output_path = output_dir / source_path.name
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    return len(rows)


def extract_yindian_records(
    source_dir: Path,
    *,
    vocabulary: bool = False,
    note: bool = False,
    output_root: Optional[Path] = None,
) -> dict[str, dict[str, int]]:
    """Extract special rows from per-location MCPDict TSV files."""
    if not vocabulary and not note:
        raise ValueError("至少需要启用 vocabulary 或 note")

    source_dir = Path(source_dir)
    output_root = Path(output_root) if output_root is not None else EXTRACT_YINDIAN_DIR
    output_dirs = {}

    if vocabulary:
        output_dirs["vocabulary"] = output_root / "vocabulary"
        _clear_output_dir(output_dirs["vocabulary"])
    if note:
        output_dirs["note"] = output_root / "note"
        _clear_output_dir(output_dirs["note"])

    result = {mode: {} for mode in output_dirs}
    source_paths = sorted(path for path in source_dir.glob("*.tsv") if path.is_file())

    for source_path in source_paths:
        with source_path.open("r", encoding="utf-8-sig", newline="") as source_file:
            reader = csv.reader(source_file, delimiter="\t")
            header = next(reader, None)
            if not header:
                continue

            hanzi_index = _find_column_index(header, HANZI_HEADERS)
            note_index = _find_column_index(header, NOTE_HEADERS)
            vocabulary_rows = []
            note_rows = []

            for row in reader:
                if vocabulary and any(char in BOX_CHARS for char in _cell(row, hanzi_index)):
                    vocabulary_rows.append(row)
                if note and _cell(row, note_index).strip():
                    note_rows.append(row)

        if vocabulary:
            count = _write_rows(
                output_dirs["vocabulary"],
                source_path,
                header,
                vocabulary_rows,
            )
            if count:
                result["vocabulary"][source_path.name] = count

        if note:
            count = _write_rows(
                output_dirs["note"],
                source_path,
                header,
                note_rows,
            )
            if count:
                result["note"][source_path.name] = count

    return result


def extract_yindian_words(
    source_dir: Path,
    *,
    output_root: Optional[Path] = None,
) -> dict[str, int]:
    """Extract modern character-table word candidates without merging locations."""
    source_dir = Path(source_dir)
    output_dir = (
        Path(output_root) / "word"
        if output_root is not None
        else WORD_EXTRACT_DIR
    )
    _clear_output_dir(output_dir)

    result = {}
    source_paths = sorted(path for path in source_dir.glob("*.tsv") if path.is_file())

    for source_path in source_paths:
        if _is_excluded_word_source(source_path):
            continue

        output_rows = []
        with source_path.open("r", encoding="utf-8-sig", newline="") as source_file:
            reader = csv.reader(source_file, delimiter="\t")
            header = next(reader, None)
            if not header:
                continue

            hanzi_index = _find_column_index(header, HANZI_HEADERS)
            note_index = _find_column_index(header, NOTE_HEADERS)
            tone_index = _find_column_index(header, frozenset({"音標", "音标"}))
            if not _is_character_table(header, hanzi_index) or note_index is None:
                continue

            for row_number, row in enumerate(reader, start=2):
                hanzi = _cell(row, hanzi_index)
                note_value = _cell(row, note_index)
                if not note_value.strip():
                    continue

                has_tilde = _contains_word_marker(note_value)
                dialect_words = (
                    _reconstruct_dialect_words(hanzi, note_value)
                    if has_tilde
                    else [""]
                )
                for dialect_word in dialect_words:
                    output_rows.append(
                        [
                            "",
                            dialect_word,
                            _cell(row, tone_index),
                            note_value,
                            "tilde" if has_tilde else "note",
                            hanzi,
                            source_path.name,
                            str(row_number),
                        ]
                    )

        if not output_rows:
            continue

        output_path = output_dir / source_path.name
        with output_path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.writer(output_file, delimiter="\t", lineterminator="\n")
            writer.writerow(WORD_OUTPUT_HEADER)
            writer.writerows(output_rows)
        result[source_path.name] = len(output_rows)

    return result
