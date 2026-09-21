import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from app.db import Database
from app.ui.main_window import MainWindow

def main():
    Path('data').mkdir(exist_ok=True)
    Path('data/outputs').mkdir(parents=True, exist_ok=True)
    db=Database('data/studio.db')
    app=QApplication(sys.argv); app.setApplicationName('AI YouTube Studio V5')
    w=MainWindow(db); w.show(); sys.exit(app.exec())
if __name__=='__main__': main()
