import tempfile
import unittest
from pathlib import Path

from source.extract_yindian import BOX_CHARS, extract_yindian_records


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


if __name__ == "__main__":
    unittest.main()
