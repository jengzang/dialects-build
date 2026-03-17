"""
语保数据库写入脚本
将两个语保Excel文件写入SQLite数据库 yubao.db：
1. 语保1284方言点词汇.xlsx → vocabulary 表
2. 语保1284方言点语法.xlsx → grammar 表
"""

import os
import sys
import sqlite3
from typing import Dict, List, Tuple
import pandas as pd
from tqdm import tqdm

# 设置UTF-8输出
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None


# ============================================================================
# 配置
# ============================================================================

# Excel文件路径
VOCAB_EXCEL = "scripts/sql/语保1284方言点词汇.xlsx"
GRAMMAR_EXCEL = "scripts/sql/语保1284方言点语法.xlsx"

# 数据库路径
DB_PATH = "data/yubao.db"

# 词汇表列名映射（原始列名 -> 英文列名）
VOCAB_COLUMN_MAPPING = {
    'no': 'no',
    'sheng': 'province',
    'shi': 'city',
    'xian': 'county',
    'cun': 'village',
    'jiedao': 'location',
    'jing': 'longitude',
    'wei': 'latitude',
    'word': 'word',
    '語音': 'pronunciation',
    '說明': 'note1',
    '說明.1': 'note2',
    '語言1': 'lang_cat1',
    '語言1.1': 'lang_cat2',
    '語言1.2': 'lang_cat3',
    'id': 'id'
}

# 语法表列名映射（原始列名 -> 英文列名）
GRAMMAR_COLUMN_MAPPING = {
    'city': 'city_code',
    'city_1': 'city_name',
    'a': 'form_a',
    'b': 'form_b',
    'c': 'form_c',
    'd': 'form_d',
    'e': 'form_e',
    'jing': 'longitude',
    'wei': 'latitude',
    'iid': 'iid',
    'memo': 'memo',
    'phonetic': 'phonetic',
    'sentence': 'sentence',
    'yuyan1': 'lang_cat1',
    'yuyan2': 'lang_cat2',
    'yuyan3': 'lang_cat3',
    'id': 'id'
}


# ============================================================================
# 辅助函数
# ============================================================================

def create_vocabulary_table(conn: sqlite3.Connection) -> None:
    """创建词汇表（vocabulary）"""
    conn.execute("DROP TABLE IF EXISTS vocabulary")

    create_sql = """
    CREATE TABLE vocabulary (
        id INTEGER PRIMARY KEY,
        no INTEGER,
        province TEXT,
        city TEXT,
        county TEXT,
        village TEXT,
        location TEXT,
        longitude REAL,
        latitude REAL,
        word TEXT,
        pronunciation TEXT,
        note1 TEXT,
        note2 TEXT,
        lang_cat1 TEXT,
        lang_cat2 TEXT,
        lang_cat3 TEXT
    )
    """
    conn.execute(create_sql)
    print("[OK] 已创建 vocabulary 表")


def create_grammar_table(conn: sqlite3.Connection) -> None:
    """创建语法表（grammar）"""
    conn.execute("DROP TABLE IF EXISTS grammar")

    create_sql = """
    CREATE TABLE grammar (
        id INTEGER PRIMARY KEY,
        iid INTEGER,
        city_code TEXT,
        city_name TEXT,
        form_a TEXT,
        form_b TEXT,
        form_c TEXT,
        form_d TEXT,
        form_e TEXT,
        longitude REAL,
        latitude REAL,
        phonetic TEXT,
        sentence TEXT,
        memo TEXT,
        lang_cat1 TEXT,
        lang_cat2 TEXT,
        lang_cat3 TEXT
    )
    """
    conn.execute(create_sql)
    print("[OK] 已创建 grammar 表")


def create_vocabulary_indexes(conn: sqlite3.Connection) -> None:
    """为词汇表创建索引"""
    indexes = [
        "CREATE UNIQUE INDEX idx_vocab_id ON vocabulary(id)",
        "CREATE INDEX idx_vocab_word ON vocabulary(word)",
        "CREATE INDEX idx_vocab_province ON vocabulary(province)",
        "CREATE INDEX idx_vocab_location_full ON vocabulary(province, city, county, village, location)",
        "CREATE INDEX idx_vocab_word_pronunciation ON vocabulary(word, pronunciation)",
        "CREATE INDEX idx_vocab_lang_cat ON vocabulary(lang_cat1, lang_cat2, lang_cat3)",
        "CREATE INDEX idx_vocab_coordinates ON vocabulary(longitude, latitude)"
    ]

    for idx_sql in indexes:
        conn.execute(idx_sql)

    print(f"[OK] 已为 vocabulary 创建 {len(indexes)} 个索引")


def create_grammar_indexes(conn: sqlite3.Connection) -> None:
    """为语法表创建索引"""
    indexes = [
        "CREATE UNIQUE INDEX idx_grammar_id ON grammar(id)",
        "CREATE INDEX idx_grammar_city_name ON grammar(city_name)",
        "CREATE INDEX idx_grammar_sentence ON grammar(sentence)",
        "CREATE INDEX idx_grammar_sentence_phonetic ON grammar(sentence, phonetic)",
        "CREATE INDEX idx_grammar_lang_cat ON grammar(lang_cat1, lang_cat2, lang_cat3)",
        "CREATE INDEX idx_grammar_city_sentence ON grammar(city_name, sentence)",
        "CREATE INDEX idx_grammar_city_full ON grammar(city_code, city_name)",
        "CREATE INDEX idx_grammar_coordinates ON grammar(longitude, latitude)"
    ]

    for idx_sql in indexes:
        conn.execute(idx_sql)

    print(f"[OK] 已为 grammar 创建 {len(indexes)} 个索引")


def rename_columns(df: pd.DataFrame, column_mapping: Dict[str, str]) -> pd.DataFrame:
    """重命名DataFrame列名"""
    # 只保留映射中存在的列
    existing_cols = [col for col in column_mapping.keys() if col in df.columns]
    df_filtered = df[existing_cols].copy()

    # 重命名
    rename_dict = {old: new for old, new in column_mapping.items() if old in existing_cols}
    df_filtered = df_filtered.rename(columns=rename_dict)

    return df_filtered


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """清洗DataFrame数据"""
    # 移除全空行
    df = df.dropna(how='all')

    # 处理datetime类型
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")

    # NaN -> None (SQLite NULL)
    df = df.where(pd.notnull(df), None)

    return df


def insert_dataframe_batch(
    conn: sqlite3.Connection,
    table_name: str,
    df: pd.DataFrame,
    batch_size: int = 1000
) -> int:
    """批量插入DataFrame数据"""
    cursor = conn.cursor()

    # 构建插入SQL
    columns = list(df.columns)
    placeholders = ", ".join(["?"] * len(columns))
    col_list = ", ".join([f'"{c}"' for c in columns])
    insert_sql = f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'

    # 转换为记录列表
    records = df.values.tolist()
    total_records = len(records)

    # 批量插入
    inserted = 0
    with tqdm(total=total_records, desc=f"写入 {table_name}", unit="行") as pbar:
        for i in range(0, total_records, batch_size):
            batch = records[i:i + batch_size]
            cursor.executemany(insert_sql, batch)
            conn.commit()
            inserted += len(batch)
            pbar.update(len(batch))

    return inserted


# ============================================================================
# 主处理函数
# ============================================================================

def process_vocabulary(conn: sqlite3.Connection) -> Tuple[int, int]:
    """处理词汇表Excel文件（35个sheet合并）"""
    print("\n" + "="*60)
    print("开始处理词汇表...")
    print("="*60)

    # 读取所有sheet
    excel_file = pd.ExcelFile(VOCAB_EXCEL, engine="openpyxl")
    sheet_names = excel_file.sheet_names
    print(f"检测到 {len(sheet_names)} 个sheet")

    all_dfs = []
    total_rows = 0

    # 逐个sheet读取并处理
    for sheet_name in tqdm(sheet_names, desc="读取sheet", unit="个"):
        df = pd.read_excel(VOCAB_EXCEL, sheet_name=sheet_name, engine="openpyxl")

        # 重命名列
        df = rename_columns(df, VOCAB_COLUMN_MAPPING)

        # 清洗数据
        df = clean_dataframe(df)

        all_dfs.append(df)
        total_rows += len(df)

    print(f"[OK] 读取完成，共 {total_rows} 行数据")

    # 合并所有sheet
    print("正在合并所有sheet...")
    merged_df = pd.concat(all_dfs, ignore_index=True)
    print(f"[OK] 合并完成，共 {len(merged_df)} 行")

    # 重新生成ID（确保唯一性）
    merged_df['id'] = range(1, len(merged_df) + 1)

    # 插入数据库
    inserted = insert_dataframe_batch(conn, "vocabulary", merged_df)

    return len(sheet_names), inserted


def process_grammar(conn: sqlite3.Connection) -> int:
    """处理语法表Excel文件（1个sheet）"""
    print("\n" + "="*60)
    print("开始处理语法表...")
    print("="*60)

    # 读取Excel
    print(f"正在读取 {GRAMMAR_EXCEL}...")
    df = pd.read_excel(GRAMMAR_EXCEL, sheet_name="語寶1284方言點語法(完整)", engine="openpyxl")
    print(f"[OK] 读取完成，共 {len(df)} 行")

    # 重命名列
    df = rename_columns(df, GRAMMAR_COLUMN_MAPPING)

    # 清洗数据
    df = clean_dataframe(df)

    print(f"[OK] 数据清洗完成，剩余 {len(df)} 行")

    # 插入数据库
    inserted = insert_dataframe_batch(conn, "grammar", df)

    return inserted


# ============================================================================
# 主程序
# ============================================================================

def main():
    """主函数"""
    print("\n" + "="*60)
    print("语保数据库写入程序")
    print("="*60)

    # 检查文件是否存在
    if not os.path.exists(VOCAB_EXCEL):
        raise FileNotFoundError(f"未找到词汇表文件: {VOCAB_EXCEL}")
    if not os.path.exists(GRAMMAR_EXCEL):
        raise FileNotFoundError(f"未找到语法表文件: {GRAMMAR_EXCEL}")

    print(f"[OK] 词汇表文件: {VOCAB_EXCEL}")
    print(f"[OK] 语法表文件: {GRAMMAR_EXCEL}")
    print(f"[OK] 目标数据库: {DB_PATH}")

    # 创建数据库目录
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # 连接数据库
    print("\n连接数据库...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64MB cache

    try:
        # 创建表
        print("\n创建数据表...")
        create_vocabulary_table(conn)
        create_grammar_table(conn)

        # 处理词汇表
        sheet_count, vocab_inserted = process_vocabulary(conn)

        # 处理语法表
        grammar_inserted = process_grammar(conn)

        # 创建索引
        print("\n" + "="*60)
        print("创建索引...")
        print("="*60)
        create_vocabulary_indexes(conn)
        create_grammar_indexes(conn)

        # 优化数据库
        print("\n优化数据库...")
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
        print("[OK] 数据库优化完成")

        # 统计信息
        print("\n" + "="*60)
        print("写入完成统计")
        print("="*60)
        print(f"词汇表:")
        print(f"  - 处理sheet数: {sheet_count}")
        print(f"  - 写入记录数: {vocab_inserted:,}")
        print(f"  - 索引数: 7")
        print(f"\n语法表:")
        print(f"  - 写入记录数: {grammar_inserted:,}")
        print(f"  - 索引数: 8")
        print(f"\n数据库文件: {DB_PATH}")

        # 数据库大小
        db_size = os.path.getsize(DB_PATH) / (1024 * 1024)
        print(f"数据库大小: {db_size:.2f} MB")

        # 验证数据
        print("\n" + "="*60)
        print("数据验证")
        print("="*60)

        cursor = conn.cursor()

        # 验证词汇表
        cursor.execute("SELECT COUNT(*) FROM vocabulary")
        vocab_count = cursor.fetchone()[0]
        print(f"[OK] vocabulary 表记录数: {vocab_count:,}")

        cursor.execute("SELECT COUNT(DISTINCT province) FROM vocabulary")
        province_count = cursor.fetchone()[0]
        print(f"[OK] 省份数: {province_count}")

        # 验证语法表
        cursor.execute("SELECT COUNT(*) FROM grammar")
        grammar_count = cursor.fetchone()[0]
        print(f"[OK] grammar 表记录数: {grammar_count:,}")

        cursor.execute("SELECT COUNT(DISTINCT city_name) FROM grammar")
        city_count = cursor.fetchone()[0]
        print(f"[OK] 城市数: {city_count}")

        print("\n" + "="*60)
        print("[SUCCESS] 全部完成！")
        print("="*60)

    except Exception as e:
        print(f"\n[ERROR] 错误: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
