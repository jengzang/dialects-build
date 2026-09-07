import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

from source.check import tone_match


def write_tsv(directory, name, rows):
    path = Path(directory) / f"{name}.tsv"
    with open(path, "w", encoding="utf-8") as f:
        f.write("#漢字\t音標\t解釋\n")
        for char, phonetic in rows:
            f.write(f"{char}\t{phonetic}\t\n")
    return str(path)


class ToneSimilarityTests(unittest.TestCase):
    def test_similarity_score_uses_coverage_weight_point_two(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = tone_match.load_similarity_profile(
                write_tsv(tmpdir, "target", [("一", "pa1"), ("二", "ta2"), ("三", "ka3")])
            )
            candidate = tone_match.load_similarity_profile(
                write_tsv(tmpdir, "candidate", [("一", "pa1"), ("二", "ta5"), ("四", "xa4")])
            )

            score = tone_match.score_similarity_profiles(target, candidate)

            self.assertAlmostEqual(score["coverage"], 2 / 3)
            self.assertAlmostEqual(score["jaccard"], 2 / 4)
            self.assertAlmostEqual(score["syllable_match_rate"], 1 / 2)
            self.assertAlmostEqual(score["initial_match_rate"], 1)
            self.assertAlmostEqual(score["final_match_rate"], 1)
            self.assertAlmostEqual(score["tone_match_rate"], 1 / 2)
            self.assertAlmostEqual(
                score["score"],
                0.20 * (2 / 3) + 0.25 * (1 / 2) + 0.15 + 0.15 + 0.10 * (1 / 2),
            )

    def test_attach_no_tone_similarity_excludes_no_tone_candidates_and_keeps_top_three(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = write_tsv(
                tmpdir,
                "target",
                [("一", "pa1"), ("二", "ta2"), ("三", "ka3"), ("四", "sa4")],
            )
            no_tone_peer_path = write_tsv(
                tmpdir,
                "no_tone_peer",
                [("一", "pa1"), ("二", "ta2"), ("三", "ka3"), ("四", "sa4")],
            )
            best_path = write_tsv(
                tmpdir,
                "best",
                [("一", "pa1"), ("二", "ta2"), ("三", "ka5"), ("五", "xa1")],
            )
            second_path = write_tsv(
                tmpdir,
                "second",
                [("一", "pa1"), ("二", "la2"), ("六", "xa1")],
            )
            third_path = write_tsv(
                tmpdir,
                "third",
                [("三", "ka3"), ("七", "xa1")],
            )
            fourth_path = write_tsv(
                tmpdir,
                "fourth",
                [("八", "xa1")],
            )
            no_tone_rows = [
                {
                    "簡稱": "target",
                    "tsv_files": [{"path": target_path}],
                },
                {
                    "簡稱": "no_tone_peer",
                    "tsv_files": [{"path": no_tone_peer_path}],
                },
            ]
            matched_rows = [
                {"matched": "target", "path": target_path},
                {"matched": "no_tone_peer", "path": no_tone_peer_path},
                {"matched": "best", "path": best_path},
                {"matched": "second", "path": second_path},
                {"matched": "third", "path": third_path},
                {"matched": "fourth", "path": fourth_path},
            ]

            tone_match.attach_no_tone_similarity(no_tone_rows, matched_rows, top_n=3)

            top = no_tone_rows[0]["similar_tsvs"]
            self.assertEqual([row["簡稱"] for row in top], ["third", "best", "second"])
            self.assertNotIn("no_tone_peer", [row["簡稱"] for row in top])
            self.assertTrue(all("score" in row for row in top))
            self.assertEqual(
                [row["score"] for row in top],
                sorted([row["score"] for row in top], reverse=True),
            )

    def test_attach_no_tone_similarity_prefilters_before_full_profile_loading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_path = write_tsv(tmpdir, "target", [("一", "pa1"), ("二", "ta2")])
            related_path = write_tsv(tmpdir, "related", [("一", "pa1")])
            unrelated_paths = [
                write_tsv(tmpdir, f"unrelated{i}", [(chr(0x4E09 + i), "xa1")])
                for i in range(5)
            ]
            no_tone_rows = [
                {
                    "簡稱": "target",
                    "tsv_files": [{"path": target_path}],
                },
            ]
            matched_rows = [
                {"matched": "target", "path": target_path},
                {"matched": "related", "path": related_path},
                *[
                    {"matched": f"unrelated{i}", "path": path}
                    for i, path in enumerate(unrelated_paths)
                ],
            ]

            with mock.patch(
                "source.check.tone_match.load_similarity_profile",
                wraps=tone_match.load_similarity_profile,
            ) as load_profile:
                tone_match.attach_no_tone_similarity(
                    no_tone_rows,
                    matched_rows,
                    top_n=1,
                    prefilter_limit=1,
                )

            self.assertEqual([row["簡稱"] for row in no_tone_rows[0]["similar_tsvs"]], ["related"])
            self.assertLessEqual(load_profile.call_count, 2)

    def test_attach_old_tone_info_finds_matching_shortname_in_old_workbook(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_workbook = Path(tmpdir) / "old.xlsx"
            pd.DataFrame(
                [
                    {"簡稱": "target", "[1]陰平": "55", "[2]陽平": ""},
                    {"簡稱": "other", "[1]陰平": "", "[2]陽平": "21"},
                ]
            ).to_excel(old_workbook, index=False)
            no_tone_rows = [{"簡稱": "target"}]

            tone_match.attach_old_tone_info(
                no_tone_rows,
                old_workbook_paths=[old_workbook],
                tone_columns=["[1]陰平", "[2]陽平"],
            )

            old_tone_info = no_tone_rows[0]["old_tone_info"]
            self.assertEqual(len(old_tone_info), 1)
            self.assertEqual(old_tone_info[0]["old_file"], "old.xlsx")
            self.assertEqual(old_tone_info[0]["tone_values"], {"[1]陰平": "55"})


if __name__ == "__main__":
    unittest.main()
