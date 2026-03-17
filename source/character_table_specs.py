from dataclasses import dataclass, field
from typing import Callable, Mapping

import pandas as pd

from common.config import (
    FENYUN_CUOYAO_PATH,
    HONGWU_ZHENGYUN_PATH,
    MENGGU_ZIYUN_PATH,
    PHO_TABLE_PATH,
    SHANGGU_HANYU_PATH,
    ZHONGYUAN_YINYUN_PATH,
)

DataFrameTransform = Callable[[pd.DataFrame], pd.DataFrame]


@dataclass(frozen=True)
class MergeTextSpec:
    meaning_column: str = "釋義"
    note_column: str | None = None
    note_label: str = "注釋"


@dataclass(frozen=True)
class CharacterTableSpec:
    table_name: str
    file_path: str
    file_type: str = "excel"
    sheet_name: str | int = 0
    columns: tuple[str, ...] = ()
    rename_columns: Mapping[str, str] = field(default_factory=dict)
    final_columns: tuple[str, ...] | None = None
    single_index_columns: tuple[str, ...] = ()
    pair_index_columns: tuple[str, ...] = ()
    hierarchy_index: tuple[str, ...] | None = None  # 层级复合索引
    char_column: str | None = None
    row_filter: DataFrameTransform | None = None
    transform_func: DataFrameTransform | None = None
    merge_text_spec: MergeTextSpec | None = None
    drop_unnamed: bool = False


@dataclass(frozen=True)
class PhonologyTableSpec:
    table_name: str
    file_path: str
    sheet_name: str | int
    source_columns: tuple[str, ...]
    rename_columns: Mapping[str, str]
    final_columns: tuple[str, ...]
    char_column: str
    meaning_column: str
    composite_index_columns: tuple[str, ...]
    triple_indexes: tuple[tuple[str, str], ...]
    multi_column_indexes: tuple[tuple[str, ...], ...]
    hierarchy_index: tuple[str, ...] | None  # 层级复合索引
    single_index_columns: tuple[str, ...]
    missing_check_exempt_columns: tuple[str, ...]
    duplicate_flag_column: str


def chinese_numeral_to_int(text: str) -> int | None:
    """
    把簡單中文數字轉為整數，足夠處理本項目中的韻序。
    """
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }

    if not text:
        return None

    if text == "十":
        return 10

    if "十" in text:
        left, right = text.split("十", 1)
        tens = digits.get(left, 1) if left else 1
        ones = digits.get(right, 0) if right else 0
        return tens * 10 + ones

    return digits.get(text)


def filter_fenyun_cuoyao_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    分韻撮要只保留單字字頭，濾掉問號與非單字記錄。
    """
    hanzi = df["漢字"].astype(str).str.strip()
    return df[(hanzi != "?") & (hanzi.str.len() == 1)]


def split_menggu_yunbu_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    將蒙古字韻的韻部拆成韻序與純韻部名。
    """
    result = df.copy()
    yunbu_series = result["韻部"].fillna("").astype(str).str.strip()
    match_series = yunbu_series.str.extract(r"^([一二三四五六七八九十百]+)(.+)$")

    result["韻序"] = match_series[0].map(lambda value: chinese_numeral_to_int(value) if pd.notna(value) else "")
    result["韻部"] = match_series[1].fillna(yunbu_series)
    return result


def split_zhongyuan_yunmu_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    將中原音韻的韻母拆成韻母本體、呼、等。
    """
    result = df.copy()
    yunmu_series = result["韻母"].fillna("").astype(str).str.strip()
    match_series = yunmu_series.str.extract(r"^(.*?)([開合撮齊])([一二三四五六七八九十]+)?$")

    result["韻母"] = match_series[0].fillna(yunmu_series)
    result["呼"] = match_series[1].fillna("")
    result["等"] = match_series[2].fillna("")
    return result


PHONOLOGY_TABLE_SPEC = PhonologyTableSpec(
    table_name="characters",
    file_path=PHO_TABLE_PATH,
    sheet_name="層級",
    source_columns=(
        "攝", "呼", "等", "韻", "入", "調", "清濁", "系", "組", "母", "部位", "方式", "單字", "釋義",
        "多聲母", "多等", "多韻", "多調",
    ),
    rename_columns={"單字": "漢字"},
    final_columns=(
        "攝", "呼", "等", "韻", "入", "調", "清濁", "系", "組", "母", "部位", "方式", "漢字", "釋義",
        "多聲母", "多等", "多韻", "多調",
    ),
    char_column="漢字",
    meaning_column="釋義",
    composite_index_columns=("攝", "呼", "等", "韻", "入", "調", "清濁", "系", "組", "母", "部位", "方式"),
    triple_indexes=(("攝", "等"), ("攝", "呼"), ("攝", "母"), ("清濁", "調")),
    multi_column_indexes=(("組", "等", "攝", "呼", "韻", "調"), ("多地位標記", "漢字"), ("等", "漢字")),
    hierarchy_index=("組", "等", "攝", "呼", "韻", "調"),  # 层级复合索引（根据后端邮件要求）
    single_index_columns=("漢字", "多聲母", "多等", "多韻", "多調", "多地位標記"),
    missing_check_exempt_columns=("漢字", "釋義"),
    duplicate_flag_column="多地位標記",
)


LEGACY_CHARACTER_TABLE_NAMES = (
    "hongwu_zhengyun_main",
    "menggu_ziyun",
    "shanggu_hanyu",
    "zhongyuan_yinyun",
    "fenyun_cuoyao",
    "hongwu",
    "menggu",
    "old_chinese",
    "zhongyuan",
    "fenyun",
)


ADDITIONAL_CHARACTER_TABLE_SPECS = (
    CharacterTableSpec(
        table_name="hongwu",
        file_path=HONGWU_ZHENGYUN_PATH,
        file_type="excel",
        sheet_name="01 洪武正韻",
        columns=("字", "聲調", "韻部", "聲母", "聲類", "清濁", "上字", "下字", "釋義"),
        rename_columns={"字": "漢字"},
        final_columns=("漢字", "聲調", "韻部", "聲母", "聲類", "清濁", "上字", "下字", "釋義"),
        char_column="漢字",
        single_index_columns=("漢字",),
        pair_index_columns=("聲調", "韻部", "聲母", "聲類", "清濁"),
        hierarchy_index=("聲母", "韻部", "聲調", "清濁"),  # 层级复合索引
    ),
    CharacterTableSpec(
        table_name="menggu",
        file_path=MENGGU_ZIYUN_PATH,
        file_type="tsv",
        columns=("韻部", "八思巴字", "聲調", "字頭", "備選異體", "釋義", "注釋", "unt轉寫", "對應切韻音系音韻地位"),
        transform_func=split_menggu_yunbu_columns,
        merge_text_spec=MergeTextSpec(meaning_column="釋義", note_column="注釋", note_label="注釋"),
        rename_columns={"字頭": "漢字", "unt轉寫": "擬音"},
        final_columns=("韻序", "韻部", "八思巴字", "聲調", "漢字", "備選異體", "釋義", "擬音", "對應切韻音系音韻地位"),
        char_column="漢字",
        single_index_columns=("漢字",),
        pair_index_columns=("聲調", "韻部"),
        hierarchy_index=("韻部", "聲調"),  # 层级复合索引
    ),
    CharacterTableSpec(
        table_name="old_chinese",
        file_path=SHANGGU_HANYU_PATH,
        file_type="excel",
        columns=(
            "字", "原始音標", "聲調", "聲母", "韻母", "韻部", "聲母組", "r介音", "非三等", "諧聲域", "音",
            "見詩經韻", "見其他韻", "總出現次數", "先秦字頻（歸一化）", "少見詞出處", "見西周",
            "西周字頻（歸一化）", "釋義", "注釋",
        ),
        drop_unnamed=True,
        rename_columns={"字": "漢字"},
        final_columns=(
            "漢字", "原始音標", "聲調", "聲母", "韻母", "韻部", "聲母組", "r介音", "非三等", "諧聲域", "音",
            "見詩經韻", "見其他韻", "總出現次數", "先秦字頻（歸一化）", "少見詞出處", "見西周",
            "西周字頻（歸一化）", "釋義", "注釋",
        ),
        char_column="漢字",
        single_index_columns=("漢字",),
        pair_index_columns=("聲調", "聲母", "韻母", "韻部", "聲母組", "諧聲域", "r介音", "非三等"),
        hierarchy_index=("聲母", "韻母", "韻部", "聲調"),  # 层级复合索引
    ),
    CharacterTableSpec(
        table_name="zhongyuan",
        file_path=ZHONGYUAN_YINYUN_PATH,
        file_type="tsv",
        columns=("小韻", "字", "聲母", "韻母", "聲調", "unt", "釋義", "校註"),
        transform_func=split_zhongyuan_yunmu_columns,
        merge_text_spec=MergeTextSpec(meaning_column="釋義", note_column="校註", note_label="校註"),
        rename_columns={"字": "漢字", "unt": "擬音"},
        final_columns=("小韻", "漢字", "聲母", "韻母", "呼", "等", "聲調", "擬音", "釋義"),
        char_column="漢字",
        single_index_columns=("漢字",),
        pair_index_columns=("聲母", "韻母", "呼", "等", "聲調", "小韻"),
        hierarchy_index=("聲母", "韻母", "呼", "等", "聲調"),  # 层级复合索引
    ),
    CharacterTableSpec(
        table_name="fenyun",
        file_path=FENYUN_CUOYAO_PATH,
        file_type="excel",
        sheet_name="YFanwan",
        columns=("漢字", "聲母jp", "韻腹jp", "韻尾jp", "調類jp", "小韻", "釋義", "聲母", "韻母", "韻部", "聲調"),
        row_filter=filter_fenyun_cuoyao_rows,
        final_columns=("漢字", "聲母jp", "韻腹jp", "韻尾jp", "調類jp", "小韻", "釋義", "聲母", "韻母", "韻部", "聲調"),
        char_column="漢字",
        single_index_columns=("漢字",),
        pair_index_columns=("小韻", "聲母", "韻母", "韻部", "聲調"),
        hierarchy_index=("聲母", "韻母", "韻部", "聲調"),  # 层级复合索引
    ),
)
