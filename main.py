import sys

from PySide6.QtWidgets import QApplication
from interface_v101 import FFmpegGUI


def main():
    app = QApplication(sys.argv)
    window = FFmpegGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
