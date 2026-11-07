"""Tests indépendants de PySide6 et FFmpeg : scheduler et annulation."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path


class SignalInstance:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class SignalDescriptor:
    def __init__(self, *args):
        self.name = None

    def __set_name__(self, cls, name):
        self.name = name

    def __get__(self, instance, cls):
        if instance is None:
            return self
        return instance.__dict__.setdefault(self.name, SignalInstance())


class FakeQObject:
    def __init__(self, parent=None):
        pass

    def deleteLater(self):
        pass


class FakeWorker:
    created = []
    active = 0
    maximum = 0

    def __init__(self, sources, output_folder, ffmpeg_path, settings=None,
                 targets=None, parent=None):
        self.sources = sources
        self.state_changed = SignalInstance()
        self.progress_changed = SignalInstance()
        self.timing_started = SignalInstance()
        self.timing_updated = SignalInstance()
        self.timing_finished = SignalInstance()
        self.output_measured = SignalInstance()
        self.batch_finished = SignalInstance()
        self.finished = SignalInstance()
        self.cancelled = False
        self.started = False
        FakeWorker.created.append(self)

    def start(self):
        self.started = True
        FakeWorker.active += 1
        FakeWorker.maximum = max(FakeWorker.maximum, FakeWorker.active)

    def request_cancel(self):
        self.cancelled = True

    def complete(self, success=True):
        if not self.started:
            raise AssertionError("Travailleur non démarré")
        if success:
            self.progress_changed.emit(0, 100)
        self.batch_finished.emit(int(success), 0, int(not success),
                                 self.cancelled, [] if success else ['erreur'])
        FakeWorker.active -= 1
        self.finished.emit()

    def deleteLater(self):
        pass


def load_controller():
    qt = types.ModuleType("PySide6.QtCore")
    qt.QObject = FakeQObject
    qt.Signal = SignalDescriptor
    pkg = types.ModuleType("PySide6")
    pkg.QtCore = qt
    converter = types.ModuleType("converter")
    converter.ConversionWorker = FakeWorker
    old = {key: sys.modules.get(key) for key in ("PySide6", "PySide6.QtCore", "converter")}
    sys.modules.update({"PySide6": pkg, "PySide6.QtCore": qt, "converter": converter})
    try:
        spec = importlib.util.spec_from_file_location(
            "parallel_converter_under_test", Path(__file__).with_name("parallel_converter.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ParallelBatchController
    finally:
        for key, value in old.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


Controller = load_controller()


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        FakeWorker.created.clear()
        FakeWorker.active = 0
        FakeWorker.maximum = 0

    def make(self, count, parallel):
        return Controller(
            [f"video_{i}.mp4" for i in range(count)], ".", "ffmpeg",
            settings=None, targets=[f"video_{i}.mkv" for i in range(count)],
            max_parallel=parallel,
        )

    def test_limits_workers_and_maps_progress(self):
        controller = self.make(5, 2)
        outputs = []
        statuses = []
        controller.progress_changed.connect(lambda row, pct: outputs.append((row, pct)))
        controller.batch_finished.connect(lambda *args: statuses.append(args))
        controller.start()
        self.assertEqual(len(FakeWorker.created), 2)
        FakeWorker.created[1].complete()
        self.assertEqual(len(FakeWorker.created), 3)
        self.assertIn((1, 100), outputs)
        FakeWorker.created[0].complete()
        FakeWorker.created[2].complete()
        FakeWorker.created[3].complete()
        FakeWorker.created[4].complete()
        self.assertEqual(FakeWorker.maximum, 2)
        self.assertEqual(statuses, [(5, 0, 0, False, [])])

    def test_cancel_stops_pending_launches(self):
        controller = self.make(4, 2)
        statuses = []
        controller.batch_finished.connect(lambda *args: statuses.append(args))
        controller.start()
        controller.request_cancel()
        self.assertTrue(all(w.cancelled for w in FakeWorker.created))
        FakeWorker.created[0].complete(False)
        FakeWorker.created[1].complete(False)
        self.assertEqual(len(FakeWorker.created), 2)
        self.assertTrue(statuses[0][3])

    def test_one_file_and_zero_file_batches(self):
        controller = self.make(1, 4)
        statuses = []
        controller.batch_finished.connect(lambda *args: statuses.append(args))
        controller.start()
        FakeWorker.created[0].complete()
        self.assertEqual(statuses, [(1, 0, 0, False, [])])
        self.assertEqual(FakeWorker.maximum, 1)


if __name__ == "__main__":
    unittest.main()
