from pathlib import Path
import sqlite3
import pydoc

from common.config import PROCESSED_DATA_DIR, YINDIAN_DATA_DIR, QUERY_DB_PATH
from source.match_fromdb import get_tsvs


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


def _should_display_row(row):
    """
    只在终端显示需要关注的文件：
    1. 未匹配文件
    2. 匹配成功，但文件名簡稱和最终簡稱不完全一致
    """
    if row['status'] != 'OK':
        return True

    return row['filename'] != row['matched']


def _format_row_detail(row, index):
    lines = [
        f'{index}. [{row["status"]}] {row["filename"]}',
        f'   來源: {row["source"]}',
    ]

    if row['matched']:
        lines.append(f'   最終簡稱: {row["matched"]}')

    if row['partition']:
        lines.append(f'   分區: {row["partition"]}')

    lines.append(f'   路徑: {row["path"]}')

    return '\n'.join(lines)


def run_match_check(query_db_path=QUERY_DB_PATH, show_output=True, use_pager=True):
    rows = []
    total = 0
    ok_count = 0
    miss_count = 0

    def _emit(text=''):
        if show_output:
            print(text)

    _emit('\n============================================================')
    _emit('步驟0：模擬最終 TSV 文件名 -> 簡稱 匹配結果...')
    _emit('============================================================')
    _emit(f'   query_db: {query_db_path}')
    _emit(f'   yindian:  {YINDIAN_DATA_DIR}')
    _emit(f'   processed:{PROCESSED_DATA_DIR}')
    _emit('   說明: 直接調用 get_tsvs(single=...)，與最終寫庫匹配鏈路保持一致')

    ready, message = _check_query_db_ready(query_db_path)
    if not ready:
        _emit(f'\n❌ 無法執行 match 檢查：{message}')
        _emit('   先运行：python build.py -t query')
        return rows

    for path in _iter_tsv_paths():
        total += 1
        row = _check_one_file(path, query_db_path=query_db_path)
        rows.append(row)

        if row['status'] == 'OK':
            ok_count += 1
        else:
            miss_count += 1

    _emit(f'\n共掃描 {total} 個 TSV 文件')
    _emit(f'匹配成功 {ok_count} 個')
    _emit(f'匹配失敗 {miss_count} 個')

    if not rows:
        _emit('\n⚠️ 沒有找到任何 TSV 文件。')
        return rows

    display_rows = [row for row in rows if _should_display_row(row)]
    same_count = len(rows) - len(display_rows)
    mismatch_rows = [
        row for row in display_rows
        if row['status'] == 'OK' and row['filename'] != row['matched']
    ]
    miss_rows = [row for row in display_rows if row['status'] != 'OK']

    _emit(f'\n簡稱完全一致 {same_count} 個，已省略顯示')
    _emit(f'簡稱不一致 {len(mismatch_rows)} 個')
    _emit(f'未匹配 {len(miss_rows)} 個')
    _emit(f'需要關注 {len(display_rows)} 個')

    if not display_rows:
        _emit('\n✅ 所有已匹配文件的簡稱均完全一致，且沒有未匹配文件。')
        return rows

    lines = []

    lines.append('【需要關注的文件】')
    lines.append('')
    lines.append(f'共 {len(display_rows)} 個')
    lines.append(f'  - 簡稱不一致: {len(mismatch_rows)} 個')
    lines.append(f'  - 未匹配: {len(miss_rows)} 個')
    lines.append('')

    if mismatch_rows:
        lines.append('============================================================')
        lines.append('【簡稱不一致】')
        lines.append('============================================================')
        lines.append('')

        for index, row in enumerate(mismatch_rows, start=1):
            lines.append(_format_row_detail(row, index))
            lines.append('')

    if miss_rows:
        lines.append('============================================================')
        lines.append('【未匹配文件】')
        lines.append('============================================================')
        lines.append('')

        for index, row in enumerate(miss_rows, start=1):
            lines.append(_format_row_detail(row, index))
            lines.append('')

    if show_output:
        report_text = '\n'.join(lines)
        if use_pager:
            pydoc.pager(report_text)
        else:
            print(report_text)

    return rows