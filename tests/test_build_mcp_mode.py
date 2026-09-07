import argparse
import unittest
from unittest import mock

import build


class BuildMainMcpModeTests(unittest.TestCase):
    def test_parser_defaults_to_master_and_accepts_wip_branch(self):
        parser = build.create_parser()

        default_args = parser.parse_args(['-m', 'diff'])
        wip_args = parser.parse_args(['-m', 'diff', '--branch', 'wip'])

        self.assertEqual(default_args.mcp_branch, 'master')
        self.assertEqual(wip_args.mcp_branch, 'wip')

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
