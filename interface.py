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
        self.batch_progress.setValue(0)
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
            if self.output_sizes:
                self.reset_output_stats()
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
        self.batch_progress.setValue(0)
        self.batch_elapsed_label.setText('Temps écoulé du lot : 00:00:00')
        self.batch_eta_label.setText('Temps restant estimé du lot : —')
        self.batch_eta_seconds = None
        self.active_file_started_at = None
        self.active_file_index = None
        self.reset_output_stats()
        for row in range(self.table.rowCount()):
            self.table.item(row, 6).setText('En attente')
            self.table.cellWidget(row, 7).setValue(0)
            for column in (8, 9, 10):
                self.table.item(row, column).setText('—')
            self.table.item(row, 0).setToolTip(f'Destination prévue : {targets[row]}')
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
