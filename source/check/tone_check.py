import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

from common.config import HAN_PATH, QUERY_DB_USER_PATH
from common.search_tones import search_tones

TONE_CHECK_JSON_PATH = Path("data/dependency/tone_value_overrides.json")
WEIRD_TONE_NAME_PATTERN = re.compile(r"[^㐀-䶿一-鿿豈-﫿]")
TONE_INDEX_TO_LABEL = {
    1: '[1]陰平',
    2: '[2]陽平',
    3: '[3]陰上',
    4: '[4]陽上',
    5: '[5]陰去',
    6: '[6]陽去',
    7: '[7]陰入',
    8: '[8]陽入',
    9: '[9]變調',
    10: '[0]輕聲',
}


def load_tone_overrides(json_path=TONE_CHECK_JSON_PATH):
    if not Path(json_path).exists():
        return {}
    return json.loads(Path(json_path).read_text(encoding='utf-8'))


def save_tone_overrides(overrides, json_path=TONE_CHECK_JSON_PATH):
    path = Path(json_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')


def load_tone_dataframe(excel_path=HAN_PATH):
    df = pd.read_excel(excel_path, sheet_name='檔案', dtype=object).fillna('')
    df.columns = [str(col).strip() for col in df.columns]
    df['簡稱'] = df['簡稱'].astype(str).str.strip()
    return df


def classify_tone_name(name):
    text = str(name).strip()
    if not text:
        return {'is_weird': False, 'chars': []}
    weird_chars = sorted(set(WEIRD_TONE_NAME_PATTERN.findall(text)))
    return {
        'is_weird': bool(weird_chars),
        'chars': weird_chars,
    }


def split_cell_to_name_parts(cell):
    text = '' if cell is None else str(cell).strip()
    if not text:
        return []
    parts = []
    for element in re.split(r'[，,|;]', text):
        element = element.strip()
        if not element:
            continue
        name = ''.join(re.findall(r'[^\d,]+', re.sub(r'\[.*?\]', '', element))).strip()
        if name:
            parts.append(name)
    return parts


def get_dialects_db_tone_names(cell):
    text = '' if cell is None else str(cell).strip()
    if not text:
        return []

    tone_names = []
    cell = re.sub(r'[-/ʔˀ]', '', str(cell))
    tag_value_pairs = re.findall(
        r"\[([0-9]{1,2}[a-zA-Z]?)\](?:\d+)?([^\[\],\d]*)",
        cell
    )
    for _tag, name in tag_value_pairs:
        name = name.strip()
        if name:
            tone_names.append(name)
    return tone_names


def find_weird_name_hits_in_cell(cell):
    hits = []
    for name in split_cell_to_name_parts(cell):
        info = classify_tone_name(name)
        if info['is_weird']:
            hits.append({'tone_name': name, 'weird_chars': info['chars']})
    return hits


def fetch_raw_tone_rows(locations, db_path):
    rows = []
    total = len(locations)
    for idx, location in enumerate(locations, start=1):
        if idx == 1 or idx % 100 == 0 or idx == total:
            print(f"[tone] 掃描進度 {idx}/{total}: {location}")
        try:
            result = search_tones(locations=[location], regions=None, get_raw=True, db_path=db_path)
            if result:
                rows.extend(result)
        except Exception as exc:
            print(f"[tone] 跳過 {location}: {exc}")
            continue
    return rows


def analyze_tone_workbook(excel_path=HAN_PATH, db_path=QUERY_DB_USER_PATH, overrides=None):
    overrides = overrides or {}
    workbook_df = load_tone_dataframe(excel_path)
    workbook_map = {
        str(row['簡稱']).strip(): row
        for _, row in workbook_df.iterrows()
        if str(row.get('簡稱', '')).strip() and not str(row.get('簡稱', '')).strip().startswith('#')
    }

    raw_rows = fetch_raw_tone_rows(workbook_map.keys(), db_path=db_path)
    weird_tone_names = defaultdict(list)
    summary = {
        'checked_locations': len(raw_rows),
    }

    for row in raw_rows:
        shortname = str(row.get('簡稱', '')).strip()
        total_data = row.get('總數據', [])
        workbook_row = workbook_map.get(shortname)

        for idx, cell in enumerate(total_data, start=1):
            if not cell:
                continue
            hits = find_weird_name_hits_in_cell(cell)
            if not hits:
                continue

            column_label = TONE_INDEX_TO_LABEL.get(idx, f'T{idx}')
            workbook_value = ''
            if workbook_row is not None and column_label in workbook_row.index:
                workbook_value = str(workbook_row[column_label]).strip()
                workbook_value = overrides.get(shortname, {}).get(workbook_value, workbook_value)

            dialects_db_tone_names = get_dialects_db_tone_names(cell)
            for hit in hits:
                weird_tone_names[hit['tone_name']].append({
                    '簡稱': shortname,
                    'tone_index': idx,
                    'column': column_label,
                    'raw_total_data_value': str(cell).strip(),
                    'workbook_value': workbook_value,
                    'dialects_db_tone_names': dialects_db_tone_names,
                    'weird_chars': hit['weird_chars'],
                })

    weird_tone_names = dict(sorted(weird_tone_names.items(), key=lambda item: item[0]))
    summary['weird_tone_name_count'] = len(weird_tone_names)
    summary['weird_hit_count'] = sum(len(items) for items in weird_tone_names.values())
    return {
        'summary': summary,
        'weird_tone_names': weird_tone_names,
        'overrides': overrides,
    }


def format_tone_analysis_report(result, sample_limit=30):
    lines = []
    summary = result['summary']
    lines.append('tone check summary')
    lines.append(f"- checked_locations: {summary['checked_locations']}")
    lines.append(f"- weird_tone_name_count: {summary['weird_tone_name_count']}")
    lines.append(f"- weird_hit_count: {summary['weird_hit_count']}")

    if result['weird_tone_names']:
        lines.append('')
        lines.append('[weird_tone_names]')
        for tone_name, items in result['weird_tone_names'].items():
            weird_chars = sorted({char for item in items for char in item['weird_chars']})
            weird_char_text = ''.join(weird_chars) if weird_chars else '(none)'
            lines.append(f"- {tone_name!r} | count={len(items)} | weird_chars={weird_char_text}")
            for item in items[:sample_limit]:
                lines.append(
                    # f"  簡稱={item['簡稱']} | 列={item['column']} | raw={item['raw_total_data_value']!r} | xlsx={item['workbook_value']!r} | dialects_db={item['dialects_db_tone_names']!r}"
                    f"  簡稱={item['簡稱']} | 列={item['column']} | raw={item['raw_total_data_value']!r} | dialects_db={item['dialects_db_tone_names']!r}"
                )
            if len(items) > sample_limit:
                lines.append(f"  ... {len(items) - sample_limit} more")

    return '\n'.join(lines)


def run_tone_check(excel_path=HAN_PATH, db_path=QUERY_DB_USER_PATH, json_path=TONE_CHECK_JSON_PATH):
    overrides = load_tone_overrides(json_path)
    result = analyze_tone_workbook(excel_path=excel_path, db_path=db_path, overrides=overrides)
    print(format_tone_analysis_report(result))
    return result
