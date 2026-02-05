#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理 yindian 和 processed 目錄下的重複文件
找出完全相同的文件（包括修改時間），並可選擇刪除
"""

import os
import filecmp
from pathlib import Path
from datetime import datetime
import sys

def get_file_info(filepath):
    """獲取文件信息"""
    stat = os.stat(filepath)
    return {
        'size': stat.st_size,
        'mtime': stat.st_mtime,
        'path': filepath
    }

def compare_files_exact(file1, file2):
    """
    比較兩個文件是否完全相同（內容和修改時間）

    Returns:
        'identical': 完全相同（內容和時間）
        'same_content': 內容相同但時間不同
        'different': 內容不同
    """
    # 先比較文件大小
    stat1 = os.stat(file1)
    stat2 = os.stat(file2)

    if stat1.st_size != stat2.st_size:
        return 'different'

    # 比較內容
    if not filecmp.cmp(file1, file2, shallow=False):
        return 'different'

    # 內容相同，檢查修改時間
    if abs(stat1.st_mtime - stat2.st_mtime) < 1:  # 允許1秒誤差
        return 'identical'
    else:
        return 'same_content'

def find_duplicates(yindian_dir, processed_dir):
    """
    找出兩個目錄下的重複文件

    Returns:
        identical_files: 完全相同的文件列表
        same_name_diff_content: 同名但內容不同的文件列表
        same_content_diff_time: 內容相同但時間不同的文件列表
    """
    identical_files = []
    same_name_diff_content = []
    same_content_diff_time = []

    # 獲取 yindian 目錄下的所有 TSV 文件
    yindian_files = {}
    for file in Path(yindian_dir).glob('*.tsv'):
        if file.is_file():
            yindian_files[file.name] = file

    # 獲取 processed 目錄下的所有 TSV 文件
    processed_files = {}
    for file in Path(processed_dir).glob('*.tsv'):
        if file.is_file():
            processed_files[file.name] = file

    # 比較同名文件
    common_names = set(yindian_files.keys()) & set(processed_files.keys())

    for filename in sorted(common_names):
        yindian_file = yindian_files[filename]
        processed_file = processed_files[filename]

        result = compare_files_exact(yindian_file, processed_file)

        if result == 'identical':
            identical_files.append({
                'name': filename,
                'yindian': yindian_file,
                'processed': processed_file
            })
        elif result == 'same_content':
            same_content_diff_time.append({
                'name': filename,
                'yindian': yindian_file,
                'processed': processed_file
            })
        elif result == 'different':
            same_name_diff_content.append({
                'name': filename,
                'yindian': yindian_file,
                'processed': processed_file
            })

    return identical_files, same_name_diff_content, same_content_diff_time

def print_report(identical_files, same_name_diff_content, same_content_diff_time):
    """打印比較報告"""
    print("=" * 80)
    print("yindian 和 processed 目錄重複文件檢查報告")
    print("=" * 80)
    print()

    # 1. 完全相同的文件
    if identical_files:
        print(f"[完全相同的文件] ({len(identical_files)} 個)")
        print("這些文件的內容和修改時間都完全相同")
        print("-" * 80)
        for item in identical_files:
            yindian_info = get_file_info(item['yindian'])
            print(f"  * {item['name']}")
            print(f"    大小: {yindian_info['size']:,} bytes | "
                  f"修改時間: {datetime.fromtimestamp(yindian_info['mtime']).strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    else:
        print("[完全相同的文件] 無")
        print()

    # 2. 內容相同但時間不同的文件
    if same_content_diff_time:
        print(f"[內容相同但時間不同的文件] ({len(same_content_diff_time)} 個)")
        print("-" * 80)
        for item in same_content_diff_time:
            yindian_info = get_file_info(item['yindian'])
            processed_info = get_file_info(item['processed'])
            print(f"  * {item['name']}")
            print(f"    yindian:   {datetime.fromtimestamp(yindian_info['mtime']).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    processed: {datetime.fromtimestamp(processed_info['mtime']).strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    else:
        print("[內容相同但時間不同的文件] 無")
        print()

    # 3. 同名但內容不同的文件
    if same_name_diff_content:
        print(f"[同名但內容不同的文件] ({len(same_name_diff_content)} 個)")
        print("警告：這些文件名相同但內容不同，請手動檢查")
        print("-" * 80)
        for item in same_name_diff_content:
            yindian_info = get_file_info(item['yindian'])
            processed_info = get_file_info(item['processed'])
            print(f"  * {item['name']}")
            print(f"    yindian:   大小={yindian_info['size']:>8,} bytes | "
                  f"時間={datetime.fromtimestamp(yindian_info['mtime']).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    processed: 大小={processed_info['size']:>8,} bytes | "
                  f"時間={datetime.fromtimestamp(processed_info['mtime']).strftime('%Y-%m-%d %H:%M:%S')}")
        print()
    else:
        print("[同名但內容不同的文件] 無")
        print()

    print("=" * 80)

def delete_files(file_list):
    """刪除文件列表中的文件"""
    deleted_count = 0
    failed_count = 0

    for item in file_list:
        try:
            os.remove(item['yindian'])
            print(f"[已刪除] {item['name']}")
            deleted_count += 1
        except Exception as e:
            print(f"[刪除失敗] {item['name']}: {e}")
            failed_count += 1

    return deleted_count, failed_count

def run_cleanup(auto_confirm=False, export_file=None):
    """
    運行清理功能

    Args:
        auto_confirm: 是否自動確認刪除（用於測試）
        export_file: 導出報告文件路徑
    """
    # 如果指定了導出文件，重定向輸出
    original_stdout = sys.stdout
    if export_file:
        sys.stdout = open(export_file, 'w', encoding='utf-8')

    try:
        # 設置目錄路徑
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        yindian_dir = project_root / 'data' / 'yindian'
        processed_dir = project_root / 'data' / 'processed'

        # 檢查目錄是否存在
        if not yindian_dir.exists():
            print(f"[錯誤] 找不到目錄: {yindian_dir}")
            sys.exit(1)

        if not processed_dir.exists():
            print(f"[錯誤] 找不到目錄: {processed_dir}")
            sys.exit(1)

        # 查找重複文件
        print("正在掃描文件...")
        identical_files, same_name_diff_content, same_content_diff_time = find_duplicates(
            yindian_dir, processed_dir
        )

        # 打印報告
        print_report(identical_files, same_name_diff_content, same_content_diff_time)

        # 如果有完全相同的文件，詢問是否刪除
        if identical_files:
            print(f"\n發現 {len(identical_files)} 個完全相同的文件（內容和時間都相同）")
            print(f"這些文件將從 yindian 目錄中刪除（processed 目錄保留）")
            print()

            if not auto_confirm and not export_file:
                response = input("是否確認刪除？(yes/no): ").strip().lower()
            else:
                response = 'yes' if auto_confirm else 'no'
                if export_file:
                    print("（導出模式：不執行刪除操作）")

            if response in ['yes', 'y'] and not export_file:
                print("\n開始刪除文件...")
                deleted, failed = delete_files(identical_files)
                print(f"\n刪除完成：成功 {deleted} 個，失敗 {failed} 個")
            else:
                print("\n已取消刪除操作")
        else:
            print("沒有發現完全相同的文件，無需刪除")

    finally:
        if export_file:
            sys.stdout.close()
            sys.stdout = original_stdout
            print(f"[OK] 報告已導出到: {export_file}")

def main():
    """主函數"""
    import argparse

    parser = argparse.ArgumentParser(
        description="清理 yindian 和 processed 目錄下的重複文件"
    )
    parser.add_argument(
        '--auto-confirm',
        action='store_true',
        help='自動確認刪除，不詢問用戶'
    )

    args = parser.parse_args()
    run_cleanup(auto_confirm=args.auto_confirm)

if __name__ == '__main__':
    main()
