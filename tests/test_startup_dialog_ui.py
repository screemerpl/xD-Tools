from mdtools.panels import startup_dialog as startup_dialog_module
from mdtools.panels.startup_dialog import StartupDialog


def test_empty_recent_list_shows_a_disabled_placeholder_and_disables_open(qt_app):
    dialog = StartupDialog([])

    assert dialog.list_widget.count() == 1
    assert not dialog.open_btn.isEnabled()


def test_open_selected_accepts_with_the_currently_selected_recent_path(qt_app):
    dialog = StartupDialog(["/some/path/album.mdproj", "/other/path/second.mdproj"])
    assert dialog.open_btn.isEnabled()

    dialog.list_widget.setCurrentRow(1)
    dialog._open_selected()

    assert dialog.result_path == "/other/path/second.mdproj"


def test_double_clicking_a_recent_item_opens_it(qt_app):
    dialog = StartupDialog(["/some/path/album.mdproj"])
    item = dialog.list_widget.item(0)

    dialog._open_item(item)

    assert dialog.result_path == "/some/path/album.mdproj"


def test_new_project_button_accepts_with_no_path(qt_app):
    dialog = StartupDialog(["/some/path/album.mdproj"])

    dialog._new_project()

    assert dialog.result_path is None


def test_browse_accepts_with_the_chosen_path(qt_app, monkeypatch, tmp_path):
    chosen = tmp_path / "picked.mdproj"
    monkeypatch.setattr(
        startup_dialog_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(chosen), ""))
    )

    dialog = StartupDialog([])
    dialog._browse()

    assert dialog.result_path == str(chosen)


def test_cancelling_browse_leaves_result_path_unset(qt_app, monkeypatch):
    monkeypatch.setattr(
        startup_dialog_module.QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: ("", ""))
    )

    dialog = StartupDialog([])
    dialog._browse()

    assert dialog.result_path is None


def test_multiprint_button_opens_multiprint_dialog_without_closing_the_startup_dialog(qt_app, monkeypatch):
    """Multiprint is a standalone side-trip, not one of the "what should
    the main window do next" outcomes -- it must not set result_path or
    accept()/reject() this dialog, so the user lands back on the startup
    screen once the (here: faked) MultiprintDialog closes."""
    opened = []

    class _FakeMultiprintDialog:
        def __init__(self, parent=None):
            opened.append(parent)

        def exec(self):
            opened.append("exec")

    monkeypatch.setattr(startup_dialog_module, "MultiprintDialog", _FakeMultiprintDialog)

    dialog = StartupDialog([])
    dialog._open_multiprint()

    assert opened == [dialog, "exec"]
    assert dialog.result_path is None
    assert dialog.result() == 0  # neither accept() nor reject() was called
