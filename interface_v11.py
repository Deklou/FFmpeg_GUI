"""V1.1 — Extraction audio, en complément intact de la conversion vidéo V1.0.

Extension autonome : seuls main.py et ce fichier sont ajoutés/remplacés.
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
from interface import FFmpegGUI as VideoGUI
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
        self._audio_ready = False
        super().__init__()
        self.setWindowTitle("FFmpeg GUI — V1.1")
        self._add_processing_mode()
        self._add_audio_settings()
        self._audio_ready = True
        mode = self.settings.value("v11/processing_mode", "video")
        self.mode_combo.setCurrentIndex(1 if mode == "audio" else 0)
        self._change_mode()

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
            if self.output_sizes:
                self.reset_output_stats()
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
        self.batch_progress.setValue(0)
        self.batch_elapsed_label.setText("Temps écoulé du lot : 00:00:00")
        self.batch_eta_label.setText("Temps restant estimé du lot : —")
        self.batch_eta_seconds = None
        self.active_file_started_at = None
        self.active_file_index = None
        self.reset_output_stats()
        for row, target in enumerate(targets):
            self.table.item(row, 6).setText("En attente")
            self.table.cellWidget(row, 7).setValue(0)
            for column in (8, 9, 10):
                self.table.item(row, column).setText("—")
            self.table.item(row, 0).setToolTip(f"Destination prévue : {target}")
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
