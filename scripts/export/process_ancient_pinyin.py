#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
处理上古汉语拼音数据
根据 .claude/skills/process-ancient-chinese.md 中的算法
从 data/dependency/上古汉语音节表.xlsx 读取数据并处理
"""

import pandas as pd
import sys
import os
import zipfile
import xml.etree.ElementTree as ET

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# 韵部查找表：完整韵母 -> 韵部
YUNBU_MAP = {
    # 无韵尾
    'a': '魚', 'e': '支', 'o': '侯', 'y': '之', 'i': '脂', 'u': '幽u',
    # j韵尾
    'aj': '歌a', 'oj': '歌o', 'yj': '微y', 'uj': '微u',
    # w韵尾
    'aw': '宵a', 'ew': '宵e', 'iw': '幽i',
    # m韵尾
    'am': '談a', 'em': '談e', 'ym': '侵y', 'im': '侵i', 'um': '侵u',
    # n韵尾
    'an': '元a', 'en': '元e', 'on': '元o', 'yn': '文y', 'in': '真n', 'un': '文u',
    # ng韵尾
    'ang': '陽', 'eng': '耕', 'ong': '東', 'yng': '蒸', 'ing': '真ng', 'ung': '冬',
    # p韵尾
    'ap': '葉a', 'ep': '葉e', 'yp': '緝y', 'ip': '緝i',
    # t韵尾
    'at': '月a', 'et': '月e', 'ot': '月o', 'yt': '物y', 'it': '質t', 'ut': '物u',
    # k韵尾
    'ak': '鐸', 'ek': '錫', 'ok': '屋', 'yk': '職', 'ik': '質k', 'uk': '覺u',
    # wk韵尾
    'awk': '藥a', 'ewk': '藥e', 'iwk': '覺i',
}

# 声母组查找表：声母 -> 声母组
SHENGMU_ZU_MAP = {
    # P组
    'p': 'P', 'ph': 'P', 'b': 'P',
    # M组
    'm': 'M', 'mh': 'M',
    # T组
    't': 'T', 'th': 'T', 'd': 'T', 'st': 'T',
    # N组
    'n': 'N', 'nh': 'N',
    # TS组
    'ts': 'TS', 'tsh': 'TS', 'dz': 'TS', 's': 'TS',
    # L组
    'l': 'L', 'lh': 'L', 'sl': 'L', 'ml': 'L',
    # R组
    'r': 'R', 'C.r': 'R', 'rh': 'R',
    # J组
    'j': 'J', 'jh': 'J', 'kj': 'J', 'khj': 'J', 'mj': 'J', 'hj': 'J', 'sj': 'J',
    # K组
    'k': 'K', 'kh': 'K', 'g': 'K', 'h': 'K',
    # NG组
    'ng': 'NG', 'ngh': 'NG',
    # W组
    'kw': 'W', 'khw': 'W', 'gw': 'W', 'ngw': 'W', 'w': 'W', 'wh': 'W', 'qw': 'W',
    # Q组
    'q': 'Q',
}


def find_vowel_position(pinyin_str):
    """
    从后向前查找第一个元音字母的位置
    元音: a, e, i, o, u, y
    返回: 元音位置索引（从0开始）
    """
    if not pinyin_str:
        return None

    for i in range(len(pinyin_str)-1, -1, -1):
        if pinyin_str[i] in ['a', 'e', 'i', 'o', 'u', 'y']:
            return i
    return None


def identify_tone(pinyin_str):
    """
    根据拼音末尾字符判断声调
    """
    if not pinyin_str:
        return '平聲'

    last_char = pinyin_str[-1]

    tone_map = {
        'q': '上聲',
        'h': '去聲',
        's': '去聲',
        'p': '入聲',
        't': '入聲',
        'k': '入聲'
    }

    return tone_map.get(last_char, '平聲')


def find_yunbu(yun_mu):
    """
    根据完整韵母查找韵部
    """
    if yun_mu == 'ar':
        return '元ar'
    if yun_mu == 'or':
        return '元or'
    return YUNBU_MAP.get(yun_mu, '')


def extract_components(pinyin_str, char=''):
    """
    提取声母、韵母、韵部等音韵要素
    处理顺序固定为: q/h -> yps -> s
    """
    if not pinyin_str:
        return None

    working = pinyin_str

    # 先处理 q/h 声调标记。伪代码中写作删掉末尾替换后的整段标记，
    # 当前脚本直接处理原始拼音，因此只去掉最后一个 q/h 字符。
    if working[-1] in ['q', 'h']:
        working = working[:-1]

    # 再处理 yps 韵。这里判断的是韵是否为 yps，而不是整串字面必须等于 yps。
    if working.endswith('yps'):
        sheng_mu = working[:-3]
        if sheng_mu in ['t', 'd', 'n', 's']:
            return {
                '韵部': '物u',
                '声母': sheng_mu,
                '韵母': 'ut',
                '声母组': '',
                'r介音': False,
                '非三等': False
            }
        return {
            '韵部': '物y',
            '声母': sheng_mu,
            '韵母': 'yt',
            '声母组': '',
            'r介音': False,
            '非三等': False
        }

    # 最后处理去声 s，把它改写成 t。
    if working[-1] == 's':
        working = working[:-1] + 't'

    # 查找元音位置，韵母保留完整韵尾，例如 at / eng / iwk。
    vowel_pos = find_vowel_position(working)
    if vowel_pos is None:
        return None

    # 分离韵母和声母
    yun_mu = working[vowel_pos:]
    sheng_mu = working[:vowel_pos]

    # 特殊字处理
    special_chars = '釃灑矖數藪棷籔數率帥率'
    if char and char in special_chars:
        sheng_mu = 'rh' + sheng_mu[2:]

    # 处理r介音和非三等标记
    r_jieyin = False
    fei_san_deng = False
    sheng_mu_zu = ''

    # 检查撇号标记（非三等）
    if sheng_mu.endswith("'"):
        fei_san_deng = True
        sheng_mu_zu = 'R'
        sheng_mu = sheng_mu[:-1]
    # 检查r介音
    elif (sheng_mu.endswith('r') and
          not sheng_mu.startswith('r') and
          not sheng_mu.startswith('C')):
        sheng_mu = sheng_mu[:-1]
        r_jieyin = True
        # 再次检查撇号
        if sheng_mu.endswith("'"):
            sheng_mu = sheng_mu[:-1]
            fei_san_deng = True
            sheng_mu_zu = 'R'

    return {
        '声母': sheng_mu,
        '韵母': yun_mu,
        '韵部': '',
        '声母组': sheng_mu_zu,
        'r介音': r_jieyin,
        '非三等': fei_san_deng
    }


def generate_xie_sheng_yu(sheng_mu_zu, yun_mu):
    """
    生成谐声域标识
    格式: 声母组 + 大写韵母
    """
    return sheng_mu_zu + yun_mu.upper()


def is_missing_value(value):
    """
    只把真正缺失的 NaN/None 当作空值。
    字符串 'nan' 是有效内容，不能在这里过滤掉。
    """
    return value is None or (not isinstance(value, str) and pd.isna(value))


def get_cell_text(row, column_name):
    """
    从 DataFrame 行中读取单元格文本。
    保留字面值 'nan'，仅把真正缺失值转成空字符串。
    """
    value = row.get(column_name, '')
    if is_missing_value(value):
        return ''
    return str(value)


def process_ancient_chinese_pinyin(pinyin_str, char=''):
    """
    处理上古汉语拼音的完整流程

    参数:
        pinyin_str: 拼音字符串（如 "pa", "krumq"）
        char: 对应的汉字（用于特殊字处理）

    返回:
        dict: 包含声调、声母、韵母、韵部、谐声域等信息
    """
    if not pinyin_str:
        return None

    # 1. 识别声调
    tone = identify_tone(pinyin_str)

    # 2. 提取音韵要素
    components = extract_components(pinyin_str, char)
    if components is None:
        return None

    # 3. 查找韵部（通过完整韵母查表）
    yunbu = find_yunbu(components['韵母'])
    if not yunbu and components.get('韵部'):
        yunbu = components['韵部']  # 使用特殊情况的韵部（如yps）

    # 4. 查找声母组（通过声母查表）
    shengmu_zu = SHENGMU_ZU_MAP.get(components['声母'], '')
    if not shengmu_zu and components.get('声母组'):
        shengmu_zu = components['声母组']  # 使用特殊情况的声母组（如撇号标记）

    # 5. 生成谐声域
    xie_sheng_yu = generate_xie_sheng_yu(shengmu_zu, components['韵母'])

    return {
        '声调': tone,
        '声母': components['声母'],
        '韵母': components['韵母'],
        '韵部': yunbu,
        '声母组': shengmu_zu,
        'r介音': components['r介音'],
        '非三等': components['非三等'],
        '谐声域': xie_sheng_yu
    }


def read_excel_manually(xlsx_file, sheet_name='字典表'):
    """
    手动解析xlsx文件（避免openpyxl版本兼容性问题）
    """
    with zipfile.ZipFile(xlsx_file, 'r') as zip_ref:
        # 读取共享字符串
        shared_strings_xml = zip_ref.read('xl/sharedStrings.xml')
        ss_root = ET.fromstring(shared_strings_xml)
        shared_strings = []
        for si in ss_root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t'):
            shared_strings.append(si.text if si.text else '')

        # 确定sheet编号（字典表是sheet3）
        sheet_xml = zip_ref.read('xl/worksheets/sheet3.xml')
        sheet_root = ET.fromstring(sheet_xml)

        # 读取所有行
        rows = sheet_root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row')

        # 使用字典来存储单元格数据（按行列索引）
        cell_data = {}
        max_col = 0

        for row in rows:
            row_num = int(row.get('r'))
            cells = row.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c')

            for cell in cells:
                cell_ref = cell.get('r')  # 如 'A1', 'B2'
                # 解析列号
                col_letter = ''.join([c for c in cell_ref if c.isalpha()])
                col_num = 0
                for c in col_letter:
                    col_num = col_num * 26 + (ord(c) - ord('A') + 1)

                max_col = max(max_col, col_num)

                cell_type = cell.get('t')
                v = cell.find('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')

                if v is not None and v.text:
                    if cell_type == 's':  # 共享字符串
                        idx = int(v.text)
                        if idx < len(shared_strings):
                            cell_data[(row_num, col_num)] = shared_strings[idx]
                        else:
                            cell_data[(row_num, col_num)] = v.text
                    else:
                        cell_data[(row_num, col_num)] = v.text

        # 构建数据矩阵
        if not cell_data:
            return pd.DataFrame()

        max_row = max([r for r, c in cell_data.keys()])

        data = []
        for row_num in range(1, max_row + 1):
            row_data = []
            for col_num in range(1, max_col + 1):
                row_data.append(cell_data.get((row_num, col_num), ''))
            data.append(row_data)

        # 第一行是列名
        if data:
            columns = data[0]
            df = pd.DataFrame(data[1:], columns=columns)
            return df
        return pd.DataFrame()


def main():
    """
    主函数：读取Excel文件，处理数据，写入新文件
    """
    print("开始处理上古汉语拼音数据...")

    # 输入输出文件路径
    input_file = 'data/dependency/上古汉语音节表.xlsx'
    output_file = 'data/processed_ancient_pinyin.xlsx'

    try:
        # 读取Excel文件
        print(f"正在读取文件: {input_file}")
        df = read_excel_manually(input_file, sheet_name='字典表')
        print(f"读取成功，共 {len(df)} 行数据")

        # 显示原始列名
        print(f"原始列名: {df.columns.tolist()}")

        # 处理每一行数据
        results = []
        error_count = 0

        for idx, row in df.iterrows():
            try:
                # 获取字和拼音
                char = get_cell_text(row, df.columns[0])
                pinyin_col = df.columns[2] if len(df.columns) > 2 else '拼音'
                pinyin = get_cell_text(row, pinyin_col)

                # 初始化结果行（即使处理失败也要保留）
                result_row = {
                    '字': char,
                    '原始拼音': pinyin,
                    '声调': '',
                    '声母': '',
                    '韵母': '',
                    '韵部': '',
                    '声母组': '',
                    'r介音': False,
                    '非三等': False,
                    '谐声域': ''
                }

                # 尝试处理拼音
                if pinyin:
                    result = process_ancient_chinese_pinyin(pinyin, char)

                    if result:
                        # 优先使用计算结果，只有在计算结果为空时才使用Excel数据
                        final_yunbu = result['韵部']
                        final_yunmu = result['韵母']

                        # 如果计算结果为空，尝试从Excel读取
                        if not final_yunbu:
                            if len(df.columns) > 3:
                                excel_yunbu = get_cell_text(row, df.columns[3])
                                # 只使用有意义的Excel数据（排除"√"等标记）
                                if excel_yunbu and excel_yunbu != '√':
                                    final_yunbu = excel_yunbu

                        if not final_yunmu:
                            if len(df.columns) > 4:
                                excel_yunmu = get_cell_text(row, df.columns[4])
                                # 只使用有意义的Excel数据（排除"√"等标记）
                                if excel_yunmu and excel_yunmu != '√':
                                    final_yunmu = excel_yunmu

                        # 更新结果
                        result_row.update({
                            '声调': result['声调'],
                            '声母': result['声母'],
                            '韵母': final_yunmu,
                            '韵部': final_yunbu,
                            '声母组': result['声母组'],
                            'r介音': result['r介音'],
                            '非三等': result['非三等'],
                            '谐声域': result['谐声域']
                        })
                    else:
                        error_count += 1
                        # 处理失败时，尝试从Excel读取数据（排除"√"等标记）
                        if len(df.columns) > 3:
                            excel_yunbu = get_cell_text(row, df.columns[3])
                            if excel_yunbu and excel_yunbu != '√':
                                result_row['韵部'] = excel_yunbu
                        if len(df.columns) > 4:
                            excel_yunmu = get_cell_text(row, df.columns[4])
                            if excel_yunmu and excel_yunmu != '√':
                                result_row['韵母'] = excel_yunmu
                else:
                    error_count += 1

                # 添加原始数据的其他列
                for col in df.columns:
                    if col not in [df.columns[0], pinyin_col]:
                        result_row[f'{col}'] = row.get(col, '')

                results.append(result_row)

            except Exception as e:
                error_count += 1
                if error_count <= 10:  # 只打印前10个错误
                    print(f"处理第 {idx+1} 行时出错: {e}")

        # 创建结果DataFrame
        result_df = pd.DataFrame(results)

        # 写入Excel文件
        print(f"\n正在写入文件: {output_file}")
        result_df.to_excel(output_file, index=False, engine='openpyxl')

        print(f"\n处理完成！")
        print(f"成功处理: {len(results)} 行")
        print(f"错误数量: {error_count} 行")
        print(f"输出文件: {output_file}")

        # 显示前几行结果
        print("\n前5行处理结果:")
        print(result_df.head().to_string())

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
