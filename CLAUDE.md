# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**方音圖鑒 (Dialect Atlas)** - A Chinese dialect pronunciation database preprocessing system that converts various word list formats into optimized SQLite databases. Processes data from ~2000 dialect locations with 6M+ entries.

**Related repositories:**
- Backend: https://github.com/jengzang/dialects-backend
- Frontend: https://github.com/jengzang/dialects-js-frontend
- Live site: https://dialects.yzup.top/

## Development Commands

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Or install individually
pip install pandas==2.2.3 openpyxl==3.1.5 xlrd==2.0.1 python-docx==1.1.2 opencc==1.1.9
```

### Main Processing Commands

**Complete preprocessing pipeline:**
```bash
# Full admin mode (processes data/processed/ + data/yindian/)
python build.py -u admin -t convert needchars sync query chars

# User mode only (processes data/yindian/ only)
python build.py -u user

# Default behavior (no args): writes processed TSV files to database
python build.py
```

**Individual processing steps:**
```bash
# Convert raw files to TSV only
python build.py -u admin -t convert

# Write to database without conversion
python build.py -u admin

# Build query database
python build.py -u admin -t query

# Sync storage flags
python build.py -u admin -t sync

# Write Middle Chinese position table
python build.py -u admin -t chars

# Incremental update (only files marked "待更新" in config)
python build.py -u admin -t convert needchars append sync
```

### Utility Commands

**Word list validation (5-step interactive check):**
```bash
python utils.py -t CHECK
```

**Jyutping to IPA conversion:**
```bash
python utils.py -t jyut
```

**Merge multiple word lists:**
```bash
python utils.py -t MERGE
```

**Compare yindian vs pull_yindian files:**
```bash
python utils.py -t COMPARE
```

**Clean up duplicate files:**
```bash
python utils.py -t CLEANUP
```

## Architecture

### Data Processing Pipeline

```
Raw Files (Excel/Word/TSV)
    ↓
[raw2tsv.py] Format Detection & Conversion
    ↓
TSV Files (data/processed/ or data/yindian/)
    ↓
[tsv2sql.py] Feature Extraction (initials, finals, tones)
    ↓
SQLite Databases
    ├─ characters.db (Middle Chinese positions)
    ├─ dialects_all.db (phonological data)
    └─ dialects_query.db (geographic metadata)
```

### Core Modules

**source/** - Data processing pipeline
- `raw2tsv.py`: Orchestrates format conversion; dispatches to format-specific handlers
- `format_convert.py`: Contains handlers for three formats (音典, 跳跳老鼠, 縣志)
- `process_tones.py`: Extracts tone mappings and converts tone values to tone names
- `tsv2sql.py`: Database operations - writes data, builds query DB, syncs flags
- `convert_jyut.py`: Jyutping (Cantonese romanization) to IPA conversion
- `match_fromdb.py`: Scans TSV files and resolves character conflicts via database lookup
- `change_coordinates.py`: Transforms Baidu coordinates to GCJ-02 (Mars coordinate system)
- `get_new.py`: Extracts phonological data from processed files

**common/** - Shared utilities
- `config.py`: Centralized path definitions and database locations
- `constants.py`: Exclusion lists and shared constants
- `s2t.py`: Multi-level simplified/traditional Chinese conversion using OpenCC
- `search_tones.py`: Tone searching and matching utilities

**scripts/** - Interactive tools
- `check/checks.py`: Five-step validation system (character validity, tone consistency, zero initials, phonemic oppositions, irregular readings)
- `jyut2ipa/replace.py`: Batch Jyutping to IPA conversion
- `merge/wordsheet_merge.py`: Merges multiple word lists maintaining character order
- `sql/`: Database initialization and index creation utilities
- `compare_yindian.py`: Compares yindian directory with pull_yindian updates
- `cleanup_duplicates.py`: Identifies and removes duplicate files

### Configuration System

All data sources must be registered in `data/dependency/jengzang補充.xlsx` (Sheet: "檔案"):

**Required fields:**
- `簡稱`: Unique dialect identifier (e.g., 广州, 香港)
- `文件名`: Filename pattern (supports * wildcard)
- `字表格式`: Format type (音典 / 跳跳老鼠 / 縣志)
- `是否有人在做`: Processing flag (must be "已做" to process)

**Optional but important:**
- `繁簡`: Simplified/Traditional marker ("简" triggers s2t conversion)
- `字聲韻調註列名`: Column mapping (e.g., "A,B,C" or "A,(G),H" for Jyutping)
- `字表使用調值`: Whether word list uses tone values (☑) vs tone names (☐)
- `拼音`: Romanization system ("粵拼" for Jyutping)
- `待更新`: Append mode flag (1 = update this entry)

### Word List Formats

The system supports three primary formats originating from the 漢字音典 (Chinese Character Pronunciation Dictionary) standard:

1. **音典 (Standard Dictionary)**: One character per row
   - Format: `#漢字 音標 解釋`
   - Example files in `data/raw/`

2. **跳跳老鼠 (Syllable-grouped)**: Multiple characters per syllable
   - Format: `音節 漢字列表`
   - Characters with same pronunciation grouped together

3. **縣志 (County Gazetteer)**: Separated tables by initial/final/tone
   - Format: `#韻 聲母 聲調 字`
   - Phonological components split into separate sections

### Database Schema

**dialects_all.db** - Main pronunciation database
```sql
CREATE TABLE dialects (
    簡稱 TEXT,      -- Dialect code
    漢字 TEXT,      -- Character
    音節 TEXT,      -- IPA syllable
    聲母 TEXT,      -- Initial
    韻母 TEXT,      -- Final
    聲調 TEXT,      -- Tone name
    註釋 TEXT,      -- Notes (literary/colloquial readings)
    多音字 TEXT     -- Polyphonic marker
);
-- Compound indexes for optimized queries
CREATE INDEX idx_dialects_char_abbr ON dialects(漢字, 簡稱);
CREATE INDEX idx_dialects_abbr_char ON dialects(簡稱, 漢字);
```

**dialects_query.db** - Geographic and metadata
- Contains coordinates (GCJ-02), administrative divisions, tone values (T1-T10)
- Used for filtering and categorizing dialect locations

**characters.db** - Middle Chinese reconstruction
- 13+ fields including 攝, 呼, 等, 韻, 調, 清濁, 系, 組, 母
- Source data: `data/dependency/聲韻.xlsx`

### Mode System

**Admin Mode** (`-u admin`):
- Processes: `data/processed/` + `data/yindian/`
- Databases: `dialects_admin.db`, `query_admin.db`
- Use for comprehensive dataset management

**User Mode** (`-u user`):
- Processes: `data/yindian/` only
- Databases: `dialects_user.db`, `query_user.db`
- Use for public-facing data segregation

## Key Implementation Details

### Simplified/Traditional Conversion
Uses multi-level conversion strategy:
1. Custom normalization table (`data/dependency/正字.tsv`)
2. OpenCC conversion library
3. Applied based on `繁簡` column in config ("简" triggers conversion)

### Jyutping Support
- Detected via parentheses in column mapping: `A,(G),H`
- Converted to IPA using rule table in `scripts/jyut2ipa/`
- Tone numbers (1-6) mapped to tone names using Middle Chinese categories

### Coordinate Transformation
- Input: Baidu coordinates from config file
- Output: GCJ-02 (火星坐標系) for Chinese mapping systems
- Implementation: `source/change_coordinates.py` (GPSUtil class)

### Performance Optimizations
- Batch inserts using `executemany()`
- `PRAGMA synchronous=OFF` during bulk writes
- Compound indexes on (漢字, 簡稱) and (簡稱, 漢字)
- Memory-based logging to reduce I/O
- Result: 6-8x speedup (120 min → 15-20 min for full dataset)

### Conflict Resolution
The `match_fromdb.py` module handles character ambiguities:
- Detects simplified characters mapping to multiple traditional variants
- Queries Middle Chinese database for context-based resolution
- Saves resolution decisions to `data/conflict_resolutions.json`
- Reuses saved resolutions for consistency

## Working with This Codebase

### Adding a New Dialect Location
1. Place raw file in `data/raw/`
2. Add entry to `data/dependency/jengzang補充.xlsx`
3. Set `是否有人在做` = "已做"
4. Fill required fields (簡稱, 文件名, 字表格式)
5. Run: `python build.py -u admin -t convert needchars sync`

### Modifying Format Handlers
Format-specific logic is in `source/format_convert.py`:
- `process_音典()`: One-character-per-row format
- `process_跳跳老鼠()`: Syllable-grouped format
- `process_縣志()`: Split-table format

Each handler must:
1. Read file and normalize to standard columns
2. Return DataFrame with: 漢字, 音標, 解釋
3. Handle format-specific quirks (tone markers, separators)

### Database Queries
Common patterns for working with the databases:
```python
import sqlite3
from common.config import DIALECTS_DB_ADMIN_PATH, QUERY_DB_ADMIN_PATH

# Query character pronunciation
conn = sqlite3.connect(DIALECTS_DB_ADMIN_PATH)
cursor = conn.execute(
    "SELECT * FROM dialects WHERE 漢字=? AND 簡稱=?",
    ("時", "广州")
)
results = cursor.fetchall()

# Query location metadata
conn = sqlite3.connect(QUERY_DB_ADMIN_PATH)
cursor = conn.execute(
    "SELECT 經緯度, T1陰平, T2陽平 FROM dialects WHERE 簡稱=?",
    ("广州",)
)
```

### Logging and Debugging
Logs are in `logs/` directory:
- `缺資料.txt`: Missing data warnings
- `write.txt`: Write operation status
- `write_error.txt`: Write errors

Most modules use print statements for progress tracking. The processing pipeline is sequential, making it easy to identify which stage fails.

## Important Notes

### File Naming Conventions
- TSV files must match `簡稱` field from config
- Example: config has `簡稱="广州"` → file should be `广州.tsv`
- Wildcard matching: `文件名="广州*.xlsx"` matches `广州.xlsx`, `广州方言.xlsx`, etc.

### Character Encoding
- All TSV files use UTF-8 encoding
- Excel files can be any encoding (handled by pandas/openpyxl)
- Database stores data in UTF-8

### Append Mode Caution
Using `-t append` will only process entries where `待更新=1` in config. This overwrites existing data for those locations. Ensure this is intentional before running.

### Update Mode
The `-t update` flag processes TSV files from `data/raw/pull_yindian/` directory. This is for incremental updates from external sources.

## Troubleshooting

**"找不到對應處理函數"**: Check that `字表格式` is exactly one of: 音典, 跳跳老鼠, 縣志

**"無法匹配任何文件"**: Verify file exists in `data/raw/` and matches `文件名` pattern in config

**"粵拼轉換失敗"**: Ensure `拼音="粵拼"` and column mapping uses parentheses: `A,(G),H`

**Database locked errors**: Close any SQLite browser/tool that might have the database open

**Memory errors on large datasets**: Processing happens in batches; if issues persist, reduce batch size in `tsv2sql.py`
