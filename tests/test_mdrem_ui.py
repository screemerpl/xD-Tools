"""Where MDRem support meets the UI: the Settings rows that configure it,
and the two entry points that only exist once it's enabled.

Note the visibility assertions use isHidden(), not isVisible() -- a widget
inside a dialog that was never shown reports isVisible() == False whatever
its own state is, so it cannot distinguish "hidden on purpose" from "its
parent isn't on screen", which is the whole point here.
"""

import pytest

from mdtools import app_settings, mdrem
from mdtools.panels import mdrem_port as mdrem_port_module
from mdtools.panels.mdrem_upload_dialog import MDRemUploadDialog, _UploadWorker
from mdtools.panels.metadata_dialog import MetadataDialog
from mdtools.panels.settings_dialog import SettingsDialog
from mdtools.panels.startup_dialog import StartupDialog
from mdtools.project import ProjectMetadata, Track


@pytest.fixture
def no_real_ports(monkeypatch):
    """Nothing in this file may touch a real serial port -- a developer
    machine with an actual adapter plugged in would otherwise get different
    results from one without."""
    monkeypatch.setattr(mdrem, "list_ports", lambda: [])
    monkeypatch.setattr(mdrem, "detect_port", lambda *a, **k: None)


def _fake_ports(*names):
    return [
        mdrem.PortCandidate(name=name, description="USB Serial", manufacturer="", is_likely=True) for name in names
    ]


def _album():
    return ProjectMetadata(
        album="Lost Souls", artist="Caskets", year=2021, tracks=[Track("The Only Ones"), Track("Glass Heart")]
    )


# --- settings --------------------------------------------------------------


def test_settings_seed_the_checkbox_and_port_from_saved_values(qt_app, monkeypatch):
    monkeypatch.setattr(mdrem, "list_ports", lambda: _fake_ports("COM3", "COM7"))
    app_settings.set_mdrem_enabled(True)
    app_settings.set_mdrem_port("COM7")

    dialog = SettingsDialog()

    assert dialog.mdrem_check.isChecked()
    assert dialog.selected_port() == "COM7"


def test_accepting_saves_the_adapter_settings(qt_app, monkeypatch):
    monkeypatch.setattr(mdrem, "list_ports", lambda: _fake_ports("COM3"))
    dialog = SettingsDialog()
    dialog.mdrem_check.setChecked(True)

    dialog._on_accept()

    assert app_settings.mdrem_enabled() is True
    assert app_settings.mdrem_port() == "COM3"


def test_a_saved_port_survives_the_adapter_being_unplugged(qt_app, monkeypatch):
    """Silently resetting the setting to whatever else happens to be
    connected would be worse than showing the real one as missing."""
    monkeypatch.setattr(mdrem, "list_ports", lambda: _fake_ports("COM3"))
    app_settings.set_mdrem_port("COM9")

    dialog = SettingsDialog()

    assert dialog.selected_port() == "COM9"
    assert "COM9" in dialog.mdrem_port_combo.currentText()


def test_the_port_row_is_inert_while_the_adapter_is_disabled(qt_app, no_real_ports):
    dialog = SettingsDialog()

    dialog.mdrem_check.setChecked(False)
    assert not dialog._mdrem_port_widget.isEnabled()
    dialog.mdrem_check.setChecked(True)
    assert dialog._mdrem_port_widget.isEnabled()


def test_detect_reports_when_nothing_answers(qt_app, no_real_ports, monkeypatch):
    shown = []
    monkeypatch.setattr(
        "mdtools.panels.settings_dialog.QMessageBox.information", lambda *a, **k: shown.append(a)
    )
    dialog = SettingsDialog()

    dialog._detect_port()

    assert shown, "the user must be told nothing was found, not left with an unchanged combo"


def test_detect_selects_whatever_answered(qt_app, monkeypatch):
    monkeypatch.setattr(mdrem, "list_ports", lambda: _fake_ports("COM3", "COM8"))
    monkeypatch.setattr(mdrem, "detect_port", lambda *a, **k: "COM8")
    dialog = SettingsDialog()

    dialog._detect_port()

    assert dialog.selected_port() == "COM8"


# --- entry points appear only when enabled ---------------------------------


def test_upload_button_is_absent_until_the_adapter_is_enabled(qt_app, no_real_ports):
    app_settings.set_mdrem_enabled(False)
    assert MetadataDialog(_album()).upload_btn.isHidden()

    app_settings.set_mdrem_enabled(True)
    assert not MetadataDialog(_album()).upload_btn.isHidden()


def test_remote_button_is_absent_until_the_adapter_is_enabled(qt_app, no_real_ports):
    app_settings.set_mdrem_enabled(False)
    assert StartupDialog([]).remote_btn.isHidden()

    app_settings.set_mdrem_enabled(True)
    assert not StartupDialog([]).remote_btn.isHidden()


# --- port resolution -------------------------------------------------------


def test_a_configured_port_is_used_without_probing(qt_app, monkeypatch):
    app_settings.set_mdrem_port("COM4")
    monkeypatch.setattr(
        mdrem, "detect_port", lambda *a, **k: pytest.fail("must not probe when a port is already configured")
    )

    assert mdrem_port_module.resolve_port(None) == "COM4"


def test_a_probed_port_is_remembered_so_the_probe_happens_once(qt_app, monkeypatch):
    monkeypatch.setattr(mdrem, "detect_port", lambda *a, **k: "COM5")

    assert mdrem_port_module.resolve_port(None) == "COM5"
    assert app_settings.mdrem_port() == "COM5"


def test_resolve_port_warns_and_gives_up_when_nothing_is_found(qt_app, no_real_ports, monkeypatch):
    warned = []
    monkeypatch.setattr("mdtools.panels.mdrem_port.QMessageBox.warning", lambda *a, **k: warned.append(a))

    assert mdrem_port_module.resolve_port(None) is None
    assert warned


# --- upload dialog ---------------------------------------------------------


def test_upload_dialog_shows_every_title_before_writing_any_of_them(qt_app):
    dialog = MDRemUploadDialog(_album(), "COM_TEST")

    written = [dialog.tree.topLevelItem(i).text(1) for i in range(dialog.tree.topLevelItemCount())]
    assert written == ["Caskets - Lost Souls (2021)", "The Only Ones", "Glass Heart"]


def test_upload_dialog_does_not_touch_the_device_until_start_is_pressed(qt_app):
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    assert dialog._worker is None


def test_upload_dialog_warns_about_characters_the_deck_cannot_show(qt_app):
    metadata = ProjectMetadata(album="日本語", artist="Caskets", tracks=[Track("Track ①")])
    dialog = MDRemUploadDialog(metadata, "COM_TEST")

    warning = dialog._warning_text()
    assert "日" in warning


def test_upload_dialog_refuses_to_start_with_nothing_to_write(qt_app):
    dialog = MDRemUploadDialog(ProjectMetadata(), "COM_TEST")
    assert not dialog.start_btn.isEnabled()


def test_erasing_is_on_by_default_because_leaving_old_text_behind_is_worse(qt_app):
    assert MDRemUploadDialog(_album(), "COM_TEST").clear_check.isChecked()


def test_turning_off_erasing_updates_the_quoted_time(qt_app):
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    with_clearing = dialog.summary_label.text()

    dialog.clear_check.setChecked(False)

    assert dialog.summary_label.text() != with_clearing


def test_the_erase_choice_actually_reaches_the_firmware(qt_app, monkeypatch):
    """The checkbox is worthless if it only changes the estimate -- what
    matters is which form of the command goes out. It is said per command
    (TITLETRACKCLEAR / TITLETRACKNOCLEAR) rather than by first putting the
    board into a TIMING COUNT, which it keeps in RAM until it is reset."""
    sent: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def command(self, text, **kwargs):
            sent.append(text)

    monkeypatch.setattr(mdrem, "MDRemClient", FakeClient)
    plan = mdrem.build_upload_plan(_album())

    # run() called directly rather than via start(): it is an ordinary
    # method, and this keeps the test free of thread timing.
    _UploadWorker("COM_TEST", plan.steps, clear_first=False).run()
    assert sent == [step.command(False) for step in plan.steps]
    assert all("NOCLEAR" in line for line in sent)

    sent.clear()
    _UploadWorker("COM_TEST", plan.steps, clear_first=True).run()
    assert sent == [step.command(True) for step in plan.steps]
    assert not any("TIMING" in line for line in sent), "the global is never touched"


def test_progress_advances_between_steps_not_only_at_their_boundaries(qt_app):
    """One update per step leaves the bar frozen for the 20-30 s a title
    takes, which reads as a hung app -- it is driven by elapsed time
    instead, so it must move without any new step being reported."""
    dialog = MDRemUploadDialog(_album(), "COM_TEST")
    dialog._step_estimates = [10.0, 10.0]
    dialog._total_estimate = 20.0
    dialog._completed_estimate = 0.0
    dialog._current_estimate = 10.0
    dialog._step_clock.start()

    dialog._tick()
    first = dialog.progress.value()
    dialog._completed_estimate = 10.0  # as if a step boundary had passed
    dialog._tick()

    assert dialog.progress.value() > first


def test_stopping_does_not_block_on_the_worker(qt_app, monkeypatch):
    """reject() used to call worker.wait(), freezing the whole window for
    up to 30 s while the current title finished -- reported as the dialog
    hanging. It must now return immediately and close later."""
    dialog = MDRemUploadDialog(_album(), "COM_TEST")

    class BusyWorker:
        def __init__(self):
            self.cancelled = False

        def isRunning(self):
            return True

        def cancel(self):
            self.cancelled = True

        def wait(self, *a):
            pytest.fail("reject() must not wait on the worker from the GUI thread")

    worker = BusyWorker()
    dialog._worker = worker
    dialog.show()

    dialog.reject()

    assert worker.cancelled, "the worker must be asked to stop"
    assert dialog._closing, "the dialog must remember it is closing"
    assert not dialog.isHidden(), "it stays open until the worker actually finishes"

    dialog._worker = None
    dialog._on_worker_finished()
    assert dialog.isHidden(), "and closes itself once the worker reports finished"
