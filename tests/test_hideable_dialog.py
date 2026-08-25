"""exec_hideable() -- the thing that makes the Hide button survivable.

The bug this is all about, reproduced first below: QDialog.hide() from
inside that dialog's own exec() makes exec() RETURN (Qt exits the modal
event loop on setVisible(False)), with no result and no finished signal.
Shipped once and reported immediately -- Hide during a CD rip took the
whole rip window and the main window's progress bar with it, while
cd-paranoia carried on ripping in a worker nobody could reach any more.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QDialog

from mdtools.panels.hideable_dialog import exec_hideable, hide_for_background, surface


class _Dialog(QDialog):
    """The shape every real operation dialog now has -- see
    cd_rip_dialog.py and friends."""

    visibility_changed = Signal(bool)
    show_requested = Signal()

    def __init__(self):
        super().__init__()
        self.hidden_for_background = False

    def request_show(self) -> None:
        self.show_requested.emit()


def test_a_plain_hide_really_does_end_exec(qt_app):
    """The Qt behaviour this module exists to work around -- asserted
    directly, so nobody has to take the docstring's word for it."""
    dialog = _Dialog()
    QTimer.singleShot(0, dialog.hide)

    result = dialog.exec()

    # exec() returned, without done() ever having been called: no result
    # was set and nothing was accepted or rejected on purpose.
    assert result == QDialog.DialogCode.Rejected
    assert not dialog.isVisible()


def test_hiding_for_background_does_not_end_exec_hideable(qt_app):
    """The fix: the same hide, through exec_hideable(), leaves the
    operation running instead of reporting a cancel."""
    dialog = _Dialog()
    returned: list[int] = []

    def hide_it():
        hide_for_background(dialog)
        # If exec_hideable() were as broken as a plain exec(), it would
        # have returned by now.
        QTimer.singleShot(0, check_still_waiting)

    def check_still_waiting():
        assert returned == [], "exec_hideable() returned on a Hide -- the bug is back"
        assert not dialog.isVisible()
        dialog.accept()  # the operation finishes on its own, while hidden

    QTimer.singleShot(0, hide_it)
    returned.append(exec_hideable(dialog))

    assert returned == [QDialog.DialogCode.Accepted]


def test_the_dialog_can_be_asked_back_and_then_finish_normally(qt_app):
    """Hide, then "Show recording window", then a real close -- the
    result the call site gets is the real one, from the end."""
    dialog = _Dialog()
    seen: list[str] = []

    def hide_it():
        hide_for_background(dialog)
        QTimer.singleShot(0, show_it)

    def show_it():
        seen.append("hidden")
        assert not dialog.isVisible()
        dialog.request_show()
        QTimer.singleShot(0, finish_it)

    def finish_it():
        seen.append("shown")
        assert dialog.isVisible(), "request_show() did not bring it back"
        dialog.accept()

    QTimer.singleShot(0, hide_it)
    result = exec_hideable(dialog)

    assert seen == ["hidden", "shown"]
    assert result == QDialog.DialogCode.Accepted


def test_coming_back_is_announced_so_the_bar_can_follow(qt_app):
    """MainWindow puts its "Show recording window" button away (and
    clears its own hidden flag) off this, rather than at whichever button
    asked -- so every route back, including surface() bringing a dialog
    up to ask the user something, keeps them in step."""
    dialog = _Dialog()
    seen: list[bool] = []
    dialog.visibility_changed.connect(seen.append)

    def hide_it():
        hide_for_background(dialog)
        QTimer.singleShot(0, show_it)

    def show_it():
        dialog.request_show()
        QTimer.singleShot(0, dialog.accept)

    QTimer.singleShot(0, hide_it)
    exec_hideable(dialog)

    assert seen == [True, False]


def test_surface_puts_a_hidden_dialog_up_before_it_asks_anything(qt_app):
    """A QMessageBox is its own window and shows whether or not its
    parent does -- so a hidden recording could otherwise ask "put the
    next disc in" with nothing behind it. surface() has to make the
    dialog visible *there and then*, not merely request it: the request
    only lands once control is back in exec_hideable's wait loop, which
    is after the caller's message box has already opened."""
    dialog = _Dialog()
    seen: list[bool] = []
    dialog.visibility_changed.connect(seen.append)

    def hide_then_ask():
        hide_for_background(dialog)
        assert dialog.isHidden()
        # Standing in for "about to open a QMessageBox".
        surface(dialog)
        assert not dialog.isHidden(), "surface() left the dialog hidden"
        QTimer.singleShot(0, dialog.accept)

    QTimer.singleShot(0, hide_then_ask)
    exec_hideable(dialog)

    assert seen[0] is True and seen[1] is False


def test_surface_leaves_a_visible_dialog_alone(qt_app):
    dialog = _Dialog()
    seen: list = []
    dialog.visibility_changed.connect(seen.append)

    def check():
        surface(dialog)
        assert seen == []
        dialog.accept()

    QTimer.singleShot(0, check)
    exec_hideable(dialog)


def test_an_ordinary_close_is_unchanged(qt_app):
    """Nothing about the no-Hide path may have moved: a straight
    accept()/reject() still returns immediately, exactly as exec() did."""
    dialog = _Dialog()
    QTimer.singleShot(0, dialog.reject)
    assert exec_hideable(dialog) == QDialog.DialogCode.Rejected

    other = _Dialog()
    QTimer.singleShot(0, other.accept)
    assert exec_hideable(other) == QDialog.DialogCode.Accepted


def test_hide_for_background_says_so_for_the_progress_bar(qt_app):
    dialog = _Dialog()
    seen: list[bool] = []
    dialog.visibility_changed.connect(seen.append)

    hide_for_background(dialog)

    assert seen == [True]
    assert dialog.hidden_for_background is True
    assert not dialog.isVisible()


def test_a_dialog_without_the_contract_falls_back_to_plain_exec(qt_app):
    """A test's own stand-in dialog needs no extra machinery -- see
    exec_hideable()'s own docstring."""
    plain = QDialog()
    QTimer.singleShot(0, plain.accept)
    assert exec_hideable(plain) == QDialog.DialogCode.Accepted
