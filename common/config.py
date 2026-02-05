import os
import socket

# ============ 路徑 =================
# 計算專案根目錄路徑
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# database路徑依賴
QUERY_DB_PATH = os.path.join(BASE_DIR, "data", "query_dialects.db")
DIALECTS_DB_PATH = os.path.join(BASE_DIR, "data", "dialects_all.db")
CHARACTERS_DB_PATH = os.path.join(BASE_DIR, "data", "characters.db")
SUPPLE_DB_PATH = os.path.join(BASE_DIR, "data", "supplements.db")
SUPPLE_DB_URL = f"sqlite:///{SUPPLE_DB_PATH}"

# 字表寫入SQL路徑依賴
APPEND_PATH = os.path.join(BASE_DIR,  "data", "dependency", "jengzang補充.xlsx")
HAN_PATH = os.path.join(BASE_DIR,  "data", "dependency", "漢字音典字表檔案（長期更新）.xlsx")
PHO_TABLE_PATH = os.path.join(BASE_DIR,  "data", "dependency", "聲韻.xlsx")
RAW_DATA_DIR = os.path.join(BASE_DIR,  "data", "raw")
PROCESSED_DATA_DIR = os.path.join(BASE_DIR,  "data", "processed")
YINDIAN_DATA_DIR = os.path.join(BASE_DIR,  "data", "yindian")
UPDATE_DATA_DIR = os.path.join(BASE_DIR, "data", "raw", "pull_yindian")

# 通用路徑依賴
ZHENGZI_PATH = os.path.join(BASE_DIR, "data", "dependency", "正字.tsv")
MULCODECHAR_PATH = os.path.join(BASE_DIR, "data", "dependency", "mulcodechar.dt")

# 字表處理路徑依賴
MISSING_DATA_LOG = os.path.join(BASE_DIR, "logs", "缺資料.txt")
WRITE_INFO_LOG = os.path.join(BASE_DIR, "logs", "write.txt")
WRITE_ERROR_LOG = os.path.join(BASE_DIR, "logs", "write_error.txt")

# Admin 模式數據庫路徑
QUERY_DB_ADMIN_PATH = os.path.join(BASE_DIR, "data", "query_admin.db")
DIALECTS_DB_ADMIN_PATH = os.path.join(BASE_DIR, "data", "dialects_admin.db")

# User 模式數據庫路徑
QUERY_DB_USER_PATH = os.path.join(BASE_DIR, "data", "query_user.db")
DIALECTS_DB_USER_PATH = os.path.join(BASE_DIR, "data", "dialects_user.db")

# 保持向後兼容（默認指向 admin）
QUERY_DB_PATH = QUERY_DB_ADMIN_PATH
DIALECTS_DB_PATH = DIALECTS_DB_ADMIN_PATH

