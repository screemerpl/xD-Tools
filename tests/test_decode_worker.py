"""DecodeWorker: the real thread, against real files.

The two recording dialogs stand this in for (see their own tests), so
this is the one place the actual QThread runs -- including its cancel
path, which is what a Stop pressed mid-decode depends on.

Every test here waits for the worker to finish before returning. A
QThread whose C++ object is collected while it still reports isRunning()
aborts the whole process with no Python traceback.
"""

from __future__ import annotations

import time

import numpy as np
import pytest
import soundfile as sf
from PySide6.QtWidgets import QApplication

from mdtools.panels.decode_worker import DecodeWorker


def _wav(path, seconds: float = 0.2, rate: int = 48000) -> str:
    """48 kHz on purpose: it forces the resample every real source needs."""
    samples = np.zeros((int(rate * seconds), 2), dtype=np.float32)
    sf.write(path, samples, rate, subtype="PCM_24")
    return str(path)


def _pump_until(condition, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.005)


def _finish(worker: DecodeWorker) -> None:
    worker.cancel()
    _pump_until(lambda: not worker.isRunning())
    worker.wait(5000)


@pytest.fixture
def paths(tmp_path):
    return [_wav(tmp_path / f"{i:02d}.wav") for i in range(1, 4)]


def test_it_decodes_every_path_in_order(qt_app, paths):
    worker = DecodeWorker(paths, samplerate=44100, dithered=True)
    got: list = []
    worker.decoded.connect(got.append)
    worker.start()
    try:
        _pump_until(lambda: bool(got))
    finally:
        _finish(worker)

    assert len(got) == 1
    buffers = got[0]
    assert len(buffers) == len(paths)
    # Resampled to the rate asked for, not left at the file's own 48 kHz.
    assert all(len(buffer) == pytest.approx(0.2 * 44100, rel=0.02) for buffer in buffers)


def test_it_reports_one_progress_step_per_track(qt_app, paths):
    worker = DecodeWorker(paths, samplerate=44100, dithered=False)
    steps: list = []
    done: list = []
    worker.progress.connect(lambda index, total, name: steps.append((index, total, name)))
    worker.decoded.connect(done.append)
    worker.start()
    try:
        _pump_until(lambda: bool(done))
    finally:
        _finish(worker)

    assert steps == [(1, 3, "01"), (2, 3, "02"), (3, 3, "03")]


def test_a_bad_file_is_reported_rather_than_raised(qt_app, tmp_path):
    not_audio = tmp_path / "sleeve.jpg"
    not_audio.write_bytes(b"not audio at all")
    worker = DecodeWorker([not_audio], samplerate=44100, dithered=True)
    failures: list = []
    worker.failed.connect(failures.append)
    worker.start()
    try:
        _pump_until(lambda: bool(failures))
    finally:
        _finish(worker)

    assert failures, "a file that cannot be decoded has to come back as a message"


def test_cancelling_stops_the_loop_and_says_nothing(qt_app, paths):
    """Stop lands between tracks -- and a cancelled decode emits neither
    decoded nor failed, because the caller already knows why it ended."""
    worker = DecodeWorker(paths, samplerate=44100, dithered=True)
    said: list = []
    worker.decoded.connect(lambda buffers: said.append("decoded"))
    worker.failed.connect(lambda error: said.append("failed"))
    # Cancelled before it ever starts, so the very first progress call ends
    # it -- the same path a Stop a moment later takes.
    worker.cancel()
    worker.start()
    _pump_until(lambda: not worker.isRunning())
    worker.wait(5000)

    assert said == []


def test_the_dithered_and_plain_loaders_both_come_back_playable(qt_app, paths):
    """A MiniDisc's digital input needs Red Book PCM; a cassette's line-out
    does not. Both have to return float32 in [-1, 1], which is what
    AudioPlayer.play() takes."""
    for dithered in (True, False):
        worker = DecodeWorker(paths, samplerate=44100, dithered=dithered)
        got: list = []
        worker.decoded.connect(got.append)
        worker.start()
        try:
            _pump_until(lambda: bool(got))
        finally:
            _finish(worker)

        assert got, dithered
        for buffer in got[0]:
            assert buffer.dtype == np.float32
            assert np.all(np.abs(buffer) <= 1.0)
