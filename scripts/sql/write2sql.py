import os
import re
import sqlite3
import tkinter as tk
from tkinter import filedialog
from typing import Iterable, Optional, Tuple, List

import pandas as pd


def _sanitize_identifier(name: str) -> str:
    """
    尽量把列名/表名变成 SQLite 可接受的标识符（不完美但实用）。
    你也可以直接改成强制用双引号引用（我下面所有 SQL 都已用双引号）。
    """
    if name is None:
        return "unnamed"
    s = str(name).strip()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", s)  # 保留中文/字母数字下划线
    s = s.strip("_")
    return s or "unnamed"


def _detect_sqlite_type(series: pd.Series) -> str:
    """
    给每列做一个简单类型映射：INTEGER / REAL / TEXT / BLOB
    """
    if pd.api.types.is_bool_dtype(series):
        return "INTEGER"
    if pd.api.types.is_integer_dtype(series):
        return "INTEGER"
    if pd.api.types.is_float_dtype(series):
        return "REAL"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "TEXT"  # 用 ISO 字符串存
    return "TEXT"


def import_excel_sheet_columns_to_sqlite_via_tk(
    db_path: str,
    table_name: str,
    sheet_name: Optional[str] = None,
    exclude_cols: Optional[Iterable[str]] = None,
    if_exists: str = "replace",
    drop_all_null_rows: bool = False,
) -> Tuple[str, str, List[str]]:
    """
    弹出 Tk 选框选择 Excel 文件；只导入你指定的 sheet（表名），并把列写入 SQLite table。

    参数：
      - db_path: sqlite 文件路径
      - table_name: 目标 SQLite 表名
      - sheet_name: Excel sheet 名；若为 None，会弹出终端提示你输入（不做 GUI 的 sheet 列表弹窗，避免过重）
      - exclude_cols: 要排除不写入的列名列表（精确匹配，区分大小写）
      - if_exists: "replace" | "append" | "fail"
      - drop_all_null_rows: 是否删除全空行

    返回：(excel_path, used_sheet_name, inserted_columns)
    """
    exclude_set = set(exclude_cols or [])

    # --- Tk 选择文件 ---
    root = tk.Tk()
    root.withdraw()
    excel_path = filedialog.askopenfilename(
        title="选择 Excel 文件",
        filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")]
    )
    root.destroy()

    if not excel_path:
        raise RuntimeError("未选择 Excel 文件，已取消。")

    if not os.path.exists(excel_path):
        raise FileNotFoundError(excel_path)

    # --- 若未传 sheet_name：先列出所有 sheet，再让你输入一个 ---
    if sheet_name is None:
        xls = pd.ExcelFile(excel_path)
        print("检测到的 sheets：")
        for s in xls.sheet_names:
            print(f"  - {s}")
        sheet_name = input("请输入要导入的 sheet 名（精确匹配）：").strip()
        if not sheet_name:
            raise ValueError("sheet_name 不能为空。")

    # --- 读取指定 sheet ---
    df = pd.read_excel(excel_path, sheet_name=sheet_name, engine="openpyxl")

    # 可选：删除全空行
    if drop_all_null_rows:
        df = df.dropna(how="all")

    # 处理列名：保持原列名用于匹配 exclude；同时生成安全列名用于建表/写入
    original_cols = list(df.columns)
    kept_pairs = []
    for col in original_cols:
        if col in exclude_set:
            continue
        kept_pairs.append((col, _sanitize_identifier(str(col))))

    if not kept_pairs:
        raise ValueError("所有列都被排除或为空，无法写入数据库。")

    # 重建一个只保留列的 df，并把列名替换为 sanitize 后的版本
    kept_original = [p[0] for p in kept_pairs]
    kept_sanitized = [p[1] for p in kept_pairs]
    df2 = df.loc[:, kept_original].copy()
    df2.columns = kept_sanitized



    # datetime 转字符串（SQLite 无原生 datetime）
    for c in df2.columns:
        if pd.api.types.is_datetime64_any_dtype(df2[c]):
            df2[c] = df2[c].dt.strftime("%Y-%m-%d %H:%M:%S")

    # --- 写入 SQLite ---
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    # 设置 WAL 相关文件权限为 777
    try:
        os.chmod(db_path, 0o777)
        wal_path = db_path + "-wal"
        shm_path = db_path + "-shm"
        if os.path.exists(wal_path):
            os.chmod(wal_path, 0o777)
        if os.path.exists(shm_path):
            os.chmod(shm_path, 0o777)
    except Exception:
        pass  # 权限设置失败不影响主流程

    try:
        if if_exists not in {"replace", "append", "fail"}:
            raise ValueError('if_exists 必须是 "replace" / "append" / "fail"')

        cur = conn.cursor()

        if if_exists == "replace":
            cur.execute(f'DROP TABLE IF EXISTS "{table_name}"')

        # 如果是 fail，需要检查表是否存在
        if if_exists == "fail":
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            if cur.fetchone():
                raise RuntimeError(f'表 "{table_name}" 已存在，if_exists="fail" 不允许覆盖。')

        # 如果表不存在则建表（append 模式下可能要建）
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        table_exists = cur.fetchone() is not None

        if not table_exists:
            col_defs = []
            for col in df2.columns:
                sql_type = _detect_sqlite_type(df2[col])
                col_defs.append(f'"{col}" {sql_type}')
            create_sql = f'CREATE TABLE "{table_name}" ({", ".join(col_defs)})'
            cur.execute(create_sql)

        # 插入数据
        placeholders = ", ".join(["?"] * len(df2.columns))
        col_list = ", ".join([f'"{c}"' for c in df2.columns])
        insert_sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'

        # pandas 的 NaN -> None
        records = df2.where(pd.notnull(df2), None).values.tolist()
        cur.executemany(insert_sql, records)
        conn.commit()

    finally:
        conn.close()

    return excel_path, sheet_name, kept_sanitized


exclude_cols = ["unicode","显示", "序号", "原释义",     "0_912352941176471",
    "1"]  # 这些列不会写进 sqlite

excel_path, used_sheet, inserted_cols = import_excel_sheet_columns_to_sqlite_via_tk(
    db_path="data/yc.db",
    table_name="口语字",
    # sheet_name="Sheet1",      # 你也可以不传，让它列出来后在终端输入
    exclude_cols=exclude_cols,
    if_exists="replace",
)

print("Excel:", excel_path)
print("Sheet:", used_sheet)
print("写入列:", inserted_cols)
