"""Decoding a disc's (or a tape side's) worth of audio off the GUI thread.

**Why this exists.** Both recording dialogs decode everything they are
about to play *before* anything starts moving -- the MiniDisc deck is
armed and record-paused first, a cassette deck is already rolling onto
tape -- because decoding after the fact would put however long it takes
onto the disc as silence. That part is right and stays.

What was wrong is where it ran. `audio_engine.load_for_recording()` reads
every file, resamples it (soxr) and noise-shape-dithers it to 16-bit, and
all of that used to happen on the GUI thread, with a single
`processEvents()` between tracks as the only relief. Between those calls
the whole window is frozen: it cannot repaint, cannot be moved, and its
Stop button cannot be clicked -- for seconds per track, and a full album
is minutes of it. Reported directly as the UI blocking when a recording
starts.

So the work moves to a QThread, the same shape `_RipWorker` and
`_BurnWorker` already use, and the dialog carries on the moment it is
handed the finished buffers. Nothing else about the sequence changes: the
deck is still armed before decoding and released after it.

**Cancelling takes effect between tracks, not during one** -- the same
"between steps, not during one" rule every other worker here follows.
`load_*`'s own progress callback is called once per file, so raising out
of it is what ends the loop; a partially decoded file is simply
discarded, since nothing downstream has been handed anything yet.

No Qt-specific knowledge about either dialog lives here: the two of them
differ only in which loader they want (a MiniDisc's digital input needs
`load_for_recording()`'s dither, a cassette's analogue line-out does not
-- see audio_engine), which is one flag.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from mdtools import audio_engine


class _Cancelled(Exception):
    """Raised out of the progress callback to end the decode loop."""


class DecodeWorker(QThread):
    """Decodes `paths` and hands back one buffer per track.

    Exactly one of `decoded` / `failed` is emitted, and neither is emitted
    at all after `cancel()` -- a cancelled decode has nothing to say."""

    progress = Signal(int, int, str)  # index (1-based), total, the track's name
    decoded = Signal(object)  # list[np.ndarray], in the order given
    failed = Signal(str)

    def __init__(self, paths: list[Path], *, samplerate: int, dithered: bool, parent=None):
        super().__init__(parent)
        self._paths = list(paths)
        self._samplerate = samplerate
        self._dithered = dithered
        self._cancelled = False

    def cancel(self) -> None:
        """Takes effect at the next track boundary. The thread is still
        running when this returns -- wait for `finished` rather than
        blocking the GUI thread on wait()."""
        self._cancelled = True

    def run(self) -> None:
        load = audio_engine.load_for_recording if self._dithered else audio_engine.load_for_playback
        try:
            buffers = load(
                self._paths, samplerate=self._samplerate, on_progress=self._on_progress
            )
        except _Cancelled:
            return
        except audio_engine.AudioEngineError as exc:
            self.failed.emit(str(exc))
            return
        if self._cancelled:
            # Cancelled during the last file, after its own progress call.
            return
        self.decoded.emit(buffers)

    def _on_progress(self, index: int, total: int, path) -> None:
        if self._cancelled:
            raise _Cancelled
        self.progress.emit(index, total, Path(path).stem)
