import csv
import shutil
from pathlib import Path
from typing import Optional

from common.config import (
    EXTRACT_YINDIAN_DIR,
)


BOX_CHARS = frozenset("□■⬜⬛☐☑☒▯▢▣█�")
HANZI_HEADERS = frozenset({"漢字", "汉字"})
NOTE_HEADERS = frozenset({"解釋", "解释", "注釋", "注释", "notes", "note"})


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


def _clear_output_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _write_rows(output_dir: Path, source_path: Path, header: list[str], rows: list[list[str]]) -> int:
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
