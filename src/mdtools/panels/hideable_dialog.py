"""Running a modal operation dialog that can be *hidden* while it keeps
working -- the "Hide" button behind #27's bottom-of-window progress bar.

**The problem this exists for.** `QDialog.hide()`, called from inside
that dialog's own `exec()`, makes `exec()` **return** -- Qt's
`QDialog::setVisible(false)` explicitly exits the modal event loop
`exec()` is sitting in. It does not call `done()`, so no result is set
and no `finished` signal is emitted: the call site simply gets 0
(`Rejected`) back, exactly as though the user had cancelled.

That was shipped once and reported immediately: clicking Hide during a
CD rip made the whole rip window disappear along with the progress bar
in the main window (its call site's own `finally` released it), while
cd-paranoia carried on ripping in a worker thread nobody could reach any
more. Verified directly against this project's own PySide6 -- `exec()`
returned before a 100 ms timer scheduled at the same moment as the
`hide()` could fire, with the parent window still visible throughout.

**What this does instead.** `exec_hideable()` runs `exec()` in a loop.
When `exec()` returns because the dialog deliberately hid itself (which
is what `hide_for_background()` marks), a plain, *non-modal* nested
`QEventLoop` takes over: the main window becomes usable (nothing modal
is visible any more), the dialog's worker thread carries on untouched,
and its signals keep being delivered because the application's own event
loop is still turning. That wait ends one of two ways -- the user asks
for the dialog back (`request_show()`, from the progress bar's own "Show
recording window" button), which re-enters `exec()`; or the operation
finishes on its own and the dialog calls `accept()`/`reject()`, whose
`done()` emits `finished` and gives this function the real result to
return.

The call site therefore stays exactly as linear as it was with a plain
`exec()` -- it blocks until the operation genuinely ends, and never sees
a Hide at all. That is what makes this usable both from `app_window.py`
and from *inside* `RecordDialog`, which `exec()`s a nested
`MDRemUploadDialog` of its own for titling.
"""

from __future__ import annotations

from PySide6.QtCore import QEventLoop


def hide_for_background(dialog) -> None:
    """The Hide button's own handler: marks the hide as deliberate (so
    `exec_hideable()` knows this is not a cancel), hides, and says so for
    the main window's progress bar to show its "Show recording window"
    button."""
    dialog.hidden_for_background = True
    dialog.hide()
    dialog.visibility_changed.emit(True)


def close_hides_while_busy(dialog, event) -> bool:
    """The window's own X, while its work is in flight, means "get this
    window out of my way" -- not "throw the work away".

    This replaced a **Hide** button on every one of these dialogs. The
    button said what it did, but it sat in a row of other buttons on six
    separate windows and duplicated something the title bar already
    offers on every window on the desktop; closing a window whose work
    carries on regardless is what minimising to a background task looks
    like everywhere else.

    Only while busy. With nothing running there is nothing to keep
    alive, so X keeps its ordinary meaning and closes the dialog -- being
    unable to shut an idle window with its own X would be far more
    surprising than the hiding is.

    Returns True when the close has been turned into a hide, so a
    dialog's own closeEvent can hand back immediately; False means "this
    is an ordinary close, carry on".
    """
    if not dialog.is_busy():
        return False
    # Ignore first: hide() makes a running exec() return (the whole
    # reason exec_hideable() exists), and there is no reason to leave
    # the event unanswered across that.
    event.ignore()
    hide_for_background(dialog)
    return True


def surface(dialog) -> None:
    """Bring a dialog back if it is hidden, *before* it asks the user
    something.

    A QMessageBox is its own top-level window, so it appears whether or
    not the dialog that parented it is visible -- which means a hidden
    recording could otherwise pop up "put the next disc in" with no
    window behind it to explain where it came from. Anything a hidden
    operation can prompt with mid-run calls this first.

    The window is put up here and now, not merely requested: asking
    exec_hideable() to re-enter exec() only takes effect once control
    returns to its wait loop, which is *after* the message box the caller
    is about to open. request_show() still follows, so that when control
    does return, the dialog goes back to being properly modal rather than
    left visible with no loop of its own."""
    if not dialog.isHidden():
        return
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    dialog.visibility_changed.emit(False)
    dialog.request_show()


def exec_hideable(dialog) -> int:
    """`dialog.exec()`, but surviving its Hide button -- see the module
    docstring. Returns the dialog's real result code, only once the
    operation has actually ended.

    Falls back to a plain `exec()` for anything without the two
    attributes this needs (`hidden_for_background`, `show_requested`),
    so a test's own stand-in dialog needs no extra machinery."""
    if not hasattr(dialog, "show_requested"):
        return dialog.exec()

    while True:
        result = dialog.exec()
        if not getattr(dialog, "hidden_for_background", False):
            return result
        dialog.hidden_for_background = False

        # Nothing modal is visible now, so this nested loop leaves the
        # main window fully usable -- which is the whole point of Hide.
        loop = QEventLoop()
        outcome: list[int] = []

        def _on_finished(code: int) -> None:
            outcome.append(code)
            loop.quit()

        dialog.finished.connect(_on_finished)
        dialog.show_requested.connect(loop.quit)
        try:
            loop.exec()
        finally:
            dialog.finished.disconnect(_on_finished)
            dialog.show_requested.disconnect(loop.quit)

        if outcome:
            # It finished while hidden (a worker's own accept(), say) --
            # that result is the real one, and there is nothing left to
            # re-show.
            return outcome[0]
        # Otherwise it was asked for back: say so before rounding again
        # into exec(), which shows it modally once more. Announcing it
        # here rather than at whichever button asked means every route
        # back -- the progress bar's own button, and surface() bringing a
        # dialog up to ask the user something -- keeps MainWindow and its
        # bar in step for free.
        dialog.visibility_changed.emit(False)
