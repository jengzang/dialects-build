import pandas as pd
import re

from common.constants import replace_data


def build_replace_table():
    return pd.DataFrame(replace_data, columns=["to_replace", "replacement", "condition"]).astype(str)


def process_yutping_file(filepath, replace_df, convert_tone=True, debug=True):
    # === 載入原始 Excel ===
    df = pd.read_excel(filepath, dtype=str, keep_default_na=False)
    # === 自動識別粵拼欄位 ===
    column_candidates = ['粤拼', '粵拼', '粤拼_程序更改', '粵拼_程序更改', 'jyut']
    match_column = None
    for col in df.columns:
        for target in column_candidates:
            if target in col:
                match_column = col
                break
        if match_column:
            break

    if not match_column:
        raise ValueError(f"❌ 找不到有效的粵拼欄位，請確認欄位名稱為：{column_candidates} 中之一")

    if debug:
        print(f"✅ 使用粵拼欄位: {match_column}")

    if debug:
        print(f"✅ 讀取檔案: {filepath} 共 {len(df)} 條")

    vowels = set('aeuioyr')

    def clean_and_extract_notes_fixed(text):
        if not text:
            return "", ""
        symbols = re.findall(r'[？?＊*]', text)
        chinese = re.findall(r'[\u4e00-\u9fa5]', text)
        notes = ''.join([c for c in chinese if c != '或'] + symbols)
        cleaned = re.sub(r'[？?＊*]', '', text)
        cleaned = ''.join(c for c in cleaned if c not in chinese or c == '或')
        return cleaned, notes

    def split_pinyin(pinyin):
        initial = final = tone = medial = coda = ''
        for ch in pinyin:
            if ch.isdigit():
                tone += ch
            else:
                if tone:
                    final += ch
                else:
                    initial += ch
        for i, ch in enumerate(initial):
            if ch in vowels:
                final = initial[i:] + final
                initial = initial[:i]
                break
        else:
            if initial.endswith(('ng', 'n', 'm')):
                final = initial[-2:] + final if initial.endswith('ng') else initial[-1:] + final
                initial = initial[:-2] if initial.endswith('ng') else initial[:-1]
        if final in ['ng', 'n', 'm']:
            medial = final
            coda = ""
        elif len(final) == 1 and final[0] in vowels:
            medial = final
            coda = ""
        elif len(final) > 1:
            if final[-1] in 'iu' and len([char for char in final if char in vowels]) > 1:
                medial = final[:-1]
                coda = final[-1]
            else:
                medial = "".join([char for char in final if char in vowels])
                coda = "".join([char for char in final if char not in vowels])
        return initial, final, tone, medial, coda

    def replace(component, condition):
        if not component:
            return ''
        sorted_df = replace_df[replace_df['condition'] == condition].sort_values(
            by='to_replace', key=lambda x: x.str.len(), ascending=False)
        for _, row in sorted_df.iterrows():
            if row['to_replace'] in component:
                result = component.replace(row['to_replace'], row['replacement'])
                if debug:
                    print(f"  [{condition}] 替换: {component} → {result}")
                return result
        if debug:
            print(f"  [{condition}] 無替換: {component}")
        return component

    def process_yutping(text):
        if not text:
            return pd.Series([""] * 11)

        text_cleaned, notes = clean_and_extract_notes_fixed(text)
        if debug:
            print(f"\n🎯 原始: {text} → 清理: {text_cleaned} | 注釋: {notes}")
        parts = re.split(r'(或|/|\||\\|;)', text_cleaned)
        if debug:
            print(f"🧩 分段: {parts}")

        fields = {k: [] for k in
                  ['声母', '韵母', '音调', '韵腹', '韵尾', '声母IPA', '韵腹IPA', '韵尾IPA', '音调IPA', 'IPA']}

        for part in parts:
            if part in ['或', '/', '|', '\\', ';']:
                for key in fields:
                    fields[key].append(part)
            elif part.strip():
                ini, fin, tone, med, coda = split_pinyin(part)
                if debug:
                    print(f"🔍 拆分: {part} => 声母: {ini}, 韵母: {fin}, 音调: {tone}, 韵腹: {med}, 韵尾: {coda}")

                ini_ipa = replace(ini, 'sm') or 'ʔ'
                if not ini_ipa.strip():
                    ini_ipa = 'ʔ'
                if med in ['ng', 'n', 'm']:
                    if debug:
                        print("  ✅ 特例: ng/n/m 韵腹 → 使用 wm")
                    med_ipa = replace(med, 'wm')
                else:
                    med_ipa = replace(med, 'wf')
                coda_ipa = replace(coda, 'wm')
                tone_ipa = replace(tone, 'jd') if convert_tone else tone
                ipa = ini_ipa + med_ipa + coda_ipa + tone_ipa

                fields['声母'].append(ini)
                fields['韵母'].append(fin)
                fields['音调'].append(tone)
                fields['韵腹'].append(med)
                fields['韵尾'].append(coda)
                fields['声母IPA'].append(ini_ipa)
                fields['韵腹IPA'].append(med_ipa)
                fields['韵尾IPA'].append(coda_ipa)
                fields['音调IPA'].append(tone_ipa)
                fields['IPA'].append(ipa)

        def conditional_join(parts):
            valid = [p for p in parts if p not in ['或', '/', '|', '\\', ';'] and p.strip()]
            if len(valid) == 0:
                return ''
            if len(set(valid)) == 1:
                return valid[0]
            return ''.join(parts)

        row_result = [conditional_join(fields[key]) for key in [
            '声母', '韵母', '音调', '韵腹', '韵尾',
            '声母IPA', '韵腹IPA', '韵尾IPA', '音调IPA', 'IPA'
        ]] + [notes]

        return pd.Series(row_result)

    # 處理整個 df
    columns = ['声母', '韵母', '音调', '韵腹', '韵尾',
               '声母IPA', '韵腹IPA', '韵尾IPA', '音调IPA', 'IPA_程序改名', '注释_add']
    df_result = df.copy()
    df_result[columns] = df[match_column].apply(process_yutping)
    df_result.to_excel(filepath, index=False, na_rep="")
    print(f"✅ 已寫入到文件: {filepath}")
    return df_result


