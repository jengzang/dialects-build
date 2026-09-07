import csv
import pydoc
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

import pandas as pd

from common.config import HAN_PATH, YINDIAN_DATA_DIR, QUERY_DB_PATH
from common.constants import col_map, exclude_files, vowel_pattern
from source.match_fromdb import get_tsvs, match_paths_to_abbr
from source.check.tone_check import load_tone_dataframe, TONE_INDEX_TO_LABEL


EXCLUDE_SHORTNAMES = {str(item).strip() for item in exclude_files}
EMPTY_SET = frozenset()


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


def _iter_old_tone_workbook_paths(current_excel_path):
    old_dir = Path(current_excel_path).parent / 'old'

    if not old_dir.exists():
        return []

    paths = [path for path in old_dir.glob('*.xlsx') if path.is_file()]

    def sort_key(path):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0
        return (mtime, path.name)

    return sorted(paths, key=sort_key, reverse=True)


def _load_old_tone_dataframe(path):
    try:
        return load_tone_dataframe(path)
    except Exception:
        df = pd.read_excel(path, dtype=object).fillna('')
        df.columns = [str(col).strip() for col in df.columns]
        if '簡稱' in df.columns:
            df['簡稱'] = df['簡稱'].astype(str).str.strip()
        return df


def attach_old_tone_info(no_tone_rows, old_workbook_paths=None, tone_columns=None):
    old_workbook_paths = list(old_workbook_paths or [])
    tone_columns = list(tone_columns or _get_tone_columns())

    old_workbooks = []

    for path in old_workbook_paths:
        try:
            df = _load_old_tone_dataframe(path)
        except Exception as exc:
            old_workbooks.append({
                'path': Path(path),
                'error': str(exc),
                'df': None,
            })
            continue

        old_workbooks.append({
            'path': Path(path),
            'df': df,
        })

    for item in no_tone_rows:
        shortname = str(item.get('簡稱', '')).strip()
        hits = []
        errors = []

        if not shortname:
            item['old_tone_info'] = []
            continue

        for workbook in old_workbooks:
            path = workbook['path']
            df = workbook.get('df')

            if df is None:
                errors.append({
                    'old_file': path.name,
                    'error': workbook.get('error', ''),
                })
                continue

            if '簡稱' not in df.columns:
                errors.append({
                    'old_file': path.name,
                    'error': '缺少 簡稱 欄',
                })
                continue

            matched = df[df['簡稱'].astype(str).str.strip() == shortname]

            if matched.empty:
                continue

            existing_columns = [col for col in tone_columns if col in df.columns]

            for _, row in matched.iterrows():
                tone_values = {
                    col: str(row[col]).strip()
                    for col in existing_columns
                    if _cell_has_value(row[col])
                }

                if tone_values:
                    hits.append({
                        'old_file': path.name,
                        'path': str(path),
                        'tone_values': tone_values,
                    })

        item['old_tone_info'] = hits
        if errors:
            item['old_tone_errors'] = errors

    return no_tone_rows


def _extract_tone_code(phonetic):
    text = str(phonetic or '').strip()

    if not text:
        return ''

    if '輕聲' in text or '轻声' in text:
        return '輕聲'

    matches = re.findall(r'\d{1,2}[A-Da-d]?', text)
    return matches[-1] if matches else ''


def _standard_similarity_column_name(col_name):
    for standard_col, possible_names in col_map.items():
        if col_name in possible_names:
            return standard_col
    return col_name


def _normalize_similarity_initial(initial):
    initial = str(initial or '').strip()
    for old, new in {
        '∫': 'ʃ',
        'th': 'tʰ',
        'kh': 'kʰ',
        'ph': 'pʰ',
        'tsh': 'tsʰ',
        'ts': 'ʦ',
        'tʃ': 'ʧ',
        'tɕ': 'ʨ',
        'tʰs': 'ʦʰ',
        '(ʔ)': 'ʔ',
        '∅': 'ʔ',
        'Ø': 'ʔ',
    }.items():
        initial = initial.replace(old, new)
    return initial


def _normalize_similarity_final(final):
    final = str(final or '').strip()
    final = re.sub(r'[一-鿿]', '', final)
    for old, new in {
        'ε': 'ɛ',
        'α': 'ɑ',
        'ʯ': 'ʮ',
        '∅': 'ø',
        'ο': 'o',
        'ǝ': 'ə',
        'о': 'o',
        'у': 'y',
        'е': 'e',
        'ã': 'ã',
        'ẽ': 'ẽ',
        'ĩ': 'ĩ',
        'ī': 'ĩ',
        'ā': 'ã',
        'ỹ': 'ỹ',
        'õ': 'õ',
    }.items():
        final = final.replace(old, new)
    return final


def _split_similarity_phonetic(phonetic):
    text = str(phonetic or '').strip()
    base = re.sub(r'\d{1,2}[A-Da-d]?', '', text)
    base = re.sub(r'\s.*$', '', base).strip()

    if not base:
        return '', ''

    if base[0] in {'∅', 'Ø'}:
        return 'ʔ', _normalize_similarity_final(base[1:])

    vowel_match = re.search(vowel_pattern, base)

    if not vowel_match:
        return _normalize_similarity_initial(base), ''

    initial = base[:vowel_match.start()] or '/'
    final = base[vowel_match.start():]
    return _normalize_similarity_initial(initial), _normalize_similarity_final(final)


def _iter_similarity_tsv_rows(path):
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')

        if not reader.fieldnames:
            return

        field_map = {
            field: _standard_similarity_column_name(str(field).strip())
            for field in reader.fieldnames
        }

        for row in reader:
            normalized = {
                standard_field: row.get(raw_field, '')
                for raw_field, standard_field in field_map.items()
            }
            yield normalized


def _build_field_sets_by_char(readings_by_char):
    field_sets_by_char = {}

    for char, readings in readings_by_char.items():
        field_sets_by_char[char] = {
            field: {
                reading.get(field, '')
                for reading in readings
                if reading.get(field, '')
            }
            for field in ('syllable', 'initial', 'final', 'tone')
        }

    return field_sets_by_char


def _finalize_similarity_profile(profile):
    readings_by_char = dict(profile['readings_by_char'])
    profile['readings_by_char'] = readings_by_char
    profile['field_sets_by_char'] = _build_field_sets_by_char(readings_by_char)
    profile['char_set'] = set(readings_by_char)
    profile['char_count'] = len(readings_by_char)
    return profile


def _field_matches(target_field_sets, candidate_field_sets, char, field):
    return bool(
        target_field_sets.get(char, {}).get(field, EMPTY_SET)
        & candidate_field_sets.get(char, {}).get(field, EMPTY_SET)
    )


def _empty_similarity_score():
    return {
        'score': 0.0,
        'coverage': 0.0,
        'jaccard': 0.0,
        'syllable_match_rate': 0.0,
        'initial_match_rate': 0.0,
        'final_match_rate': 0.0,
        'tone_match_rate': 0.0,
        'shared_char_count': 0,
        'target_char_count': 0,
        'candidate_char_count': 0,
        'union_char_count': 0,
    }


def load_similarity_profile(path):
    """
    读取 TSV 并抽取用于 no-tone 参照的字表画像。

    字表画像按汉字聚合，保留同字多读；声调只取音标里的末尾调号/调类码，
    不依赖音典档案里的声调信息。
    """
    profile = {
        'path': str(path),
        'readings_by_char': defaultdict(list),
    }

    for row in _iter_similarity_tsv_rows(str(path)):
        char = str(row.get('漢字', '')).strip()
        phonetic = str(row.get('音標', '')).strip()

        if not char or not phonetic:
            continue

        phonetic_variants = (
            phonetic.split('/')
            if '/' in phonetic and phonetic.strip() != '/'
            else [phonetic]
        )

        for phonetic_variant in phonetic_variants:
            phonetic_variant = phonetic_variant.strip()

            if not phonetic_variant:
                continue

            initial, final = _split_similarity_phonetic(phonetic_variant)
            profile['readings_by_char'][char].append({
                'syllable': phonetic_variant,
                'initial': initial,
                'final': final,
                'tone': _extract_tone_code(phonetic_variant),
            })

    return _finalize_similarity_profile(profile)


def load_similarity_char_set(path):
    chars = set()

    for row in _iter_similarity_tsv_rows(str(path)):
        char = str(row.get('漢字', '')).strip()
        phonetic = str(row.get('音標', '')).strip()

        if char and phonetic:
            chars.add(char)

    return chars


def _combine_similarity_char_sets(paths):
    chars = set()

    for path in paths:
        if path:
            chars.update(load_similarity_char_set(path))

    return chars


def _combine_similarity_profiles(paths):
    combined = {
        'path': '',
        'readings_by_char': defaultdict(list),
    }
    path_list = [str(path) for path in paths if path]
    combined['path'] = ';'.join(path_list)

    for path in path_list:
        profile = load_similarity_profile(path)

        for char, readings in profile['readings_by_char'].items():
            combined['readings_by_char'][char].extend(readings)

    return _finalize_similarity_profile(combined)


def score_similarity_profiles(target, candidate):
    target_chars = target.get('char_set') or set(target.get('readings_by_char', {}))
    candidate_chars = candidate.get('char_set') or set(candidate.get('readings_by_char', {}))
    shared_chars = target_chars & candidate_chars
    union_chars = target_chars | candidate_chars

    score = _empty_similarity_score()
    score['shared_char_count'] = len(shared_chars)
    score['target_char_count'] = len(target_chars)
    score['candidate_char_count'] = len(candidate_chars)
    score['union_char_count'] = len(union_chars)

    if not target_chars or not candidate_chars or not shared_chars:
        return score

    shared_count = len(shared_chars)
    syllable_matches = 0
    initial_matches = 0
    final_matches = 0
    tone_matches = 0

    target_field_sets = target.get('field_sets_by_char') or _build_field_sets_by_char(
        target.get('readings_by_char', {})
    )
    candidate_field_sets = candidate.get('field_sets_by_char') or _build_field_sets_by_char(
        candidate.get('readings_by_char', {})
    )

    for char in shared_chars:
        if _field_matches(target_field_sets, candidate_field_sets, char, 'syllable'):
            syllable_matches += 1
        if _field_matches(target_field_sets, candidate_field_sets, char, 'initial'):
            initial_matches += 1
        if _field_matches(target_field_sets, candidate_field_sets, char, 'final'):
            final_matches += 1
        if _field_matches(target_field_sets, candidate_field_sets, char, 'tone'):
            tone_matches += 1

    score['coverage'] = shared_count / len(target_chars)
    score['jaccard'] = shared_count / len(union_chars)
    score['syllable_match_rate'] = syllable_matches / shared_count
    score['initial_match_rate'] = initial_matches / shared_count
    score['final_match_rate'] = final_matches / shared_count
    score['tone_match_rate'] = tone_matches / shared_count
    score['score'] = (
        0.20 * score['coverage']
        + 0.25 * score['syllable_match_rate']
        + 0.15 * score['initial_match_rate']
        + 0.15 * score['final_match_rate']
        + 0.10 * score['tone_match_rate']
    )

    return score


def _paths_from_no_tone_item(item):
    return [
        row.get('path')
        for row in item.get('tsv_files', [])
        if row.get('path')
    ]


def _similarity_candidate_sort_key(row):
    return (
        -row.get('score', 0.0),
        -row.get('coverage', 0.0),
        -row.get('jaccard', 0.0),
        -row.get('shared_char_count', 0),
        row.get('簡稱', ''),
    )


def _similarity_prefilter_sort_key(row):
    return (
        -row.get('shared_char_count', 0),
        -row.get('coverage', 0.0),
        -row.get('jaccard', 0.0),
        row.get('簡稱', ''),
    )


def _format_similarity_metric(value):
    return f'{value:.3f}'


def attach_no_tone_similarity(no_tone_rows, matched_rows, top_n=3, prefilter_limit=50):
    no_tone_shortnames = {
        str(row.get('簡稱', '')).strip()
        for row in no_tone_rows
    }

    candidate_summaries = []
    profile_cache = {}

    for row in matched_rows:
        shortname = str(row.get('matched') or row.get('簡稱') or '').strip()
        path = row.get('path')

        if not shortname or shortname in no_tone_shortnames or not path:
            continue

        try:
            char_set = load_similarity_char_set(path)
        except Exception as exc:
            candidate_summaries.append({
                '簡稱': shortname,
                'filename': row.get('filename') or Path(path).stem,
                'path': path,
                'error': str(exc),
                'char_set': set(),
            })
            continue

        candidate_summaries.append({
            '簡稱': shortname,
            'filename': row.get('filename') or Path(path).stem,
            'path': path,
            'char_set': char_set,
        })

    for item in no_tone_rows:
        target_paths = _paths_from_no_tone_item(item)

        try:
            target_char_set = _combine_similarity_char_sets(target_paths)
        except Exception as exc:
            item['similar_tsvs'] = []
            item['similarity_error'] = str(exc)
            continue

        prefiltered_candidates = []

        for candidate in candidate_summaries:
            candidate_chars = candidate.get('char_set') or set()
            shared_chars = target_char_set & candidate_chars

            if not target_char_set or not candidate_chars or not shared_chars:
                continue

            union_chars = target_char_set | candidate_chars
            prefiltered_candidates.append({
                **candidate,
                'shared_char_count': len(shared_chars),
                'target_char_count': len(target_char_set),
                'candidate_char_count': len(candidate_chars),
                'union_char_count': len(union_chars),
                'coverage': len(shared_chars) / len(target_char_set),
                'jaccard': len(shared_chars) / len(union_chars),
            })

        prefiltered_candidates.sort(key=_similarity_prefilter_sort_key)
        prefiltered_candidates = prefiltered_candidates[:max(top_n, prefilter_limit)]

        try:
            target_profile = _combine_similarity_profiles(target_paths)
        except Exception as exc:
            item['similar_tsvs'] = []
            item['similarity_error'] = str(exc)
            continue

        scored_rows = []

        for candidate in prefiltered_candidates:
            path = candidate['path']
            if path not in profile_cache:
                try:
                    profile_cache[path] = load_similarity_profile(path)
                except Exception:
                    profile_cache[path] = None

            profile = profile_cache[path]

            if profile is None:
                continue

            similarity = score_similarity_profiles(target_profile, profile)

            if similarity['shared_char_count'] == 0:
                continue

            scored_rows.append({
                '簡稱': candidate['簡稱'],
                'filename': candidate['filename'],
                'path': candidate['path'],
                **similarity,
            })

        scored_rows.sort(key=_similarity_candidate_sort_key)
        item['similar_tsvs'] = scored_rows[:top_n]

    return no_tone_rows


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
            lines.append(f'   裁决: {item.reason}')
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

    old_workbook_paths = _iter_old_tone_workbook_paths(excel_path)
    attach_old_tone_info(
        no_tone_rows,
        old_workbook_paths=old_workbook_paths,
        tone_columns=existing_tone_columns,
    )
    attach_no_tone_similarity(no_tone_rows, matched_rows, top_n=3)
    no_tone_shortnames = {row['簡稱'] for row in no_tone_rows}
    similarity_candidate_count = sum(
        1
        for row in matched_rows
        if row.get('matched') not in no_tone_shortnames
    )

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
        'old_tone_workbook_count': len(old_workbook_paths),
        'no_tone_with_old_tone_count': sum(
            1 for row in no_tone_rows if row.get('old_tone_info')
        ),
        'similarity_candidate_count': similarity_candidate_count,
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
    print(f'已查询旧音典档案数: {summary["old_tone_workbook_count"]}')
    print(f'no-tone 在旧档案找到声调信息: {summary["no_tone_with_old_tone_count"]}')
    print(f'no-tone 相似度候选 TSV 数: {summary["similarity_candidate_count"]}')

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

            if item.get('old_tone_info'):
                lines.append('   旧档案声调信息:')
                for old_info in item['old_tone_info']:
                    values = ' | '.join(
                        f'{col}={value}'
                        for col, value in old_info['tone_values'].items()
                    )
                    lines.append(f'   - {old_info["old_file"]}: {values}')
            elif not old_workbook_paths:
                lines.append('   旧档案声调信息: 未找到 old/*.xlsx')
            else:
                lines.append('   旧档案声调信息: 未找到')

            if item.get('old_tone_errors'):
                for error in item['old_tone_errors'][:3]:
                    lines.append(
                        f'   旧档案读取警告: {error["old_file"]} | {error["error"]}'
                    )

            if item.get('similarity_error'):
                lines.append(f'   相似度计算失败: {item["similarity_error"]}')
            elif item.get('similar_tsvs'):
                lines.append('   相似 TSV top3:')
                for rank, similar in enumerate(item['similar_tsvs'], start=1):
                    shared = similar['shared_char_count']
                    target_total = similar['target_char_count']
                    lines.append(
                        f'   {rank}. {similar["簡稱"]} '
                        f'score={_format_similarity_metric(similar["score"])} '
                        f'coverage={_format_similarity_metric(similar["coverage"])} '
                        f'jaccard={_format_similarity_metric(similar["jaccard"])} '
                        f'syllable={_format_similarity_metric(similar["syllable_match_rate"])} '
                        f'initial={_format_similarity_metric(similar["initial_match_rate"])} '
                        f'final={_format_similarity_metric(similar["final_match_rate"])} '
                        f'tone={_format_similarity_metric(similar["tone_match_rate"])} '
                        f'shared={shared}/{target_total} '
                        f'file={similar["filename"]}'
                    )
            else:
                lines.append('   相似 TSV top3: 无共同字候选')

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
