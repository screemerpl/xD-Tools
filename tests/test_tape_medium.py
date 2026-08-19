"""A cassette project: three pages, none of them a disc.

The medium that broke the "a project is a disc label and a cover"
assumption for good -- a cassette has no disc page at all, and two of its
three pages are the same sticker printed twice with different halves of the
album on them.
"""

import copy
import io

import pytest
from PIL import Image

from mdtools.app_window import TAPE_JCARD_TEMPLATE, TAPE_LABEL_TEMPLATE, MainWindow
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.project import (
    MEDIUM_MD,
    MEDIUM_TAPE,
    PAGE_COVER,
    PAGE_DISC,
    PAGE_SIDE_A,
    PAGE_SIDE_B,
    ProjectMetadata,
    Track,
    medium_pages,
    page_title,
)
from mdtools.templates import registry


@pytest.fixture(autouse=True)
def _isolated_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def _metadata() -> ProjectMetadata:
    out = io.BytesIO()
    Image.new("RGB", (240, 240), (30, 70, 40)).save(out, format="PNG")
    return ProjectMetadata(
        album="Unleashed",
        artist="Skillet",
        year=2016,
        tracks=[Track(title=f"Track {i}", time_seconds=200) for i in range(1, 9)],
        cover_art=out.getvalue(),
    )


def _tape_window() -> MainWindow:
    templates = registry.load_templates()
    window = MainWindow(show_startup_dialog=False)
    window.project.medium = MEDIUM_TAPE
    jcard = next(t for t in templates["cover"] if t.name == TAPE_JCARD_TEMPLATE)
    label = next(t for t in templates["label"] if t.name == TAPE_LABEL_TEMPLATE)
    window.apply_template(PAGE_COVER, copy.deepcopy(jcard))
    del window.project.pages[PAGE_DISC]
    for page in (PAGE_SIDE_A, PAGE_SIDE_B):
        window.project.pages[page] = window.project.pages[PAGE_COVER].__class__(copy.deepcopy(label))
    window.current_page = PAGE_COVER
    window._refresh_page_combo()
    return window


# -- the medium ----------------------------------------------------------


def test_a_cassette_has_a_j_card_and_a_label_per_side_and_no_disc():
    pages = [entry.page for entry in medium_pages(MEDIUM_TAPE)]

    assert pages == [PAGE_COVER, PAGE_SIDE_A, PAGE_SIDE_B]
    assert PAGE_DISC not in pages
    assert all(not entry.optional for entry in medium_pages(MEDIUM_TAPE))


def test_the_side_pages_are_named_for_the_side_they_label(qt_app):
    assert page_title(PAGE_SIDE_A, MEDIUM_TAPE) != page_title(PAGE_SIDE_B, MEDIUM_TAPE)
    assert "A" in page_title(PAGE_SIDE_A, MEDIUM_TAPE)
    assert "B" in page_title(PAGE_SIDE_B, MEDIUM_TAPE)


# -- choosing it ---------------------------------------------------------


def test_the_new_project_dialog_offers_a_row_per_cassette_page(qt_app):
    dialog = NewDesignDialog()

    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_TAPE))
    dialog._on_accept()

    assert set(dialog.selected_templates) == {PAGE_COVER, PAGE_SIDE_A, PAGE_SIDE_B}
    assert dialog.selected_templates[PAGE_COVER].name == TAPE_JCARD_TEMPLATE


def test_the_disc_row_is_hidden_for_a_medium_that_has_no_disc(qt_app):
    dialog = NewDesignDialog()

    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_MD))
    assert dialog.disc_combo.isVisibleTo(dialog)

    dialog.medium_combo.setCurrentIndex(dialog.medium_combo.findData(MEDIUM_TAPE))
    assert not dialog.disc_combo.isVisibleTo(dialog)


def test_creating_a_cassette_project_gives_it_exactly_those_three_pages(qt_app, monkeypatch):
    def fake_exec(self):
        self.medium_combo.setCurrentIndex(self.medium_combo.findData(MEDIUM_TAPE))
        self._on_accept()
        return NewDesignDialog.DialogCode.Accepted

    monkeypatch.setattr(NewDesignDialog, "exec", fake_exec)
    window = MainWindow(show_startup_dialog=False)

    assert window._new_design(prompt=True) is True

    assert window.project.medium == MEDIUM_TAPE
    assert window.project.ordered_pages() == [PAGE_COVER, PAGE_SIDE_A, PAGE_SIDE_B]
    # no MiniDisc insertion mark anywhere: that belongs to a disc page
    for scene in window.project.pages.values():
        assert scene.print_items() == []


def test_the_suggested_filename_says_which_machine_it_is_for(qt_app):
    window = _tape_window()
    window.project.metadata = _metadata()

    assert window._suggested_project_name().endswith("-MC")


# -- laying it out -------------------------------------------------------


def test_auto_layout_fills_all_three_pages_and_splits_the_album(qt_app):
    window = _tape_window()
    metadata = _metadata()

    window._auto_layout_project(metadata)

    titles = {
        page: "\n".join(
            item.toPlainText()
            for item in window.project.pages[page].print_items()
            if hasattr(item, "toPlainText")
        )
        for page in (PAGE_COVER, PAGE_SIDE_A, PAGE_SIDE_B)
    }
    # the card names the whole record, each label only its own half
    for track in metadata.tracks:
        assert track.title in titles[PAGE_COVER]
    first, last = metadata.tracks[0].title, metadata.tracks[-1].title
    assert first in titles[PAGE_SIDE_A] and first not in titles[PAGE_SIDE_B]
    assert last in titles[PAGE_SIDE_B] and last not in titles[PAGE_SIDE_A]


def test_the_layout_prompt_names_the_cassettes_own_pages(qt_app):
    window = _tape_window()

    names = window._auto_layout_page_names()

    assert "J-Card" in names
    assert "Side A" in names and "Side B" in names
    assert "MiniDisc" not in names and "disc label" not in names.lower()


def test_the_pages_a_cassette_lays_out_include_no_disc(qt_app):
    window = _tape_window()

    assert window._auto_layout_pages() == {PAGE_COVER, PAGE_SIDE_A, PAGE_SIDE_B}


# -- recording onto it ---------------------------------------------------


def test_every_recording_source_is_offered_for_a_cassette_without_an_adapter(qt_app, monkeypatch):
    """A cassette deck is driven by hand, so none of the three sources
    needs the infrared adapter -- and a CD rip is a CD rip whichever
    machine it ends up on."""
    from mdtools import app_settings

    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: False)
    window = _tape_window()
    window._sync_mdrem_actions()

    for action in (window.record_cd_action, window.record_folder_action, window.record_action):
        assert action.isVisible(), action.text()
        assert "Cassette" in action.text()
    assert window.telegram_record_action.isVisible()
    # the deck's own keys still need the adapter, and a cassette has none
    assert not window.erase_disc_action.isVisible()
    assert not window.remote_action.isVisible()


def test_the_same_entries_still_say_minidisc_on_a_minidisc_project(qt_app, monkeypatch):
    from mdtools import app_settings

    monkeypatch.setattr(app_settings, "mdrem_enabled", lambda: True)
    window = MainWindow(show_startup_dialog=False)
    window._sync_mdrem_actions()

    assert "MiniDisc" in window.record_cd_action.text()
    assert "Cassette" not in window.record_action.text()


def test_a_cassette_project_records_through_the_cassette_dialog(qt_app, monkeypatch):
    """The source decides what is in the playlist; the project decides
    which machine it goes to."""
    from mdtools import app_window as app_window_module

    opened = {}

    class FakeTapeDialog:
        def __init__(self, *args, **kwargs):
            opened["kwargs"] = kwargs
            self.result_metadata = None
            self.total_minutes = 60.0

        def exec(self):
            opened["ran"] = True
            return 0

    monkeypatch.setattr(app_window_module, "TapeRecordDialog", FakeTapeDialog)
    monkeypatch.setattr(
        app_window_module, "RecordDialog", lambda *a, **k: pytest.fail("that is a MiniDisc deck")
    )
    window = _tape_window()

    window._run_record_dialog("", metadata=_metadata())

    assert opened.get("ran") is True
    assert opened["kwargs"]["metadata"] is not None, "a folder's own corrections have to reach the labels"


def test_recording_a_cassette_resolves_no_port_at_all(qt_app, monkeypatch):
    """Not "resolves one and ignores it": asking for a port would put a
    warning about missing hardware in front of a flow that needs none."""
    from mdtools import app_window as app_window_module

    monkeypatch.setattr(
        app_window_module, "resolve_port", lambda *a, **k: pytest.fail("no adapter is involved")
    )
    window = _tape_window()

    assert window._resolve_recording_port() == ""


# -- printing it ---------------------------------------------------------


def test_both_shell_labels_share_a_sheet_and_the_j_card_gets_its_own(qt_app):
    """They are the same sticker printed twice, cut at the same time and
    stuck on opposite faces of one tape."""
    from mdtools.panels.print_dialog import PrintDialog

    window = _tape_window()
    dialog = PrintDialog(window.project)

    sheets = [sorted(map(id, sheet)) for sheet in dialog.sheets()]
    assert len(sheets) == 2
    side_items = sorted(map(id, dialog.items_for(PAGE_SIDE_A) + dialog.items_for(PAGE_SIDE_B)))
    assert side_items in sheets
    assert sorted(map(id, dialog.items_for(PAGE_COVER))) in sheets


def test_the_two_shell_labels_do_not_overlap_on_their_shared_sheet(qt_app):
    from mdtools.panels.print_dialog import PrintDialog

    window = _tape_window()
    dialog = PrintDialog(window.project)

    a, b = dialog.items_for(PAGE_SIDE_A)[0], dialog.items_for(PAGE_SIDE_B)[0]
    assert not a.sceneBoundingRect().intersects(b.sceneBoundingRect())
