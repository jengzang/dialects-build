# 音典特殊记录与词表候选提取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为音典拉取流程增加按地点分文件的方框字表、带注释记录和现代字表词语候选提取功能。

**Architecture:** 保持 `source/mcp_export.py` 只负责拉取文件，使用 `source/extract_yindian.py` 负责扫描和筛选 TSV。`build.py` 解析 `-v/--vocabulary`、`-n/--note` 与 `-w/--word`，在拉取后或独立运行时调用提取器；输出目录和输入目录通过 `common.config` 常量集中定义。词表候选只处理现代 `#漢字` 字表，输出 `~` 可恢复候选和普通注释待审查记录。

**Tech Stack:** Python、argparse、标准库 `csv`/`shutil`/`pathlib`、unittest/pytest。

---

### Task 1: Add extraction behavior tests

**Files:**
- Create: `tests/test_extract_yindian.py`
- Modify: `tests/test_build_mcp_mode.py`

- [x] **Step 1: Write the failing extractor test**

Create temporary `pull_yindian/` input files with rows containing `□`, `■`, `☑`, a normal character, and both populated and blank explanation fields. Assert that:

```python
extract_yindian_records(
    source_dir,
    vocabulary=True,
    note=True,
    output_root=output_root,
)
```

creates one output file per matching source location under `vocabulary/` and `note/`, preserves the header and original columns, excludes unmatched rows, and does not create a file for a location with no matches.

- [x] **Step 2: Run the focused test and verify it fails**

Run:

```bash
pytest -q tests/test_extract_yindian.py
```

Expected: FAIL because `source.extract_yindian` and `extract_yindian_records` do not yet exist.

- [x] **Step 3: Add CLI tests**

Extend `tests/test_build_mcp_mode.py` to assert:

```python
args = parser.parse_args(["-v", "-n"])
assert args.vocabulary is True
assert args.note is True
```

Also invoke `build.main()` with only `vocabulary=True` while mocking the extractor and `write_to_sql`; assert the extractor is called and the default database writer is not called.

- [x] **Step 4: Run the focused CLI test and verify the expected failure**

Run:

```bash
pytest -q tests/test_build_mcp_mode.py
```

Expected: FAIL because the parser and `main()` do not yet define or dispatch the new flags.

### Task 2: Implement per-location extraction

**Files:**
- Modify: `common/config.py`
- Create: `source/extract_yindian.py`

- [x] **Step 1: Add output path constants**

Add `EXTRACT_YINDIAN_DIR`, `VOCABULARY_EXTRACT_DIR`, and `NOTE_EXTRACT_DIR` under the existing MCP pull path constants:

```python
EXTRACT_YINDIAN_DIR = Path(BASE_DIR) / "data" / "raw" / "extract"
VOCABULARY_EXTRACT_DIR = EXTRACT_YINDIAN_DIR / "vocabulary"
NOTE_EXTRACT_DIR = EXTRACT_YINDIAN_DIR / "note"
```

- [x] **Step 2: Implement the extractor**

Implement:

```python
def extract_yindian_records(
    source_dir: Path,
    *,
    vocabulary: bool = False,
    note: bool = False,
    output_root: Path | None = None,
) -> dict[str, int]:
    ...
```

The function must:

1. Validate that at least one extraction mode is enabled.
2. Clear only the selected output subdirectories before scanning.
3. Iterate source `*.tsv` files in stable filename order.
4. Parse each file with `csv.reader(..., delimiter="\t")`.
5. Resolve the `漢字`, `音標`, and explanation column indexes from the header.
6. Match box characters by testing every character in the hanzi cell against the shared box set.
7. Match notes after stripping whitespace.
8. Write matching rows with the original header and all original columns using UTF-8 TSV.
9. Skip empty result files.
10. Return counts keyed by output mode and source filename for testable reporting.

- [x] **Step 3: Run the extractor tests and verify they pass**

Run:

```bash
pytest -q tests/test_extract_yindian.py
```

Expected: PASS.

### Task 3: Wire the flags into `build.py`

**Files:**
- Modify: `build.py`
- Modify: `tests/test_build_mcp_mode.py`

- [x] **Step 1: Add parser options**

Add boolean flags in the MCP pull argument group:

```python
pull_group.add_argument(
    "-v", "--vocabulary",
    action="store_true",
    help="提取汉字字段中的方框占位符记录，按地点输出到 data/raw/extract/vocabulary/",
)
pull_group.add_argument(
    "-n", "--note",
    action="store_true",
    help="提取带解释/注释的记录，按地点输出到 data/raw/extract/note/",
)
```

- [x] **Step 2: Dispatch extraction at the correct point**

After `export_mcp_assets()` returns, call `extract_yindian_records()` when either flag is enabled. When no MCP mode is supplied, call it against the existing pull directory. Use `getattr()` for the new fields in `main()` so existing programmatic callers without those attributes remain compatible.

- [x] **Step 3: Prevent accidental default database writes**

Update the default-write predicate so `python build.py -v`, `python build.py -n`, and `python build.py -v -n` perform extraction only and do not call `write_to_sql()`.

- [x] **Step 4: Run the CLI tests**

Run:

```bash
pytest -q tests/test_build_mcp_mode.py
```

Expected: PASS.

### Task 4: Add modern word-list candidate extraction

**Files:**
- Modify: `source/extract_yindian.py`
- Modify: `common/config.py`
- Modify: `tests/test_extract_yindian.py`

- [x] **Step 1: Write failing tests for candidate extraction**

Add a temporary source directory containing:

```text
#漢字  音標  解釋
㗦      lu4  ~嘈,吵鬧
□       sɔ1  ~腰:脊背微駝
一       i1   这条注释没有占位符，但保留待审查
```

Also add `#詞語`/historical filenames with notes. Assert that `extract_yindian_words()` writes only the eligible location file, produces columns
`标准词、方言词、音标、注释、type、原始汉字、来源文件、原始行号`, replaces every `~`/`～` for `tilde`, leaves `标准词` empty, leaves `方言词` empty for `note`, and skips `固原`/historical/dictionary files.

- [x] **Step 2: Run the focused test and verify it fails**

Run:

```bash
pytest -q tests/test_extract_yindian.py -k word
```

Expected: FAIL because the word extractor and output constant do not yet exist.

- [x] **Step 3: Implement the candidate extractor**

Add a focused function that:

1. Clears only the word output directory.
2. Skips filenames beginning with a four-digit year or matching the historical/dictionary/non-dialect exclusion terms and `固原`.
3. Requires a `#漢字`/`#汉字` header, so `#詞語` files never enter.
4. Emits every non-empty note row.
5. Replaces all `~` and `～` markers with the raw hanzi for `type=tilde`.
6. Emits `type=note` and an empty dialect word when no marker exists.
7. Writes one UTF-8 TSV per source location with source filename and one-based source row number.

- [x] **Step 4: Run the focused tests**

Run:

```bash
pytest -q tests/test_extract_yindian.py -k word
```

Expected: PASS.

### Task 5: Wire the word flag into `build.py`

**Files:**
- Modify: `build.py`
- Modify: `tests/test_build_mcp_mode.py`

- [x] **Step 1: Add parser and dispatch tests**

Assert `parser.parse_args(["-w"])` sets `word=True`, and a programmatic call with only `word=True` calls the word extractor without entering the default database-writing path.

- [x] **Step 2: Run the focused CLI tests and verify they fail**

Run:

```bash
pytest -q tests/test_build_mcp_mode.py -k word
```

Expected: FAIL because `build.py` does not yet expose or dispatch `-w`.

- [x] **Step 3: Wire the flag**

Call the word extractor after a requested MCP export or against the existing `pull_yindian` directory, and include `word` in the early-return and default-write guards.

- [x] **Step 4: Run the focused CLI tests**

Run:

```bash
pytest -q tests/test_build_mcp_mode.py -k word
```

Expected: PASS.

### Task 6: Update user documentation and verify real data

**Files:**
- Modify: `readme.md`

- [x] **Step 1: Document the two flags**

Add all three flags to the command-line parameter table, explain the three output directories, document `type=tilde`/`type=note`, and add examples:

```bash
python build.py -m diff -v
python build.py -m diff -n
python build.py -m diff -v -n
python build.py -v
python build.py -w
```

- [x] **Step 2: Run focused and complete tests**

Run:

```bash
pytest -q
```

Expected: all existing and new tests pass.

- [x] **Step 3: Run a real sample extraction through the main entry**

Run:

```bash
python3 build.py -w
```

Verify that `data/raw/extract/word/` contains separate per-location TSV files, excluded sources are absent, and `data/raw/pull_yindian/` is unchanged.

### Task 7: Analyze complete selected points with an independent DeepSeek script

**Files:**
- Add: `scripts/yindian_llm.py`
- Add: `tests/test_yindian_llm.py`
- Modify: `readme.md`
- Modify: `docs/superpowers/specs/2026-09-22-yindian-row-extract-design.md`

- [x] **Step 1: Run the independent command**

```bash
python3 scripts/yindian_llm.py run \
  --points 泉州,蘇州東村,南寧 \
  --batch-size 20 \
  --workers 4 \
  --reset
```

The command reads the original `#漢字` TSV for the selected points, sends every
non-empty annotated row, and writes input JSONL, result JSONL, and final XLSX
files under `data/raw/extract/word_llm/`. It does not use `build.py` or the
mechanically generated `word/` files.
The script reads `DEEPSEEK_API_KEY` from the environment or the project-root
`.env` file, including the existing `deepseek-api-key` spelling.

- [x] **Step 2: Verify complete input coverage**

Read each point's `逐行结果` sheet and verify every selected point has one row
for every non-empty annotated source row, with no audio or mechanical candidate
fields sent to the model.

- [x] **Step 3: Verify the final deliverables**

Open each point's XLSX and verify it contains `词表` and `逐行结果` sheets.
Every generated word row must retain the original explanation and source
provenance; rows without a usable word must remain in `逐行结果`.
