"""PlaybackBridge -- the QObject that lets AudioPlayer's realtime callback
thread reach the GUI thread safely. Fires the signal from a real, separate
Python thread (standing in for PortAudio's own callback thread) and
proves the connected slot only ever runs on the main/GUI thread, after an
explicit pump of the event loop -- if this were a plain direct call
(no thread crossing at all), the slot would already have run before
`thread.join()` even returns.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread

from mdtools.panels.playback_bridge import PlaybackBridge


def test_track_boundary_is_delivered_on_the_main_thread(qt_app):
    bridge = PlaybackBridge()
    received = []
    threads_seen = []

    def on_boundary(index):
        received.append(index)
        threads_seen.append(QThread.currentThread())

    bridge.track_boundary.connect(on_boundary)

    def fire_from_worker_thread():
        bridge.track_boundary.emit(3)

    worker = threading.Thread(target=fire_from_worker_thread)
    worker.start()
    worker.join()

    # Not delivered yet -- a queued connection waits for the event loop.
    assert received == []

    qt_app.processEvents()

    assert received == [3]
    assert threads_seen == [QThread.currentThread()]


def test_finished_is_delivered_on_the_main_thread(qt_app):
    bridge = PlaybackBridge()
    received = []
    bridge.finished.connect(lambda: received.append(True))

    def fire_from_worker_thread():
        bridge.finished.emit()

    worker = threading.Thread(target=fire_from_worker_thread)
    worker.start()
    worker.join()
    assert received == []

    qt_app.processEvents()

    assert received == [True]
