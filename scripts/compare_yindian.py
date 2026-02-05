#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
比較 yindian 和 raw/pull_yindian 目錄下的文件差異
使用方法：
    python scripts/compare_yindian.py
    python scripts/compare_yindian.py --detail  # 顯示更詳細的信息
    python scripts/compare_yindian.py --export output.txt  # 導出到文件
"""

import os
import argparse
from pathlib import Path
from datetime import datetime
import sys

def get_file_info(filepath):
    """獲取文件信息"""
    stat = os.stat(filepath)
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = sum(1 for _ in f)

    return {
        'size': stat.st_size,
        'lines': lines,
        'mtime': datetime.fromtimestamp(stat.st_mtime),
        'path': filepath
    }

def compare_directories(dir1, dir2):
    """比較兩個目錄"""
    # 獲取所有文件名（不包括路徑）
    dir1_files = {}
    dir2_files = {}

    # 掃描第一個目錄
    for file in Path(dir1).glob('*'):
        if file.is_file() and file.suffix == '.tsv':
            dir1_files[file.name] = file

    # 掃描第二個目錄
    for file in Path(dir2).glob('*'):
        if file.is_file() and file.suffix == '.tsv':
            dir2_files[file.name] = file

    # 找出差異
    only_in_dir1 = set(dir1_files.keys()) - set(dir2_files.keys())
    only_in_dir2 = set(dir2_files.keys()) - set(dir1_files.keys())
    common_files = set(dir1_files.keys()) & set(dir2_files.keys())

    return dir1_files, dir2_files, only_in_dir1, only_in_dir2, common_files

def print_report(yindian_files, pull_files, only_yindian, only_pull, common, detail=False, output_file=None):
    """打印比較報告"""
    # 如果指定了輸出文件，重定向輸出
    original_stdout = sys.stdout
    if output_file:
        sys.stdout = open(output_file, 'w', encoding='utf-8')

    try:
        print("=" * 80)
        print("文件比較報告：yindian vs raw/pull_yindian")
        print("=" * 80)
        print()

        # 統計信息
        print(f"[統計摘要]")
        print(f"{'-' * 80}")
        print(f"yindian 目錄文件總數: {len(yindian_files)}")
        print(f"pull_yindian 目錄文件總數: {len(pull_files)}")
        print(f"共同文件數: {len(common)}")
        print(f"僅在 yindian 中的文件數: {len(only_yindian)}")
        print(f"僅在 pull_yindian 中的文件數: {len(only_pull)}")
        print()

        # 1. 僅在 yindian 中的文件
        if only_yindian:
            print(f"[僅在 yindian 目錄中的文件] ({len(only_yindian)} 個)")
            print(f"{'-' * 80}")
            for filename in sorted(only_yindian):
                filepath = yindian_files[filename]
                if detail:
                    info = get_file_info(filepath)
                    print(f"  * {filename}")
                    print(f"    行數: {info['lines']:,} | 大小: {info['size']:,} bytes | "
                          f"修改時間: {info['mtime'].strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"  * {filename}")
            print()
        else:
            print(f"[OK] 沒有僅在 yindian 中的文件")
            print()

        # 2. 僅在 pull_yindian 中的文件
        if only_pull:
            print(f"[僅在 pull_yindian 目錄中的文件] ({len(only_pull)} 個)")
            print(f"{'-' * 80}")
            for filename in sorted(only_pull):
                filepath = pull_files[filename]
                if detail:
                    info = get_file_info(filepath)
                    print(f"  * {filename}")
                    print(f"    行數: {info['lines']:,} | 大小: {info['size']:,} bytes | "
                          f"修改時間: {info['mtime'].strftime('%Y-%m-%d %H:%M:%S')}")
                else:
                    print(f"  * {filename}")
            print()
        else:
            print(f"[OK] 沒有僅在 pull_yindian 中的文件")
            print()

        # 3. 共同文件的差異比較
        if common:
            print(f"[共同文件的差異比較] ({len(common)} 個)")
            print(f"{'-' * 80}")

            differences = []
            identical = []

            for filename in sorted(common):
                yindian_info = get_file_info(yindian_files[filename])
                pull_info = get_file_info(pull_files[filename])

                # 檢查是否有差異
                has_diff = (
                    yindian_info['lines'] != pull_info['lines'] or
                    yindian_info['size'] != pull_info['size']
                )

                if has_diff:
                    differences.append({
                        'filename': filename,
                        'yindian': yindian_info,
                        'pull': pull_info
                    })
                else:
                    identical.append(filename)

            # 顯示有差異的文件
            if differences:
                print(f"\n[!] 有差異的文件 ({len(differences)} 個):")
                print()
                for item in differences:
                    filename = item['filename']
                    y_info = item['yindian']
                    p_info = item['pull']

                    print(f"  >> {filename}")
                    print(f"     yindian:      行數={y_info['lines']:>6,} | "
                          f"大小={y_info['size']:>8,} bytes | "
                          f"時間={y_info['mtime'].strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"     pull_yindian: 行數={p_info['lines']:>6,} | "
                          f"大小={p_info['size']:>8,} bytes | "
                          f"時間={p_info['mtime'].strftime('%Y-%m-%d %H:%M:%S')}")

                    # 計算差異
                    line_diff = y_info['lines'] - p_info['lines']
                    size_diff = y_info['size'] - p_info['size']
                    time_diff = (y_info['mtime'] - p_info['mtime']).total_seconds()

                    print(f"     差異:         行數差={line_diff:+,} | "
                          f"大小差={size_diff:+,} bytes | "
                          f"時間差={time_diff:+.0f} 秒")
                    print()

            # 顯示完全相同的文件
            if identical:
                if detail:
                    print(f"\n[OK] 完全相同的文件 ({len(identical)} 個):")
                    print(f"{'-' * 80}")
                    # 分行顯示，每行5個
                    for i in range(0, len(identical), 5):
                        batch = identical[i:i+5]
                        print(f"  {', '.join(batch)}")
                    print()
                else:
                    print(f"\n[OK] 完全相同的文件: {len(identical)} 個")
                    print()

        print("=" * 80)
        print("比較完成！")
        print("=" * 80)

    finally:
        if output_file:
            sys.stdout.close()
            sys.stdout = original_stdout
            print(f"[OK] 報告已導出到: {output_file}")

def run_comparison(detail=False, export_file=None):
    """
    運行比較功能的核心函數

    Args:
        detail: 是否顯示詳細信息
        export_file: 導出文件路徑（可選）
    """
    # 設置目錄路徑（相對於項目根目錄）
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    yindian_dir = project_root / 'data' / 'yindian'
    pull_dir = project_root / 'data' / 'raw' / 'pull_yindian'

    # 檢查目錄是否存在
    if not yindian_dir.exists():
        print(f"[錯誤] 找不到目錄 {yindian_dir}")
        sys.exit(1)

    if not pull_dir.exists():
        print(f"[錯誤] 找不到目錄 {pull_dir}")
        sys.exit(1)

    # 比較目錄
    yindian_files, pull_files, only_yindian, only_pull, common = compare_directories(
        yindian_dir, pull_dir
    )

    # 打印報告
    print_report(
        yindian_files, pull_files, only_yindian, only_pull, common,
        detail=detail,
        output_file=export_file
    )

def main():
    """主函數"""
    parser = argparse.ArgumentParser(
        description="比較 yindian 和 raw/pull_yindian 目錄下的文件差異",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例：
  python scripts/compare_yindian.py                    # 基本比較
  python scripts/compare_yindian.py --detail           # 顯示詳細信息
  python scripts/compare_yindian.py --export report.txt  # 導出到文件
  python scripts/compare_yindian.py -d -e report.txt   # 詳細信息並導出
        """
    )

    parser.add_argument(
        '-d', '--detail',
        action='store_true',
        help='顯示詳細的文件信息（行數、大小、時間）'
    )

    parser.add_argument(
        '-e', '--export',
        type=str,
        metavar='FILE',
        help='將報告導出到指定文件'
    )

    args = parser.parse_args()
    run_comparison(detail=args.detail, export_file=args.export)

if __name__ == '__main__':
    main()
