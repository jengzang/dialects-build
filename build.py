import argparse

from source.raw2tsv import convert_all_to_tsv
from source.tsv2sql import write_to_sql, sync_dialects_flags, build_dialect_database, process_phonology_excel

"""
用来前置处理字表，转成tsv，然后写入数据库。
"""


import argparse

# === 主執行函式 ===
def main(args):
    # 1️⃣ 字表轉換
    if 'convert' in args.type:
        convert_all_to_tsv()

    # 2️⃣ 寫入資料庫（admin 或 user）
    # 當 args.type 為空，或包含 needchars/append/update 時執行
    if not args.type or any(x in args.type for x in ['needchars', 'append', 'update']):
        if args.user == 'admin':
            write_to_sql(
                mode='admin',
                write_chars_db='needchars' in args.type,
                append='append' in args.type,
                update='update' in args.type
            )
        elif args.user == 'user':
            write_to_sql(
                mode='user',
                write_chars_db='needchars' in args.type,
                append='append' in args.type,
                update='update' in args.type
            )

    # 3️⃣ 建立 dialect 資料表
    if 'query' in args.type:
        build_dialect_database(mode=args.user)

    # 4️⃣ 同步方言標記
    if 'sync' in args.type:
        from common.config import (QUERY_DB_ADMIN_PATH, QUERY_DB_USER_PATH,
                                   DIALECTS_DB_ADMIN_PATH, DIALECTS_DB_USER_PATH,
                                   CHARACTERS_DB_PATH)
        if args.user == 'admin':
            sync_dialects_flags(
                all_db_path=DIALECTS_DB_ADMIN_PATH,
                query_db_path=QUERY_DB_ADMIN_PATH,
                log_path=CHARACTERS_DB_PATH
            )
        else:  # user
            sync_dialects_flags(
                all_db_path=DIALECTS_DB_USER_PATH,
                query_db_path=QUERY_DB_USER_PATH,
                log_path=CHARACTERS_DB_PATH
            )

    # 5️⃣ 寫入中古地位表
    if 'chars' in args.type:
        process_phonology_excel()


# === 命令列參數設定 ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="📘 字表預處理工具，支持各種字表格式轉換、數據庫寫入。"
    )

    # 使用者資料庫類型（預設為 admin）
    parser.add_argument(
        '-u', '--user',
        choices=['admin', 'user'],
        default='admin',
        help="👤 指定要寫入的資料庫類型：admin（預設）或 user"
    )

    # 要執行的處理功能（可多選）
    parser.add_argument(
        '-t', '--type',
        nargs='*',
        choices=['convert', 'chars', 'query', 'sync', 'needchars', 'append', 'update'],
        default=[],
        help=(
            "⚙️ 要執行的處理功能（可多選）：\n"
            "  convert      → 字表轉TSV\n"
            "  needchars     → 需要重寫中古地位數據庫characters.db\n"
            "  query        → 寫方言查詢數據庫query.db\n"
            "  sync         → 存儲標記\n"
            "  chars    → 寫中古地位數據庫characters.db\n"
            "  append       → 寫入方式為添加(從jengzang補充裡面的“待更新”列中添加，慎用)\n"
            "  update       → 增量更新模式(從pull_yindian目錄讀取TSV文件並更新到數據庫中)\n"
        )
    )

    args = parser.parse_args()
    main(args)
