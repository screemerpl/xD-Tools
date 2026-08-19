"""The Recording menu shows what applies to the project in front of you.

A MiniDisc project has no use for "Burn Audio CD", and a CD project none
for the deck's remote or for erasing an MD. This is a deliberate change of
principle rather than tidying: erasing, the remote and the record entries
all act on whatever disc is physically in the deck, which has nothing to do
with which label is open -- and that independence was itself deliberate
once. It loses to a menu that matches the project.
"""

import pytest

from mdtools import app_settings
from mdtools.app_window import MainWindow
from mdtools.project import MEDIUM_CD, MEDIUM_MD


@pytest.fixture
def window(qt_app, monkeypatch):
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: True)
    win = MainWindow(show_startup_dialog=False)
    return win


def _visible(win) -> dict[str, bool]:
    return {
        "record": win.record_action.isVisible(),
        "record_cd": win.record_cd_action.isVisible(),
        "record_folder": win.record_folder_action.isVisible(),
        "erase": win.erase_disc_action.isVisible(),
        "remote": win.remote_action.isVisible(),
        "burn_folder": win.burn_folder_action.isVisible(),
        "burn_foobar": win.burn_foobar_action.isVisible(),
    }


def test_a_minidisc_project_is_not_offered_cd_burning(window):
    window.project.medium = MEDIUM_MD
    window._sync_mdrem_actions()

    state = _visible(window)
    assert state["record"] and state["erase"] and state["remote"]
    assert not state["burn_folder"] and not state["burn_foobar"]


def test_a_cd_project_is_not_offered_the_deck(window):
    window.project.medium = MEDIUM_CD
    window._sync_mdrem_actions()

    state = _visible(window)
    assert state["burn_folder"] and state["burn_foobar"]
    assert not any(state[name] for name in ("record", "record_cd", "record_folder", "erase", "remote"))


def test_burning_does_not_disappear_with_the_adapter(window, monkeypatch):
    """It needs the drive, not the infrared adapter -- the trap that made
    the Telegram entry worth a note of its own."""
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: False)
    window.project.medium = MEDIUM_CD
    window._sync_mdrem_actions()

    assert window.burn_folder_action.isVisible()
    assert window.burn_foobar_action.isVisible()


def test_without_an_adapter_a_minidisc_project_keeps_only_what_works(window, monkeypatch):
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: False)
    window.project.medium = MEDIUM_MD
    window._sync_mdrem_actions()

    assert not any(_visible(window).values())


def test_with_no_project_nothing_is_hidden_for_the_medium(window):
    """Only reachable before the startup screen has been answered: there is
    no medium to follow yet."""
    window.project = None
    window._sync_mdrem_actions()

    assert all(_visible(window).values())


def test_opening_a_project_of_the_other_medium_re_syncs_the_menu(window, tmp_path):
    from mdtools.io.project_io import save_project

    window.project.medium = MEDIUM_CD
    path = tmp_path / "cd.mdproj"
    save_project(window.project, path)

    window.project.medium = MEDIUM_MD
    window._sync_mdrem_actions()
    assert window.record_action.isVisible()

    assert window._open_project_path(str(path)) is True

    assert window.burn_folder_action.isVisible()
    assert not window.record_action.isVisible()


# --- the page switcher ---------------------------------------------------


def test_the_second_page_is_not_called_a_j_card_on_a_cd_project(window):
    from mdtools.project import PAGE_COVER

    window.project.medium = MEDIUM_CD
    window._sync_mdrem_actions()
    index = window.page_combo.findData(PAGE_COVER)

    assert "J-Card" not in window.page_combo.itemText(index)

    window.project.medium = MEDIUM_MD
    window._sync_mdrem_actions()

    assert "J-Card" in window.page_combo.itemText(index)


# --- the Experimental menu ----------------------------------------------


def test_the_telegram_hand_offs_follow_the_medium_as_well(window, monkeypatch):
    """They are the same two operations as the Recording menu's, reached
    from somewhere else -- reported as not changing with the medium."""
    window.project.medium = MEDIUM_MD
    window._sync_mdrem_actions()
    assert window.telegram_record_action.isVisible()
    assert not window.telegram_burn_action.isVisible()

    window.project.medium = MEDIUM_CD
    window._sync_mdrem_actions()
    assert not window.telegram_record_action.isVisible()
    assert window.telegram_burn_action.isVisible()


def test_burning_telegram_downloads_survives_the_adapter_being_off(window, monkeypatch):
    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: False)
    window.project.medium = MEDIUM_CD
    window._sync_mdrem_actions()

    assert window.telegram_burn_action.isVisible()


# --- dialogs that belong to one medium ----------------------------------


def test_a_cd_project_is_not_offered_infrared_titling(qt_app, monkeypatch):
    """"Upload Tracklist" writes titles onto a MiniDisc over infrared. On a
    CD project there is no MiniDisc to write to, and the titles went on as
    CD-Text when the disc was burned -- reported as still being offered."""
    from mdtools.panels.metadata_dialog import MetadataDialog
    from mdtools.project import ProjectMetadata

    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: True)
    metadata = ProjectMetadata(album="Album", artist="Artist")

    on_md = MetadataDialog(metadata, medium=MEDIUM_MD)
    on_cd = MetadataDialog(metadata, medium=MEDIUM_CD)

    assert on_md.upload_btn.isVisibleTo(on_md) is True
    assert on_cd.upload_btn.isVisibleTo(on_cd) is False


def test_the_about_box_describes_both_media(qt_app):
    from mdtools.panels.about_dialog import AboutDialog
    from PySide6.QtWidgets import QLabel

    # kept in a variable: an inline AboutDialog() is collected on the spot,
    # taking its labels with it (see the PySide gotchas in CLAUDE.md)
    dialog = AboutDialog()
    texts = " ".join(label.text() for label in dialog.findChildren(QLabel))

    assert "CD-R" in texts and "MiniDisc" in texts
    assert "CD-Text" in texts
