from mdtools import app_settings
from mdtools.app_window import MainWindow
from mdtools.panels.settings_dialog import SettingsDialog


def test_dialog_seeds_fields_from_current_settings(qt_app):
    app_settings.set_screen_dpi(120.0)
    app_settings.set_default_export_dpi(600.0)
    app_settings.set_bake_dpi(1800.0)

    dialog = SettingsDialog()

    assert dialog.screen_dpi_spin.value() == 120.0
    assert dialog.export_dpi_spin.value() == 600.0
    assert dialog.bake_dpi_spin.value() == 1800.0


def test_accepting_saves_the_edited_values(qt_app):
    dialog = SettingsDialog()
    dialog.screen_dpi_spin.setValue(110.0)
    dialog.export_dpi_spin.setValue(450.0)
    dialog.bake_dpi_spin.setValue(1500.0)

    dialog._on_accept()

    assert app_settings.screen_dpi() == 110.0
    assert app_settings.default_export_dpi() == 450.0
    assert app_settings.bake_dpi() == 1500.0


def test_cancelling_does_not_save_anything(qt_app):
    app_settings.set_screen_dpi(96.0)
    dialog = SettingsDialog()
    dialog.screen_dpi_spin.setValue(300.0)

    dialog.reject()

    assert app_settings.screen_dpi() == 96.0


def test_restore_defaults_resets_the_fields_without_saving(qt_app):
    app_settings.set_screen_dpi(200.0)
    dialog = SettingsDialog()
    dialog.screen_dpi_spin.setValue(55.0)

    dialog._restore_defaults()

    assert dialog.screen_dpi_spin.value() == app_settings.DEFAULT_SCREEN_DPI
    assert dialog.export_dpi_spin.value() == app_settings.DEFAULT_EXPORT_DPI
    assert dialog.bake_dpi_spin.value() == app_settings.DEFAULT_BAKE_DPI
    # restoring the fields alone must not touch the saved setting
    assert app_settings.screen_dpi() == 200.0


def test_window_menu_settings_action_opens_the_dialog(qt_app, monkeypatch):
    import mdtools.app_window as app_window_module

    opened = []

    def fake_exec(self):
        opened.append(self)
        return 0

    monkeypatch.setattr(app_window_module.SettingsDialog, "exec", fake_exec)

    win = MainWindow(show_startup_dialog=False)
    win._show_settings()

    assert len(opened) == 1
    assert isinstance(opened[0], app_window_module.SettingsDialog)


# --- Record CD to MiniDisc settings -----------------------------------------


def test_cd_rows_seed_from_settings_and_save_on_ok(qt_app, tmp_path):
    app_settings.set_cd_rip_folder(str(tmp_path / "rips"))
    app_settings.set_foobar_exe(str(tmp_path / "foobar2000.exe"))

    dialog = SettingsDialog()
    assert dialog.cd_rip_folder_edit.text() == str(tmp_path / "rips")
    assert dialog.foobar_exe_edit.text() == str(tmp_path / "foobar2000.exe")

    dialog.cd_rip_folder_edit.setText(str(tmp_path / "elsewhere"))
    dialog._on_accept()

    assert app_settings.cd_rip_folder() == str(tmp_path / "elsewhere")


def test_the_rip_folder_falls_back_to_a_temp_subfolder(qt_app):
    app_settings.set_cd_rip_folder("")
    assert app_settings.cd_rip_folder() == app_settings.default_cd_rip_folder()
    assert "MDTools CD Rip" in app_settings.cd_rip_folder()


def test_restore_defaults_puts_the_rip_folder_back(qt_app, tmp_path):
    app_settings.set_cd_rip_folder(str(tmp_path / "somewhere"))
    dialog = SettingsDialog()

    dialog._restore_defaults()

    assert dialog.cd_rip_folder_edit.text() == app_settings.default_cd_rip_folder()


def test_the_foobar_program_field_is_prefilled_by_detection_when_unset(qt_app, monkeypatch):
    """A first run should not have to be told where foobar2000 is when the
    installer already registered it."""
    from mdtools.panels import settings_dialog as module

    app_settings.set_foobar_exe("")
    monkeypatch.setattr(module.foobar, "find_foobar_exe", lambda: r"C:\fb2k\foobar2000.exe")

    assert SettingsDialog().foobar_exe_edit.text() == r"C:\fb2k\foobar2000.exe"


# --- the CD rip folder ------------------------------------------------
#
# It is a path somebody typed, so it routinely names a directory that does
# not exist yet -- which is the normal state before the first rip, and used
# to be left for the rip itself to trip over.


def test_accepting_creates_the_rip_folder(qt_app, tmp_path):
    target = tmp_path / "rips" / "here"
    dialog = SettingsDialog()
    dialog.cd_rip_folder_edit.setText(str(target))

    dialog._on_accept()

    assert target.is_dir()
    assert app_settings.cd_rip_folder() == str(target)


def test_a_folder_that_cannot_be_created_warns_but_keeps_the_setting(qt_app, tmp_path, monkeypatch):
    """The same rule the MDRem port follows: a drive that is not plugged in
    right now is a reason to say so, not a reason to refuse the setting."""
    from mdtools.panels import settings_dialog as module

    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory")
    warned: list = []
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(True)))

    dialog = SettingsDialog()
    dialog.cd_rip_folder_edit.setText(str(blocked / "underneath"))
    dialog._on_accept()

    assert warned
    assert app_settings.cd_rip_folder() == str(blocked / "underneath")


def test_browsing_creates_the_folder_first_so_the_picker_opens_in_it(qt_app, tmp_path, monkeypatch):
    """A picker pointed at a directory that is not there does not politely
    fall back -- it complains."""
    from PySide6.QtWidgets import QFileDialog

    target = tmp_path / "not-yet"
    seen: list = []
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda parent, caption, directory="", *a, **k: (seen.append(directory), "")[1]),
    )
    dialog = SettingsDialog()
    dialog.cd_rip_folder_edit.setText(str(target))

    dialog._browse_rip_folder()

    assert target.is_dir()
    assert seen == [str(target)]
