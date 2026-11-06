import os
from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

VIDEO_EXTENSIONS = {".mkv", ".mp4"}


class FFmpegGUI(QMainWindow):
    """Étape 1 : préparer une liste de vidéos et un dossier de sortie."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFmpeg GUI")
        self.resize(1250, 800)

        self.settings = QSettings("Deklou", "FFmpegGUI")
        self.last_input_dir = self.settings.value("last_input_dir", str(Path.home()))
        self.output_dir = self.settings.value("output_dir", "")
        self.video_paths = []
        self.video_keys = set()

        self.setup_ui()
        self.update_paths()
        self.update_actions()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        title = QLabel("FFmpeg GUI")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        main_layout.addWidget(title)

        paths_group = QGroupBox("Fichiers et dossiers")
        paths_layout = QVBoxLayout(paths_group)

        buttons_layout = QHBoxLayout()
        self.import_button = QPushButton("Ajouter des vidéos")
        self.folder_button = QPushButton("Ajouter un dossier")
        self.output_button = QPushButton("Dossier de sortie")
        for button in (self.import_button, self.folder_button, self.output_button):
            button.setMinimumHeight(40)
            buttons_layout.addWidget(button)
        buttons_layout.addStretch()
        paths_layout.addLayout(buttons_layout)

        self.input_label = QLabel()
        self.output_label = QLabel()
        for label in (self.input_label, self.output_label):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setStyleSheet("padding: 8px; border: 1px solid #555; border-radius: 5px;")
            paths_layout.addWidget(label)

        main_layout.addWidget(paths_group)

        queue_header = QHBoxLayout()
        queue_title = QLabel("Vidéos sélectionnées")
        queue_title.setStyleSheet("font-size: 17px; font-weight: bold;")
        queue_header.addWidget(queue_title)
        queue_header.addStretch()

        self.remove_button = QPushButton("Retirer la sélection")
        self.clear_button = QPushButton("Tout vider")
        queue_header.addWidget(self.remove_button)
        queue_header.addWidget(self.clear_button)
        main_layout.addLayout(queue_header)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nom du fichier", "Dossier source", "Format", "Taille"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        main_layout.addWidget(self.table, 1)

        self.summary_label = QLabel("0 vidéo sélectionnée")
        main_layout.addWidget(self.summary_label)

        info_label = QLabel(
            "Étape 1 : sélection des vidéos. Les réglages FFmpeg et la conversion arriveront ensuite."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #999;")
        main_layout.addWidget(info_label)

        self.import_button.clicked.connect(self.import_videos)
        self.folder_button.clicked.connect(self.import_folder)
        self.output_button.clicked.connect(self.select_output_dir)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear_videos)
        self.table.itemSelectionChanged.connect(self.update_actions)

    @staticmethod
    def path_key(path):
        return os.path.normcase(os.path.abspath(path))

    @staticmethod
    def format_size(size):
        if size < 1024:
            return f"{size} o"
        if size < 1024**2:
            return f"{size / 1024:.1f} Ko"
        if size < 1024**3:
            return f"{size / 1024**2:.1f} Mo"
        return f"{size / 1024**3:.2f} Go"

    def import_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Sélectionner des vidéos", self.last_input_dir, "Vidéos (*.mkv *.mp4)"
        )
        if not paths:
            return
        self.remember_input_dir(str(Path(paths[0]).parent))
        added = self.add_paths(paths)
        self.statusBar().showMessage(f"{added} vidéo(s) ajoutée(s)")

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Sélectionner un dossier de vidéos", self.last_input_dir
        )
        if not folder:
            return
        self.remember_input_dir(folder)
        try:
            paths = sorted(
                (
                    str(path)
                    for path in Path(folder).iterdir()
                    if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
                ),
                key=str.casefold,
            )
        except OSError as exc:
            self.statusBar().showMessage(f"Lecture du dossier impossible : {exc}")
            return
        added = self.add_paths(paths)
        self.statusBar().showMessage(f"{added} vidéo(s) ajoutée(s) depuis ce dossier")

    def remember_input_dir(self, folder):
        self.last_input_dir = folder
        self.settings.setValue("last_input_dir", folder)
        self.update_paths()

    def select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choisir le dossier de sortie", self.output_dir or self.last_input_dir
        )
        if folder:
            self.output_dir = folder
            self.settings.setValue("output_dir", folder)
            self.update_paths()

    def add_paths(self, paths):
        added = 0
        for raw_path in paths:
            path = Path(raw_path)
            key = self.path_key(path)
            if key in self.video_keys or path.suffix.lower() not in VIDEO_EXTENSIONS or not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue

            self.video_paths.append(str(path))
            self.video_keys.add(key)

            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(path.name)
            name_item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(path.parent)))
            self.table.setItem(row, 2, QTableWidgetItem(path.suffix.lower()))
            self.table.setItem(row, 3, QTableWidgetItem(self.format_size(size)))
            added += 1
        self.update_paths()
        self.update_actions()
        return added

    def remove_selected(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            item = self.table.item(row, 0)
            path = item.data(Qt.ItemDataRole.UserRole) if item else None
            if path:
                self.video_keys.discard(self.path_key(path))
                self.video_paths = [
                    existing for existing in self.video_paths
                    if self.path_key(existing) != self.path_key(path)
                ]
            self.table.removeRow(row)
        self.update_paths()
        self.update_actions()

    def clear_videos(self):
        self.video_paths.clear()
        self.video_keys.clear()
        self.table.setRowCount(0)
        self.update_paths()
        self.update_actions()

    def update_paths(self):
        source_folders = sorted(
            {str(Path(path).parent) for path in self.video_paths}, key=str.casefold
        )
        if len(source_folders) == 1:
            source = source_folders[0]
        elif len(source_folders) > 1:
            source = f"Plusieurs dossiers ({len(source_folders)})"
        else:
            source = self.last_input_dir or "Non sélectionné"

        self.input_label.setText(f"Dossier(s) d'entrée : {source}")
        self.input_label.setToolTip("\n".join(source_folders) if source_folders else source)
        output = self.output_dir or "Non sélectionné"
        self.output_label.setText(f"Dossier de sortie : {output}")
        self.output_label.setToolTip(output)

    def update_actions(self):
        count = len(self.video_paths)
        self.summary_label.setText(
            f"{count} vidéo{'s' if count > 1 else ''} sélectionnée{'s' if count > 1 else ''}"
        )
        self.remove_button.setEnabled(bool(self.table.selectedIndexes()))
        self.clear_button.setEnabled(count > 0)
