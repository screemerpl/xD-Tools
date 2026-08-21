"""Toolbar > "Regenerate with Font...": wiring between RegenerateFontDialog,
MainWindow, canvas.scene.font_family_override(), and
_reused_cover_filter() -- not the dialog's own widgets (see
test_regenerate_font_dialog.py) and not the override mechanism itself (see
test_font_family_override.py).
"""

from __future__ import annotations

import copy
import io

import pytest
from PIL import Image
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGraphicsTextItem, QMessageBox

from mdtools import app_window as app_module
from mdtools import cover_filters
from mdtools.app_window import CD_INSERT_TEMPLATE, CD_LABEL_TEMPLATE, MainWindow
from mdtools.panels.cover_filter_dialog import CoverFilterDialog
from mdtools.panels.regenerate_font_dialog import RegenerateFontDialog
from mdtools.project import MEDIUM_CD, MEDIUM_TAPE, PAGE_COVER, PAGE_DISC, PAGE_SIDE_A, PAGE_SIDE_B, ProjectMetadata, Track
from mdtools.templates import registry


@pytest.fixture(autouse=True)
def _isolated_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def _cover(colour=(10, 20, 40), size=(240, 240)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, format="PNG")
    return out.getvalue()


def _metadata(**overrides) -> ProjectMetadata:
    fields = dict(
        album="Album",
        artist="Artist",
        year=2020,
        tracks=[Track(title=f"Track {i}", time_seconds=200) for i in range(1, 9)],
        cover_art=_cover(),
    )
    fields.update(overrides)
    return ProjectMetadata(**fields)


def _md_window(monkeypatch) -> MainWindow:
    from mdtools.templates.models import CoverTemplate, DiscTemplate

    template = DiscTemplate(
        name="full label",
        width_mm=69.4,
        height_mm=66.4,
        shape="full_label",
        corner_radius_mm=4.0,
        slider_notch_width_mm=27.5,
        slider_notch_height_mm=17.5,
        slider_notch_corner_radius_mm=2.5,
        slider_notch_top_mm=24.3,
        slider_notch_buffer_mm=0.8,
        slider_travel_mm=19.4,
        slider_width_mm=27.5,
        slider_height_mm=17.5,
        slider_corner_radius_mm=2.5,
    )
    monkeypatch.setattr(
        registry,
        "load_templates",
        lambda: {"disc": [template], "cover": [CoverTemplate(name="plain", width_mm=126.0, height_mm=73.0)]},
    )
    monkeypatch.setattr("mdtools.app_window.FULL_LABEL_TEMPLATE", template.name)
    window = MainWindow(show_startup_dialog=False)
    window.project.metadata = _metadata()
    return window


def _md_window_no_slider(monkeypatch) -> MainWindow:
    """A MiniDisc project whose disc page is already on the plain "Full
    disc label" (no slider) variant -- for checking that "Regenerate with
    Font..." preserves it rather than silently rebuilding the "(with
    Slider)" twin (see app_window._auto_layout_method_for_page's own
    disc_template_name parameter)."""
    from mdtools.project import PAGE_DISC
    from mdtools.templates.models import CoverTemplate, DiscTemplate

    with_slider = DiscTemplate(
        name="full label",
        width_mm=69.4,
        height_mm=66.4,
        shape="full_label",
        corner_radius_mm=4.0,
        slider_notch_width_mm=27.5,
        slider_notch_height_mm=17.5,
        slider_notch_corner_radius_mm=2.5,
        slider_notch_top_mm=24.3,
        slider_notch_buffer_mm=0.8,
        slider_travel_mm=19.4,
        slider_width_mm=27.5,
        slider_height_mm=17.5,
        slider_corner_radius_mm=2.5,
    )
    no_slider = DiscTemplate(
        name="full label no slider",
        width_mm=69.4,
        height_mm=66.4,
        shape="full_label",
        corner_radius_mm=4.0,
        slider_notch_width_mm=27.5,
        slider_notch_height_mm=17.5,
        slider_notch_corner_radius_mm=2.5,
        slider_notch_top_mm=24.3,
        slider_notch_buffer_mm=0.8,
        slider_travel_mm=19.4,
    )
    monkeypatch.setattr(
        registry,
        "load_templates",
        lambda: {
            "disc": [with_slider, no_slider],
            "cover": [CoverTemplate(name="plain", width_mm=126.0, height_mm=73.0)],
        },
    )
    monkeypatch.setattr("mdtools.app_window.FULL_LABEL_TEMPLATE", with_slider.name)
    monkeypatch.setattr("mdtools.app_window.FULL_LABEL_NO_SLIDER_TEMPLATE", no_slider.name)
    window = MainWindow(show_startup_dialog=False)
    window.project.metadata = _metadata()
    window.apply_template(PAGE_DISC, no_slider)
    return window


def _cd_window(monkeypatch) -> MainWindow:
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window = MainWindow(show_startup_dialog=False)
    templates = registry.load_templates()
    window.project.medium = MEDIUM_CD
    window.apply_template(PAGE_DISC, next(t for t in templates["disc"] if t.name == CD_LABEL_TEMPLATE))
    window.apply_template(PAGE_COVER, next(t for t in templates["cover"] if t.name == CD_INSERT_TEMPLATE))
    window.project.metadata = _metadata()
    return window


def _cd_window_front_insert(monkeypatch) -> MainWindow:
    """A CD project whose cover page is already on the front-only insert --
    for checking that "Regenerate with Font..." preserves it rather than
    silently rebuilding the folded, two-panel one (see
    app_window._auto_layout_method_for_page's own cover_template_name
    parameter)."""
    from mdtools.app_window import CD_INSERT_FRONT_TEMPLATE

    window = _cd_window(monkeypatch)
    front = next(t for t in registry.load_templates()["cover"] if t.name == CD_INSERT_FRONT_TEMPLATE)
    window.apply_template(PAGE_COVER, front)
    return window


def _tape_window(monkeypatch) -> MainWindow:
    from mdtools.app_window import TAPE_JCARD_TEMPLATE, TAPE_LABEL_TEMPLATE

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
    window.project.metadata = _metadata()
    return window


def _text_families(scene) -> set[str]:
    return {i.font().family() for i in scene.print_items() if isinstance(i, QGraphicsTextItem)}


def _run_dialog(monkeypatch, window, *, family="Courier New", preview=True, final=None, confirm=None, after_preview=None):
    """Drives _open_regenerate_font_dialog() without a real modal loop:
    RegenerateFontDialog.exec is stubbed to optionally fire one Preview
    first (calling `after_preview()`, if given, right afterwards -- while
    the preview's own effect is still on screen, before whatever `final`
    resolves the dialog to has a chance to revert or replace it), then
    return `final` (Accepted/Rejected). QMessageBox.warning (the "are you
    sure" confirmation) is stubbed to return `confirm`."""

    def _fake_exec(self):
        self._family = family
        if preview:
            self.preview_requested.emit(family)
            if after_preview is not None:
                after_preview()
        return final if final is not None else RegenerateFontDialog.DialogCode.Rejected

    monkeypatch.setattr(RegenerateFontDialog, "exec", _fake_exec)
    if confirm is not None:
        monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *a, **k: confirm)
    window._open_regenerate_font_dialog()


# -- preview only touches the current page -----------------------------------


def test_preview_changes_the_current_pages_text_font(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    window.current_page = PAGE_DISC
    seen = {}

    def _check():
        seen["families"] = _text_families(window.project.pages[PAGE_DISC])

    _run_dialog(monkeypatch, window, family="Courier New", after_preview=_check)

    assert "Courier New" in seen["families"]


def test_preview_does_not_touch_a_different_page(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    window.current_page = PAGE_DISC
    window.apply_template(PAGE_COVER, next(t for t in registry.load_templates()["cover"] if t.name == "plain"))
    cover_before = window.project.pages[PAGE_COVER]
    seen = {}

    def _check():
        seen["cover"] = window.project.pages[PAGE_COVER]

    _run_dialog(monkeypatch, window, family="Courier New", after_preview=_check)

    assert seen["cover"] is cover_before


# -- cancelling reverts ---------------------------------------------------


def test_cancelling_after_a_preview_restores_the_original_page(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    window.current_page = PAGE_DISC
    original_texts = sorted(i.toPlainText() for i in window.project.pages[PAGE_DISC].print_items() if isinstance(i, QGraphicsTextItem))
    original_fonts = _text_families(window.project.pages[PAGE_DISC])

    _run_dialog(monkeypatch, window, family="Courier New", final=RegenerateFontDialog.DialogCode.Rejected)

    restored_texts = sorted(i.toPlainText() for i in window.project.pages[PAGE_DISC].print_items() if isinstance(i, QGraphicsTextItem))
    assert restored_texts == original_texts
    assert _text_families(window.project.pages[PAGE_DISC]) == original_fonts


def test_declining_the_final_confirmation_also_restores_the_page(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    window.current_page = PAGE_DISC
    original_fonts = _text_families(window.project.pages[PAGE_DISC])

    _run_dialog(
        monkeypatch,
        window,
        family="Courier New",
        final=RegenerateFontDialog.DialogCode.Accepted,
        confirm=QMessageBox.StandardButton.No,
    )

    assert _text_families(window.project.pages[PAGE_DISC]) == original_fonts


def test_two_previews_in_a_row_do_not_compound(qt_app, monkeypatch):
    """Preview "Courier New" then "Arial" without accepting either --
    cancelling must land back on the *original* page, not on whatever
    "Courier New" left behind."""
    window = _md_window(monkeypatch)
    window.current_page = PAGE_DISC
    original_texts = sorted(i.toPlainText() for i in window.project.pages[PAGE_DISC].print_items() if isinstance(i, QGraphicsTextItem))

    def _fake_exec(self):
        self._family = "Courier New"
        self.preview_requested.emit("Courier New")
        self._family = "Arial"
        self.preview_requested.emit("Arial")
        return RegenerateFontDialog.DialogCode.Rejected

    monkeypatch.setattr(RegenerateFontDialog, "exec", _fake_exec)
    window._open_regenerate_font_dialog()

    restored_texts = sorted(i.toPlainText() for i in window.project.pages[PAGE_DISC].print_items() if isinstance(i, QGraphicsTextItem))
    assert restored_texts == original_texts


# -- the disc page's own template (with/without slider) is preserved -----


def test_preview_does_not_swap_the_no_slider_variant_back_to_the_slider_one(qt_app, monkeypatch):
    window = _md_window_no_slider(monkeypatch)
    window.current_page = PAGE_DISC
    seen = {}

    def _check():
        seen["template"] = window.project.pages[PAGE_DISC].template.name

    _run_dialog(monkeypatch, window, family="Courier New", after_preview=_check)

    assert seen["template"] == "full label no slider"


def test_accepting_does_not_swap_the_no_slider_variant_back_to_the_slider_one(qt_app, monkeypatch):
    window = _md_window_no_slider(monkeypatch)
    window.current_page = PAGE_DISC

    _run_dialog(
        monkeypatch,
        window,
        family="Courier New",
        preview=False,
        final=RegenerateFontDialog.DialogCode.Accepted,
        confirm=QMessageBox.StandardButton.Yes,
    )

    assert window.project.pages[PAGE_DISC].template.name == "full label no slider"


def test_preview_does_not_swap_the_front_only_insert_back_to_the_folded_one(qt_app, monkeypatch):
    from mdtools.app_window import CD_INSERT_FRONT_TEMPLATE

    window = _cd_window_front_insert(monkeypatch)
    window.current_page = PAGE_COVER
    seen = {}

    def _check():
        seen["template"] = window.project.pages[PAGE_COVER].template.name

    _run_dialog(monkeypatch, window, family="Courier New", after_preview=_check)

    assert seen["template"] == CD_INSERT_FRONT_TEMPLATE


def test_accepting_does_not_swap_the_front_only_insert_back_to_the_folded_one(qt_app, monkeypatch):
    from mdtools.app_window import CD_INSERT_FRONT_TEMPLATE

    window = _cd_window_front_insert(monkeypatch)
    window.current_page = PAGE_COVER

    _run_dialog(
        monkeypatch,
        window,
        family="Courier New",
        preview=False,
        final=RegenerateFontDialog.DialogCode.Accepted,
        confirm=QMessageBox.StandardButton.Yes,
    )

    assert window.project.pages[PAGE_COVER].template.name == CD_INSERT_FRONT_TEMPLATE


# -- accepting regenerates every page ------------------------------------


def test_accepting_regenerates_only_the_current_page(qt_app, monkeypatch):
    """Explicit, narrower scope than "every automatically generated label
    in the project": only the page that was on screen when the dialog was
    opened, matching the toolbar button's own "current element" framing."""
    window = _cd_window(monkeypatch)
    window.current_page = PAGE_DISC
    cover_before = window.project.pages[PAGE_COVER]

    _run_dialog(
        monkeypatch,
        window,
        family="Courier New",
        preview=False,
        final=RegenerateFontDialog.DialogCode.Accepted,
        confirm=QMessageBox.StandardButton.Yes,
    )

    assert "Courier New" in _text_families(window.project.pages[PAGE_DISC])
    assert window.project.pages[PAGE_COVER] is cover_before


def test_accepting_without_ever_clicking_preview_still_regenerates(qt_app, monkeypatch):
    """OK can be pressed with no Preview click first -- the font still has
    to apply."""
    window = _md_window(monkeypatch)
    window.current_page = PAGE_DISC

    _run_dialog(
        monkeypatch,
        window,
        family="Courier New",
        preview=False,
        final=RegenerateFontDialog.DialogCode.Accepted,
        confirm=QMessageBox.StandardButton.Yes,
    )

    assert "Courier New" in _text_families(window.project.pages[PAGE_DISC])


def test_the_warning_names_the_chosen_font(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    window.current_page = PAGE_DISC
    seen = {}

    def _capture_warning(self_, title, text, *a, **k):
        seen["text"] = text
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(RegenerateFontDialog, "exec", lambda self: RegenerateFontDialog.DialogCode.Accepted)
    monkeypatch.setattr(
        app_module.QMessageBox,
        "warning",
        lambda parent, title, text, *a, **k: seen.setdefault("text", text) or QMessageBox.StandardButton.No,
    )

    def _fake_exec(self):
        self._family = "Wingdings"
        return RegenerateFontDialog.DialogCode.Accepted

    monkeypatch.setattr(RegenerateFontDialog, "exec", _fake_exec)
    window._open_regenerate_font_dialog()

    assert "Wingdings" in seen["text"]


def test_no_warning_is_shown_when_the_dialog_is_simply_cancelled(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    window.current_page = PAGE_DISC
    warned = []
    monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *a, **k: warned.append(a))

    _run_dialog(monkeypatch, window, preview=False, final=RegenerateFontDialog.DialogCode.Rejected)

    assert not warned


# -- cover filter reuse, not re-asking -------------------------------------


def test_preview_reuses_the_labels_original_filter_without_a_new_dialog(qt_app, monkeypatch):
    window = _cd_window(monkeypatch)
    window.current_page = PAGE_DISC
    # Build the disc label once for real, choosing Brighten -- this is the
    # filter "originally selected" the feature request refers to.
    monkeypatch.setattr(CoverFilterDialog, "exec", lambda self: (setattr(self, "result_filter_id", cover_filters.FILTER_BRIGHTEN), CoverFilterDialog.DialogCode.Accepted)[1])
    window._auto_layout_cd_disc_label(window.project.metadata)
    assert window._last_cover_filter_id == cover_filters.FILTER_BRIGHTEN

    # Now Preview a font -- if this opened a real CoverFilterDialog it would
    # hang forever under offscreen with nothing to answer it; asserting the
    # constructor is never even called is a stronger guarantee than "it
    # didn't hang".
    calls = []
    monkeypatch.setattr(CoverFilterDialog, "__init__", lambda self, *a, **k: calls.append(1))

    _run_dialog(monkeypatch, window, family="Courier New")

    assert not calls


def test_accepting_reuses_the_filter_for_every_regenerated_label(qt_app, monkeypatch):
    window = _cd_window(monkeypatch)
    window.current_page = PAGE_DISC
    monkeypatch.setattr(
        CoverFilterDialog,
        "exec",
        lambda self: (setattr(self, "result_filter_id", cover_filters.FILTER_BRIGHTEN), CoverFilterDialog.DialogCode.Accepted)[1],
    )
    window._auto_layout_cd_disc_label(window.project.metadata)

    calls = []
    monkeypatch.setattr(CoverFilterDialog, "__init__", lambda self, *a, **k: calls.append(1))

    _run_dialog(
        monkeypatch,
        window,
        family="Courier New",
        preview=False,
        final=RegenerateFontDialog.DialogCode.Accepted,
        confirm=QMessageBox.StandardButton.Yes,
    )

    assert not calls


# -- preconditions, matching the Tools panel button's own -------------------


def test_missing_album_and_artist_is_explained_rather_than_opening_the_dialog(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    window.project.metadata = ProjectMetadata()
    told = []
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda *a, **k: told.append(a))
    opened = []
    monkeypatch.setattr(RegenerateFontDialog, "exec", lambda self: opened.append(1))

    window._open_regenerate_font_dialog()

    assert told
    assert not opened


def test_no_cover_anywhere_is_explained_rather_than_opening_the_dialog(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    window.project.metadata = ProjectMetadata(album="A", artist="B")
    monkeypatch.setattr(app_module, "find_cover", lambda *a, **k: (None, None))
    warned = []
    monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *a, **k: warned.append(a))
    opened = []
    monkeypatch.setattr(RegenerateFontDialog, "exec", lambda self: opened.append(1))

    window._open_regenerate_font_dialog()

    assert warned
    assert not opened
