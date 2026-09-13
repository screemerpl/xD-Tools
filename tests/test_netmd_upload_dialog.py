"""NetMdUploadDialog: the titles a disc is about to get, then getting them.

The worker is driven synchronously here rather than as a real QThread --
what matters is the sequence (read the disc, plan against what is on it,
write, report), and a thread would only add waiting to it. netmd.py's own
tests cover the commands themselves.
"""

from __future__ import annotations

import pytest

from mdtools import netmd
from mdtools.panels.netmd_upload_dialog import NetMdUploadDialog
from mdtools.project import ProjectMetadata, Track


# isHidden() rather than isVisible() throughout: these dialogs are never
# shown in the suite, and a child of an unshown window reports
# isVisible() == False however its own flag is set.


def _metadata(*titles: str, album: str = "Night Ferry") -> ProjectMetadata:
    return ProjectMetadata(album=album, artist="Aurora", tracks=[Track(title=t) for t in titles])


@pytest.fixture(autouse=True)
def no_real_deck(monkeypatch):
    """Nothing in this file may reach a USB cable."""
    from mdtools.panels import netmd_upload_dialog as module

    monkeypatch.setattr(module.netmd, "missing_tools", lambda: [])
    return module


# --- before anything is written -------------------------------------------


def test_the_preview_lists_every_title_that_will_go_out(qt_app):
    dialog = NetMdUploadDialog(_metadata("Harbour Lights", "Slow Tide"))

    text = dialog.preview.toPlainText()
    assert "Night Ferry" in text
    assert "Harbour Lights" in text
    assert "Slow Tide" in text


def test_a_title_the_disc_cannot_carry_is_shown_before_it_is_written(qt_app):
    """The whole reason this dialog opens in a preview state: a user gets
    to see the transliterated form before it is on a disc."""
    dialog = NetMdUploadDialog(_metadata("Jôlie"))

    assert not dialog.warning_label.isHidden()
    assert "Jolie" in dialog.warning_label.text()


def test_nothing_is_written_just_by_opening_it(qt_app, monkeypatch, no_real_deck):
    monkeypatch.setattr(
        no_real_deck.netmd, "read_disc", lambda **k: pytest.fail("must not touch the deck")
    )

    NetMdUploadDialog(_metadata("One"))


# --- writing --------------------------------------------------------------


class _FakeWorker:
    """Stands in for the QThread: start() runs the whole sequence inline."""

    instances: list["_FakeWorker"] = []

    def __init__(self, dialog, disc, *, fail=None):
        self.dialog = dialog
        self.disc = disc
        self.fail = fail
        _FakeWorker.instances.append(self)

    def run_now(self) -> None:
        if self.fail is not None:
            self.dialog._on_failed(self.fail)
            return
        plan = netmd.build_title_plan(
            self.dialog._metadata.album or "",
            [track.title for track in self.dialog._metadata.tracks],
            track_count=self.disc.track_count,
        )
        self.dialog._on_plan_ready(plan)
        for index, command in enumerate(plan.commands, start=1):
            self.dialog._on_step(index, len(plan.commands), command.description)
        self.dialog._on_succeeded()


def test_progress_is_reported_as_titles_go_out(qt_app):
    dialog = NetMdUploadDialog(_metadata("One", "Two"))
    seen: list[tuple[float, str]] = []
    dialog.overall_progress_changed.connect(lambda fraction, text: seen.append((fraction, text)))

    _FakeWorker(dialog, netmd.NetMdDisc(tracks=[netmd.NetMdTrack(1), netmd.NetMdTrack(2)])).run_now()

    assert seen[-1][0] == 1.0
    assert dialog.succeeded is True


def test_a_disc_with_fewer_tracks_says_which_titles_are_dropped(qt_app):
    """Reported to the user rather than written partially and silently."""
    dialog = NetMdUploadDialog(_metadata("One", "Two", "Three"))

    _FakeWorker(dialog, netmd.NetMdDisc(tracks=[netmd.NetMdTrack(1), netmd.NetMdTrack(2)])).run_now()

    assert not dialog.warning_label.isHidden()
    assert "3" in dialog.warning_label.text()


def test_a_failure_is_reported_and_not_counted_as_success(qt_app):
    dialog = NetMdUploadDialog(_metadata("One"))

    _FakeWorker(dialog, netmd.NetMdDisc(), fail="no NetMD device found").run_now()

    assert dialog.succeeded is False
    assert "no NetMD device" in dialog.status_label.text()


def test_a_missing_tool_stops_before_it_starts(qt_app, monkeypatch, no_real_deck):
    monkeypatch.setattr(no_real_deck.netmd, "missing_tools", lambda: ["netmdcli"])
    dialog = NetMdUploadDialog(_metadata("One"))

    dialog._start()

    assert dialog._worker is None
    assert "netmdcli" in dialog.status_label.text()


def test_an_idle_dialog_is_not_busy(qt_app):
    """What decides whether the window's X hides it or closes it."""
    assert NetMdUploadDialog(_metadata("One")).is_busy() is False


def test_unattended_hides_the_start_button(qt_app, monkeypatch, no_real_deck):
    """The post-recording hand-off: nobody is sitting there to press it."""
    started: list[bool] = []
    monkeypatch.setattr(NetMdUploadDialog, "_start", lambda self: started.append(True))

    dialog = NetMdUploadDialog(_metadata("One"), unattended=True)

    assert dialog.start_btn.isVisible() is False
    assert started == [True]
