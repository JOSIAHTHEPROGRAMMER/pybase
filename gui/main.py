import sys
import os


# Ensure pybase root is on the path so core/storage imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow

os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts=false"


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("PyBase")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run()