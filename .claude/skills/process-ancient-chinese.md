# 上古汉语拼音处理 (Process Ancient Chinese Pinyin)

## 功能说明

处理 `data/dependency/上古汉语音节表.xlsx` 中 "字典表" sheet 的上古汉语拼音数据，将拼音字符串解析为声母、韵母、声调、韵部、声母组、`r` 介音、非三等等音韵学要素，并生成谐声域标识。

## 数据源

- **文件**: `data/dependency/上古汉语音节表.xlsx`
- **Sheet**: 字典表
- **数据结构**:
  - 字: 汉字
  - 拼音: 上古汉语拼音（如 `pa`、`krumq`、`pat`、`typs`）
  - 韵部: 韵部名称
  - 韵母: 韵母
  - 其他音韵学字段...

## 处理算法

### 1. 查找元音位置

```python
def find_vowel_position(pinyin_str):
    """
    从后向前查找第一个元音字母的位置。
    元音: a, e, i, o, u, y
    返回: 元音位置索引（从0开始）
    """
    for i in range(len(pinyin_str) - 1, -1, -1):
        if pinyin_str[i] in ['a', 'e', 'i', 'o', 'u', 'y']:
            return i
    return None
```

### 2. 识别声调

```python
def identify_tone(pinyin_str):
    """
    根据拼音末尾字符判断声调。
    """
    last_char = pinyin_str[-1]

    tone_map = {
        'q': '上聲',
        'h': '去聲',
        's': '去聲',
        'p': '入聲',
        't': '入聲',
        'k': '入聲',
    }

    return tone_map.get(last_char, '平聲')
```

### 3. 提取声母和韵母

```python
def extract_components(pinyin_str, char=''):
    """
    提取声母、韵母、韵部、声母组、r介音、非三等等音韵要素。
    固定处理顺序: q/h -> yps -> s
    """
    working = pinyin_str

    # 1) 先处理 q/h。
    # 伪代码写作 str = str[0:-2]，语义是删掉末尾的 q/h 声调标记；
    # 如果实现中仍保留原始 q/h 字母，则按实际字符串表示去掉该标记即可。
    if working and working[-1] in ['q', 'h']:
        working = working[:-1]

    # 2) 再处理 yps 韵。
    # 这里判断的是“韵是否为 yps”，不是要求整串必须字面等于 yps。
    if working.endswith('yps'):
        sheng_mu = working[:-3]
        if sheng_mu in ['t', 'd', 'n', 's']:
            return {
                '声母': sheng_mu,
                '韵母': 'ut',
                '韵部': '物u',
                '声母组': '',
                'r介音': False,
                '非三等': False,
            }
        return {
            '声母': sheng_mu,
            '韵母': 'yt',
            '韵部': '物y',
            '声母组': '',
            'r介音': False,
            '非三等': False,
        }

    # 3) 最后处理去声 s，把它改写成 t。
    if working and working[-1] == 's':
        working = working[:-1] + 't'

    # 4) 正常切分声母和韵母。
    # 韵母保留完整韵尾，例如 at / eng / iwk。
    vowel_pos = find_vowel_position(working)
    if vowel_pos is None:
        return None

    yun_mu = working[vowel_pos:]
    sheng_mu = working[:vowel_pos]

    # 5) 特殊字处理。
    # 这些字的声母要改写成以 rh 开头的对应形式。
    special_chars = '釃灑矖數藪棷籔數率帥率'
    if char and char in special_chars:
        sheng_mu = 'rh' + sheng_mu[2:]

    # 6) 处理非三等和 r 介音。
    r_jieyin = False
    fei_san_deng = False
    sheng_mu_zu = ''

    if sheng_mu.endswith("'"):
        fei_san_deng = True
        sheng_mu_zu = 'R'
        sheng_mu = sheng_mu[:-1]
    elif (
        sheng_mu.endswith('r')
        and not sheng_mu.startswith('r')
        and not sheng_mu.startswith('C')
    ):
        sheng_mu = sheng_mu[:-1]
        r_jieyin = True
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
        '非三等': fei_san_deng,
    }
```

### 4. 查找韵部（通过完整韵母查表）

```python
# 韵部查找表：完整韵母 -> 韵部
# 韵母保留闭音尾，不拆成“主元音 + 韵尾”两个字段。
YUNBU_MAP = {
    # 无韵尾
    'a': '魚', 'e': '支', 'o': '侯', 'y': '之', 'i': '脂', 'u': '幽u',

    # j 韵尾
    'aj': '歌a', 'oj': '歌o', 'yj': '微y', 'uj': '微u',

    # w 韵尾
    'aw': '宵a', 'ew': '宵e', 'iw': '幽i',

    # m 韵尾
    'am': '談a', 'em': '談e', 'ym': '侵y', 'im': '侵i', 'um': '侵u',

    # n 韵尾
    'an': '元a', 'en': '元e', 'on': '元o', 'yn': '文y', 'in': '真n', 'un': '文u',

    # ng 韵尾
    'ang': '陽', 'eng': '耕', 'ong': '東', 'yng': '蒸', 'ing': '真ng', 'ung': '冬',

    # p 韵尾
    'ap': '葉a', 'ep': '葉e', 'yp': '緝y', 'ip': '緝i',

    # t 韵尾
    'at': '月a', 'et': '月e', 'ot': '月o', 'yt': '物y', 'it': '質t', 'ut': '物u',

    # k 韵尾
    'ak': '鐸', 'ek': '錫', 'ok': '屋', 'yk': '職', 'ik': '質k', 'uk': '覺u',

    # wk 韵尾
    'awk': '藥a', 'ewk': '藥e', 'iwk': '覺i',
}


def find_yunbu(yunmu):
    """
    根据完整韵母查找韵部。
    """
    if yunmu == 'ar':
        return '元ar'
    if yunmu == 'or':
        return '元or'
    return YUNBU_MAP.get(yunmu, '')
```

### 5. 查找声母组（通过声母查表）

```python
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


def find_shengmu_zu(shengmu):
    """
    根据声母查找声母组。
    """
    return SHENGMU_ZU_MAP.get(shengmu, '')
```

### 6. 生成谐声域

```python
def generate_xie_sheng_yu(sheng_mu_zu, yun_mu):
    """
    生成谐声域标识。
    格式: 声母组 + 大写韵母
    """
    return sheng_mu_zu + yun_mu.upper()
```

## 完整处理流程

```python
def process_ancient_chinese_pinyin(pinyin_str, char=''):
    """
    处理上古汉语拼音的完整流程。

    参数:
        pinyin_str: 拼音字符串（如 'pa', 'krumq', 'pat', 'typs'）
        char: 对应的汉字（用于特殊字处理）

    返回:
        dict: 包含声调、声母、韵母、韵部、声母组、r介音、非三等、谐声域等信息
    """
    # 1. 识别声调
    tone = identify_tone(pinyin_str)

    # 2. 提取音韵要素
    components = extract_components(pinyin_str, char)
    if components is None:
        return None

    # 3. 查找韵部
    yunbu = components['韵部'] or find_yunbu(components['韵母'])

    # 4. 查找声母组
    shengmu_zu = components['声母组'] or find_shengmu_zu(components['声母'])

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
        '谐声域': xie_sheng_yu,
    }
```

## 使用示例

```python
# 示例1: 简单拼音
result = process_ancient_chinese_pinyin('pa', '扒')
# 输出: {'声调': '平聲', '声母': 'p', '韵母': 'a', '韵部': '魚', ...}

# 示例2: 带声调标记
result = process_ancient_chinese_pinyin('krumq', '窟')
# 输出: {'声调': '上聲', '声母': 'k', '韵母': 'um', '韵部': '侵u', 'r介音': True, ...}

# 示例3: 入声
result = process_ancient_chinese_pinyin('pat', '八')
# 输出: {'声调': '入聲', '声母': 'p', '韵母': 'at', '韵部': '月a', ...}

# 示例4: yps 特判
result = process_ancient_chinese_pinyin('typs', '亭')
# 输出: {'声调': '去聲', '声母': 't', '韵母': 'ut', '韵部': '物u', ...}
```

## 注意事项

1. **索引规则**:
   - `str[-1]` 表示字符串最后一个字符
   - `str[0:n]` 表示从开头到第 `n` 个字符（不含第 `n` 个）
   - `str[n:]` 表示从第 `n` 个字符到结尾

2. **大小写转换**:
   - `uppercase()` 或 `str.upper()` 将小写字母转换为大写

3. **特殊字处理**:
   - 某些特殊字（`釃灑矖數藪棷籔數率帥率`）需要把声母改写成以 `rh` 开头的对应形式

4. **处理顺序**:
   - 必须先判定声调，再按 `q/h -> yps -> s` 的顺序处理
   - 不能先处理 `s`，再处理上面的 `q/h`

5. **q/h 声调标记**:
   - 伪代码里的 `str[0:-2]` 对应“删掉 `q/h` 声调标记”这个语义
   - 如果中间步骤把声调替换成了两字符标签，就删整个标签
   - 如果仍然保留原始 `q/h` 字母，就删掉末尾这个声调字符

6. **yps 特判**:
   - 判断对象是“韵为 `yps`”，不是要求整串字面等于 `yps`
   - 若声母是 `t/d/n/s`，则韵母记为 `ut`、韵部记为 `物u`
   - 其余声母则韵母记为 `yt`、韵部记为 `物y`

7. **韵母和韵部**:
   - 韵母保留完整韵尾，例如 `at`、`eng`、`iwk`
   - `韵部` 通过完整韵母查表得到，例如 `at -> 月a`
   - 额外特判: `ar -> 元ar`，`or -> 元or`

8. **r介音和非三等**:
   - 撇号 `'` 标记非三等，并将声母组记为 `R`
   - 字母 `r` 在特定位置标记 `r` 介音
   - 去掉末尾 `r` 后，还要再次检查是否带有撇号

## 数据库集成

处理后的数据可以写入 `characters.db` 或相关数据库，字段包括：
- 字
- 拼音
- 声母
- 韵母
- 声调
- 韵部
- 谐声域
- 声母组
- `r` 介音标记
- 非三等标记
