"""NetMdRemoteDialog -- the NetMD counterpart to RemoteDialog, and
open_remote_control() (remote_dialog.py), which is what picks between the
two now that "Remote Control..." is one entry point for either machine.

No deck, no subprocess: every netmd.py function this dialog calls is
monkeypatched at the module-function level, the same pattern the other
NetMD test files use.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

from mdtools import app_settings, netmd
from mdtools.panels import netmd_remote_dialog as netmd_remote_module
from mdtools.panels import remote_dialog as remote_module
from mdtools.panels.netmd_remote_dialog import NetMdRemoteDialog


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setattr(netmd, "missing_tools", lambda: [])
    monkeypatch.setattr(
        netmd,
        "read_disc",
        lambda: netmd.NetMdDisc(title="Night Ferry", tracks=[netmd.NetMdTrack(number=1, title="One")]),
    )


# --- status on open ---------------------------------------------------


def test_a_connected_deck_shows_its_disc(qt_app, connected):
    dialog = NetMdRemoteDialog(None)
    assert "Night Ferry" in dialog.status_label.text()
    assert dialog.track_spin.maximum() == 1


def test_no_device_says_not_connected(qt_app, monkeypatch):
    monkeypatch.setattr(netmd, "missing_tools", lambda: [])
    monkeypatch.setattr(netmd, "read_disc", lambda: (_ for _ in ()).throw(netmd.NetMdError("no NetMD device found")))

    dialog = NetMdRemoteDialog(None)

    assert "Not connected" in dialog.status_label.text()
    assert "no NetMD device found" in dialog.status_label.text()


def test_a_missing_tool_is_reported_without_trying_to_read_a_disc(qt_app, monkeypatch):
    monkeypatch.setattr(netmd, "missing_tools", lambda: ["netmdcli"])
    monkeypatch.setattr(
        netmd, "read_disc", lambda: pytest.fail("must not read a disc when the tool itself is missing")
    )

    dialog = NetMdRemoteDialog(None)

    assert "netmdcli" in dialog.status_label.text()


# --- every button reaches the right netmd.py function -------------------


def test_every_transport_button_calls_its_own_function(qt_app, connected, monkeypatch):
    calls = []
    for name in ("play", "pause", "stop", "fast_forward", "rewind", "next_track", "previous_track", "restart_track"):
        monkeypatch.setattr(netmd, name, lambda *a, _n=name: calls.append(_n))

    dialog = NetMdRemoteDialog(None)
    dialog._play()
    dialog._pause()
    dialog._stop()
    dialog._fast_forward()
    dialog._rewind()
    dialog._next()
    dialog._previous()
    dialog._restart()

    assert calls == [
        "play",
        "pause",
        "stop",
        "fast_forward",
        "rewind",
        "next_track",
        "previous_track",
        "restart_track",
    ]
    assert "Done: Restart track" in dialog.status_label.text()


def test_play_a_track_passes_the_spin_boxs_value(qt_app, connected, monkeypatch):
    seen = []
    monkeypatch.setattr(netmd, "play", lambda track=None: seen.append(track))
    dialog = NetMdRemoteDialog(None)
    dialog.track_spin.setValue(1)

    dialog._play_track()

    assert seen == [1]


def test_set_play_mode_sends_the_combos_own_data(qt_app, connected, monkeypatch):
    seen = []
    monkeypatch.setattr(netmd, "set_play_mode", lambda mode: seen.append(mode))
    dialog = NetMdRemoteDialog(None)
    dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("shuffle"))

    dialog._set_play_mode()

    assert seen == ["shuffle"]


def test_a_refused_command_is_shown_not_swallowed(qt_app, connected, monkeypatch):
    monkeypatch.setattr(netmd, "play", lambda *a, **k: (_ for _ in ()).throw(netmd.NetMdError("no NetMD device found")))
    dialog = NetMdRemoteDialog(None)

    dialog._play()

    assert "failed" in dialog.status_label.text().lower()
    assert "no NetMD device found" in dialog.status_label.text()


# --- there is no Eject button: netmdcli has no such command --------------


def test_there_is_no_eject_button(qt_app, connected):
    from PySide6.QtWidgets import QPushButton

    dialog = NetMdRemoteDialog(None)
    labels = [button.text() for button in dialog.findChildren(QPushButton)]
    assert not any("eject" in label.lower() for label in labels)


# --- open_remote_control() picks the right dialog ------------------------


def test_netmd_enabled_opens_the_netmd_remote(qt_app, monkeypatch):
    app_settings.set_netmd_enabled(True)
    opened = []
    monkeypatch.setattr(
        remote_module,
        "NetMdRemoteDialog",
        lambda parent=None: opened.append(True) or _AlwaysAccepts(),
    )
    monkeypatch.setattr(
        remote_module, "resolve_port", lambda *a, **k: pytest.fail("must not resolve an MDRem port for NetMD")
    )

    remote_module.open_remote_control(None)

    assert opened == [True]


def test_mdrem_enabled_still_opens_the_mdrem_remote(qt_app, monkeypatch):
    app_settings.set_mdrem_enabled(True)
    monkeypatch.setattr(remote_module, "resolve_port", lambda parent: "COM_TEST")
    opened = []

    class _FakeRemote:
        def __init__(self, port, parent=None):
            opened.append(port)

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(remote_module, "RemoteDialog", _FakeRemote)

    remote_module.open_remote_control(None)

    assert opened == ["COM_TEST"]


class _AlwaysAccepts:
    def exec(self):
        return QDialog.DialogCode.Accepted
