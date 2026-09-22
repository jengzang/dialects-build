# 音典特殊记录提取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为音典拉取流程增加按地点分文件的方框字表和带注释记录提取功能。

**Architecture:** 保持 `source/mcp_export.py` 只负责拉取文件，新增 `source/extract_yindian.py` 负责扫描和筛选 TSV。`build.py` 解析 `-v/--vocabulary` 与 `-n/--note`，在拉取后或独立运行时调用提取器；输出目录和输入目录通过 `common.config` 常量集中定义。

**Tech Stack:** Python、argparse、标准库 `csv`/`shutil`/`pathlib`、unittest/pytest。

---

### Task 1: Add extraction behavior tests

**Files:**
- Create: `tests/test_extract_yindian.py`
- Modify: `tests/test_build_mcp_mode.py`

- [ ] **Step 1: Write the failing extractor test**

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

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
pytest -q tests/test_extract_yindian.py
```

Expected: FAIL because `source.extract_yindian` and `extract_yindian_records` do not yet exist.

- [ ] **Step 3: Add CLI tests**

Extend `tests/test_build_mcp_mode.py` to assert:

```python
args = parser.parse_args(["-v", "-n"])
assert args.vocabulary is True
assert args.note is True
```

Also invoke `build.main()` with only `vocabulary=True` while mocking the extractor and `write_to_sql`; assert the extractor is called and the default database writer is not called.

- [ ] **Step 4: Run the focused CLI test and verify the expected failure**

Run:

```bash
pytest -q tests/test_build_mcp_mode.py
```

Expected: FAIL because the parser and `main()` do not yet define or dispatch the new flags.

### Task 2: Implement per-location extraction

**Files:**
- Modify: `common/config.py`
- Create: `source/extract_yindian.py`

- [ ] **Step 1: Add output path constants**

Add `EXTRACT_YINDIAN_DIR`, `VOCABULARY_EXTRACT_DIR`, and `NOTE_EXTRACT_DIR` under the existing MCP pull path constants:

```python
EXTRACT_YINDIAN_DIR = Path(BASE_DIR) / "data" / "raw" / "extract"
VOCABULARY_EXTRACT_DIR = EXTRACT_YINDIAN_DIR / "vocabulary"
NOTE_EXTRACT_DIR = EXTRACT_YINDIAN_DIR / "note"
```

- [ ] **Step 2: Implement the extractor**

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

- [ ] **Step 3: Run the extractor tests and verify they pass**

Run:

```bash
pytest -q tests/test_extract_yindian.py
```

Expected: PASS.

### Task 3: Wire the flags into `build.py`

**Files:**
- Modify: `build.py`
- Modify: `tests/test_build_mcp_mode.py`

- [ ] **Step 1: Add parser options**

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

- [ ] **Step 2: Dispatch extraction at the correct point**

After `export_mcp_assets()` returns, call `extract_yindian_records()` when either flag is enabled. When no MCP mode is supplied, call it against the existing pull directory. Use `getattr()` for the new fields in `main()` so existing programmatic callers without those attributes remain compatible.

- [ ] **Step 3: Prevent accidental default database writes**

Update the default-write predicate so `python build.py -v`, `python build.py -n`, and `python build.py -v -n` perform extraction only and do not call `write_to_sql()`.

- [ ] **Step 4: Run the CLI tests**

Run:

```bash
pytest -q tests/test_build_mcp_mode.py
```

Expected: PASS.

### Task 4: Update user documentation

**Files:**
- Modify: `readme.md`

- [ ] **Step 1: Document the two flags**

Add both flags to the command-line parameter table, explain the two output directories, and add examples:

```bash
python build.py -m diff -v
python build.py -m diff -n
python build.py -m diff -v -n
python build.py -v
```

- [ ] **Step 2: Run the complete test suite**

Run:

```bash
pytest -q
```

Expected: all existing and new tests pass.

- [ ] **Step 3: Run a real sample extraction**

Run:

```bash
python build.py -v -n
```

Verify that `data/raw/extract/vocabulary/` and `data/raw/extract/note/` contain separate per-location TSV files and that `data/raw/pull_yindian/` is unchanged.
