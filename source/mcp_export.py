import argparse
import io
import json
import re
import shutil
import subprocess
import tarfile
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional

from common.config import (
    ALL_SHEET_DIR,
    ALL_YINDIAN_DIR,
    ALL_YINDIAN_MAP_FILE,
    MCP_CACHE_DIR,
    MCP_REPO_URL,
    MCP_SOURCEFORGE_CODE_URL,
    MCP_SHEET_HISTORY_MAP_FILE,
    MCP_SHEET_PATH,
    MCP_TARGET_FOLDER,
    MCP_VERSION_FILE,
    PULL_YINDIAN_DIR,
)


def run_git_command(args, cwd=None, capture_output=False, text=True, encoding='utf-8'):
    return subprocess.run(
        ['git', *args],
        cwd=cwd,
        check=True,
        text=text,
        encoding=encoding if text else None,
        capture_output=capture_output,
    )


def ensure_mcp_cache():
    if not MCP_CACHE_DIR.exists():
        print('🚀 Initializing git cache...')
        run_git_command(['clone', '--filter=blob:none', '--no-checkout', MCP_REPO_URL, str(MCP_CACHE_DIR)])

    run_git_command(['config', 'core.quotePath', 'false'], cwd=MCP_CACHE_DIR)
    index_lock = MCP_CACHE_DIR / '.git/index.lock'
    if index_lock.exists():
        index_lock.unlink()


def clear_target_dir(target_dir: Path, preserve_names=None):
    preserve_names = set(preserve_names or [])
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in target_dir.iterdir():
        if child.name in preserve_names:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def clear_pull_yindian_dir():
    clear_target_dir(PULL_YINDIAN_DIR, preserve_names={'.last_commit'})


def load_last_commit():
    if not MCP_VERSION_FILE.exists():
        return None
    text = MCP_VERSION_FILE.read_text(encoding='utf-8', errors='ignore')
    value = text.strip()
    return value or None


def has_exported_tsv_files():
    if not PULL_YINDIAN_DIR.exists():
        return False
    return any(path.suffix == '.tsv' for path in PULL_YINDIAN_DIR.iterdir() if path.is_file())


def list_full_export_files(latest_commit):
    result = run_git_command(
        ['ls-tree', '-r', '--name-only', latest_commit, '--', MCP_TARGET_FOLDER],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip().endswith('.tsv')]


def list_diff_export_files(last_commit, latest_commit):
    result = run_git_command(
        ['diff', '--name-only', last_commit, latest_commit, '--', MCP_TARGET_FOLDER],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip().endswith('.tsv')]


def load_tar_member_bytes(commit, target_folder):
    target_path = target_folder
    try:
        archive_bytes = run_git_command(
            ['archive', '--format=tar', commit, target_path],
            cwd=MCP_CACHE_DIR,
            capture_output=True,
            text=False,
        ).stdout
    except subprocess.CalledProcessError:
        target_path = 'tools/tables'
        archive_bytes = run_git_command(
            ['archive', '--format=tar', commit, target_path],
            cwd=MCP_CACHE_DIR,
            capture_output=True,
            text=False,
        ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode='r:') as tar:
        extracted = {}
        for member in tar.getmembers():
            if not (member.isfile() and member.name.endswith('.tsv')):
                continue
            fileobj = tar.extractfile(member)
            if fileobj is None:
                continue
            extracted[Path(member.name).name] = fileobj.read()
        return extracted


def export_all_history_tables():
    ensure_mcp_cache()

    print('📡 Fetching MCPDict latest commit for full history scan...')
    run_git_command(['fetch', 'origin', 'master', '--quiet'], cwd=MCP_CACHE_DIR)

    log_output = run_git_command(
        ['log', '--format=%H\t%ct', '--all', '--', MCP_TARGET_FOLDER],
        cwd=MCP_CACHE_DIR,
        capture_output=True,
    ).stdout
    commit_lines = [line.strip() for line in log_output.splitlines() if line.strip()]
    print(f'🧭 Scanning {len(commit_lines)} history commits...')

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

    print(f'🗂️ Collected {len(latest_by_name)} unique TSV names from {scanned} commits')

    clear_target_dir(ALL_YINDIAN_DIR, preserve_names={ALL_YINDIAN_MAP_FILE.name})

    commits_needed = sorted({meta['commit'] for meta in latest_by_name.values()})
    tar_cache = {}
    for idx, commit in enumerate(commits_needed, start=1):
        print(f'📦 Loading archive {idx}/{len(commits_needed)}: {commit[:7]}')
        tar_cache[commit] = load_tar_member_bytes(commit, MCP_TARGET_FOLDER)

    history_map = {}
    for idx, file_name in enumerate(sorted(latest_by_name), start=1):
        meta = latest_by_name[file_name]
        commit_files = tar_cache.get(meta['commit'], {})
        if file_name not in commit_files:
            raise RuntimeError(f'歷史導出缺少文件：{file_name} @ {meta["commit"]}')
        destination = ALL_YINDIAN_DIR / file_name
        destination.write_bytes(commit_files[file_name])
        history_map[file_name] = {
            'path': meta['path'],
            'commit': meta['commit'],
            'commit_time': meta['commit_time'],
            'commit_datetime': datetime.fromtimestamp(meta['commit_time'], tz=timezone.utc).isoformat(),
        }
        if idx <= 20 or idx % 200 == 0:
            print(f'  [+] {file_name}')

    ALL_YINDIAN_MAP_FILE.write_text(
        json.dumps(history_map, ensure_ascii=False, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    print(f'✨ All-history export done! files={len(history_map)} map={ALL_YINDIAN_MAP_FILE}')


def export_mcp_tables(mode):
    ensure_mcp_cache()

    print('📡 Fetching MCPDict latest commit...')
    run_git_command(['fetch', 'origin', 'master', '--quiet'], cwd=MCP_CACHE_DIR)
    latest_commit = run_git_command(['rev-parse', 'origin/master'], cwd=MCP_CACHE_DIR, capture_output=True).stdout.strip()

    last_commit = load_last_commit()

    if mode == 'full' or not last_commit:
        if mode == 'diff' and not last_commit:
            print('⚠️ 未找到 .last_commit，diff 模式自动退回 full 导出')
        files_to_export = list_full_export_files(latest_commit)
        print('⚠️ Mode: Full Export')
    else:
        print(f'🔍 Diffing: {last_commit} -> {latest_commit}')
        files_to_export = list_diff_export_files(last_commit, latest_commit)

    if mode == 'full' and not has_exported_tsv_files() and not files_to_export:
        raise RuntimeError('Full 模式未列出任何 TSV，且 pull_yindian 目錄為空，拒絕誤報 All up to date')

    if not files_to_export:
        print('✅ All up to date.')
        return

    clear_pull_yindian_dir()
    print(f'🚚 Extracting {len(files_to_export)} files...')

    archive_bytes = run_git_command(
        ['archive', '--format=tar', latest_commit, MCP_TARGET_FOLDER],
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
                raise RuntimeError(f'archive 中找不到 {file_name}')
            extracted = tar.extractfile(member)
            if extracted is None:
                raise RuntimeError(f'無法從 archive 讀取 {file_name}')
            destination = PULL_YINDIAN_DIR / file_name
            destination.write_bytes(extracted.read())
            extracted_names.append(file_name)
            print(f'  [+] {file_name}')

    if len(extracted_names) != len(files_to_export):
        raise RuntimeError(f'導出文件數不一致：預期 {len(files_to_export)}，實際 {len(extracted_names)}')

    MCP_VERSION_FILE.write_text(f'{latest_commit}\n', encoding='ascii')
    print(f'✨ Done! Version updated to {latest_commit[:7]}')


def build_sheet_history_entries(sheet_path=MCP_SHEET_PATH):
    encoded_path = urllib.parse.quote('/' + sheet_path)
    url = f'{MCP_SOURCEFORGE_CODE_URL}/master/log/?path={encoded_path}'
    html = run_curl_text(url)
    row_pattern = re.compile(
        r'revision="(?P<commit>[0-9a-f]{40})".*?'
        r'<td style="vertical-align: text-top">\s*(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*</td>.*?'
        r'href="/p/mcpdict/code/ci/(?P=commit)/tree/' + re.escape(sheet_path) + r'\?format=raw"',
        re.S,
    )
    commits = []
    seen = set()
    for match in row_pattern.finditer(html):
        commit = match.group('commit')
        if commit in seen:
            continue
        seen.add(commit)
        dt = datetime.strptime(match.group('date'), '%Y-%m-%d %H:%M:%S')
        commits.append(
            {
                'commit': commit,
                'commit_time': int(dt.replace(tzinfo=timezone.utc).timestamp()),
                'blob_path': sheet_path,
            }
        )
    return commits


def run_curl_bytes(url):
    command = ['curl', '--http1.1', '-L', '--silent', '--show-error', '--fail', url]
    try:
        result = subprocess.run(command, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        result = subprocess.run(command + ['--retry', '3', '--retry-all-errors'], check=True, capture_output=True)
    return result.stdout


def run_curl_text(url):
    return run_curl_bytes(url).decode('utf-8', errors='ignore')


def load_blob_bytes(commit, blob_path):
    quoted_path = urllib.parse.quote(blob_path)
    url = f'{MCP_SOURCEFORGE_CODE_URL}/{commit}/tree/{quoted_path}?format=raw'
    return run_curl_bytes(url)


def format_sheet_export_name(commit_time: int):
    dt = datetime.fromtimestamp(commit_time, tz=timezone.utc)
    return f'漢字音典字表檔案（長期更新）-{dt.strftime("%Y%m%d-%H%M%S")}.xlsx'


def export_all_sheet_history(
    history_entries: Optional[Iterable[dict]] = None,
    blob_loader: Optional[Callable[[str, str], bytes]] = None,
    target_dir: Optional[Path] = None,
    history_map_file: Optional[Path] = None,
):
    history_entries = list(history_entries if history_entries is not None else build_sheet_history_entries())
    blob_loader = blob_loader or load_blob_bytes
    target_dir = target_dir or ALL_SHEET_DIR
    history_map_file = history_map_file or MCP_SHEET_HISTORY_MAP_FILE

    clear_target_dir(target_dir, preserve_names={history_map_file.name})

    history_map = {}
    for idx, entry in enumerate(sorted(history_entries, key=lambda item: item['commit_time']), start=1):
        blob_path = entry.get('blob_path') or MCP_SHEET_PATH
        payload = blob_loader(entry['commit'], blob_path)
        filename = format_sheet_export_name(entry['commit_time'])
        destination = target_dir / filename
        destination.write_bytes(payload)
        history_map[filename] = {
            'commit': entry['commit'],
            'commit_time': entry['commit_time'],
            'commit_datetime': datetime.fromtimestamp(entry['commit_time'], tz=timezone.utc).isoformat(),
            'path': blob_path,
        }
        print(f'  [{idx}/{len(history_entries)}] {filename}')

    history_map_file.write_text(
        json.dumps(history_map, ensure_ascii=False, indent=2, sort_keys=True),
        encoding='utf-8',
    )
    print(f'✨ Sheet history export done! files={len(history_map)} map={history_map_file}')


def export_mcp_assets(mode):
    if mode == 'all':
        export_all_history_tables()
    elif mode == 'all_sheet':
        export_all_sheet_history()
    else:
        export_mcp_tables(mode)
