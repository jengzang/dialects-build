"""讀取漢字音典表檔案的元數據 sheet。

「漢字音典字表檔案（長期更新）.xlsx」目前包含兩張元數據表：
- 檔案（主要字表）
- 民國調查大系列檔案（民國時期方言調查點，schema 幾乎相同）

兩張表合併成一個 DataFrame 供 query.db 寫入與 -c 檢查共用。
"""

import pandas as pd

from common.config import HAN_PATH

MAIN_SHEET = "檔案"
MINGUO_SHEET = "民國調查大系列檔案"

# 民國調查 sheet 用「[9]其他調」，檔案 sheet 用「[9]變調」；
# 二者對應同一個 DB 欄位 T9其他調，統一成「[9]變調」以通過欄位校驗。
MINGUO_COLUMN_RENAME = {"[9]其他調": "[9]變調"}


def _read_sheet(excel_path, sheet_name, dtype, keep_default_na):
    kwargs = dict(header=0, engine="openpyxl")
    if dtype is not None:
        kwargs["dtype"] = dtype
    if keep_default_na is not None:
        kwargs["keep_default_na"] = keep_default_na

    df = pd.read_excel(excel_path, sheet_name=sheet_name, **kwargs)
    # 第 2 行為欄位說明行（#↓必塡↓# ...），跳過
    df = df.drop(index=0).reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _valid_abbr(series):
    """回傳有效簡稱集合（排除空、NaN 與以 # 開頭的說明行）。"""
    abbr = series.astype(str).str.strip()
    return {
        x for x in abbr.tolist()
        if x and x != "nan" and not x.startswith("#")
    }


def load_han_metadata(excel_path=HAN_PATH, dtype=None, keep_default_na=None):
    """讀取「檔案」+「民國調查大系列檔案」並合併。

    - 民國調查 sheet 缺「[9]變調」時會從「[9]其他調」歸一化補上。
    - 與檔案重名的簡稱（如 泰順筱村 等）以檔案優先，剔除民國調查的重複行；
      空行/說明行保留，交由下游用 set() 或空簡稱過濾處理。
    - 舊版 xlsx 若沒有民國調查 sheet，則只回傳檔案 sheet。
    """
    main = _read_sheet(excel_path, MAIN_SHEET, dtype, keep_default_na)

    try:
        sheet_names = pd.ExcelFile(excel_path, engine="openpyxl").sheet_names
    except Exception:
        sheet_names = []

    if MINGUO_SHEET not in sheet_names:
        return main

    minguo = _read_sheet(excel_path, MINGUO_SHEET, dtype, keep_default_na)
    minguo = minguo.rename(columns=MINGUO_COLUMN_RENAME)

    main_abbr = _valid_abbr(main["簡稱"])
    minguo_abbr = minguo["簡稱"].astype(str).str.strip()
    is_valid = (minguo_abbr != "") & (minguo_abbr != "nan") & ~minguo_abbr.str.startswith("#")
    drop_overlap = is_valid & minguo_abbr.isin(main_abbr)
    minguo = minguo[~drop_overlap].copy()

    return pd.concat([main, minguo], ignore_index=True)
