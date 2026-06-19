import argparse
from datetime import datetime, timezone
import json
import shutil
import subprocess
import io
import tarfile
from pathlib import Path

"""
用来前置处理字表，转成tsv，然后写入数据库。
"""


from common.config import (
    MCP_REPO_URL,
    MCP_TARGET_FOLDER,
    PULL_YINDIAN_DIR,
    ALL_YINDIAN_DIR,
    MCP_CACHE_DIR,
    MCP_VERSION_FILE,
    ALL_YINDIAN_MAP_FILE,
)


def run_git_command(args, cwd=None, capture_output=False, text=True, encoding="utf-8"):
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=text,
        encoding=encoding if text else None,
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
        ["ls-tree", "-r", "--name-only", latest_commit, "--", MCP_TARGET_FOLDER],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip().endswith('.tsv')]


def list_diff_export_files(last_commit, latest_commit):
    result = run_git_command(
        ["diff", "--name-only", last_commit, latest_commit, "--", MCP_TARGET_FOLDER],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip().endswith('.tsv')]


def clear_pull_yindian_dir():
    PULL_YINDIAN_DIR.mkdir(parents=True, exist_ok=True)
    for child in PULL_YINDIAN_DIR.iterdir():
        if child.name == ".last_commit":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def load_last_commit():
    if not MCP_VERSION_FILE.exists():
        return None
    text = MCP_VERSION_FILE.read_text(encoding="utf-8", errors="ignore")
    value = text.strip()
    return value or None


def has_exported_tsv_files():
    if not PULL_YINDIAN_DIR.exists():
        return False
    return any(path.suffix == '.tsv' for path in PULL_YINDIAN_DIR.iterdir() if path.is_file())


def clear_target_dir(target_dir, preserve_names=None):
    preserve_names = set(preserve_names or [])
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in target_dir.iterdir():
        if child.name in preserve_names:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def load_tar_member_bytes(commit, target_folder):
    target_path = target_folder
    try:
        archive_bytes = run_git_command(
            [
                "archive",
                "--format=tar",
                commit,
                target_path,
            ],
            cwd=MCP_CACHE_DIR,
            capture_output=True,
            text=False,
        ).stdout
    except subprocess.CalledProcessError:
        target_path = "tools/tables"
        archive_bytes = run_git_command(
            [
                "archive",
                "--format=tar",
                commit,
                target_path,
            ],
            cwd=MCP_CACHE_DIR,
            capture_output=True,
            text=False,
        ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:') as tar:
        return {
            Path(member.name).name: tar.extractfile(member).read()
            for member in tar.getmembers()
            if member.isfile() and member.name.endswith('.tsv') and tar.extractfile(member) is not None
        }


def export_all_history_tables():
    ensure_mcp_cache()

    print("📡 Fetching MCPDict latest commit for full history scan...")
    run_git_command(["fetch", "origin", "master", "--quiet"], cwd=MCP_CACHE_DIR)

    log_output = run_git_command(
        ["log", "--format=%H\t%ct", "--all", "--", MCP_TARGET_FOLDER],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
    ).stdout
    commit_lines = [line.strip() for line in log_output.splitlines() if line.strip()]
    print(f"🧭 Scanning {len(commit_lines)} history commits...")

    latest_by_name = {}
    scanned = 0
    for line in commit_lines:
        commit, commit_ts = line.split('\t', 1)
        files = list_full_export_files(commit)
        scanned += 1
        for relative_path in files:
            file_name = Path(relative_path).name
            if file_name in latest_by_name:
                continue
            latest_by_name[file_name] = {
                'path': relative_path,
                'commit': commit,
                'commit_time': int(commit_ts),
            }

    print(f"🗂️ Collected {len(latest_by_name)} unique TSV names from {scanned} commits")

    clear_target_dir(ALL_YINDIAN_DIR, preserve_names={ALL_YINDIAN_MAP_FILE.name})

    commits_needed = sorted({meta['commit'] for meta in latest_by_name.values()})
    tar_cache = {}
    for idx, commit in enumerate(commits_needed, start=1):
        print(f"📦 Loading archive {idx}/{len(commits_needed)}: {commit[:7]}")
        tar_cache[commit] = load_tar_member_bytes(commit, MCP_TARGET_FOLDER)

    history_map = {}
    for idx, file_name in enumerate(sorted(latest_by_name), start=1):
        meta = latest_by_name[file_name]
        commit_files = tar_cache.get(meta['commit'], {})
        if file_name not in commit_files:
            raise RuntimeError(f"歷史導出缺少文件：{file_name} @ {meta['commit']}")
        destination = ALL_YINDIAN_DIR / file_name
        destination.write_bytes(commit_files[file_name])
        history_map[file_name] = {
            'path': meta['path'],
            'commit': meta['commit'],
            'commit_time': meta['commit_time'],
            'commit_datetime': datetime.fromtimestamp(meta['commit_time'], tz=timezone.utc).isoformat(),
        }
        if idx <= 20 or idx % 200 == 0:
            print(f"  [+] {file_name}")

    ALL_YINDIAN_MAP_FILE.write_text(
        json.dumps(history_map, ensure_ascii=False, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    print(f"✨ All-history export done! files={len(history_map)} map={ALL_YINDIAN_MAP_FILE}")


def export_mcp_tables(mode):
    ensure_mcp_cache()

    print("📡 Fetching MCPDict latest commit...")
    run_git_command(["fetch", "origin", "master", "--quiet"], cwd=MCP_CACHE_DIR)
    latest_commit = run_git_command(["rev-parse", "origin/master"], cwd=MCP_CACHE_DIR, capture_output=True).stdout.strip()

    last_commit = load_last_commit()

    if mode == "full" or not last_commit:
        if mode == "diff" and not last_commit:
            print("⚠️ 未找到 .last_commit，diff 模式自动退回 full 导出")
        files_to_export = list_full_export_files(latest_commit)
        print("⚠️ Mode: Full Export")
    else:
        print(f"🔍 Diffing: {last_commit} -> {latest_commit}")
        files_to_export = list_diff_export_files(last_commit, latest_commit)

    if mode == 'full' and not has_exported_tsv_files() and not files_to_export:
        raise RuntimeError("Full 模式未列出任何 TSV，且 pull_yindian 目錄為空，拒絕誤報 All up to date")

    if not files_to_export:
        print("✅ All up to date.")
        return

    clear_pull_yindian_dir()
    print(f"🚚 Extracting {len(files_to_export)} files...")

    archive_bytes = run_git_command(
        [
            "archive",
            "--format=tar",
            latest_commit,
            MCP_TARGET_FOLDER,
        ],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
        text=False,
    ).stdout

    extracted_names = []
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:') as tar:
        member_map = {
            Path(member.name).name: member
            for member in tar.getmembers()
            if member.isfile() and member.name.endswith('.tsv')
        }
        for relative_path in files_to_export:
            file_name = Path(relative_path).name
            member = member_map.get(file_name)
            if member is None:
                raise RuntimeError(f"archive 中找不到 {file_name}")
            extracted = tar.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"無法從 archive 讀取 {file_name}")
            destination = PULL_YINDIAN_DIR / file_name
            destination.write_bytes(extracted.read())
            extracted_names.append(file_name)
            print(f"  [+] {file_name}")

    if len(extracted_names) != len(files_to_export):
        raise RuntimeError(
            f"導出文件數不一致：預期 {len(files_to_export)}，實際 {len(extracted_names)}"
        )

    MCP_VERSION_FILE.write_text(f"{latest_commit}\n", encoding="ascii")
    print(f"✨ Done! Version updated to {latest_commit[:7]}")


# === 主執行函式 ===
def main(args):
    from source.tsv2sql import (
        write_to_sql,
        sync_dialects_flags,
        build_dialect_database,
        process_phonology_excel,
        check_han_abbreviation_changes,
    )

    if args.mcp_mode:
        if args.mcp_mode == 'all':
            export_all_history_tables()
        else:
            export_mcp_tables(args.mcp_mode)
        if not args.type:
            return

    if 'convert' in args.type:
        from source.raw2tsv import convert_all_to_tsv

    # 1️⃣ 字表轉換
    if 'convert' in args.type:
        convert_all_to_tsv()

    if 'check' in args.type:
        check_status_filter = '不收' if 'deny' in args.type else None
        check_han_abbreviation_changes(status_filter=check_status_filter)

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
        choices=['full', 'diff', 'all'],
        default=None,
        help=(
            "📥 拉取 MCPDict 的音典 TSV 到 data/raw/pull_yindian（单独使用时只拉取，不写库）：\n"
            "  full         → 全量导出\n"
            "  diff         → 增量导出（基于 .last_commit）\n"
            "  all          → 遍歷歷史提交，按文件名保留最新版本，輸出到 data/raw/all_yindian/\n"
            "  若同时传入 -t，则拉取完成后继续执行对应处理流程\n"
        )
    )

    # 要執行的處理功能（可多選）
    parser.add_argument(
        '-t', '--type',
        nargs='*',
        choices=['convert', 'chars', 'query', 'sync', 'needchars', 'append', 'update', 'check', 'deny'],
        default=[],
        help=(
            "⚙️ 要執行的處理功能（可多選）：\n"
            "  convert      → 字表轉TSV\n"
            "  check        → 對比 old/ 與當前音典檔案，輸出簡稱新增/改名/刪除與同坐標衝突\n"
            "  deny         → 僅配合 check 使用，只輸出 是否有人在做=不收 的記錄\n"
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
