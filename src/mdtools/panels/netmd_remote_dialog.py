"""A NetMD transport remote -- the NetMD counterpart to RemoteDialog,
opened from the same "Remote Control" entry points (Window menu, startup
screen) once `app_settings.netmd_enabled()` says NetMD is the machine
being driven.

Deliberately not the same class as RemoteDialog, and deliberately far
smaller. RemoteDialog mirrors a *physical* remote key for key because the
MDRem adapter presses buttons on a deck that cannot answer -- every group
on it (titling, character entry, track-number keys up to 25, the disc
editing pair) exists because infrared has no other way to reach that part
of the deck. None of that applies here:

- **Titling already happens elsewhere, in one shot.** A NetMD title goes
  out with its track's audio (`netmd.send_tracks()`) or through Upload
  Tracklist (`netmd.build_title_plan()`/`write_titles()`), never typed key
  by key -- so there is no Titling group, no Typing group, and no on-screen
  keyboard capture to mirror RemoteDialog's own keyPressEvent.
- **The deck answers.** Every `netmdcli` command reports success or
  failure, so a press here can say "Done" or the real reason it was not,
  never RemoteDialog's "Sent" (which is all MDRem can ever promise).
- **There is no `eject` in netmdcli's own command list** -- confirmed
  against its `--help` output, not assumed -- so there is no Eject button
  to offer, unlike RemoteDialog's Transport group.
- **Track numbers are typed, not laid out as a bank of buttons.** NetMD
  tracks go up to 99 (MAX_TRACK, the same ceiling titling is held to), far
  more than a button grid is worth building for something the deck can
  already read a disc's own track count for.

No worker thread here either, for the same reason RemoteDialog has none:
one `netmdcli` invocation is a fraction of a second."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from mdtools import netmd


class NetMdRemoteDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Remote (NetMD)"))

        layout = QVBoxLayout(self)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        transport = QGroupBox(self.tr("Transport"))
        grid = QGridLayout(transport)
        grid.addWidget(self._command_button(self.tr("|<<"), self._previous), 0, 0)
        grid.addWidget(self._command_button(self.tr("Play"), self._play), 0, 1)
        grid.addWidget(self._command_button(self.tr(">>|"), self._next), 0, 2)
        grid.addWidget(self._command_button(self.tr("<<"), self._rewind), 1, 0)
        grid.addWidget(self._command_button(self.tr("Pause"), self._pause), 1, 1)
        grid.addWidget(self._command_button(self.tr(">>"), self._fast_forward), 1, 2)
        grid.addWidget(self._command_button(self.tr("Stop"), self._stop), 2, 0)
        grid.addWidget(self._command_button(self.tr("Restart"), self._restart), 2, 1)
        layout.addWidget(transport)

        track_row = QGroupBox(self.tr("Play a Track"))
        track_form = QHBoxLayout(track_row)
        self.track_spin = QSpinBox()
        self.track_spin.setRange(1, netmd.MAX_TRACK)
        track_form.addWidget(self.track_spin, 1)
        play_track_btn = QPushButton(self.tr("Play"))
        play_track_btn.clicked.connect(self._play_track)
        track_form.addWidget(play_track_btn)
        layout.addWidget(track_row)

        mode_row = QGroupBox(self.tr("Play Mode"))
        mode_form = QFormLayout(mode_row)
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(self.tr("Single"), "single")
        self.mode_combo.addItem(self.tr("Repeat"), "repeat")
        self.mode_combo.addItem(self.tr("Shuffle"), "shuffle")
        mode_form.addRow(self.mode_combo)
        set_mode_btn = QPushButton(self.tr("Set"))
        set_mode_btn.clicked.connect(self._set_play_mode)
        mode_form.addRow(set_mode_btn)
        layout.addWidget(mode_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_status()

    def _command_button(self, label: str, handler) -> QPushButton:
        button = QPushButton(label)
        button.clicked.connect(handler)
        return button

    # --- the deck -------------------------------------------------------

    def _refresh_status(self) -> None:
        """Read once, on open -- not a live "is it still there?" poll, the
        same "asked once, trusted until proven otherwise" stance every
        other NetMD entry point here takes. The disc's own track count
        also caps what a "Play a Track" number is worth entering."""
        missing = netmd.missing_tools()
        if missing:
            self.status_label.setText(
                self.tr("Missing tools: {tools}.").format(tools=", ".join(missing))
            )
            return
        try:
            disc = netmd.read_disc()
        except netmd.NetMdError as exc:
            self.status_label.setText(self.tr("Not connected: {error}").format(error=exc))
            return
        if disc.track_count:
            self.track_spin.setMaximum(min(netmd.MAX_TRACK, disc.track_count))
        self.status_label.setText(
            self.tr("Connected -- {title} ({count} tracks).").format(
                title=disc.title or self.tr("(untitled disc)"), count=disc.track_count
            )
        )

    def _run(self, action, description: str) -> None:
        """Every button goes through this: the deck answers, unlike
        MDRem's, so a press here can say what actually happened rather
        than only that something was sent."""
        try:
            action()
        except netmd.NetMdError as exc:
            self.status_label.setText(self.tr("{action} failed: {error}").format(action=description, error=exc))
            return
        self.status_label.setText(self.tr("Done: {action}").format(action=description))

    def _play(self) -> None:
        self._run(netmd.play, self.tr("Play"))

    def _play_track(self) -> None:
        track = self.track_spin.value()
        self._run(lambda: netmd.play(track), self.tr("Play track {number}").format(number=track))

    def _pause(self) -> None:
        self._run(netmd.pause, self.tr("Pause"))

    def _stop(self) -> None:
        self._run(netmd.stop, self.tr("Stop"))

    def _fast_forward(self) -> None:
        self._run(netmd.fast_forward, self.tr("Fast forward"))

    def _rewind(self) -> None:
        self._run(netmd.rewind, self.tr("Rewind"))

    def _next(self) -> None:
        self._run(netmd.next_track, self.tr("Next track"))

    def _previous(self) -> None:
        self._run(netmd.previous_track, self.tr("Previous track"))

    def _restart(self) -> None:
        self._run(netmd.restart_track, self.tr("Restart track"))

    def _set_play_mode(self) -> None:
        mode = self.mode_combo.currentData()
        self._run(lambda: netmd.set_play_mode(mode), self.mode_combo.currentText())
