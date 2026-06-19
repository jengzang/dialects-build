import unittest
from pathlib import Path
import tempfile

from source import mcp_export


class McpExportAllSheetTests(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
