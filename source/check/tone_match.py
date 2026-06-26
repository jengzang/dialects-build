import pydoc
import sqlite3
from collections import defaultdict
from pathlib import Path

import pandas as pd

from common.config import HAN_PATH, YINDIAN_DATA_DIR, QUERY_DB_PATH, exclude_files
from source.match_fromdb import get_tsvs
from source.check.tone_check import load_tone_dataframe, TONE_INDEX_TO_LABEL

def _cell_has_value(value):
    if value is None:
        return False

    try:
        if pd.isna(value):
            return False
    except TypeError:
        pass

    text = str(value).strip()
    if not text:
        return False

    if text.lower() in {'nan', 'none', 'null'}:
        return False

    if text in {'_', '-', '—', '/', '無', '无'}:
        return False

    return True


def _get_tone_columns(include_biantiao=True, include_qingsheng=True):
    indexes = list(range(1, 9))

    if include_biantiao:
        indexes.append(9)

    if include_qingsheng:
        indexes.append(10)

    return [TONE_INDEX_TO_LABEL[index] for index in indexes]


def _iter_yindian_tsv_paths():
    """
    tone-data 只检查 yindian 来源。
    processed 是另一个来源，这里不扫描、不统计、不输出。
    """
    root = Path(YINDIAN_DATA_DIR)

    if not root.exists():
        return

    for path in sorted(root.glob('*.tsv')):
        if path.is_file():
            yield path


def _check_query_db_ready(query_db_path):
    """
    tone-data 必须使用 get_tsvs，而 get_tsvs 依赖 query db 的 dialects 表。
    这里自己检查，不复用 source.check.match 里的函数。
    """
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


def _match_one_yindian_tsv_by_get_tsvs(path, query_db_path):
    """
    使用 get_tsvs(single=...) 对单个 yindian TSV 做真实匹配。

    注意：
    这里不复用 run_match_check。
    这里只复用最终写库真实使用的 get_tsvs 匹配函数。
    """
    stem = path.stem
    source = path.parent.name

    matched_paths, locations, partitions = get_tsvs(
        single=str(path),
        query_db_path=query_db_path,
    )

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


def collect_yindian_tsv_match_rows_by_get_tsvs(query_db_path=QUERY_DB_PATH):
    """
    tone-data 自己的匹配阶段。

    特点：
    1. 只扫描 yindian。
    2. 不扫描 processed。
    3. 不调用 run_match_check。
    4. 但必须调用 get_tsvs(single=...)，保持和最终写库匹配链路一致。
    """

    rows = []

    for path in _iter_yindian_tsv_paths():
        row = _match_one_yindian_tsv_by_get_tsvs(
            path,
            query_db_path=query_db_path,
        )
        rows.append(row)

    return rows

def check_matched_tsvs_without_tone_info(
    excel_path=HAN_PATH,
    query_db_path=QUERY_DB_PATH,
    include_biantiao=True,
    include_qingsheng=True,
    use_pager=True,
):
    """
    tone-data 专用检查。

    逻辑：
    1. 只扫描 YINDIAN_DATA_DIR 下的 TSV。
    2. 不扫描 processed。
    3. 不调用 run_match_check。
    4. 使用 get_tsvs(single=...) 做真实 TSV -> 最终简称匹配。
    5. 只针对匹配成功 status == OK 的最终简称检查声调信息。
    """

    ready, message = _check_query_db_ready(query_db_path)

    if not ready:
        print(f'\n❌ 無法執行 tone-data 檢查：{message}')
        print('   因為 tone-data 需要使用 get_tsvs(single=...)，所以 query 数据库必须已经构建好。')
        print('   先运行：python build.py -t query')
        return {
            'summary': {},
            'match_rows': [],
            'matched_rows': [],
            'match_failed_tsv_rows': [],
            'xlsx_missing_rows': [],
            'no_tone_rows': [],
        }

    workbook_df = load_tone_dataframe(excel_path)

    workbook_map = {
        str(row['簡稱']).strip(): row
        for _, row in workbook_df.iterrows()
        if str(row.get('簡稱', '')).strip()
        and not str(row.get('簡稱', '')).strip().startswith('#')
    }

    match_rows = collect_yindian_tsv_match_rows_by_get_tsvs(
        query_db_path=query_db_path,
    )

    if not match_rows:
        print('\n❌ 無法執行聲調信息檢查：沒有掃描到任何 yindian TSV 文件。')
        print(f'   yindian: {YINDIAN_DATA_DIR}')
        return {
            'summary': {
                'tsv_count': 0,
                'matched_tsv_count': 0,
                'unique_matched_shortname_count': 0,
                'match_failed_tsv_count': 0,
                'xlsx_missing_count': 0,
                'no_tone_count': 0,
                'existing_tone_columns': [],
            },
            'match_rows': [],
            'matched_rows': [],
            'match_failed_tsv_rows': [],
            'xlsx_missing_rows': [],
            'no_tone_rows': [],
        }

    tone_columns = _get_tone_columns(
        include_biantiao=include_biantiao,
        include_qingsheng=include_qingsheng,
    )

    existing_tone_columns = [
        col for col in tone_columns
        if col in workbook_df.columns
    ]

    if not existing_tone_columns:
        print('\n❌ 音典档案中没有找到任何声调列。')
        print(f'   期望列名: {tone_columns}')
        return {
            'summary': {
                'tsv_count': len(match_rows),
                'matched_tsv_count': 0,
                'unique_matched_shortname_count': 0,
                'match_failed_tsv_count': 0,
                'xlsx_missing_count': 0,
                'no_tone_count': 0,
                'existing_tone_columns': [],
            },
            'match_rows': match_rows,
            'matched_rows': [],
            'match_failed_tsv_rows': [],
            'xlsx_missing_rows': [],
            'no_tone_rows': [],
        }

    matched_rows = []
    match_failed_tsv_rows = []

    for row in match_rows:
        if row.get('status') == 'OK' and row.get('matched'):
            matched_rows.append(row)
        else:
            match_failed_tsv_rows.append(row)

    matched_by_shortname = defaultdict(list)

    for row in matched_rows:
        matched_by_shortname[row['matched']].append(row)

    xlsx_missing_rows = []
    no_tone_rows = []

    # 关键：
    # 这里只针对 get_tsvs 匹配成功的最终简称检查声调。
    for shortname, rows in sorted(matched_by_shortname.items()):
        workbook_row = workbook_map.get(shortname)

        if workbook_row is None:
            xlsx_missing_rows.append({
                '簡稱': shortname,
                'status': 'XLSX_MISS',
                'tsv_count': len(rows),
                'tsv_files': rows,
            })
            continue

        has_tone_info = any(
            _cell_has_value(workbook_row[col])
            for col in existing_tone_columns
        )

        if not has_tone_info:
            no_tone_rows.append({
                '簡稱': shortname,
                'status': 'NO_TONE',
                'tsv_count': len(rows),
                'tsv_files': rows,
            })

    summary = {
        'tsv_count': len(match_rows),
        'matched_tsv_count': len(matched_rows),
        'unique_matched_shortname_count': len(matched_by_shortname),
        'match_failed_tsv_count': len(match_failed_tsv_rows),
        'xlsx_missing_count': len(xlsx_missing_rows),
        'no_tone_count': len(no_tone_rows),
        'existing_tone_columns': existing_tone_columns,
    }

    print('\n============================================================')
    print('yindian TSV -> get_tsvs 匹配成功简称 -> 音典档案声调信息检查')
    print('============================================================')
    print(f'query_db: {query_db_path}')
    print(f'excel:    {excel_path}')
    print(f'yindian:  {YINDIAN_DATA_DIR}')
    print(f'检查声调列: {existing_tone_columns}')
    print('')
    print(f'yindian TSV 总数: {summary["tsv_count"]}')
    print(f'get_tsvs 匹配成功 TSV 数: {summary["matched_tsv_count"]}')
    print(f'get_tsvs 匹配成功唯一简称数: {summary["unique_matched_shortname_count"]}')
    print(f'get_tsvs 匹配失败 TSV 数: {summary["match_failed_tsv_count"]}')
    print(f'音典档案中找不到简称: {summary["xlsx_missing_count"]}')
    print(f'匹配成功但没有声调信息: {summary["no_tone_count"]}')

    lines = []

    # if match_failed_tsv_rows:
    #     lines.append('============================================================')
    #     lines.append('【get_tsvs 未匹配的 yindian TSV】')
    #     lines.append('============================================================')
    #     lines.append('')

    #     for index, row in enumerate(match_failed_tsv_rows, start=1):
    #         lines.append(f'{index}. [MISS] {row["filename"]}')
    #         lines.append(f'   路径: {row["path"]}')
    #         lines.append('')

    if xlsx_missing_rows:
        lines.append('============================================================')
        lines.append('【get_tsvs 匹配成功，但音典档案中找不到简称】')
        lines.append('============================================================')
        lines.append('')

        for index, item in enumerate(xlsx_missing_rows, start=1):
            lines.append(f'{index}. [XLSX_MISS] {item["簡稱"]}')
            lines.append(f'   TSV 文件数: {item["tsv_count"]}')

            for tsv_row in item['tsv_files']:
                filename = tsv_row['filename']
                matched = tsv_row['matched']

                if filename == matched:
                    lines.append(f'   - {filename}')
                else:
                    lines.append(f'   - {filename} -> {matched}')

            lines.append('')

    if no_tone_rows:
        lines.append('============================================================')
        lines.append('【get_tsvs 匹配成功，但音典档案中没有声调信息】')
        lines.append('============================================================')
        lines.append('')

        for index, item in enumerate(no_tone_rows, start=1):
            lines.append(f'{index}. [NO_TONE] {item["簡稱"]}')
            lines.append(f'   TSV 文件数: {item["tsv_count"]}')

            for tsv_row in item['tsv_files']:
                filename = tsv_row['filename']
                matched = tsv_row['matched']

                if filename == matched:
                    lines.append(f'   - {filename}')
                else:
                    lines.append(f'   - {filename} -> {matched}')

            lines.append('')

    if lines:
        report_text = '\n'.join(lines)
        if use_pager:
            pydoc.pager(report_text)
        else:
            print(report_text)
    else:
        print('\n✅ 所有 get_tsvs 匹配成功的 yindian TSV，在音典档案中都有声调信息。')

    return {
        'summary': summary,
        'match_rows': match_rows,
        'matched_rows': matched_rows,
        'match_failed_tsv_rows': match_failed_tsv_rows,
        'xlsx_missing_rows': xlsx_missing_rows,
        'no_tone_rows': no_tone_rows,
    }