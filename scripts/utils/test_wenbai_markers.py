import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from common.wenbai_rules import (
    WEN_BAI_COLLOQUIAL_MARK,
    WEN_BAI_LITERARY_MARK,
    detect_wenbai_from_note,
    merge_wenbai_markers,
    split_wenbai_marker,
)
from source.tsv2sql import apply_polyphonic_labels


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_split_wenbai_marker():
    assert_equal(split_wenbai_marker('jau1='), ('jau1', WEN_BAI_LITERARY_MARK), 'tail = -> 2')
    assert_equal(split_wenbai_marker('jau1-'), ('jau1', WEN_BAI_COLLOQUIAL_MARK), 'tail - -> 3')
    assert_equal(split_wenbai_marker('jau1'), ('jau1', ''), 'plain syllable unchanged')


def test_detect_wenbai_from_note():
    literary_notes = [
        '文讀',
        '文读,~产党',
        '文',
        '~通,~钱[文]',
        '命令（文）',
        '讀書音',
        '读书音',
    ]
    colloquial_notes = [
        '白讀',
        '白读,~抢',
        '白',
        '是[白]',
        '~相帮助(白)',
    ]
    neutral_notes = [
        '白面~:獾猪',
        '原文作“宽”,有误',
        '口语,声音大',
    ]

    for note in literary_notes:
        assert_equal(detect_wenbai_from_note(note), WEN_BAI_LITERARY_MARK, f'literary note {note}')
    for note in colloquial_notes:
        assert_equal(detect_wenbai_from_note(note), WEN_BAI_COLLOQUIAL_MARK, f'colloquial note {note}')
    for note in neutral_notes:
        assert_equal(detect_wenbai_from_note(note), '', f'neutral note {note}')


def test_merge_wenbai_markers_priority():
    assert_equal(merge_wenbai_markers('2', '3'), '2', 'primary 2 wins over note 3')
    assert_equal(merge_wenbai_markers('3', '2'), '3', 'primary 3 wins over note 2')
    assert_equal(merge_wenbai_markers('', '2'), '2', 'note 2 fills empty primary')
    assert_equal(merge_wenbai_markers('', '3'), '3', 'note 3 fills empty primary')
    assert_equal(merge_wenbai_markers('1', '2'), '1', 'existing polyphonic 1 is preserved')


def test_apply_polyphonic_labels_priority():
    df = pd.DataFrame([
        {'簡稱': 'A', '漢字': '交', '音節': 'kau1', '多音字': '2'},
        {'簡稱': 'A', '漢字': '交', '音節': 'kɔ1', '多音字': '3'},
        {'簡稱': 'A', '漢字': '分', '音節': 'fɐn1', '多音字': '2'},
        {'簡稱': 'A', '漢字': '分', '音節': 'fan1', '多音字': ''},
        {'簡稱': 'A', '漢字': '會', '音節': 'wui6', '多音字': ''},
        {'簡稱': 'A', '漢字': '會', '音節': 'fui6', '多音字': ''},
        {'簡稱': 'A', '漢字': '單', '音節': 'taan1', '多音字': ''},
    ])

    result = apply_polyphonic_labels(df, ['簡稱', '漢字'])
    actual = list(result[['漢字', '音節', '多音字']].itertuples(index=False, name=None))
    expected = [
        ('交', 'kau1', '2'),
        ('交', 'kɔ1', '3'),
        ('分', 'fɐn1', '2'),
        ('分', 'fan1', '1'),
        ('會', 'wui6', '1'),
        ('會', 'fui6', '1'),
        ('單', 'taan1', ''),
    ]
    assert_equal(actual, expected, 'apply_polyphonic_labels result')


if __name__ == '__main__':
    test_split_wenbai_marker()
    test_detect_wenbai_from_note()
    test_merge_wenbai_markers_priority()
    test_apply_polyphonic_labels_priority()
    print('wenbai marker tests passed')
