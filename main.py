
import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
)


class FFmpegGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("FFmpeg GUI")
        self.resize(1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        title = QLabel("FFmpeg GUI")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.import_button = QPushButton("Importer des vidéos")
        self.import_button.setMinimumHeight(40)

        layout.addWidget(title)
        layout.addWidget(self.import_button)
        layout.addStretch()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = FFmpegGUI()
    window.show()

    sys.exit(app.exec())
