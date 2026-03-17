#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将 scripts/fanwan.sql 中的 INSERT 数据导出为 Excel。
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd


INSERT_HEADER_RE = re.compile(
    r"INSERT\s+INTO\s+`(?P<table>[^`]+)`\s*\((?P<columns>[^)]+)\)\s*VALUES",
    re.IGNORECASE,
)


def parse_insert_header(sql_text: str) -> tuple[str, list[str]]:
    match = INSERT_HEADER_RE.search(sql_text)
    if not match:
        raise ValueError("未在 SQL 文件中找到 INSERT 头部。")

    table_name = match.group("table")
    columns = [col.strip().strip("`") for col in match.group("columns").split(",")]
    return table_name, columns


def create_sqlite_table(conn: sqlite3.Connection, table_name: str, columns: list[str]) -> None:
    quoted_columns = ", ".join(f'"{column}" TEXT' for column in columns)
    conn.execute(f'DROP TABLE IF EXISTS "{table_name}"')
    conn.execute(f'CREATE TABLE "{table_name}" ({quoted_columns})')


def export_fanwan_sql_to_xlsx(sql_path: Path, xlsx_path: Path) -> tuple[int, int]:
    sql_text = sql_path.read_text(encoding="utf-8")
    table_name, columns = parse_insert_header(sql_text)

    with sqlite3.connect(":memory:") as conn:
        create_sqlite_table(conn, table_name, columns)
        conn.executescript(sql_text)

        query = f'SELECT * FROM "{table_name}" ORDER BY CAST("id" AS INTEGER)'
        df = pd.read_sql_query(query, conn)

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=table_name, index=False)

    return len(df), len(df.columns)


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    sql_path = project_root / "scripts" / "fanwan.sql"
    xlsx_path = project_root / "data" / "fanwan.xlsx"

    row_count, column_count = export_fanwan_sql_to_xlsx(sql_path, xlsx_path)
    print(f"SQL 文件: {sql_path}")
    print(f"输出文件: {xlsx_path}")
    print(f"工作表: YFanwan")
    print(f"行数: {row_count}")
    print(f"列数: {column_count}")


if __name__ == "__main__":
    main()
