import sqlite3
import os
import glob


def init_wal_mode_for_db(db_path: str):
    """
    为指定数据库立即启用 WAL 模式并强制生成 .db-wal 和 .db-shm 文件
    """
    if not os.path.exists(db_path):
        # 如果数据库不存在，创建一个空数据库
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS _init (id INTEGER)")
        conn.commit()
        conn.close()

    # 连接并启用 WAL
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    # 执行一次写操作，强制生成 .wal 和 .shm 文件
    conn.execute("CREATE TABLE IF NOT EXISTS _wal_init (id INTEGER)")
    conn.execute("INSERT INTO _wal_init (id) VALUES (1)")
    conn.commit()

    # 设置所有相关文件权限为 777
    wal_path = db_path + "-wal"
    shm_path = db_path + "-shm"
    try:
        os.chmod(db_path, 0o777)
        if os.path.exists(wal_path):
            os.chmod(wal_path, 0o777)
        if os.path.exists(shm_path):
            os.chmod(shm_path, 0o777)
        print(f"  权限已设置为 777")
    except Exception as e:
        print(f"  ⚠ 权限设置失败: {e}")

    # 不执行 checkpoint，保持 WAL 文件存在
    conn.close()

    print(f"✓ {db_path}")
    wal_path = db_path + "-wal"
    shm_path = db_path + "-shm"
    print(f"  - {wal_path}: {'存在' if os.path.exists(wal_path) else '不存在'}")
    print(f"  - {shm_path}: {'存在' if os.path.exists(shm_path) else '不存在'}")


def init_all_dbs_in_directory(directory: str):
    """
    为指定目录下所有 .db 文件启用 WAL 模式
    """
    db_files = glob.glob(os.path.join(directory, "*.db"))

    if not db_files:
        print(f"在 {directory} 目录下没有找到 .db 文件")
        return

    print(f"找到 {len(db_files)} 个数据库文件：\n")

    for db_path in db_files:
        init_wal_mode_for_db(db_path)
        print()


if __name__ == "__main__":
    # 示例 1: 初始化单个数据库
    # init_wal_mode_for_db("data/my.db")

    # 示例 2: 初始化整个目录的所有数据库
    init_all_dbs_in_directory("data")
