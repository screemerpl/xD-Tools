from mdtools import app_settings, audio_engine
from mdtools.app_window import MainWindow
from mdtools.panels.settings_dialog import GROUP_GENERAL, GROUP_TELEGRAM, SettingsDialog


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


# --- experimental features flag --------------------------------------------


def test_experimental_checkbox_seeds_from_current_setting(qt_app):
    app_settings.set_experimental_features_enabled(True)

    assert SettingsDialog().experimental_check.isChecked() is True


def test_accepting_saves_the_experimental_checkbox(qt_app):
    app_settings.set_experimental_features_enabled(False)
    dialog = SettingsDialog()
    dialog.experimental_check.setChecked(True)

    dialog._on_accept()

    assert app_settings.experimental_features_enabled() is True


def test_cancelling_does_not_save_the_experimental_checkbox(qt_app):
    app_settings.set_experimental_features_enabled(False)
    dialog = SettingsDialog()
    dialog.experimental_check.setChecked(True)

    dialog.reject()

    assert app_settings.experimental_features_enabled() is False


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

    dialog = SettingsDialog()
    assert dialog.cd_rip_folder_edit.text() == str(tmp_path / "rips")

    dialog.cd_rip_folder_edit.setText(str(tmp_path / "elsewhere"))
    dialog._on_accept()

    assert app_settings.cd_rip_folder() == str(tmp_path / "elsewhere")


def test_the_rip_folder_falls_back_to_the_shared_audio_folder(qt_app):
    app_settings.set_cd_rip_folder("")
    assert app_settings.cd_rip_folder() == app_settings.default_cd_rip_folder()
    assert "Audio" in app_settings.cd_rip_folder()


def test_restore_defaults_puts_the_rip_folder_back(qt_app, tmp_path):
    app_settings.set_cd_rip_folder(str(tmp_path / "somewhere"))
    dialog = SettingsDialog()

    dialog._restore_defaults()

    assert dialog.cd_rip_folder_edit.text() == app_settings.default_cd_rip_folder()


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


# --- audio output device -----------------------------------------------


def _fake_devices(monkeypatch, *names):
    devices = [
        audio_engine.OutputDevice(index=i, name=name, max_output_channels=2, default_samplerate=44100.0)
        for i, name in enumerate(names)
    ]
    monkeypatch.setattr(audio_engine, "list_output_devices", lambda: devices)


def test_the_device_combo_always_offers_system_default_first(qt_app, monkeypatch):
    _fake_devices(monkeypatch, "Speakers (Realtek)")

    dialog = SettingsDialog()

    assert dialog.audio_device_combo.itemText(0) == "System default"
    assert dialog.audio_device_combo.itemData(0) == ""


def test_choosing_a_device_and_accepting_saves_its_name(qt_app, monkeypatch):
    _fake_devices(monkeypatch, "Speakers (Realtek)", "Headset Earphone (Jabra)")
    app_settings.set_audio_output_device("")

    dialog = SettingsDialog()
    index = dialog.audio_device_combo.findData("Headset Earphone (Jabra)")
    dialog.audio_device_combo.setCurrentIndex(index)
    dialog._on_accept()

    assert app_settings.audio_output_device() == "Headset Earphone (Jabra)"


def test_a_saved_device_that_is_no_longer_plugged_in_still_shows_up(qt_app, monkeypatch):
    """Same rule the MDRem port combo already follows: a saved choice must
    survive opening this dialog even when its device isn't there right
    now -- silently falling back to whatever else is plugged in would be
    worse than showing it as disconnected."""
    _fake_devices(monkeypatch, "Speakers (Realtek)")
    app_settings.set_audio_output_device("Some USB DAC")

    dialog = SettingsDialog()

    assert dialog._selected_audio_device(dialog.audio_device_combo) == "Some USB DAC"
    assert "not connected" in dialog.audio_device_combo.currentText()


def test_restore_defaults_resets_the_device_to_system_default(qt_app, monkeypatch):
    _fake_devices(monkeypatch, "Speakers (Realtek)")
    app_settings.set_audio_output_device("Speakers (Realtek)")
    dialog = SettingsDialog()

    dialog._restore_defaults()

    assert dialog._selected_audio_device(dialog.audio_device_combo) == ""


def test_refresh_button_re_lists_devices_without_losing_the_saved_choice(qt_app, monkeypatch):
    _fake_devices(monkeypatch, "Speakers (Realtek)")
    app_settings.set_audio_output_device("Speakers (Realtek)")
    dialog = SettingsDialog()

    _fake_devices(monkeypatch, "Speakers (Realtek)", "New USB Interface")
    dialog._populate_audio_devices(dialog.audio_device_combo, dialog._selected_audio_device(dialog.audio_device_combo))

    assert dialog.audio_device_combo.findData("New USB Interface") >= 0
    assert dialog._selected_audio_device(dialog.audio_device_combo) == "Speakers (Realtek)"


# --- the cassette gets its own, independent device setting ----------------


def test_the_cassette_device_combo_is_independent_of_the_minidisc_one(qt_app, monkeypatch):
    """Explicit request: a MiniDisc deck typically wants a digital
    (S/PDIF) output and a cassette deck an analogue line output, which are
    routinely two different physical interfaces."""
    _fake_devices(monkeypatch, "SPDIF Out (Realtek)", "Line Out (Realtek)")
    app_settings.set_audio_output_device("SPDIF Out (Realtek)")
    app_settings.set_tape_audio_output_device("Line Out (Realtek)")

    dialog = SettingsDialog()

    assert dialog._selected_audio_device(dialog.audio_device_combo) == "SPDIF Out (Realtek)"
    assert dialog._selected_audio_device(dialog.tape_audio_device_combo) == "Line Out (Realtek)"


def test_accepting_saves_both_devices_separately(qt_app, monkeypatch):
    _fake_devices(monkeypatch, "SPDIF Out (Realtek)", "Line Out (Realtek)")
    dialog = SettingsDialog()
    dialog.audio_device_combo.setCurrentIndex(dialog.audio_device_combo.findData("SPDIF Out (Realtek)"))
    dialog.tape_audio_device_combo.setCurrentIndex(
        dialog.tape_audio_device_combo.findData("Line Out (Realtek)")
    )

    dialog._on_accept()

    assert app_settings.audio_output_device() == "SPDIF Out (Realtek)"
    assert app_settings.tape_audio_output_device() == "Line Out (Realtek)"


def test_restore_defaults_resets_both_devices(qt_app, monkeypatch):
    _fake_devices(monkeypatch, "SPDIF Out (Realtek)", "Line Out (Realtek)")
    app_settings.set_audio_output_device("SPDIF Out (Realtek)")
    app_settings.set_tape_audio_output_device("Line Out (Realtek)")
    dialog = SettingsDialog()

    dialog._restore_defaults()

    assert dialog._selected_audio_device(dialog.audio_device_combo) == ""
    assert dialog._selected_audio_device(dialog.tape_audio_device_combo) == ""


def test_a_missing_sounddevice_backend_leaves_only_system_default(qt_app, monkeypatch):
    """audio_engine.list_output_devices() raises when sounddevice/PortAudio
    isn't available at all -- this dialog must degrade to just the default
    option rather than failing to open."""
    monkeypatch.setattr(
        audio_engine,
        "list_output_devices",
        lambda: (_ for _ in ()).throw(audio_engine.AudioEngineError("no backend")),
    )

    dialog = SettingsDialog()

    assert dialog.audio_device_combo.count() == 1
    assert dialog.audio_device_combo.itemText(0) == "System default"


# --- recording gain -------------------------------------------------------


def test_the_gain_spinner_seeds_from_the_saved_setting(qt_app, monkeypatch):
    _fake_devices(monkeypatch)
    app_settings.set_recording_gain_db(-8.0)

    dialog = SettingsDialog()

    assert dialog.recording_gain_spin.value() == -8.0


def test_the_gain_defaults_to_minus_5_db_for_a_fresh_install(qt_app, monkeypatch):
    _fake_devices(monkeypatch)

    dialog = SettingsDialog()

    assert dialog.recording_gain_spin.value() == -5.0


def test_changing_the_gain_and_accepting_saves_it(qt_app, monkeypatch):
    _fake_devices(monkeypatch)
    dialog = SettingsDialog()
    dialog.recording_gain_spin.setValue(-2.0)

    dialog._on_accept()

    assert app_settings.recording_gain_db() == -2.0


def test_restore_defaults_resets_the_gain_too(qt_app, monkeypatch):
    _fake_devices(monkeypatch)
    app_settings.set_recording_gain_db(-12.0)
    dialog = SettingsDialog()

    dialog._restore_defaults()

    assert dialog.recording_gain_spin.value() == app_settings.DEFAULT_RECORDING_GAIN_DB


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


# --- settings groups ---------------------------------------------------------
#
# Settings used to be one long form here plus a second dialog of their own
# for the Telegram account, reached from the Experimental menu -- the same
# question ("what is xD-Tools configured to do?") answered in two places,
# one of them only findable if you knew it was filed under Experimental.


def test_the_groups_are_listed_down_the_left(qt_app):
    dialog = SettingsDialog()
    labels = [dialog.group_list.item(i).text() for i in range(dialog.group_list.count())]
    assert labels == ["General", "Telegram"]
    assert dialog.pages.count() == len(labels), "one page per group"


def test_it_opens_on_general(qt_app):
    assert SettingsDialog().pages.currentIndex() == GROUP_GENERAL


def test_picking_a_group_shows_its_page(qt_app):
    dialog = SettingsDialog()

    dialog.group_list.setCurrentRow(GROUP_TELEGRAM)

    assert dialog.pages.currentIndex() == GROUP_TELEGRAM


def test_show_group_jumps_straight_to_one(qt_app):
    """The Telegram chat's own "Sign in..." button has one page to send
    the user to and no reason to drop them on General to find it."""
    dialog = SettingsDialog()

    dialog.show_group(GROUP_TELEGRAM)

    assert dialog.pages.currentIndex() == GROUP_TELEGRAM
    assert dialog.group_list.currentRow() == GROUP_TELEGRAM


def test_ok_saves_every_group_not_just_the_one_on_screen(qt_app):
    """They are pages of one settings window with one OK underneath, so a
    change made in Telegram must survive switching back to General before
    pressing it."""
    dialog = SettingsDialog()
    dialog.bot_username_edit.setText("@some_bot")
    dialog.group_list.setCurrentRow(GROUP_GENERAL)

    dialog._on_accept()

    assert app_settings.telegram_bot_username() == "@some_bot"


def test_the_telegram_group_reports_whether_a_sign_in_is_saved(qt_app):
    """Local file presence only -- no network round trip just to open the
    settings window."""
    app_settings.telegram_session_path().unlink(missing_ok=True)
    dialog = SettingsDialog()
    assert "Not signed in" in dialog.telegram_status_label.text()
    assert not dialog.sign_out_btn.isEnabled()

    path = app_settings.telegram_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake session")
    dialog._refresh_telegram_status()

    assert "saved sign-in" in dialog.telegram_status_label.text()
    assert dialog.sign_out_btn.isEnabled()


def test_signing_out_forgets_the_local_session(qt_app):
    path = app_settings.telegram_session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake session")
    dialog = SettingsDialog()

    dialog._sign_out()

    assert not path.exists()
    assert not dialog.sign_out_btn.isEnabled()
