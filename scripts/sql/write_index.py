import sqlite3
from typing import List, Dict, Any, Optional


def add_index_and_list_indexes(
    db_path: str,
    table_name: str,
    columns: List[str],
    index_type: str = "NORMAL",   # NORMAL | UNIQUE
    index_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    在 SQLite 表上添加索引，然后输出该表所有索引及“类型”(是否 UNIQUE)与列等信息。

    参数：
      - db_path: sqlite 路径
      - table_name: 表名
      - columns: 要建索引的列名列表（支持复合索引）
      - index_type: NORMAL / UNIQUE
      - index_name: 可选，不传则自动生成

    返回：索引信息列表（也会 print）
    """
    if not columns:
        raise ValueError("columns 不能为空。")

    idx_type = index_type.strip().upper()
    if idx_type not in {"NORMAL", "UNIQUE"}:
        raise ValueError('index_type 仅支持 "NORMAL" 或 "UNIQUE"（如需 FTS5，请单独设计）。')

    # 自动生成索引名
    if not index_name:
        cols_part = "_".join(columns)
        index_name = f"idx_{table_name}_{cols_part}_{idx_type.lower()}"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        # 设置 WAL 相关文件权限为 777
        try:
            import os
            os.chmod(db_path, 0o777)
            wal_path = db_path + "-wal"
            shm_path = db_path + "-shm"
            if os.path.exists(wal_path):
                os.chmod(wal_path, 0o777)
            if os.path.exists(shm_path):
                os.chmod(shm_path, 0o777)
        except Exception:
            pass  # 权限设置失败不影响主流程
        cur = conn.cursor()

        cols_sql = ", ".join([f'"{c}"' for c in columns])
        if idx_type == "UNIQUE":
            sql = f'CREATE UNIQUE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({cols_sql})'
        else:
            sql = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({cols_sql})'

        cur.execute(sql)
        conn.commit()

        # 列出该表的索引：PRAGMA index_list / index_info + sqlite_master.sql
        cur.execute(f'PRAGMA index_list("{table_name}")')
        idx_list = cur.fetchall()
        # index_list: (seq, name, unique, origin, partial) 具体字段随版本略有差异，但前三个稳定

        results = []
        for row in idx_list:
            # 兼容不同 sqlite 版本字段数
            seq = row[0]
            name = row[1]
            unique = row[2] if len(row) > 2 else 0

            cur.execute(f'PRAGMA index_info("{name}")')
            info_rows = cur.fetchall()
            # index_info: (seqno, cid, name)
            idx_cols = [r[2] for r in info_rows]

            cur.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                (name,)
            )
            sql_row = cur.fetchone()
            ddl = sql_row[0] if sql_row else None

            results.append({
                "seq": seq,
                "name": name,
                "type": "UNIQUE" if unique else "NORMAL",
                "columns": idx_cols,
                "ddl": ddl,
            })

        # 打印
        print(f'表 "{table_name}" 的索引列表：')
        for r in results:
            print(f'  - {r["name"]}: {r["type"]}, columns={r["columns"]}')
            if r["ddl"]:
                print(f'    ddl: {r["ddl"]}')

        return results

    finally:
        conn.close()

# 添加普通索引（单列）
add_index_and_list_indexes(
    db_path="data/characters.db",
    table_name="characters",
    columns=["攝", "呼", "等", "韻", "入", "調", "清濁", "系", "組", "母", "部位", "方式", "漢字", "釋義", "多聲母", "多等", "多韻", "多調", "多地位標記"],
    index_type="NORMAL"
)

# # 添加唯一索引（复合）
# add_index_and_list_indexes(
#     db_path="data/my.db",
#     table_name="my_table",
#     columns=["省", "市", "县"],
#     index_type="UNIQUE"
# )
