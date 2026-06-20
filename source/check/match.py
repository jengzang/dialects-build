from pathlib import Path
import sqlite3

from common.config import PROCESSED_DATA_DIR, YINDIAN_DATA_DIR, QUERY_DB_PATH
from source.match_fromdb import get_tsvs


DISPLAY_WIDTH = 24
PATH_WIDTH = 72
PART_WIDTH = 8
STATUS_WIDTH = 10


def _truncate(text, width):
    text = '' if text is None else str(text)
    if len(text) <= width:
        return text.ljust(width)
    if width <= 1:
        return text[:width]
    return (text[:width - 1] + '…').ljust(width)


def _iter_tsv_paths():
    roots = [Path(YINDIAN_DATA_DIR), Path(PROCESSED_DATA_DIR)]
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob('*.tsv')):
            if path.is_file():
                yield path


def _check_query_db_ready(query_db_path):
    db_path = Path(query_db_path)
    if not db_path.exists():
        return False, f'找不到 query 数据库: {db_path}'

    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dialects'"
            ).fetchone()
    except sqlite3.Error as exc:
        return False, f'无法读取 query 数据库: {db_path} | {exc}'

    if not row:
        return False, f'query 数据库中缺少 dialects 表: {db_path}'

    return True, ''


def _check_one_file(path, query_db_path):
    matched_paths, locations, partitions = get_tsvs(single=str(path), query_db_path=query_db_path)
    stem = path.stem
    source = path.parent.name

    matched = [loc for loc in locations if loc != '_']
    parts = [part for part in partitions if part]

    if matched:
        return {
            'source': source,
            'filename': stem,
            'matched': matched[0],
            'partition': parts[0] if parts else '',
            'status': 'OK',
            'path': matched_paths[0] if matched_paths else str(path),
        }

    return {
        'source': source,
        'filename': stem,
        'matched': '',
        'partition': '',
        'status': 'MISS',
        'path': str(path),
    }


def run_match_check(query_db_path=QUERY_DB_PATH):
    rows = []
    total = 0
    ok_count = 0
    miss_count = 0

    print('\n============================================================')
    print('步驟0：模擬最終 TSV 文件名 -> 簡稱 匹配結果...')
    print('============================================================')
    print(f'   query_db: {query_db_path}')
    print(f'   yindian:  {YINDIAN_DATA_DIR}')
    print(f'   processed:{PROCESSED_DATA_DIR}')
    print('   說明: 直接調用 get_tsvs(single=...)，與最終寫庫匹配鏈路保持一致')

    ready, message = _check_query_db_ready(query_db_path)
    if not ready:
        print(f'\n❌ 無法執行 match 檢查：{message}')
        print('   先运行：python build.py -t query')
        return rows

    for path in _iter_tsv_paths():
        total += 1
        row = _check_one_file(path, query_db_path=query_db_path)
        rows.append(row)
        if row['status'] == 'OK':
            ok_count += 1
        else:
            miss_count += 1

    print(f'\n共掃描 {total} 個 TSV 文件')
    print(f'匹配成功 {ok_count} 個')
    print(f'匹配失敗 {miss_count} 個')

    if not rows:
        print('\n⚠️ 沒有找到任何 TSV 文件。')
        return rows

    print('\n【匹配明細】')
    header = (
        f"{'來源'.ljust(12)} "
        f"{'文件名'.ljust(DISPLAY_WIDTH)} "
        f"{'最終簡稱'.ljust(DISPLAY_WIDTH)} "
        f"{'分區'.ljust(PART_WIDTH)} "
        f"{'狀態'.ljust(STATUS_WIDTH)} "
        f"路徑"
    )
    print(header)
    print('-' * max(110, len(header)))

    for row in rows:
        print(
            f"{row['source'].ljust(12)} "
            f"{_truncate(row['filename'], DISPLAY_WIDTH)} "
            f"{_truncate(row['matched'], DISPLAY_WIDTH)} "
            f"{_truncate(row['partition'], PART_WIDTH)} "
            f"{row['status'].ljust(STATUS_WIDTH)} "
            f"{_truncate(row['path'], PATH_WIDTH)}"
        )

    miss_rows = [row for row in rows if row['status'] != 'OK']
    if miss_rows:
        print('\n【未匹配文件】')
        for row in miss_rows:
            print(f"  - {row['path']}")

    return rows
