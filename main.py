"""Point d'entrée de FFmpeg GUI."""
import sys
from PySide6.QtWidgets import QApplication
from interface import FFmpegGUI


def main():
    app = QApplication(sys.argv)
    window = FFmpegGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
