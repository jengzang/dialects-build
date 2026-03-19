# build.py 的 append 參數詳解

## 🎯 核心差異

### ❌ **不給 append 參數（默認模式）**

```bash
python build.py -t needchars
# 或
python build.py -t needchars -u admin
```

**執行流程**：

1. **完全重建數據庫**
   ```python
   cursor.execute("DROP TABLE IF EXISTS dialects")  # 刪除整個表
   ```
   - 刪除 `dialects` 表的所有數據
   - 重新創建空表

2. **處理所有 TSV 文件**
   - 掃描所有方言點的 TSV 文件
   - 全部寫入數據庫
   - 處理所有方言點的多音字和註釋

3. **適用場景**
   - ✅ 首次建立數據庫
   - ✅ 需要完全重建數據
   - ✅ 數據結構有變化
   - ✅ 需要清理所有舊數據

### ✅ **給 append 參數（增量更新模式）**

```bash
python build.py -t needchars append
# 或
python build.py -t needchars append -u admin
```

**執行流程**：

1. **保留現有數據庫**
   ```python
   if not append:
       cursor.execute("DROP TABLE IF EXISTS dialects")  # 不執行
   ```
   - **不刪除** `dialects` 表
   - 保留所有現有數據

2. **讀取更新配置**
   ```python
   df_append = pd.read_excel(APPEND_PATH, sheet_name="檔案")
   update_rows = df_append[df_append['待更新'] == 1]
   valid_簡稱 = update_rows['簡稱'].dropna().unique().tolist()
   ```
   - 讀取：`data/dependency/jengzang補充.xlsx`
   - 工作表：`檔案`
   - 篩選：`待更新 == 1` 的行
   - 提取：這些行的 `簡稱` 欄位

3. **刪除指定方言點的舊數據**
   ```python
   for row in valid_簡稱:
       cursor.execute("DELETE FROM dialects WHERE 簡稱 = ?", (row,))
   ```
   - **只刪除**配置文件中指定的方言點
   - 其他方言點的數據保持不變

4. **只處理指定的 TSV 文件**
   ```python
   if append and tsv_name not in update_rows['簡稱'].values:
       print(f"跳過：{tsv_name} (不在待更新清單中)")
       continue
   ```
   - 只處理配置文件中指定的方言點
   - 跳過其他所有方言點

5. **適用場景**
   - ✅ 只更新部分方言點
   - ✅ 新增少量方言點
   - ✅ 修正特定方言點的數據
   - ✅ 節省處理時間

## 📊 詳細對比表

| 項目 | 不給 append | 給 append |
|------|------------|-----------|
| **數據庫操作** | 刪除整個表 | 保留現有表 |
| **處理範圍** | 所有方言點 | 僅指定方言點 |
| **處理時間** | 長（全部處理） | 短（部分處理） |
| **數據保留** | 全部重建 | 保留未更新的 |
| **配置文件** | 不需要 | 需要 Excel 配置 |
| **風險** | 低（全新數據） | 中（需確保配置正確） |

## 🔍 實際執行示例

### 場景 1：首次建立數據庫

```bash
# 處理所有方言點，建立完整數據庫
python build.py -t needchars -u admin
```

**結果**：
- 處理所有 TSV 文件（假設 2000+ 個方言點）
- 耗時：約 30-60 分鐘
- 數據庫：完整的方言數據

### 場景 2：只更新廣州、北京兩個方言點

**步驟 1**：編輯 `data/dependency/jengzang補充.xlsx`

| 簡稱 | 待更新 | 備註 |
|------|--------|------|
| 廣州 | 1      | 需要更新 |
| 北京 | 1      | 需要更新 |
| 上海 | 0      | 不更新 |
| 深圳 | 0      | 不更新 |

**步驟 2**：執行命令

```bash
python build.py -t needchars append -u admin
```

**結果**：
- 只處理廣州、北京的 TSV 文件
- 刪除數據庫中廣州、北京的舊數據
- 寫入廣州、北京的新數據
- 其他方言點（上海、深圳等）保持不變
- 耗時：約 1-2 分鐘

### 場景 3：新增一個方言點

**步驟 1**：添加新的 TSV 文件
- 將新方言點的 TSV 文件放入 `data/processed/` 或 `data/yindian/`

**步驟 2**：編輯配置文件

| 簡稱 | 待更新 | 備註 |
|------|--------|------|
| 新方言 | 1    | 新增 |

**步驟 3**：執行命令

```bash
python build.py -t needchars append -u admin
```

**結果**：
- 只處理新方言點
- 不影響現有數據
- 快速完成

## ⚠️ 注意事項

### 使用 append 模式時需要注意：

1. **配置文件必須正確**
   - 確保 `data/dependency/jengzang補充.xlsx` 存在
   - 確保有 `檔案` 工作表
   - 確保有 `簡稱` 和 `待更新` 欄位

2. **簡稱必須匹配**
   - Excel 中的 `簡稱` 必須與 TSV 文件名匹配
   - 大小寫敏感
   - 不能有多餘空格

3. **數據一致性**
   - append 模式會刪除指定方言點的所有舊數據
   - 確保新的 TSV 文件是完整的
   - 不要部分更新（會導致數據不完整）

4. **錯誤處理**
   ```python
   try:
       df_append = pd.read_excel(APPEND_PATH, sheet_name="檔案")
       update_rows = df_append[df_append['待更新'] == 1]
   except:
       print("读取 APPEND_PATH 文件失败，跳过筛选。")
   ```
   - 如果讀取配置文件失敗，會處理所有文件
   - 建議先測試配置文件是否正確

## 💡 最佳實踐

### 推薦工作流程

1. **日常更新（少量方言點）**
   ```bash
   # 使用 append 模式
   python build.py -t needchars append -u admin
   ```

2. **大規模更新（多個方言點）**
   ```bash
   # 使用 append 模式，但分批處理
   # 第一批：更新 10 個方言點
   python build.py -t needchars append -u admin
   # 第二批：更新另外 10 個方言點
   # 修改 Excel 配置後再次執行
   python build.py -t needchars append -u admin
   ```

3. **完全重建（定期維護）**
   ```bash
   # 不使用 append，完全重建
   python build.py -t needchars -u admin
   ```

### 性能對比

假設數據庫有 2000 個方言點：

| 操作 | 不給 append | 給 append (更新 10 個) |
|------|------------|----------------------|
| 處理文件數 | 2000 個 | 10 個 |
| 耗時 | 30-60 分鐘 | 1-2 分鐘 |
| 數據庫操作 | 刪除全部 + 寫入全部 | 刪除 10 個 + 寫入 10 個 |
| 風險 | 低 | 中（需確保配置正確） |

## 🎓 總結

**不給 append**：
- 🔄 完全重建
- ⏰ 耗時長
- ✅ 適合首次建立或大規模更新

**給 append**：
- ➕ 增量更新
- ⚡ 快速高效
- ✅ 適合日常維護和小規模更新
- ⚠️ 需要正確配置 Excel 文件

選擇哪種模式取決於你的需求：
- 需要完全重建？→ 不給 append
- 只更新少量方言點？→ 給 append
