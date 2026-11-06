import os
from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QSpinBox,
    QInputDialog,
    QFormLayout,
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
from conversion_settings import ConversionSettings
from presets import PresetStore, BUILTIN_PRESETS
from compression_stats import format_bytes, reduction_percentage, calculate_summary

VIDEO_EXTENSIONS = {".mkv", ".mp4"}


class FFmpegGUI(QMainWindow):
    """Conversion par lot avec presets vidéo et contrôles de compatibilité."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFmpeg GUI")
        self.resize(1450, 850)

        self.settings = QSettings("Deklou", "FFmpegGUI")
        self.last_input_dir = self.settings.value("last_input_dir", str(Path.home()))
        self.output_dir = self.settings.value("output_dir", "")
        self.video_paths = []
        self.video_keys = set()
        self.output_sizes = {}  # index de ligne -> octets de sortie validée
        self.worker = None
        self.conversion_active = False
        self.ffmpeg_path = self.settings.value("ffmpeg_path", "") or locate_ffmpeg()
        self.applying_preset = False
        self.preset_store = None
        self.preset_error = None
        self.preset_read_only = False
        try:
            self.preset_store = PresetStore()
        except ValueError as exc:
            self.preset_error = str(exc)
            self.preset_read_only = True
            # Les presets sur le disque ne sont jamais modifiés si la lecture échoue.
            self.preset_store = PresetStore.__new__(PresetStore)
            self.preset_store.path = Path.home() / ".ffmpeg_gui" / "presets.json"
            self.preset_store.custom = {}


        self.setup_ui()
        self.update_paths()
        self.update_actions()
        if self.preset_error:
            QMessageBox.warning(self, "Presets illisibles", self.preset_error)

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
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset :"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(240)
        self.preset_combo.addItem("Personnalisé", None)
        for name in self.preset_store.all_presets():
            self.preset_combo.addItem(name, name)
        self.save_preset_button = QPushButton("Sauvegarder")
        self.delete_preset_button = QPushButton("Supprimer")
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.save_preset_button)
        preset_row.addWidget(self.delete_preset_button)
        ffmpeg_layout.addLayout(preset_row)

        options_row = QHBoxLayout()
        video_group = QGroupBox("Vidéo")
        video_layout = QFormLayout(video_group)
        self.codec_combo = QComboBox()
        self.codec_combo.addItem("H.265 / HEVC", "libx265")
        self.codec_combo.addItem("H.264 / AVC", "libx264")
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(28)
        self.crf_spin.setToolTip("Plus bas : qualité supérieure et fichiers plus volumineux.")
        self.speed_combo = QComboBox()
        for speed in ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"):
            self.speed_combo.addItem(speed, speed)
        self.speed_combo.setCurrentIndex(self.speed_combo.findData("medium"))
        video_layout.addRow("Codec :", self.codec_combo)
        video_layout.addRow("CRF :", self.crf_spin)
        video_layout.addRow("Vitesse :", self.speed_combo)

        tracks_group = QGroupBox("Pistes et format")
        tracks_layout = QFormLayout(tracks_group)
        self.audio_combo = QComboBox()
        self.audio_combo.addItem("Copier sans réencoder", "copy")
        self.audio_combo.addItem("AAC 192 kb/s", "aac")
        self.audio_combo.addItem("Ignorer les pistes audio", "none")
        self.subtitle_combo = QComboBox()
        self.subtitle_combo.addItem("Copier toutes les pistes", "copy")
        self.subtitle_combo.addItem("Ignorer les sous-titres", "none")
        self.container_combo = QComboBox()
        self.container_combo.addItem("MKV", "mkv")
        self.container_combo.addItem("MP4", "mp4")
        tracks_layout.addRow("Audio :", self.audio_combo)
        tracks_layout.addRow("Sous-titres :", self.subtitle_combo)
        tracks_layout.addRow("Sortie :", self.container_combo)

        options_row.addWidget(video_group, 1)
        options_row.addWidget(tracks_group, 1)
        ffmpeg_layout.addLayout(options_row)

        self.encoding_info = QLabel()
        self.encoding_info.setWordWrap(True)
        self.encoding_info.setStyleSheet("color: #aaaaaa;")
        ffmpeg_layout.addWidget(self.encoding_info)
        main_layout.addWidget(ffmpeg_group)
        self.apply_conversion_settings(ConversionSettings(), select_preset="H.265 · Archivage MKV (habituel)")

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

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "Nom du fichier", "Dossier source", "Format", "Taille entrée",
            "Taille sortie", "Réduction", "État", "Progression",
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(4, 8):
            self.table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
            )
        main_layout.addWidget(self.table, 1)

        self.summary_label = QLabel("0 vidéo sélectionnée")
        main_layout.addWidget(self.summary_label)

        # Synthèse indépendante de la progression : seuls les résultats réellement
        # produits (ou déjà présents) sont comptés dans les tailles de sortie.
        totals_row = QHBoxLayout()
        self.total_input_label = QLabel("Entrée du lot : —")
        self.total_output_label = QLabel("Sorties connues : —")
        self.saved_label = QLabel("Espace économisé : —")
        self.reduction_label = QLabel("Réduction : —")
        for label in (
            self.total_input_label, self.total_output_label,
            self.saved_label, self.reduction_label,
        ):
            label.setStyleSheet("font-weight: 600; padding: 5px;")
            totals_row.addWidget(label)
        totals_row.addStretch()
        main_layout.addLayout(totals_row)
        self.totals_info = QLabel(
            "La réduction globale porte uniquement sur les sorties connues "
            "(terminées ou déjà présentes), jamais sur les vidéos en attente."
        )
        self.totals_info.setStyleSheet("color: #999;")
        self.totals_info.setWordWrap(True)
        main_layout.addWidget(self.totals_info)

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
        self.preset_combo.currentIndexChanged.connect(self.on_preset_selected)
        self.save_preset_button.clicked.connect(self.save_preset)
        self.delete_preset_button.clicked.connect(self.delete_preset)
        self.codec_combo.currentIndexChanged.connect(self.on_options_changed)
        self.crf_spin.valueChanged.connect(self.on_options_changed)
        self.speed_combo.currentIndexChanged.connect(self.on_options_changed)
        self.audio_combo.currentIndexChanged.connect(self.on_options_changed)
        self.subtitle_combo.currentIndexChanged.connect(self.on_options_changed)
        self.container_combo.currentIndexChanged.connect(self.on_container_changed)
        self.update_options_label()
        self.update_preset_actions()

    def current_conversion_settings(self):
        return ConversionSettings(
            codec=self.codec_combo.currentData(),
            crf=self.crf_spin.value(),
            speed=self.speed_combo.currentData(),
            audio=self.audio_combo.currentData(),
            subtitles=self.subtitle_combo.currentData(),
            container=self.container_combo.currentData(),
        )

    @staticmethod
    def choose_combo(combo, data):
        index = combo.findData(data)
        if index >= 0:
            combo.setCurrentIndex(index)

    def apply_conversion_settings(self, settings, select_preset=None):
        self.applying_preset = True
        try:
            self.choose_combo(self.codec_combo, settings.codec)
            self.crf_spin.setValue(settings.crf)
            self.choose_combo(self.speed_combo, settings.speed)
            self.choose_combo(self.audio_combo, settings.audio)
            self.choose_combo(self.subtitle_combo, settings.subtitles)
            self.choose_combo(self.container_combo, settings.container)
            index = self.preset_combo.findData(select_preset)
            self.preset_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.applying_preset = False
        self.update_options_label()
        self.update_preset_actions()

    def on_preset_selected(self, _index):
        if self.applying_preset:
            return
        name = self.preset_combo.currentData()
        if name is None:
            self.update_preset_actions()
            return
        try:
            settings = ConversionSettings.from_dict(self.preset_store.all_presets()[name])
        except (KeyError, ValueError) as exc:
            QMessageBox.warning(self, "Preset", str(exc))
            return
        self.apply_conversion_settings(settings, select_preset=name)

    def on_container_changed(self, _index=None):
        if self.applying_preset:
            return
        if self.container_combo.currentData() == "mp4" and self.subtitle_combo.currentData() == "copy":
            # La copie des sous-titres MKV dans MP4 peut être impossible.
            self.applying_preset = True
            self.choose_combo(self.subtitle_combo, "none")
            self.applying_preset = False
            self.statusBar().showMessage("MP4 : les sous-titres ont été réglés sur Ignorer.", 7000)
        self.on_options_changed()

    def on_options_changed(self, _value=None):
        if self.applying_preset:
            return
        if self.preset_combo.currentIndex() != 0:
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(0)
            self.preset_combo.blockSignals(False)
        self.update_options_label()
        self.update_preset_actions()

    def update_options_label(self):
        settings = self.current_conversion_settings()
        message = (
            f"Sortie : {settings.container.upper()}  |  "
            f"Vidéo : {settings.codec} / CRF {settings.crf} / {settings.speed}  |  "
            f"Audio : {settings.audio}  |  Sous-titres : {settings.subtitles}"
        )
        if settings.container == "mp4" and settings.audio == "copy":
            message += "\nAttention : certaines pistes audio copiées ne sont pas compatibles MP4. AAC est plus sûr."
        if settings.container == "mp4" and settings.subtitles == "copy":
            message += "\nIncompatible : copie directe des sous-titres en MP4."
        self.encoding_info.setText(message)

    def update_preset_actions(self):
        if not hasattr(self, "preset_combo") or not hasattr(self, "delete_preset_button"):
            return
        name = self.preset_combo.currentData()
        self.delete_preset_button.setEnabled(
            not self.is_converting() and not self.preset_read_only and name in self.preset_store.custom
        )
        self.save_preset_button.setEnabled(not self.is_converting() and not self.preset_read_only)
        self.preset_combo.setEnabled(not self.is_converting())

    def save_preset(self):
        name, accepted = QInputDialog.getText(self, "Sauvegarder un preset", "Nom du preset :")
        if not accepted or not name.strip():
            return
        name = name.strip()
        if name in self.preset_store.custom:
            reply = QMessageBox.question(self, "Remplacer le preset", f"Remplacer « {name} » ?")
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            self.preset_store.set(name, self.current_conversion_settings().to_dict())
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Preset", str(exc))
            return
        self.refresh_preset_combo(name)

    def delete_preset(self):
        name = self.preset_combo.currentData()
        if name not in self.preset_store.custom or self.preset_read_only:
            return
        answer = QMessageBox.question(self, "Supprimer le preset", f"Supprimer « {name} » ?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.preset_store.delete(name)
        except OSError as exc:
            QMessageBox.warning(self, "Preset", str(exc))
            return
        self.refresh_preset_combo(None)

    def refresh_preset_combo(self, name):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("Personnalisé", None)
        for preset_name in self.preset_store.all_presets():
            self.preset_combo.addItem(preset_name, preset_name)
        self.preset_combo.setCurrentIndex(max(0, self.preset_combo.findData(name)))
        self.preset_combo.blockSignals(False)
        self.update_preset_actions()

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
            name_item.setData(Qt.ItemDataRole.UserRole + 1, size)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(path.parent)))
            self.table.setItem(row, 2, QTableWidgetItem(path.suffix.lower()))
            self.table.setItem(row, 3, QTableWidgetItem(self.format_size(size)))
            self.table.setItem(row, 4, QTableWidgetItem("—"))
            self.table.setItem(row, 5, QTableWidgetItem("—"))
            self.table.setItem(row, 6, QTableWidgetItem("En attente"))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            self.table.setCellWidget(row, 7, bar)
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
        # Les indices de lignes ont changé ; les anciens résultats ne sont plus
        # associés de façon fiable. On nettoie seulement les statistiques d'affichage.
        self.reset_output_stats()
        self.update_paths()
        self.update_actions()

    def clear_videos(self):
        self.video_paths.clear()
        self.video_keys.clear()
        self.table.setRowCount(0)
        self.output_sizes.clear()
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
        self.update_size_summary()
        self.clear_button.setEnabled(count > 0 and not self.is_converting())
        self.remove_button.setEnabled(bool(self.table.selectedIndexes()) and not self.is_converting())
        self.import_button.setEnabled(not self.is_converting())
        self.folder_button.setEnabled(not self.is_converting())
        self.output_button.setEnabled(not self.is_converting())
        self.ffmpeg_edit.setEnabled(not self.is_converting())
        self.ffmpeg_browse.setEnabled(not self.is_converting())
        self.start_button.setEnabled(count > 0 and not self.is_converting())
        for control in (self.codec_combo, self.crf_spin, self.speed_combo,
                        self.audio_combo, self.subtitle_combo, self.container_combo):
            control.setEnabled(not self.is_converting())
        self.update_preset_actions()

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
        conversion_settings = self.current_conversion_settings()
        try:
            conversion_settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Paramètres incompatibles", str(exc))
            return
        if any(self.path_key(path) == self.path_key(Path(self.output_dir) / (Path(path).stem + f".{conversion_settings.container}")) for path in self.video_paths):
            QMessageBox.warning(self, "Dossier de sortie", "Le fichier de destination ne doit pas être le fichier source.")
            return

        self.batch_progress.setValue(0)
        self.reset_output_stats()
        for row in range(self.table.rowCount()):
            self.table.item(row, 6).setText("En attente")
            self.table.cellWidget(row, 7).setValue(0)
        self.worker = ConversionWorker(
            self.video_paths, self.output_dir, self.ffmpeg_path,
            settings=conversion_settings, parent=self
        )
        self.worker.state_changed.connect(self.on_file_state)
        self.worker.progress_changed.connect(self.on_file_progress)
        self.worker.output_measured.connect(self.on_output_measured)
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
            self.table.item(index, 6).setText(state)

    def on_file_progress(self, index, percentage):
        if index < self.table.rowCount():
            self.table.cellWidget(index, 7).setValue(percentage)
        total = self.table.rowCount()
        if total:
            progress_sum = sum(self.table.cellWidget(i, 7).value() for i in range(total))
            self.batch_progress.setValue(round(progress_sum / total))

    def on_output_measured(self, index, output_bytes, status):
        """Signal émis par le worker après succès ou pour une sortie déjà présente."""
        if not 0 <= index < self.table.rowCount():
            return
        source_bytes = self.table.item(index, 0).data(Qt.ItemDataRole.UserRole + 1)
        self.output_sizes[index] = int(output_bytes)
        self.table.item(index, 4).setText(format_bytes(output_bytes))
        reduction = reduction_percentage(source_bytes, output_bytes)
        self.table.item(index, 5).setText(
            f"{reduction:+.1f} %" if reduction is not None else "—"
        )
        self.table.item(index, 4).setToolTip(
            "Fichier déjà présent (son encodage peut différer des réglages actuels)."
            if status == "Déjà converti" else "Fichier converti avec succès."
        )
        self.update_size_summary()

    def reset_output_stats(self):
        self.output_sizes.clear()
        for row in range(self.table.rowCount()):
            self.table.item(row, 4).setText("—")
            self.table.item(row, 5).setText("—")
            self.table.item(row, 4).setToolTip("")
        self.update_size_summary()

    def update_size_summary(self):
        sizes = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                sizes.append(int(item.data(Qt.ItemDataRole.UserRole + 1) or 0))
        summary = calculate_summary(sizes, self.output_sizes)
        self.total_input_label.setText(
            f"Entrée du lot : {format_bytes(summary['total_input'])}"
        )
        if summary["known_count"] == 0:
            self.total_output_label.setText("Sorties connues : —")
            self.saved_label.setText("Espace économisé : —")
            self.reduction_label.setText("Réduction : —")
            return

        self.total_output_label.setText(
            f"Sorties connues ({summary['known_count']}/{summary['count']}) : "
            f"{format_bytes(summary['known_output'])}"
        )
        saving = summary["known_input"] - summary["known_output"]
        saving_abs = format_bytes(abs(saving))
        self.saved_label.setText(
            f"Espace {'économisé' if saving >= 0 else 'supplémentaire'} : {saving_abs}"
        )
        reduction = summary["known_reduction"]
        self.reduction_label.setText(
            f"Réduction : {reduction:+.1f} %" if reduction is not None else "Réduction : —"
        )

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
