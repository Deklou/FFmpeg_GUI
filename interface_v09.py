"""V0.9 : limite configurable de conversions simultanées.

L'interface V0.8.1 est réutilisée sans réécrire sa gestion des dossiers,
des presets, des statistiques ou des chemins de destination.
"""

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox, QSpinBox

from converter import ConversionWorker
from conversion_time import format_duration
from output_planning import plan_destinations, path_identity
from parallel_converter import ParallelBatchController
from interface_v08 import FFmpegGUI as PreviousFFmpegGUI


class FFmpegGUI(PreviousFFmpegGUI):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFmpeg GUI — V0.9")
        self._add_parallel_control()

    def _add_parallel_control(self):
        # Le bouton garde son layout d'origine, même dans la QScrollArea V0.8.1.
        content = self.centralWidget().widget()
        layout = content.layout()
        conversion_row = None
        for index in range(layout.count()):
            nested = layout.itemAt(index).layout()
            if nested and any(
                nested.itemAt(i).widget() is self.start_button
                for i in range(nested.count())
            ):
                conversion_row = nested
                break
        if conversion_row is None:
            raise RuntimeError("Impossible de localiser les boutons de conversion.")

        self.parallel_label = QLabel("Conversions simultanées :")
        self.parallel_spin = QSpinBox()
        self.parallel_spin.setRange(1, 4)
        self.parallel_spin.setValue(1)  # sécurité et ressources CPU par défaut
        self.parallel_spin.setToolTip(
            "Nombre de vidéos encodées en même temps (1 à 4). "
            "Plus n'est pas toujours plus rapide avec H.265."
        )
        try:
            saved = int(self.settings.value("max_parallel", 1))
        except (TypeError, ValueError):
            saved = 1
        self.parallel_spin.setValue(max(1, min(4, saved)))
        self.parallel_spin.valueChanged.connect(
            lambda value: self.settings.setValue("max_parallel", value)
        )
        conversion_row.insertWidget(2, self.parallel_label)
        conversion_row.insertWidget(3, self.parallel_spin)
        self.update_actions()

    def update_actions(self):
        super().update_actions()
        if hasattr(self, "parallel_spin"):
            self.parallel_spin.setEnabled(not self.is_converting())

    def start_conversion(self):
        if self.is_converting() or not self.video_paths:
            return
        # Forcer une dernière synchronisation avant de figer sources/cibles.
        self.refresh_sources()
        self.refresh_destinations()
        self.remember_ffmpeg()
        if not Path(self.ffmpeg_path).is_file():
            QMessageBox.warning(self, "FFmpeg", "Sélectionne un fichier ffmpeg.exe valide.")
            return
        if not self.output_dir:
            QMessageBox.warning(self, "Dossier de sortie", "Choisis un dossier de sortie.")
            return
        settings = self.current_conversion_settings()
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Paramètres incompatibles", str(exc))
            return
        targets = plan_destinations(
            self.video_paths, self.source_roots, self.output_dir, settings.container,
            preserve_tree=self.preserve_tree_check.isChecked(),
        )
        identities = {path_identity(source) for source in self.video_paths}
        if any(path_identity(target) in identities for target in targets):
            QMessageBox.warning(
                self, "Dossier de sortie",
                "Une destination correspond à une vidéo source du lot. "
                "Choisis un autre dossier de sortie.",
            )
            return

        self.batch_progress.setValue(0)
        self.batch_elapsed_label.setText("Temps écoulé du lot : 00:00:00")
        self.batch_eta_label.setText("Temps restant estimé du lot : —")
        self.batch_eta_seconds = None
        self.active_file_started_at = None
        self.active_file_index = None
        self.reset_output_stats()
        for row in range(self.table.rowCount()):
            self.table.item(row, 6).setText("En attente")
            self.table.cellWidget(row, 7).setValue(0)
            for column in (8, 9, 10):
                self.table.item(row, column).setText("—")
            self.table.item(row, 0).setToolTip(
                f"Destination prévue : {targets[row]}"
            )

        parallel = self.parallel_spin.value()
        if parallel == 1:
            # Ancien worker strictement inchangé : conserve l'ETA du lot.
            self.worker = ConversionWorker(
                self.video_paths, self.output_dir, self.ffmpeg_path,
                settings=settings, parent=self, targets=targets,
            )
        else:
            self.worker = ParallelBatchController(
                self.video_paths, self.output_dir, self.ffmpeg_path, settings,
                targets, max_parallel=parallel, parent=self,
            )

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
        self.generated_targets.update(path_identity(p) for p in targets)
        self.refresh_button.setEnabled(False)
        self.batch_started_at = time.monotonic()
        self.elapsed_timer.start()
        self.update_actions()
        self.worker.start()
        self.statusBar().showMessage(
            f"Conversions en cours — {parallel} simultanée(s) au maximum"
        )

    def on_timing_started(self, index):
        if self.parallel_spin.value() == 1:
            return super().on_timing_started(index)
        # Plusieurs fichiers sont actifs : l'horloge de chaque ligne est
        # alimentée par timing_updated, pas par un index actif unique.
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 8).setText("00:00:00")
            self.table.item(index, 9).setText("—")
            self.table.item(index, 10).setText("—")

    def on_timing_updated(self, index, elapsed, remaining, speed, batch_remaining):
        if self.parallel_spin.value() == 1:
            return super().on_timing_updated(index, elapsed, remaining, speed, batch_remaining)
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 8).setText(format_duration(elapsed))
            self.table.item(index, 9).setText(format_duration(remaining))
            self.table.item(index, 10).setText(f"{speed:.2f}x" if speed > 0 else "—")
        # On ne somme PAS les ETA des vidéos parallèles : cela donnerait
        # une estimation erronée. Une ETA de lot parallèle nécessite un
        # modèle dédié de durée des futures tâches.
        self.batch_eta_label.setText("Temps restant estimé du lot : — (parallèle)")

    def on_timing_finished(self, index, elapsed):
        if self.parallel_spin.value() == 1:
            return super().on_timing_finished(index, elapsed)
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 8).setText(format_duration(elapsed))
            self.table.item(index, 9).setText("—")

    def on_worker_finished(self):
        # La V0.7 réactive déjà la synchronisation et le bouton Actualiser.
        self.elapsed_timer.stop()
        if self.batch_started_at is not None:
            self.batch_elapsed_label.setText(
                f"Temps écoulé du lot : {format_duration(time.monotonic() - self.batch_started_at)}"
            )
        super().on_worker_finished()
