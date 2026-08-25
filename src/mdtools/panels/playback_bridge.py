"""Crossing from `AudioPlayer`'s realtime audio callback thread onto the
Qt/GUI thread -- the one genuinely new piece of Qt-threading code the
foobar2000-to-AudioPlayer migration needed.

`AudioPlayer.play()`'s `on_track_boundary`/`on_finished` callbacks
(audio_engine.py) run on PortAudio's own callback thread, never on the
GUI thread -- calling into a QDialog's own slots directly from there
(sending an MDRem key, touching a QTreeWidget) would be exactly the kind
of cross-thread Qt access that is undefined behaviour. A plain `QObject`
with `Signal`s does the safe crossing for free: Qt's default
`AutoConnection` becomes a queued connection the moment the emitting
thread differs from the connected slot's own thread, so `emit()` from the
callback thread is safe, and the slot always runs later, on the GUI
thread's own event loop -- no manual `QMetaObject.invokeMethod` needed.

This *must* be a real QObject constructed on the GUI thread (so its own
thread affinity is the GUI thread, which is what makes the auto-queueing
above kick in) -- a plain Python callable handed straight to
`AudioPlayer.play()` would run on the audio thread with no crossing at
all.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class PlaybackBridge(QObject):
    track_boundary = Signal(int)
    finished = Signal()
