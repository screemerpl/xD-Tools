"""The toolbar's plain "Regenerate" button, the font dialog's
preview-on-pick, and the rule both the magic wand and the post-recording
layout now follow: build only up to the templates already chosen.

The bug those last two share is one bug, because they are one method. Both
called every `_auto_layout_*` with no template name, so each fell back to
its own hardcoded default and *replaced* whatever the user had picked -- a
project deliberately set up with the small sticker disc label came back with
the full-face one. The fix is MainWindow._generator_template_name_for_page,
which answers "what may this page be rebuilt onto" once, for every caller.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from mdtools import app_window as app_module
from mdtools.app_window import (
    FULL_LABEL_TEMPLATE,
    JCARD_TEMPLATE,
    STICKER_TEMPLATE,
    MainWindow,
)
from mdtools.project import PAGE_COVER, PAGE_DISC, ProjectMetadata, Track
from mdtools.templates import registry
from mdtools.templates.models import CoverTemplate, DiscTemplate


@pytest.fixture(autouse=True)
def _isolated_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def _cover(colour=(12, 26, 52)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (240, 240), colour).save(out, format="PNG")
    return out.getvalue()


def _metadata(**overrides) -> ProjectMetadata:
    fields = dict(
        album="Album",
        artist="Artist",
        year=2020,
        tracks=[Track(title=f"Track {i}", time_seconds=200) for i in range(1, 7)],
        cover_art=_cover(),
    )
    fields.update(overrides)
    return ProjectMetadata(**fields)


def _full_label(name=FULL_LABEL_TEMPLATE, builtin=True) -> DiscTemplate:
    return DiscTemplate(
        name=name, width_mm=69.4, height_mm=66.4, shape="full_label", corner_radius_mm=4.0,
        slider_notch_width_mm=27.5, slider_notch_height_mm=17.5, slider_notch_corner_radius_mm=2.5,
        slider_notch_top_mm=24.3, slider_notch_buffer_mm=0.8, slider_travel_mm=19.4,
        slider_width_mm=27.5, slider_height_mm=17.5, slider_corner_radius_mm=2.5, builtin=builtin,
    )


def _sticker(name=STICKER_TEMPLATE, builtin=True) -> DiscTemplate:
    return DiscTemplate(
        name=name, width_mm=37.0, height_mm=52.0, shape="sticker", chamfer_mm=3.0,
        corner_radius_mm=1.0, slider_width_mm=27.5, slider_height_mm=17.5,
        slider_corner_radius_mm=2.5, slider_gap_mm=3.0, builtin=builtin,
    )


def _jcard(name=JCARD_TEMPLATE, builtin=True) -> CoverTemplate:
    return CoverTemplate(
        name=name, width_mm=126.0, height_mm=73.0, fold_offsets_mm=[58.85, 67.15], builtin=builtin
    )


def _registry(monkeypatch, disc, cover):
    monkeypatch.setattr(
        registry,
        "load_templates",
        lambda: {"disc": list(disc), "cover": list(cover), "label": [], "case_back": []},
    )


def _md_window(monkeypatch, *, disc, cover) -> MainWindow:
    _registry(monkeypatch, disc, cover)
    window = MainWindow(show_startup_dialog=False)
    window.project.metadata = _metadata()
    return window


def _yes(monkeypatch):
    monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Yes)


def _silence_info(monkeypatch, captured=None):
    def fake_info(parent, title, text, *a, **k):
        if captured is not None:
            captured.append(text)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(app_module.QMessageBox, "information", fake_info)


# -- the magic wand / post-recording layout respects the chosen templates ----


def test_the_whole_project_layout_keeps_the_disc_template_already_chosen(qt_app, monkeypatch):
    """The actual report: a project set up with the sticker label came back
    with the full-face one, because _auto_layout_project passed no template
    name and the generator fell back to its own default."""
    window = _md_window(monkeypatch, disc=[_full_label(), _sticker()], cover=[_jcard()])
    window.apply_template(PAGE_DISC, _sticker())
    assert window.project.pages[PAGE_DISC].template.name == STICKER_TEMPLATE

    window._auto_layout_project(window.project.metadata)

    assert window.project.pages[PAGE_DISC].template.name == STICKER_TEMPLATE
    assert window.project.pages[PAGE_DISC].print_items()


def test_the_whole_project_layout_leaves_a_custom_template_alone(qt_app, monkeypatch):
    """Explicit instruction: a custom template is the user's own, may carry
    its own saved layers, and nothing here knows how to build it -- so that
    page is skipped rather than replaced."""
    custom = _sticker(name="my own sticker", builtin=False)
    window = _md_window(monkeypatch, disc=[_full_label(), custom], cover=[_jcard()])
    window.apply_template(PAGE_DISC, custom)
    before = len(window.project.pages[PAGE_DISC].print_items())

    window._auto_layout_project(window.project.metadata)

    assert window.project.pages[PAGE_DISC].template.name == "my own sticker"
    # Untouched: same template, same layer count (the seeded insertion mark).
    assert len(window.project.pages[PAGE_DISC].print_items()) == before
    # ...while the cover page, which is on a built-in, did get built.
    assert window.project.pages[PAGE_COVER].print_items()


def test_a_renamed_builtin_is_skipped_too(qt_app, monkeypatch):
    """A built-in renamed through the Template Manager stops matching by
    name, which is the same rule the Template dropdown already applies."""
    renamed = _sticker(name="sticker but renamed", builtin=True)
    window = _md_window(monkeypatch, disc=[_full_label(), renamed], cover=[_jcard()])
    window.apply_template(PAGE_DISC, renamed)

    assert window._generator_template_name_for_page(PAGE_DISC) is None


def test_the_generator_name_is_the_template_actually_on_the_page(qt_app, monkeypatch):
    window = _md_window(monkeypatch, disc=[_full_label(), _sticker()], cover=[_jcard()])
    window.apply_template(PAGE_DISC, _sticker())

    assert window._generator_template_name_for_page(PAGE_DISC) == STICKER_TEMPLATE
    assert window._generator_template_name_for_page(PAGE_COVER) == JCARD_TEMPLATE


# -- the plain Regenerate button ---------------------------------------------


def test_the_toolbar_has_a_regenerate_button_left_of_the_font_one(qt_app, monkeypatch):
    window = _md_window(monkeypatch, disc=[_full_label()], cover=[_jcard()])
    toolbar = window.regenerate_btn.parent()

    # Icon-only now -- the label lives in the tooltip instead.
    assert window.regenerate_btn.text() == ""
    assert "Regenerate" in window.regenerate_btn.toolTip()
    assert not window.regenerate_btn.icon().isNull()
    # Same toolbar, and ahead of the font button in it.
    assert window.regenerate_font_btn.parent() is toolbar
    children = toolbar.findChildren(type(window.regenerate_btn))
    assert children.index(window.regenerate_btn) < children.index(window.regenerate_font_btn)


def test_regenerate_rebuilds_the_current_page_on_its_own_template(qt_app, monkeypatch):
    window = _md_window(monkeypatch, disc=[_full_label(), _sticker()], cover=[_jcard()])
    window.apply_template(PAGE_DISC, _sticker())
    window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_DISC))
    _yes(monkeypatch)

    window._regenerate_current_page()

    assert window.project.pages[PAGE_DISC].template.name == STICKER_TEMPLATE
    assert window.project.pages[PAGE_DISC].print_items()


def test_regenerate_does_nothing_without_confirmation(qt_app, monkeypatch):
    window = _md_window(monkeypatch, disc=[_full_label()], cover=[_jcard()])
    window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_COVER))
    before = len(window.project.pages[PAGE_COVER].print_items())
    monkeypatch.setattr(app_module.QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.No)

    window._regenerate_current_page()

    assert len(window.project.pages[PAGE_COVER].print_items()) == before


def test_regenerate_explains_itself_on_a_custom_template(qt_app, monkeypatch):
    """Rather than silently doing nothing, which is what a page whose
    template has no generator would otherwise get."""
    custom = _jcard(name="my own card", builtin=False)
    window = _md_window(monkeypatch, disc=[_full_label()], cover=[_jcard(), custom])
    window.apply_template(PAGE_COVER, custom)
    window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_COVER))
    shown: list[str] = []
    _silence_info(monkeypatch, shown)
    _yes(monkeypatch)

    window._regenerate_current_page()

    assert shown, "a custom template should be explained, not silently skipped"
    assert "nothing to regenerate" in shown[0]


def test_regenerate_asks_for_metadata_before_anything_else(qt_app, monkeypatch):
    window = _md_window(monkeypatch, disc=[_full_label()], cover=[_jcard()])
    window.project.metadata = ProjectMetadata()
    window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_COVER))
    shown: list[str] = []
    _silence_info(monkeypatch, shown)
    _yes(monkeypatch)

    window._regenerate_current_page()

    assert shown
    assert "album and artist" in shown[0]
