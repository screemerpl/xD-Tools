"""RecordingProgressBar in isolation -- no MainWindow involved, see
test_main_window_recording_bar.py for the wiring that feeds it.
"""

from __future__ import annotations

from mdtools.panels.recording_progress_bar import RecordingProgressBar


def test_hidden_until_started(qt_app):
    bar = RecordingProgressBar()
    assert not bar.isVisible()


def test_start_shows_the_bar_and_resets_it(qt_app):
    bar = RecordingProgressBar()
    bar.set_overall(0.7, "stale")
    bar.start(track_progress=True)
    assert bar.isVisible()
    assert bar.overall_bar.value() == 0
    assert bar.overall_label.text() == ""


def test_track_progress_true_shows_the_track_row(qt_app):
    bar = RecordingProgressBar()
    bar.start(track_progress=True)
    assert bar.track_bar.isVisible()
    assert bar.track_label.isVisible()


def test_track_progress_false_hides_the_track_row(qt_app):
    bar = RecordingProgressBar()
    bar.start(track_progress=False)
    assert not bar.track_bar.isVisible()
    assert not bar.track_label.isVisible()


def test_set_overall_maps_the_fraction_onto_the_1000_range(qt_app):
    bar = RecordingProgressBar()
    bar.start(track_progress=False)
    bar.set_overall(0.5, "halfway")
    assert bar.overall_bar.value() == 500
    assert bar.overall_label.text() == "halfway"


def test_set_track_negative_fraction_hides_the_row(qt_app):
    """RecordDialog's own sentinel for "titling now, no per-track
    concept" -- see record_dialog.py's _begin_nested_titling()."""
    bar = RecordingProgressBar()
    bar.start(track_progress=True)
    bar.set_track(0.3, "Track One")
    assert bar.track_bar.isVisible()

    bar.set_track(-1.0, "")
    assert not bar.track_bar.isVisible()
    assert not bar.track_label.isVisible()


def test_set_track_non_negative_shows_and_fills_the_row(qt_app):
    bar = RecordingProgressBar()
    bar.start(track_progress=True)
    bar.set_track(-1.0, "")
    bar.set_track(0.25, "Track Two")
    assert bar.track_bar.isVisible()
    assert bar.track_bar.value() == 250
    assert bar.track_label.text() == "Track Two"


def test_set_dialog_hidden_toggles_the_show_button(qt_app):
    bar = RecordingProgressBar()
    bar.start(track_progress=True)
    assert not bar.show_dialog_btn.isVisible()
    bar.set_dialog_hidden(True)
    assert bar.show_dialog_btn.isVisible()
    bar.set_dialog_hidden(False)
    assert not bar.show_dialog_btn.isVisible()


def test_stop_hides_the_bar_and_the_show_button(qt_app):
    bar = RecordingProgressBar()
    bar.start(track_progress=True)
    bar.set_dialog_hidden(True)
    bar.stop()
    assert not bar.isVisible()
    assert not bar.show_dialog_btn.isVisible()


def test_start_does_not_reset_an_already_hidden_dialog_button(qt_app):
    """A dialog hidden during disc 1 of a multi-disc recording is still
    hidden when disc 2's own running_changed(True) fires start() again --
    start() must not clear that back to False on its own."""
    bar = RecordingProgressBar()
    bar.start(track_progress=True)
    bar.set_dialog_hidden(True)
    bar.start(track_progress=True)
    assert bar.show_dialog_btn.isVisible()


def test_stop_requested_signal_fires_on_click(qt_app):
    bar = RecordingProgressBar()
    received = []
    bar.stop_requested.connect(lambda: received.append(True))
    bar.stop_btn.click()
    assert received == [True]


def test_show_dialog_requested_signal_fires_on_click(qt_app):
    bar = RecordingProgressBar()
    bar.start(track_progress=True)
    bar.set_dialog_hidden(True)
    received = []
    bar.show_dialog_requested.connect(lambda: received.append(True))
    bar.show_dialog_btn.click()
    assert received == [True]
