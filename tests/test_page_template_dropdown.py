"""The toolbar's Template dropdown (between the page selector and
"Regenerate with Font...") -- lets a page's template be swapped without
going through Templates > "Change Template for This Page..." first.

Three behaviours, matching the feature request directly:
- the list is filtered to the current page's own kind and the project's
  medium, and follows the page selector;
- picking a *custom* (non-builtin) template replaces the page with it
  outright, no questions asked -- it is already the user's own choice;
- picking a *built-in* template asks Empty / Generated from Metadata /
  Cancel, with "Generated" disabled unless a known auto-layout algorithm
  actually targets that exact template (see
  app_window._can_auto_generate_page).
"""

from __future__ import annotations

import io

import pytest
from PIL import Image
from PySide6.QtWidgets import QMessageBox

from mdtools import app_window as app_module
from mdtools.app_window import CD_LABEL_TEMPLATE, FULL_LABEL_TEMPLATE, JCARD_TEMPLATE, MainWindow
from mdtools.project import MEDIUM_CD, PAGE_BACK, PAGE_COVER, PAGE_DISC, ProjectMetadata, Track
from mdtools.templates import registry
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _full_label(name=FULL_LABEL_TEMPLATE, builtin=True, items=None) -> DiscTemplate:
    return DiscTemplate(
        name=name,
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
        builtin=builtin,
        items=items or [],
    )


def _sticker(name="sticker", builtin=True) -> DiscTemplate:
    return DiscTemplate(name=name, width_mm=37.0, height_mm=52.0, builtin=builtin)


def _jcard(name=JCARD_TEMPLATE, builtin=True, items=None) -> CoverTemplate:
    return CoverTemplate(
        name=name, width_mm=126.0, height_mm=73.0, fold_offsets_mm=[58.85, 67.15], builtin=builtin, items=items or []
    )


def _cd_label(name=CD_LABEL_TEMPLATE, builtin=True) -> DiscTemplate:
    return DiscTemplate(
        name=name, width_mm=117.0, height_mm=117.0, shape="cd_label",
        outer_diameter_mm=117.0, hole_diameter_mm=35.0, medium=MEDIUM_CD, builtin=builtin,
    )


def _tray_card(name="Tray Card", builtin=True) -> CoverTemplate:
    return CoverTemplate(
        name=name, width_mm=151.0, height_mm=117.5, fold_offsets_mm=[6.5, 144.5],
        kind="case_back", medium=MEDIUM_CD, builtin=builtin,
    )


def _templates(**kinds) -> dict:
    base = {"disc": [], "cover": [], "label": [], "case_back": []}
    base.update(kinds)
    return base


@pytest.fixture
def _md_registry(monkeypatch):
    templates = _templates(disc=[_full_label(), _sticker()], cover=[_jcard()])
    monkeypatch.setattr(registry, "load_templates", lambda: templates)
    return templates


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


def _window(monkeypatch) -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _select(window: MainWindow, name: str) -> None:
    """Drives the toolbar Template combo the way a user click would."""
    window.template_combo.setCurrentIndex(window.template_combo.findData(name))


# -- populating the dropdown --------------------------------------------------


def test_the_combo_lists_only_the_current_pages_kind_and_medium(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window._refresh_template_combo()

    names = {window.template_combo.itemData(i) for i in range(window.template_combo.count())}
    assert names == {FULL_LABEL_TEMPLATE, "sticker"}


def test_the_combo_starts_on_the_pages_own_template(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)

    assert window.template_combo.currentData() == window.project.pages[PAGE_DISC].template.name


def test_switching_pages_updates_the_combo(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)

    window.page_combo.setCurrentIndex(window.page_combo.findData(PAGE_COVER))

    assert window.template_combo.currentData() == JCARD_TEMPLATE


def test_a_template_no_longer_in_the_registry_still_shows_as_the_current_choice(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)
    # The registry lost this template after it was already on the page --
    # e.g. deleted from templates.json by hand.
    monkeypatch.setattr(registry, "load_templates", lambda: _templates(disc=[_sticker()], cover=[_jcard()]))

    window._refresh_template_combo()

    assert window.template_combo.currentData() == FULL_LABEL_TEMPLATE


# -- custom templates apply outright ------------------------------------------


def test_selecting_a_custom_template_applies_it_with_no_dialog(qt_app, monkeypatch):
    custom = _sticker(name="my sticker", builtin=False)
    monkeypatch.setattr(registry, "load_templates", lambda: _templates(disc=[_full_label(), custom], cover=[_jcard()]))
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window._refresh_template_combo()
    shown = []
    monkeypatch.setattr(app_module.QMessageBox, "exec", lambda self: shown.append(1))

    _select(window, "my sticker")

    assert not shown
    assert window.project.pages[PAGE_DISC].template.name == "my sticker"


def test_a_custom_templates_own_saved_layers_are_used(qt_app, monkeypatch):
    from mdtools.canvas.scene import DesignScene
    from mdtools.io.project_io import item_to_dict

    scratch = DesignScene(_sticker())
    saved_item = item_to_dict(scratch.add_text("From the custom template"))
    custom = _sticker(name="my sticker", builtin=False)
    custom.items = [saved_item]
    monkeypatch.setattr(registry, "load_templates", lambda: _templates(disc=[_full_label(), custom], cover=[_jcard()]))
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window._refresh_template_combo()

    _select(window, "my sticker")

    texts = [i.toPlainText() for i in window.project.pages[PAGE_DISC].print_items() if hasattr(i, "toPlainText")]
    assert "From the custom template" in texts


# -- built-in templates ask first ---------------------------------------------


def _fake_message_box(monkeypatch, clicked_index: int):
    """Stubs QMessageBox.exec/clickedButton so _offer_template_replacement's
    three-button dialog resolves to whichever button was added at
    `clicked_index` (0 = Empty, 1 = Generated, 2 = Cancel), without a real
    modal loop."""

    def fake_exec(self):
        self._clicked = self.buttons()[clicked_index]
        return 0

    def fake_clicked_button(self):
        return self._clicked

    monkeypatch.setattr(app_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_module.QMessageBox, "clickedButton", fake_clicked_button)


def test_selecting_a_builtin_template_asks_first(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window._refresh_template_combo()
    asked = []
    monkeypatch.setattr(app_module.QMessageBox, "exec", lambda self: asked.append(1) or 0)
    monkeypatch.setattr(app_module.QMessageBox, "clickedButton", lambda self: self.buttons()[-1])  # Cancel

    _select(window, "sticker")

    assert asked


def test_cancel_leaves_the_page_and_the_combo_untouched(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    original = window.project.pages[PAGE_DISC]
    _fake_message_box(monkeypatch, clicked_index=2)  # Cancel

    _select(window, "sticker")

    assert window.project.pages[PAGE_DISC] is original
    assert window.template_combo.currentData() == FULL_LABEL_TEMPLATE


def test_choosing_empty_template_clears_the_page(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window.project.pages[PAGE_DISC].add_text("something the user drew")
    _fake_message_box(monkeypatch, clicked_index=0)  # Empty Template

    _select(window, "sticker")

    assert window.project.pages[PAGE_DISC].template.name == "sticker"
    texts = [i.toPlainText() for i in window.project.pages[PAGE_DISC].print_items() if hasattr(i, "toPlainText")]
    assert "something the user drew" not in texts


def test_generated_is_disabled_when_no_algorithm_targets_this_template(qt_app, monkeypatch, _md_registry):
    """"sticker" isn't FULL_LABEL_TEMPLATE, so nothing here knows how to
    auto-generate content for it -- the button must be disabled, not just
    silently ignored on click."""
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window._refresh_template_combo()
    captured = {}

    def fake_exec(self):
        captured["enabled"] = self.buttons()[1].isEnabled()
        self._clicked = self.buttons()[2]  # Cancel
        return 0

    monkeypatch.setattr(app_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_module.QMessageBox, "clickedButton", lambda self: self._clicked)

    _select(window, "sticker")

    assert captured["enabled"] is False


def test_generated_is_enabled_for_the_templates_own_target(qt_app, monkeypatch):
    """Switching *away* from the full-label template and back to it: the
    dropdown offers "Full disc label (with Slider)" itself as a choice
    (e.g. after picking "sticker" first), and that one *does* have a known
    generator."""
    monkeypatch.setattr(registry, "load_templates", lambda: _templates(disc=[_full_label(), _sticker()], cover=[_jcard()]))
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window.apply_template(PAGE_DISC, _sticker())
    window._refresh_template_combo()
    captured = {}

    def fake_exec(self):
        captured["enabled"] = self.buttons()[1].isEnabled()
        self._clicked = self.buttons()[2]  # Cancel
        return 0

    monkeypatch.setattr(app_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_module.QMessageBox, "clickedButton", lambda self: self._clicked)

    _select(window, FULL_LABEL_TEMPLATE)

    assert captured["enabled"] is True


def test_generated_builds_the_page_from_metadata(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window.project.metadata = _metadata()
    window.apply_template(PAGE_DISC, _sticker())
    window._refresh_template_combo()
    monkeypatch.setattr(app_module.CoverFilterDialog, "exec", lambda self: (setattr(self, "result_filter_id", "none"), 1)[1])
    _fake_message_box(monkeypatch, clicked_index=1)  # Generated from Metadata

    _select(window, FULL_LABEL_TEMPLATE)

    scene = window.project.pages[PAGE_DISC]
    assert scene.template.name == FULL_LABEL_TEMPLATE
    assert len(scene.print_items()) > 0


def test_generated_with_no_metadata_is_explained_and_the_page_is_untouched(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    window.apply_template(PAGE_DISC, _sticker())
    window._refresh_template_combo()
    original = window.project.pages[PAGE_DISC]
    told = []
    monkeypatch.setattr(app_module.QMessageBox, "information", lambda *a, **k: told.append(a))
    _fake_message_box(monkeypatch, clicked_index=1)  # Generated from Metadata

    _select(window, FULL_LABEL_TEMPLATE)

    assert told
    assert window.project.pages[PAGE_DISC] is original


# -- the case back has no fixed target template, only a shape check ----------


def test_case_back_generated_is_enabled_for_any_three_panel_template(qt_app, monkeypatch):
    """build_case_back() works from whatever three-panel shape is already
    on the page rather than demanding one template by name -- so a
    *different* three-panel case_back template must still offer Generated."""
    templates = _templates(
        disc=[_full_label(), _cd_label()],
        cover=[_jcard(), CoverTemplate(name="CD Insert", width_mm=240.0, height_mm=120.0, fold_offsets_mm=[120.0], medium=MEDIUM_CD, builtin=True)],
        case_back=[_tray_card(), _tray_card(name="Another Tray Card")],
    )
    monkeypatch.setattr(registry, "load_templates", lambda: templates)
    window = _window(monkeypatch)
    window.project.medium = MEDIUM_CD
    window.apply_template(PAGE_BACK, _tray_card())
    window.current_page = PAGE_BACK
    window._refresh_page_combo()
    window._refresh_template_combo()
    captured = {}

    def fake_exec(self):
        captured["enabled"] = self.buttons()[1].isEnabled()
        self._clicked = self.buttons()[2]  # Cancel
        return 0

    monkeypatch.setattr(app_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_module.QMessageBox, "clickedButton", lambda self: self._clicked)

    _select(window, "Another Tray Card")

    assert captured["enabled"] is True


def test_case_back_generated_is_disabled_for_a_template_with_the_wrong_fold_count(qt_app, monkeypatch):
    templates = _templates(
        disc=[_full_label(), _cd_label()],
        cover=[_jcard(), CoverTemplate(name="CD Insert", width_mm=240.0, height_mm=120.0, fold_offsets_mm=[120.0], medium=MEDIUM_CD, builtin=True)],
        case_back=[_tray_card(), CoverTemplate(name="Two Panel", width_mm=200.0, height_mm=100.0, fold_offsets_mm=[100.0], kind="case_back", medium=MEDIUM_CD, builtin=True)],
    )
    monkeypatch.setattr(registry, "load_templates", lambda: templates)
    window = _window(monkeypatch)
    window.project.medium = MEDIUM_CD
    window.apply_template(PAGE_BACK, _tray_card())
    window.current_page = PAGE_BACK
    window._refresh_page_combo()
    window._refresh_template_combo()
    captured = {}

    def fake_exec(self):
        captured["enabled"] = self.buttons()[1].isEnabled()
        self._clicked = self.buttons()[2]  # Cancel
        return 0

    monkeypatch.setattr(app_module.QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(app_module.QMessageBox, "clickedButton", lambda self: self._clicked)

    _select(window, "Two Panel")

    assert captured["enabled"] is False


# -- re-selecting the current template is a no-op -----------------------------


def test_reselecting_the_current_template_does_nothing(qt_app, monkeypatch, _md_registry):
    window = _window(monkeypatch)
    window.current_page = PAGE_DISC
    original = window.project.pages[PAGE_DISC]
    shown = []
    monkeypatch.setattr(app_module.QMessageBox, "exec", lambda self: shown.append(1))

    _select(window, FULL_LABEL_TEMPLATE)

    assert not shown
    assert window.project.pages[PAGE_DISC] is original
