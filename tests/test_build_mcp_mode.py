import argparse
import unittest
from unittest import mock

import build


class BuildMainMcpModeTests(unittest.TestCase):
    def test_parser_defaults_to_master_and_accepts_wip_branch(self):
        parser = build.create_parser()

        default_args = parser.parse_args(['-m', 'diff'])
        wip_args = parser.parse_args(['-m', 'diff', '--branch', 'wip'])
        extract_args = parser.parse_args(['-v', '-n'])

        self.assertEqual(default_args.mcp_branch, 'master')
        self.assertEqual(wip_args.mcp_branch, 'wip')
        self.assertTrue(extract_args.vocabulary)
        self.assertTrue(extract_args.note)

    def test_vocabulary_only_dispatches_extraction_without_default_database_write(self):
        args = argparse.Namespace(
            mcp_mode=None,
            mcp_branch='master',
            type=[],
            check=[],
            user='admin',
            vocabulary=True,
            note=False,
        )

        with mock.patch('build.extract_yindian_records') as extract:
            build.main(args)

        extract.assert_called_once()

    def test_word_only_dispatches_word_extraction_without_default_database_write(self):
        args = argparse.Namespace(
            mcp_mode=None,
            mcp_branch='master',
            type=[],
            check=[],
            user='admin',
            vocabulary=False,
            note=False,
            word=True,
        )

        with mock.patch('build.extract_yindian_words') as extract:
            build.main(args)

        extract.assert_called_once()

    def test_all_sheet_mode_dispatches_to_export_module_and_returns_without_type(self):
        args = argparse.Namespace(
            mcp_mode='all_sheet',
            mcp_branch='wip',
            type=[],
            check=[],
            user='admin',
        )

        with mock.patch('build.export_mcp_assets') as mock_export:
            build.main(args)

        mock_export.assert_called_once_with('all_sheet', branch='wip')


if __name__ == '__main__':
    unittest.main()
