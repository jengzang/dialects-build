import sys
from pathlib import Path

import pandas as pd

from common.config import HAN_PATH


def normalize_coordinate_text(value):
    text = '' if value is None else str(value).strip()
    if not text or text.lower() == 'nan':
        return ''
    text = text.replace('，', ',')
    parts = [part.strip() for part in text.split(',')]
    if len(parts) == 2 and parts[0] and parts[1]:
        return f"{parts[0]},{parts[1]}"
    return text


def load_han_file_for_change_check(file_path):
    df = pd.read_excel(file_path, sheet_name='檔案', dtype=object)
    df.columns = [str(c).strip() for c in df.columns]
    missing_cols = [col for col in ['簡稱', '經緯度', '是否有人在做'] if col not in df.columns]
    if missing_cols:
        print(f"\n❌ 簡稱變化檢查失敗：文件【{Path(file_path).name}】缺少必要欄位 {missing_cols}")
        print(f"   實際讀到的欄位 ({len(df.columns)}個): {list(df.columns)}")
        sys.exit(1)

    df = df.fillna('').copy()
    df['簡稱'] = df['簡稱'].astype(str).str.strip()
    df['是否有人在做'] = df['是否有人在做'].astype(str).str.strip()
    df = df[(df['簡稱'] != '') & (~df['簡稱'].str.startswith('#'))].copy()
    df['norm_經緯度'] = df['經緯度'].apply(normalize_coordinate_text)
    return df


def get_old_han_history_files(current_han_path=HAN_PATH):
    current_file = Path(current_han_path)
    if not current_file.exists():
        print(f"\n❌ 簡稱變化檢查失敗：找不到當前音典文件 {current_file}")
        sys.exit(1)

    old_dir = current_file.parent / 'old'
    if not old_dir.exists():
        print(f"\n❌ 簡稱變化檢查失敗：找不到 old 目錄 {old_dir}")
        sys.exit(1)

    prefix = current_file.stem
    candidates = sorted(old_dir.glob('*.xlsx'))
    matched = [path for path in candidates if path.stem.startswith(prefix)]
    if not matched:
        print(f"\n❌ 簡稱變化檢查失敗：old 目錄下找不到以前綴【{prefix}】開頭的歷史文件")
        sys.exit(1)
    return current_file, matched


def _build_abbreviation_status_entries(df):
    status_by_name = {}
    entries = []
    for _, row in df.iterrows():
        name = str(row['簡稱']).strip()
        status = str(row.get('是否有人在做', '')).strip()
        coord = str(row.get('norm_經緯度', '')).strip()
        county = str(row.get('縣/市/區', '')).strip()
        map_level = str(row.get('地圖級別', '')).strip()
        status_by_name.setdefault(name, []).append(
            {
                'coord': coord,
                'status': status,
                'county': county,
                'map_level': map_level,
            }
        )
        entries.append(
            {
                'name': name,
                'coord': coord,
                'status': status,
                'county': county,
                'map_level': map_level,
            }
        )
    return status_by_name, entries


def _pop_unique_entry(entries, *, name=None, coord=None):
    for idx, entry in enumerate(entries):
        if name is not None and entry['name'] != name:
            continue
        if coord is not None and entry['coord'] != coord:
            continue
        return entries.pop(idx)
    return None


def _format_status_entry(entry):
    suffix = [f"是否有人在做={entry['status']}"]
    if entry['coord']:
        suffix.append(f"經緯度={entry['coord']}")
    if entry['county']:
        suffix.append(f"縣/市/區={entry['county']}")
    if entry['map_level']:
        suffix.append(f"地圖級別={entry['map_level']}")
    return ' | '.join(suffix)


def _format_status_entry_from_entries(entries):
    if not entries:
        return '是否有人在做='
    if len(entries) == 1:
        return _format_status_entry(entries[0])
    return '候選=' + ' || '.join(_format_status_entry(entry) for entry in entries)


def _check_single_han_abbreviation_changes(current_file, old_file, status_filter=None):
    print("\n============================================================")
    print("步驟0：檢查新舊音典簡稱變化...")
    print("============================================================")
    print(f"   current: {current_file}")
    print(f"   old:     {old_file}")
    if status_filter:
        print(f"   filter:  是否有人在做={status_filter}")

    current_df = load_han_file_for_change_check(current_file)
    old_df = load_han_file_for_change_check(old_file)

    if status_filter:
        current_df = current_df[current_df['是否有人在做'] == status_filter].copy()
        old_df = old_df[old_df['是否有人在做'] == status_filter].copy()

    old_by_coord = old_df[old_df['norm_經緯度'] != ''].groupby('norm_經緯度')
    new_by_coord = current_df[current_df['norm_經緯度'] != ''].groupby('norm_經緯度')

    old_coord_map = {coord: group.copy() for coord, group in old_by_coord}
    new_coord_map = {coord: group.copy() for coord, group in new_by_coord}

    exact_unchanged = []
    exact_renamed = []
    exact_metadata_changed = []
    coord_conflicts = []
    matched_old_idx = set()
    matched_new_idx = set()

    shared_coords = sorted(set(old_coord_map) & set(new_coord_map))
    for coord in shared_coords:
        old_group = old_coord_map[coord]
        new_group = new_coord_map[coord]

        if len(old_group) == 1 and len(new_group) == 1:
            old_row = old_group.iloc[0]
            new_row = new_group.iloc[0]
            matched_old_idx.add(old_row.name)
            matched_new_idx.add(new_row.name)

            old_abbr = str(old_row['簡稱']).strip()
            new_abbr = str(new_row['簡稱']).strip()
            payload = {
                'coord': coord,
                'old_簡稱': old_abbr,
                'new_簡稱': new_abbr,
                'old_是否有人在做': str(old_row.get('是否有人在做', '')).strip(),
                'new_是否有人在做': str(new_row.get('是否有人在做', '')).strip(),
                'old_地圖級別': str(old_row.get('地圖級別', '')).strip(),
                'new_地圖級別': str(new_row.get('地圖級別', '')).strip(),
                'old_縣': str(old_row.get('縣/市/區', '')).strip(),
                'new_縣': str(new_row.get('縣/市/區', '')).strip(),
            }

            if old_abbr != new_abbr:
                exact_renamed.append(payload)
            elif payload['old_地圖級別'] != payload['new_地圖級別'] or payload['old_縣'] != payload['new_縣']:
                exact_metadata_changed.append(payload)
            else:
                exact_unchanged.append(payload)
        else:
            coord_conflicts.append({
                'coord': coord,
                'old_items': [
                    {
                        '簡稱': str(row['簡稱']).strip(),
                        '是否有人在做': str(row.get('是否有人在做', '')).strip(),
                    }
                    for _, row in old_group.iterrows()
                ],
                'new_items': [
                    {
                        '簡稱': str(row['簡稱']).strip(),
                        '是否有人在做': str(row.get('是否有人在做', '')).strip(),
                    }
                    for _, row in new_group.iterrows()
                ],
            })
            matched_old_idx.update(old_group.index.tolist())
            matched_new_idx.update(new_group.index.tolist())

    old_status_entries, old_entries = _build_abbreviation_status_entries(old_df)
    current_status_entries, new_entries = _build_abbreviation_status_entries(current_df)

    for item in exact_renamed:
        _pop_unique_entry(old_entries, name=item['old_簡稱'], coord=item['coord'])
        _pop_unique_entry(new_entries, name=item['new_簡稱'], coord=item['coord'])

    for item in exact_metadata_changed:
        _pop_unique_entry(old_entries, name=item['old_簡稱'], coord=item['coord'])
        _pop_unique_entry(new_entries, name=item['new_簡稱'], coord=item['coord'])

    old_unmatched = old_df[~old_df.index.isin(matched_old_idx)].copy()
    new_unmatched = current_df[~current_df.index.isin(matched_new_idx)].copy()

    old_abbr_set = {entry['name'] for entry in old_entries}
    new_abbr_set = {entry['name'] for entry in new_entries}
    added_abbrs = sorted(new_abbr_set - old_abbr_set)
    removed_abbrs = sorted(old_abbr_set - new_abbr_set)
    same_name_unmatched = sorted(set(old_unmatched['簡稱'].astype(str).str.strip()) & set(new_unmatched['簡稱'].astype(str).str.strip()))

    print(f"   新表記錄數: {len(current_df)}")
    print(f"   舊表記錄數: {len(old_df)}")
    print(f"   經緯度完全一致且一對一匹配: {len(exact_unchanged) + len(exact_renamed) + len(exact_metadata_changed)}")
    print(f"   同坐標衝突組: {len(coord_conflicts)}")
    print(f"   新增簡稱: {len(added_abbrs)}")
    print(f"   改名簡稱: {len(exact_renamed)}")
    print(f"   刪除簡稱: {len(removed_abbrs)}")
    print(f"   同名但未精確配對: {len(same_name_unmatched)}")

    if added_abbrs:
        print("\n【新增簡稱】")
        for name in added_abbrs:
            for entry in [item for item in new_entries if item['name'] == name]:
                print(f"  + {name} | {_format_status_entry(entry)}")

    if exact_renamed:
        print("\n【改名簡稱】")
        for item in exact_renamed:
            print(
                f"  {item['old_簡稱']} -> {item['new_簡稱']}"
                f"  @ {item['coord']}"
                f" | old是否有人在做={item['old_是否有人在做']}"
                f" | new是否有人在做={item['new_是否有人在做']}"
            )

    if removed_abbrs:
        print("\n【刪除簡稱】")
        for name in removed_abbrs:
            for entry in [item for item in old_entries if item['name'] == name]:
                print(f"  - {name} | {_format_status_entry(entry)}")

    if exact_metadata_changed:
        print("\n【同點但元數據有變】")
        for item in exact_metadata_changed[:50]:
            print(
                f"  {item['old_簡稱']} @ {item['coord']}"
                f" | old是否有人在做={item['old_是否有人在做']}"
                f" | new是否有人在做={item['new_是否有人在做']}"
                f" | 地圖級別: {item['old_地圖級別']} -> {item['new_地圖級別']} | "
                f"縣: {item['old_縣']} -> {item['new_縣']}"
            )
        if len(exact_metadata_changed) > 50:
            print(f"  ... 其餘 {len(exact_metadata_changed) - 50} 條省略")

    if coord_conflicts:
        print("\n【同坐標衝突組】")
        for item in coord_conflicts[:50]:
            old_text = [f"{entry['簡稱']}({entry['是否有人在做']})" for entry in item['old_items']]
            new_text = [f"{entry['簡稱']}({entry['是否有人在做']})" for entry in item['new_items']]
            print(f"  {item['coord']} | old={old_text} | new={new_text}")
        if len(coord_conflicts) > 50:
            print(f"  ... 其餘 {len(coord_conflicts) - 50} 組省略")

    if same_name_unmatched:
        print("\n【同名但未精確配對】")
        for name in same_name_unmatched:
            print(
                f"  ? {name}"
                f" | old{_format_status_entry_from_entries(old_status_entries.get(name, []))}"
                f" | new{_format_status_entry_from_entries(current_status_entries.get(name, []))}"
            )

    return {
        'added_abbrs': added_abbrs,
        'renamed_pairs': exact_renamed,
        'removed_abbrs': removed_abbrs,
        'metadata_changed': exact_metadata_changed,
        'coord_conflicts': coord_conflicts,
        'same_name_unmatched': same_name_unmatched,
        'exact_unchanged_count': len(exact_unchanged),
    }


def check_han_abbreviation_changes(current_han_path=HAN_PATH, status_filter=None):
    current_file, old_files = get_old_han_history_files(current_han_path=current_han_path)
    results = []
    print(f"\n共找到 {len(old_files)} 個歷史文件需要比對")
    for index, old_file in enumerate(old_files, start=1):
        print(f"\n>>>> [{index}/{len(old_files)}] 比對歷史文件：{old_file.name}")
        results.append(
            {
                'old_file': str(old_file),
                'result': _check_single_han_abbreviation_changes(
                    current_file=current_file,
                    old_file=old_file,
                    status_filter=status_filter,
                ),
            }
        )
    return results


def run_sheet_check(*, status_filter=None):
    return check_han_abbreviation_changes(status_filter=status_filter)
