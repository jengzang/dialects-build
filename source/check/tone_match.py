import pydoc
import sqlite3
from collections import defaultdict
from pathlib import Path

import pandas as pd

from common.config import HAN_PATH, YINDIAN_DATA_DIR, QUERY_DB_PATH
from common.constants import exclude_files
from source.match_fromdb import get_tsvs, match_paths_to_abbr
from source.check.tone_check import load_tone_dataframe, TONE_INDEX_TO_LABEL


EXCLUDE_SHORTNAMES = {str(item).strip() for item in exclude_files}


def _is_excluded_shortname(shortname):
    return str(shortname).strip() in EXCLUDE_SHORTNAMES


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


def _iter_all_yindian_tsv_paths():
    root = Path(YINDIAN_DATA_DIR)

    if not root.exists():
        return

    for path in sorted(root.glob('*.tsv')):
        if path.is_file():
            yield path


def _iter_checked_yindian_tsv_paths():
    """
    tone-data 只检查 yindian 来源。

    processed 是另一个来源，这里不扫描、不统计、不输出。

    exclude_files 中的文件在进入 get_tsvs 之前就排除。
    """
    for path in _iter_all_yindian_tsv_paths():
        if _is_excluded_shortname(path.stem):
            continue

        yield path


def _count_all_yindian_tsvs():
    return sum(1 for _ in _iter_all_yindian_tsv_paths())


def _count_excluded_yindian_tsvs():
    count = 0

    for path in _iter_all_yindian_tsv_paths():
        if _is_excluded_shortname(path.stem):
            count += 1

    return count


def _load_workbook_map(excel_path):
    workbook_df = load_tone_dataframe(excel_path)

    workbook_map = {
        str(row['簡稱']).strip(): row
        for _, row in workbook_df.iterrows()
        if str(row.get('簡稱', '')).strip()
        and not str(row.get('簡稱', '')).strip().startswith('#')
        and not _is_excluded_shortname(row.get('簡稱', ''))
    }

    return workbook_df, workbook_map


def _match_one_yindian_tsv_by_get_tsvs(path, query_db_path):
    """
    使用 get_tsvs(single=...) 对单个 yindian TSV 做真实匹配。

    注意：
    这里不复用 run_match_check。
    这里只复用最终写库真实使用的 get_tsvs 匹配函数。
    """
    stem = path.stem
    source = path.parent.name

    try:
        matched_paths, locations, partitions = get_tsvs(
            single=str(path),
            query_db_path=query_db_path,
        )
    except Exception as exc:
        return {
            'source': source,
            'filename': stem,
            'matched': '',
            'partition': '',
            'status': 'ERROR',
            'error': str(exc),
            'path': str(path),
        }

    matched = [loc for loc in locations if loc != '_']
    parts = [part for part in partitions if part]

    if matched:
        final_shortname = matched[0]

        if _is_excluded_shortname(final_shortname):
            return {
                'source': source,
                'filename': stem,
                'matched': final_shortname,
                'partition': parts[0] if parts else '',
                'status': 'EXCLUDED',
                'path': matched_paths[0] if matched_paths else str(path),
            }

        return {
            'source': source,
            'filename': stem,
            'matched': final_shortname,
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
    3. 先排除 exclude_files。
    4. 不调用 source.check.match.run_match_check。
    5. 调用 get_tsvs(single=...) 保留逐檔诊断视角。
    6. 最终声调统计再按 yindian 范围内的全局裁决过滤 shadowed/ambiguous。
    """
    rows = []

    for path in _iter_checked_yindian_tsv_paths():
        row = _match_one_yindian_tsv_by_get_tsvs(
            path,
            query_db_path=query_db_path,
        )
        rows.append(row)

    return rows


def _format_global_resolution_lines(resolution):
    lines = []

    if resolution.shadowed:
        lines.append('============================================================')
        lines.append('【yindian 范围内写库会跳过的 shadowed 文件】')
        lines.append('============================================================')
        lines.append('')
        for index, item in enumerate(resolution.shadowed, start=1):
            lines.append(f'{index}. {Path(item.loser.path).name} -> {item.loser.abbr}')
            lines.append(
                f'   原因: 被 {item.winner.stage} 文件 {Path(item.winner.path).name} 覆盖'
            )
            lines.append(f'   路径: {item.loser.path}')
            lines.append('')

    if resolution.ambiguous:
        lines.append('============================================================')
        lines.append('【yindian 范围内写库会中止的 ambiguous 简称】')
        lines.append('============================================================')
        lines.append('')
        for index, item in enumerate(resolution.ambiguous, start=1):
            lines.append(f'{index}. {item.abbr}')
            lines.append(f'   原因: {item.reason}')
            lines.append('   候选:')
            for claim in item.claims:
                lines.append(f'   - {Path(claim.path).name} {claim.stage}')
            lines.append('')

    return lines


def check_matched_tsvs_without_tone_info(
    excel_path=HAN_PATH,
    query_db_path=QUERY_DB_PATH,
    include_biantiao=True,
    include_qingsheng=True,
    use_pager=False,
):
    """
    tone-data 专用检查。

    逻辑：
    1. 只扫描 YINDIAN_DATA_DIR 下的 TSV。
    2. 不扫描 processed。
    3. 先排除 exclude_files。
    4. 不调用 source.check.match.run_match_check。
    5. 使用 get_tsvs(single=...) 做逐檔 TSV -> 简称诊断。
    6. 使用 match_paths_to_abbr 在 yindian 范围内模拟写库裁决。
    7. 只针对 single 匹配成功且全局裁决 accepted 的简称检查声调信息。
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
            'match_error_tsv_rows': [],
            'excluded_after_match_rows': [],
            'xlsx_missing_rows': [],
            'no_tone_rows': [],
            'global_resolution': None,
        }

    workbook_df, workbook_map = _load_workbook_map(excel_path)

    total_yindian_tsv_count = _count_all_yindian_tsvs()
    excluded_tsv_count = _count_excluded_yindian_tsvs()

    match_rows = collect_yindian_tsv_match_rows_by_get_tsvs(
        query_db_path=query_db_path,
    )
    global_resolution = match_paths_to_abbr(
        [row['path'] for row in match_rows],
        query_db_path=query_db_path,
    ) if match_rows else None
    accepted_paths = set(global_resolution.accepted) if global_resolution else set()

    if not match_rows:
        print('\n❌ 無法執行聲調信息檢查：排除 exclude_files 后，没有任何 yindian TSV 文件进入检查。')
        print(f'   yindian: {YINDIAN_DATA_DIR}')
        print(f'   yindian TSV 总数: {total_yindian_tsv_count}')
        print(f'   已排除 TSV 数: {excluded_tsv_count}')
        return {
            'summary': {
                'total_yindian_tsv_count': total_yindian_tsv_count,
                'excluded_tsv_count': excluded_tsv_count,
                'checked_tsv_count': 0,
                'matched_tsv_count': 0,
                'unique_matched_shortname_count': 0,
                'match_failed_tsv_count': 0,
                'match_error_tsv_count': 0,
                'excluded_after_match_count': 0,
                'xlsx_missing_count': 0,
                'no_tone_count': 0,
                'existing_tone_columns': [],
            },
            'match_rows': [],
            'matched_rows': [],
            'match_failed_tsv_rows': [],
            'match_error_tsv_rows': [],
            'excluded_after_match_rows': [],
            'xlsx_missing_rows': [],
            'no_tone_rows': [],
            'global_resolution': None,
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
                'total_yindian_tsv_count': total_yindian_tsv_count,
                'excluded_tsv_count': excluded_tsv_count,
                'checked_tsv_count': len(match_rows),
                'matched_tsv_count': 0,
                'unique_matched_shortname_count': 0,
                'match_failed_tsv_count': 0,
                'match_error_tsv_count': 0,
                'excluded_after_match_count': 0,
                'xlsx_missing_count': 0,
                'no_tone_count': 0,
                'existing_tone_columns': [],
            },
            'match_rows': match_rows,
            'matched_rows': [],
            'match_failed_tsv_rows': [],
            'match_error_tsv_rows': [],
            'excluded_after_match_rows': [],
            'xlsx_missing_rows': [],
            'no_tone_rows': [],
            'global_resolution': global_resolution,
        }

    matched_rows = []
    match_failed_tsv_rows = []
    match_error_tsv_rows = []
    excluded_after_match_rows = []

    for row in match_rows:
        status = row.get('status')

        if status == 'OK' and row.get('matched') and row.get('path') in accepted_paths:
            matched_rows.append(row)
        elif status == 'ERROR':
            match_error_tsv_rows.append(row)
        elif status == 'EXCLUDED':
            excluded_after_match_rows.append(row)
        else:
            match_failed_tsv_rows.append(row)

    matched_by_shortname = defaultdict(list)

    for row in matched_rows:
        matched_by_shortname[row['matched']].append(row)

    xlsx_missing_rows = []
    no_tone_rows = []

    # 关键：这里只针对 single 匹配成功且全局裁决 accepted 的最终简称检查声调。
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
        'total_yindian_tsv_count': total_yindian_tsv_count,
        'excluded_tsv_count': excluded_tsv_count,
        'checked_tsv_count': len(match_rows),
        'matched_tsv_count': len(matched_rows),
        'unique_matched_shortname_count': len(matched_by_shortname),
        'match_failed_tsv_count': len(match_failed_tsv_rows),
        'match_error_tsv_count': len(match_error_tsv_rows),
        'excluded_after_match_count': len(excluded_after_match_rows),
        'shadowed_tsv_count': len(global_resolution.shadowed) if global_resolution else 0,
        'ambiguous_group_count': len(global_resolution.ambiguous) if global_resolution else 0,
        'xlsx_missing_count': len(xlsx_missing_rows),
        'no_tone_count': len(no_tone_rows),
        'existing_tone_columns': existing_tone_columns,
    }

    print('\n============================================================')
    print('yindian TSV -> single 匹配 -> yindian 全局裁决 -> 音典档案声调信息检查')
    print('============================================================')
    print(f'query_db: {query_db_path}')
    print(f'excel:    {excel_path}')
    print(f'yindian:  {YINDIAN_DATA_DIR}')
    print(f'检查声调列: {existing_tone_columns}')
    print('')
    print(f'yindian TSV 总数: {summary["total_yindian_tsv_count"]}')
    print(f'已排除 TSV 数: {summary["excluded_tsv_count"]}')
    print(f'进入检查 TSV 数: {summary["checked_tsv_count"]}')
    print(f'get_tsvs 匹配成功 TSV 数: {summary["matched_tsv_count"]}')
    print(f'get_tsvs 匹配成功唯一简称数: {summary["unique_matched_shortname_count"]}')
    print(f'get_tsvs 匹配失败 TSV 数: {summary["match_failed_tsv_count"]}')
    print(f'get_tsvs 匹配异常 TSV 数: {summary["match_error_tsv_count"]}')
    print(f'匹配后排除 TSV 数: {summary["excluded_after_match_count"]}')
    print(f'yindian 全局裁决 shadowed TSV 数: {summary["shadowed_tsv_count"]}')
    print(f'yindian 全局裁决 ambiguous 组数: {summary["ambiguous_group_count"]}')
    print(f'音典档案中找不到简称: {summary["xlsx_missing_count"]}')
    print(f'匹配成功但没有声调信息: {summary["no_tone_count"]}')

    lines = []
    if global_resolution:
        lines.extend(_format_global_resolution_lines(global_resolution))

    # if match_failed_tsv_rows:
    #     lines.append('============================================================')
    #     lines.append('【get_tsvs 未匹配的 yindian TSV】')
    #     lines.append('============================================================')
    #     lines.append('')

    #     for index, row in enumerate(match_failed_tsv_rows, start=1):
    #         lines.append(f'{index}. [MISS] {row["filename"]}')
    #         lines.append(f'   路径: {row["path"]}')
    #         lines.append('')

    if match_error_tsv_rows:
        lines.append('============================================================')
        lines.append('【get_tsvs 匹配异常的 yindian TSV】')
        lines.append('============================================================')
        lines.append('')

        for index, row in enumerate(match_error_tsv_rows, start=1):
            lines.append(f'{index}. [ERROR] {row["filename"]}')
            lines.append(f'   错误: {row.get("error", "")}')
            lines.append(f'   路径: {row["path"]}')
            lines.append('')

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
        'match_error_tsv_rows': match_error_tsv_rows,
        'excluded_after_match_rows': excluded_after_match_rows,
        'xlsx_missing_rows': xlsx_missing_rows,
        'no_tone_rows': no_tone_rows,
        'global_resolution': global_resolution,
    }
