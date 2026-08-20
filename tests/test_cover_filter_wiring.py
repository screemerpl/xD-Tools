"""Wiring the CoverFilterDialog picker into the three places a disc/shell
label's cover art is placed full-bleed as a background: the MiniDisc disc
label, the CD-R ring label, and the cassette's two shell labels.

conftest.py's autouse `_auto_accept_cover_filter_dialog` fixture makes the
dialog answer itself with "No Filter" by default (so every *other* test
touching these code paths doesn't hang and doesn't change behaviour) --
these tests override that per-test to actually exercise a real choice, or
a cancel.
"""

from __future__ import annotations

import copy
import io

import pytest
from PIL import Image
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QGraphicsPixmapItem, QMessageBox

from mdtools import cover_filters
from mdtools.app_window import (
    CD_INSERT_TEMPLATE,
    CD_LABEL_TEMPLATE,
    FULL_LABEL_TEMPLATE,
    TAPE_JCARD_TEMPLATE,
    TAPE_LABEL_TEMPLATE,
    MainWindow,
)
from mdtools.panels.cover_filter_dialog import CoverFilterDialog
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


def _choose(monkeypatch, filter_id: str | None) -> None:
    """Makes the next CoverFilterDialog shown answer with `filter_id`
    (accepted), or act as if it was cancelled when `filter_id` is None."""

    def _fake_exec(self):
        if filter_id is None:
            return CoverFilterDialog.DialogCode.Rejected
        self.result_filter_id = filter_id
        return CoverFilterDialog.DialogCode.Accepted

    monkeypatch.setattr(CoverFilterDialog, "exec", _fake_exec)


def _largest_pixmap_item(items) -> QGraphicsPixmapItem:
    pixmaps = [item for item in items if isinstance(item, QGraphicsPixmapItem)]
    return max(pixmaps, key=lambda item: item.boundingRect().width() * item.boundingRect().height())


def _pixel(pixmap: QPixmap, xy=(2, 2)):
    return pixmap.toImage().pixelColor(*xy).getRgb()[:3]


# -- MiniDisc -----------------------------------------------------------------


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
    return MainWindow(show_startup_dialog=False)


def test_md_disc_label_uses_the_chosen_filter(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    _choose(monkeypatch, cover_filters.FILTER_BRIGHTEN)
    metadata = _metadata()

    window._auto_layout_disc_label(metadata)

    cover = _largest_pixmap_item(window.project.pages[PAGE_DISC].print_items())
    r, g, b = _pixel(cover.pixmap())
    # The metadata's own cover colour, (10, 20, 40) -- brighten() must have
    # moved every channel towards white.
    assert r > 10 and g > 20 and b > 40


def test_cancelling_the_md_disc_label_filter_leaves_the_page_untouched(qt_app, monkeypatch):
    window = _md_window(monkeypatch)
    before = list(window.project.pages[PAGE_DISC].print_items())
    _choose(monkeypatch, None)

    window._auto_layout_disc_label(_metadata())

    assert list(window.project.pages[PAGE_DISC].print_items()) == before
    assert window.project.pages[PAGE_DISC].template.name != FULL_LABEL_TEMPLATE


# -- CD -------------------------------------------------------------------


def _cd_window(monkeypatch) -> MainWindow:
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    window = MainWindow(show_startup_dialog=False)
    templates = registry.load_templates()
    window.project.medium = MEDIUM_CD
    window.apply_template(PAGE_DISC, next(t for t in templates["disc"] if t.name == CD_LABEL_TEMPLATE))
    window.apply_template(PAGE_COVER, next(t for t in templates["cover"] if t.name == CD_INSERT_TEMPLATE))
    return window


def test_cd_disc_label_uses_the_chosen_filter(qt_app, monkeypatch):
    """Checked by spying on cd_layout.build_disc_label's own
    `background_art` argument, not by sampling a pixel back off the
    finished, already-clip-layered canvas -- a CD label is a ring with a
    hole through the middle, so most obvious sample points (a corner, the
    centre) land in the very area Clip Layers made transparent, which has
    nothing to do with whether the right bytes were actually passed in."""
    import mdtools.app_window as app_window_module

    window = _cd_window(monkeypatch)
    _choose(monkeypatch, cover_filters.FILTER_BRIGHTEN)
    metadata = _metadata()
    seen = {}
    real_build = app_window_module.build_disc_label

    def _spy(scene, meta, logo_path=None, **kwargs):
        seen["background_art"] = kwargs.get("background_art")
        return real_build(scene, meta, logo_path, **kwargs)

    monkeypatch.setattr(app_window_module, "build_disc_label", _spy)

    window._auto_layout_cd_disc_label(metadata)

    assert seen["background_art"] == cover_filters.apply_cover_filter(
        metadata.cover_art, cover_filters.FILTER_BRIGHTEN
    )


def test_cancelling_the_cd_disc_label_skips_only_that_label(qt_app, monkeypatch):
    """_auto_layout_project builds the insert first, then the disc label --
    cancelling the disc label's filter dialog must not undo the insert."""
    window = _cd_window(monkeypatch)
    _choose(monkeypatch, None)
    metadata = _metadata()

    window._auto_layout_project(metadata)

    assert window.project.pages[PAGE_COVER].print_items(), "the insert should still have been built"
    assert window.project.pages[PAGE_DISC].print_items() == []


# -- cassette -----------------------------------------------------------------


def _tape_window(monkeypatch) -> MainWindow:
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


def test_both_shell_labels_get_the_same_chosen_filter(qt_app, monkeypatch):
    """Same reasoning as the CD test above -- a shell label is cut with a
    hole through its middle too, so this spies on build_side_label's own
    `background_art` argument rather than sampling the finished canvas."""
    import mdtools.app_window as app_window_module

    window = _tape_window(monkeypatch)
    _choose(monkeypatch, cover_filters.FILTER_BRIGHTEN)
    metadata = _metadata()
    seen = []
    real_build = app_window_module.build_side_label

    def _spy(scene, meta, side, **kwargs):
        seen.append(kwargs.get("background_art"))
        return real_build(scene, meta, side, **kwargs)

    monkeypatch.setattr(app_window_module, "build_side_label", _spy)

    window._auto_layout_tape(metadata)

    expected = cover_filters.apply_cover_filter(metadata.cover_art, cover_filters.FILTER_BRIGHTEN)
    assert seen == [expected, expected]


def test_the_filter_dialog_for_shell_labels_is_only_shown_once(qt_app, monkeypatch):
    window = _tape_window(monkeypatch)
    calls = []
    real_exec = CoverFilterDialog.exec

    def _counting_exec(self):
        calls.append(1)
        self.result_filter_id = cover_filters.FILTER_NONE
        return CoverFilterDialog.DialogCode.Accepted

    monkeypatch.setattr(CoverFilterDialog, "exec", _counting_exec)

    window._auto_layout_tape(_metadata())

    assert len(calls) == 1


def test_cancelling_the_shell_label_filter_still_leaves_the_jcard_built(qt_app, monkeypatch):
    window = _tape_window(monkeypatch)
    _choose(monkeypatch, None)

    window._auto_layout_tape(_metadata())

    assert window.project.pages[PAGE_COVER].print_items(), "the J-card should still have been built"
    assert window.project.pages[PAGE_SIDE_A].print_items() == []
    assert window.project.pages[PAGE_SIDE_B].print_items() == []
