import os
import sqlite3
from pathlib import Path

import opencc
import pandas as pd

from common.config import QUERY_DB_PATH, PROCESSED_DATA_DIR
from common.constants import custom_variant_dict

# 創建全局 OpenCC 實例，避免重複初始化
converter_s2t = opencc.OpenCC('s2t.json')
converter_t2s = opencc.OpenCC('t2s.json')
converter_variant = opencc.OpenCC('tw2sp.json')


# # 建立雙向映射
# custom_variant_bidict = {}
# for k, v in custom_variant_dict.items():
#     custom_variant_bidict[k] = v
#     custom_variant_bidict[v] = k


def get_tsvs(output_dir=PROCESSED_DATA_DIR, partition_name='全部', single=None, query_db_path=None):
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
    db_path = query_db_path if query_db_path else QUERY_DB_PATH
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

    # 使用全局的 OpenCC 實例（已在模塊級別初始化）

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
    sort_order_abbr_trad = [
        converter_s2t.convert(x) for x in sort_order_abbr
        if isinstance(x, str) and x  # 確保是非空字符串
    ]
    unmatched_locations_step2 = []
    for loc in unmatched_locations_step1:
        # print(f"Step2 檢查：{loc}")  # 調試輸出
        if not isinstance(loc, str) or not loc:
            unmatched_locations_step2.append(loc)
            continue
        for abbr, abbr_trad in zip(sort_order_abbr, sort_order_abbr_trad):
            if loc == abbr_trad:
                matched_abbr_to_path[abbr] = name_to_path[loc]  # 使用原始檔名對應到簡稱
                # print(f"Step2 匹配：{abbr} -> 簡轉繁 => {loc} => {name_to_path[loc]}")  # ✅
                break
        else:
            unmatched_locations_step2.append(loc)

    # Step 3: 簡轉簡體匹配
    sort_order_abbr_simp = [
        converter_t2s.convert(x) for x in sort_order_abbr
        if isinstance(x, str) and x  # 確保是非空字符串
    ]
    unmatched_locations_step3 = []
    for loc in unmatched_locations_step2:
        # print(f"Step3 檢查：{loc}")  # 調試輸出
        if not isinstance(loc, str) or not loc:
            unmatched_locations_step3.append(loc)
            continue
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
        if isinstance(abbr, str) and abbr  # 確保是非空字符串
    }
    unmatched_locations_step4 = []
    for loc in unmatched_locations_step3:
        # print(f"Step4 檢查：{loc}")  # 調試輸出
        if not isinstance(loc, str) or not loc:
            unmatched_locations_step4.append(loc)
            continue
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
        if isinstance(abbr, str) and abbr  # 確保是非空字符串
    }
    unmatched_locations = []
    for loc in unmatched_locations_step4:
        # print(f"Step5 檢查：{loc}")  # 調試輸出
        if not isinstance(loc, str) or not loc:
            unmatched_locations.append(loc)
            continue
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


def scan_tsv_files_no_db(output_dir):
    """
    掃描目錄中的 TSV 文件（不依賴數據庫）

    Args:
        output_dir: 要掃描的目錄路徑

    Returns:
        dict: {文件名(不含擴展名): 完整路徑}
    """
    from pathlib import Path

    output_path = Path(output_dir)
    tsv_files = {}

    if output_path.exists():
        for tsv_file in output_path.glob("*.tsv"):
            if tsv_file.is_file():
                filename = tsv_file.stem  # 不含擴展名
                tsv_files[filename] = str(tsv_file)

    return tsv_files


def scan_tsv_with_conflict_resolution(mode='admin', append_df=None):
    """
    掃描 TSV 文件並處理重名衝突（不依賴數據庫）

    Args:
        mode: 'admin' 或 'user'
        append_df: APPEND_PATH 的 DataFrame（用於獲取 isUser 列）

    Returns:
        tuple: (tsv_paths, sources)
            - tsv_paths: TSV 路徑列表
            - sources: 字典 {簡稱: 'yindian' 或 'processed'}
    """
    import json
    from datetime import datetime
    from pathlib import Path
    from common.config import YINDIAN_DATA_DIR, PROCESSED_DATA_DIR, BASE_DIR
    from common.s2t import simplified2traditional, traditional2simplified

    # 配置文件路徑
    config_file = Path(BASE_DIR) / "data" / "conflict_resolutions.json"

    def load_conflict_config():
        """讀取衝突解決配置"""
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 根據模式返回對應的配置
                    return config.get(mode, {}).get('conflict_resolutions', {})
            except:
                return {}
        return {}

    def save_conflict_config(resolutions):
        """保存衝突解決配置"""
        # 讀取現有配置
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                config = {}
        else:
            config = {}

        # 確保模式鍵存在
        if mode not in config:
            config[mode] = {}

        # 更新配置
        config[mode]['conflict_resolutions'] = resolutions
        config[mode]['last_updated'] = datetime.now().isoformat()

        # 保存配置
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def count_lines(file_path):
        """統計 TSV 文件行數"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for line in f) - 1  # 減去表頭
        except:
            return 0

    # 讀取已保存的衝突解決配置
    saved_resolutions = load_conflict_config()

    # 第一步：掃描 yindian 目錄
    print(f"   掃描 yindian 目錄...")
    yindian_files = scan_tsv_files_no_db(YINDIAN_DATA_DIR)
    print(f"   找到 {len(yindian_files)} 個 yindian TSV 文件")

    # 第二步：掃描 processed 目錄
    print(f"   掃描 processed 目錄...")
    processed_files = scan_tsv_files_no_db(PROCESSED_DATA_DIR)

    # User 模式：過濾 processed 文件
    if mode == 'user' and append_df is not None:
        print(f"   User 模式：過濾 isUser=1 的文件...")
        print(f"   [DEBUG] append_df 列名: {append_df.columns.tolist()}")
        print(f"   [DEBUG] 'isUser' 在列名中: {'isUser' in append_df.columns}")
        if 'isUser' in append_df.columns:
            print(f"   [DEBUG] isUser 唯一值: {append_df['isUser'].unique()}")
            print(f"   [DEBUG] isUser=1 的數量: {append_df[append_df['isUser'] == 1.0].shape[0]}")

        filtered_processed = {}
        for filename, filepath in processed_files.items():
            # 嘗試多種變體匹配
            variants = [filename]
            try:
                variants.append(simplified2traditional(filename))
            except:
                pass
            try:
                variants.append(traditional2simplified(filename))
            except:
                pass

            # 檢查是否在 APPEND_PATH 中且 isUser=1
            is_user_file = False
            for variant in variants:
                matching_rows = append_df[append_df['簡稱'] == variant]
                if not matching_rows.empty:
                    is_user_value = matching_rows.iloc[0].get('isUser', 0)
                    # 檢查多種可能的值格式（包括 numpy.float64(1.0)）
                    if is_user_value == 1 or is_user_value == 1.0 or is_user_value == '1' or is_user_value == True:
                        is_user_file = True
                        print(f"   [DEBUG] 匹配: {filename} -> {variant}, isUser={is_user_value}")
                        break

            if is_user_file:
                filtered_processed[filename] = filepath

        processed_files = filtered_processed
        print(f"   過濾後：{len(processed_files)} 個 processed TSV 文件")
    else:
        print(f"   找到 {len(processed_files)} 個 processed TSV 文件")

    # 第三步：檢測衝突並交互式解決
    final_files = {}
    sources = {}
    all_filenames = set(yindian_files.keys()) | set(processed_files.keys())
    new_resolutions = {}  # 記錄新的選擇

    for filename in sorted(all_filenames):
        in_yindian = filename in yindian_files
        in_processed = filename in processed_files

        if in_yindian and in_processed:
            # 衝突：檢查是否有保存的選擇
            if filename in saved_resolutions:
                saved_choice = saved_resolutions[filename]
                if saved_choice == 'yindian' and in_yindian:
                    final_files[filename] = yindian_files[filename]
                    sources[filename] = 'yindian'
                    print(f"   [自動] {filename}.tsv -> 使用已保存的選擇: yindian")
                elif saved_choice == 'processed' and in_processed:
                    final_files[filename] = processed_files[filename]
                    sources[filename] = 'processed'
                    print(f"   [自動] {filename}.tsv -> 使用已保存的選擇: processed")
                else:
                    # 保存的選擇無效（文件可能已刪除），重新詢問
                    print(f"\n   [警告] {filename}.tsv 的保存選擇無效，需要重新選擇")
                    saved_resolutions.pop(filename, None)  # 移除無效配置
                    # 繼續下面的交互式選擇

            # 如果沒有保存的選擇或保存的選擇無效，詢問用戶
            if filename not in sources:
                yindian_path = yindian_files[filename]
                processed_path = processed_files[filename]
                yindian_lines = count_lines(yindian_path)
                processed_lines = count_lines(processed_path)

                print(f"\n   發現重名文件：{filename}.tsv")
                print(f"   1. {yindian_path} ({yindian_lines} 行)")
                print(f"   2. {processed_path} ({processed_lines} 行)")

                while True:
                    choice = input("   請選擇 (1/2): ").strip()
                    if choice == '1':
                        final_files[filename] = yindian_path
                        sources[filename] = 'yindian'
                        new_resolutions[filename] = 'yindian'
                        print(f"   已選擇：yindian/{filename}.tsv")
                        break
                    elif choice == '2':
                        final_files[filename] = processed_path
                        sources[filename] = 'processed'
                        new_resolutions[filename] = 'processed'
                        print(f"   已選擇：processed/{filename}.tsv")
                        break
                    else:
                        print("   無效選擇，請輸入 1 或 2")

        elif in_yindian:
            final_files[filename] = yindian_files[filename]
            sources[filename] = 'yindian'

        elif in_processed:
            final_files[filename] = processed_files[filename]
            sources[filename] = 'processed'

    # 保存新的選擇（合併到已有配置中）
    if new_resolutions:
        saved_resolutions.update(new_resolutions)
        save_conflict_config(saved_resolutions)
        print(f"\n   已保存 {len(new_resolutions)} 個新的衝突解決選擇到配置文件")

    # 返回路徑列表和來源字典
    tsv_paths = [final_files[name] for name in sorted(final_files.keys())]

    return tsv_paths, sources


# if __name__ == "__main__":
#     locations= get_tsvs(single=r"C:\Users\joengzaang\PycharmProjects\process_phonology\data\yindian\尙志.tsv")[1]
#     # print("sorted_paths", sorted_paths)
#     print("locations:", locations)
#     print( len(locations))
    # print(partitions)
    # for path, name, part in zip(sorted_paths, locations, partitions):
    #     print(f"{part}\t{name}\t{path}")
