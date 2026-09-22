import csv
import tempfile
import unittest
from pathlib import Path

from source.extract_yindian import (
    BOX_CHARS,
    extract_yindian_records,
    extract_yindian_words,
)


class ExtractYindianRecordsTests(unittest.TestCase):
    def test_recognizes_all_supported_box_variants(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "pull_yindian"
            output_root = root / "extract"
            source_dir.mkdir()
            rows = "".join(f"{char}\tka1\t\n" for char in sorted(BOX_CHARS))
            (source_dir / "甲地.tsv").write_text(
                "#漢字\t音標\t解釋\n" + rows,
                encoding="utf-8",
            )

            result = extract_yindian_records(
                source_dir,
                vocabulary=True,
                output_root=output_root,
            )

            self.assertEqual(result["vocabulary"]["甲地.tsv"], len(BOX_CHARS))

    def test_extracts_each_mode_per_location_and_preserves_original_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "pull_yindian"
            output_root = root / "extract"
            source_dir.mkdir()

            (source_dir / "甲地.tsv").write_text(
                "#漢字\t音標\t解釋\t備註\n"
                "□\tka1\t~拄棒:拐杖\tone\n"
                "■\ttʊ1\t\t\n"
                "☑\tto1\t  \t\n"
                "一\ti1\t普通字\t\n"
                "二\tti1\t\t\n",
                encoding="utf-8",
            )
            (source_dir / "乙地.tsv").write_text(
                "#漢字\t音標\t解釋\t備註\n"
                "一\ti1\t\t\n",
                encoding="utf-8",
            )

            result = extract_yindian_records(
                source_dir,
                vocabulary=True,
                note=True,
                output_root=output_root,
            )

            vocabulary_path = output_root / "vocabulary" / "甲地.tsv"
            note_path = output_root / "note" / "甲地.tsv"

            self.assertEqual(result["vocabulary"]["甲地.tsv"], 3)
            self.assertEqual(result["note"]["甲地.tsv"], 2)
            self.assertTrue(vocabulary_path.exists())
            self.assertTrue(note_path.exists())
            self.assertFalse((output_root / "vocabulary" / "乙地.tsv").exists())
            self.assertFalse((output_root / "note" / "乙地.tsv").exists())

            self.assertEqual(
                vocabulary_path.read_text(encoding="utf-8"),
                "#漢字\t音標\t解釋\t備註\n"
                "□\tka1\t~拄棒:拐杖\tone\n"
                "■\ttʊ1\t\t\n"
                "☑\tto1\t  \t\n",
            )
            self.assertEqual(
                note_path.read_text(encoding="utf-8"),
                "#漢字\t音標\t解釋\t備註\n"
                "□\tka1\t~拄棒:拐杖\tone\n"
                "一\ti1\t普通字\t\n",
            )

    def test_clears_selected_output_directories_before_rebuilding(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "pull_yindian"
            output_root = root / "extract"
            source_dir.mkdir()
            vocabulary_dir = output_root / "vocabulary"
            note_dir = output_root / "note"
            vocabulary_dir.mkdir(parents=True)
            note_dir.mkdir(parents=True)
            (vocabulary_dir / "過期.tsv").write_text("old", encoding="utf-8")
            (note_dir / "保留.tsv").write_text("old", encoding="utf-8")
            (source_dir / "甲地.tsv").write_text(
                "#漢字\t音標\t解釋\n□\tka1\t\n",
                encoding="utf-8",
            )

            extract_yindian_records(
                source_dir,
                vocabulary=True,
                output_root=output_root,
            )

            self.assertFalse((vocabulary_dir / "過期.tsv").exists())
            self.assertTrue((note_dir / "保留.tsv").exists())

    def test_extracts_word_candidates_with_types_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "pull_yindian"
            output_root = root / "extract"
            source_dir.mkdir()

            (source_dir / "甲地.tsv").write_text(
                "#漢字\t音標\t解釋\n"
                "㗦\tlu4\t~嘈,吵鬧\n"
                "□\tsɔ1\t～腰:脊背微駝\n"
                "一\ti1\t这条注释没有占位符，但保留待审查\n"
                "二\tti1\t   \n",
                encoding="utf-8",
            )

            result = extract_yindian_words(
                source_dir,
                output_root=output_root,
            )

            output_path = output_root / "word" / "甲地.tsv"
            self.assertEqual(result["甲地.tsv"], 3)
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                "标准词\t方言词\t音标\t注释\ttype\t原始汉字\t来源文件\t原始行号\n"
                "\t㗦嘈\tlu4\t~嘈,吵鬧\ttilde\t㗦\t甲地.tsv\t2\n"
                "\t□腰\tsɔ1\t～腰:脊背微駝\ttilde\t□\t甲地.tsv\t3\n"
                "\t\ti1\t这条注释没有占位符，但保留待审查\tnote\t一\t甲地.tsv\t4\n",
            )

    def test_word_candidates_keep_multiple_tilde_clauses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "pull_yindian"
            output_root = root / "extract"
            source_dir.mkdir()
            (source_dir / "甲地.tsv").write_text(
                "#漢字\t音標\t解釋\n"
                "□\tka1\t~出来:突出;~~头:突出的部分\n",
                encoding="utf-8",
            )

            result = extract_yindian_words(
                source_dir,
                output_root=output_root,
            )

            self.assertEqual(result["甲地.tsv"], 2)
            self.assertEqual(
                (output_root / "word" / "甲地.tsv").read_text(encoding="utf-8"),
                "标准词\t方言词\t音标\t注释\ttype\t原始汉字\t来源文件\t原始行号\n"
                "\t□出来\tka1\t~出来:突出;~~头:突出的部分\ttilde\t□\t甲地.tsv\t2\n"
                "\t□□头\tka1\t~出来:突出;~~头:突出的部分\ttilde\t□\t甲地.tsv\t2\n",
            )

    def test_word_candidates_ignore_date_and_numeric_range_tildes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "pull_yindian"
            output_root = root / "extract"
            source_dir.mkdir()
            (source_dir / "甲地.tsv").write_text(
                "#漢字\t音標\t解釋\n"
                "明\tmin2\t朝代名（西元1368年~西元1644年）\n"
                "一\ti1\t第一至第三声（1~3）\n"
                "□\tka1\t~腰:脊背\n",
                encoding="utf-8",
            )

            extract_yindian_words(source_dir, output_root=output_root)

            with (output_root / "word" / "甲地.tsv").open(
                encoding="utf-8",
                newline="",
            ) as output_file:
                rows = list(csv.DictReader(output_file, delimiter="\t"))
            self.assertEqual(len(rows), 3)
            self.assertEqual([row["type"] for row in rows], ["note", "note", "tilde"])
            self.assertEqual(rows[0]["方言词"], "")
            self.assertEqual(rows[1]["方言词"], "")
            self.assertEqual(rows[2]["方言词"], "□腰")

    def test_word_candidates_skip_non_character_and_historical_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_dir = root / "pull_yindian"
            output_root = root / "extract"
            source_dir.mkdir()

            source_files = {
                "固原.tsv": "#詞語\t音標\t解釋\n词\ttsɿ1\t~词\n",
                "1926綜合.tsv": "#漢字\t音標\t解釋\n□\ttsɿ1\t~词\n",
                "清末蘇州.tsv": "#漢字\t音標\t解釋\n□\ttsɿ1\t~词\n",
                "中唐.tsv": "#漢字\t音標\t解釋\n□\ttsɿ1\t~词\n",
                "廣韻.tsv": "#漢字\t音標\t解釋\n□\ttsɿ1\t~词\n",
                "甲地.tsv": "#漢字\t音標\t解釋\n□\ttsɿ1\t~词\n",
            }
            for filename, content in source_files.items():
                (source_dir / filename).write_text(content, encoding="utf-8")

            result = extract_yindian_words(
                source_dir,
                output_root=output_root,
            )

            self.assertEqual(result, {"甲地.tsv": 1})
            self.assertTrue((output_root / "word" / "甲地.tsv").exists())
            self.assertFalse((output_root / "word" / "固原.tsv").exists())
            self.assertFalse((output_root / "word" / "1926綜合.tsv").exists())
            self.assertFalse((output_root / "word" / "清末蘇州.tsv").exists())
            self.assertFalse((output_root / "word" / "中唐.tsv").exists())
            self.assertFalse((output_root / "word" / "廣韻.tsv").exists())

if __name__ == "__main__":
    unittest.main()
