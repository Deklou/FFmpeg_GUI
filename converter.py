"""Moteur de conversion FFmpeg, séquentiel ou parallèle, non bloquant."""
import os
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from PySide6.QtCore import QThread, Signal, QObject
from config import ConversionSettings, build_command
from metrics import parse_speed, parse_out_time, estimate_remaining

def locate_ffmpeg():
    """Détecte FFmpeg fourni à côté de l'application ou installé via PATH.

    Ne privilégie aucun emplacement personnel ni aucun dossier utilisateur.
    """
    import sys
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    candidates = (root / 'ffmpeg.exe', root / 'ffmpeg', root / 'bin' / 'ffmpeg.exe', root / 'bin' / 'ffmpeg')
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which('ffmpeg') or ''


def probe_duration(ffmpeg_path, source):
    """Durée en secondes ; None lorsque ffprobe n'est pas accessible."""
    ffmpeg = Path(ffmpeg_path)
    probe = ffmpeg.with_name('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
    candidate = str(probe) if probe.is_file() else shutil.which('ffprobe') or ''
    if not candidate:
        return None
    try:
        result = subprocess.run([candidate, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(source)], capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        duration = float(result.stdout.strip()) if result.returncode == 0 else 0
        return duration if duration > 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None

class ConversionWorker(QThread):
    state_changed = Signal(int, str)
    progress_changed = Signal(int, int)
    timing_started = Signal(int)
    timing_updated = Signal(int, float, float, float, float)
    timing_finished = Signal(int, float)
    output_measured = Signal(int, int, str)
    batch_finished = Signal(int, int, int, bool, list)

    def __init__(self, sources, output_folder, ffmpeg_path, settings=None, parent=None, targets=None):
        super().__init__(parent)
        self.sources = list(sources)
        self.targets = [Path(p) for p in targets] if targets is not None else [Path(output_folder) / (Path(p).stem + '.' + (settings.container if settings else 'mkv')) for p in sources]
        if len(self.targets) != len(self.sources):
            raise ValueError('Le nombre de destinations ne correspond pas aux sources.')
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
        done, skipped, failed = (0, 0, 0)
        errors = []
        try:
            self.output_folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.batch_finished.emit(0, 0, len(self.sources), False, [str(exc)])
            return
        durations = {}
        for index, filename in enumerate(self.sources):
            if self.cancel_event.is_set():
                break
            source = Path(filename)
            target = self.targets[index]
            if target.exists() or not source.is_file():
                durations[index] = 0.0
            else:
                durations[index] = probe_duration(self.ffmpeg_path, source)
        for index, filename in enumerate(self.sources):
            if self.cancel_event.is_set():
                break
            source = Path(filename)
            target = self.targets[index]
            if target.exists():
                skipped += 1
                try:
                    self.output_measured.emit(index, target.stat().st_size, 'Déjà converti')
                except OSError:
                    pass
                self.state_changed.emit(index, 'Déjà converti')
                self.progress_changed.emit(index, 100)
                continue
            if not source.is_file():
                failed += 1
                self.state_changed.emit(index, 'Source introuvable')
                errors.append(f'{source.name} : source introuvable')
                continue
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                failed += 1
                self.state_changed.emit(index, 'Erreur')
                errors.append(f'{source.name} : création du dossier impossible ({exc})')
                continue
            self.state_changed.emit(index, 'Conversion en cours')
            self.progress_changed.emit(index, 0)
            duration = durations.get(index)
            temporary = target.parent / f'.{target.stem}.{uuid.uuid4().hex}.part.{self.settings.container}'
            command = build_command(self.ffmpeg_path, source, temporary, self.settings)
            recent_errors = []
            process = None
            stderr_reader = None
            started_at = None
            try:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
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
                    key, separator, value = raw_line.strip().partition('=')
                    if not separator:
                        continue
                    progress_block[key] = value
                    if key != 'progress':
                        continue
                    encoded_seconds = parse_out_time(progress_block)
                    speed = parse_speed(progress_block.get('speed'))
                    elapsed = time.monotonic() - started_at
                    remaining = estimate_remaining(duration, encoded_seconds, speed)
                    pending = [durations.get(i) for i in range(index + 1, len(self.sources))]
                    if remaining is not None and all((p is not None for p in pending)):
                        batch_remaining = remaining + sum(pending) / speed
                    else:
                        batch_remaining = None
                    if duration and encoded_seconds is not None:
                        percent = min(99, max(0, int(encoded_seconds / duration * 100)))
                        self.progress_changed.emit(index, percent)
                    self.timing_updated.emit(index, elapsed, remaining if remaining is not None else -1.0, speed if speed is not None else -1.0, batch_remaining if batch_remaining is not None else -1.0)
                    progress_block.clear()
                if self.cancel_event.is_set() and process.poll() is None:
                    process.terminate()
                exit_code = process.wait()
                if stderr_reader:
                    stderr_reader.join(timeout=2)
                if self.cancel_event.is_set():
                    self.state_changed.emit(index, 'Annulé')
                    break
                if exit_code != 0:
                    failed += 1
                    self.state_changed.emit(index, 'Erreur')
                    errors.append(f"{source.name} : {' | '.join(recent_errors[-4:]) or 'FFmpeg a échoué'}")
                elif target.exists():
                    skipped += 1
                    try:
                        self.output_measured.emit(index, target.stat().st_size, 'Déjà converti')
                    except OSError:
                        pass
                    self.state_changed.emit(index, 'Déjà converti')
                    self.progress_changed.emit(index, 100)
                else:
                    os.replace(temporary, target)
                    done += 1
                    try:
                        self.output_measured.emit(index, target.stat().st_size, 'Terminé')
                    except OSError:
                        pass
                    self.state_changed.emit(index, 'Terminé')
                    self.progress_changed.emit(index, 100)
            except (OSError, ValueError) as exc:
                failed += 1
                self.state_changed.emit(index, 'Erreur')
                errors.append(f'{source.name} : {exc}')
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

class ParallelBatchController(QObject):
    state_changed = Signal(int, str)
    progress_changed = Signal(int, int)
    timing_started = Signal(int)
    timing_updated = Signal(int, float, float, float, float)
    timing_finished = Signal(int, float)
    output_measured = Signal(int, int, str)
    batch_finished = Signal(int, int, int, bool, list)
    finished = Signal()

    def __init__(self, sources, output_folder, ffmpeg_path, settings, targets, max_parallel=2, parent=None):
        super().__init__(parent)
        if len(sources) != len(targets):
            raise ValueError('Les sources et destinations doivent correspondre.')
        if not 1 <= max_parallel <= 4:
            raise ValueError('Le parallélisme doit être entre 1 et 4.')
        self.sources = list(sources)
        self.targets = list(targets)
        self.output_folder = output_folder
        self.ffmpeg_path = ffmpeg_path
        self.settings = settings
        self.max_parallel = max_parallel
        self._active = {}
        self._next_index = 0
        self._results = {}
        self._cancelled = False
        self._started = False
        self._finished = False

    def start(self):
        if self._started:
            return
        self._started = True
        self._fill_slots()

    def _fill_slots(self):
        if self._finished:
            return
        while not self._cancelled and len(self._active) < self.max_parallel and (self._next_index < len(self.sources)):
            index = self._next_index
            self._next_index += 1
            worker = ConversionWorker([self.sources[index]], self.output_folder, self.ffmpeg_path, settings=self.settings, targets=[self.targets[index]], parent=self)
            self._active[index] = worker
            worker.state_changed.connect(lambda _i, state, row=index: self.state_changed.emit(row, state))
            worker.progress_changed.connect(lambda _i, percent, row=index: self.progress_changed.emit(row, percent))
            worker.timing_started.connect(lambda _i, row=index: self.timing_started.emit(row))
            worker.timing_updated.connect(lambda _i, elapsed, remaining, speed, _batch, row=index: self.timing_updated.emit(row, elapsed, remaining, speed, -1.0))
            worker.timing_finished.connect(lambda _i, elapsed, row=index: self.timing_finished.emit(row, elapsed))
            worker.output_measured.connect(lambda _i, size, status, row=index: self.output_measured.emit(row, size, status))
            worker.batch_finished.connect(lambda done, skipped, failed, cancelled, errors, row=index: self._results.__setitem__(row, (done, skipped, failed, errors)))
            worker.finished.connect(lambda row=index: self._worker_finished(row))
            worker.finished.connect(worker.deleteLater)
            worker.start()
        if not self._active and (self._cancelled or self._next_index >= len(self.sources)):
            self._finish()

    def _worker_finished(self, index):
        self._active.pop(index, None)
        self._fill_slots()

    def request_cancel(self):
        if self._finished:
            return
        self._cancelled = True
        for index in range(self._next_index, len(self.sources)):
            self.state_changed.emit(index, 'Annulé')
        for worker in list(self._active.values()):
            worker.request_cancel()
        if not self._active:
            self._finish()

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        done = sum((result[0] for result in self._results.values()))
        skipped = sum((result[1] for result in self._results.values()))
        failed = sum((result[2] for result in self._results.values()))
        errors = [error for result in self._results.values() for error in result[3]]
        self.batch_finished.emit(done, skipped, failed, self._cancelled, errors)
        self.finished.emit()
