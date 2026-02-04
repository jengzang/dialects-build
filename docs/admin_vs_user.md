# Admin vs User 模式數據庫分離說明

## 概述

本系統支持兩種數據庫模式：**Admin 模式**和 **User 模式**，用於管理不同範圍的方言數據。

## 數據庫文件

### Admin 模式
- `data/query_dialects_admin.db` - 方言查詢數據庫
- `data/dialects_all_admin.db` - 完整方言數據庫

### User 模式
- `data/query_dialects_user.db` - 方言查詢數據庫
- `data/dialects_all_user.db` - 用戶方言數據庫

## 數據來源

### Admin 模式
- 掃描 `data/processed/` 目錄中的**所有** TSV 文件
- 掃描 `data/yindian/` 目錄中的**所有** TSV 文件
- 如果有重名文件，系統會提示用戶選擇

### User 模式
- 掃描 `data/processed/` 目錄中 **isUser=1** 的 TSV 文件
- 掃描 `data/yindian/` 目錄中的**所有** TSV 文件
- 如果有重名文件，系統會提示用戶選擇

## isUser 列配置

在 `data/dependency/jengzang補充.xlsx` 文件的「檔案」工作表中，需要添加 `isUser` 列：

- `isUser=1` 或 `isUser='1'` 或 `isUser=True`：該方言點會被包含在 User 模式中
- `isUser=0` 或空值：該方言點僅在 Admin 模式中

## 元數據選擇規則

系統根據 TSV 文件的來源自動選擇對應的元數據：

### TSV 來自 yindian 目錄
1. 優先使用 `漢字音典字表檔案（長期更新）.xlsx` 中的元數據
2. 如果 HAN 文件中沒有該方言點，則使用 `jengzang補充.xlsx` 中的元數據
3. 如果兩個文件都沒有，跳過該方言點

### TSV 來自 processed 目錄
1. 優先使用 `jengzang補充.xlsx` 中的元數據
2. 如果 APPEND 文件中沒有該方言點，則使用 `漢字音典字表檔案（長期更新）.xlsx` 中的元數據
3. 如果兩個文件都沒有，跳過該方言點

## 交互式衝突解決

當在 `yindian/` 和 `processed/` 目錄中發現同名 TSV 文件時，系統會顯示：

```
⚠️  發現重名文件：廣州.tsv
1. data/yindian/廣州.tsv (1234 行)
2. data/processed/廣州.tsv (5678 行)
請選擇 (1/2):
```

用戶需要輸入 `1` 或 `2` 來選擇使用哪個文件。

## 使用方法

### 構建 Admin 模式數據庫

```bash
# 僅構建查詢數據庫
python build.py -u admin -t query

# 構建完整數據庫（包含方言數據）
python build.py -u admin

# 構建並同步存儲標記
python build.py -u admin -t sync
```

### 構建 User 模式數據庫

```bash
# 僅構建查詢數據庫
python build.py -u user -t query

# 構建完整數據庫（包含方言數據）
python build.py -u user

# 構建並同步存儲標記
python build.py -u user -t sync
```

## 注意事項

1. **isUser 列必須存在**：確保 `jengzang補充.xlsx` 中有 `isUser` 列
2. **繁簡轉換**：系統會自動處理繁簡體匹配，TSV 文件名和 Excel 簡稱可以是繁體或簡體
3. **數據一致性**：如果 TSV 存在但兩個 Excel 都沒有元數據，該方言點會被跳過
4. **交互式輸入**：衝突解決需要用戶手動輸入，建議在批處理前先解決所有衝突

## 向後兼容

為了保持向後兼容，`common/config.py` 中的默認路徑指向 Admin 模式：

```python
QUERY_DB_PATH = QUERY_DB_ADMIN_PATH
DIALECTS_DB_PATH = DIALECTS_DB_ADMIN_PATH
```

這意味著不指定模式的舊代碼會默認使用 Admin 模式數據庫。
