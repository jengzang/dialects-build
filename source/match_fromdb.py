import os
import sqlite3
from pathlib import Path

import opencc
import pandas as pd

from common.config import QUERY_DB_PATH, PROCESSED_DATA_DIR
from common.constants import custom_variant_dict


# # 建立雙向映射
# custom_variant_bidict = {}
# for k, v in custom_variant_dict.items():
#     custom_variant_bidict[k] = v
#     custom_variant_bidict[v] = k


def get_tsvs(output_dir=PROCESSED_DATA_DIR, partition_name='全部', single=None):
    # Use the Path object for the directory
    output_dir = Path(output_dir)
    if single:
        file_paths = [str(Path(single))]
    else:
        file_paths = [
            str(f) for f in output_dir.glob("*.tsv") if f.is_file()
        ]

    # ❗以下為遞迴抓子目錄中的 .tsv，已註解
    # file_paths = [str(f) for f in output_dir.rglob("*.tsv") if f.is_file()]

    if not file_paths:
        print("❌ processed 資料夾中找不到任何 .tsv 檔案，程式結束。")
        return

    # 文件名 => 原路径映射
    name_to_path = {
        os.path.splitext(os.path.basename(p))[0]: p
        for p in file_paths
    }

    original_locations = list(name_to_path.keys())
    # print(f"[調試] 自動載入的原始地點：{original_locations}")

    # === 從資料庫讀取簡稱表 ===
    db_path = QUERY_DB_PATH
    with sqlite3.connect(db_path) as conn:
        abbreviation_df = pd.read_sql_query("SELECT 簡稱, 音典分區 FROM dialects", conn)

    # print(f"[調試] 載入的簡稱數量：{len(abbreviation_df)}")

    # 檢查簡稱是否有重複
    duplicated_abbr = abbreviation_df[abbreviation_df.duplicated(subset=['簡稱'], keep=False)]
    if not duplicated_abbr.empty:
        print("[錯誤] 偵測到以下簡稱有重複，請處理後再執行：")
        print(duplicated_abbr[['簡稱']].drop_duplicates())
        raise SystemExit("中止執行：發現重複簡稱。")

    abbr_partition_df = abbreviation_df.dropna(subset=["簡稱", "音典分區"])
    sort_order_abbr = abbr_partition_df["簡稱"].tolist()
    partition_raw = abbr_partition_df["音典分區"].tolist()
    partition_map = {
        name: (region.split('-')[0] if '-' in region else region)
        for name, region in zip(sort_order_abbr, partition_raw)
    }

    converter_s2t = opencc.OpenCC('s2t')
    converter_t2s = opencc.OpenCC('t2s')
    converter_variant = opencc.OpenCC('tw2sp.json')

    def apply_custom_variant(text):
        for old, new in custom_variant_dict.items():
            text = text.replace(old, new)
        return text

    unmatched_locations_step1 = []
    # 篩選分區處理
    partition_filter_set = None
    if partition_name.strip() != "全部":
        selected_parts = partition_name.strip().split()
        partition_filter_set = set(selected_parts)
        print(f"[調試] 篩選分區：{partition_filter_set}")

    matched_abbr_to_path = {}  # abbr -> tsv_path

    # Step 1: 匹配原始名稱
    for loc in original_locations:
        if loc in sort_order_abbr:
            matched_abbr_to_path[loc] = name_to_path[loc]  # 立刻將路徑對應
            # print(f"Step1 匹配：{loc} -> 簡簿 => {name_to_path[loc]}")
        else:
            unmatched_locations_step1.append(loc)

    # Step 2: 簡轉繁匹配
    sort_order_abbr_trad = [converter_s2t.convert(x) for x in sort_order_abbr]
    unmatched_locations_step2 = []
    for loc in unmatched_locations_step1:
        # print(f"Step2 檢查：{loc}")  # 調試輸出
        for abbr, abbr_trad in zip(sort_order_abbr, sort_order_abbr_trad):
            if loc == abbr_trad:
                matched_abbr_to_path[abbr] = name_to_path[loc]  # 使用原始檔名對應到簡稱
                # print(f"Step2 匹配：{abbr} -> 簡轉繁 => {loc} => {name_to_path[loc]}")  # ✅
                break
        else:
            unmatched_locations_step2.append(loc)

    # Step 3: 簡轉簡體匹配
    sort_order_abbr_simp = [converter_t2s.convert(x) for x in sort_order_abbr]
    unmatched_locations_step3 = []
    for loc in unmatched_locations_step2:
        # print(f"Step3 檢查：{loc}")  # 調試輸出
        loc_simp = converter_t2s.convert(loc)
        for abbr, abbr_simp in zip(sort_order_abbr, sort_order_abbr_simp):
            if loc_simp == abbr_simp:
                matched_abbr_to_path[abbr] = name_to_path[loc]  # 使用原始檔名對應到簡稱
                # print(f"Step3 匹配：{loc}(轉簡體) -> 簡簿(轉簡體) => {abbr} => {name_to_path[loc]}")  # ✅
                break
        else:
            unmatched_locations_step3.append(loc)

    # Step 4: 異體字簡化匹配
    abbr_variant_map = {
        converter_variant.convert(abbr): abbr
        for abbr in sort_order_abbr
    }
    unmatched_locations_step4 = []
    for loc in unmatched_locations_step3:
        # print(f"Step4 檢查：{loc}")  # 調試輸出
        loc_var = converter_variant.convert(loc)
        if loc_var in abbr_variant_map:
            abbr = abbr_variant_map[loc_var]
            matched_abbr_to_path[abbr] = name_to_path[loc]
            # print(f"Step4 匹配：{loc}(異體簡化為 {loc_var}) -> 簡簿(異體簡化) => {abbr} => {name_to_path[loc]}")
        else:
            unmatched_locations_step4.append(loc)

    # Step 5: 自定義異體字匹配
    abbr_custom_map = {
        apply_custom_variant(abbr): abbr
        for abbr in sort_order_abbr
    }
    unmatched_locations = []
    for loc in unmatched_locations_step4:
        # print(f"Step5 檢查：{loc}")  # 調試輸出
        loc_custom = apply_custom_variant(loc)
        if loc_custom in abbr_custom_map:
            abbr = abbr_custom_map[loc_custom]
            matched_abbr_to_path[abbr] = name_to_path[loc]
            # print(f"Step5 匹配：{loc}(自定義轉為 {loc_custom}) -> 簡簿(自定義) => {abbr} => {name_to_path[loc]}")
        else:
            unmatched_locations.append(loc)
            # print(f"未匹配：{loc}(自定義轉為 {loc_custom})")  # 調試輸出

    # Step 6: 按順序處理匹配結果
    sorted_matched = [
        abbr for abbr in sort_order_abbr
        if abbr in matched_abbr_to_path and (
                partition_filter_set is None or partition_map.get(abbr, '') in partition_filter_set
        )
    ]

    locations = []
    partitions = []
    sorted_paths = []
    previous_partition = None

    # 使用匹配結果生成最終路徑和分區
    for loc in sorted_matched:
        current_partition = partition_map.get(loc, '')

        # === 優先使用前面比對階段已對應的檔名 ===
        chosen_path = matched_abbr_to_path.get(loc)

        if chosen_path is None:
            # === 五重轉換匹配 ===
            candidates = [name for name in name_to_path if loc == name or
                          converter_s2t.convert(name) == loc or
                          converter_t2s.convert(name) == loc or
                          converter_variant.convert(name) == loc or
                          apply_custom_variant(name) == loc]

            if not candidates:
                print(f"[⚠️ 無匹配檔案] 找不到 {loc} 對應的來源檔案")
                continue  # 如果找不到對應的檔案，跳過這個簡稱
            elif len(candidates) == 1:
                chosen_path = name_to_path[candidates[0]]
            else:
                # 多重匹配，選擇修改時間較新的檔案
                chosen = max(candidates, key=lambda x: os.path.getmtime(name_to_path[x]))
                print(f"[⚠️ 多重匹配] 簡稱 '{loc}' 命中多個來源，保留較新檔案：'{chosen}'")
                for c in candidates:
                    mtime = os.path.getmtime(name_to_path[c])
                    print(f" - {c}: 修改時間 {mtime}")
                chosen_path = name_to_path[chosen]

        # === 分區斷開顯示 ===
        if previous_partition is not None and current_partition != previous_partition:
            locations.append("_")
            sorted_paths.append("_")
            partitions.append("")

        locations.append(loc)
        sorted_paths.append(chosen_path)  # 使用選擇的檔案路徑
        partitions.append(current_partition)
        previous_partition = current_partition

    # print("\n=== 最終排序結果 ===")
    # for loc, part in zip(locations, partitions):
    # print(f"{loc}\t{part}")

    if (not single) and unmatched_locations:
        print("\n=== 未匹配 ===")
        print(unmatched_locations)
    elif single and unmatched_locations:
        print(f"[❌ 單一模式] 無法為檔案 {single} 匹配任何簡稱。")

    return sorted_paths, locations, partitions


# if __name__ == "__main__":
#     locations= get_tsvs(single=r"C:\Users\joengzaang\PycharmProjects\process_phonology\data\yindian\尙志.tsv")[1]
#     # print("sorted_paths", sorted_paths)
#     print("locations:", locations)
#     print( len(locations))
    # print(partitions)
    # for path, name, part in zip(sorted_paths, locations, partitions):
    #     print(f"{part}\t{name}\t{path}")
