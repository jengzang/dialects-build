import os
import tkinter as tk
from tkinter import filedialog

from source.format_convert import process_音典
from source.get_new import extract_all_from_files

# 直接開始執行
root = tk.Tk()
root.withdraw()

file_paths = filedialog.askopenfilenames(
    title="選擇多個 Excel 文件",
    filetypes=[("Excel Files", "*.xlsx")]
)

results = []

for file in file_paths:
    output_path = os.path.splitext(file)[0] + ".tsv"

    # 調用你已寫好的函數
    process_音典(file, output_path=output_path)
    result = extract_all_from_files(output_path)

    results.append(result)

# 現在 results 是一個 DataFrame 列表
print(f"已處理 {len(results)} 個檔案")
