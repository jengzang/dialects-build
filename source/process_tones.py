import os
import re

import pandas as pd

from common.config import APPEND_PATH, PROCESSED_DATA_DIR, WRITE_ERROR_LOG


def extract_tone_maps(shortname: str, dialect_excel=APPEND_PATH):
    tone_shu = {}  # 陰平 ~ 陽去（[1] ~ [6]）
    tone_ru = {}  # 陰入、陽入（[7], [8]）
    tone_bian = {}  # 其他調、輕聲（[9], [10]）

    try:
        df = pd.read_excel(dialect_excel)
    except Exception as e:
        print(f"❗ 無法讀取 {dialect_excel}：{e}")
        return {}, {}, {}

    row = df[df["簡稱"] == shortname]
    if row.empty:
        print(f"⚠️ 未找到簡稱對應行：{shortname}")
        return {}, {}, {}

    row = row.iloc[0]

    for col in df.columns:
        if not isinstance(col, str):
            continue
        if "[" not in col or "]" not in col:
            continue

        match = re.search(r"\[(\d+)\]", col)
        if not match:
            continue
        base_code = match.group(1)  # 如欄位 [3]陰上 → base_code = "3"

        val = str(row[col]).strip()
        if not val or val.lower() == "nan":
            continue

        # 如果值中含有 [tag]，只依據 tag 標記建立映射
        if "[" in val and "]" in val:
            tagged = re.findall(r"\[(\d+[a-zA-Z]?)\](\d{1,3})", val)
            for tag_code, tone in tagged:
                if re.match(r"^[1-6][a-zA-Z]?$", tag_code):
                    tone_shu.setdefault(tone, []).append(tag_code)
                elif re.match(r"^[78][a-zA-Z]?$", tag_code):
                    tone_ru.setdefault(tone, []).append(tag_code)
                elif re.match(r"^([9]|10)[a-zA-Z]?$", tag_code):
                    tone_bian.setdefault(tone, []).append(tag_code)
        else:
            # fallback：無 tag → 根據欄位代碼建立映射
            tones = re.findall(r"(\d{1,3})", val)
            for tone in tones:
                col_num = int(base_code)
                if 1 <= col_num <= 6:
                    tone_shu.setdefault(tone, []).append(base_code)
                elif col_num in [7, 8]:
                    tone_ru.setdefault(tone, []).append(base_code)
                elif col_num in [9, 10]:
                    tone_bian.setdefault(tone, []).append(base_code)
    tone = {
        "shu": tone_shu,
        "ru": tone_ru,
        "bian": tone_bian
    }
    return tone


def convert_tones(tone: dict, shortname: str):
    tsv_file_path = os.path.join(PROCESSED_DATA_DIR, f"{shortname}.tsv")
    if not os.path.exists(tsv_file_path):
        print(f"错误：找不到文件 {tsv_file_path}")
        with open(WRITE_ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"❌ [{shortname}] 找不到文件 {tsv_file_path}\t【process_tones->convert_tones】\n")
        return

    tsv_df = pd.read_csv(tsv_file_path, sep="\t")

    if '#漢字' not in tsv_df.columns or '音標' not in tsv_df.columns:
        print("错误：文件缺少必要的 '#漢字' 或 '音標' 列！")
        with open(WRITE_ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"❌ [{shortname}] 缺少 #漢字 或 音標\t【process_tones->convert_tones】\n")
        return

    tone_shu = tone.get("shu", {})
    tone_ru = tone.get("ru", {})
    tone_bian = tone.get("bian", {})

    ru_initials = set("ptkʔˀᵖᵏᵗbdg")

    def match_tone(tail_tone, prev_char, tone_map):
        if tail_tone in tone_map:
            return tone_map[tail_tone][0]
        return None

    def replace_tone(ipa: str) -> str:
        match = re.search(r"([0-9¹²³⁴⁵⁶⁷⁸⁹⁰]{1,4})$", ipa)
        if not match:
            return ipa

        tail_tone = match.group(1)
        # 將上標數字轉為正常數字
        tail_tone = tail_tone.translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
        head = ipa[:-len(tail_tone)]
        prev_char = head[-1] if head else ""

        tone_num = None

        if prev_char in ru_initials:
            tone_num = match_tone(tail_tone, prev_char, tone_ru)
            if tone_num is None:
                tone_num = match_tone(tail_tone, prev_char, tone_bian)

        if tone_num is None:
            tone_num = match_tone(tail_tone, prev_char, tone_shu)

        if tone_num is None:
            tone_num = match_tone(tail_tone, prev_char, tone_bian)

        if tone_num is None:
            tone_num = match_tone(tail_tone, prev_char, tone_ru)

        if tone_num:
            new_ipa = head + tone_num
            # print(f"[DEBUG] 轉換：{ipa} → {new_ipa}")
            return new_ipa
        else:
            print(f"[DEBUG] 未匹配：{ipa}")
            with open(WRITE_ERROR_LOG, "a", encoding="utf-8") as f:
                f.write(f"⚠️ [{shortname}] 未匹配音標：{ipa}\t【process_tones->convert_tones】\n")
            return ipa  # ❗保留原音標

    # ✅ 直接修改原 "音標" 欄
    tsv_df["音標"] = tsv_df["音標"].apply(replace_tone)

    # ✅ 覆寫寫回原 tsv 文件
    tsv_df.to_csv(tsv_file_path, sep="\t", index=False)
    print(f"✅ 已更新音標列並覆寫：{tsv_file_path}")
    # ✅ 預覽輸出
    # print("✅ 轉換結果預覽（已覆寫原欄）：")
    # preview_cols = ["#漢字", "音標"]
    # if all(col in tsv_df.columns for col in preview_cols):
    # print(tsv_df[preview_cols].head(10))
    # else:
    #     print("⚠️ 欄位缺失，無法預覽。實際欄位為：", tsv_df.columns.tolist())
    return tsv_df


def tone_jyut2yindian(shortname: str):
    tsv_file_path = os.path.join(PROCESSED_DATA_DIR, f"{shortname}.tsv")
    if not os.path.exists(tsv_file_path):
        print(f"错误：找不到文件 {tsv_file_path}")
        with open(WRITE_ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"❌ [{shortname}] 找不到文件 {tsv_file_path}\t【process_tones->tone_jyut2yindian】\n")
        return

    tsv_df = pd.read_csv(tsv_file_path, sep="\t")

    if '#漢字' not in tsv_df.columns or '音標' not in tsv_df.columns:
        print("错误：文件缺少必要的 '#漢字' 或 '音標' 列！")
        with open(WRITE_ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"❌ [{shortname}] 缺少 #漢字 或 音標\t【process_tones->tone_jyut2yindian】\n")
        return

    ru_finals = set("ptkʔˀᵖᵏᵗ")
    error_logs = []

    def is_rusheng_final(ipa: str) -> bool:
        match = re.search(r"(.+?)([0-9]{1,2})$", ipa)
        if not match:
            return False
        ipa_body = match.group(1)
        return ipa_body and ipa_body[-1] in ru_finals

    def has_rusheng_with_4_or_10() -> bool:
        for ipa in tsv_df["音標"]:
            match = re.search(r"(.+?)([0-9]{1,2})$", str(ipa))
            if not match:
                continue
            ipa_body, tone = match.groups()
            if ipa_body and ipa_body[-1] in ru_finals and tone in {"4", "10"}:
                return True
        return False

    has_rusheng_4_10 = has_rusheng_with_4_or_10()

    def log_error(msg: str):
        full_msg = f"[{shortname}] {msg}"
        print(f"❌ {full_msg}")
        error_logs.append(f"❌ {full_msg}\t【process_tones->tone_jyut2yindian】")

    def convert_jyuttone(tone: str, is_rusheng: bool, ipa: str) -> str:
        match tone:
            case "1":
                return "7a" if is_rusheng else "1"
            case "2":
                if is_rusheng:
                    log_error(f"入聲尾卻使用非入聲調 2：{ipa}")
                    return ipa
                return "3"
            case "3":
                return "7b" if is_rusheng else "5"
            case "4":
                return "8b" if is_rusheng else "2"
            case "5":
                if is_rusheng:
                    log_error(f"入聲尾卻使用非入聲調 5：{ipa}")
                    return ipa
                return "4"
            case "6":
                if is_rusheng:
                    return "8a" if has_rusheng_4_10 else "8"
                return "6"
            case "7":
                if not is_rusheng:
                    log_error(f"非入聲尾卻使用入聲調 7：{ipa}")
                    return ipa
                return "7a"
            case "8":
                if not is_rusheng:
                    log_error(f"非入聲尾卻使用入聲調 8：{ipa}")
                    return ipa
                return "7b"
            case "9":
                if not is_rusheng:
                    log_error(f"非入聲尾卻使用入聲調 9：{ipa}")
                    return ipa
                return "8a" if has_rusheng_4_10 else "8"
            case "10":
                if not is_rusheng:
                    log_error(f"非入聲尾卻使用入聲調 10：{ipa}")
                    return ipa
                return "8b"
            case "0":
                return "9"
            case _:
                return tone

    def replace_tone(ipa: str) -> str:
        match = re.search(r"([0-9]{1,2})$", ipa)
        if not match:
            return ipa
        tone_num = match.group(1)
        rusheng = is_rusheng_final(ipa)
        new_tone = convert_jyuttone(tone_num, rusheng, ipa)
        if new_tone == ipa:
            return ipa  # 錯誤或無需轉換
        return re.sub(r"([0-9]{1,2})$", new_tone, ipa)

    # 處理音標欄
    tsv_df["音標"] = tsv_df["音標"].apply(replace_tone)

    # 保存回原 tsv 檔
    tsv_df.to_csv(tsv_file_path, sep="\t", index=False)
    print(f"✅ 已轉換 Jyutping 調號為 Yindian：{shortname}")

    # 輸出錯誤紀錄
    if error_logs:
        os.makedirs("data", exist_ok=True)
        with open(WRITE_ERROR_LOG, "a", encoding="utf-8") as f:
            f.write("\n".join(error_logs))
        print(f"⚠️ 錯誤紀錄已寫入：{WRITE_ERROR_LOG}（共 {len(error_logs)} 條）")

