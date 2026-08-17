from mdtools.app_window import MainWindow


def test_docks_expose_a_toggle_view_action(qt_app):
    win = MainWindow(show_startup_dialog=False)

    for dock in (win.tool_dock, win.properties_dock, win.layers_dock):
        action = dock.toggleViewAction()
        assert action is not None
        assert action.isCheckable()
        assert action.text() == dock.windowTitle()


def test_tools_dock_is_no_wider_than_its_buttons_need(qt_app):
    """Regression test: QMainWindow's dock layout otherwise allocates the
    Tools dock a chunk of the window's width unrelated to its actual
    content -- a narrow column of small icon-only buttons ended up with a
    lot of dead space beside it, reported as "the toolbar itself is a bit
    too wide"."""
    win = MainWindow(show_startup_dialog=False)
    win.show()

    expected = win.tool_panel.sizeHint().width()
    assert win.tool_dock.maximumWidth() == expected
    assert win.tool_dock.width() == expected


def test_toggle_view_action_recovers_a_closed_dock(qt_app):
    win = MainWindow(show_startup_dialog=False)
    win.show()  # isVisible() reflects the whole ancestor chain -- an unshown
    # top-level window would make every dock report invisible regardless of
    # its own state, so this test needs a genuinely shown window.

    win.properties_dock.close()  # simulates the user clicking the dock's own close button
    assert not win.properties_dock.isVisible()
    assert not win.properties_dock.toggleViewAction().isChecked()

    win.properties_dock.toggleViewAction().trigger()

    assert win.properties_dock.isVisible()
    assert win.properties_dock.toggleViewAction().isChecked()
