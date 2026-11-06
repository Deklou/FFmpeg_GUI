"""Conversion FFmpeg séquentielle, avec progression, annulation et sortie temporaire."""

import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from conversion_settings import ConversionSettings, build_command
from conversion_time import parse_speed, parse_out_time, estimate_remaining


DEFAULT_FFMPEG = r"C:\Outils\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe"


def locate_ffmpeg():
    """Retrouve FFmpeg via son emplacement historique ou le PATH Windows."""
    if Path(DEFAULT_FFMPEG).is_file():
        return DEFAULT_FFMPEG
    return shutil.which("ffmpeg") or ""


def probe_duration(ffmpeg_path, source):
    """Durée en secondes ; None lorsque ffprobe n'est pas accessible."""
    ffmpeg = Path(ffmpeg_path)
    probe = ffmpeg.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    candidate = str(probe) if probe.is_file() else (shutil.which("ffprobe") or "")
    if not candidate:
        return None
    try:
        result = subprocess.run(
            [candidate, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
            capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        duration = float(result.stdout.strip()) if result.returncode == 0 else 0
        return duration if duration > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


class ConversionWorker(QThread):
    state_changed = Signal(int, str)
    progress_changed = Signal(int, int)  # index, percent
    timing_started = Signal(int)
    timing_updated = Signal(int, float, float, float, float)  # index, elapsed, ETA fichier, vitesse, ETA lot
    timing_finished = Signal(int, float)
    output_measured = Signal(int, int, str)  # index, taille réelle en octets, statut
    batch_finished = Signal(int, int, int, bool, list)  # ok, ignored, errors, cancelled, details

    def __init__(self, sources, output_folder, ffmpeg_path, settings=None, parent=None):
        super().__init__(parent)
        self.sources = list(sources)
        self.output_folder = Path(output_folder)
        self.ffmpeg_path = str(ffmpeg_path)
        self.settings = settings if settings is not None else ConversionSettings()
        self.settings.validate()
        self.cancel_event = threading.Event()
        self._process = None
        self._process_lock = threading.Lock()

    def request_cancel(self):
        self.cancel_event.set()
        with self._process_lock:
            process = self._process
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def run(self):
        done, skipped, failed = 0, 0, 0
        errors = []
        try:
            self.output_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.batch_finished.emit(0, 0, len(self.sources), False, [str(exc)])
            return

        # Analyse des durées une seule fois, pour une estimation de lot lorsque
        # ffprobe est disponible pour tous les fichiers restant à convertir.
        durations = {}
        for index, filename in enumerate(self.sources):
            if self.cancel_event.is_set():
                break
            source = Path(filename)
            target = self.output_folder / f"{source.stem}.{self.settings.container}"
            if target.exists() or not source.is_file():
                durations[index] = 0.0
            else:
                durations[index] = probe_duration(self.ffmpeg_path, source)

        for index, filename in enumerate(self.sources):
            if self.cancel_event.is_set():
                break
            source = Path(filename)
            target = self.output_folder / f"{source.stem}.{self.settings.container}"
            if target.exists():
                skipped += 1
                try:
                    self.output_measured.emit(index, target.stat().st_size, "Déjà converti")
                except OSError:
                    pass
                self.state_changed.emit(index, "Déjà converti")
                self.progress_changed.emit(index, 100)
                continue

            if not source.is_file():
                failed += 1
                self.state_changed.emit(index, "Source introuvable")
                errors.append(f"{source.name} : source introuvable")
                continue

            self.state_changed.emit(index, "Conversion en cours")
            self.progress_changed.emit(index, 0)
            duration = durations.get(index)
            # Le fichier temporaire conserve l’extension du conteneur pour FFmpeg.
            temporary = self.output_folder / f".{source.stem}.{uuid.uuid4().hex}.part.{self.settings.container}"
            command = build_command(self.ffmpeg_path, source, temporary, self.settings)
            recent_errors = []
            process = None
            stderr_reader = None
            started_at = None
            try:
                process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1, errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                with self._process_lock:
                    self._process = process
                started_at = time.monotonic()
                self.timing_started.emit(index)

                def read_errors():
                    for line in process.stderr:
                        recent_errors.append(line.rstrip())
                        if len(recent_errors) > 25:
                            del recent_errors[0]

                stderr_reader = threading.Thread(target=read_errors, daemon=True)
                stderr_reader.start()

                progress_block = {}
                for raw_line in process.stdout:
                    if self.cancel_event.is_set():
                        break
                    key, separator, value = raw_line.strip().partition("=")
                    if not separator:
                        continue
                    progress_block[key] = value
                    if key != "progress":
                        continue

                    encoded_seconds = parse_out_time(progress_block)
                    speed = parse_speed(progress_block.get("speed"))
                    elapsed = time.monotonic() - started_at
                    remaining = estimate_remaining(duration, encoded_seconds, speed)
                    pending = [durations.get(i) for i in range(index + 1, len(self.sources))]
                    if remaining is not None and all(p is not None for p in pending):
                        batch_remaining = remaining + sum(pending) / speed
                    else:
                        batch_remaining = None

                    if duration and encoded_seconds is not None:
                        percent = min(99, max(0, int(encoded_seconds / duration * 100)))
                        self.progress_changed.emit(index, percent)
                    self.timing_updated.emit(
                        index, elapsed,
                        remaining if remaining is not None else -1.0,
                        speed if speed is not None else -1.0,
                        batch_remaining if batch_remaining is not None else -1.0,
                    )
                    progress_block.clear()

                if self.cancel_event.is_set() and process.poll() is None:
                    process.terminate()
                exit_code = process.wait()
                if stderr_reader:
                    stderr_reader.join(timeout=2)

                if self.cancel_event.is_set():
                    self.state_changed.emit(index, "Annulé")
                    break

                if exit_code != 0:
                    failed += 1
                    self.state_changed.emit(index, "Erreur")
                    errors.append(f"{source.name} : {' | '.join(recent_errors[-4:]) or 'FFmpeg a échoué'}")
                elif target.exists():
                    # Un fichier créé entre-temps ne doit jamais être écrasé.
                    skipped += 1
                    try:
                        self.output_measured.emit(index, target.stat().st_size, "Déjà converti")
                    except OSError:
                        pass
                    self.state_changed.emit(index, "Déjà converti")
                    self.progress_changed.emit(index, 100)
                else:
                    os.replace(temporary, target)
                    done += 1
                    try:
                        self.output_measured.emit(index, target.stat().st_size, "Terminé")
                    except OSError:
                        pass
                    self.state_changed.emit(index, "Terminé")
                    self.progress_changed.emit(index, 100)
            except (OSError, ValueError) as exc:
                failed += 1
                self.state_changed.emit(index, "Erreur")
                errors.append(f"{source.name} : {exc}")
            finally:
                if started_at is not None:
                    self.timing_finished.emit(index, time.monotonic() - started_at)
                durations[index] = 0.0
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
