"""V0.10.1 : suivi des renommages de vidéos importées individuellement.

Extension ciblée de l'interface V0.10. Les conversions restent inchangées.
"""

from pathlib import Path

from PySide6.QtCore import Qt

from interface_v10 import FFmpegGUI as PreviousFFmpegGUI
from output_planning import path_identity
from rename_tracking import file_signature, renamed_candidate


class FFmpegGUI(PreviousFFmpegGUI):
    def __init__(self):
        # L'extension ne supprime aucune configuration de l'application.
        self._tracked_fingerprints = {}
        super().__init__()
        self.setWindowTitle('FFmpeg GUI — V0.10.1')

    def add_paths(self, paths, source_root=None):
        result = super().add_paths(paths, source_root=source_root)
        # S'applique aussi bien au glisser-déposer qu'à « Ajouter des vidéos ».
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
        # Actualisation de la signature d'un fichier modifié sur place.
        present = {path_identity(path) for path in self.video_paths}
        self._tracked_fingerprints = {
            key: signature
            for key, signature in self._tracked_fingerprints.items()
            if key in present
        }
        for path in self.video_paths:
            signature = file_signature(path)
            if signature is not None:
                self._tracked_fingerprints[path_identity(path)] = signature
        if renamed:
            self.statusBar().showMessage(
                f'{renamed} vidéo(s) renommée(s) retrouvée(s) automatiquement.', 5000
            )

    def _refresh_manual_renames(self):
        """Corrige chemin et nom AVANT le nettoyage des fichiers manquants V0.7."""
        occupied = set(self.video_paths)
        renamed_count = 0
        # Une suppression de dossier suivie d'une recréation n'est pas un renommage.
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
            # Garder la ligne et son ordre, mais invalider les résultats liés à
            # l'ancienne destination et à son éventuel ancien fichier.
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
        self._tracked_fingerprints = {
            key: value for key, value in self._tracked_fingerprints.items()
            if key in remaining
        }

    def clear_videos(self):
        super().clear_videos()
        self._tracked_fingerprints.clear()
