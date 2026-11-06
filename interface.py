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
    QLineEdit,
    QProgressBar,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from converter import ConversionWorker, locate_ffmpeg

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
        self.worker = None
        self.conversion_active = False
        self.ffmpeg_path = self.settings.value("ffmpeg_path", "") or locate_ffmpeg()

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

        ffmpeg_group = QGroupBox("FFmpeg et paramètres de conversion")
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)
        executable_row = QHBoxLayout()
        self.ffmpeg_edit = QLineEdit(self.ffmpeg_path)
        self.ffmpeg_edit.setPlaceholderText("Chemin vers ffmpeg.exe")
        self.ffmpeg_browse = QPushButton("Parcourir...")
        executable_row.addWidget(QLabel("FFmpeg :"))
        executable_row.addWidget(self.ffmpeg_edit, 1)
        executable_row.addWidget(self.ffmpeg_browse)
        ffmpeg_layout.addLayout(executable_row)
        self.encoding_info = QLabel(
            "Sortie : MKV  |  Vidéo : H.265 / CRF 28 / medium  |  "
            "Audio et sous-titres : copie"
        )
        self.encoding_info.setWordWrap(True)
        ffmpeg_layout.addWidget(self.encoding_info)
        main_layout.addWidget(ffmpeg_group)

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

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Nom du fichier", "Dossier source", "Format", "Taille", "État", "Progression"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        main_layout.addWidget(self.table, 1)

        self.summary_label = QLabel("0 vidéo sélectionnée")
        main_layout.addWidget(self.summary_label)

        conversion_row = QHBoxLayout()
        self.start_button = QPushButton("Lancer les conversions")
        self.cancel_button = QPushButton("Annuler")
        self.start_button.setMinimumHeight(40)
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.setEnabled(False)
        conversion_row.addWidget(self.start_button)
        conversion_row.addWidget(self.cancel_button)
        conversion_row.addStretch()
        main_layout.addLayout(conversion_row)
        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 100)
        self.batch_progress.setValue(0)
        main_layout.addWidget(self.batch_progress)

        self.import_button.clicked.connect(self.import_videos)
        self.folder_button.clicked.connect(self.import_folder)
        self.output_button.clicked.connect(self.select_output_dir)
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button.clicked.connect(self.clear_videos)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.ffmpeg_browse.clicked.connect(self.select_ffmpeg)
        self.ffmpeg_edit.editingFinished.connect(self.remember_ffmpeg)
        self.start_button.clicked.connect(self.start_conversion)
        self.cancel_button.clicked.connect(self.cancel_conversion)

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
            self.table.setItem(row, 4, QTableWidgetItem("En attente"))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            self.table.setCellWidget(row, 5, bar)
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
        self.clear_button.setEnabled(count > 0 and not self.is_converting())
        self.remove_button.setEnabled(bool(self.table.selectedIndexes()) and not self.is_converting())
        self.import_button.setEnabled(not self.is_converting())
        self.folder_button.setEnabled(not self.is_converting())
        self.output_button.setEnabled(not self.is_converting())
        self.ffmpeg_edit.setEnabled(not self.is_converting())
        self.ffmpeg_browse.setEnabled(not self.is_converting())
        self.start_button.setEnabled(count > 0 and not self.is_converting())

    def is_converting(self):
        return self.conversion_active

    def select_ffmpeg(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Sélectionner FFmpeg", self.ffmpeg_edit.text() or self.last_input_dir,
            "Exécutable FFmpeg (ffmpeg.exe);;Tous les fichiers (*)",
        )
        if filename:
            self.ffmpeg_edit.setText(filename)
            self.remember_ffmpeg()

    def remember_ffmpeg(self):
        self.ffmpeg_path = self.ffmpeg_edit.text().strip().strip('"')
        self.settings.setValue("ffmpeg_path", self.ffmpeg_path)

    def start_conversion(self):
        if self.is_converting() or not self.video_paths:
            return
        self.remember_ffmpeg()
        if not Path(self.ffmpeg_path).is_file():
            QMessageBox.warning(self, "FFmpeg", "Sélectionne un fichier ffmpeg.exe valide.")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "Dossier de sortie", "Choisis un dossier de sortie.")
            return
        if any(self.path_key(path) == self.path_key(Path(self.output_dir) / (Path(path).stem + ".mkv")) for path in self.video_paths):
            QMessageBox.warning(self, "Dossier de sortie", "Le fichier de destination ne doit pas être le fichier source.")
            return

        self.batch_progress.setValue(0)
        for row in range(self.table.rowCount()):
            self.table.item(row, 4).setText("En attente")
            self.table.cellWidget(row, 5).setValue(0)
        self.worker = ConversionWorker(self.video_paths, self.output_dir, self.ffmpeg_path, self)
        self.worker.state_changed.connect(self.on_file_state)
        self.worker.progress_changed.connect(self.on_file_progress)
        self.worker.batch_finished.connect(self.on_batch_finished)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.conversion_active = True
        self.cancel_button.setEnabled(True)
        self.update_actions()
        self.worker.start()
        self.update_actions()
        self.statusBar().showMessage("Conversions en cours...")

    def cancel_conversion(self):
        if self.is_converting():
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("Annulation demandée...")
            self.worker.request_cancel()

    def on_file_state(self, index, state):
        if index < self.table.rowCount():
            self.table.item(index, 4).setText(state)

    def on_file_progress(self, index, percentage):
        if index < self.table.rowCount():
            self.table.cellWidget(index, 5).setValue(percentage)
        total = self.table.rowCount()
        if total:
            progress_sum = sum(self.table.cellWidget(i, 5).value() for i in range(total))
            self.batch_progress.setValue(round(progress_sum / total))

    def on_batch_finished(self, done, skipped, failed, cancelled, errors):
        self.cancel_button.setEnabled(False)
        # La fin du thread suit immédiatement l'émission de batch_finished.
        self.start_button.setEnabled(False)
        self.statusBar().showMessage("Lot annulé" if cancelled else "Lot terminé")
        message = (
            f"Converties : {done}\nDéjà présentes : {skipped}\n"
            f"Erreurs : {failed}"
        )
        if cancelled:
            message += "\nConversion annulée."
        if errors:
            message += "\n\n" + "\n".join(errors[:5])
        QMessageBox.information(self, "Résultat des conversions", message)

    def on_worker_finished(self):
        self.conversion_active = False
        self.worker = None
        self.update_actions()

    def closeEvent(self, event):
        if self.is_converting():
            QMessageBox.information(
                self, "Conversion en cours",
                "Annule d'abord le traitement et attends sa fin avant de fermer."
            )
            event.ignore()
        else:
            event.accept()
