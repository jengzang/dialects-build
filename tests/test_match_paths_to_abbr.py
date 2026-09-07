import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import pandas as pd

from source import tsv2sql
from source.check import match as match_check
from source.match_fromdb import (
    AmbiguousMatch,
    MatchClaim,
    MatchResolution,
    ShadowedMatch,
    match_paths_to_abbr,
)


def write_query_db(path, rows):
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE dialects (簡稱 TEXT, 音典分區 TEXT)")
        conn.executemany("INSERT INTO dialects (簡稱, 音典分區) VALUES (?, ?)", rows)


def touch_tsv(directory, stem):
    path = Path(directory) / f"{stem}.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#漢字\t音標\t解釋\n", encoding="utf-8")
    return str(path)


class MatchPathsToAbbrTests(unittest.TestCase):
    def test_empty_and_separator_paths_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("上猶群英", "客家話")])

            empty_result = match_paths_to_abbr([], query_db_path=str(db_path))
            separator_result = match_paths_to_abbr(["_"], query_db_path=str(db_path))

            for result in (empty_result, separator_result):
                self.assertEqual(result.accepted, {})
                self.assertEqual(result.shadowed, [])
                self.assertEqual(result.ambiguous, [])
                self.assertEqual(result.unmatched, [])

    def test_exact_claim_shadows_variant_claim(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("上猶群英", "客家話")])
            exact_path = touch_tsv(tmpdir, "上猶群英")
            variant_path = touch_tsv(tmpdir, "上猶羣英")

            result = match_paths_to_abbr([variant_path, exact_path], query_db_path=str(db_path))

            self.assertEqual(result.accepted[exact_path].abbr, "上猶群英")
            self.assertEqual([item.loser.path for item in result.shadowed], [variant_path])
            self.assertEqual(result.shadowed[0].winner.path, exact_path)
            self.assertEqual(result.ambiguous, [])

    def test_single_variant_claim_is_accepted_when_no_exact_owner_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("上猶群英", "客家話")])
            variant_path = touch_tsv(tmpdir, "上猶羣英")

            result = match_paths_to_abbr([variant_path], query_db_path=str(db_path))

            self.assertEqual(result.accepted[variant_path].abbr, "上猶群英")
            self.assertEqual(result.shadowed, [])
            self.assertEqual(result.ambiguous, [])

    def test_prefixed_xiamen_claim_matches_prefixed_abbr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("廈門", "閩語"), ("1883廈門", "閩語")])
            xiamen_path = touch_tsv(tmpdir, "1883厦門")

            result = match_paths_to_abbr([xiamen_path], query_db_path=str(db_path))

            self.assertEqual(result.accepted[xiamen_path].abbr, "1883廈門")
            self.assertEqual(result.ambiguous, [])

    def test_same_priority_variant_collision_uses_newest_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("上猶群英", "客家話")])
            first_path = touch_tsv(tmpdir, "上犹羣英")
            second_path = touch_tsv(tmpdir, "上犹群英")
            first_mtime = 1_700_000_000
            second_mtime = 1_700_000_100
            Path(first_path).touch()
            Path(second_path).touch()
            os.utime(first_path, (first_mtime, first_mtime))
            os.utime(second_path, (second_mtime, second_mtime))

            result = match_paths_to_abbr([first_path, second_path], query_db_path=str(db_path))

            self.assertEqual(result.accepted[second_path].abbr, "上猶群英")
            self.assertNotIn(first_path, result.accepted)
            self.assertEqual(result.ambiguous, [])
            self.assertEqual(result.shadowed[0].loser.path, first_path)
            self.assertEqual(result.shadowed[0].winner.path, second_path)
            self.assertEqual(result.shadowed[0].reason, "newer same-priority claim won")

    def test_same_priority_variant_collision_stays_ambiguous_when_mtime_ties(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("上猶群英", "客家話")])
            first_path = touch_tsv(tmpdir, "上犹羣英")
            second_path = touch_tsv(tmpdir, "上犹群英")
            tied_mtime = 1_700_000_000
            os.utime(first_path, (tied_mtime, tied_mtime))
            os.utime(second_path, (tied_mtime, tied_mtime))

            result = match_paths_to_abbr([first_path, second_path], query_db_path=str(db_path))

            self.assertEqual(result.accepted, {})
            self.assertEqual(len(result.ambiguous), 1)
            self.assertEqual(result.ambiguous[0].abbr, "上猶群英")
            self.assertEqual({claim.path for claim in result.ambiguous[0].claims}, {first_path, second_path})

    def test_one_path_matching_multiple_abbr_at_same_stage_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("發州", "A"), ("髮州", "B")])
            path = touch_tsv(tmpdir, "发州")

            result = match_paths_to_abbr([path], query_db_path=str(db_path))

            self.assertEqual(result.accepted, {})
            self.assertEqual(len(result.ambiguous), 1)
            self.assertEqual({claim.abbr for claim in result.ambiguous[0].claims}, {"發州", "髮州"})

    def test_update_prefers_incoming_same_stem_claim(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("上猶群英", "客家話")])
            existing_path = touch_tsv(Path(tmpdir) / "yindian", "上猶群英")
            incoming_path = touch_tsv(Path(tmpdir) / "pull_yindian", "上猶群英")

            result = match_paths_to_abbr(
                [existing_path, incoming_path],
                query_db_path=str(db_path),
                prefer_paths={incoming_path},
            )

            self.assertEqual(result.accepted[incoming_path].abbr, "上猶群英")
            self.assertNotIn(existing_path, result.accepted)
            self.assertEqual(result.shadowed[0].loser.path, existing_path)

    def test_update_variant_incoming_is_shadowed_by_existing_exact_claim(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("上猶群英", "客家話")])
            existing_path = touch_tsv(Path(tmpdir) / "yindian", "上猶群英")
            incoming_path = touch_tsv(Path(tmpdir) / "pull_yindian", "上猶羣英")

            result = match_paths_to_abbr(
                [existing_path, incoming_path],
                query_db_path=str(db_path),
                prefer_paths={incoming_path},
            )

            self.assertEqual(result.accepted[existing_path].abbr, "上猶群英")
            self.assertNotIn(incoming_path, result.accepted)
            self.assertEqual(result.shadowed[0].loser.path, incoming_path)
            self.assertEqual(result.shadowed[0].winner.path, existing_path)


class ProcessAll2SqlMatchGuardTests(unittest.TestCase):
    def test_process_all2sql_aborts_before_drop_when_ambiguous(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "dialects.db"
            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE dialects (簡稱 TEXT)")
                conn.execute("INSERT INTO dialects (簡稱) VALUES ('sentinel')")

            ambiguous = MatchResolution(
                ambiguous=[
                    AmbiguousMatch(
                        abbr="A",
                        claims=(),
                        reason="multiple same-priority claims for one abbreviation",
                    )
                ]
            )

            with (
                mock.patch("source.tsv2sql.match_paths_to_abbr", return_value=ambiguous),
                mock.patch("source.tsv2sql.write_match_decision_log"),
            ):
                with self.assertRaises(SystemExit):
                    tsv2sql.process_all2sql(["/tmp/a.tsv"], str(db_path), query_db_path="/tmp/query.db")

            with sqlite3.connect(db_path) as conn:
                rows = conn.execute("SELECT 簡稱 FROM dialects").fetchall()

            self.assertEqual(rows, [("sentinel",)])

    def test_process_all2sql_skips_shadowed_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "dialects.db"
            winner_path = touch_tsv(tmpdir, "上猶群英")
            loser_path = touch_tsv(tmpdir, "上猶羣英")
            winner = MatchClaim(
                path=winner_path,
                stem="上猶群英",
                abbr="上猶群英",
                partition="客家話",
                stage="exact",
                priority=0,
                source=Path(winner_path).parent.name,
            )
            loser = MatchClaim(
                path=loser_path,
                stem="上猶羣英",
                abbr="上猶群英",
                partition="客家話",
                stage="opencc_variant",
                priority=3,
                source=Path(loser_path).parent.name,
            )
            resolution = MatchResolution(
                accepted={winner_path: winner},
                shadowed=[
                    ShadowedMatch(
                        loser=loser,
                        winner=winner,
                        reason="lower-priority claim lost",
                    )
                ],
            )
            df = pd.DataFrame(
                [
                    {
                        "汉字": "一",
                        "音标": "i",
                        "声母": "",
                        "韵母": "i",
                        "声调": "陰平",
                        "註釋": "",
                    }
                ]
            )

            with (
                mock.patch("source.tsv2sql.match_paths_to_abbr", return_value=resolution),
                mock.patch("source.tsv2sql.write_match_decision_log"),
                mock.patch("source.tsv2sql.extract_all_from_files", return_value=df) as extract,
            ):
                tsv2sql.process_all2sql([loser_path, winner_path], str(db_path), query_db_path="/tmp/query.db")

            extract.assert_called_once_with(winner_path, query_db_path="/tmp/query.db")

    def test_process_all2sql_update_does_not_delete_shadowed_incoming(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "dialects.db"
            incoming_path = touch_tsv(Path(tmpdir) / "pull_yindian", "上猶羣英")
            existing = MatchClaim(
                path=str(Path(tmpdir) / "yindian" / "上猶群英.tsv"),
                stem="上猶群英",
                abbr="上猶群英",
                partition="客家話",
                stage="exact",
                priority=0,
                source="yindian",
            )
            incoming = MatchClaim(
                path=incoming_path,
                stem="上猶羣英",
                abbr="上猶群英",
                partition="客家話",
                stage="opencc_variant",
                priority=3,
                source="pull_yindian",
            )
            resolution = MatchResolution(
                accepted={},
                shadowed=[
                    ShadowedMatch(
                        loser=incoming,
                        winner=existing,
                        reason="lower-priority claim lost",
                    )
                ],
            )

            with sqlite3.connect(db_path) as conn:
                conn.execute("CREATE TABLE dialects (簡稱 TEXT)")
                conn.execute("INSERT INTO dialects (簡稱) VALUES ('上猶群英')")

            with (
                mock.patch("source.tsv2sql.write_match_decision_log"),
                mock.patch("source.tsv2sql.extract_all_from_files") as extract,
            ):
                processed = tsv2sql.process_all2sql(
                    [incoming_path],
                    str(db_path),
                    update=True,
                    query_db_path="/tmp/query.db",
                    match_resolution=resolution,
                )

            with sqlite3.connect(db_path) as conn:
                rows = conn.execute("SELECT 簡稱 FROM dialects").fetchall()

            self.assertEqual(processed, [])
            self.assertEqual(rows, [("上猶群英",)])
            extract.assert_not_called()

    def test_process_all2sql_append_empty_update_list_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "dialects.db"
            path = touch_tsv(tmpdir, "上猶群英")
            claim = MatchClaim(
                path=path,
                stem="上猶群英",
                abbr="上猶群英",
                partition="客家話",
                stage="exact",
                priority=0,
                source=Path(path).parent.name,
            )
            resolution = MatchResolution(accepted={path: claim})

            with (
                mock.patch("source.tsv2sql.write_match_decision_log"),
                mock.patch(
                    "source.tsv2sql.pd.read_excel",
                    return_value=pd.DataFrame({"簡稱": [], "待更新": []}),
                ),
                mock.patch("source.tsv2sql.extract_all_from_files") as extract,
            ):
                processed = tsv2sql.process_all2sql(
                    [path],
                    str(db_path),
                    append=True,
                    query_db_path="/tmp/query.db",
                    match_resolution=resolution,
                )

            with sqlite3.connect(db_path) as conn:
                rows = conn.execute("SELECT COUNT(*) FROM dialects").fetchone()

            self.assertEqual(processed, [])
            self.assertEqual(rows, (0,))
            extract.assert_not_called()

    def test_write_to_sql_update_matches_existing_and_incoming_before_write(self):
        existing_path = "data/yindian/上猶群英.tsv"
        incoming_path = "data/raw/pull_yindian/上猶群英.tsv"
        claim = mock.Mock()
        claim.abbr = "上猶群英"
        guard_resolution = MatchResolution(accepted={incoming_path: claim})

        with (
            mock.patch("source.tsv2sql.build_dialect_database", return_value=[existing_path]),
            mock.patch("source.tsv2sql.scan_update_directory", return_value=[incoming_path]),
            mock.patch("source.tsv2sql.match_paths_to_abbr", return_value=guard_resolution) as match_paths,
            mock.patch("source.tsv2sql.process_all2sql", return_value=["上猶群英"]) as process_all,
            mock.patch("source.tsv2sql.process_polyphonic_annotations_selective"),
            mock.patch("source.tsv2sql.sync_dialects_flags"),
        ):
            tsv2sql.write_to_sql(update=True, mode="admin")

        match_paths.assert_called_once()
        self.assertEqual(match_paths.call_args.args[0], [existing_path, incoming_path])
        self.assertEqual(match_paths.call_args.kwargs["prefer_paths"], {incoming_path})
        process_all.assert_called_once()
        self.assertEqual(process_all.call_args.args[0], [incoming_path])
        self.assertEqual(process_all.call_args.kwargs["match_resolution"].accepted[incoming_path].abbr, "上猶群英")


class MatchCheckReportTests(unittest.TestCase):
    def test_match_check_includes_shadowed_section(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "query.db"
            write_query_db(db_path, [("上猶群英", "客家話")])
            winner_path = touch_tsv(tmpdir, "上猶群英")
            loser_path = touch_tsv(tmpdir, "上猶羣英")
            claim = mock.Mock()
            claim.abbr = "上猶群英"
            resolution = MatchResolution(accepted={winner_path: claim})
            shadowed = mock.Mock()
            shadowed.loser.path = loser_path
            shadowed.loser.abbr = "上猶群英"
            shadowed.winner.path = winner_path
            shadowed.winner.stage = "exact"
            resolution.shadowed = [shadowed]

            with (
                mock.patch("source.check.match._iter_tsv_paths", return_value=[Path(winner_path), Path(loser_path)]),
                mock.patch("source.check.match._check_one_file", side_effect=[
                    {
                        "source": "tmp",
                        "filename": "上猶群英",
                        "matched": "上猶群英",
                        "partition": "客家話",
                        "status": "OK",
                        "path": winner_path,
                    },
                    {
                        "source": "tmp",
                        "filename": "上猶羣英",
                        "matched": "上猶群英",
                        "partition": "客家話",
                        "status": "OK",
                        "path": loser_path,
                    },
                ]),
                mock.patch("source.check.match.match_paths_to_abbr", return_value=resolution),
            ):
                output = StringIO()
                with redirect_stdout(output):
                    match_check.run_match_check(
                        query_db_path=str(db_path),
                        show_output=True,
                        use_pager=False,
                    )

            self.assertIn("【写库会跳过的 shadowed 文件】", output.getvalue())
            self.assertIn("上猶羣英.tsv -> 上猶群英", output.getvalue())


if __name__ == "__main__":
    unittest.main()
