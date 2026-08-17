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
