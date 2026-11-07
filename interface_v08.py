"""V0.8 — Présentation compacte de FFmpeg GUI, sans toucher au moteur V0.7.

Cette classe réorganise les widgets existants et hérite de toutes les
fonctionnalités de synchronisation et de conversion de l'interface V0.7.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from interface_v07 import FFmpegGUI as PreviousFFmpegGUI


class FFmpegGUI(PreviousFFmpegGUI):
    def __init__(self):
        self._compact_ready = False
        super().__init__()
        self.setWindowTitle("FFmpeg GUI — V0.8")
        self.resize(1450, 850)
        self._reorganize_interface()
        self._compact_ready = True
        self.update_paths()
        self._configure_table()

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

        # Le cadre initial reste en place, caché, pour préserver les références
        # utilisées par la V0.7 et leurs connexions aux signaux.
        old_paths_group.hide()
        compact_group = QGroupBox("Fichiers et dossiers")
        compact_layout = QVBoxLayout(compact_group)
        compact_layout.setContentsMargins(10, 10, 10, 10)
        compact_layout.setSpacing(6)
        first_row = QHBoxLayout()
        first_row.setSpacing(7)
        compact_layout.addLayout(first_row)

        self.input_path_field = self._readonly_path()
        self.output_path_field = self._readonly_path()
        self.input_path_field.setPlaceholderText("Aucun dossier importé")
        self.output_path_field.setPlaceholderText("Choisir un dossier de sortie")

        # Ajouter un widget à un nouveau layout le retire de son ancien
        # layout ; les mêmes boutons et callbacks continuent de fonctionner.
        first_row.addWidget(self.import_button)
        first_row.addWidget(self.folder_button)
        first_row.addWidget(QLabel("Entrée :"))
        first_row.addWidget(self.input_path_field, 3)
        first_row.addWidget(self.output_button)
        first_row.addWidget(QLabel("Sortie :"))
        first_row.addWidget(self.output_path_field, 3)
        first_row.addWidget(self.refresh_button)

        check_row = QHBoxLayout()
        check_row.setSpacing(12)
        check_row.addWidget(self.recursive_check)
        check_row.addWidget(self.preserve_tree_check)
        check_row.addStretch(1)
        compact_layout.addLayout(check_row)
        main_layout.insertWidget(1, compact_group)

        # On garde le chemin FFmpeg, le preset et le résumé visibles.
        # Seuls les deux panneaux techniques deviennent repliables.
        self.advanced_button = QPushButton("▸ Afficher les réglages avancés")
        self.advanced_button.setCheckable(True)
        self.advanced_button.setChecked(False)
        self.advanced_button.setToolTip(
            "Afficher ou masquer les réglages vidéo, audio, sous-titres et format."
        )
        ffmpeg_layout = ffmpeg_group.layout()
        options_layout = ffmpeg_layout.itemAt(2).layout()
        self._advanced_panels = [
            options_layout.itemAt(index).widget()
            for index in range(options_layout.count())
            if options_layout.itemAt(index).widget() is not None
        ]
        ffmpeg_layout.insertWidget(2, self.advanced_button)
        self.advanced_button.toggled.connect(self._toggle_advanced)
        self._toggle_advanced(False)

        # Le tableau est prioritaire dans la hauteur de fenêtre.
        self.table.setMinimumHeight(240)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        for index in range(main_layout.count()):
            item = main_layout.itemAt(index)
            if item.widget() is self.table:
                main_layout.setStretch(index, 1)
            else:
                main_layout.setStretch(index, 0)

        self.import_button.setToolTip("Choisir des vidéos individuelles")
        self.folder_button.setToolTip("Importer et surveiller un dossier")
        self.refresh_button.setToolTip("Actualiser les dossiers surveillés")

    def _toggle_advanced(self, expanded):
        for panel in self._advanced_panels:
            panel.setVisible(expanded)
        self.advanced_button.setText(
            "▾ Masquer les réglages avancés"
            if expanded else "▸ Afficher les réglages avancés"
        )

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
        if not getattr(self, "_compact_ready", False):
            return
        # On réutilise les libellés calculés par l'interface existante,
        # sans dupliquer sa logique de sélection des dossiers.
        sources = self.input_label.text().partition(": ")[2]
        destination = self.output_label.text().partition(": ")[2]
        self.input_path_field.setText(sources)
        self.input_path_field.setToolTip(self.input_label.toolTip() or sources)
        self.input_path_field.setCursorPosition(0)
        self.output_path_field.setText(destination)
        self.output_path_field.setToolTip(destination)
        self.output_path_field.setCursorPosition(0)
