import os
import re
import sqlite3
import traceback
from pathlib import Path

import pandas as pd

from common.constants import exclude_files
from source.change_coordinates import bd09togcj02
from common.config import HAN_PATH, APPEND_PATH, QUERY_DB_PATH, DIALECTS_DB_PATH, CHARACTERS_DB_PATH, PHO_TABLE_PATH, \
    MISSING_DATA_LOG, WRITE_INFO_LOG, YINDIAN_DATA_DIR
from source.get_new import extract_all_from_files
from source.match_fromdb import get_tsvs


def build_dialect_database():
    # han_file = Path(HAN_CSV_PATH)
    han_file = Path(HAN_PATH)
    other_file = Path(APPEND_PATH)
    sqlite_db = Path(QUERY_DB_PATH)

    # --- 欄位對應 ---
    tone_map = {
        "[1]陰平": "T1陰平",
        "[2]陽平": "T2陽平",
        "[3]陰上": "T3陰上",
        "[4]陽上": "T4陽上",
        "[5]陰去": "T5陰去",
        "[6]陽去": "T6陽去",
        "[7]陰入": "T7陰入",
        "[8]陽入": "T8陽入",
        "[9]其他調": "T9其他調",
        "[10]輕聲": "T10輕聲"
    }

    geo_map = {
        "省/自治區/直轄市": "省",
        "地區/市/州": "市",
        "縣/市/區": "縣",
        "鄕/鎭/街道": "鎮",
        "村/社區/居民點": "行政村",
        "自然村": "自然村"
    }

    rename_map = {**tone_map, **geo_map}

    # 欄位清單（原始名稱）
    required_columns = [
        "語言", "簡稱", "音典排序", "地圖集二分區", "音典分區", "字表來源（母本）", "方言島",
        "存儲標記", "經緯度", "地圖級別",
        *geo_map.keys(),
        *tone_map.keys()
    ]

    # --- 讀取 Append_files.xlsx.xlsx ---
    df_other = pd.read_excel(other_file, sheet_name="檔案", header=0)
    df_other.columns = df_other.columns.str.strip()
    df_other["存儲標記"] = ""  # ✅ 補上這一列
    df_other = df_other[[col for col in required_columns if col in df_other.columns]].copy()
    df_other = df_other.rename(columns=rename_map)

    # --- 讀取 漢字音典表，跳過第 2 行（即 index 0）---
    df_han = pd.read_excel(han_file, sheet_name="檔案", header=0, engine='openpyxl', keep_default_na=False)
    # df_han = pd.read_csv(han_file)
    df_han = df_han.drop(index=0).reset_index(drop=True)
    df_han.columns = df_han.columns.str.strip()
    df_han["存儲標記"] = ""  # ✅ 補上這一列
    df_han = df_han[[col for col in required_columns if col in df_han.columns]].copy()
    df_han = df_han.rename(columns=rename_map)

    # --- 處理經緯度轉換 ---
    def convert_coordinates(df):
        """
        對 '經緯度' 列進行坐標轉換，忽略空值
        """
        new_coordinates = []
        for coords in df['經緯度']:
            # 如果經緯度為空，跳過
            if pd.isna(coords) or coords.strip() == '':
                new_coordinates.append(None)  # 如果是空值，將經緯度設為 None
                continue

            # 確保 coords 是字符串類型
            coords = str(coords).strip()

            # 分割經緯度
            bd_lon, bd_lat = map(float, re.split(r'[，,]', coords))

            # 使用轉換函數
            converted_coords = bd09togcj02(bd_lon, bd_lat)
            new_coordinates.append(f"{converted_coords[0]},{converted_coords[1]}")  # 轉換後的坐標以逗號分隔

        # 更新 '經緯度' 列
        df['經緯度'] = new_coordinates
        return df

    # 處理 df_other 和 df_han 兩個 DataFrame
    df_other = convert_coordinates(df_other)
    df_han = convert_coordinates(df_han)

    # --- 寫入 SQLite ---
    with sqlite3.connect(sqlite_db) as conn:
        # 記錄來源
        df_other["_來源"] = "Append_files.xlsx"
        df_han["_來源"] = "漢字音典表"

        # 合併資料
        merged = pd.concat([df_other, df_han], ignore_index=True)

        # ✅ 在此處插入替換邏輯
        def replace_dialect_zone(val):
            if isinstance(val, str):
                if val.startswith("客家話-粵北片"):
                    return val.replace("客家話-粵北片", "客家話-粵北片·客", 1)
                elif val.startswith("平話和土話-粵北片"):
                    return val.replace("平話和土話-粵北片", "平話和土話-粵北片·土", 1)
            return val

        merged["地圖集二分區"] = merged["地圖集二分區"].apply(replace_dialect_zone)

        # 後續處理 ...

        # 轉換 required_columns → 重命名後的欄位名
        renamed_required_columns = [rename_map.get(col, col) for col in required_columns]

        # 計算非空欄位數
        merged["_non_null_count"] = merged[renamed_required_columns].notna().sum(axis=1)

        # 優先來源標記（漢字音典表優先）
        merged["_來源優先"] = merged["_來源"].apply(lambda x: 1 if x == "漢字音典表" else 0)

        # 最終保留資料列表
        final_rows = []

        def get_nonnull_info(row):
            if row.empty:
                return 0, []
            # count = int(row["_non_null_count"])
            cols = [col for col in renamed_required_columns if pd.notna(row[col]) and row[col] != ""]
            count = len(cols)
            return count, cols
        print("\n📊 重複簡稱選擇詳情如下：")
        for name, group in merged.groupby("簡稱"):
            if len(group) > 1:
                # 计算每行的非空列数并添加为新列
                group["count"] = group.apply(
                    lambda row: len([col for col in renamed_required_columns if pd.notna(row[col]) and row[col] != ""]),
                    axis=1)

                # 选择 count 最大的行，如果 count 相同则优先选择 "漢字音典表"
                selected = None
                for _, row in group.iterrows():
                    count, cols = get_nonnull_info(row)
                    if selected is None or count > selected["count"] or (
                            count == selected["count"] and row["_來源"] == "漢字音典表"):
                        selected = row
                        selected["count"] = count  # 更新 selected 的 count

                final_rows.append(selected)

                print(f"\n🟡 簡稱: {name}")
                for _, row in group.iterrows():
                    count, cols = get_nonnull_info(row)
                    print(f"  ➤ 來源：{row['_來源']}，非空欄位 {count} 個：{', '.join(cols)}")

                print(f"  ✅ 最終選中來源：{selected['_來源']}")
            else:
                final_rows.append(group.iloc[0])

        # 建立最終 DataFrame
        final_df = pd.DataFrame(final_rows).drop(columns=["_non_null_count", "_來源優先", "_來源"])
        final_df = final_df.sort_values(by="音典排序", na_position="last")

        # 寫入資料庫
        final_df.to_sql("dialects", conn, if_exists="replace", index=False)
        # 加索引
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_dialects_code ON dialects(簡稱);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dialects_zone ON dialects(音典分區);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dialects_zone ON dialects(地圖集二分區);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dialects_flag ON dialects(存儲標記);")

    print(f"✅ SQLite 資料庫 `dialects_query.db` 已建立，dialects 表已更新完成。")


def process_all2sql(tsv_paths, db_path, append=False):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not append:
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
    update_rows = pd.DataFrame()  # 默认空的 DataFrame

    def clean_join(series):
        return ", ".join(x.strip() for x in series.dropna().astype(str).unique() if x and x.strip())

    # 只有当 append=True 时，才进行筛选
    if append:
        try:
            df_append = pd.read_excel(APPEND_PATH, sheet_name="檔案")
            update_rows = df_append[df_append['待更新'] == 1]
        except:
            print("读取 APPEND_PATH 文件失败，跳过筛选。")

        # 如果 append 为 True，删除数据库中与待更新行中“簡稱”匹配的记录
        if not update_rows.empty:
            # 去除 NaN 和空值，确保只有有效的簡稱列参与删除操作
            valid_簡稱 = update_rows['簡稱'].dropna()  # 去除 NaN 值
            for row in valid_簡稱:
                cursor.execute("DELETE FROM dialects WHERE 簡稱 = ?", (row,))
            conn.commit()

    for path in tsv_paths:
        if path == "_":
            continue

        # tsv_name = os.path.splitext(os.path.basename(path))[0]
        tsv_name = get_tsvs(single=path)[1][0]
        now_process = f"\n🔍 正在處理：{tsv_name}"
        print(now_process)
        with open(MISSING_DATA_LOG, "a", encoding="utf-8") as f:
            f.write("\n" + now_process + "\n")

        # 如果 append 为 True，则进行筛选
        if append and not update_rows.empty and tsv_name not in update_rows['簡稱'].values:
            print(f"跳過：{tsv_name} (不在待更新清單中)")
            continue

        try:
            df = extract_all_from_files(path)
            print(f"  📄 提取資料表：{len(df)} 行")

            df = df.fillna("")
            df["漢字"] = df["汉字"].astype(str).str.strip()
            df["音節"] = df["音标"].astype(str).str.strip()
            df["聲母"] = df["声母"].astype(str).str.strip()
            df["韻母"] = df["韵母"].astype(str).str.strip()
            df["聲調"] = df["声调"].astype(str).str.strip()
            df["註釋"] = df["註釋"].astype(str).str.strip() if "註釋" in df.columns else ""

            insert_count = 0
            for _, row in df.iterrows():
                char = row["漢字"]
                phonetic = row["音節"]
                cons = row["聲母"]
                vow = row["韻母"]
                tone = row["聲調"]
                note = row["註釋"]

                if not any([cons, vow, tone]):
                    continue

                if not all([cons, vow, tone]):
                    log_message = f"❗ 缺資料：char={char}, 音節={phonetic}, 聲母='{cons}', 韻母='{vow}', 聲調='{tone}'"
                    # print(log_message)
                    with open(MISSING_DATA_LOG, "a", encoding="utf-8") as f:
                        f.write(log_message + "\n")

                cursor.execute('''
                    INSERT INTO dialects (簡稱, 漢字, 音節, 聲母, 韻母, 聲調, 註釋, 多音字)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    tsv_name, char, phonetic,
                    cons, vow, tone, note, ""
                ))
                insert_count += 1

            conn.commit()
            log_lines.append(f"{tsv_name} 寫入了 {insert_count} 筆。")
            # print(f"✅ {tsv_name} 完成：共寫入 {insert_count} 筆。")

        except Exception as e:
            error_detail = traceback.format_exc()
            log_lines.append(f"❌ {tsv_name} 寫入失敗：\n{error_detail}")
            print(f"❌ 錯誤處理 {tsv_name}：\n{error_detail}")

    conn.close()
    print(f"\n📦 所有資料已寫入：{db_path}")
    conn_all = sqlite3.connect(db_path)
    # 創建索引，加快查詢速度
    print("※ 開始創建索引 ※")
    conn_all.execute("CREATE INDEX IF NOT EXISTS idx_loc ON dialects(簡稱);")
    conn_all.execute("CREATE INDEX IF NOT EXISTS idx_char ON dialects(漢字);")
    conn_all.commit()

    # print("\n📊 寫入總結：")
    # for line in log_lines:
    # print("   " + line)

    with open(WRITE_INFO_LOG, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines))
    # print(f"\n📝 已寫入紀錄至：{log_path}")


# 舊版代碼，直接刪除整個數據庫並更新(快，但是电脑会特别卡）
def process_polyphonic_annotations(db_path: str):
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM dialects ORDER BY 簡稱, 漢字", conn)

    print(f"🔍 資料庫讀取完成，共 {len(df)} 筆")

    # 一階段：合併同音節註釋（聲母、韻母、聲調一致）
    merged = []
    grouped = df.groupby(["簡稱", "漢字", "音節"])

    previous_short_name = None  # 用来保存上一次的地点信息
    count_num = 1
    for (short_name, char, syllable), group in grouped:
        if short_name != previous_short_name:  # 当地点变化时触发
            print(f"正在處理：{short_name}(第{count_num}個)")  # 输出调试信息，地点发生变化
            count_num += 1

        unique_phonetics = group[["聲母", "韻母", "聲調"]].drop_duplicates()
        if len(unique_phonetics) == 1:
            notes = group["註釋"].dropna().astype(str).str.strip().unique()
            notes = [n for n in notes if n]
            combined_note = ";".join(notes) if notes else ""

            base_row = group.iloc[0].copy()
            # if base_row["註釋"] != combined_note:
            #     print(f"📝 合併註釋：{char} / {syllable} → 「{combined_note}」")
            base_row["註釋"] = combined_note
            merged.append(base_row)
        else:
            print(f"⚠️ 音節相同但聲韻調不同：{char} / {syllable}")
            for _, row in group.iterrows():
                merged.append(row)
        previous_short_name = short_name  # 更新之前的地点

    merged_df = pd.DataFrame(merged)
    print(f"✅ 合併後剩餘 {len(merged_df)} 筆")

    # 二階段：標記多音字（音節不同）
    # final = []
    grouped2 = merged_df.groupby(["簡稱", "漢字"])

    # for (short_name, char), group in grouped2:
    #     if len(group["音節"].unique()) > 1:
    #         # print(f"🔁 多音字標記：{short_name} / {char}")
    #         group["多音字"] = "1"
    #         # for _, row in group.iterrows():
    #         # print("  ➤", dict(row))
    #     else:
    #         group["多音字"] = ""
    #     final.append(group)
    # final_df = pd.concat(final).reset_index(drop=True)

    # 使用 `transform()` 判断是否多音字
    merged_df['多音字'] = grouped2['音節'].transform(lambda x: '1' if x.nunique() > 1 else '')
    final_df = merged_df

    # print(f"💾 清空並重建資料表 dialects，共 {len(final_df)} 筆")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS dialects")
    final_df.to_sql("dialects", conn, index=False)

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

    print(f"🔍 待處理資料筆數：{len(df)}")

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
    # 創建索引，加快查詢速度
    print("※ 開始創建索引 ※")
    conn_all.execute("CREATE INDEX IF NOT EXISTS idx_loc ON dialects(簡稱);")
    conn_all.execute("CREATE INDEX IF NOT EXISTS idx_char ON dialects(漢字);")
    conn_all.commit()
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

    print("✅ 同步完成。已更新存儲標記。")


def process_phonology_excel(
        excel_file=PHO_TABLE_PATH,
        sheet_name="層級",
        db_file=CHARACTERS_DB_PATH,
        log_file=WRITE_INFO_LOG
):
    os.makedirs("data", exist_ok=True)

    # 欄位設置
    columns_needed = ["攝", "呼", "等", "韻", "入", "調", "清濁", "系", "組", "母", "部位", "方式", "單字", "釋義"]
    rename_map = {"單字": "漢字"}
    write_columns = ["攝", "呼", "等", "韻", "入", "調", "清濁", "系", "組", "母", "部位", "方式", "漢字", "釋義"]

    # 讀取 Excel
    try:
        df = pd.read_excel(excel_file, sheet_name=sheet_name, dtype=str)
    except Exception as e:
        print(f"❌ 讀取 Excel 失敗: {e}")
        return

    try:
        df = df[columns_needed].rename(columns=rename_map)
    except KeyError as e:
        print(f"❌ 缺少必要欄位: {e}")
        return

    # 清除漢字為空的行
    df = df[df["漢字"].notna() & (df["漢字"].str.strip() != "")]
    df['num'] = df.index + 2  # Excel 行號

    # 檢查其他欄位是否有缺值（不包含"漢字"與"num"）
    check_cols = [col for col in df.columns if col not in ["漢字", "num", "釋義"]]
    invalid_rows = df[df[check_cols].isnull().any(axis=1)]

    # 有效列
    df_valid = df.drop(index=invalid_rows.index)

    # 去除完全重複的列（只比較要寫入的列）
    df_unique = df_valid.drop_duplicates(subset=write_columns).copy()

    # 標記「多地位」：同漢字出現多次（但行不同）
    dup_counts = df_unique["漢字"].value_counts()
    df_unique["多地位標記"] = df_unique["漢字"].map(lambda x: "1" if dup_counts.get(x, 0) > 1 else "")

    # 輸出錯誤記錄
    if not invalid_rows.empty:
        invalid_output = invalid_rows[["num", "漢字"] + check_cols]
        print("❗ 發現欄位缺漏如下：")
        print(invalid_output)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(invalid_output.to_csv(index=False, sep='\t', lineterminator='\n'))

    # 寫入 SQLite
    try:
        conn = sqlite3.connect(db_file)
        df_unique.drop(columns=["num"]).to_sql("characters", conn, if_exists="replace", index=False)
        # ➤ 建立索引
        index_columns = [col for col in write_columns if col != "釋義"]  # 排除「釋義」
        index_columns.append("多地位標記")
        for col in index_columns:
            index_name = f"idx_characters_{col}"
            conn.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON characters({col});")

        conn.close()
        print("✅ 成功寫入 SQLite，總筆數：", len(df_unique))
    except Exception as e:
        print(f"❌ SQLite 寫入失敗: {e}")


def write_to_sql(yindian=None, write_chars_db=None, append=False):
    #  寫檔案表
    print("开始寫入檔案表")
    build_dialect_database()

    #  寫總數據表
    if yindian:
        if yindian == 'only':
            tsv_paths_yindian, *_ = get_tsvs(output_dir=YINDIAN_DATA_DIR)
            tsv_paths = [
                p for p in tsv_paths_yindian
                if os.path.splitext(os.path.basename(p))[0] not in exclude_files
            ]
        else:
            tsv_paths_yindian, *_ = get_tsvs(output_dir=YINDIAN_DATA_DIR)
            tsv_paths_mine, *_ = get_tsvs()
            # 用字典来保存最终的路径，并按文件名进行合并
            merged_paths = {}
            # 将 tsv_paths_yindian 中的文件路径添加到字典中，使用文件名作为键
            for path in tsv_paths_yindian:
                filename = os.path.basename(path)
                merged_paths[filename] = path
            # 遍历 tsv_paths_mine，如果文件名已存在，更新为 mine 中的路径
            for path in tsv_paths_mine:
                filename = os.path.basename(path)
                merged_paths[filename] = path  # 直接覆盖已有路径
            # print(merged_paths)
            # 合并完成后的路径列表
            # tsv_paths = list(merged_paths.values())
            tsv_paths = [
                path for file, path in merged_paths.items()
                if os.path.splitext(file)[0] not in exclude_files
            ]
            # print(tsv_paths)
            # tsv_paths = tsv_paths_yindian + tsv_paths_mine
    else:
        tsv_paths, *_ = get_tsvs()
    db_path = os.path.join(os.getcwd(), DIALECTS_DB_PATH)
    print("🚀 開始導入資料...")
    process_all2sql(tsv_paths, db_path, append)
    print("开始处理重复行以及标记多音字")
    if append:
        process_polyphonic_annotations_new(DIALECTS_DB_PATH, append=True)
    else:
        process_polyphonic_annotations(DIALECTS_DB_PATH)
    print("开始寫入存儲標記")
    sync_dialects_flags()

    if write_chars_db:
        #  寫漢字地位表
        print("开始寫入漢字地位表")
        process_phonology_excel()
    # print("✅ 測試完成。")


if __name__ == "__main__":
    write_to_sql()
    # build_dialect_database()
