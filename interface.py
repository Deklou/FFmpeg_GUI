"""Interface FFmpeg GUI : imports, synchronisation, conversion et préférences.

Les classes internes représentent des responsabilités de l'interface, sans
importer en chaîne d'anciennes versions du programme.
"""
import os
import time
from pathlib import Path
from PySide6.QtCore import Qt, QSettings, QTimer, QEvent
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QComboBox, QCheckBox, QSpinBox, QInputDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
    QLineEdit, QProgressBar, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QFrame, QScrollArea, QSizePolicy,
)
from converter import ConversionWorker, ParallelBatchController, locate_ffmpeg
from config import ConversionSettings, PresetStore, BUILTIN_PRESETS, default_preset_path
from metrics import format_bytes, reduction_percentage, calculate_summary, format_duration, format_reduction
from file_utils import VIDEO_EXTENSIONS, discover_videos, plan_destinations, path_identity, classify_paths, file_signature, renamed_candidate, output_change_requires_rescan
class _BaseUI(QMainWindow):
    """Conversion par lot avec presets vidéo et contrôles de compatibilité."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle('FFmpeg GUI')
        self.resize(1450, 850)
        self.settings = QSettings('FFmpeg GUI', 'FFmpeg GUI')
        self.last_input_dir = self.settings.value('last_input_dir', str(Path.home()))
        self.output_dir = self.settings.value('output_dir', '')
        self.video_paths = []
        self.video_keys = set()
        self.source_roots = {}
        self.output_sizes = {}
        self.worker = None
        self.conversion_active = False
        self.batch_started_at = None
        self.active_file_started_at = None
        self.active_file_index = None
        self.batch_eta_seconds = None
        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(1000)
        self.elapsed_timer.timeout.connect(self.update_elapsed_clock)
        self.ffmpeg_path = self.settings.value('ffmpeg_path', '') or locate_ffmpeg()
        self.applying_preset = False
        self.preset_store = None
        self.preset_error = None
        self.preset_read_only = False
        try:
            self.preset_store = PresetStore()
        except ValueError as exc:
            self.preset_error = str(exc)
            self.preset_read_only = True
            self.preset_store = PresetStore.__new__(PresetStore)
            self.preset_store.path = default_preset_path()
            self.preset_store.custom = {}
        self.setup_ui()
        self.update_paths()
        self.update_actions()
        if self.preset_error:
            QMessageBox.warning(self, 'Presets illisibles', self.preset_error)

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)
        title = QLabel('FFmpeg GUI')
        title.setStyleSheet('font-size: 24px; font-weight: bold;')
        main_layout.addWidget(title)
        paths_group = QGroupBox('Fichiers et dossiers')
        paths_layout = QVBoxLayout(paths_group)
        buttons_layout = QHBoxLayout()
        self.import_button = QPushButton('Ajouter des vidéos')
        self.folder_button = QPushButton('Ajouter un dossier')
        self.output_button = QPushButton('Dossier de sortie')
        for button in (self.import_button, self.folder_button, self.output_button):
            button.setMinimumHeight(40)
            buttons_layout.addWidget(button)
        buttons_layout.addStretch()
        paths_layout.addLayout(buttons_layout)
        folders_options = QHBoxLayout()
        self.recursive_check = QCheckBox('Inclure les sous-dossiers')
        self.recursive_check.setChecked(False)
        self.recursive_check.setToolTip("Recherche aussi les vidéos dans les dossiers imbriqués lors de l'ajout d'un dossier.")
        self.preserve_tree_check = QCheckBox("Conserver l'arborescence en sortie")
        self.preserve_tree_check.setChecked(True)
        self.preserve_tree_check.setToolTip('Recrée les sous-dossiers relatifs au dossier importé. Les fichiers ajoutés individuellement vont à la racine.')
        folders_options.addWidget(self.recursive_check)
        folders_options.addWidget(self.preserve_tree_check)
        folders_options.addStretch()
        paths_layout.addLayout(folders_options)
        self.input_label = QLabel()
        self.output_label = QLabel()
        for label in (self.input_label, self.output_label):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setStyleSheet('padding: 8px; border: 1px solid #555; border-radius: 5px;')
            paths_layout.addWidget(label)
        main_layout.addWidget(paths_group)
        ffmpeg_group = QGroupBox('FFmpeg et paramètres de conversion')
        ffmpeg_layout = QVBoxLayout(ffmpeg_group)
        executable_row = QHBoxLayout()
        self.ffmpeg_edit = QLineEdit(self.ffmpeg_path)
        self.ffmpeg_edit.setPlaceholderText('Chemin vers ffmpeg.exe')
        self.ffmpeg_browse = QPushButton('Parcourir...')
        executable_row.addWidget(QLabel('FFmpeg :'))
        executable_row.addWidget(self.ffmpeg_edit, 1)
        executable_row.addWidget(self.ffmpeg_browse)
        ffmpeg_layout.addLayout(executable_row)
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel('Preset :'))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(240)
        self.preset_combo.addItem('Personnalisé', None)
        for name in self.preset_store.all_presets():
            self.preset_combo.addItem(name, name)
        self.save_preset_button = QPushButton('Sauvegarder')
        self.delete_preset_button = QPushButton('Supprimer')
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.save_preset_button)
        preset_row.addWidget(self.delete_preset_button)
        ffmpeg_layout.addLayout(preset_row)
        options_row = QHBoxLayout()
        video_group = QGroupBox('Vidéo')
        video_layout = QFormLayout(video_group)
        self.codec_combo = QComboBox()
        self.codec_combo.addItem('H.265 / HEVC', 'libx265')
        self.codec_combo.addItem('H.264 / AVC', 'libx264')
        self.crf_spin = QSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(28)
        self.crf_spin.setToolTip('Plus bas : qualité supérieure et fichiers plus volumineux.')
        self.speed_combo = QComboBox()
        for speed in ('ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'):
            self.speed_combo.addItem(speed, speed)
        self.speed_combo.setCurrentIndex(self.speed_combo.findData('medium'))
        video_layout.addRow('Codec :', self.codec_combo)
        video_layout.addRow('CRF :', self.crf_spin)
        video_layout.addRow('Vitesse :', self.speed_combo)
        tracks_group = QGroupBox('Pistes et format')
        tracks_layout = QFormLayout(tracks_group)
        self.audio_combo = QComboBox()
        self.audio_combo.addItem('Copier sans réencoder', 'copy')
        self.audio_combo.addItem('AAC 192 kb/s', 'aac')
        self.audio_combo.addItem('Ignorer les pistes audio', 'none')
        self.subtitle_combo = QComboBox()
        self.subtitle_combo.addItem('Copier toutes les pistes', 'copy')
        self.subtitle_combo.addItem('Ignorer les sous-titres', 'none')
        self.container_combo = QComboBox()
        self.container_combo.addItem('MKV', 'mkv')
        self.container_combo.addItem('MP4', 'mp4')
        tracks_layout.addRow('Audio :', self.audio_combo)
        tracks_layout.addRow('Sous-titres :', self.subtitle_combo)
        tracks_layout.addRow('Sortie :', self.container_combo)
        options_row.addWidget(video_group, 1)
        options_row.addWidget(tracks_group, 1)
        ffmpeg_layout.addLayout(options_row)
        self.encoding_info = QLabel()
        self.encoding_info.setWordWrap(True)
        self.encoding_info.setStyleSheet('color: #aaaaaa;')
        ffmpeg_layout.addWidget(self.encoding_info)
        main_layout.addWidget(ffmpeg_group)
        self.apply_conversion_settings(ConversionSettings(), select_preset='H.265 · Archivage MKV (habituel)')
        queue_header = QHBoxLayout()
        queue_title = QLabel('Vidéos sélectionnées')
        queue_title.setStyleSheet('font-size: 17px; font-weight: bold;')
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        self.remove_button = QPushButton('Retirer la sélection')
        self.clear_button = QPushButton('Tout vider')
        queue_header.addWidget(self.remove_button)
        queue_header.addWidget(self.clear_button)
        main_layout.addLayout(queue_header)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(['Nom du fichier', 'Dossier source', 'Format', 'Taille entrée', 'Taille sortie', 'Réduction', 'État', 'Progression', 'Temps écoulé', 'Restant estimé', 'Vitesse'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(4, 11):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        main_layout.addWidget(self.table, 1)
        self.summary_label = QLabel('0 vidéo sélectionnée')
        main_layout.addWidget(self.summary_label)
        totals_row = QHBoxLayout()
        self.total_input_label = QLabel('Entrée du lot : —')
        self.total_output_label = QLabel('Sorties connues : —')
        self.saved_label = QLabel('Espace économisé : —')
        self.reduction_label = QLabel('Réduction : —')
        for label in (self.total_input_label, self.total_output_label, self.saved_label, self.reduction_label):
            label.setStyleSheet('font-weight: 600; padding: 5px;')
            totals_row.addWidget(label)
        totals_row.addStretch()
        main_layout.addLayout(totals_row)
        self.totals_info = QLabel('La réduction globale porte uniquement sur les sorties connues (terminées ou déjà présentes), jamais sur les vidéos en attente.')
        self.totals_info.setStyleSheet('color: #999;')
        self.totals_info.setWordWrap(True)
        main_layout.addWidget(self.totals_info)
        conversion_row = QHBoxLayout()
        self.start_button = QPushButton('Lancer les conversions')
        self.cancel_button = QPushButton('Annuler')
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
        time_row = QHBoxLayout()
        self.batch_elapsed_label = QLabel('Temps écoulé du lot : 00:00:00')
        self.batch_eta_label = QLabel('Temps restant estimé du lot : —')
        for label in (self.batch_elapsed_label, self.batch_eta_label):
            label.setStyleSheet('font-weight: 600; padding: 5px;')
            time_row.addWidget(label)
        time_row.addStretch()
        main_layout.addLayout(time_row)
        self.import_button.clicked.connect(self.import_videos)
        self.folder_button.clicked.connect(self.import_folder)
        self.output_button.clicked.connect(self.select_output_dir)
        self.preserve_tree_check.toggled.connect(self.update_actions)
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
        return ConversionSettings(codec=self.codec_combo.currentData(), crf=self.crf_spin.value(), speed=self.speed_combo.currentData(), audio=self.audio_combo.currentData(), subtitles=self.subtitle_combo.currentData(), container=self.container_combo.currentData())

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
            QMessageBox.warning(self, 'Preset', str(exc))
            return
        self.apply_conversion_settings(settings, select_preset=name)

    def on_container_changed(self, _index=None):
        if self.applying_preset:
            return
        if self.container_combo.currentData() == 'mp4' and self.subtitle_combo.currentData() == 'copy':
            self.applying_preset = True
            self.choose_combo(self.subtitle_combo, 'none')
            self.applying_preset = False
            self.statusBar().showMessage('MP4 : les sous-titres ont été réglés sur Ignorer.', 7000)
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
        message = f'Sortie : {settings.container.upper()}  |  Vidéo : {settings.codec} / CRF {settings.crf} / {settings.speed}  |  Audio : {settings.audio}  |  Sous-titres : {settings.subtitles}'
        if settings.container == 'mp4' and settings.audio == 'copy':
            message += '\nAttention : certaines pistes audio copiées ne sont pas compatibles MP4. AAC est plus sûr.'
        if settings.container == 'mp4' and settings.subtitles == 'copy':
            message += '\nIncompatible : copie directe des sous-titres en MP4.'
        self.encoding_info.setText(message)

    def update_preset_actions(self):
        if not hasattr(self, 'preset_combo') or not hasattr(self, 'delete_preset_button'):
            return
        name = self.preset_combo.currentData()
        self.delete_preset_button.setEnabled(not self.is_converting() and (not self.preset_read_only) and (name in self.preset_store.custom))
        self.save_preset_button.setEnabled(not self.is_converting() and (not self.preset_read_only))
        self.preset_combo.setEnabled(not self.is_converting())

    def save_preset(self):
        name, accepted = QInputDialog.getText(self, 'Sauvegarder un preset', 'Nom du preset :')
        if not accepted or not name.strip():
            return
        name = name.strip()
        if name in self.preset_store.custom:
            reply = QMessageBox.question(self, 'Remplacer le preset', f'Remplacer « {name} » ?')
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            self.preset_store.set(name, self.current_conversion_settings().to_dict())
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, 'Preset', str(exc))
            return
        self.refresh_preset_combo(name)

    def delete_preset(self):
        name = self.preset_combo.currentData()
        if name not in self.preset_store.custom or self.preset_read_only:
            return
        answer = QMessageBox.question(self, 'Supprimer le preset', f'Supprimer « {name} » ?')
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.preset_store.delete(name)
        except OSError as exc:
            QMessageBox.warning(self, 'Preset', str(exc))
            return
        self.refresh_preset_combo(None)

    def refresh_preset_combo(self, name):
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem('Personnalisé', None)
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
            return f'{size} o'
        if size < 1024 ** 2:
            return f'{size / 1024:.1f} Ko'
        if size < 1024 ** 3:
            return f'{size / 1024 ** 2:.1f} Mo'
        return f'{size / 1024 ** 3:.2f} Go'

    def import_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Sélectionner des vidéos', self.last_input_dir, 'Vidéos (*.mkv *.mp4)')
        if not paths:
            return
        self.remember_input_dir(str(Path(paths[0]).parent))
        added = self.add_paths(paths)
        self.statusBar().showMessage(f'{added} vidéo(s) ajoutée(s)')

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Sélectionner un dossier de vidéos', self.last_input_dir)
        if not folder:
            return
        self.remember_input_dir(folder)
        try:
            paths = discover_videos(folder, recursive=self.recursive_check.isChecked(), exclude_folder=self.output_dir or None)
        except OSError as exc:
            self.statusBar().showMessage(f'Lecture du dossier impossible : {exc}')
            return
        added = self.add_paths(paths, source_root=folder)
        self.statusBar().showMessage(f'{added} vidéo(s) ajoutée(s) depuis ce dossier')

    def remember_input_dir(self, folder):
        self.last_input_dir = folder
        self.settings.setValue('last_input_dir', folder)
        self.update_paths()

    def select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, 'Choisir le dossier de sortie', self.output_dir or self.last_input_dir)
        if folder:
            self.output_dir = folder
            self.settings.setValue('output_dir', folder)
            self.update_paths()

    def add_paths(self, paths, source_root=None):
        added = 0
        for raw_path in paths:
            path = Path(raw_path)
            key = self.path_key(path)
            if key in self.video_keys:
                if source_root and self.source_roots.get(path_identity(path)) is None:
                    self.source_roots[path_identity(path)] = source_root
                continue
            if path.suffix.lower() not in VIDEO_EXTENSIONS or not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            self.video_paths.append(str(path))
            self.video_keys.add(key)
            self.source_roots[path_identity(path)] = source_root
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(path.name)
            name_item.setData(Qt.ItemDataRole.UserRole, str(path))
            name_item.setData(Qt.ItemDataRole.UserRole + 1, size)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(path.parent)))
            self.table.setItem(row, 2, QTableWidgetItem(path.suffix.lower()))
            self.table.setItem(row, 3, QTableWidgetItem(self.format_size(size)))
            self.table.setItem(row, 4, QTableWidgetItem('—'))
            self.table.setItem(row, 5, QTableWidgetItem('—'))
            self.table.setItem(row, 6, QTableWidgetItem('En attente'))
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            self.table.setCellWidget(row, 7, bar)
            for col in (8, 9, 10):
                self.table.setItem(row, col, QTableWidgetItem('—'))
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
                self.source_roots.pop(path_identity(path), None)
                self.video_paths = [existing for existing in self.video_paths if self.path_key(existing) != self.path_key(path)]
            self.table.removeRow(row)
        self.reset_output_stats()
        self.update_paths()
        self.update_actions()

    def clear_videos(self):
        self.video_paths.clear()
        self.video_keys.clear()
        self.source_roots.clear()
        self.table.setRowCount(0)
        self.output_sizes.clear()
        self.update_paths()
        self.update_actions()

    def update_paths(self):
        source_folders = sorted({str(Path(path).parent) for path in self.video_paths}, key=str.casefold)
        if len(source_folders) == 1:
            source = source_folders[0]
        elif len(source_folders) > 1:
            source = f'Plusieurs dossiers ({len(source_folders)})'
        else:
            source = self.last_input_dir or 'Non sélectionné'
        self.input_label.setText(f"Dossier(s) d'entrée : {source}")
        self.input_label.setToolTip('\n'.join(source_folders) if source_folders else source)
        output = self.output_dir or 'Non sélectionné'
        self.output_label.setText(f'Dossier de sortie : {output}')
        self.output_label.setToolTip(output)

    def update_actions(self):
        count = len(self.video_paths)
        self.summary_label.setText(f"{count} vidéo{('s' if count > 1 else '')} sélectionnée{('s' if count > 1 else '')}")
        self.update_size_summary()
        self.clear_button.setEnabled(count > 0 and (not self.is_converting()))
        self.remove_button.setEnabled(bool(self.table.selectedIndexes()) and (not self.is_converting()))
        self.import_button.setEnabled(not self.is_converting())
        self.folder_button.setEnabled(not self.is_converting())
        self.output_button.setEnabled(not self.is_converting())
        self.recursive_check.setEnabled(not self.is_converting())
        self.preserve_tree_check.setEnabled(not self.is_converting())
        self.ffmpeg_edit.setEnabled(not self.is_converting())
        self.ffmpeg_browse.setEnabled(not self.is_converting())
        self.start_button.setEnabled(count > 0 and (not self.is_converting()))
        for control in (self.codec_combo, self.crf_spin, self.speed_combo, self.audio_combo, self.subtitle_combo, self.container_combo):
            control.setEnabled(not self.is_converting())
        self.update_preset_actions()

    def is_converting(self):
        return self.conversion_active

    def select_ffmpeg(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Sélectionner FFmpeg', self.ffmpeg_edit.text() or self.last_input_dir, 'Exécutable FFmpeg (ffmpeg.exe);;Tous les fichiers (*)')
        if filename:
            self.ffmpeg_edit.setText(filename)
            self.remember_ffmpeg()

    def remember_ffmpeg(self):
        self.ffmpeg_path = self.ffmpeg_edit.text().strip().strip('"')
        self.settings.setValue('ffmpeg_path', self.ffmpeg_path)

    def start_conversion(self):
        if self.is_converting() or not self.video_paths:
            return
        self.remember_ffmpeg()
        if not Path(self.ffmpeg_path).is_file():
            QMessageBox.warning(self, 'FFmpeg', 'Sélectionne un fichier ffmpeg.exe valide.')
            return
        if not self.output_dir:
            QMessageBox.warning(self, 'Dossier de sortie', 'Choisis un dossier de sortie.')
            return
        conversion_settings = self.current_conversion_settings()
        try:
            conversion_settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, 'Paramètres incompatibles', str(exc))
            return
        targets = plan_destinations(self.video_paths, self.source_roots, self.output_dir, conversion_settings.container, preserve_tree=self.preserve_tree_check.isChecked())
        source_identities = {path_identity(source) for source in self.video_paths}
        if any((path_identity(target) in source_identities for target in targets)):
            QMessageBox.warning(self, 'Dossier de sortie', 'Une destination correspond à une vidéo source du lot. Choisis un autre dossier de sortie.')
            return
        self.batch_elapsed_label.setText('Temps écoulé du lot : 00:00:00')
        self.batch_eta_label.setText('Temps restant estimé du lot : —')
        self.batch_eta_seconds = None
        self.active_file_started_at = None
        self.active_file_index = None
        self.reset_output_stats()
        for row in range(self.table.rowCount()):
            self.table.item(row, 6).setText('En attente')
            self.table.cellWidget(row, 7).setValue(0)
            for col in (8, 9, 10):
                self.table.item(row, col).setText('—')
        self.worker = ConversionWorker(self.video_paths, self.output_dir, self.ffmpeg_path, settings=conversion_settings, parent=self, targets=targets)
        for row, target in enumerate(targets):
            self.table.item(row, 0).setToolTip(f'Destination prévue : {target}')
        self.worker.state_changed.connect(self.on_file_state)
        self.worker.progress_changed.connect(self.on_file_progress)
        self.worker.output_measured.connect(self.on_output_measured)
        self.worker.timing_started.connect(self.on_timing_started)
        self.worker.timing_updated.connect(self.on_timing_updated)
        self.worker.timing_finished.connect(self.on_timing_finished)
        self.worker.batch_finished.connect(self.on_batch_finished)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.conversion_active = True
        self.cancel_button.setEnabled(True)
        self.update_actions()
        self.batch_started_at = time.monotonic()
        self.elapsed_timer.start()
        self.worker.start()
        self.update_actions()
        self.statusBar().showMessage('Conversions en cours...')

    def cancel_conversion(self):
        if self.is_converting():
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage('Annulation demandée...')
            self.worker.request_cancel()

    def on_file_state(self, index, state):
        if index < self.table.rowCount():
            self.table.item(index, 6).setText(state)

    def on_file_progress(self, index, percentage):
        if index < self.table.rowCount():
            self.table.cellWidget(index, 7).setValue(percentage)
        total = self.table.rowCount()
        if total:
            progress_sum = sum((self.table.cellWidget(i, 7).value() for i in range(total)))
            self.batch_progress.setValue(round(progress_sum / total))

    def update_elapsed_clock(self):
        now = time.monotonic()
        if self.batch_started_at is not None:
            elapsed = now - self.batch_started_at
            self.batch_elapsed_label.setText(f'Temps écoulé du lot : {format_duration(elapsed)}')
        if self.active_file_started_at is not None and self.active_file_index is not None:
            row = self.active_file_index
            if 0 <= row < self.table.rowCount():
                self.table.item(row, 8).setText(format_duration(now - self.active_file_started_at))

    def on_timing_started(self, index):
        self.active_file_index = index
        self.active_file_started_at = time.monotonic()
        self.batch_eta_seconds = None
        self.batch_eta_label.setText('Temps restant estimé du lot : —')
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 8).setText('00:00:00')
            self.table.item(index, 9).setText('—')
            self.table.item(index, 10).setText('—')

    def on_timing_updated(self, index, elapsed, remaining, speed, batch_remaining):
        if not 0 <= index < self.table.rowCount():
            return
        self.table.item(index, 8).setText(format_duration(elapsed))
        self.table.item(index, 9).setText(format_duration(remaining))
        self.table.item(index, 10).setText(f'{speed:.2f}x' if speed > 0 else '—')
        self.batch_eta_seconds = batch_remaining if batch_remaining >= 0 else None
        self.batch_eta_label.setText(f'Temps restant estimé du lot : {format_duration(self.batch_eta_seconds)}')

    def on_timing_finished(self, index, elapsed):
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 8).setText(format_duration(elapsed))
            self.table.item(index, 9).setText('—')
        if self.active_file_index == index:
            self.active_file_index = None
            self.active_file_started_at = None

    def on_output_measured(self, index, output_bytes, status):
        """Signal émis par le worker après succès ou pour une sortie déjà présente."""
        if not 0 <= index < self.table.rowCount():
            return
        source_bytes = self.table.item(index, 0).data(Qt.ItemDataRole.UserRole + 1)
        self.output_sizes[index] = int(output_bytes)
        self.table.item(index, 4).setText(format_bytes(output_bytes))
        reduction = reduction_percentage(source_bytes, output_bytes)
        self.table.item(index, 5).setText(format_reduction(reduction))
        self.table.item(index, 4).setToolTip('Fichier déjà présent (son encodage peut différer des réglages actuels).' if status == 'Déjà converti' else 'Fichier converti avec succès.')
        self.update_size_summary()

    def reset_output_stats(self):
        self.output_sizes.clear()
        for row in range(self.table.rowCount()):
            self.table.item(row, 4).setText('—')
            self.table.item(row, 5).setText('—')
            self.table.item(row, 4).setToolTip('')
        self.update_size_summary()

    def update_size_summary(self):
        sizes = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                sizes.append(int(item.data(Qt.ItemDataRole.UserRole + 1) or 0))
        summary = calculate_summary(sizes, self.output_sizes)
        self.total_input_label.setText(f"Entrée du lot : {format_bytes(summary['total_input'])}")
        if summary['known_count'] == 0:
            self.total_output_label.setText('Sorties connues : —')
            self.saved_label.setText('Espace économisé : —')
            self.reduction_label.setText('Réduction : —')
            return
        self.total_output_label.setText(f"Sorties connues ({summary['known_count']}/{summary['count']}) : {format_bytes(summary['known_output'])}")
        saving = summary['known_input'] - summary['known_output']
        saving_abs = format_bytes(abs(saving))
        self.saved_label.setText(f"Espace {('économisé' if saving >= 0 else 'supplémentaire')} : {saving_abs}")
        reduction = summary['known_reduction']
        self.reduction_label.setText(f'Réduction : {format_reduction(reduction)}')

    def on_batch_finished(self, done, skipped, failed, cancelled, errors):
        self.cancel_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.statusBar().showMessage('Lot annulé' if cancelled else 'Lot terminé')
        message = f'Converties : {done}\nDéjà présentes : {skipped}\nErreurs : {failed}'
        if cancelled:
            message += '\nConversion annulée.'
        if errors:
            message += '\n\n' + '\n'.join(errors[:5])
        QMessageBox.information(self, 'Résultat des conversions', message)

    def on_worker_finished(self):
        self.elapsed_timer.stop()
        self.update_elapsed_clock()
        self.active_file_index = None
        self.active_file_started_at = None
        self.batch_eta_label.setText('Temps restant estimé du lot : —')
        self.conversion_active = False
        self.worker = None
        self.update_actions()

    def closeEvent(self, event):
        if self.is_converting():
            QMessageBox.information(self, 'Conversion en cours', "Annule d'abord le traitement et attends sa fin avant de fermer.")
            event.ignore()
        else:
            event.accept()

class _SourceUI(_BaseUI):
    REFRESH_INTERVAL_MS = 3000

    def __init__(self):
        self.monitored_roots = {}
        self.manual_files = set()
        self.excluded_files = set()
        self.generated_targets = set()
        self._syncing = False
        self._destinations = ()
        super().__init__()
        self.setWindowTitle('FFmpeg GUI — V0.7')
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels(['Nom du fichier', 'Dossier source', 'Format', 'Taille entrée', 'Taille sortie', 'Réduction', 'État', 'Progression', 'Temps écoulé', 'Restant estimé', 'Vitesse', 'Destination'])
        self.table.horizontalHeader().setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(11, 260)
        buttons_layout = self.import_button.parentWidget().layout().itemAt(0).layout()
        self.refresh_button = QPushButton('Actualiser')
        self.refresh_button.setToolTip('Rescanner tous les dossiers importés')
        buttons_layout.insertWidget(2, self.refresh_button)
        self.refresh_button.clicked.connect(self.refresh_sources)
        self.recursive_check.setToolTip('Appliqué immédiatement aux dossiers importés, sans nouvel import.')
        self.preserve_tree_check.setToolTip('Actualise immédiatement la colonne Destination, sans modifier les sources.')
        self.recursive_check.toggled.connect(self.refresh_sources)
        self.preserve_tree_check.toggled.connect(self.refresh_destinations)
        self.container_combo.currentIndexChanged.connect(self.refresh_destinations)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(self.REFRESH_INTERVAL_MS)
        self.refresh_timer.timeout.connect(self.refresh_sources)
        self.refresh_timer.start()
        self.refresh_destinations()

    def import_videos(self):
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(self, 'Sélectionner des vidéos', self.last_input_dir, 'Vidéos (*.mkv *.mp4)')
        if not paths:
            return
        self.remember_input_dir(str(Path(paths[0]).parent))
        self.manual_files.update((path_identity(p) for p in paths if Path(p).is_file()))
        self.excluded_files.difference_update((path_identity(p) for p in paths))
        added = self.add_paths(paths)
        self.statusBar().showMessage(f'{added} vidéo(s) ajoutée(s) manuellement', 5000)
        self.refresh_destinations()

    def import_folder(self):
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, 'Sélectionner un dossier de vidéos', self.last_input_dir)
        if not folder:
            return
        self.remember_input_dir(folder)
        self.monitored_roots[path_identity(folder)] = folder
        self.excluded_files = {key for key in self.excluded_files if not self._belongs_to_root(key, folder)}
        self.refresh_sources()

    @staticmethod
    def _belongs_to_root(path, root):
        try:
            Path(path).resolve().relative_to(Path(root).resolve())
            return True
        except (ValueError, OSError):
            return False

    def refresh_sources(self, *_args):
        if self.is_converting() or self._syncing:
            return
        self._syncing = True
        try:
            by_key = {}
            errors = []
            roots = sorted(self.monitored_roots.values(), key=lambda p: len(Path(p).parts))
            for root in roots:
                try:
                    paths = discover_videos(root, recursive=self.recursive_check.isChecked(), exclude_folder=self.output_dir or None)
                    for path in paths:
                        by_key[path_identity(path)] = (path, root)
                except OSError as exc:
                    errors.append(f'{root} : {exc}')
            currently_present = set(by_key)
            self.generated_targets.intersection_update((key for key in self.generated_targets if Path(key).exists()))
            by_key = {k: v for k, v in by_key.items() if k not in self.generated_targets}
            self.excluded_files.intersection_update(currently_present)
            by_key = {k: v for k, v in by_key.items() if k not in self.excluded_files}
            old_paths = list(self.video_paths)
            old_keys = [path_identity(p) for p in old_paths]
            old_sizes = dict(self.output_sizes)
            removed_rows = []
            for row, (path, key) in enumerate(zip(old_paths, old_keys)):
                exists = Path(path).is_file()
                if not exists:
                    self.manual_files.discard(key)
                if not exists or (key not in self.manual_files and key not in by_key):
                    removed_rows.append(row)
            if removed_rows:
                removed_set = set(removed_rows)
                for row in reversed(removed_rows):
                    self.table.removeRow(row)
                self.video_paths = [p for i, p in enumerate(old_paths) if i not in removed_set]
                self.video_keys = {self.path_key(p) for p in self.video_paths}
                self.output_sizes = {new_index: old_sizes[old_index] for new_index, old_index in enumerate((i for i in range(len(old_paths)) if i not in removed_set)) if old_index in old_sizes}
                valid_keys = {path_identity(p) for p in self.video_paths}
                self.source_roots = {k: v for k, v in self.source_roots.items() if k in valid_keys}
            for key, (_path, root) in by_key.items():
                if self.path_key(_path) in self.video_keys:
                    self.source_roots[key] = root
            added = 0
            for key, (path, root) in by_key.items():
                if self.path_key(path) not in self.video_keys:
                    added += super().add_paths([path], source_root=root)
            for row, path in enumerate(self.video_paths):
                try:
                    size = Path(path).stat().st_size
                except OSError:
                    continue
                item = self.table.item(row, 0)
                previous = item.data(Qt.ItemDataRole.UserRole + 1)
                if previous != size:
                    item.setData(Qt.ItemDataRole.UserRole + 1, size)
                    self.table.item(row, 3).setText(self.format_size(size))
                    self.output_sizes.pop(row, None)
                    self.table.item(row, 4).setText('—')
                    self.table.item(row, 5).setText('—')
            self.update_paths()
            self.update_actions()
            self.refresh_destinations()
            if errors:
                self.statusBar().showMessage('Actualisation incomplète : ' + errors[0], 6000)
            elif added or removed_rows:
                self.statusBar().showMessage(f'Dossiers synchronisés : +{added}, -{len(removed_rows)} vidéo(s)', 5000)
        finally:
            self._syncing = False

    def refresh_destinations(self, *_args):
        if self.is_converting() or not hasattr(self, 'table') or self.table.columnCount() < 12:
            return
        if not self.output_dir:
            targets = ()
        else:
            targets = tuple(plan_destinations(self.video_paths, self.source_roots, self.output_dir, self.container_combo.currentData(), preserve_tree=self.preserve_tree_check.isChecked()))
        if targets != self._destinations:
            # Pas de reset global : le contrôleur final recalcule les données
            # ligne par ligne selon la destination et l'existence réelle.
            self._destinations = targets
        for row in range(self.table.rowCount()):
            target = str(targets[row]) if row < len(targets) else '—'
            item = self.table.item(row, 11)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, 11, item)
            item.setText(target)
            item.setToolTip(target)

    def select_output_dir(self):
        previous = self.output_dir
        super().select_output_dir()
        if self.output_dir == previous:
            return
        # Ne pas scanner toutes les vidéos quand le dossier de sortie
        # n'est pas à l'intérieur d'une racine surveillée. Le scan synchrone
        # était susceptible de figer momentanément l'interface.
        if output_change_requires_rescan(
            previous, self.output_dir, self.monitored_roots.values()
        ):
            self.refresh_sources()  # met aussi les destinations à jour
        else:
            self.refresh_destinations()

    def remove_selected(self):
        selected = {index.row() for index in self.table.selectedIndexes()}
        for row in selected:
            item = self.table.item(row, 0)
            if item:
                key = path_identity(item.data(Qt.ItemDataRole.UserRole))
                self.manual_files.discard(key)
                self.excluded_files.add(key)
        super().remove_selected()
        self.refresh_destinations()

    def clear_videos(self):
        self.monitored_roots.clear()
        self.manual_files.clear()
        self.excluded_files.clear()
        self.generated_targets.clear()
        super().clear_videos()
        self.refresh_destinations()

    def on_options_changed(self, _value=None):
        super().on_options_changed(_value)
        if hasattr(self, 'table') and self.table.columnCount() == 12:
            self.refresh_destinations()

    def apply_conversion_settings(self, settings, select_preset=None):
        super().apply_conversion_settings(settings, select_preset=select_preset)
        if hasattr(self, 'table') and self.table.columnCount() == 12:
            self.refresh_destinations()

    def start_conversion(self):
        self.refresh_sources()
        self.refresh_destinations()
        planned_targets = tuple(self._destinations)
        super().start_conversion()
        if self.is_converting():
            self.generated_targets.update((path_identity(p) for p in planned_targets))
            self.refresh_button.setEnabled(False)

    def on_worker_finished(self):
        super().on_worker_finished()
        self.refresh_button.setEnabled(True)
        QTimer.singleShot(0, self.refresh_sources)

class _CompactUI(_SourceUI):

    def __init__(self):
        self._compact_ready = False
        self._height_before_advanced = None
        super().__init__()
        self.setWindowTitle('FFmpeg GUI — V0.8.1')
        self.resize(1450, 850)
        self._reorganize_interface()
        self._compact_ready = True
        self.update_paths()
        self._configure_table()
        self._enable_small_windows()

    @staticmethod
    def _readonly_path():
        field = QLineEdit()
        field.setReadOnly(True)
        field.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        field.setMinimumWidth(110)
        field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return field

    def _reorganize_interface(self):
        main_layout = self.centralWidget().layout()
        old_paths_group = main_layout.itemAt(1).widget()
        ffmpeg_group = main_layout.itemAt(2).widget()
        old_paths_group.hide()
        compact_group = QGroupBox('Fichiers et dossiers')
        compact_layout = QVBoxLayout(compact_group)
        compact_layout.setContentsMargins(10, 10, 10, 10)
        compact_layout.setSpacing(6)
        first_row = QHBoxLayout()
        first_row.setSpacing(7)
        compact_layout.addLayout(first_row)
        self.input_path_field = self._readonly_path()
        self.output_path_field = self._readonly_path()
        self.input_path_field.setPlaceholderText('Aucun dossier importé')
        self.output_path_field.setPlaceholderText('Choisir un dossier de sortie')
        first_row.addWidget(self.import_button)
        first_row.addWidget(self.folder_button)
        first_row.addWidget(QLabel('Entrée :'))
        first_row.addWidget(self.input_path_field, 3)
        first_row.addWidget(self.output_button)
        first_row.addWidget(QLabel('Sortie :'))
        first_row.addWidget(self.output_path_field, 3)
        first_row.addWidget(self.refresh_button)
        check_row = QHBoxLayout()
        check_row.setSpacing(12)
        check_row.addWidget(self.recursive_check)
        check_row.addWidget(self.preserve_tree_check)
        check_row.addStretch(1)
        compact_layout.addLayout(check_row)
        main_layout.insertWidget(1, compact_group)
        self.advanced_button = QPushButton('▸ Afficher les réglages avancés')
        self.advanced_button.setCheckable(True)
        self.advanced_button.setChecked(False)
        self.advanced_button.setToolTip('Afficher ou masquer les réglages vidéo, audio, sous-titres et format.')
        ffmpeg_layout = ffmpeg_group.layout()
        options_layout = ffmpeg_layout.itemAt(2).layout()
        self._advanced_panels = [options_layout.itemAt(index).widget() for index in range(options_layout.count()) if options_layout.itemAt(index).widget() is not None]
        ffmpeg_layout.insertWidget(2, self.advanced_button)
        self.advanced_button.toggled.connect(self._toggle_advanced)
        self._toggle_advanced(False)
        self.table.setMinimumHeight(80)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        for index in range(main_layout.count()):
            item = main_layout.itemAt(index)
            main_layout.setStretch(index, 1 if item.widget() is self.table else 0)
        self.import_button.setToolTip('Choisir des vidéos individuelles')
        self.folder_button.setToolTip('Importer et surveiller un dossier')
        self.refresh_button.setToolTip('Actualiser les dossiers surveillés')

    def _enable_small_windows(self):
        """Éviter que les minima des panneaux bloquent la taille de fenêtre.

        En dessous de la hauteur nécessaire, les contrôles restent accessibles
        en faisant défiler la page. À hauteur normale, le tableau s'étend.
        """
        content = self.takeCentralWidget()
        scroll = QScrollArea(self)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content.setMinimumSize(0, 0)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)
        self.setMinimumSize(620, 340)

    def _toggle_advanced(self, expanded):
        if expanded and self._compact_ready:
            self._height_before_advanced = self.height()
        for panel in self._advanced_panels:
            panel.setVisible(expanded)
        self.advanced_button.setText('▾ Masquer les réglages avancés' if expanded else '▸ Afficher les réglages avancés')
        if not expanded and self._compact_ready:
            wanted_height = self._height_before_advanced
            self._height_before_advanced = None
            if wanted_height is not None:
                QTimer.singleShot(0, lambda h=wanted_height: self._restore_height(h))

    def _restore_height(self, height):
        if not self.advanced_button.isChecked():
            self.resize(self.width(), max(self.minimumHeight(), height))

    def _configure_table(self):
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        widths = [235, 225, 75, 100, 100, 85, 110, 105, 105, 110, 75, 330]
        for index, width in enumerate(widths):
            header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(index, width)
        header.setStretchLastSection(True)
        self.table.setHorizontalScrollMode(self.table.ScrollMode.ScrollPerPixel)
        self.table.setWordWrap(False)

    def update_paths(self):
        super().update_paths()
        if not getattr(self, '_compact_ready', False):
            return
        sources = self.input_label.text().partition(': ')[2]
        destination = self.output_label.text().partition(': ')[2]
        self.input_path_field.setText(sources)
        self.input_path_field.setToolTip(self.input_label.toolTip() or sources)
        self.input_path_field.setCursorPosition(0)
        self.output_path_field.setText(destination)
        self.output_path_field.setToolTip(destination)
        self.output_path_field.setCursorPosition(0)

class _ParallelUI(_CompactUI):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('FFmpeg GUI — V0.9')
        self._add_parallel_control()

    def _add_parallel_control(self):
        content = self.centralWidget().widget()
        layout = content.layout()
        conversion_row = None
        for index in range(layout.count()):
            nested = layout.itemAt(index).layout()
            if nested and any((nested.itemAt(i).widget() is self.start_button for i in range(nested.count()))):
                conversion_row = nested
                break
        if conversion_row is None:
            raise RuntimeError('Impossible de localiser les boutons de conversion.')
        self.parallel_label = QLabel('Conversions simultanées :')
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 4)
        self.parallel_spin.setValue(1)
        self.parallel_spin.setToolTip("Nombre de vidéos encodées en même temps (1 à 4). Plus n'est pas toujours plus rapide avec H.265.")
        try:
            saved = int(self.settings.value('max_parallel', 1))
        except (TypeError, ValueError):
            saved = 1
        self.parallel_spin.setValue(max(1, min(4, saved)))
        self.parallel_spin.valueChanged.connect(lambda value: self.settings.setValue('max_parallel', value))
        conversion_row.insertWidget(2, self.parallel_label)
        conversion_row.insertWidget(3, self.parallel_spin)
        self.update_actions()

    def update_actions(self):
        super().update_actions()
        if hasattr(self, 'parallel_spin'):
            self.parallel_spin.setEnabled(not self.is_converting())

    def start_conversion(self):
        if self.is_converting() or not self.video_paths:
            return
        # Vérifications rapides AVANT un rescan potentiellement coûteux.
        # Lancer sans dossier de sortie ne doit jamais analyser les sources.
        if not self.output_dir:
            QMessageBox.warning(self, 'Dossier de sortie', 'Choisis un dossier de sortie.')
            return
        if not Path(self.output_dir).is_dir():
            QMessageBox.warning(self, 'Dossier de sortie', 'Le dossier de sortie est introuvable ou inaccessible.')
            return
        self.remember_ffmpeg()
        if not Path(self.ffmpeg_path).is_file():
            QMessageBox.warning(self, 'FFmpeg', 'Sélectionne un fichier ffmpeg.exe valide.')
            return
        self.refresh_sources()
        self.refresh_destinations()
        settings = self.current_conversion_settings()
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, 'Paramètres incompatibles', str(exc))
            return
        targets = plan_destinations(self.video_paths, self.source_roots, self.output_dir, settings.container, preserve_tree=self.preserve_tree_check.isChecked())
        identities = {path_identity(source) for source in self.video_paths}
        if any((path_identity(target) in identities for target in targets)):
            QMessageBox.warning(self, 'Dossier de sortie', 'Une destination correspond à une vidéo source du lot. Choisis un autre dossier de sortie.')
            return
        self.batch_elapsed_label.setText('Temps écoulé du lot : 00:00:00')
        self.batch_eta_label.setText('Temps restant estimé du lot : —')
        self.batch_eta_seconds = None
        self.active_file_started_at = None
        self.active_file_index = None
        for row in range(self.table.rowCount()):
            target = Path(targets[row])
            if not target.is_file():
                self.table.item(row, 6).setText('En attente')
                self.table.cellWidget(row, 7).setValue(0)
                for column in (8, 9, 10):
                    self.table.item(row, column).setText('—')
            self.table.item(row, 0).setToolTip(f'Destination prévue : {target}')
        # Les sorties existantes ne doivent pas perdre leurs statistiques
        # lors du démarrage d'un nouveau lot.
        if getattr(self, '_output_sync_ready', False):
            self._sync_output_queue()
        parallel = self.parallel_spin.value()
        if parallel == 1:
            self.worker = ConversionWorker(self.video_paths, self.output_dir, self.ffmpeg_path, settings=settings, parent=self, targets=targets)
        else:
            self.worker = ParallelBatchController(self.video_paths, self.output_dir, self.ffmpeg_path, settings, targets, max_parallel=parallel, parent=self)
        self.worker.state_changed.connect(self.on_file_state)
        self.worker.progress_changed.connect(self.on_file_progress)
        self.worker.output_measured.connect(self.on_output_measured)
        self.worker.timing_started.connect(self.on_timing_started)
        self.worker.timing_updated.connect(self.on_timing_updated)
        self.worker.timing_finished.connect(self.on_timing_finished)
        self.worker.batch_finished.connect(self.on_batch_finished)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.conversion_active = True
        self.cancel_button.setEnabled(True)
        self.generated_targets.update((path_identity(p) for p in targets))
        self.refresh_button.setEnabled(False)
        self.batch_started_at = time.monotonic()
        self.elapsed_timer.start()
        self.update_actions()
        self.worker.start()
        self.statusBar().showMessage(f'Conversions en cours — {parallel} simultanée(s) au maximum')

    def on_timing_started(self, index):
        if self.parallel_spin.value() == 1:
            return super().on_timing_started(index)
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 8).setText('00:00:00')
            self.table.item(index, 9).setText('—')
            self.table.item(index, 10).setText('—')

    def on_timing_updated(self, index, elapsed, remaining, speed, batch_remaining):
        if self.parallel_spin.value() == 1:
            return super().on_timing_updated(index, elapsed, remaining, speed, batch_remaining)
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 8).setText(format_duration(elapsed))
            self.table.item(index, 9).setText(format_duration(remaining))
            self.table.item(index, 10).setText(f'{speed:.2f}x' if speed > 0 else '—')
        self.batch_eta_label.setText('Temps restant estimé du lot : — (parallèle)')

    def on_timing_finished(self, index, elapsed):
        if self.parallel_spin.value() == 1:
            return super().on_timing_finished(index, elapsed)
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 8).setText(format_duration(elapsed))
            self.table.item(index, 9).setText('—')

    def on_worker_finished(self):
        self.elapsed_timer.stop()
        if self.batch_started_at is not None:
            self.batch_elapsed_label.setText(f'Temps écoulé du lot : {format_duration(time.monotonic() - self.batch_started_at)}')
        super().on_worker_finished()

class _DropUI(_ParallelUI):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('FFmpeg GUI — V0.10')
        self._install_drop_targets()
        self._restore_layout_preferences()

    def _install_drop_targets(self):
        """Surveiller également les zones qui captent les événements Qt.

        Le contenu principal est dans une QScrollArea depuis la V0.8.1.
        La table possède son propre viewport : activer seulement le drop sur
        QMainWindow ne suffirait donc pas.
        """
        scroll = self.centralWidget()
        content = scroll.widget()
        candidates = [self, scroll, scroll.viewport(), content, self.table, self.table.viewport(), self.input_path_field]
        self._drop_targets = []
        for widget in candidates:
            if widget is None or widget in self._drop_targets:
                continue
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)
            self._drop_targets.append(widget)
        self.import_button.setToolTip('Choisir des vidéos ou glisser des fichiers MKV/MP4 dans la fenêtre')
        self.folder_button.setToolTip('Importer un dossier ; vous pouvez aussi le glisser dans la fenêtre')

    def eventFilter(self, watched, event):
        if watched in getattr(self, '_drop_targets', ()):
            event_type = event.type()
            if event_type in (QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop):
                mime = event.mimeData()
                if self.is_converting() or not mime.hasUrls():
                    event.ignore()
                    return True
                urls = mime.urls()
                if not any((url.isLocalFile() for url in urls)):
                    event.ignore()
                    return True
                if event_type == QEvent.Type.Drop:
                    paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
                    self._handle_dropped_paths(paths)
                event.acceptProposedAction()
                return True
        return super().eventFilter(watched, event)

    def _handle_dropped_paths(self, paths):
        """Ajout direct des fichiers ; surveillance persistante des dossiers.

        Le scan, l'anti-doublon et le calcul des destinations sont ceux de la
        V0.7. Les fichiers ajoutés à la main restent manuels, même s'ils se
        trouvent dans un sous-dossier suivi.
        """
        if self.is_converting():
            return
        videos, folders = classify_paths(paths)
        if not videos and (not folders):
            self.statusBar().showMessage('Aucun fichier vidéo MKV/MP4 ou dossier valide dans le dépôt.', 6000)
            return
        for folder in folders:
            self.monitored_roots[path_identity(folder)] = folder
            self.excluded_files = {key for key in self.excluded_files if not self._belongs_to_root(key, folder)}
        for video in videos:
            key = path_identity(video)
            self.manual_files.add(key)
            self.excluded_files.discard(key)
        before = len(self.video_paths)
        if videos:
            self.add_paths(videos)
        if folders:
            self.refresh_sources()
        self.refresh_destinations()
        latest = videos[0] if videos else folders[0]
        self.remember_input_dir(str(Path(latest).parent if videos else Path(latest)))
        added = len(self.video_paths) - before
        self.statusBar().showMessage(f'Glisser-déposer : {added} vidéo(s) ajoutée(s), {len(folders)} dossier(s) surveillé(s).', 6500)

    def _restore_layout_preferences(self):
        """QSettings stocke localement la géométrie et les colonnes.

        Pas de chemins de fichiers sauvegardés ici ; ceux de FFmpeg et des
        dossiers restent gérés par l'interface existante.
        """
        geometry = self.settings.value('v010/window_geometry')
        if geometry:
            self.restoreGeometry(geometry)
        header = self.settings.value('v010/table_header')
        if header:
            self.table.horizontalHeader().restoreState(header)
        advanced = self.settings.value('v010/advanced_open', False, type=bool)
        if advanced:
            self.advanced_button.setChecked(True)

    def closeEvent(self, event):
        super().closeEvent(event)
        if not event.isAccepted():
            return
        self.settings.setValue('v010/window_geometry', self.saveGeometry())
        self.settings.setValue('v010/table_header', self.table.horizontalHeader().saveState())
        self.settings.setValue('v010/advanced_open', self.advanced_button.isChecked())
        self.settings.sync()

class _RenamingUI(_DropUI):

    def __init__(self):
        self._tracked_fingerprints = {}
        super().__init__()
        self.setWindowTitle('FFmpeg GUI')

    def add_paths(self, paths, source_root=None):
        result = super().add_paths(paths, source_root=source_root)
        for path in paths:
            if self.path_key(path) in self.video_keys:
                signature = file_signature(path)
                if signature is not None:
                    self._tracked_fingerprints[path_identity(path)] = signature
        return result

    def refresh_sources(self, *_args):
        if self.is_converting() or self._syncing:
            return
        renamed = self._refresh_manual_renames()
        super().refresh_sources(*_args)
        present = {path_identity(path) for path in self.video_paths}
        self._tracked_fingerprints = {key: signature for key, signature in self._tracked_fingerprints.items() if key in present}
        for path in self.video_paths:
            signature = file_signature(path)
            if signature is not None:
                self._tracked_fingerprints[path_identity(path)] = signature
        if renamed:
            self.statusBar().showMessage(f'{renamed} vidéo(s) renommée(s) retrouvée(s) automatiquement.', 5000)

    def _refresh_manual_renames(self):
        """Corrige chemin et nom AVANT le nettoyage des fichiers manquants V0.7."""
        occupied = set(self.video_paths)
        renamed_count = 0
        for row, old_path in enumerate(list(self.video_paths)):
            old_key = path_identity(old_path)
            if old_key not in self.manual_files or Path(old_path).is_file():
                continue
            signature = self._tracked_fingerprints.get(old_key)
            candidate = renamed_candidate(old_path, signature, occupied)
            if candidate is None:
                continue
            new_key = path_identity(candidate)
            if new_key in self.manual_files or self.path_key(candidate) in self.video_keys:
                continue
            self.video_paths[row] = candidate
            self.video_keys.discard(self.path_key(old_path))
            self.video_keys.add(self.path_key(candidate))
            self.manual_files.discard(old_key)
            self.manual_files.add(new_key)
            root = self.source_roots.pop(old_key, None)
            self.source_roots[new_key] = root
            self._tracked_fingerprints.pop(old_key, None)
            self._tracked_fingerprints[new_key] = signature
            self.excluded_files.discard(new_key)
            name_item = self.table.item(row, 0)
            name_item.setText(Path(candidate).name)
            name_item.setData(Qt.ItemDataRole.UserRole, candidate)
            self.table.item(row, 1).setText(str(Path(candidate).parent))
            self.table.item(row, 2).setText(Path(candidate).suffix.lower())
            self.output_sizes.pop(row, None)
            self.table.item(row, 4).setText('—')
            self.table.item(row, 5).setText('—')
            self.table.item(row, 4).setToolTip('')
            self.table.item(row, 6).setText('En attente')
            self.table.cellWidget(row, 7).setValue(0)
            for col in (8, 9, 10):
                self.table.item(row, col).setText('—')
            occupied.add(candidate)
            renamed_count += 1
        return renamed_count

    def remove_selected(self):
        super().remove_selected()
        remaining = {path_identity(path) for path in self.video_paths}
        self._tracked_fingerprints = {key: value for key, value in self._tracked_fingerprints.items() if key in remaining}

    def clear_videos(self):
        super().clear_videos()
        self._tracked_fingerprints.clear()


class FFmpegGUI(_RenamingUI):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('FFmpeg GUI — V1.0')
        self._add_clear_output_button()
        self._add_ffmpeg_help()
        self.update_paths()
        self._update_ffmpeg_help()

    def _add_clear_output_button(self):
        # Le premier layout du groupe compact est la rangée des chemins.
        container = self.input_path_field.parentWidget()
        path_row = container.layout().itemAt(0).layout()
        if path_row is None:
            raise RuntimeError('Impossible de trouver la rangée des chemins.')
        index = path_row.indexOf(self.output_path_field)
        if index < 0:
            raise RuntimeError('Champ du dossier de sortie introuvable.')
        self.clear_output_button = QPushButton('Effacer')
        self.clear_output_button.setToolTip('Retirer le dossier de sortie mémorisé')
        self.clear_output_button.clicked.connect(self.clear_output_dir)
        path_row.insertWidget(index + 1, self.clear_output_button)
        self.clear_output_button.setEnabled(bool(self.output_dir))

    def clear_output_dir(self):
        """Retire la sélection sans supprimer ni modifier aucun fichier."""
        if self.is_converting() or not self.output_dir:
            return
        previous = self.output_dir
        self.output_dir = ''
        self.settings.remove('output_dir')
        self.settings.sync()
        self.update_paths()
        if output_change_requires_rescan(
            previous, '', self.monitored_roots.values()
        ):
            self.refresh_sources()
        else:
            self.refresh_destinations()
        self.statusBar().showMessage('Dossier de sortie effacé.', 4000)

    def _add_ffmpeg_help(self):
        """Indication non bloquante, visible si FFmpeg est introuvable."""
        # ffmpeg_edit et le bouton Parcourir restent accessibles.
        ffmpeg_group = self.ffmpeg_edit.parentWidget()
        group_layout = ffmpeg_group.layout()
        if group_layout is None:
            raise RuntimeError('Groupe des paramètres FFmpeg introuvable.')
        self.ffmpeg_help_label = QLabel(
            'FFmpeg introuvable. Télécharge-le sur '
            '<a href="https://ffmpeg.org/download.html">ffmpeg.org</a> '
            '(ffmpeg.exe se trouve dans le dossier bin du téléchargement).'
        )
        self.ffmpeg_help_label.setWordWrap(True)
        self.ffmpeg_help_label.setTextFormat(Qt.TextFormat.RichText)
        self.ffmpeg_help_label.setOpenExternalLinks(True)
        self.ffmpeg_help_label.setStyleSheet('color: #d29c57;')
        group_layout.insertWidget(1, self.ffmpeg_help_label)
        self.ffmpeg_edit.textChanged.connect(self._update_ffmpeg_help)

    def _resolved_ffmpeg(self):
        typed = self.ffmpeg_edit.text().strip().strip('"')
        if typed and Path(typed).is_file():
            return typed
        # Ne pas substituer silencieusement un autre exécutable lorsque
        # l'utilisateur a choisi explicitement un chemin incorrect.
        if typed:
            return ''
        return locate_ffmpeg()

    def _update_ffmpeg_help(self, *_args):
        if hasattr(self, 'ffmpeg_help_label'):
            self.ffmpeg_help_label.setVisible(not bool(self._resolved_ffmpeg()))

    def update_paths(self):
        super().update_paths()
        if hasattr(self, 'clear_output_button'):
            self.clear_output_button.setEnabled(
                bool(self.output_dir) and not self.is_converting()
            )

    def update_actions(self):
        super().update_actions()
        if hasattr(self, 'clear_output_button'):
            self.clear_output_button.setEnabled(
                bool(self.output_dir) and not self.is_converting()
            )

    def start_conversion(self):
        # Vérification avant les rescans potentiellement coûteux du lot.
        if not self.video_paths or self.is_converting():
            return
        if not self.output_dir:
            QMessageBox.warning(
                self, 'Dossier de sortie',
                'Choisis un dossier de sortie avant de lancer la conversion.'
            )
            return
        resolved = self._resolved_ffmpeg()
        if not resolved:
            QMessageBox.warning(
                self, 'FFmpeg introuvable',
                'FFmpeg introuvable. Télécharge-le sur https://ffmpeg.org/download.html\n'
                '(ffmpeg.exe se trouve dans le dossier bin du téléchargement).'
            )
            self._update_ffmpeg_help()
            return
        # La version précédente contrôle le chemin de l'exécutable ; si
        # le champ est vide mais FFmpeg est dans le PATH, remplir le champ.
        if not self.ffmpeg_edit.text().strip():
            self.ffmpeg_edit.setText(resolved)
        super().start_conversion()


# Interface vidéo V1.0 : conservée sans modification pour la compatibilité.
VideoGUI = FFmpegGUI


"""V1.1 — Extraction audio, en complément intact de la conversion vidéo V1.0.

Intégration de l’extraction audio dans l’interface principale.
"""

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
)

from config import ConversionSettings
from converter import ConversionWorker, ParallelBatchController, probe_duration
from file_utils import path_identity, plan_destinations, publish_without_overwrite
from metrics import format_duration, parse_out_time, parse_speed, estimate_remaining


@dataclass(frozen=True)
class AudioSettings:
    container: str = "wav"
    bitrate: str = "192k"
    sample_rate: int = 48000
    channels: int = 2

    def validate(self):
        if self.container not in {"wav", "mp3", "ogg", "flac", "m4a"}:
            raise ValueError("Format audio inconnu.")
        if self.bitrate not in {"128k", "192k", "256k", "320k"}:
            raise ValueError("Débit audio invalide.")
        if self.sample_rate not in {44100, 48000}:
            raise ValueError("Fréquence d'échantillonnage invalide.")
        if self.channels not in {1, 2}:
            raise ValueError("Nombre de canaux invalide.")


def build_audio_command(ffmpeg, source, target, settings):
    """Extrait la première piste audio, sans jamais inclure la vidéo."""
    settings.validate()
    codecs = {
        "wav": "pcm_s16le", "mp3": "libmp3lame", "ogg": "libvorbis",
        "flac": "flac", "m4a": "aac",
    }
    command = [
        str(ffmpeg), "-hide_banner", "-nostdin", "-nostats", "-y",
        "-i", str(source), "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-c:a", codecs[settings.container],
        "-ar", str(settings.sample_rate), "-ac", str(settings.channels),
    ]
    if settings.container in {"mp3", "ogg", "m4a"}:
        command += ["-b:a", settings.bitrate]
    command += ["-progress", "pipe:1", str(target)]
    return command


class AudioWorker(ConversionWorker):
    """Même contrat de signaux/annulation que ConversionWorker, codec audio dédié."""

    def __init__(self, sources, output_folder, ffmpeg_path, settings, targets, parent=None):
        self.audio_settings = settings
        self.audio_settings.validate()
        super().__init__(
            sources, output_folder, ffmpeg_path,
            settings=ConversionSettings(), targets=targets, parent=parent,
        )

    def run(self):
        done = skipped = failed = 0
        errors = []
        try:
            self.output_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.batch_finished.emit(0, 0, len(self.sources), False, [str(exc)])
            return

        for index, name in enumerate(self.sources):
            if self.cancel_event.is_set():
                break
            source, target = Path(name), self.targets[index]
            if target.exists():
                skipped += 1
                self.state_changed.emit(index, "Déjà converti")
                self.progress_changed.emit(index, 100)
                try:
                    self.output_measured.emit(index, target.stat().st_size, "Déjà converti")
                except OSError:
                    pass
                continue
            if not source.is_file():
                failed += 1
                self.state_changed.emit(index, "Source introuvable")
                errors.append(f"{source.name} : source introuvable")
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                failed += 1
                self.state_changed.emit(index, "Erreur")
                errors.append(f"{source.name} : {exc}")
                continue

            duration = probe_duration(self.ffmpeg_path, source)
            if self.cancel_event.is_set():
                break
            temporary = target.parent / (
                f".{target.stem}.{uuid.uuid4().hex}.part.{self.audio_settings.container}"
            )
            process = None
            reader = None
            started = None
            recent_errors = []
            self.state_changed.emit(index, "Extraction en cours")
            self.progress_changed.emit(index, 0)
            try:
                command = build_audio_command(
                    self.ffmpeg_path, source, temporary, self.audio_settings
                )
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1, errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                with self._process_lock:
                    self._process = process
                started = time.monotonic()
                self.timing_started.emit(index)

                def read_errors():
                    for line in process.stderr:
                        recent_errors.append(line.rstrip())
                        if len(recent_errors) > 25:
                            recent_errors.pop(0)

                reader = threading.Thread(target=read_errors, daemon=True)
                reader.start()
                progress = {}
                for raw_line in process.stdout:
                    if self.cancel_event.is_set():
                        break
                    key, sep, value = raw_line.strip().partition("=")
                    if not sep:
                        continue
                    progress[key] = value
                    if key != "progress":
                        continue
                    processed = parse_out_time(progress)
                    speed = parse_speed(progress.get("speed"))
                    elapsed = time.monotonic() - started
                    remaining = estimate_remaining(duration, processed, speed)
                    if duration and processed is not None:
                        self.progress_changed.emit(
                            index, min(99, max(0, int(processed / duration * 100)))
                        )
                    self.timing_updated.emit(
                        index, elapsed, remaining if remaining is not None else -1.0,
                        speed if speed is not None else -1.0, -1.0,
                    )
                    progress.clear()
                if self.cancel_event.is_set() and process.poll() is None:
                    process.terminate()
                result = process.wait()
                if reader:
                    reader.join(timeout=2)
                if self.cancel_event.is_set():
                    self.state_changed.emit(index, "Annulé")
                    break
                if result != 0:
                    failed += 1
                    self.state_changed.emit(index, "Erreur")
                    errors.append(
                        f"{source.name} : {' | '.join(recent_errors[-4:]) or 'FFmpeg a échoué'}"
                    )
                    continue
                if publish_without_overwrite(temporary, target):
                    done += 1
                    label = "Terminé"
                else:
                    skipped += 1
                    label = "Déjà converti"
                self.state_changed.emit(index, label)
                self.progress_changed.emit(index, 100)
                try:
                    self.output_measured.emit(index, target.stat().st_size, label)
                except OSError:
                    pass
            except (OSError, ValueError) as exc:
                failed += 1
                self.state_changed.emit(index, "Erreur")
                errors.append(f"{source.name} : {exc}")
            finally:
                if started is not None:
                    self.timing_finished.emit(index, time.monotonic() - started)
                if process and process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                with self._process_lock:
                    self._process = None
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

        self.batch_finished.emit(done, skipped, failed, self.cancel_event.is_set(), errors)


class AudioParallelController(ParallelBatchController):
    """Réutilise la gestion des slots et l'annulation de la V1.0."""

    def _fill_slots(self):
        if self._finished:
            return
        while (
            not self._cancelled and len(self._active) < self.max_parallel
            and self._next_index < len(self.sources)
        ):
            index = self._next_index
            self._next_index += 1
            worker = AudioWorker(
                [self.sources[index]], self.output_folder, self.ffmpeg_path,
                self.settings, [self.targets[index]], parent=self,
            )
            self._active[index] = worker
            worker.state_changed.connect(
                lambda _i, state, row=index: self.state_changed.emit(row, state)
            )
            worker.progress_changed.connect(
                lambda _i, value, row=index: self.progress_changed.emit(row, value)
            )
            worker.timing_started.connect(
                lambda _i, row=index: self.timing_started.emit(row)
            )
            worker.timing_updated.connect(
                lambda _i, elapsed, remaining, speed, _batch, row=index:
                self.timing_updated.emit(row, elapsed, remaining, speed, -1.0)
            )
            worker.timing_finished.connect(
                lambda _i, elapsed, row=index: self.timing_finished.emit(row, elapsed)
            )
            worker.output_measured.connect(
                lambda _i, size, state, row=index:
                self.output_measured.emit(row, size, state)
            )
            worker.batch_finished.connect(
                lambda done, skipped, failed, cancelled, errors, row=index:
                self._results.__setitem__(row, (done, skipped, failed, errors))
            )
            worker.finished.connect(lambda row=index: self._worker_finished(row))
            worker.finished.connect(worker.deleteLater)
            worker.start()
        if not self._active and (
            self._cancelled or self._next_index >= len(self.sources)
        ):
            self._finish()


class FFmpegGUI(VideoGUI):
    """Sélecteur de traitement et panneau audio ; mode vidéo inchangé."""

    def __init__(self):
        # La synchronisation des sorties démarre seulement après la création
        # complète des widgets et des réglages audio.
        self._output_sync_ready = False
        self._last_target_for_source = {}
        self._audio_ready = False
        super().__init__()
        self.setWindowTitle("FFmpeg GUI — V1.1")
        self._add_processing_mode()
        self._add_audio_settings()
        self._audio_ready = True
        mode = self.settings.value("v11/processing_mode", "video")
        self.mode_combo.setCurrentIndex(1 if mode == "audio" else 0)
        self._change_mode()
        self._output_sync_ready = True
        self.refresh_destinations()

    def _add_processing_mode(self):
        main_layout = self.centralWidget().widget().layout()
        title_item = main_layout.takeAt(0)
        title = title_item.widget()
        title_row = QHBoxLayout()
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(QLabel("Type de traitement :"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Conversion vidéo", "video")
        self.mode_combo.addItem("Extraction audio", "audio")
        self.mode_combo.setMinimumWidth(190)
        title_row.addWidget(self.mode_combo)
        main_layout.insertLayout(0, title_row)
        self.mode_combo.currentIndexChanged.connect(self._change_mode)

    def _add_audio_settings(self):
        ffmpeg_group = self.ffmpeg_edit.parentWidget()
        layout = ffmpeg_group.layout()
        self.audio_group = QGroupBox("Paramètres d'extraction audio")
        row = QHBoxLayout(self.audio_group)
        self.audio_format = QComboBox()
        for label, value in (
            ("WAV (PCM)", "wav"), ("MP3", "mp3"), ("OGG Vorbis", "ogg"),
            ("FLAC", "flac"), ("M4A (AAC)", "m4a"),
        ):
            self.audio_format.addItem(label, value)
        self.audio_bitrate = QComboBox()
        for rate in ("128k", "192k", "256k", "320k"):
            self.audio_bitrate.addItem(rate.replace("k", " kb/s"), rate)
        self.audio_sample_rate = QComboBox()
        for rate in (44100, 48000):
            self.audio_sample_rate.addItem(f"{rate:,} Hz".replace(",", " "), rate)
        self.audio_channels = QComboBox()
        self.audio_channels.addItem("Mono", 1)
        self.audio_channels.addItem("Stéréo", 2)
        for label, widget in (
            ("Format :", self.audio_format),
            ("Bitrate :", self.audio_bitrate),
            ("Fréquence :", self.audio_sample_rate),
            ("Canaux :", self.audio_channels),
        ):
            row.addWidget(QLabel(label))
            row.addWidget(widget, 1)
        layout.insertWidget(2, self.audio_group)
        self._video_preset_widgets = []
        # La V1.0 a inséré un message d'aide FFmpeg dans ce layout :
        # ne pas supposer un index fixe pour la rangée des presets.
        for outer_index in range(layout.count()):
            preset_layout = layout.itemAt(outer_index).layout()
            if preset_layout is None:
                continue
            widgets = [
                preset_layout.itemAt(index).widget()
                for index in range(preset_layout.count())
                if preset_layout.itemAt(index).widget() is not None
            ]
            if self.preset_combo in widgets:
                self._video_preset_widgets = widgets
                break
        for key, widget, fallback in (
            ("format", self.audio_format, "wav"),
            ("bitrate", self.audio_bitrate, "192k"),
            ("sample_rate", self.audio_sample_rate, 48000),
            ("channels", self.audio_channels, 2),
        ):
            saved = self.settings.value(f"v11/audio_{key}", fallback)
            try:
                saved = int(saved) if isinstance(fallback, int) else str(saved)
            except (TypeError, ValueError):
                saved = fallback
            idx = widget.findData(saved)
            widget.setCurrentIndex(idx if idx >= 0 else widget.findData(fallback))
            widget.currentIndexChanged.connect(self._audio_option_changed)
        self.audio_group.hide()

    def _is_audio(self):
        return self._audio_ready and self.mode_combo.currentData() == "audio"

    def _audio_settings(self):
        return AudioSettings(
            container=self.audio_format.currentData(),
            bitrate=self.audio_bitrate.currentData(),
            sample_rate=self.audio_sample_rate.currentData(),
            channels=self.audio_channels.currentData(),
        )

    def _audio_option_changed(self, _index=None):
        if not self._audio_ready:
            return
        for key, widget in (
            ("format", self.audio_format), ("bitrate", self.audio_bitrate),
            ("sample_rate", self.audio_sample_rate),
            ("channels", self.audio_channels),
        ):
            self.settings.setValue(f"v11/audio_{key}", widget.currentData())
        self.audio_bitrate.setEnabled(
            self.audio_format.currentData() in {"mp3", "ogg", "m4a"}
            and not self.is_converting()
        )
        if self._is_audio():
            self.refresh_destinations()
            self.update_options_label()

    def _change_mode(self, _index=None):
        if not self._audio_ready or self.is_converting():
            return
        audio = self._is_audio()
        self.settings.setValue("v11/processing_mode", "audio" if audio else "video")
        self.audio_group.setVisible(audio)
        self.advanced_button.setVisible(not audio)
        for widget in self._video_preset_widgets:
            widget.setVisible(not audio)
        for panel in self._advanced_panels:
            panel.setVisible(not audio and self.advanced_button.isChecked())
        self.start_button.setText("Extraire l'audio" if audio else "Lancer les conversions")
        self._audio_option_changed()
        self.refresh_destinations()
        self.update_options_label()

    def update_options_label(self):
        if not self._is_audio():
            return super().update_options_label()
        settings = self._audio_settings()
        summary = (
            f"Extraction audio : {settings.container.upper()} | "
            f"{settings.sample_rate} Hz | "
            f"{'Mono' if settings.channels == 1 else 'Stéréo'}"
        )
        if settings.container in {"mp3", "ogg", "m4a"}:
            summary += f" | {settings.bitrate}"
        self.encoding_info.setText(summary)

    def refresh_destinations(self, *_args):
        if not self._is_audio():
            return super().refresh_destinations(*_args)
        if self.is_converting() or self.table.columnCount() < 12:
            return
        if self.output_dir:
            targets = tuple(plan_destinations(
                self.video_paths, self.source_roots, self.output_dir,
                self.audio_format.currentData(),
                preserve_tree=self.preserve_tree_check.isChecked(),
            ))
        else:
            targets = ()
        if targets != self._destinations:
            # Pas de reset global : le contrôleur final recalcule les données
            # ligne par ligne selon la destination et l'existence réelle.
            self._destinations = targets
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 11)
            if item is not None:
                target = str(targets[row]) if row < len(targets) else "—"
                item.setText(target)
                item.setToolTip(target)

    def update_actions(self):
        super().update_actions()
        if not self._audio_ready:
            return
        self.mode_combo.setEnabled(not self.is_converting())
        for widget in (
            self.audio_format, self.audio_bitrate,
            self.audio_sample_rate, self.audio_channels,
        ):
            widget.setEnabled(not self.is_converting())
        self.audio_bitrate.setEnabled(
            not self.is_converting() and self.audio_format.currentData()
            in {"mp3", "ogg", "m4a"}
        )

    def start_conversion(self):
        if not self._is_audio():
            return super().start_conversion()
        if self.is_converting() or not self.video_paths:
            return
        if not self.output_dir or not Path(self.output_dir).is_dir():
            QMessageBox.warning(self, "Dossier de sortie", "Choisis un dossier de sortie valide.")
            return
        resolved = self._resolved_ffmpeg()
        if not resolved:
            QMessageBox.warning(
                self, "FFmpeg introuvable",
                "Télécharge FFmpeg sur https://ffmpeg.org/download.html "
                "(l'exécutable est dans le dossier bin).",
            )
            return
        self.ffmpeg_path = resolved
        settings = self._audio_settings()
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Paramètres audio", str(exc))
            return
        self.refresh_sources()
        self.refresh_destinations()
        if not self.video_paths:
            return
        targets = plan_destinations(
            self.video_paths, self.source_roots, self.output_dir,
            settings.container, preserve_tree=self.preserve_tree_check.isChecked(),
        )
        identities = {path_identity(source) for source in self.video_paths}
        if any(path_identity(target) in identities for target in targets):
            QMessageBox.warning(self, "Sortie", "Une destination correspond à une vidéo source.")
            return
        self.batch_elapsed_label.setText("Temps écoulé du lot : 00:00:00")
        self.batch_eta_label.setText("Temps restant estimé du lot : —")
        self.batch_eta_seconds = None
        self.active_file_started_at = None
        self.active_file_index = None
        for row, target in enumerate(targets):
            if not Path(target).is_file():
                self.table.item(row, 6).setText("En attente")
                self.table.cellWidget(row, 7).setValue(0)
                for column in (8, 9, 10):
                    self.table.item(row, column).setText("—")
            self.table.item(row, 0).setToolTip(f"Destination prévue : {target}")
        self._sync_output_queue()
        parallel = self.parallel_spin.value()
        if parallel == 1:
            self.worker = AudioWorker(
                self.video_paths, self.output_dir, resolved, settings, targets, parent=self,
            )
        else:
            self.worker = AudioParallelController(
                self.video_paths, self.output_dir, resolved, settings, targets,
                max_parallel=parallel, parent=self,
            )
        for signal, handler in (
            (self.worker.state_changed, self.on_file_state),
            (self.worker.progress_changed, self.on_file_progress),
            (self.worker.output_measured, self.on_output_measured),
            (self.worker.timing_started, self.on_timing_started),
            (self.worker.timing_updated, self.on_timing_updated),
            (self.worker.timing_finished, self.on_timing_finished),
            (self.worker.batch_finished, self.on_batch_finished),
            (self.worker.finished, self.on_worker_finished),
        ):
            signal.connect(handler)
        self.worker.finished.connect(self.worker.deleteLater)
        self.conversion_active = True
        self.cancel_button.setEnabled(True)
        self.generated_targets.update(path_identity(p) for p in targets)
        self.refresh_button.setEnabled(False)
        self.batch_started_at = time.monotonic()
        self.elapsed_timer.start()
        self.update_actions()
        self.worker.start()
        self.statusBar().showMessage(
            f"Extraction audio en cours — {parallel} simultanée(s) au maximum"
        )

    def on_timing_started(self, index):
        if self._is_audio():
            self.active_file_index = None
            self.active_file_started_at = None
            if 0 <= index < self.table.rowCount():
                self.table.item(index, 8).setText("00:00:00")
                self.table.item(index, 9).setText("—")
                self.table.item(index, 10).setText("—")
            return
        return super().on_timing_started(index)

    def on_timing_updated(self, index, elapsed, remaining, speed, batch_remaining):
        if self._is_audio():
            if 0 <= index < self.table.rowCount():
                self.table.item(index, 8).setText(format_duration(elapsed))
                self.table.item(index, 9).setText(format_duration(remaining))
                self.table.item(index, 10).setText(
                    f"{speed:.2f}x" if speed > 0 else "—"
                )
            self.batch_eta_label.setText("Temps restant estimé du lot : —")
            return
        return super().on_timing_updated(index, elapsed, remaining, speed, batch_remaining)

    def on_timing_finished(self, index, elapsed):
        if self._is_audio():
            if 0 <= index < self.table.rowCount():
                self.table.item(index, 8).setText(format_duration(elapsed))
                self.table.item(index, 9).setText("—")
            return
        return super().on_timing_finished(index, elapsed)

    def refresh_destinations(self, *_args):
        # Les deux modes calculent leurs destinations respectives comme avant.
        # Le tableau est ensuite aligné sur les sorties réellement présentes.
        super().refresh_destinations(*_args)
        if not getattr(self, "_output_sync_ready", False) or self.is_converting():
            return
        self._sync_output_queue()

    def _sync_output_queue(self):
        """Garde les résultats valides et réarme les sorties supprimées.

        L'identité de la source évite de confondre les lignes après ajout ou
        retrait d'un fichier. Aucun fichier n'est créé ni supprimé ici.
        """
        previous = self._last_target_for_source
        current = {}
        targets = self._destinations
        for row, source in enumerate(self.video_paths):
            if row >= self.table.rowCount():
                break
            source_key = path_identity(source)
            target = Path(targets[row]) if row < len(targets) else None
            target_key = path_identity(target) if target is not None else None
            current[source_key] = target_key
            changed = source_key in previous and previous[source_key] != target_key

            state_item = self.table.item(row, 6)
            size_item = self.table.item(row, 4)
            reduction_item = self.table.item(row, 5)
            source_item = self.table.item(row, 0)
            progress = self.table.cellWidget(row, 7)
            if any(item is None for item in (state_item, size_item, reduction_item, source_item)) or progress is None:
                continue

            if changed:
                for column in (8, 9, 10):
                    item = self.table.item(row, column)
                    if item is not None:
                        item.setText("—")

            try:
                output_size = target.stat().st_size if target is not None and target.is_file() else None
            except OSError:
                output_size = None

            if output_size is not None:
                self.output_sizes[row] = output_size
                size_item.setText(format_bytes(output_size))
                original = source_item.data(Qt.ItemDataRole.UserRole + 1)
                reduction_item.setText(format_reduction(reduction_percentage(original, output_size)))
                if changed or state_item.text() not in ("Terminé", "Déjà converti"):
                    state_item.setText("Déjà converti")
                size_item.setToolTip("Fichier de sortie présent sur le disque.")
                if progress.value() != 100:
                    progress.setValue(100)
            else:
                self.output_sizes.pop(row, None)
                size_item.setText("—")
                size_item.setToolTip("")
                reduction_item.setText("—")
                if changed or state_item.text() in ("Terminé", "Déjà converti"):
                    state_item.setText("En attente")
                    for column in (8, 9, 10):
                        item = self.table.item(row, column)
                        if item is not None:
                            item.setText("—")
                if progress.value():
                    progress.setValue(0)

        self._last_target_for_source = current
        self.update_size_summary()
        count = self.table.rowCount()
        self.batch_progress.setValue(
            round(sum(self.table.cellWidget(row, 7).value() for row in range(count)) / count)
            if count else 0
        )
