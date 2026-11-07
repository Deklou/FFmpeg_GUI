"""V0.8.1 — Interface compacte : fenêtre redimensionnable et panneaux réversibles.

Réutilise intégralement les fonctions métier et de synchronisation de V0.7.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
)

from interface_v07 import FFmpegGUI as PreviousFFmpegGUI


class FFmpegGUI(PreviousFFmpegGUI):
    def __init__(self):
        self._compact_ready = False
        self._height_before_advanced = None
        super().__init__()
        self.setWindowTitle("FFmpeg GUI — V0.8.1")
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

        # Conserver les widgets originaux (et leurs signaux) sans montrer
        # l'ancien cadre de chemins.
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

        # Moins de hauteur minimale pour laisser la fenêtre se contracter.
        self.table.setMinimumHeight(80)
        self.table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        for index in range(main_layout.count()):
            item = main_layout.itemAt(index)
            main_layout.setStretch(
                index, 1 if item.widget() is self.table else 0
            )

        self.import_button.setToolTip("Choisir des vidéos individuelles")
        self.folder_button.setToolTip("Importer et surveiller un dossier")
        self.refresh_button.setToolTip("Actualiser les dossiers surveillés")

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
        # Au moment d'ouvrir, retenir la hauteur visible de la fenêtre.
        if expanded and self._compact_ready:
            self._height_before_advanced = self.height()

        for panel in self._advanced_panels:
            panel.setVisible(expanded)
        self.advanced_button.setText(
            "▾ Masquer les réglages avancés"
            if expanded else "▸ Afficher les réglages avancés"
        )

        # Certaines mises en page Qt agrandissent la fenêtre à l'ouverture
        # mais ne réduisent pas automatiquement sa taille à la fermeture.
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
        if not getattr(self, "_compact_ready", False):
            return
        sources = self.input_label.text().partition(": ")[2]
        destination = self.output_label.text().partition(": ")[2]
        self.input_path_field.setText(sources)
        self.input_path_field.setToolTip(self.input_label.toolTip() or sources)
        self.input_path_field.setCursorPosition(0)
        self.output_path_field.setText(destination)
        self.output_path_field.setToolTip(destination)
        self.output_path_field.setCursorPosition(0)
