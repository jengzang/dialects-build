import argparse
import textwrap

"""
用来前置处理字表，转成tsv，然后写入数据库。
"""


from source.mcp_export import export_mcp_assets

# === argparse 格式化器 ===
class SmartFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawTextHelpFormatter
):
    pass


# === 主執行函式 ===
def main(args):
    args.type = args.type or []
    args.check = args.check or []

    # deny 依赖 sheet；允许用户直接写 -c deny
    if 'deny' in args.check and 'sheet' not in args.check:
        args.check.insert(0, 'sheet')

    if args.mcp_mode:
        export_mcp_assets(args.mcp_mode)

        # 单独使用 -m 时，只拉取音典数据，不继续写库或检查
        if not args.type and not args.check:
            return

    from source.tsv2sql import (
        write_to_sql,
        sync_dialects_flags,
        build_dialect_database,
        process_phonology_excel,
        check_han_abbreviation_changes,
    )
    from source.tone_check import run_tone_check

    if 'convert' in args.type:
        from source.raw2tsv import convert_all_to_tsv

    # 1️⃣ 字表轉換
    if 'convert' in args.type:
        convert_all_to_tsv()

    # 2️⃣ 字表检查
    if 'sheet' in args.check:
        check_status_filter = '不收' if 'deny' in args.check else None
        check_han_abbreviation_changes(status_filter=check_status_filter)

    # 3️⃣ 聲調欄检查
    if 'tone' in args.check:
        run_tone_check()

    # 4️⃣ 寫入資料庫（admin 或 user）
    # 保持原有默认行为：
    #   python build.py                  → 默认写库
    #   python build.py -t needchars      → 重写中古地位数据库
    #   python build.py -t append         → 追加写入
    #   python build.py -t update         → 增量更新
    #
    # 但避免：
    #   python build.py -c sheet          → 意外触发默认写库
    should_write_default = (
        not args.mcp_mode
        and not args.type
        and not args.check
    )
    should_write_special = any(x in args.type for x in ['needchars', 'append', 'update'])

    if should_write_default or should_write_special:
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

    # 5️⃣ 建立 dialect 資料表
    if 'query' in args.type:
        build_dialect_database(mode=args.user)

    # 6️⃣ 同步方言標記
    if 'sync' in args.type:
        from common.config import (
            QUERY_DB_ADMIN_PATH,
            QUERY_DB_USER_PATH,
            DIALECTS_DB_ADMIN_PATH,
            DIALECTS_DB_USER_PATH,
            CHARACTERS_DB_PATH,
        )

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

    # 7️⃣ 寫入中古地位表
    if 'chars' in args.type:
        process_phonology_excel()


# === 命令列參數設定 ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="build.py",
        description="📘 字表预处理工具：支持音典数据拉取、字表转换、数据库写入与数据检查。",
        formatter_class=SmartFormatter,
        epilog=textwrap.dedent("""\
        示例:
          python build.py
          python build.py -m full
          python build.py -m diff -t update
          python build.py -t convert chars query
          python build.py -c sheet
          python build.py -c deny
          python build.py -c sheet deny
          python build.py -c tone
        """)
    )

    # 使用者資料庫類型（預設為 admin）
    parser.add_argument(
        '-u', '--user',
        choices=['admin', 'user'],
        default='admin',
        metavar='USER',
        help='指定写入数据库：admin 或 user'
    )

    # 拉取 MCPDict 音典資料
    pull_group = parser.add_argument_group('音典数据拉取')
    pull_group.add_argument(
        '-m', '--mcp', '--yindian',
        dest='mcp_mode',
        choices=['full', 'diff', 'all', 'all_sheet'],
        default=None,
        metavar='MODE',
        help=textwrap.dedent("""\
        拉取 MCPDict 的音典数据：
          full       全量导出 tools/tables/output/*.tsv 到 data/raw/pull_yindian/
          diff       增量导出，基于 .last_commit
          all        遍历历史提交，按文件名保留最新 TSV，输出到 data/raw/all_yindian/
          all_sheet  导出历史提交中的「汉字音典字表」xlsx 到 data/raw/all_sheet/

        说明：
          单独使用 -m 时，只拉取数据，不写库；
          若同时传入 -t 或 -c，则拉取完成后继续执行对应流程。
        """)
    )

    # 要執行的處理功能（可多選）
    task_group = parser.add_argument_group('处理流程')
    task_group.add_argument(
        '-t', '--type',
        nargs='+',
        choices=[
            'convert',
            'chars',
            'query',
            'sync',
            'needchars',
            'append',
            'update',
        ],
        default=[],
        metavar='TASK',
        help=textwrap.dedent("""\
        执行处理任务，可多选：
          convert    字表转 TSV
          chars      写中古地位数据库 characters.db
          needchars  重写中古地位数据库 characters.db
          query      写方言查询数据库 query.db
          sync       同步方言标记
          append     追加写入，从补充表“待更新”列中添加，慎用
          update     增量更新，从 pull_yindian/ 读取 TSV 并更新数据库
        """)
    )

    # 要執行的檢查功能（可多選）
    check_group = parser.add_argument_group('检查流程')
    check_group.add_argument(
        '-c', '--check',
        nargs='*',
        choices=[
            'sheet',
            'deny',
            'tone',
        ],
        default=None,
        metavar='CHECK',
        help=textwrap.dedent("""\
        执行检查任务，可多选：
          sheet      对比 old/ 与当前音典文件，输出简称新增、改名、删除与同坐标冲突
          deny       只输出「是否有人在做=不收」的记录，默认配合 sheet 使用
          tone       检查 xlsx 声调栏，列出异常调类与拆解失败值

        说明：
          -c              等价于 -c sheet
          -c deny         等价于 -c sheet deny
          -c sheet deny   检查字表变动，但只输出“不收”记录
          -c tone         只检查声调栏
        """)
    )

    args = parser.parse_args()

    # 让 python build.py -c 等价于 python build.py -c sheet
    if args.check == []:
        args.check = ['sheet']

    main(args)