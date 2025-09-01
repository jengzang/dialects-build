#  此腳本用來運行scripts路徑下諸多不同功能的程序
from scripts.check.checks import check_pro
from scripts.jyut2ipa.replace import jyut2ipa
from scripts.merge.wordsheet_merge import merge_main
import argparse

def main(TYPE):
    if TYPE == 'CHECK':
        # 檢查字表格式及錯字
        MODE = 'only'
        check_pro(MODE)
    elif TYPE == 'jyut':
        jyut2ipa()
    elif TYPE == 'MERGE':
        merge_main()
    else:
        print(f"未知的 TYPE：{TYPE}，請使用 CHECK、jyut 或 MERGE。")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='處理字表的工具，可選擇檢查字表、轉換 IPA 或合併字表。'
    )
    parser.add_argument(
        '--type', '-t',
        type=str,
        required=True,
        choices=['CHECK', 'jyut', 'MERGE'],
        help='選擇要執行的功能：CHECK（檢查字表）、jyut（粵拼轉 IPA）、MERGE（合併字表）'
    )

    args = parser.parse_args()
    main(args.type)



