import math
import os
import re

import pandas as pd

from common.search_tones import search_tones
from common.constants import col_map, vowel_pattern, TONE_MAP
from source.match_fromdb import get_tsvs


def extract_all_from_files(file_path: str, get_tone: bool = True, preserve_empty_rows: bool = False, query_db_path: str = None) -> pd.DataFrame:
    from common.config import QUERY_DB_PATH

    # 如果沒有指定 query_db_path，使用默認值
    if query_db_path is None:
        query_db_path = QUERY_DB_PATH

    def build_tone_map_yindian(result):
        tone_map = {}

        for row in result:
            total_data = row.get("總數據", [])

            for cell in total_data:
                if not cell:
                    continue

                # 提取所有 [tag]字 的形式，如 [1a]陰平、[7B]上陰入
                tag_value_pairs = re.findall(r"\[([0-9]{1,2}[a-zA-Z]?)\](?:\d{1,3})?([^\[\],\d]*)", cell)

                for tag, name in tag_value_pairs:
                    name = name.strip()
                    if tag and name and tag not in tone_map:
                        tone_map[tag] = name

        return tone_map

    if get_tone:
        shortname = get_tsvs(single=file_path, query_db_path=query_db_path)[1]
        result = search_tones(locations=shortname, regions=None, get_raw=True, db_path=query_db_path)
        tone_map_yindian = build_tone_map_yindian(result)
    else:
        tone_map_yindian = TONE_MAP

    # tone_map_jyutping = {
    #     "1": "陰平", "2": "陰上", "3": "陰去", "4": "陽平", "5": "陽上", "6": "陽去",
    #     "7": "上陰入", "8": "下陰入", "9": "陽入", "10": "下陽入", "0": "變調"
    # }


    def get_standard_column_name(col_name, col_map):
        """
        根據 col_map 返回標準化的列名。
        :param col_name: 當前列名
        :param col_map: 列名映射
        :return: 返回對應的標準化列名
        """
        for standard_col, possible_names in col_map.items():
            if col_name in possible_names:
                return standard_col
        return col_name  # 如果找不到對應的列名，返回原列名

    # 檢查文件的副檔名來決定使用哪種方法
    file_extension = os.path.splitext(file_path)[1].lower()
    # print(file_extension)
    if file_extension == ".tsv":
        df = pd.read_csv(file_path, sep="\t", dtype=str)
    elif file_extension in [".xls", ".xlsx"]:
        df = pd.read_excel(file_path, dtype=str)
    else:
        raise ValueError("Unsupported file format. Please provide a TSV or Excel file.")

        # 處理欄位名稱，根據 col_map 進行模糊對應
    df.columns = [get_standard_column_name(col, col_map) for col in df.columns]
    df = df.fillna("")

    # 判斷 tone 系統
    # def extract_tone_number(df, char):
    #     row = df[df['漢字'] == char]
    #     if not row.empty:
    #         phonetic = row.iloc[0]['音標']
    #         if isinstance(phonetic, str):
    #             match = re.search(r"(\d+)", phonetic)
    #             if match:
    #                 return match.group(1).lstrip("0")
    #     return None

    # tone_shi = extract_tone_number(df, "時")
    # tone_qiong = extract_tone_number(df, "窮")
    tone_map = tone_map_yindian
    # tone_map = tone_map_yindian if "2" in [tone_shi, tone_qiong] else tone_map_jyutping

    results = []

    for _, row in df.iterrows():
        hanzi = row.get("漢字", "").strip()
        phonetic = row.get("音標", "").strip()
        note = row.get("解釋", "").strip()
        if isinstance(phonetic, str):
            phonetic = phonetic.strip()
        if not hanzi or not phonetic or phonetic == "0" or hanzi == "0":
            if preserve_empty_rows:
                results.append({
                    '汉字': '',
                    '音标': '',
                    '声母': '',
                    '韵母': '',
                    '声调': '',
                    '註釋': ''
                })
                continue
            continue
        if re.search(r"[□■⬜⬛☐☑☒▯▢▣█�]", hanzi):
            if preserve_empty_rows:
                results.append({
                    '汉字': '',
                    '音标': '',
                    '声母': '',
                    '韵母': '',
                    '声调': '',
                    '註釋': ''
                })
                continue
            continue
        if phonetic and (isinstance(phonetic, float) and math.isnan(phonetic)):
            if preserve_empty_rows:
                results.append({
                    '汉字': '',
                    '音标': '',
                    '声母': '',
                    '韵母': '',
                    '声调': '',
                    '註釋': ''
                })
                continue
            continue
        if isinstance(phonetic, str) and phonetic and phonetic[0].isdigit():
            if preserve_empty_rows:
                results.append({
                    '汉字': '',
                    '音标': '',
                    '声母': '',
                    '韵母': '',
                    '声调': '',
                    '註釋': ''
                })
                continue
            continue

        phonetic_variants = phonetic.split("/") if "/" in phonetic and phonetic.strip() != '/' else [phonetic]

        for phon in phonetic_variants:
            phon = phon.strip()  # 先清乾淨
            if not phon:  # 若為空，跳過（這一步是關鍵防炸）
                continue
            if re.match(r'^[\d\/?\'"’”、|；：，。:;,.]+$', phon):
                continue

            # 提取聲母
            consonant = ""
            if phon and phon[0] in {"∅", "Ø"}:
                consonant = "ʔ"
            else:
                if not re.search(vowel_pattern, re.split(r"\d", phon)[0]):
                    vowel_fallback = r"([ʐɣmnŋɲȵƞʋvʒlḷfzr])"
                    # if phon[0] in ['l', 'f']:
                    #     consonant = phon[0]
                    if re.match(vowel_fallback, phon[0]):
                        consonant = "/"
                    elif not re.search(vowel_fallback, phon):
                        # consonant = f"報錯：{phon}"
                        consonant = ""
                    else:
                        for char in phon:
                            if re.match(vowel_fallback, char) or re.match(r'\d', char):
                                break
                            consonant += char
                else:
                    if re.match(vowel_pattern, phon[0]):
                        consonant = "/"
                    elif 'j' in phon[1:] or 'ʲ' in phon[1:]:
                        for char in phon:
                            if re.match(vowel_pattern, char) or char in ('j', 'ʲ'):
                                break
                            consonant += char
                    else:
                        for char in phon:
                            if re.match(vowel_pattern, char):
                                break
                            consonant += char
                consonant = re.sub(r"\d", "", consonant)

            # 韻母提取
            all_rhymes = []
            tmp_phon = phon[1:] if phon.startswith(("∅", "Ø")) else phon
            if 'j' not in tmp_phon[1:] and 'ʲ' not in tmp_phon[1:]:
                vowel_found = False
                for c in tmp_phon:
                    if re.match(vowel_pattern, c) and not vowel_found:
                        vowel_found = True
                        all_rhymes.append(c)
                    elif vowel_found and (c.isdigit() or c.isspace()):
                        break
                    elif vowel_found:
                        all_rhymes.append(c)
                if not vowel_found and any(c in tmp_phon for c in "ʐzflḷɣmnŋȵɲƞʋvʒr"):
                    match = re.search(r".*?([ʐzflḷɣrmnŋɲȵƞʋvʒ].*?)(?=\d|\s|$)", tmp_phon)
                    if match:
                        all_rhymes += list(match.group(1))
            else:
                match = re.search(rf"[{vowel_pattern.strip('[]')}jʲ][^\d\s]*", tmp_phon)
                if match:
                    all_rhymes = list(match.group(0))

            rhyme = ''.join(c for c in all_rhymes if not (c.isdigit() or re.match(r'[一-鿿]', c)))
            for old, new in {
                'ε': 'ɛ', "α": "ɑ", "ʯ": "ʮ", "∅": "ø", "ο": "o", "ǝ": "ə", "о": "o", "у": "y", "е": "e",
                "ã": "ã", "ẽ": "ẽ", "ĩ": "ĩ", "ī": "ĩ", "ā": "ã", "ỹ": "ỹ", "õ": "õ", "ʱ": "ʰ"
            }.items():
                rhyme = rhyme.replace(old, new)

            for old, new in {
                '∫': 'ʃ', 'th': 'tʰ', 'kh': 'kʰ', 'ph': 'pʰ',
                'tsh': 'tsʰ', "ς": "ɕ", 'ts': 'ʦ', 'tʃ': 'ʧ', 'tɕ': 'ʨ',
                "∨": "v", "ł": "ɬ", "tʰs": "ʦʰ", "(ʔ)": "ʔ", "∅": "ʔ", "Ǿ": "ʔ"
            }.items():
                consonant = consonant.replace(old, new)

            if not get_tone:
                results.append({
                    '汉字': hanzi,
                    '音标': phon,
                    '声母': consonant,
                    '韵母': rhyme,
                    '声调': '',
                    '註釋': note
                })
                continue

            # 提取聲調
            if "輕聲" in phon:
                tone = "輕聲"
            else:
                tone_match = re.search(r"([A-Da-d0-9]+)", phon[::-1])
                tone_code = tone_match.group(1) if tone_match else ""
                if tone_code:
                    # 使用正則表達式刪除末尾的字母，直到遇到數字
                    tone_code = re.sub(r'[a-dA-D]+$', '', tone_code)
                tone_code = tone_code[::-1] if tone_code else ""
                tone = tone_map.get(tone_code, tone_map.get(tone_code, "未知")) if tone_code else ""

            results.append({
                '汉字': hanzi,
                '音标': phon,
                '声母': consonant,
                '韵母': rhyme,
                '声调': tone,
                '註釋': note
            })

    return pd.DataFrame(results)


# tsv_file = r"C:\Users\joengzaang\myfiles\杂文件\声韵处理\processed\東莞東坑.tsv"
# tsv_file = r"C:\Users\joengzaang\PycharmProjects\chars\data\yindian\東莞莞城.tsv"
# result = extract_all_from_files(tsv_file)
# pd.set_option('display.max_rows', None)  # 显示所有行
# pd.set_option('display.max_columns', None)  # 显示所有列
# pd.set_option('display.width', None)  # 自动适应宽度
# pd.set_option('display.max_colwidth', None)  # 显示所有列内容（不截断长字符串）
# print(result)
