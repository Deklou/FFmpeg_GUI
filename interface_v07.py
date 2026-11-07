"""V0.7 : synchronisation dynamique des dossiers et prévisualisation des sorties.

Extension de l'interface V0.6.1 : aucune modification de son moteur FFmpeg.
"""

from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QPushButton, QTableWidgetItem, QHeaderView,
)

from interface import FFmpegGUI as BaseFFmpegGUI
from output_planning import discover_videos, plan_destinations, path_identity


class FFmpegGUI(BaseFFmpegGUI):
    REFRESH_INTERVAL_MS = 3000

    def __init__(self):
        # Initialisés AVANT le constructeur parent : plusieurs méthodes Qt
        # sont appelées lors de la création de la fenêtre.
        self.monitored_roots = {}  # identity -> chemin du dossier importé
        self.manual_files = set()  # fichiers ajoutés explicitement
        self.excluded_files = set()  # retraits explicites, jusqu'à disparition
        self.generated_targets = set()  # ne pas réimporter nos propres sorties
        self._syncing = False
        self._destinations = ()
        super().__init__()

        self.setWindowTitle("FFmpeg GUI — V0.7")
        self.table.setColumnCount(12)
        self.table.setHorizontalHeaderLabels([
            "Nom du fichier", "Dossier source", "Format", "Taille entrée",
            "Taille sortie", "Réduction", "État", "Progression",
            "Temps écoulé", "Restant estimé", "Vitesse", "Destination",
        ])
        self.table.horizontalHeader().setSectionResizeMode(11, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(11, 260)

        # On utilise la rangée existante pour ne pas déplacer l'interface.
        buttons_layout = self.import_button.parentWidget().layout().itemAt(0).layout()
        self.refresh_button = QPushButton("Actualiser")
        self.refresh_button.setToolTip("Rescanner tous les dossiers importés")
        buttons_layout.insertWidget(2, self.refresh_button)
        self.refresh_button.clicked.connect(self.refresh_sources)

        self.recursive_check.setToolTip(
            "Appliqué immédiatement aux dossiers importés, sans nouvel import."
        )
        self.preserve_tree_check.setToolTip(
            "Actualise immédiatement la colonne Destination, sans modifier les sources."
        )
        self.recursive_check.toggled.connect(self.refresh_sources)
        self.preserve_tree_check.toggled.connect(self.refresh_destinations)
        self.container_combo.currentIndexChanged.connect(self.refresh_destinations)

        # Contrôle périodique robuste même pour les modifications non détectées
        # par un watcher natif (certaines clés USB / partages réseau).
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(self.REFRESH_INTERVAL_MS)
        self.refresh_timer.timeout.connect(self.refresh_sources)
        self.refresh_timer.start()
        self.refresh_destinations()

    def import_videos(self):
        # Les fichiers choisis à la main doivent survivre au changement de la
        # case récursive même s'ils résident dans un sous-dossier importé.
        from PySide6.QtWidgets import QFileDialog
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Sélectionner des vidéos", self.last_input_dir,
            "Vidéos (*.mkv *.mp4)",
        )
        if not paths:
            return
        self.remember_input_dir(str(Path(paths[0]).parent))
        self.manual_files.update(path_identity(p) for p in paths if Path(p).is_file())
        self.excluded_files.difference_update(path_identity(p) for p in paths)
        added = self.add_paths(paths)
        self.statusBar().showMessage(f"{added} vidéo(s) ajoutée(s) manuellement", 5000)
        self.refresh_destinations()

    def import_folder(self):
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(
            self, "Sélectionner un dossier de vidéos", self.last_input_dir,
        )
        if not folder:
            return
        self.remember_input_dir(folder)
        self.monitored_roots[path_identity(folder)] = folder
        # L'import volontaire réactive les fichiers précédemment retirés
        # appartenant à ce dossier.
        self.excluded_files = {
            key for key in self.excluded_files
            if not self._belongs_to_root(key, folder)
        }
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
            # Dossiers imbriqués : choisir comme racine celui qui est le plus
            # spécifique, pour que le chemin de sortie soit prévisible.
            roots = sorted(self.monitored_roots.values(), key=lambda p: len(Path(p).parts))
            for root in roots:
                try:
                    paths = discover_videos(
                        root,
                        recursive=self.recursive_check.isChecked(),
                        exclude_folder=self.output_dir or None,
                    )
                    for path in paths:
                        by_key[path_identity(path)] = (path, root)
                except OSError as exc:
                    errors.append(f"{root} : {exc}")

            # Les fichiers retirés volontairement ne sont pas réimportés à
            # chaque tick. Une disparition physique réarme leur import futur.
            currently_present = set(by_key)
            self.generated_targets.intersection_update(
                key for key in self.generated_targets if Path(key).exists()
            )
            by_key = {
                k: v for k, v in by_key.items() if k not in self.generated_targets
            }
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
                self.output_sizes = {
                    new_index: old_sizes[old_index]
                    for new_index, old_index in enumerate(
                        i for i in range(len(old_paths)) if i not in removed_set
                    )
                    if old_index in old_sizes
                }
                valid_keys = {path_identity(p) for p in self.video_paths}
                self.source_roots = {
                    k: v for k, v in self.source_roots.items() if k in valid_keys
                }

            # Réattribuer les racines des fichiers suivis, y compris ceux
            # déjà présents avant l'activation de la récursivité.
            for key, (_path, root) in by_key.items():
                if self.path_key(_path) in self.video_keys:
                    self.source_roots[key] = root

            added = 0
            for key, (path, root) in by_key.items():
                if self.path_key(path) not in self.video_keys:
                    added += super().add_paths([path], source_root=root)

            # Taille actualisée si la vidéo est remplacée sur disque à l'arrêt.
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
                    # Un ancien ratio n'est plus valide après remplacement.
                    self.output_sizes.pop(row, None)
                    self.table.item(row, 4).setText("—")
                    self.table.item(row, 5).setText("—")

            self.update_paths()
            self.update_actions()
            self.refresh_destinations()
            if errors:
                self.statusBar().showMessage("Actualisation incomplète : " + errors[0], 6000)
            elif added or removed_rows:
                self.statusBar().showMessage(
                    f"Dossiers synchronisés : +{added}, -{len(removed_rows)} vidéo(s)", 5000,
                )
        finally:
            self._syncing = False

    def refresh_destinations(self, *_args):
        if self.is_converting() or not hasattr(self, "table") or self.table.columnCount() < 12:
            return
        if not self.output_dir:
            targets = ()
        else:
            targets = tuple(plan_destinations(
                self.video_paths, self.source_roots, self.output_dir,
                self.container_combo.currentData(),
                preserve_tree=self.preserve_tree_check.isChecked(),
            ))
        if targets != self._destinations:
            # Des résultats de compression correspondant à un ancien chemin
            # ne doivent pas être présentés comme ceux de la nouvelle cible.
            if self.output_sizes:
                self.reset_output_stats()
            self._destinations = targets
        for row in range(self.table.rowCount()):
            target = str(targets[row]) if row < len(targets) else "—"
            item = self.table.item(row, 11)
            if item is None:
                item = QTableWidgetItem()
                self.table.setItem(row, 11, item)
            item.setText(target)
            item.setToolTip(target)

    def select_output_dir(self):
        previous = self.output_dir
        super().select_output_dir()
        if self.output_dir != previous:
            self.refresh_sources()
        self.refresh_destinations()

    def remove_selected(self):
        # La suppression manuelle exclut aussi le fichier de sa source suivie.
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
        # « Tout vider » vide aussi la liste des dossiers surveillés.
        self.monitored_roots.clear()
        self.manual_files.clear()
        self.excluded_files.clear()
        self.generated_targets.clear()
        super().clear_videos()
        self.refresh_destinations()

    def on_options_changed(self, _value=None):
        super().on_options_changed(_value)
        if hasattr(self, "table") and self.table.columnCount() == 12:
            self.refresh_destinations()

    def apply_conversion_settings(self, settings, select_preset=None):
        super().apply_conversion_settings(settings, select_preset=select_preset)
        if hasattr(self, "table") and self.table.columnCount() == 12:
            self.refresh_destinations()

    def start_conversion(self):
        self.refresh_sources()
        self.refresh_destinations()
        planned_targets = tuple(self._destinations)
        super().start_conversion()
        if self.is_converting():
            self.generated_targets.update(path_identity(p) for p in planned_targets)
            self.refresh_button.setEnabled(False)

    def on_worker_finished(self):
        super().on_worker_finished()
        self.refresh_button.setEnabled(True)
        # Le travail terminé peut avoir ajouté des fichiers dans le dossier
        # suivi ; la mise à jour se fait après la libération du worker.
        QTimer.singleShot(0, self.refresh_sources)
