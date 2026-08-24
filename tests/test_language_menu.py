import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QDialogButtonBox

from mdtools import i18n
from mdtools.app_window import MainWindow


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Redirect i18n's persisted language choice to a throwaway file --
    otherwise these tests would read/write the real per-user settings.ini."""
    path = tmp_path / "settings.ini"
    monkeypatch.setattr(i18n, "_settings", lambda: QSettings(str(path), QSettings.Format.IniFormat))


def test_language_menu_has_an_action_per_available_language(qt_app, isolated_settings):
    win = MainWindow(show_startup_dialog=False)
    assert set(win._language_actions) == set(i18n.AVAILABLE_LANGUAGES)
    for code, action in win._language_actions.items():
        assert action.text() == i18n.AVAILABLE_LANGUAGES[code]
        assert action.isCheckable()


def test_current_language_starts_checked(qt_app, isolated_settings):
    i18n.set_language("pl")
    win = MainWindow(show_startup_dialog=False)
    assert win._language_actions["pl"].isChecked()
    assert not win._language_actions["en"].isChecked()


def test_selecting_a_language_persists_it(qt_app, isolated_settings, monkeypatch):
    from mdtools import app_window as app_window_module

    monkeypatch.setattr(app_window_module.QMessageBox, "exec", lambda self: 0)

    win = MainWindow(show_startup_dialog=False)
    assert i18n.current_language() == "en"

    win._on_language_selected("pl")
    assert i18n.current_language() == "pl"


def test_selecting_the_already_active_language_is_a_no_op(qt_app, isolated_settings, monkeypatch):
    from mdtools import app_window as app_window_module

    def fail_if_shown(self):
        raise AssertionError("no dialog should appear when the language didn't actually change")

    monkeypatch.setattr(app_window_module.QMessageBox, "exec", fail_if_shown)

    win = MainWindow(show_startup_dialog=False)
    win._on_language_selected("en")  # already the active language


def test_language_changed_dialog_offers_a_restart_now_button(qt_app, isolated_settings, monkeypatch):
    from mdtools import app_window as app_window_module

    captured = {}

    def fake_exec(self):
        captured["buttons"] = [b.text() for b in self.buttons()]
        self._clicked = self.buttons()[1]  # "Later" -- must not trigger a restart
        return 0

    def fake_clicked_button(self):
        return self._clicked

    monkeypatch.setattr(app_window_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_window_module.QMessageBox, "clickedButton", fake_clicked_button)
    monkeypatch.setattr(
        app_window_module.MainWindow, "_restart_app", staticmethod(lambda: (_ for _ in ()).throw(
            AssertionError("Later must not restart")
        ))
    )

    win = MainWindow(show_startup_dialog=False)
    win._on_language_selected("pl")

    assert captured["buttons"] == ["Restart Now", "Later"]


def test_clicking_restart_now_calls_restart_app(qt_app, isolated_settings, monkeypatch):
    from mdtools import app_window as app_window_module

    def fake_exec(self):
        self._clicked = self.buttons()[0]  # "Restart Now"
        return 0

    def fake_clicked_button(self):
        return self._clicked

    monkeypatch.setattr(app_window_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_window_module.QMessageBox, "clickedButton", fake_clicked_button)

    restarted = []
    monkeypatch.setattr(app_window_module.MainWindow, "_restart_app", staticmethod(lambda: restarted.append(1)))

    win = MainWindow(show_startup_dialog=False)
    win._on_language_selected("pl")

    assert restarted == [1]


def test_restart_now_does_not_discard_unsaved_changes(qt_app, isolated_settings, monkeypatch):
    """_restart_app() quits via QApplication.quit(), which bypasses
    closeEvent()'s own unsaved-changes guard entirely -- restarting for a
    new language must not silently throw away unsaved project changes."""
    from mdtools import app_window as app_window_module

    def fake_exec(self):
        self._clicked = self.buttons()[0]  # "Restart Now"
        return 0

    def fake_clicked_button(self):
        return self._clicked

    monkeypatch.setattr(app_window_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_window_module.QMessageBox, "clickedButton", fake_clicked_button)

    restarted = []
    monkeypatch.setattr(app_window_module.MainWindow, "_restart_app", staticmethod(lambda: restarted.append(1)))

    win = MainWindow(show_startup_dialog=False)
    monkeypatch.setattr(win, "_may_discard_changes", lambda: False)  # simulates Cancel on the save prompt

    win._on_language_selected("pl")

    assert restarted == [], "restart must not proceed once the user declined to discard changes"


def test_restart_app_relaunches_the_process_and_quits(qt_app, monkeypatch):
    """Only QProcess.startDetached and QApplication.quit are faked here --
    QApplication.instance() is left alone (it must keep returning the
    real, session-wide app) since pytest-qt's own plugin calls
    instance().processEvents() around every test; replacing it wholesale
    would break that, not just this test."""
    from mdtools import app_window as app_window_module

    started = []
    monkeypatch.setattr(
        app_window_module.QProcess, "startDetached", staticmethod(lambda program, args: started.append((program, args)))
    )
    quit_calls = []
    monkeypatch.setattr(app_window_module.QApplication, "quit", lambda self: quit_calls.append(1))
    monkeypatch.setattr(app_window_module.sys, "argv", ["mdtools.main", "--some-flag"])
    monkeypatch.setattr(app_window_module.sys, "executable", "/usr/bin/python3")
    monkeypatch.delattr(app_window_module.sys, "frozen", raising=False)

    app_window_module.MainWindow._restart_app()

    assert started == [("/usr/bin/python3", ["mdtools.main", "--some-flag"])]
    assert quit_calls == [1]


def test_install_translator_also_translates_qts_own_standard_button_labels(qt_app, isolated_settings):
    """Regression test: mdtools_<code>.qm only ever covers this app's own
    self.tr(...) strings -- a QDialogButtonBox.StandardButton's label
    ("Close", "Cancel", "OK", ...) is owned by Qt itself and lives in a
    completely separate qtbase_<code>.qm, shipped inside the PySide6
    wheel. Installing only the former (the original bug -- reported
    directly: "why is the button Close on print dialog not translated to
    Polish") leaves every standard button in English regardless of the
    selected language."""
    try:
        i18n.install_translator(qt_app, "pl")
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        assert box.button(QDialogButtonBox.StandardButton.Close).text() == "Zamknij"
    finally:
        i18n.install_translator(qt_app, "en")  # leave no translator installed for later tests


def test_restart_app_in_a_frozen_build_does_not_duplicate_the_program_name(qt_app, monkeypatch):
    """A frozen (PyInstaller) build's sys.executable IS the program to
    relaunch -- sys.argv[1:] (not the full sys.argv, which would repeat
    the exe path as its own first argument) is what QProcess.startDetached
    expects as `arguments`."""
    from mdtools import app_window as app_window_module

    started = []
    monkeypatch.setattr(
        app_window_module.QProcess, "startDetached", staticmethod(lambda program, args: started.append((program, args)))
    )
    monkeypatch.setattr(app_window_module.QApplication, "quit", lambda self: None)
    monkeypatch.setattr(app_window_module.sys, "argv", ["MDTools.exe", "--some-flag"])
    monkeypatch.setattr(app_window_module.sys, "executable", "C:/MDTools/MDTools.exe")
    monkeypatch.setattr(app_window_module.sys, "frozen", True, raising=False)

    app_window_module.MainWindow._restart_app()

    assert started == [("C:/MDTools/MDTools.exe", ["--some-flag"])]
