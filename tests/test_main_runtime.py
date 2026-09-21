import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class MainRuntimeTests(unittest.TestCase):
    def test_runtime_layout_creates_data_logs_outputs_and_template(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'app-root'
            data = Path(temp_dir) / 'custom-data'
            root.mkdir(parents=True, exist_ok=True)
            (root / 'config.example.json').write_text('{"ok": true}', encoding='utf-8')
            with patch('main.app_root', return_value=root), patch.dict(os.environ, {'AIYS_DATA_DIR': str(data)}):
                _, data_dir = main.ensure_runtime_layout()

            self.assertEqual(data.resolve(), data_dir.resolve())
            self.assertTrue((data / 'logs').exists())
            self.assertTrue((data / 'outputs').exists())
            self.assertEqual('{"ok": true}', (data / 'config.example.json').read_text(encoding='utf-8'))

    def test_smoke_test_mode_exits_without_ui(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / 'app-root'
            data = Path(temp_dir) / 'data-dir'
            root.mkdir(parents=True, exist_ok=True)
            (root / 'config.example.json').write_text('{}', encoding='utf-8')
            with patch('main.app_root', return_value=root), patch.dict(os.environ, {'AIYS_DATA_DIR': str(data)}):
                rc = main.main(['--smoke-test'])
            self.assertEqual(0, rc)
            self.assertTrue((data / 'outputs').exists())


if __name__ == '__main__':
    unittest.main()
