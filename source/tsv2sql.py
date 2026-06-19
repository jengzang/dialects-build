import os
import re
import sqlite3
import sys
import traceback
import time
from pathlib import Path

import pandas as pd

from common.constants import (
    exclude_files,
    DIALECT_BASE_REQUIRED_COLUMNS,
    DIALECT_METADATA_RENAME_MAP,
    DIALECT_METADATA_REQUIRED_COLUMNS,
)
from source.change_coordinates import GPSUtil
from common.config import (HAN_PATH, APPEND_PATH, QUERY_DB_PATH, DIALECTS_DB_PATH, CHARACTERS_DB_PATH, \
                           MISSING_DATA_LOG, WRITE_INFO_LOG, YINDIAN_DATA_DIR, UPDATE_DATA_DIR, QUERY_DB_ADMIN_PATH,
                           QUERY_DB_USER_PATH, DIALECTS_DB_ADMIN_PATH, DIALECTS_DB_USER_PATH)
from source.character_table_specs import (
    ADDITIONAL_CHARACTER_TABLE_SPECS,
    LEGACY_CHARACTER_TABLE_NAMES,
    PHONOLOGY_TABLE_SPEC,
)
from source.match_fromdb import scan_tsv_with_conflict_resolution
from common.s2t import simplified2traditional, traditional2simplified
from source.get_new import extract_all_from_files
from source.match_fromdb import get_tsvs


WEN_BAI_LITERARY_MARK = '2'
WEN_BAI_COLLOQUIAL_MARK = '3'
WEN_BAI_MARKS = {
    '=': WEN_BAI_LITERARY_MARK,
    '-': WEN_BAI_COLLOQUIAL_MARK,
}


def split_wenbai_marker(value):
    text = '' if value is None else str(value).strip()
    if not text:
        return '', ''

    marker = WEN_BAI_MARKS.get(text[-1])
    if marker:
        return text[:-1].strip(), marker
    return text, ''


def apply_polyphonic_labels(merged_df, group_columns):
    if merged_df.empty:
        return merged_df

    result = merged_df.copy()
    syllable_counts = result.groupby(group_columns)['音節'].transform('nunique')
    is_polyphonic = syllable_counts > 1
    has_wenbai_mark = result['多音字'].isin([WEN_BAI_LITERARY_MARK, WEN_BAI_COLLOQUIAL_MARK])
    fill_mask = is_polyphonic & ~has_wenbai_mark & (result['多音字'].fillna('').astype(str).str.strip() == '')
    result.loc[fill_mask, '多音字'] = '1'
    return result


def build_dialect_database(mode='admin'):
    """
    構建方言查詢數據庫

    Args:
        mode: 'admin' 或 'user'

    Returns:
        list: TSV 路徑列表（用於後續寫入數據）
    """

    # 1. 確定數據庫路徑
    if mode == 'admin':
        sqlite_db = Path(QUERY_DB_ADMIN_PATH)
    else:  # user
        sqlite_db = Path(QUERY_DB_USER_PATH)

    print(f"\n 構建 {mode} 模式數據庫：{sqlite_db}")

    han_file = Path(HAN_PATH)
    other_file = Path(APPEND_PATH)

    rename_map = DIALECT_METADATA_RENAME_MAP
    base_required_columns = DIALECT_BASE_REQUIRED_COLUMNS

    # --- C. 定義校驗函數 ---
    def validate_required_columns(df_columns, filename):
        """
        嚴格檢查文件是否包含所有必要欄位（Mapping + Base）。
        除了 'isUser' 和 '存儲標記' 以外，缺失任何欄位都會報錯。
        """
        missing_cols = [col for col in DIALECT_METADATA_REQUIRED_COLUMNS if col not in df_columns]

        if missing_cols:
            print(f"\n❌ 嚴重錯誤：文件【{filename}】缺少必要欄位！程序終止。")
            print(f"   缺失的欄位 ({len(missing_cols)}個): {missing_cols}")
            print(f"   實際讀到的欄位 ({len(df_columns)}個): {list(df_columns)}")
            print(f"   請檢查 Excel 表頭是否被修改，或是否有隱藏字符。")
            sys.exit(1)

    # --- D. 最終需要的欄位列表 (用於篩選) ---
    # 這裡包含 isUser，如果 DataFrame 裡有就保留，沒有拉倒
    final_columns_filter = base_required_columns + ["存儲標記", "isUser"] + list(rename_map.keys())

    # --- 讀取 Append_files.xlsx ---
    print(f"⏳ 正在讀取並校驗 {other_file.name} ...")
    df_other = pd.read_excel(other_file, sheet_name="檔案", header=0)
    df_other.columns = df_other.columns.str.strip()  # 先去空格

    # 【執行校驗】
    validate_required_columns(df_other.columns, other_file.name)

    df_other["存儲標記"] = ""  # 代碼生成，無需校驗

    # 安全篩選：只保留我們定義在 final_columns_filter 裡的列，且該列必須真的存在於 df 中
    df_other = df_other[[col for col in final_columns_filter if col in df_other.columns]].copy()
    df_other = df_other.rename(columns=rename_map)

    # --- 讀取 漢字音典表 ---
    print(f"⏳ 正在讀取並校驗 {han_file.name} ...")
    # 跳過第 2 行（即 index 0）
    df_han = pd.read_excel(han_file, sheet_name="檔案", header=0, engine='openpyxl', keep_default_na=False)
    df_han = df_han.drop(index=0).reset_index(drop=True)
    df_han.columns = df_han.columns.str.strip()  # 先去空格

    # 【執行校驗】
    validate_required_columns(df_han.columns, han_file.name)

    df_han["存儲標記"] = ""  # 代碼生成，無需校驗
    df_han = df_han[[col for col in final_columns_filter if col in df_han.columns]].copy()
    df_han = df_han.rename(columns=rename_map)

    # --- 處理經緯度轉換 ---
    def convert_coordinates(df):
        """
        對 '經緯度' 列進行坐標轉換：BD-09 (百度) → WGS-84 (GPS)
        """
        new_coordinates = []
        for coords in df['經緯度']:
            # 如果經緯度為空，跳過
            if pd.isna(coords) or coords.strip() == '':
                new_coordinates.append(None)  # 如果是空值，將經緯度設為 None
                continue

            # 確保 coords 是字符串類型
            coords = str(coords).strip()

            # 分割經緯度（格式：經度,緯度）
            bd_lon, bd_lat = map(float, re.split(r'[，,]', coords))

            # BD-09 → WGS-84 轉換（注意：GPSUtil 參數順序是 lat, lon）
            wgs_lat, wgs_lon = GPSUtil.bd09_to_gps84(bd_lat, bd_lon)
            new_coordinates.append(f"{wgs_lon},{wgs_lat}")  # 存儲格式：經度,緯度

        # 更新 '經緯度' 列
        df['經緯度'] = new_coordinates
        return df

    # 處理 df_other 和 df_han 兩個 DataFrame
    df_other = convert_coordinates(df_other)
    df_han = convert_coordinates(df_han)

    # 2. 讀取兩個 Excel 文件
    print("\n⏳ 讀取元數據文件...")
    print(f"   HAN_PATH: {len(df_han)} 個方言點")
    print(f"   APPEND_PATH: {len(df_other)} 個方言點")

    # 3. 掃描 TSV 文件並處理衝突（不依賴數據庫）
    print(f"\n⏳ 掃描 TSV 文件（{mode} 模式）...")
    print(f"   正在掃描 yindian 和 processed 目錄...")
    tsv_paths, sources = scan_tsv_with_conflict_resolution(mode=mode, append_df=df_other)

    print(f"\n✅ 最終確定 {len(tsv_paths)} 個 TSV 文件")

    # 4. 根據 TSV 來源選擇元數據
    print(f"\n⏳ 根據 TSV 來源選擇元數據...")
    # 建立 簡稱 -> TSV來源 的映射（處理繁簡轉換）
    tsv_name_to_source = {}
    for filename, source in sources.items():
        variants = [filename]
        try:
            variants.append(simplified2traditional(filename))
        except:
            pass
        try:
            variants.append(traditional2simplified(filename))
        except:
            pass

        for variant in variants:
            tsv_name_to_source[variant] = source

    print(f"   建立了 {len(tsv_name_to_source)} 個簡稱映射")
    print(f"\n⏳ 匹配元數據與 TSV 文件...")

    final_rows = []
    all_abbr = set(df_han['簡稱'].tolist() + df_other['簡稱'].tolist())
    print(f"   共有 {len(all_abbr)} 個唯一簡稱需要處理")

    # User 模式：只保留 isUser=1 的簡稱
    if mode == 'user':
        print(f"\n User 模式：過濾 isUser=1 的簡稱...")
        if 'isUser' in df_other.columns:
            user_abbr = set(df_other[df_other['isUser'] == 1]['簡稱'].tolist())
            # 保留 HAN 中的所有簡稱 + APPEND 中 isUser=1 的簡稱
            han_abbr = set(df_han['簡稱'].tolist())
            all_abbr = han_abbr | user_abbr
            print(f"   HAN 簡稱: {len(han_abbr)} 個")
            print(f"   APPEND isUser=1 簡稱: {len(user_abbr)} 個")
            print(f"   合併後: {len(all_abbr)} 個")
        else:
            print(f"   警告：APPEND_PATH 中沒有 isUser 列，使用所有簡稱")

    for idx, abbr in enumerate(all_abbr, 1):
        # 每處理 100 個簡稱打印一次進度
        if idx % 100 == 0 or idx == len(all_abbr):
            print(f"   處理進度: {idx}/{len(all_abbr)}")

        # 檢查是否有對應的 TSV 文件
        source = tsv_name_to_source.get(abbr)

        # 根據 TSV 來源選擇元數據
        if source == 'yindian':
            # 有 yindian TSV：優先使用 HAN_PATH
            rows_han = df_han[df_han['簡稱'] == abbr]
            if not rows_han.empty:
                selected_row = rows_han.iloc[0]
            else:
                # HAN 中沒有，嘗試 APPEND
                rows_other = df_other[df_other['簡稱'] == abbr]
                if not rows_other.empty:
                    selected_row = rows_other.iloc[0]
                else:
                    continue

        elif source == 'processed':
            # 有 processed TSV：優先使用 APPEND_PATH
            rows_other = df_other[df_other['簡稱'] == abbr]
            if not rows_other.empty:
                selected_row = rows_other.iloc[0]
            else:
                # APPEND 中沒有，嘗試 HAN
                rows_han = df_han[df_han['簡稱'] == abbr]
                if not rows_han.empty:
                    selected_row = rows_han.iloc[0]
                else:
                    continue

        else:
            # 沒有 TSV 文件：優先使用 HAN_PATH，如果 HAN 沒有則使用 APPEND
            rows_han = df_han[df_han['簡稱'] == abbr]
            if not rows_han.empty:
                selected_row = rows_han.iloc[0]
            else:
                rows_other = df_other[df_other['簡稱'] == abbr]
                if not rows_other.empty:
                    selected_row = rows_other.iloc[0]
                else:
                    continue

        final_rows.append(selected_row)

    # 5. 建立最終 DataFrame
    print(f"\n⏳ 建立最終 DataFrame（共 {len(final_rows)} 個方言點）...")
    final_df = pd.DataFrame(final_rows)

    # 6. 應用地圖集二分區替換邏輯
    print(f"⏳ 應用地圖集二分區替換邏輯...")

    def replace_dialect_zone(val):
        if isinstance(val, str):
            if val.startswith("客家話-粵北片"):
                return val.replace("客家話-粵北片", "客家話-粵北片·客", 1)
            elif val.startswith("平話和土話-粵北片"):
                return val.replace("平話和土話-粵北片", "平話和土話-粵北片·土", 1)
        return val

    final_df["地圖集二分區"] = final_df["地圖集二分區"].apply(replace_dialect_zone)

    # 7. 排序
    print(f"⏳ 按音典排序排序...")
    final_df = final_df.sort_values(by="音典排序", na_position="last")

    # 8. 寫入 SQLite
    print(f"⏳ 寫入 SQLite 數據庫...")
    with sqlite3.connect(sqlite_db) as conn:
        # 寫入資料庫
        final_df.to_sql("dialects", conn, if_exists="replace", index=False)
        print(f"⏳ 創建索引...")
        # 加索引
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dialects_code ON dialects(簡稱);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dialects_yindian_zone ON dialects(音典分區);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dialects_atlas_zone ON dialects(地圖集二分區);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dialects_flag ON dialects(存儲標記);")
        # 新增：複合索引，優化常見查詢 WHERE 簡稱 = ? AND 存儲標記 = ?
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dialects_code_flag ON dialects(簡稱, 存儲標記);")
        # 🚀 【优先级高】用于 match_input_tip.py 的存储标记过滤
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dialects_storage ON dialects(存儲標記, 簡稱);")
        #  優化：音典分區+存儲標記複合索引（用於模糊匹配查詢）
        conn.execute("CREATE INDEX IF NOT EXISTS idx_query_partition_storage ON dialects(音典分區, 存儲標記);")
        # 優化：地圖集分區+存儲標記複合索引（用於match_input_tip.py）
        conn.execute("CREATE INDEX IF NOT EXISTS idx_query_atlas_storage ON dialects(地圖集二分區, 存儲標記);")

    print(f"✅ SQLite 資料庫已建立，dialects 表已更新完成。")

    # 返回 TSV 路徑列表（用於 write_to_sql）
    return tsv_paths


def process_all2sql(tsv_paths, db_path, append=False, update=False, query_db_path=None):
    log_dirs = {
        os.path.dirname(MISSING_DATA_LOG),
        os.path.dirname(WRITE_INFO_LOG),
    }
    for log_dir in log_dirs:
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    #  优化：设置 SQLite 性能参数
    cursor.execute("PRAGMA synchronous = OFF")  # 关闭同步写入
    cursor.execute("PRAGMA journal_mode = MEMORY")  # 使用内存日志
    cursor.execute("PRAGMA temp_store = MEMORY")  # 临时数据存内存

    if not append and not update:  # MODIFIED: Don't drop if update mode
        cursor.execute("DROP TABLE IF EXISTS dialects")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dialects (
            簡稱 TEXT,
            漢字 TEXT,
            音節 TEXT,
            聲母 TEXT,
            韻母 TEXT,
            聲調 TEXT,
            註釋 TEXT,
            多音字 TEXT
        )
    ''')
    conn.commit()

    log_lines = []
    update_簡稱_list = []  # Track which 簡稱 to update
    processed_簡稱 = []  # Track which 簡稱 were actually processed
    missing_data_logs = []  # 🚀 优化：批量收集缺失数据日志

    def clean_join(series):
        return ", ".join(x.strip() for x in series.dropna().astype(str).unique() if x and x.strip())

    # 只有当 append=True 时，才进行筛选
    if append:
        try:
            df_append = pd.read_excel(APPEND_PATH, sheet_name="檔案")
            update_rows = df_append[df_append['待更新'] == 1]
            update_簡稱_list = update_rows['簡稱'].dropna().unique().tolist()
        except:
            print("读取 APPEND_PATH 文件失败，跳过筛选。")

    elif update:
        # NEW: For update mode, extract 簡稱 from TSV filenames
        print(f"📌 update 模式：正在提取待更新的方言點...")
        for path in tsv_paths:
            try:
                tsv_result = get_tsvs(single=path, query_db_path=query_db_path)
                if tsv_result and len(tsv_result) >= 2 and tsv_result[1]:
                    tsv_name = tsv_result[1][0]
                    if tsv_name not in update_簡稱_list:
                        update_簡稱_list.append(tsv_name)
            except:
                continue

        print(f"📌 update 模式：將更新 {len(update_簡稱_list)} 個方言點")
        print(f"   簡稱列表: {update_簡稱_list}")

    # 如果 append 为 True，删除数据库中与待更新行中"簡稱"匹配的记录
    if (append or update) and update_簡稱_list:
        for 簡稱 in update_簡稱_list:
            cursor.execute("DELETE FROM dialects WHERE 簡稱 = ?", (簡稱,))
        conn.commit()
        print(f"✅ 已刪除 {len(update_簡稱_list)} 個方言點的舊數據")

    for idx, path in enumerate(tsv_paths, 1):
        if path == "_":
            continue

        # 獲取 TSV 文件的簡稱
        try:
            tsv_result = get_tsvs(single=path, query_db_path=query_db_path)
            if tsv_result is None or len(tsv_result) < 2 or not tsv_result[1]:
                # 無法匹配簡稱，跳過該文件
                print(f"\n [{idx}/{len(tsv_paths)}] [跳過] 無法匹配簡稱：{os.path.basename(path)}")
                continue
            tsv_name = tsv_result[1][0]
        except (IndexError, TypeError) as e:
            # 無法匹配簡稱，跳過該文件
            print(f"\n [{idx}/{len(tsv_paths)}] [跳過] 無法匹配簡稱：{os.path.basename(path)}")
            continue

        now_process = f"\n [{idx}/{len(tsv_paths)}] 正在處理：{tsv_name}"
        print(now_process)
        missing_data_logs.append(now_process)  # 🚀 优化：收集日志，稍后批量写入

        # 如果 append 为 True，则进行筛选 (update mode processes all files)
        if append and update_簡稱_list and tsv_name not in update_簡稱_list:
            print(f"跳過：{tsv_name} (不在待更新清單中)")
            continue

        try:
            df = extract_all_from_files(path, query_db_path=query_db_path)
            print(f"  📄 提取資料表：{len(df)} 行")

            df = df.fillna("")
            df["漢字"] = df["汉字"].astype(str).str.strip()
            split_results = df["音标"].apply(split_wenbai_marker)
            df["音節"] = split_results.str[0]
            df["多音字"] = split_results.str[1]
            df["聲母"] = df["声母"].astype(str).str.strip()
            df["韻母"] = df["韵母"].astype(str).str.strip()
            df["聲調"] = df["声调"].astype(str).str.strip()
            df["註釋"] = df["註釋"].astype(str).str.strip() if "註釋" in df.columns else ""

            # 🚀 优化：使用向量化操作过滤数据，避免 iterrows()
            # 1. 过滤：至少有一个音韵特征不为空
            has_any = (df["聲母"] != "") | (df["韻母"] != "") | (df["聲調"] != "")
            df_valid = df[has_any].copy()

            # 2. 检测缺失数据（有部分音韵特征但不完整）
            has_all = (df_valid["聲母"] != "") & (df_valid["韻母"] != "") & (df_valid["聲調"] != "")
            df_missing = df_valid[~has_all]

            # 3. 批量记录缺失数据日志（避免频繁文件I/O）
            if len(df_missing) > 0:
                for row in df_missing.itertuples(index=False):
                    missing_data_logs.append(
                        f"❗ 缺資料：char={row.漢字}, 音節={row.音節}, 聲母='{row.聲母}', 韻母='{row.韻母}', 聲調='{row.聲調}'"
                    )

            # 4. 🚀 使用 itertuples() 替代 iterrows()（快10-100倍）
            batch_data = [
                (tsv_name, row.漢字, row.音節, row.聲母, row.韻母, row.聲調, row.註釋, row.多音字)
                for row in df_valid.itertuples(index=False)
            ]
            insert_count = len(batch_data)

            # 批量插入所有数据
            if batch_data:
                cursor.executemany('''
                    INSERT INTO dialects (簡稱, 漢字, 音節, 聲母, 韻母, 聲調, 註釋, 多音字)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', batch_data)

            conn.commit()
            log_lines.append(f"{tsv_name} 寫入了 {insert_count} 筆。")
            # print(f" {tsv_name} 完成：共寫入 {insert_count} 筆。")

            # Track processed 簡稱
            if tsv_name not in processed_簡稱:
                processed_簡稱.append(tsv_name)

        except Exception as e:
            error_detail = traceback.format_exc()
            log_lines.append(f" {tsv_name} 寫入失敗：\n{error_detail}")
            print(f" 錯誤處理 {tsv_name}：\n{error_detail}")

    conn.close()
    print(f"\n📦 所有資料已寫入：{db_path}")

    # 🚀 优化：批量写入所有日志（一次性I/O）
    if missing_data_logs:
        with open(MISSING_DATA_LOG, "a", encoding="utf-8") as f:
            f.write("\n".join(missing_data_logs) + "\n")

    #  优化：重新连接并恢复正常模式，然后创建索引
    conn_all = sqlite3.connect(db_path)
    cursor = conn_all.cursor()

    # 恢复正常同步模式
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA journal_mode = DELETE")

    # 創建索引，加快查詢速度
    # update 模式下跳過創建索引（索引已存在，不需要重新創建）
    if not update:
        print("※ 開始創建索引 ※")
        # 基础单列索引（FastAPI 后端频繁查询的字段）
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_abbr ON dialects(簡稱);")
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_char ON dialects(漢字);")
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_syllable ON dialects(音節);")
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_polyphonic ON dialects(多音字);")  # 新增：多音字查询

        # 复合索引，优化多字段查询和 GROUP BY
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_char_abbr ON dialects(漢字, 簡稱);")  # FastAPI 最重要
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_abbr_char ON dialects(簡稱, 漢字);")
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_abbr_char_syllable ON dialects(簡稱, 漢字, 音節);")

        # 【优先级高】用于音韵特征查询（分别优化聲母/韻母/聲調查询）
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_abbr_initial ON dialects(簡稱, 聲母);")
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_abbr_final ON dialects(簡稱, 韻母);")
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_abbr_tone ON dialects(簡稱, 聲調);")

        # 【优先级高】优化多音字查询（WHERE 多音字='1' AND 簡稱=? AND 漢字 IN ...）
        conn_all.execute("CREATE INDEX IF NOT EXISTS idx_dialects_polyphonic_full ON dialects(多音字, 簡稱, 漢字);")
        print("✅ 索引創建完成")
    else:
        print("⏭️  update 模式：跳過創建索引（索引已存在）")

    conn_all.commit()
    conn_all.close()  # 🔧 修复：关闭数据库连接，避免锁定

    # print("\n 寫入總結：")
    # for line in log_lines:
    # print("   " + line)

    with open(WRITE_INFO_LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))
    # print(f"\n📝 已寫入紀錄至：{log_path}")

    return processed_簡稱  # Return list of processed dialects


# 🚀 优化版本：分批處理，避免內存溢出
def process_polyphonic_annotations(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    #  优化：设置 SQLite 性能参数
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = MEMORY")

    # 先獲取所有唯一的簡稱
    cursor.execute("SELECT DISTINCT 簡稱 FROM dialects")
    locations = [row[0] for row in cursor.fetchall()]
    total_locations = len(locations)

    print(f"📍 共有 {total_locations} 個地點待處理\n")

    # 創建臨時表存儲處理後的結果
    cursor.execute("DROP TABLE IF EXISTS dialects_temp")
    cursor.execute('''
        CREATE TABLE dialects_temp (
            簡稱 TEXT,
            漢字 TEXT,
            音節 TEXT,
            聲母 TEXT,
            韻母 TEXT,
            聲調 TEXT,
            註釋 TEXT,
            多音字 TEXT
        )
    ''')

    # 分批處理地點（每次處理 20 個）
    batch_size = 50
    total_batches = (total_locations + batch_size - 1) // batch_size

    for batch_idx in range(0, total_locations, batch_size):
        batch_locations = locations[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1

        print(f"\n[批次 {batch_num}/{total_batches}] 正在處理 {len(batch_locations)} 個地點...")
        print(f"  地點：{', '.join(batch_locations[:5])}{'...' if len(batch_locations) > 5 else ''}")

        # 讀取當前批次所有地點的數據
        placeholders = ','.join(['?' for _ in batch_locations])
        df = pd.read_sql_query(
            f"SELECT * FROM dialects WHERE 簡稱 IN ({placeholders}) ORDER BY 簡稱, 漢字",
            conn,
            params=batch_locations
        )

        if len(df) == 0:
            continue

        print(f"  讀取了 {len(df)} 筆數據")

        # 🚀 創建音韻特徵組合鍵
        df['_phonetic_key'] = (df['聲母'].astype(str) + '|' +
                               df['韻母'].astype(str) + '|' +
                               df['聲調'].astype(str))

        # 🚀 為每個 (簡稱, 漢字, 音節, 多音字) 組分配唯一ID，避免文白讀提前合併
        df['_group_id'] = df.groupby(['簡稱', '漢字', '音節', '多音字']).ngroup()

        # 🚀 計算每組的唯一音韻特徵數
        phonetic_counts = df.groupby('_group_id')['_phonetic_key'].nunique()
        df['_phonetic_count'] = df['_group_id'].map(phonetic_counts)

        # 🚀 分離兩種情況：音韻一致 vs 音韻不一致
        consistent_mask = df['_phonetic_count'] == 1
        inconsistent_mask = ~consistent_mask

        # === 處理音韻一致的組（需要合併註釋） ===
        consistent_df = df[consistent_mask].copy()

        # 🚀 向量化合併註釋
        def agg_notes(series):
            """聚合註釋：去空、去重、用分號連接"""
            notes = series.dropna().astype(str).str.strip()
            notes = notes[notes != '']
            if len(notes) == 0:
                return ''
            return ';'.join(notes.unique())

        # 🚀 使用 groupby.agg() 一次性處理所有組
        if len(consistent_df) > 0:
            consistent_merged = consistent_df.groupby('_group_id', as_index=False).agg({
                '簡稱': 'first',
                '漢字': 'first',
                '音節': 'first',
                '聲母': 'first',
                '韻母': 'first',
                '聲調': 'first',
                '註釋': agg_notes,
                '多音字': 'first'
            })
        else:
            consistent_merged = pd.DataFrame(columns=['簡稱', '漢字', '音節', '聲母', '韻母', '聲調', '註釋', '多音字'])

        # === 處理音韻不一致的組（保留所有行） ===
        inconsistent_df = df[inconsistent_mask][
            ['簡稱', '漢字', '音節', '聲母', '韻母', '聲調', '註釋', '多音字']].copy()

        # 🚀 合併兩部分
        merged_df = pd.concat([consistent_merged, inconsistent_df], ignore_index=True)

        # 標記多音字（音節不同）- 保留文白讀 2/3，只給其他多音讀補 1
        merged_df = apply_polyphonic_labels(merged_df, ['簡稱', '漢字'])

        # 只保留需要的列，去除臨時列
        final_columns = ['簡稱', '漢字', '音節', '聲母', '韻母', '聲調', '註釋', '多音字']
        merged_df = merged_df[final_columns]

        # 寫入臨時表
        merged_df.to_sql("dialects_temp", conn, if_exists='append', index=False)

        print(f"  處理後剩餘 {len(merged_df)} 筆（原始 {len(df)} 筆）")

        # 釋放內存
        del df, merged_df

    print("\n⏳ 正在重建數據庫表...")
    cursor.execute("DROP TABLE IF EXISTS dialects")
    cursor.execute("ALTER TABLE dialects_temp RENAME TO dialects")

    # 恢复正常模式
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA journal_mode = DELETE")

    conn.commit()
    conn.close()
    print("✅ 多音字處理完成")


# 新代碼，實時更改數據庫，加快運行速度(实际上还变慢了。。）
def process_polyphonic_annotations_new(db_path: str, append: bool = False):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM dialects ORDER BY 簡稱, 漢字", conn)
    # 如果 append 模式開啟，只保留指定簡稱
    if append:
        try:
            df_append = pd.read_excel(APPEND_PATH, sheet_name="檔案")
            update_rows = df_append[df_append['待更新'] == 1]
            valid_簡稱 = update_rows['簡稱'].dropna().unique().tolist()

            if valid_簡稱:
                df = df[df["簡稱"].isin(valid_簡稱)]
                print(f"📌 只處理待更新簡稱：{valid_簡稱}")
            else:
                print("⚠️ APPEND_PATH 中未發現任何待更新簡稱，跳過處理。")
                conn.close()
                return
        except Exception as e:
            print(f"❗ 無法讀取 APPEND_PATH：{e}，將處理全部資料。")

    print(f" 待處理資料筆數：{len(df)}")

    grouped = df.groupby(["簡稱", "漢字"])

    previous_short_name = None  # 用来保存上一次的地点信息
    count_num = 1
    for (short_name, char), group in grouped:
        if short_name != previous_short_name:  # 当地点变化时触发
            print(f"正在處理：{short_name}(第{count_num}個)")  # 输出调试信息，地点发生变化
            count_num += 1

        # 一階段：處理註釋
        grouped_syllables = group.groupby("音節")
        for syllable, syllable_group in grouped_syllables:
            unique_phonetics = syllable_group[["聲母", "韻母", "聲調"]].drop_duplicates()
            if len(unique_phonetics) == 1:
                notes = syllable_group["註釋"].dropna().astype(str).str.strip().unique()
                notes = [n for n in notes if n]
                combined_note = ";".join(notes) if notes else ""

                base_row = syllable_group.iloc[0].copy()
                base_row["註釋"] = combined_note

                # 更新資料庫中的註釋
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE dialects
                    SET 註釋 = ?
                    WHERE 簡稱 = ? AND 漢字 = ? AND 音節 = ?
                """, (combined_note, short_name, char, syllable))

                # 刪除除第一行外的其他重複行
                cursor.execute("""
                    DELETE FROM dialects
                    WHERE (簡稱 = ? AND 漢字 = ? AND 音節 = ?)
                      AND rowid NOT IN (
                        SELECT MIN(rowid)
                        FROM dialects
                        WHERE 簡稱 = ? AND 漢字 = ? AND 音節 = ?
                      )
                """, (short_name, char, syllable, short_name, char, syllable))

            else:
                print(f"⚠️ 音節相同但聲韻調不同：{char} / {syllable}")
                for _, row in syllable_group.iterrows():
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE dialects
                        SET 註釋 = ?
                        WHERE 簡稱 = ? AND 漢字 = ? AND 音節 = ?
                    """, (row["註釋"], short_name, char, syllable))

        # 二階段：標記多音字（音節不同）
        syllables_count = len(group["音節"].unique())
        if syllables_count > 1:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE dialects
                SET 多音字 = '1'
                WHERE 簡稱 = ? AND 漢字 = ?
            """, (short_name, char))

        previous_short_name = short_name  # 更新之前的地点

    conn.commit()
    print("🔨 資料庫更新完成！")

    conn.close()


def sync_dialects_flags(all_db_path=DIALECTS_DB_PATH,
                        query_db_path=QUERY_DB_PATH,
                        log_path=CHARACTERS_DB_PATH):
    # 讀取 dialects_all.db 中所有唯一簡稱
    conn_all = sqlite3.connect(all_db_path)
    #  优化：索引已在 process_all2sql 中创建，此处无需重复
    cursor_all = conn_all.cursor()
    cursor_all.execute("SELECT DISTINCT 簡稱 FROM dialects")
    all_tags = set(row[0] for row in cursor_all.fetchall())
    conn_all.close()

    # 讀取 dialects_query.db 中所有簡稱
    conn_query = sqlite3.connect(query_db_path)
    cursor_query = conn_query.cursor()

    # 確保存儲標記欄位存在
    cursor_query.execute("PRAGMA table_info(dialects)")
    columns = [col[1] for col in cursor_query.fetchall()]
    if "存儲標記" not in columns:
        cursor_query.execute("ALTER TABLE dialects ADD COLUMN 存儲標記 INTEGER DEFAULT 0")

    cursor_query.execute("SELECT rowid, 簡稱 FROM dialects")
    query_map = {tag: rowid for rowid, tag in cursor_query.fetchall()}

    matched = []
    unmatched = []

    for tag in sorted(all_tags):
        if tag in query_map:
            rowid = query_map[tag]
            cursor_query.execute("UPDATE dialects SET 存儲標記 = 1 WHERE rowid = ?", (rowid,))
            matched.append(tag)
        else:
            unmatched.append(tag)
            print(f"❗ 無法匹配簡稱：{tag}")

    conn_query.commit()
    conn_query.close()

    # 寫入 log 檔案（前面兩個空行）
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("\n\n")
        for tag in unmatched:
            f.write(f"無法匹配簡稱：{tag}\n")

        # 寫入成功存儲訊息，每 10 個換行
        lines = []
        for i in range(0, len(matched), 10):
            lines.append(", ".join(matched[i:i + 10]))
        success_message = "成功存儲：\n" + "\n".join(lines)
        f.write(success_message + "\n")

    print(" 同步完成。已更新存儲標記。")


def read_character_source_table(file_path, file_type="excel", sheet_name=0):
    """
    讀取寫入 characters.db 的來源表。
    保留空字符串，不把字面值 nan 誤當作缺失值。
    """
    if file_type == "excel":
        return pd.read_excel(file_path, sheet_name=sheet_name, dtype=str, keep_default_na=False, na_filter=False)
    if file_type == "tsv":
        return pd.read_csv(file_path, sep="\t", dtype=str, keep_default_na=False, na_filter=False)
    raise ValueError(f"不支持的文件類型: {file_type}")


def merge_text_into_meaning(df, meaning_column="釋義", note_column=None, note_label="注釋"):
    """
    把注釋/校註合併進釋義欄，避免遺失信息。
    """
    if not note_column or note_column not in df.columns or meaning_column not in df.columns:
        return df

    result = df.copy()
    meaning_series = result[meaning_column].fillna("").astype(str).str.strip()
    note_series = result[note_column].fillna("").astype(str).str.strip()
    merged_values = []

    for meaning, note in zip(meaning_series, note_series):
        if meaning and note:
            if meaning == note:
                merged_values.append(meaning)
            else:
                merged_values.append(f"{meaning}\n{note_label}：{note}")
        elif meaning:
            merged_values.append(meaning)
        elif note:
            merged_values.append(f"{note_label}：{note}")
        else:
            merged_values.append("")

    result[meaning_column] = merged_values
    return result.drop(columns=[note_column])


def append_simplified_character_rows(df, char_column, unique_columns=None):
    """
    在不改動表結構的前提下，為單字補充 t2s 後的簡體別名行。
    """
    if not char_column or char_column not in df.columns:
        return df, 0

    result = df.copy()
    result[char_column] = result[char_column].fillna("").astype(str).str.strip()
    key_columns = list(unique_columns or result.columns)
    existing_keys = {
        tuple(row)
        for row in result[key_columns].itertuples(index=False, name=None)
    }
    new_rows = []

    for row in result.to_dict("records"):
        char = str(row.get(char_column, "")).strip()
        if len(char) != 1:
            continue

        simplified = traditional2simplified(char).strip()
        if len(simplified) != 1 or simplified == char:
            continue

        new_row = row.copy()
        new_row[char_column] = simplified
        row_key = tuple(new_row[col] for col in key_columns)
        if row_key in existing_keys:
            continue

        existing_keys.add(row_key)
        new_rows.append(new_row)

    if not new_rows:
        return result, 0

    new_df = pd.DataFrame(new_rows, columns=result.columns)
    return pd.concat([result, new_df], ignore_index=True), len(new_rows)


def write_character_source_table(conn, table_name, df, single_index_columns=None, pair_index_columns=None, char_column=None, hierarchy_index=None):
    """
    將整理好的 DataFrame 寫入 characters.db 的指定表。
    """
    # 添加多地位标记列（如果有 char_column）
    if char_column and char_column in df.columns:
        df, added_rows = append_simplified_character_rows(df, char_column)
        if added_rows:
            print(f"   [繁簡補行] 追加 {added_rows} 行")
        dup_counts = df[char_column].value_counts()
        df = df.copy()
        df["多地位標記"] = df[char_column].map(lambda x: "1" if dup_counts.get(x, 0) > 1 else "")
        print(f"   [多地位] 检测到 {(df['多地位標記'] == '1').sum()} 个多地位字符")

    df.to_sql(table_name, conn, if_exists="replace", index=False)
    print(f"已寫入表 {table_name}: {len(df)} 行")

    for position, col in enumerate(single_index_columns or []):
        if col in df.columns:
            index_name = f"idx_{table_name}_single_{position}"
            conn.execute(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}"("{col}");')
            print(f"   [索引] {table_name}({col})")

    if char_column and char_column in df.columns:
        for position, col in enumerate(pair_index_columns or []):
            if col in df.columns:
                index_name = f"idx_{table_name}_pair_{position}"
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}"("{col}", "{char_column}");'
                )
                print(f"   [索引] {table_name}({col}, {char_column})")

    # 创建层级复合索引（根据后端邮件要求）
    if hierarchy_index:
        valid_columns = [col for col in hierarchy_index if col in df.columns]
        if valid_columns:
            index_name = f"idx_{table_name}_hierarchy"
            columns_sql = ", ".join(f'"{col}"' for col in valid_columns)
            conn.execute(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}"({columns_sql});')
            print(f"   [层级索引] {table_name}({', '.join(valid_columns)})")

    # 创建多地位标记复合索引（如果有多地位标记列）
    if char_column and "多地位標記" in df.columns:
        index_name = f"idx_{table_name}_multi_position"
        conn.execute(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}"("多地位標記", "{char_column}");')
        print(f"   [多地位索引] {table_name}(多地位標記, {char_column})")


def scan_update_directory():
    """
    Scan UPDATE_DATA_DIR for all TSV files
    Returns list of TSV file paths
    """
    if not os.path.exists(UPDATE_DATA_DIR):
        print(f"⚠️ UPDATE_DATA_DIR 不存在: {UPDATE_DATA_DIR}")
        return []

    tsv_files = []
    for file in os.listdir(UPDATE_DATA_DIR):
        if file.endswith('.tsv'):
            full_path = os.path.join(UPDATE_DATA_DIR, file)
            tsv_files.append(full_path)

    print(f"📂 從 UPDATE_DATA_DIR 找到 {len(tsv_files)} 個 TSV 文件")
    return tsv_files


def process_polyphonic_annotations_selective(db_path: str, 簡稱_list: list):
    """
    Process polyphonic annotations for specific dialects only
    More efficient than processing entire table

    Args:
        db_path: Path to dialects database
        簡稱_list: List of 簡稱 to process
    """
    if not 簡稱_list:
        print("⚠️ 沒有指定要處理的簡稱，跳過多音字處理")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Performance optimization
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = MEMORY")

    print(f"📝 處理多音字標記（僅處理 {len(簡稱_list)} 個方言點）...")

    # Process each 簡稱 separately to avoid loading entire table
    for idx, 簡稱 in enumerate(簡稱_list, 1):
        print(f"[{idx}/{len(簡稱_list)}] 正在處理：{簡稱}")

        # Read only this dialect's data
        query = "SELECT * FROM dialects WHERE 簡稱 = ? ORDER BY 漢字"
        df = pd.read_sql_query(query, conn, params=(簡稱,))

        if df.empty:
            continue

        # Create phonetic key
        df['_phonetic_key'] = (df['聲母'].astype(str) + '|' +
                               df['韻母'].astype(str) + '|' +
                               df['聲調'].astype(str))

        # Group by (漢字, 音節, 多音字)，避免文白讀提前合併
        df['_group_id'] = df.groupby(['漢字', '音節', '多音字']).ngroup()

        # Count unique phonetic features per group
        phonetic_counts = df.groupby('_group_id')['_phonetic_key'].nunique()
        df['_phonetic_count'] = df['_group_id'].map(phonetic_counts)

        # Process consistent groups (merge notes)
        consistent_mask = df['_phonetic_count'] == 1

        if consistent_mask.any():
            consistent_df = df[consistent_mask].copy()

            def agg_notes(series):
                notes = series.dropna().astype(str).str.strip()
                notes = notes[notes != '']
                if len(notes) == 0:
                    return ''
                return ';'.join(notes.unique())

            consistent_merged = consistent_df.groupby('_group_id', as_index=False).agg({
                '簡稱': 'first',
                '漢字': 'first',
                '音節': 'first',
                '聲母': 'first',
                '韻母': 'first',
                '聲調': 'first',
                '註釋': agg_notes,
                '多音字': 'first'
            })

            # Delete old records for this 簡稱
            cursor.execute("DELETE FROM dialects WHERE 簡稱 = ?", (簡稱,))

            # Insert merged records
            inconsistent_df = df[~consistent_mask][
                ['簡稱', '漢字', '音節', '聲母', '韻母', '聲調', '註釋', '多音字']].copy()
            merged_df = pd.concat([consistent_merged, inconsistent_df], ignore_index=True)
        else:
            # No merging needed, just use original data
            cursor.execute("DELETE FROM dialects WHERE 簡稱 = ?", (簡稱,))
            merged_df = df[['簡稱', '漢字', '音節', '聲母', '韻母', '聲調', '註釋', '多音字']].copy()

        # Mark polyphonic characters while preserving wen/bai labels
        merged_df = apply_polyphonic_labels(merged_df, ['漢字'])

        # 只保留需要的列，去除臨時列
        final_columns = ['簡稱', '漢字', '音節', '聲母', '韻母', '聲調', '註釋', '多音字']
        merged_df = merged_df[final_columns]

        # Re-insert processed data
        merged_df.to_sql('dialects', conn, if_exists='append', index=False)

    conn.commit()

    # Restore normal mode
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA journal_mode = DELETE")

    conn.close()
    print("✅ 多音字處理完成")


def write_to_sql(yindian=None, write_chars_db=None, append=False, update=False, mode='admin'):
    """
    Args:
        mode: 'admin' 或 'user'
        append: 從 Excel 配置文件讀取待更新列表
        update: 從 UPDATE_DATA_DIR 目錄讀取所有 TSV 文件進行增量更新
    """

    # 記錄開始時間
    start_time = time.time()
    step_times = {}

    # 1. 確定數據庫路徑
    if mode == 'admin':
        query_db_path = QUERY_DB_ADMIN_PATH
        dialects_db_path = DIALECTS_DB_ADMIN_PATH
    else:  # user
        query_db_path = QUERY_DB_USER_PATH
        dialects_db_path = DIALECTS_DB_USER_PATH

    # 2. 構建 query 數據庫，同時獲取 TSV 路徑列表
    print(f"\n{'=' * 60}")
    print(f"步驟1：構建方言查詢數據庫（{mode} 模式）...")
    print(f"{'=' * 60}")
    step1_start = time.time()
    tsv_paths = build_dialect_database(mode=mode)
    step_times['步驟1：構建方言查詢數據庫'] = time.time() - step1_start

    # 3. Override TSV paths if in update mode
    if update:
        print(f"\n{'=' * 60}")
        print(f"update 模式：使用 UPDATE_DATA_DIR 中的文件")
        print(f"{'=' * 60}")
        tsv_paths = scan_update_directory()

    # 4. 過濾排除文件 (非 update 模式 且 非 admin 模式才過濾)
    if not update and mode != 'admin':
        tsv_paths = [
            p for p in tsv_paths
            if os.path.splitext(os.path.basename(p))[0] not in exclude_files
        ]

    print(f"   共 {len(tsv_paths)} 個 TSV 文件待處理")

    # 5. 寫入總數據表
    print(f"\n{'=' * 60}")
    print(f"步驟2：寫入方言數據...")
    print(f"{'=' * 60}")
    step2_start = time.time()
    db_path = os.path.join(os.getcwd(), dialects_db_path)
    processed_簡稱 = process_all2sql(tsv_paths, db_path, append, update, query_db_path=query_db_path)
    step_times['步驟2：寫入方言數據'] = time.time() - step2_start

    # 5. 處理重複行和多音字
    print(f"\n{'=' * 60}")
    print(f"步驟3：處理重複行和多音字...")
    print(f"{'=' * 60}")
    step3_start = time.time()

    if update and processed_簡稱:
        # Use selective processing for update mode (more efficient)
        process_polyphonic_annotations_selective(dialects_db_path, processed_簡稱)
    else:
        # Use full processing for normal/append mode
        process_polyphonic_annotations(dialects_db_path)

    step_times['步驟3：處理重複行和多音字'] = time.time() - step3_start

    # 6. 同步存儲標記
    print(f"\n{'=' * 60}")
    print(f"步驟4：同步存儲標記...")
    print(f"{'=' * 60}")
    step4_start = time.time()
    sync_dialects_flags(
        all_db_path=dialects_db_path,
        query_db_path=query_db_path
    )
    step_times['步驟4：同步存儲標記'] = time.time() - step4_start

    # 7. 寫入漢字地位表（可選）
    if write_chars_db:
        print(f"\n{'=' * 60}")
        print(f"步驟5：寫入漢字地位表...")
        print(f"{'=' * 60}")
        step5_start = time.time()
        process_phonology_excel()
        step_times['步驟5：寫入漢字地位表'] = time.time() - step5_start

    # 計算總時間
    total_time = time.time() - start_time

    # 輸出時間統計
    print(f"\n{'=' * 60}")
    print(f"⏱️  執行時間統計")
    print(f"{'=' * 60}")
    for step_name, duration in step_times.items():
        minutes = int(duration // 60)
        seconds = duration % 60
        if minutes > 0:
            print(f"  {step_name}: {minutes}分{seconds:.2f}秒")
        else:
            print(f"  {step_name}: {seconds:.2f}秒")

    print(f"{'-' * 60}")
    total_minutes = int(total_time // 60)
    total_seconds = total_time % 60
    if total_minutes > 0:
        print(f"  ✅ 總執行時間: {total_minutes}分{total_seconds:.2f}秒")
    else:
        print(f"  ✅ 總執行時間: {total_seconds:.2f}秒")
    print(f"{'=' * 60}\n")


def _spec_value(spec, key, default=None):
    if spec is None:
        return default
    if isinstance(spec, dict):
        return spec.get(key, default)
    return getattr(spec, key, default)


def prepare_character_source_dataframe(
        df,
        columns=None,
        drop_unnamed=False,
        row_filter=None,
        transform_func=None,
        rename_columns=None,
        merge_text_spec=None,
        final_columns=None,
):
    """
    整理來源表結構，只保留指定欄位。
    """
    result = df.copy()
    if drop_unnamed:
        result = result.loc[:, ~result.columns.astype(str).str.startswith("Unnamed:")]

    if columns is not None:
        missing = [col for col in columns if col not in result.columns]
        if missing:
            raise KeyError(f"缺少必要欄位: {missing}")
        result = result[list(columns)].copy()

    if row_filter is not None:
        result = row_filter(result).copy()

    if transform_func is not None:
        result = transform_func(result).copy()

    if merge_text_spec is not None:
        result = merge_text_into_meaning(
            result,
            meaning_column=_spec_value(merge_text_spec, "meaning_column", "釋義"),
            note_column=_spec_value(merge_text_spec, "note_column"),
            note_label=_spec_value(merge_text_spec, "note_label", "注釋"),
        )

    if rename_columns:
        result = result.rename(columns=dict(rename_columns))

    if final_columns is not None:
        missing = [col for col in final_columns if col not in result.columns]
        if missing:
            raise KeyError(f"缺少整理後欄位: {missing}")
        result = result[list(final_columns)].copy()

    return result.fillna("")


def process_phonology_excel(
        excel_file=PHONOLOGY_TABLE_SPEC.file_path,
        sheet_name=PHONOLOGY_TABLE_SPEC.sheet_name,
        db_file=CHARACTERS_DB_PATH,
        log_file=WRITE_INFO_LOG
):
    os.makedirs("data", exist_ok=True)

    spec = PHONOLOGY_TABLE_SPEC
    source_columns = list(spec.source_columns)
    rename_columns = dict(spec.rename_columns)
    write_columns = list(spec.final_columns)
    char_column = spec.char_column
    duplicate_flag_column = spec.duplicate_flag_column

    try:
        df = pd.read_excel(excel_file, sheet_name=sheet_name, dtype=str, keep_default_na=False, na_filter=False)
    except Exception as e:
        print(f" 讀取 Excel 失敗: {e}")
        return

    try:
        df = df[source_columns].rename(columns=rename_columns)
    except KeyError as e:
        print(f" 缺少必要欄位: {e}")
        return

    df = df[df[char_column].notna() & (df[char_column].str.strip() != "")]
    df["num"] = df.index + 2

    exempt_columns = set(spec.missing_check_exempt_columns) | {"num"}
    check_cols = [col for col in df.columns if col not in exempt_columns]
    invalid_rows = df[df[check_cols].isnull().any(axis=1)]
    df_valid = df.drop(index=invalid_rows.index)
    df_unique = df_valid.drop_duplicates(subset=write_columns).copy()
    df_unique, added_rows = append_simplified_character_rows(
        df_unique,
        char_column,
        unique_columns=write_columns,
    )
    if added_rows:
        print(f"   [繁簡補行] 追加 {added_rows} 行")

    dup_counts = df_unique[char_column].value_counts()
    df_unique[duplicate_flag_column] = df_unique[char_column].map(
        lambda value: "1" if dup_counts.get(value, 0) > 1 else ""
    )

    if not invalid_rows.empty:
        invalid_output = invalid_rows[["num", char_column] + check_cols]
        print("發現欄位缺漏如下：")
        print(invalid_output)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(invalid_output.to_csv(index=False, sep="\t", lineterminator="\n"))

    try:
        conn = sqlite3.connect(db_file)
        df_unique.drop(columns=["num"]).to_sql(spec.table_name, conn, if_exists="replace", index=False)
        print("開始建立索引...")

        for position, (col1, col2) in enumerate(spec.triple_indexes):
            index_name = f"idx_{spec.table_name}_triple_{position}"
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                f'ON "{spec.table_name}"("{col1}", "{col2}", "{char_column}");'
            )
            print(f"   [三列索引] ({col1}, {col2}, {char_column})")

        for position, columns in enumerate(spec.multi_column_indexes):
            index_name = f"idx_{spec.table_name}_multi_{position}"
            joined_columns = ", ".join(f'"{col}"' for col in columns)
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{spec.table_name}"({joined_columns});'
            )
            print(f"   [多列索引] ({', '.join(columns)})")

        for col in spec.composite_index_columns:
            index_name = f"idx_{spec.table_name}_{col}_hanzi"
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "{index_name}" '
                f'ON "{spec.table_name}"("{col}", "{char_column}");'
            )
            print(f"   [聯合索引] ({col}, {char_column})")

        for col in spec.single_index_columns:
            if col == char_column:
                index_name = f"idx_{spec.table_name}_{char_column}"
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{spec.table_name}"("{char_column}");'
                )
            else:
                index_name = f"idx_{spec.table_name}_{col}"
                conn.execute(
                    f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{spec.table_name}"("{col}");'
                )
            print(f"   [單列索引] {col}")

        write_additional_character_tables(conn)
        conn.commit()
        conn.close()
        print(" 索引優化完成！")
    except Exception as e:
        print(f" SQLite 寫入失敗: {e}")


def write_additional_character_tables(conn):
    """
    將其他歷史音資料寫入同一個 characters.db。
    """
    for table_name in LEGACY_CHARACTER_TABLE_NAMES:
        conn.execute(f'DROP TABLE IF EXISTS "{table_name}";')

    for spec in ADDITIONAL_CHARACTER_TABLE_SPECS:
        try:
            df = read_character_source_table(
                spec.file_path,
                file_type=spec.file_type,
                sheet_name=spec.sheet_name,
            )
            df = prepare_character_source_dataframe(
                df,
                columns=spec.columns,
                drop_unnamed=spec.drop_unnamed,
                row_filter=spec.row_filter,
                transform_func=spec.transform_func,
                rename_columns=spec.rename_columns,
                merge_text_spec=spec.merge_text_spec,
                final_columns=spec.final_columns,
            )
            write_character_source_table(
                conn,
                spec.table_name,
                df,
                single_index_columns=spec.single_index_columns,
                pair_index_columns=spec.pair_index_columns,
                char_column=spec.char_column,
                hierarchy_index=spec.hierarchy_index,
            )
        except Exception as e:
            raise RuntimeError(f"寫入附加表 {spec.table_name} 失敗: {e}") from e


if __name__ == "__main__":
    write_to_sql()
    # build_dialect_database()
