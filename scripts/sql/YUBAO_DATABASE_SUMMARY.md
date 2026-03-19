# YuBao Database Implementation Summary

**Date**: 2026-01-30
**Status**: ✅ Successfully Completed
**Total Time**: ~2 hours (1h 52m reading + 10m processing/indexing)

---

## Files Created

### Main Script
- **`scripts/sql/write_yubao.py`** (413 lines)
  - Reads 35 vocabulary Excel sheets
  - Reads 1 grammar Excel sheet
  - Column mapping (Chinese → English)
  - Data cleaning and validation
  - Batch insertion with progress bars
  - Index creation
  - Database optimization

### Database
- **`data/yubao.db`** (564.68 MB)
  - 2 tables (vocabulary, grammar)
  - 15 indexes (7 + 8)
  - 1,740,598 total records

---

## Database Schema

### Table 1: `vocabulary` (词汇表)

**Source**: 语保1284方言点词汇.xlsx (35 sheets merged)
**Records**: 1,672,188
**Size**: ~550 MB

#### Fields (15 columns)
| Column Name | Type | Description | Source Column |
|------------|------|-------------|---------------|
| id | INTEGER | Unique identifier (PRIMARY KEY) | id |
| no | INTEGER | Serial number | no |
| province | TEXT | Province/Municipality | sheng |
| city | TEXT | City | shi |
| county | TEXT | County/District | xian |
| village | TEXT | Township/Village | cun |
| location | TEXT | Specific location | jiedao |
| longitude | REAL | Longitude (BD-09) | jing |
| latitude | REAL | Latitude (BD-09) | wei |
| word | TEXT | Chinese word/character | word |
| pronunciation | TEXT | IPA phonetic notation | 語音 |
| note1 | TEXT | Note/Description 1 | 說明 |
| note2 | TEXT | Note/Description 2 | 說明.1 |
| lang_cat1 | TEXT | Language category 1 | 語言1 |
| lang_cat2 | TEXT | Language category 2 | 語言1.1 |
| lang_cat3 | TEXT | Language category 3 | 語言1.2 |

#### Statistics
- **Provinces**: 35
- **Cities**: 496
- **Unique words**: 1,147
- **Total records**: 1,672,188

#### Indexes (7)
1. **idx_vocab_id** (UNIQUE): `id`
2. **idx_vocab_word**: `word`
3. **idx_vocab_province**: `province`
4. **idx_vocab_location_full**: `province, city, county, village, location`
5. **idx_vocab_word_pronunciation**: `word, pronunciation`
6. **idx_vocab_lang_cat**: `lang_cat1, lang_cat2, lang_cat3`
7. **idx_vocab_coordinates**: `longitude, latitude`

---

### Table 2: `grammar` (语法表)

**Source**: 语保1284方言点语法.xlsx (1 sheet)
**Records**: 68,410
**Size**: ~14 MB

#### Fields (16 columns)
| Column Name | Type | Description | Source Column |
|------------|------|-------------|---------------|
| id | INTEGER | Unique identifier (PRIMARY KEY) | id |
| iid | INTEGER | Internal ID | iid |
| city_code | TEXT | City code | city |
| city_name | TEXT | City name | city_1 |
| form_a | TEXT | Grammar form A | a |
| form_b | TEXT | Grammar form B | b |
| form_c | TEXT | Grammar form C | c |
| form_d | TEXT | Grammar form D | d |
| form_e | TEXT | Grammar form E | e |
| longitude | REAL | Longitude (BD-09) | jing |
| latitude | REAL | Latitude (BD-09) | wei |
| phonetic | TEXT | IPA phonetic notation | phonetic |
| sentence | TEXT | Example sentence | sentence |
| memo | TEXT | Memo/Note | memo |
| lang_cat1 | TEXT | Language category 1 | yuyan1 |
| lang_cat2 | TEXT | Language category 2 | yuyan2 |
| lang_cat3 | TEXT | Language category 3 | yuyan3 |

#### Statistics
- **City codes**: 564
- **Total records**: 68,410

#### Indexes (8)
1. **idx_grammar_id** (UNIQUE): `id`
2. **idx_grammar_city_name**: `city_name`
3. **idx_grammar_sentence**: `sentence`
4. **idx_grammar_sentence_phonetic**: `sentence, phonetic`
5. **idx_grammar_lang_cat**: `lang_cat1, lang_cat2, lang_cat3`
6. **idx_grammar_city_sentence**: `city_name, sentence`
7. **idx_grammar_city_full**: `city_code, city_name`
8. **idx_grammar_coordinates**: `longitude, latitude`

---

## Performance Verification

All indexes are functioning correctly and being used by SQLite's query planner:

### Test Results
✅ **Word search** - Uses `idx_vocab_word`
✅ **Province search** - Uses `idx_vocab_province` (covering index)
✅ **Location search** - Uses `idx_vocab_location_full`
✅ **City search** - Uses `idx_grammar_city_name`
✅ **Coordinate range search** - Uses `idx_vocab_coordinates` (covering index)

---

## Key Decisions Made

### ✅ Coordinate System
- **Decision**: Keep BD-09 (Baidu) coordinate system
- **Rationale**: Maintain consistency with source data; conversion can be done at frontend if needed

### ✅ Sheet Merging
- **Decision**: Merge all 35 vocabulary sheets into single table
- **Rationale**: Simpler queries, unified indexing, province field distinguishes regions

### ✅ Column Naming
- **Decision**: Use English column names
- **Rationale**: Better for API development, clearer for international collaboration

### ✅ Duplicate Column Handling
- **Decision**: Pandas auto-naming (說明 → 說明, 說明.1; 語言1 → 語言1, 語言1.1, 語言1.2)
- **Rationale**: Maps directly to pandas behavior, predictable

---

## Usage Examples

### Connect to Database
```python
import sqlite3
conn = sqlite3.connect('data/yubao.db')
cursor = conn.cursor()
```

### Query 1: Find pronunciations of a word
```python
cursor.execute('''
    SELECT province, city, pronunciation
    FROM vocabulary
    WHERE word = '太阳'
    LIMIT 10
''')
```

### Query 2: Find words in a specific location
```python
cursor.execute('''
    SELECT word, pronunciation
    FROM vocabulary
    WHERE province = '广东' AND city = '广州市'
    LIMIT 10
''')
```

### Query 3: Find grammar examples by city
```python
cursor.execute('''
    SELECT sentence, form_a, form_b
    FROM grammar
    WHERE city_name LIKE '%广州%'
    LIMIT 10
''')
```

### Query 4: Find dialects near coordinates
```python
cursor.execute('''
    SELECT province, city, word, pronunciation
    FROM vocabulary
    WHERE longitude BETWEEN 113.0 AND 114.0
      AND latitude BETWEEN 23.0 AND 24.0
    LIMIT 10
''')
```

---

## Data Processing Timeline

| Stage | Duration | Description |
|-------|----------|-------------|
| Sheet Reading | 1h 52m | Read and process 35 Excel sheets |
| Data Merging | ~30s | Concat all DataFrames |
| Vocabulary Insert | 6s | Insert 1,672,188 records (batch 1000) |
| Grammar Read | ~10s | Read grammar Excel file |
| Grammar Insert | <1s | Insert 68,410 records |
| Index Creation | ~2m | Create 15 indexes |
| VACUUM | ~1m | Optimize database |
| ANALYZE | <1s | Update statistics |
| **Total** | **~2h** | Complete pipeline |

---

## File Sizes

| File | Size |
|------|------|
| 语保1284方言点词汇.xlsx | 127 MB |
| 语保1284方言点语法.xlsx | 8.3 MB |
| yubao.db | 564.68 MB |
| yubao.db-wal | Variable |
| yubao.db-shm | Variable |

---

## Next Steps (Optional)

### Recommended Enhancements
1. **Coordinate Conversion**: Add WGS-84 coordinate columns for mapping
2. **Full-Text Search**: Create FTS5 virtual tables for faster text search
3. **API Development**: Build REST API using Flask/FastAPI
4. **Web Interface**: Create search interface for users
5. **Data Validation**: Add constraint checks for data quality
6. **Backup Strategy**: Implement automated backup system

### Sample Query Performance Improvements
```sql
-- Create FTS5 for fast text search
CREATE VIRTUAL TABLE vocabulary_fts USING fts5(
    word, pronunciation, note1, note2,
    content=vocabulary
);

-- Create view for WGS-84 coordinates
CREATE VIEW vocabulary_wgs84 AS
SELECT *, bd09_to_wgs84(longitude, latitude) AS coords_wgs84
FROM vocabulary;
```

---

## Technical Notes

### Database Configuration
- **Journal Mode**: WAL (Write-Ahead Logging)
- **Synchronous**: NORMAL
- **Cache Size**: 64 MB
- **Page Size**: Default (4096 bytes)

### Python Dependencies
- pandas
- openpyxl
- tqdm
- sqlite3 (built-in)

### System Requirements
- Python 3.7+
- 2 GB RAM minimum
- 1 GB free disk space

---

## Validation Checklist

- [x] Both Excel files read successfully
- [x] All 35 sheets merged correctly
- [x] Column names mapped correctly
- [x] No data loss during processing
- [x] All records inserted (1,740,598 total)
- [x] All indexes created (15 total)
- [x] Indexes used in queries
- [x] Database optimized (VACUUM + ANALYZE)
- [x] File permissions correct
- [x] No errors or warnings

---

## Contact & Support

For issues or questions about this database:
- Script location: `scripts/sql/write_yubao.py`
- Database location: `data/yubao.db`
- Documentation: This file

---

**Implementation Date**: 2026-01-30
**Script Version**: 1.0
**Database Version**: 1.0
