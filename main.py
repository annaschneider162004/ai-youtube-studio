import os
import shutil
import sys
from pathlib import Path

from app.db import Database


def app_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_root():
    override = os.environ.get('AIYS_DATA_DIR', '').strip()
    if override:
        return Path(override).expanduser().resolve()
    return app_root() / 'data'


def ensure_runtime_layout():
    root = app_root()
    data_dir = data_root()
    logs_dir = data_dir / 'logs'
    outputs_dir = data_dir / 'outputs'
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    example_source = root / 'config.example.json'
    example_target = data_dir / 'config.example.json'
    if example_source.exists() and not example_target.exists():
        shutil.copyfile(example_source, example_target)
    return root, data_dir


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    _, data_dir = ensure_runtime_layout()
    if '--smoke-test' in argv:
        return 0

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from app.ui.main_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0], *argv])
    app.setApplicationName('AI YouTube Studio V5')
    db = Database(data_dir / 'studio.db')
    window = MainWindow(db)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
