"""V0.10 : glisser-déposer et persistance de la disposition de la fenêtre.

Extension de la V0.9 : aucun changement aux workers, presets, conversions,
statistiques ou mécanismes de synchronisation des dossiers.
"""

from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from drop_paths import classify_paths
from interface_v09 import FFmpegGUI as PreviousFFmpegGUI
from output_planning import path_identity


class FFmpegGUI(PreviousFFmpegGUI):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFmpeg GUI — V0.10")
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
        candidates = [
            self,
            scroll,
            scroll.viewport(),
            content,
            self.table,
            self.table.viewport(),
            self.input_path_field,
        ]
        self._drop_targets = []
        for widget in candidates:
            if widget is None or widget in self._drop_targets:
                continue
            widget.setAcceptDrops(True)
            widget.installEventFilter(self)
            self._drop_targets.append(widget)
        self.import_button.setToolTip(
            "Choisir des vidéos ou glisser des fichiers MKV/MP4 dans la fenêtre"
        )
        self.folder_button.setToolTip(
            "Importer un dossier ; vous pouvez aussi le glisser dans la fenêtre"
        )

    def eventFilter(self, watched, event):
        if watched in getattr(self, "_drop_targets", ()):
            event_type = event.type()
            if event_type in (
                QEvent.Type.DragEnter,
                QEvent.Type.DragMove,
                QEvent.Type.Drop,
            ):
                mime = event.mimeData()
                if self.is_converting() or not mime.hasUrls():
                    event.ignore()
                    return True
                urls = mime.urls()
                # Refuser les URLs réseau : seuls les fichiers locaux sont lus.
                if not any(url.isLocalFile() for url in urls):
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
        if not videos and not folders:
            self.statusBar().showMessage(
                "Aucun fichier vidéo MKV/MP4 ou dossier valide dans le dépôt.", 6000
            )
            return

        for folder in folders:
            self.monitored_roots[path_identity(folder)] = folder
            self.excluded_files = {
                key for key in self.excluded_files
                if not self._belongs_to_root(key, folder)
            }

        for video in videos:
            key = path_identity(video)
            self.manual_files.add(key)
            self.excluded_files.discard(key)

        before = len(self.video_paths)
        if videos:
            self.add_paths(videos)
        # Rescan immédiat : respect de « Inclure les sous-dossiers » et des
        # exclusions de dossiers de sortie, même pour un dossier glissé.
        if folders:
            self.refresh_sources()
        self.refresh_destinations()
        latest = videos[0] if videos else folders[0]
        self.remember_input_dir(str(Path(latest).parent if videos else Path(latest)))
        added = len(self.video_paths) - before
        self.statusBar().showMessage(
            f"Glisser-déposer : {added} vidéo(s) ajoutée(s), "
            f"{len(folders)} dossier(s) surveillé(s).",
            6500,
        )

    def _restore_layout_preferences(self):
        """QSettings stocke localement la géométrie et les colonnes.

        Pas de chemins de fichiers sauvegardés ici ; ceux de FFmpeg et des
        dossiers restent gérés par l'interface existante.
        """
        geometry = self.settings.value("v010/window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        header = self.settings.value("v010/table_header")
        if header:
            self.table.horizontalHeader().restoreState(header)
        advanced = self.settings.value("v010/advanced_open", False, type=bool)
        if advanced:
            self.advanced_button.setChecked(True)

    def closeEvent(self, event):
        # La version précédente empêche la fermeture pendant une conversion.
        super().closeEvent(event)
        if not event.isAccepted():
            return
        self.settings.setValue("v010/window_geometry", self.saveGeometry())
        self.settings.setValue(
            "v010/table_header", self.table.horizontalHeader().saveState()
        )
        self.settings.setValue(
            "v010/advanced_open", self.advanced_button.isChecked()
        )
        self.settings.sync()
