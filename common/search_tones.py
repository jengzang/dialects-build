import json
import re
import sqlite3
from pathlib import Path

import pandas as pd

from common.config import QUERY_DB_PATH
from common.getloc_by_name_region import query_dialect_abbreviations

TONE_MAPPING_PATH = Path("data/dependency/tone_value_overrides.json")


def load_tone_value_overrides(json_path=TONE_MAPPING_PATH):
    if not Path(json_path).exists():
        return {}
    return json.loads(Path(json_path).read_text(encoding='utf-8'))


def apply_tone_value_override(shortname, raw_value, overrides):
    shortname = '' if shortname is None else str(shortname).strip()
    raw_text = '' if raw_value is None else str(raw_value).strip()
    if not shortname or not raw_text:
        return raw_value

    shortname_map = overrides.get(shortname, {})
    if raw_text in shortname_map:
        return shortname_map[raw_text]
    return raw_value


def search_tones(locations=None, regions=None, get_raw: bool = False, db_path=QUERY_DB_PATH, region_mode='yindian'):
    all_locations = query_dialect_abbreviations(regions, locations, db_path=db_path, region_mode=region_mode)
    if not all_locations:
        return [] if (get_raw or locations is not None or regions is not None) else []

    conn = sqlite3.connect(db_path)

    placeholders = ','.join(['?'] * len(all_locations))
    query = f"""
    SELECT 簡稱, T1陰平, T2陽平, T3陰上, T4陽上, T5陰去, T6陽去, T7陰入, T8陽入, T9其他調, T10輕聲
    FROM dialects
    WHERE 簡稱 IN ({placeholders})
    """
    df = pd.read_sql(query, conn, params=all_locations)
    conn.close()

    if df.empty:
        return []

    df.set_index('簡稱', inplace=True)
    if all_locations is not None:
        existing_locations = [loc for loc in all_locations if loc in df.index]
        if not existing_locations:
            return []
        df = df.loc[existing_locations]

    overrides = load_tone_value_overrides()

    def process_cell(value, num):
        if value is None or pd.isnull(value):
            return ""
        if isinstance(value, str):
            raw_elements = re.split(r'[，,|;]', value)
            elements = [e.strip() for e in raw_elements if e.strip()]
            processed_elements = []
            need_letter = len(elements) > 1

            for i, element in enumerate(elements):
                letter = chr(97 + i) if need_letter else ""
                if '[' not in element and ']' not in element:
                    processed_elements.append(f"[{num}{letter}]{element}")
                else:
                    processed_elements.append(element)

            return ','.join(processed_elements)
        return value

    match_table = {
        'T1': ['陰平', '平聲', '阴平', '平声'],
        'T2': ['陽平', '阳平'],
        'T3': ['陰上', '上聲', '阴上', '上声'],
        'T4': ['陽上', '阳上'],
        'T5': ['陰去', '去聲', '阴去', '去声'],
        'T6': ['陽去', '阳去'],
        'T7': ['陰入', '阴入'],
        'T8': ['陽入', '阳入']
    }

    for shortname, row in df.iterrows():
        for col_num, col_name in enumerate(df.columns, start=1):
            raw_value = row[col_name]
            mapped_value = apply_tone_value_override(shortname, raw_value, overrides)
            df.at[shortname, col_name] = process_cell(mapped_value, col_num)

    result = []
    new_result = []

    for index, row in df.iterrows():
        total_data = [str(x) if x != "" else "" for x in row.tolist()]
        row_data = {
            "簡稱": index,
            "總數據": total_data
        }
        new_row = {
            "簡稱": index,
            "總數據": total_data,
            "tones": []
        }

        for i in range(1, 9):
            matched = total_data[i - 1]
            raw_value = re.sub(r'\[.*?\]', '', matched)

            if raw_value:
                raw_parts = re.split(r'[，,]', raw_value)
                value_list = []
                name_list = []

                for part in raw_parts:
                    value = ''.join(re.findall(r'\d+', part))
                    name = ''.join(re.findall(r'[^\d,]+', part))
                    if "入" in name:
                        value = f'`{value}'
                    value_list.append(value)
                    name_list.append(name)

                match_list = []
                for name in name_list:
                    matched_t = set()
                    for t, names in match_table.items():
                        if any(matching_name in name for matching_name in names):
                            matched_t.add(t)
                    match_list.extend(list(matched_t))
                    if 'T1' not in match_list and '平' in name and not re.search(r'^(陽|阳)', name):
                        match_list.append('T1')
                    if 'T3' not in match_list and '上' in name and not re.search(r'^(陽|阳)', name):
                        match_list.append('T3')
                    if 'T5' not in match_list and '去' in name and not re.search(r'^(陽|阳)', name):
                        match_list.append('T5')
                    if 'T7' not in match_list and '入' in name and not re.search(r'^(陽|阳)', name):
                        match_list.append('T7')

                match_list = list(set(match_list))
                bracket_nums = re.findall(r'\[(\d+)\]', matched)
                row_data[f"T{i}"] = {
                    'raw': raw_value,
                    'value': value_list,
                    'name': name_list,
                    'match': match_list,
                    'num': bracket_nums
                }
                new_row['tones'].append(
                    {f"T{i}": ','.join(value_list) if value_list else ','.join(match_list) if match_list else '無'})
            else:
                row_data[f"T{i}"] = {
                    'raw': '',
                    'value': [],
                    'name': [],
                    'match': [],
                    'num': []
                }
                new_row['tones'].append({f"T{i}": '無'})

        for i in range(9, 11):
            matched = total_data[i - 1]
            raw_value = re.sub(r'\[.*?\]', '', matched)

            if raw_value:
                raw_parts = re.split(r'[，,]', raw_value)
                value_list = []
                name_list = []

                for part in raw_parts:
                    value = ''.join(re.findall(r'\d+', part))
                    name = ''.join(re.findall(r'[^\d,]+', part))
                    if "入" in name:
                        value = f'`{value}'
                    value_list.append(value)
                    name_list.append(name)

                match_list = []
                for name in name_list:
                    matched_t = set()
                    for t, names in match_table.items():
                        if any(matching_name in name for matching_name in names):
                            matched_t.add(t)
                    match_list.extend(list(matched_t))

                match_list = list(set(match_list))
                bracket_nums = re.findall(r'\[(\d+)\]', matched)
                row_data[f"T{i}"] = {
                    'raw': raw_value,
                    'value': value_list,
                    'name': name_list,
                    'match': match_list,
                    'num': bracket_nums
                }
                new_row['tones'].append(
                    {f"T{i}": ','.join(value_list) if value_list else ','.join(match_list) if match_list else '無'})
            else:
                row_data[f"T{i}"] = {
                    'raw': '',
                    'value': [],
                    'name': [],
                    'match': [],
                    'num': []
                }
                new_row['tones'].append({f"T{i}": '無'})

        for i in range(1, 11):
            t_data = row_data[f"T{i}"]
            if not t_data['value']:
                match_found = []
                for j in range(1, 11):
                    if j != i:
                        t_j_data = row_data[f"T{j}"]
                        if f"T{i}" in t_j_data.get('match', []):
                            match_found.append(f"T{j}")
                if match_found:
                    row_data[f"T{i}"]['match'] = ','.join(match_found)
                    new_row['tones'][i - 1] = {f"T{i}": ','.join(match_found)}
                else:
                    row_data[f"T{i}"]['match'] = '無'
                    new_row['tones'][i - 1] = {f"T{i}": '無'}

        if get_raw:
            result.append(row_data)
        else:
            new_result.append(new_row)

    return result if get_raw else new_result
