"""TelegramLoginDialog: the phone -> code -> (optional) password wizard.

Two layers of coverage, same split test_mdrem_ui.py uses for
MDRemUploadDialog: a fast, purely synchronous check that reject() never
blocks the GUI thread on a busy worker (a fake `_worker`-shaped object,
no real thread involved), and slower end-to-end tests that start a real
_LoginWorker QThread against a fake Telethon-shaped client and pump the Qt
event loop until its signals arrive -- proving the actual cross-thread
asyncio.Queue handoff (submit_code/submit_password/cancel) works, not just
the dialog's own state machine in isolation.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtWidgets import QApplication

from mdtools.panels import telegram_login_dialog as module
from mdtools.panels.telegram_login_dialog import TelegramLoginDialog
from tests.test_telegram_bot import FakeTelethonClient


def _pump_until(condition, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for the worker thread")
        QApplication.processEvents()
        time.sleep(0.01)


def _use_fake_client(monkeypatch, fake: FakeTelethonClient) -> None:
    monkeypatch.setattr(module.telegram_bot, "create_telethon_client", lambda *a, **k: fake)


# --- initial state / validation, no worker involved --------------------------


def test_dialog_starts_on_the_phone_stage(qt_app):
    dialog = TelegramLoginDialog("123456", "hash")
    assert dialog._stage == "phone"
    assert dialog._form.isRowVisible(dialog.code_edit) is False
    assert dialog._form.isRowVisible(dialog.password_edit) is False
    assert dialog.primary_btn.text() == "Send Code"


def test_missing_api_id_or_hash_refuses_to_start(qt_app):
    dialog = TelegramLoginDialog("", "")
    dialog.phone_edit.setText("+15550100")

    dialog._on_primary_clicked()

    assert dialog._worker is None
    assert "API ID and API Hash" in dialog.status_label.text()


def test_empty_phone_refuses_to_start(qt_app):
    dialog = TelegramLoginDialog("123456", "hash")

    dialog._on_primary_clicked()

    assert dialog._worker is None
    assert "phone number" in dialog.status_label.text()


def test_non_numeric_api_id_refuses_to_start(qt_app):
    dialog = TelegramLoginDialog("not-a-number", "hash")
    dialog.phone_edit.setText("+15550100")

    dialog._on_primary_clicked()

    assert dialog._worker is None
    assert "must be a number" in dialog.status_label.text()


# --- reject() must never block on a busy worker -------------------------------


def test_stopping_does_not_block_on_the_worker(qt_app):
    """Same failure mode MDRemUploadDialog's reject() once had: calling
    worker.wait() from the GUI thread freezes the whole window until the
    worker happens to finish on its own."""
    dialog = TelegramLoginDialog("123456", "hash")

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


# --- end to end, a real _LoginWorker QThread ----------------------------------


def test_end_to_end_sign_in_with_no_password_needed(qt_app, monkeypatch):
    fake = FakeTelethonClient(valid_code="42")
    _use_fake_client(monkeypatch, fake)
    dialog = TelegramLoginDialog("123456", "hash")
    dialog.phone_edit.setText("+15550100")

    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._stage == "code")
    assert "code" in dialog.status_label.text().lower()

    dialog.code_edit.setText("42")
    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._worker is None)

    assert "Signed in as Jane Doe" in dialog.status_label.text()
    assert fake.authorized is True


def test_end_to_end_sign_in_with_two_factor_password(qt_app, monkeypatch):
    fake = FakeTelethonClient(valid_code="42", needs_password=True, password="hunter2")
    _use_fake_client(monkeypatch, fake)
    dialog = TelegramLoginDialog("123456", "hash")
    dialog.phone_edit.setText("+15550100")

    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._stage == "code")

    dialog.code_edit.setText("42")
    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._stage == "password")
    assert "two-factor" in dialog.status_label.text().lower()

    dialog.password_edit.setText("hunter2")
    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._worker is None)

    assert "Signed in as Jane Doe" in dialog.status_label.text()
    assert fake.password_verified is True


def test_end_to_end_already_authorized_skips_straight_to_signed_in(qt_app, monkeypatch):
    fake = FakeTelethonClient(authorized=True)
    _use_fake_client(monkeypatch, fake)
    dialog = TelegramLoginDialog("123456", "hash")
    dialog.phone_edit.setText("+15550100")

    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._worker is None)

    assert "Already signed in as Jane Doe" in dialog.status_label.text()
    assert fake.code_requests == []


def test_end_to_end_a_wrong_code_reports_failure_and_resets_to_phone(qt_app, monkeypatch):
    fake = FakeTelethonClient(valid_code="42")
    _use_fake_client(monkeypatch, fake)
    dialog = TelegramLoginDialog("123456", "hash")
    dialog.phone_edit.setText("+15550100")

    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._stage == "code")

    dialog.code_edit.setText("wrong")
    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._worker is None)

    assert "Sign-in failed" in dialog.status_label.text()
    assert dialog._stage == "phone"


def test_end_to_end_cancelling_during_code_entry_stops_the_worker(qt_app, monkeypatch):
    fake = FakeTelethonClient(valid_code="42")
    _use_fake_client(monkeypatch, fake)
    dialog = TelegramLoginDialog("123456", "hash")
    dialog.phone_edit.setText("+15550100")
    dialog.show()

    dialog._on_primary_clicked()
    _pump_until(lambda: dialog._stage == "code")

    dialog.reject()
    assert dialog._closing

    _pump_until(lambda: dialog.isHidden())
    assert fake.disconnected is True
