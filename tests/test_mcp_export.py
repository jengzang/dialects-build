import unittest
from pathlib import Path
import tempfile
from unittest import mock

from source import mcp_export


class McpExportAllSheetTests(unittest.TestCase):
    def test_export_mcp_tables_fetches_and_resolves_requested_branch(self):
        command_results = {
            ('rev-parse', 'origin/wip'): mock.Mock(stdout='abc123\n'),
            ('ls-tree', '-r', '--name-only', 'abc123', '--', 'tools/tables/output'): mock.Mock(stdout=''),
        }

        def fake_run_git_command(args, **kwargs):
            return command_results.get(tuple(args), mock.Mock(stdout=''))

        with (
            mock.patch('source.mcp_export.ensure_mcp_cache'),
            mock.patch('source.mcp_export.run_git_command', side_effect=fake_run_git_command) as run_git,
            mock.patch('source.mcp_export.load_last_commit', return_value=None),
            mock.patch('source.mcp_export.has_exported_tsv_files', return_value=True),
        ):
            mcp_export.export_mcp_tables('full', branch='wip')

        run_git.assert_any_call(['fetch', 'origin', 'wip', '--quiet'], cwd=mcp_export.MCP_CACHE_DIR)
        run_git.assert_any_call(['rev-parse', 'origin/wip'], cwd=mcp_export.MCP_CACHE_DIR, capture_output=True)

    def test_build_sheet_history_entries_uses_requested_branch_in_first_page(self):
        seen_urls = []

        def fake_run_curl_text(url):
            seen_urls.append(url)
            return ''

        with mock.patch('source.mcp_export.run_curl_text', side_effect=fake_run_curl_text):
            entries = mcp_export.build_sheet_history_entries(branch='wip')

        self.assertEqual(entries, [])
        self.assertIn('/wip/log/', seen_urls[0])

    def test_export_all_sheet_history_writes_timestamped_xlsx_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / 'all_sheet'
            history_map_file = target_dir / '_history_map.json'
            fake_rows = [
                {'commit': 'a' * 40, 'commit_time': 1704067200, 'blob_path': 'tools/漢字音典字表檔案（長期更新）.xlsx'},
                {'commit': 'b' * 40, 'commit_time': 1704153605, 'blob_path': 'tools/漢字音典字表檔案（長期更新）.xlsx'},
            ]
            payloads = {
                'a' * 40: b'first-bytes',
                'b' * 40: b'second-bytes',
            }

            mcp_export.export_all_sheet_history(
                history_entries=fake_rows,
                blob_loader=lambda commit, blob_path: payloads[commit],
                target_dir=target_dir,
                history_map_file=history_map_file,
            )

            names = sorted(path.name for path in target_dir.glob('*.xlsx'))
            self.assertEqual(
                names,
                [
                    '漢字音典字表檔案（長期更新）-20240101-000000.xlsx',
                    '漢字音典字表檔案（長期更新）-20240102-000005.xlsx',
                ],
            )
            self.assertEqual((target_dir / names[0]).read_bytes(), b'first-bytes')
            self.assertEqual((target_dir / names[1]).read_bytes(), b'second-bytes')
            self.assertTrue(history_map_file.exists())

    def test_parse_sheet_history_page_returns_entries_and_older_link(self):
        html = '''
        <tr class="rev">
          <td><div><div class="grid-1"><input type="checkbox" class="revision" revision="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"></div></div></td>
          <td style="vertical-align: text-top">2025-12-13 02:26:29</td>
          <td><a class="download" rel="nofollow" href="/p/mcpdict/code/ci/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/tree/tools/漢字音典字表檔案（長期更新）.xlsx?format=raw">Download</a></td>
        </tr>
        <a class="page_list" href="/p/mcpdict/code/ci/olderrev/log/?path=%2Ftools%2F%E6%BC%A2%E5%AD%97%E9%9F%B3%E5%85%B8%E5%AD%97%E8%A1%A8%E6%AA%94%E6%A1%88%EF%BC%88%E9%95%B7%E6%9C%9F%E6%9B%B4%E6%96%B0%EF%BC%89.xlsx" rel="nofollow">Older &gt;</a>
        '''
        entries, next_url = mcp_export.parse_sheet_history_page(html, 'tools/漢字音典字表檔案（長期更新）.xlsx')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['commit'], 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
        self.assertEqual(next_url, 'https://sourceforge.net/p/mcpdict/code/ci/olderrev/log/?path=%2Ftools%2F%E6%BC%A2%E5%AD%97%E9%9F%B3%E5%85%B8%E5%AD%97%E8%A1%A8%E6%AA%94%E6%A1%88%EF%BC%88%E9%95%B7%E6%9C%9F%E6%9B%B4%E6%96%B0%EF%BC%89.xlsx')


if __name__ == '__main__':
    unittest.main()
