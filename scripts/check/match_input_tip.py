import re
import sqlite3
from difflib import SequenceMatcher

from pypinyin import lazy_pinyin

from common.config import QUERY_DB_PATH
from common.s2t import s2t_pro


def match_locations(user_input, filter_valid_abbrs_only=True, exact_only=True, query_db=QUERY_DB_PATH):
    def is_pinyin_similar(a, b, threshold=0.9):
        if not a or not b:
            return False
        a_pinyin = ''.join(lazy_pinyin(a)).lower()
        b_pinyin = ''.join(lazy_pinyin(b)).lower()
        ratio = SequenceMatcher(None, a_pinyin, b_pinyin).ratio()
        return ratio >= threshold

    def is_similar(a, b, threshold=0.7):
        if not a or not b:
            return False
        similarity = SequenceMatcher(None, a, b).ratio()
        return similarity >= threshold

    # print(f"[DEBUG] 使用者輸入：{user_input}")

    def generate_strict_candidates(mapping, input_len):
        # 每個位置逐字取候選值組合（不產生交叉混用）
        combinations = [[]]
        for _, candidates in mapping:
            new_combos = []
            for combo in combinations:
                for c in candidates:
                    new_combos.append(combo + [c])
            combinations = new_combos
        # 合併成詞，保證長度一致
        return {''.join(chars) for chars in combinations if len(chars) == input_len}

    # 使用 s2t_pro 轉換
    converted_str, mapping = s2t_pro(user_input, level=2)
    input_len = len(user_input)

    # 安全構造詞組候選集
    converted_candidates = generate_strict_candidates(mapping, input_len)

    # possible_inputs 包含：
    # - 原輸入
    # - 轉換字詞（保證不交叉）
    # - clean_str（第一候選組合）
    possible_inputs = set([user_input, converted_str]) | converted_candidates

    conn = sqlite3.connect(query_db)
    cursor = conn.cursor()

    # 根據 filter_valid_abbrs_only 決定是否過濾掉非存儲標記為1的數據

    if filter_valid_abbrs_only:
        # print("過濾！！")
        cursor.execute("SELECT 簡稱 FROM dialects WHERE 存儲標記 = 1")
    else:
        # print("不過濾存儲標記")
        cursor.execute("SELECT 簡稱 FROM dialects")
    valid_abbrs_set = set(row[0] for row in cursor.fetchall())

    matched_abbrs = set()
    for term in possible_inputs:
        # 完全匹配查詢部分需要根據 filter_valid_abbrs_only 來過濾
        if filter_valid_abbrs_only:
            cursor.execute("SELECT 簡稱 FROM dialects WHERE 簡稱 = ? AND 存儲標記 = 1", (term,))
        else:
            cursor.execute("SELECT 簡稱 FROM dialects WHERE 簡稱 = ?", (term,))
        exact = cursor.fetchall()
        matched_abbrs.update([row[0] for row in exact])
        # print(f"[DEBUG] 完全匹配【{term}】：{exact}")

    # 如果指定只做完全匹配，但找不到，提前返回空
    if exact_only and not matched_abbrs:
        return [], 0, [], [], [], [], [], []

    # 原來的邏輯保留：有完全匹配就返回
    if matched_abbrs:
        return list(matched_abbrs), 1, [], [], [], [], [], []

    fuzzy_abbrs = set()
    for term in possible_inputs:
        # 模糊匹配查詢部分需要根據 filter_valid_abbrs_only 來過濾
        if filter_valid_abbrs_only:
            cursor.execute("SELECT 簡稱 FROM dialects WHERE 簡稱 LIKE ? AND 存儲標記 = 1", (term + "%",))
        else:
            cursor.execute("SELECT 簡稱 FROM dialects WHERE 簡稱 LIKE ?", (term + "%",))
        fuzzy = cursor.fetchall()
        fuzzy_abbrs.update([row[0] for row in fuzzy])
        # print(f"[DEBUG] 模糊簡稱匹配【{term}】：{fuzzy}")

    geo_matches = set()
    geo_abbr_map = {}
    all_geo_names = []
    all_abbr_names = []

    for col in ["鎮", "行政村", "自然村"]:
        if filter_valid_abbrs_only:
            cursor.execute(f"SELECT {col}, 簡稱 FROM dialects WHERE 存儲標記 = 1")
        else:
            cursor.execute(f"SELECT {col}, 簡稱 FROM dialects")
        rows = cursor.fetchall()
        for name, abbr in rows:
            all_geo_names.append(name)
            all_abbr_names.append(abbr)
            for term in possible_inputs:
                if term in (name or ""):
                    geo_matches.add(name)
                    geo_abbr_map[name] = abbr

    # 加上所有簡稱（用於相似與拼音匹配）
    all_names = all_geo_names + list(valid_abbrs_set)
    all_abbrs = all_abbr_names + list(valid_abbrs_set)

    fuzzy_geo_matches = set()
    fuzzy_geo_abbrs = set()
    sound_like_matches = set()
    sound_like_abbrs = set()

    for name, abbr in zip(all_names, all_abbrs):
        if not name or not abbr or abbr not in valid_abbrs_set:
            continue

        if is_similar(user_input, name):
            # print(f"[DEBUG] 相似匹配: '{user_input}' ≈ '{name}' (abbr: {abbr})")
            fuzzy_geo_matches.add(name)
            fuzzy_geo_abbrs.add(abbr)

        if is_pinyin_similar(user_input, name):
            # print(f"[DEBUG] 拼音匹配: '{user_input}' ≈ '{name}' (abbr: {abbr})")
            sound_like_matches.add(name)
            sound_like_abbrs.add(abbr)

    return (
        list(fuzzy_abbrs),
        0,
        list(geo_matches),
        [geo_abbr_map[n] for n in geo_matches if geo_abbr_map[n] in valid_abbrs_set],
        list(fuzzy_geo_matches),
        list(fuzzy_geo_abbrs),
        list(sound_like_matches),
        list(sound_like_abbrs),
    )


def match_locations_batch(input_string: str, filter_valid_abbrs_only=True, exact_only=True, query_db=QUERY_DB_PATH
                          ):
    input_string = input_string.strip()
    if not input_string:
        # print("⚠️ 輸入為空，無法處理。")
        return []

    # 以多種分隔符切分
    parts = re.split(r"[ ,;/，；、]+", input_string)
    results = []

    for idx, part in enumerate(parts):
        part = part.strip()
        if part:
            # print(f"\n🔹 處理第 {idx + 1} 個地名：{part}")
            try:
                res = match_locations(part, filter_valid_abbrs_only, exact_only, query_db=query_db)
                results.append(res)
            except Exception as e:
                print(f"   ❌ 發生錯誤：{e}")
                results.append((False, 0, [], [], [], [], [], []))

    return results
