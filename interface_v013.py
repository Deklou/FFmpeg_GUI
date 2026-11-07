"""V0.13 — Ergonomie de première installation et effacement de la destination.

Extension légère de l'interface V0.12 : ne change pas le moteur de conversion.
La configuration locale QSettings de l'auteur n'est jamais intégrée aux fichiers.
"""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QMessageBox

from converter import locate_ffmpeg
from file_utils import output_change_requires_rescan
from interface import FFmpegGUI as PreviousFFmpegGUI


class FFmpegGUI(PreviousFFmpegGUI):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('FFmpeg GUI — V0.13')
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
