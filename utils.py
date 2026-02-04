#  此腳本用來運行scripts路徑下諸多不同功能的程序
import argparse

def main(TYPE):
    if TYPE == 'CHECK':
        # 檢查字表格式及錯字
        from scripts.check.checks import check_pro
        MODE = 'only'
        check_pro(MODE)
    elif TYPE == 'jyut':
        from scripts.jyut2ipa.replace import jyut2ipa
        jyut2ipa()
    elif TYPE == 'MERGE':
        from scripts.merge.wordsheet_merge import merge_main
        merge_main()
    elif TYPE == 'COMPARE':
        # 比較 yindian 和 pull_yindian 目錄的文件差異
        from scripts.compare_yindian import run_comparison
        run_comparison(detail=True, export_file='data/yindian_comparison_report.txt')
    elif TYPE == 'CLEANUP':
        # 清理 yindian 和 processed 目錄下的重複文件
        from scripts.cleanup_duplicates import run_cleanup
        run_cleanup(auto_confirm=False, export_file='data/cleanup_report.txt')
    else:
        print(f"未知的 TYPE：{TYPE}，請使用 CHECK、jyut、MERGE、COMPARE 或 CLEANUP。")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='處理字表的工具，可選擇檢查字表、轉換 IPA、合併字表、比較文件或清理重複文件。'
    )
    parser.add_argument(
        '--type', '-t',
        type=str,
        required=True,
        choices=['CHECK', 'jyut', 'MERGE', 'COMPARE', 'CLEANUP'],
        help='選擇要執行的功能：CHECK（檢查字表）、jyut（粵拼轉 IPA）、MERGE（合併字表）、COMPARE（比較 yindian 文件）、CLEANUP（清理重複文件）'
    )

    args = parser.parse_args()
    main(args.type)



