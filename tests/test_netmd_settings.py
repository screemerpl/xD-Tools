"""The NetMD setting, and the one rule that governs it: it and the MDRem
infrared adapter are two ways of driving the same deck, and never both at
once.

Every recording flow asks "which machine am I driving?" before it starts
-- they arm the deck differently, mark tracks differently and write titles
differently -- so the answer has to be single. These tests pin that down
at both ends: the setters, and the Settings window's own checkboxes.
"""

from __future__ import annotations

import pytest

from mdtools import app_settings, netmd
from mdtools.panels.settings_dialog import SettingsDialog


# --- the setting ----------------------------------------------------------


def test_off_by_default():
    assert app_settings.netmd_enabled() is False


def test_turning_netmd_on_turns_the_adapter_off():
    app_settings.set_mdrem_enabled(True)

    app_settings.set_netmd_enabled(True)

    assert app_settings.netmd_enabled() is True
    assert app_settings.mdrem_enabled() is False


def test_turning_the_adapter_on_turns_netmd_off():
    app_settings.set_netmd_enabled(True)

    app_settings.set_mdrem_enabled(True)

    assert app_settings.mdrem_enabled() is True
    assert app_settings.netmd_enabled() is False


def test_turning_one_off_does_not_turn_the_other_on():
    """Off is off. "Neither" is a perfectly ordinary state -- most users
    have no MiniDisc hardware at all and only ever design labels."""
    app_settings.set_netmd_enabled(True)
    app_settings.set_netmd_enabled(False)

    assert app_settings.netmd_enabled() is False
    assert app_settings.mdrem_enabled() is False


def test_a_settings_file_claiming_both_is_read_as_netmd():
    """Hand-edited, or carried over from a build that only knew about the
    adapter. A call site asking "is the adapter on?" must never be told
    yes while the app is driving the deck over USB."""
    app_settings._settings().setValue("mdrem_enabled", True)
    app_settings._settings().setValue("netmd_enabled", True)

    assert app_settings.netmd_enabled() is True
    assert app_settings.mdrem_enabled() is False


def test_the_recording_mode_defaults_to_sp():
    assert netmd.mode(app_settings.netmd_recording_mode()).key == netmd.MODE_SP


def test_the_recording_mode_round_trips():
    app_settings.set_netmd_recording_mode(netmd.MODE_LP4)
    assert app_settings.netmd_recording_mode() == netmd.MODE_LP4


def test_the_chosen_deck_round_trips():
    app_settings.set_netmd_device("MZ-N710")
    assert app_settings.netmd_device() == "MZ-N710"


# --- the Settings window --------------------------------------------------


def test_ticking_netmd_unticks_the_adapter_on_screen(qt_app):
    """Seen happening, not applied silently on OK: a user who ticks one
    while the other is on has to be able to tell that they traded."""
    app_settings.set_mdrem_enabled(True)
    dialog = SettingsDialog()
    assert dialog.mdrem_check.isChecked(), "precondition"

    dialog.netmd_check.setChecked(True)

    assert dialog.mdrem_check.isChecked() is False


def test_ticking_the_adapter_unticks_netmd_on_screen(qt_app):
    app_settings.set_netmd_enabled(True)
    dialog = SettingsDialog()
    assert dialog.netmd_check.isChecked(), "precondition"

    dialog.mdrem_check.setChecked(True)

    assert dialog.netmd_check.isChecked() is False


def test_the_netmd_rows_are_dead_until_it_is_switched_on(qt_app):
    dialog = SettingsDialog()

    assert dialog._netmd_device_widget.isEnabled() is False
    assert dialog._netmd_mode_widget.isEnabled() is False

    dialog.netmd_check.setChecked(True)

    assert dialog._netmd_device_widget.isEnabled() is True
    assert dialog._netmd_mode_widget.isEnabled() is True


def test_every_mode_is_offered_with_its_capacity(qt_app):
    dialog = SettingsDialog()

    keys = [dialog.netmd_mode_combo.itemData(i) for i in range(dialog.netmd_mode_combo.count())]
    assert keys == [netmd.MODE_SP, netmd.MODE_LP2, netmd.MODE_LP4]
    assert "80" in dialog.netmd_mode_combo.itemText(0)
    assert "320" in dialog.netmd_mode_combo.itemText(2)


def test_the_advice_follows_the_chosen_mode(qt_app):
    """The whole point of showing it here: which cables to plug in is
    decided by the mode, and getting it wrong costs a disc."""
    dialog = SettingsDialog()
    dialog.netmd_check.setChecked(True)

    dialog.netmd_mode_combo.setCurrentIndex(dialog.netmd_mode_combo.findData(netmd.MODE_SP))
    assert "optical" in dialog.netmd_advice_label.text().lower()

    dialog.netmd_mode_combo.setCurrentIndex(dialog.netmd_mode_combo.findData(netmd.MODE_LP2))
    assert "no optical cable" in dialog.netmd_advice_label.text().lower()


def test_ok_saves_the_mode_and_the_exclusion(qt_app):
    app_settings.set_mdrem_enabled(True)
    dialog = SettingsDialog()
    dialog.netmd_check.setChecked(True)
    dialog.netmd_mode_combo.setCurrentIndex(dialog.netmd_mode_combo.findData(netmd.MODE_LP2))

    dialog._on_accept()

    assert app_settings.netmd_enabled() is True
    assert app_settings.mdrem_enabled() is False
    assert app_settings.netmd_recording_mode() == netmd.MODE_LP2


def test_ok_with_neither_ticked_leaves_both_off(qt_app):
    """The setters each switch the other off, so the one written last
    would win on its own -- the checkboxes have to decide instead."""
    app_settings.set_netmd_enabled(True)
    dialog = SettingsDialog()
    dialog.netmd_check.setChecked(False)
    dialog.mdrem_check.setChecked(False)

    dialog._on_accept()

    assert app_settings.netmd_enabled() is False
    assert app_settings.mdrem_enabled() is False


def test_ok_can_switch_back_to_the_adapter(qt_app):
    app_settings.set_netmd_enabled(True)
    dialog = SettingsDialog()
    dialog.mdrem_check.setChecked(True)

    dialog._on_accept()

    assert app_settings.mdrem_enabled() is True
    assert app_settings.netmd_enabled() is False


def test_detect_explains_a_deck_that_does_not_answer(qt_app, monkeypatch):
    """Reported as identical from here whether the deck is unplugged, off,
    or bound to Sony's driver instead of WinUSB -- so the message has to
    name all three rather than claim to know which."""
    from mdtools.panels import settings_dialog as module

    said: list[str] = []
    monkeypatch.setattr(
        module.QMessageBox, "information", staticmethod(lambda *a, **k: said.append(a[2]))
    )
    monkeypatch.setattr(
        module.netmd, "read_disc", lambda: (_ for _ in ()).throw(netmd.NetMdError("no NetMD device found"))
    )
    dialog = SettingsDialog()

    dialog._detect_netmd()

    assert said
    assert "WinUSB" in said[0]


def test_detect_remembers_the_deck_that_answered(qt_app, monkeypatch):
    from mdtools.panels import settings_dialog as module

    monkeypatch.setattr(module.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(
        module.netmd,
        "read_disc",
        lambda: netmd.NetMdDisc(title="Night Ferry", tracks=[netmd.NetMdTrack(number=1)]),
    )
    dialog = SettingsDialog()

    dialog._detect_netmd()

    assert dialog.selected_netmd_device() == "Night Ferry"
