"""Orchestrateur de conversions en parallèle, fondé sur le worker V0.8.1.

Chaque vidéo garde son propre processus FFmpeg, sa progression et son fichier
.part temporaire. Ce module ne change ni les codecs ni les sorties existantes.
"""

from PySide6.QtCore import QObject, Signal

from converter import ConversionWorker


class ParallelBatchController(QObject):
    state_changed = Signal(int, str)
    progress_changed = Signal(int, int)
    timing_started = Signal(int)
    timing_updated = Signal(int, float, float, float, float)
    timing_finished = Signal(int, float)
    output_measured = Signal(int, int, str)
    batch_finished = Signal(int, int, int, bool, list)
    finished = Signal()

    def __init__(self, sources, output_folder, ffmpeg_path, settings,
                 targets, max_parallel=2, parent=None):
        super().__init__(parent)
        if len(sources) != len(targets):
            raise ValueError("Les sources et destinations doivent correspondre.")
        if not 1 <= max_parallel <= 4:
            raise ValueError("Le parallélisme doit être entre 1 et 4.")
        self.sources = list(sources)
        self.targets = list(targets)
        self.output_folder = output_folder
        self.ffmpeg_path = ffmpeg_path
        self.settings = settings
        self.max_parallel = max_parallel
        self._active = {}  # index -> ConversionWorker (un fichier)
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
        while (not self._cancelled and len(self._active) < self.max_parallel
               and self._next_index < len(self.sources)):
            index = self._next_index
            self._next_index += 1
            worker = ConversionWorker(
                [self.sources[index]], self.output_folder, self.ffmpeg_path,
                settings=self.settings, targets=[self.targets[index]], parent=self,
            )
            self._active[index] = worker
            worker.state_changed.connect(
                lambda _i, state, row=index: self.state_changed.emit(row, state)
            )
            worker.progress_changed.connect(
                lambda _i, percent, row=index: self.progress_changed.emit(row, percent)
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
                lambda _i, size, status, row=index:
                self.output_measured.emit(row, size, status)
            )
            worker.batch_finished.connect(
                lambda done, skipped, failed, cancelled, errors, row=index:
                self._results.__setitem__(row, (done, skipped, failed, errors))
            )
            worker.finished.connect(
                lambda row=index: self._worker_finished(row)
            )
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
            self.state_changed.emit(index, "Annulé")
        # Copie explicite : la suppression d'un worker fini ne modifie pas
        # l'itération. Chaque processus FFmpeg actif reçoit terminate().
        for worker in list(self._active.values()):
            worker.request_cancel()
        if not self._active:
            self._finish()

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        done = sum(result[0] for result in self._results.values())
        skipped = sum(result[1] for result in self._results.values())
        failed = sum(result[2] for result in self._results.values())
        errors = [error for result in self._results.values() for error in result[3]]
        self.batch_finished.emit(done, skipped, failed, self._cancelled, errors)
        self.finished.emit()
