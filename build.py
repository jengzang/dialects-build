import argparse
import shutil
import subprocess
from pathlib import Path

"""
用来前置处理字表，转成tsv，然后写入数据库。
"""


MCP_REPO_URL = "https://github.com/osfans/MCPDict.git"
MCP_TARGET_FOLDER = "tools/tables/output"
PULL_YINDIAN_DIR = Path("data/raw/pull_yindian")
MCP_CACHE_DIR = Path("data/raw/.git_cache")
MCP_VERSION_FILE = PULL_YINDIAN_DIR / ".last_commit"


def run_git_command(args, cwd=None, capture_output=False):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        encoding="utf-8",
        capture_output=capture_output,
    )


def ensure_mcp_cache():
    if not MCP_CACHE_DIR.exists():
        print("🚀 Initializing git cache...")
        run_git_command(["clone", "--filter=blob:none", "--no-checkout", MCP_REPO_URL, str(MCP_CACHE_DIR)])

    run_git_command(["config", "core.quotePath", "false"], cwd=MCP_CACHE_DIR)
    index_lock = MCP_CACHE_DIR / ".git/index.lock"
    if index_lock.exists():
        index_lock.unlink()


def list_full_export_files(latest_commit):
    result = run_git_command(
        ["ls-tree", "-r", "--name-only", latest_commit, "--", f"{MCP_TARGET_FOLDER}/*.tsv"],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def list_diff_export_files(last_commit, latest_commit):
    result = run_git_command(
        ["diff", "--name-only", last_commit, latest_commit, "--", f"{MCP_TARGET_FOLDER}/*.tsv"],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def clear_pull_yindian_dir():
    PULL_YINDIAN_DIR.mkdir(parents=True, exist_ok=True)
    for child in PULL_YINDIAN_DIR.iterdir():
        if child.name == ".last_commit":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def export_mcp_tables(mode):
    ensure_mcp_cache()

    print("📡 Fetching MCPDict latest commit...")
    run_git_command(["fetch", "origin", "master", "--quiet"], cwd=MCP_CACHE_DIR)
    latest_commit = run_git_command(["rev-parse", "origin/master"], cwd=MCP_CACHE_DIR, capture_output=True).stdout.strip()

    last_commit = None
    if MCP_VERSION_FILE.exists():
        last_commit = MCP_VERSION_FILE.read_text(encoding="utf-8").strip() or None

    if mode == "full" or not last_commit:
        if mode == "diff" and not last_commit:
            print("⚠️ 未找到 .last_commit，diff 模式自动退回 full 导出")
        files_to_export = list_full_export_files(latest_commit)
        print("⚠️ Mode: Full Export")
    else:
        print(f"🔍 Diffing: {last_commit} -> {latest_commit}")
        files_to_export = list_diff_export_files(last_commit, latest_commit)

    if not files_to_export:
        print("✅ All up to date.")
        return

    clear_pull_yindian_dir()
    print(f"🚚 Extracting {len(files_to_export)} files...")
    for relative_path in files_to_export:
        file_name = Path(relative_path).name
        destination = PULL_YINDIAN_DIR / file_name
        content = run_git_command(["show", f"{latest_commit}:{relative_path}"], cwd=MCP_CACHE_DIR, capture_output=True).stdout
        destination.write_text(content, encoding="utf-8")
        print(f"  [+] {file_name}")

    MCP_VERSION_FILE.write_text(f"{latest_commit}\n", encoding="ascii")
    print(f"✨ Done! Version updated to {latest_commit[:7]}")


# === 主執行函式 ===
def main(args):
    from source.tsv2sql import write_to_sql, sync_dialects_flags, build_dialect_database, process_phonology_excel

    if args.mcp_mode:
        export_mcp_tables(args.mcp_mode)
        if not args.type:
            return

    if 'convert' in args.type:
        from source.raw2tsv import convert_all_to_tsv

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

    parser.add_argument(
        '-m', '--mcp', '--yindian',
        dest='mcp_mode',
        choices=['full', 'diff'],
        default=None,
        help=(
            "📥 拉取 MCPDict 的音典 TSV 到 data/raw/pull_yindian：\n"
            "  full         → 全量导出\n"
            "  diff         → 增量导出（基于 .last_commit）\n"
        )
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
