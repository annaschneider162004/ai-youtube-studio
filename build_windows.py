from pathlib import Path
import os
import sys


def main():
    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise SystemExit(
            'PyInstaller chưa được cài. Hãy chạy: pip install -r requirements-build.txt'
        ) from exc

    root = Path(__file__).resolve().parent
    dist_dir = root / 'dist'
    build_dir = root / 'build'
    args = [
        '--noconfirm',
        '--clean',
        '--windowed',
        '--name',
        'AIYouTubeStudio',
        '--collect-all',
        'PySide6',
        '--add-data',
        f'{root / "config.example.json"}{os.pathsep}.',
        '--add-data',
        f'{root / "README.md"}{os.pathsep}.',
        '--distpath',
        str(dist_dir),
        '--workpath',
        str(build_dir),
        str(root / 'main.py'),
    ]
    PyInstaller.__main__.run(args)
    print(f'Build hoàn tất tại: {dist_dir / "AIYouTubeStudio"}', file=sys.stderr)


if __name__ == '__main__':
    main()
