"""Auditioning a single track before committing to a real recording/burn --
backlog item #18: nothing in xD-Tools let the user listen to what is
about to go onto a MiniDisc, a cassette or a CD-R before spending
40+ minutes finding out it was the wrong take or a bad rip.

Wired into the three dialogs that already show an editable track list
before the real thing starts -- RecordDialog (MiniDisc), TapeRecordDialog
(cassette) and BurnDialog (CD-R) -- rather than duplicated three times.
Every recording *source* (a project's own files, a CD rip, a folder) ends
up in one of RecordDialog/TapeRecordDialog regardless of where it came
from, so wiring this bar into just those two (plus BurnDialog for a
MEDIUM_CD project, which uses neither) covers every path with no
source-specific code.

Always plays through the OS default output device (`device=None`) at
0 dB gain -- the "preview sink" `audio_engine.AudioPlayer`'s own
docstring already anticipated, deliberately independent of whatever
output device the user configured for actual MD/cassette recording (that
one is very possibly a digital feed into a deck, not something a human
can listen to). Decoded via `audio_engine.load_for_preview()`, which does
not resample -- this is "listen to the source file as it is", not
"prepare it for a specific recording sink".

One track at a time, by design (confirmed with the user): pressing Play
plays only the selected row, not the rest of the album/side in sequence.
The bar itself does not own the track list -- Prev/Next only ever emit a
signal, and the *owning dialog* moves its own tree/table selection by one
row, which flows back into `set_current()` the same way a manual click
would. That keeps the list of tracks in exactly one place.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSlider, QWidget

from mdtools import audio_engine
from mdtools.panels.playback_bridge import PlaybackBridge
from mdtools.panels.progress_format import mmss as _mmss

POLL_MS = 200
SLIDER_RANGE = 1000


class PreviewPlayerBar(QWidget):
    """A tiny transport control: Prev / Play-Pause / Next, a seek slider,
    elapsed/total labels. Plain text buttons, not new bundled icons -- the
    same two dialogs this is wired into already use plain-text buttons
    (Move Up/Move Down/Start Disc Here) for their own controls."""

    next_requested = Signal()
    prev_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path: Path | None = None
        self._player: audio_engine.AudioPlayer | None = None
        self._playing = False
        self._duration = 0.0
        # Whether the owning dialog is actually recording/burning right
        # now -- see set_locked(). Kept alongside _has_prev/_has_next
        # because every one of the transport buttons' enabled states is
        # a function of both "is there a track here" and "are we allowed
        # to touch the audio device at all".
        self._locked = False
        self._has_prev = False
        self._has_next = False
        self._bridge = PlaybackBridge(self)
        self._bridge.finished.connect(self._on_finished)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.prev_btn = QPushButton(self.tr("|< Prev"))
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self.prev_requested.emit)
        layout.addWidget(self.prev_btn)

        self.play_btn = QPushButton(self.tr("Play"))
        self.play_btn.clicked.connect(self._on_play_pause_clicked)
        layout.addWidget(self.play_btn)

        self.next_btn = QPushButton(self.tr("Next >|"))
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self.next_requested.emit)
        layout.addWidget(self.next_btn)

        self.elapsed_label = QLabel(_mmss(0))
        layout.addWidget(self.elapsed_label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, SLIDER_RANGE)
        self.slider.sliderReleased.connect(self._on_slider_released)
        layout.addWidget(self.slider, 1)

        self.total_label = QLabel("--:--")
        layout.addWidget(self.total_label)

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._refresh_position)

        self._refresh_enabled()

    # --- selection, driven by the owning dialog ------------------------

    def set_current(self, path: Path | None, *, has_prev: bool = False, has_next: bool = False) -> None:
        """Called by the owning dialog's own selection handler (a tree's
        currentItemChanged, a table's currentCellChanged, ...) -- never by
        this widget itself. Restarting playback on an unrelated re-fire of
        that same signal (e.g. a reorder that leaves the selection where
        it was) is avoided by no-op'ing when `path` has not actually
        changed."""
        self._has_prev = has_prev
        self._has_next = has_next
        self._refresh_enabled()
        if path == self._path:
            return
        # Skip-while-playing: Prev/Next during playback should not force
        # the user back to Play, matching how an ordinary media player's
        # own skip buttons behave.
        was_playing = self._playing
        self.stop()
        self._path = path
        self._refresh_enabled()
        if path is not None and was_playing and not self._locked:
            self._begin_playback()

    def set_locked(self, locked: bool) -> None:
        """Recording/burning is under way (or has stopped), so the whole
        transport is out of bounds (or back in).

        Connected straight to the owning dialog's own `running_changed`
        -- the one thing in each of those dialogs that already means
        "real work is in progress" -- rather than called by hand at each
        place a run starts and ends, of which there are several per
        dialog and more of them over time.

        Locking is not just tidiness. This bar deliberately plays through
        the OS *default* output device (see the module docstring), which
        may well be the very device the recording is feeding a deck
        through; under WDM-KS, the host API this app prefers, a second
        stream onto a device already open is at best a fight over it. And
        on a MiniDisc the deck is recording whatever arrives down that
        feed, so anything else played while it runs risks landing on the
        disc. The bar was already stopped when a run began, but nothing
        stopped the user pressing Play again a second later."""
        self._locked = locked
        if locked:
            self.stop()
        self._refresh_enabled()

    def _refresh_enabled(self) -> None:
        usable = not self._locked and self._path is not None
        self.play_btn.setEnabled(usable)
        self.slider.setEnabled(usable)
        self.prev_btn.setEnabled(self._has_prev and not self._locked)
        self.next_btn.setEnabled(self._has_next and not self._locked)
        tip = (
            self.tr("Not while recording is in progress.")
            if self._locked
            else ""
        )
        for widget in (self.play_btn, self.slider, self.prev_btn, self.next_btn):
            widget.setToolTip(tip)

    # --- playback --------------------------------------------------------

    def _on_play_pause_clicked(self) -> None:
        # Belt and braces over the disabled button: a keyboard shortcut,
        # a click() from a test, or a stray signal must not open an audio
        # stream while a recording owns the device.
        if self._locked:
            return
        if self._player is None:
            self._begin_playback()
        elif self._playing:
            self._pause()
        else:
            self._resume()

    def _begin_playback(self) -> None:
        if self._path is None or self._locked:
            return
        try:
            samples, rate = audio_engine.load_for_preview(self._path)
        except audio_engine.AudioEngineError as exc:
            self.total_label.setText(self.tr("Error"))
            self.total_label.setToolTip(str(exc))
            return
        self._duration = len(samples) / rate
        self.total_label.setText(_mmss(self._duration))
        self.total_label.setToolTip("")
        self.slider.setValue(0)
        self.elapsed_label.setText(_mmss(0))
        self._player = audio_engine.AudioPlayer(device=None, gain_db=0.0, samplerate=rate)
        self._player.play([samples], on_finished=self._bridge.finished.emit)
        self._set_playing(True)

    def _pause(self) -> None:
        if self._player is not None:
            self._player.pause()
        self._set_playing(False)

    def _resume(self) -> None:
        if self._player is not None:
            self._player.resume()
        self._set_playing(True)

    def _set_playing(self, playing: bool) -> None:
        self._playing = playing
        self.play_btn.setText(self.tr("Pause") if playing else self.tr("Play"))
        if playing:
            self._timer.start()
        else:
            self._timer.stop()

    def _on_finished(self) -> None:
        """The track played out on its own -- back to a clean, ready
        state (not paused mid-track). Pressing Play again re-decodes from
        scratch, simpler than seeking back to 0 on a stream that PortAudio
        has already torn down its own side of."""
        if self._player is not None:
            self._player.stop()
            self._player = None
        self._set_playing(False)
        self.slider.setValue(0)
        self.elapsed_label.setText(_mmss(0))

    def stop(self) -> None:
        """Hard-stops and resets to the ready state -- called by the
        owning dialog on reject()/_fail() and right before the real
        recording/burn begins, so no preview stream is ever left open
        across that transition."""
        self._timer.stop()
        if self._player is not None:
            self._player.stop()
            self._player = None
        self._playing = False
        self.play_btn.setText(self.tr("Play"))
        self.slider.setValue(0)
        self.elapsed_label.setText(_mmss(0))
        self.total_label.setText("--:--")
        self.total_label.setToolTip("")
        self._duration = 0.0

    # --- the slider, and the timer that drives it -----------------------

    def _refresh_position(self) -> None:
        if self._player is None or self.slider.isSliderDown():
            return
        elapsed = self._player.position_seconds
        self.elapsed_label.setText(_mmss(elapsed))
        if self._duration > 0:
            self.slider.setValue(int(SLIDER_RANGE * min(1.0, elapsed / self._duration)))

    def _on_slider_released(self) -> None:
        if self._player is None or self._duration <= 0:
            return
        target = self._duration * (self.slider.value() / SLIDER_RANGE)
        self._player.seek(target)
        self.elapsed_label.setText(_mmss(target))
