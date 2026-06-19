import argparse
import unittest
from unittest import mock

import build


class BuildMainMcpModeTests(unittest.TestCase):
    def test_all_sheet_mode_dispatches_to_export_module_and_returns_without_type(self):
        args = argparse.Namespace(mcp_mode='all_sheet', type=[], user='admin')

        with mock.patch('build.export_mcp_assets') as mock_export:
            build.main(args)

        mock_export.assert_called_once_with('all_sheet')


if __name__ == '__main__':
    unittest.main()
