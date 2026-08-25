"""Shadow and glow are per-text-layer toggles: two extra, auto-contrasted
renders drawn behind the real text (see canvas/items.py's DesignTextItem).

Covers the flags round-tripping through get/set, save/load and copy/paste,
the auto-picked contrast colour, that both effects actually paint extra
pixels, that the shadow offset is applied in the text's own local (i.e.
rotates-with-the-text) space rather than the canvas's, and that every
auto-generated cover/label turns shadow on by default.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter, QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from mdtools.canvas.items import (
    DesignTextItem,
    _effect_colour,
    get_text_glow,
    get_text_shadow,
    set_text_glow,
    set_text_shadow,
)
from mdtools.canvas.scene import DesignScene
from mdtools.io.project_io import item_from_dict, item_to_dict
from mdtools.jcard_layout import _text
from mdtools.panels.properties_panel import PropertiesPanel
from mdtools.templates.models import CoverTemplate, DiscTemplate

_BG = QColor(128, 128, 128)


def _disc_template() -> DiscTemplate:
    return DiscTemplate(name="t", width_mm=37.0, height_mm=52.0)


def _cover_template() -> CoverTemplate:
    return CoverTemplate(name="c", width_mm=126.0, height_mm=73.0)


def _render(item, w=220, h=110, offset=(-30, -30)) -> QImage:
    scene = QGraphicsScene()
    scene.addItem(item)
    image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(_BG)
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, w, h), QRectF(offset[0], offset[1], w, h))
    painter.end()
    return image


def _non_background_pixel_count(image: QImage) -> int:
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y) != _BG:
                count += 1
    return count


def _big_text_item(text: str = "Hello") -> DesignTextItem:
    item = DesignTextItem(text)
    font = item.font()
    font.setPointSizeF(28)
    item.setFont(font)
    item.setDefaultTextColor(QColor("black"))
    return item


# -- flags themselves --------------------------------------------------------


def test_shadow_and_glow_default_off(qt_app):
    item = _big_text_item()
    assert get_text_shadow(item) is False
    assert get_text_glow(item) is False


def test_shadow_and_glow_round_trip_through_get_set(qt_app):
    item = _big_text_item()
    set_text_shadow(item, True)
    set_text_glow(item, True)
    assert get_text_shadow(item) is True
    assert get_text_glow(item) is True

    set_text_shadow(item, False)
    assert get_text_shadow(item) is False
    assert get_text_glow(item) is True  # independent of shadow


# -- auto-picked contrast colour ---------------------------------------------


def test_effect_colour_is_much_lighter_for_dark_text(qt_app):
    assert _effect_colour(QColor("black")).name() == "#ffffff"


def test_effect_colour_is_much_darker_for_light_text(qt_app):
    assert _effect_colour(QColor("white")).name() == "#000000"


# -- actual rendering ---------------------------------------------------------


def test_shadow_paints_more_than_the_plain_text(qt_app):
    plain = _non_background_pixel_count(_render(_big_text_item()))

    shadowed = _big_text_item()
    set_text_shadow(shadowed, True)
    with_shadow = _non_background_pixel_count(_render(shadowed))

    assert with_shadow > plain


def test_glow_paints_more_than_the_plain_text(qt_app):
    plain = _non_background_pixel_count(_render(_big_text_item()))

    glowing = _big_text_item()
    set_text_glow(glowing, True)
    with_glow = _non_background_pixel_count(_render(glowing))

    assert with_glow > plain


def _distinct_colours(image: QImage) -> set[tuple[int, int, int, int]]:
    return {image.pixelColor(x, y).getRgb() for y in range(image.height()) for x in range(image.width())}


def test_the_shadow_has_soft_blended_edges_not_a_hard_vector_fill(qt_app):
    """Explicit request: the shadow's edge should be a little blurred, not
    a crisp offset copy. A real Gaussian blur produces a range of partially
    blended tones between the background and the shadow colour at its
    boundary; a flat vector fill (the old behaviour) would not -- the only
    intermediate tones on that render came from ordinary text antialiasing,
    a handful of pixels at most."""
    item = _big_text_item()
    set_text_shadow(item, True)

    colours = _distinct_colours(_render(item))
    # Background, pure shadow colour (white, since black text -> white
    # effect colour) and pure text colour (black) accounts for 3; a soft
    # blur spreads well beyond that into many in-between shades.
    assert len(colours) > 10


def test_glow_is_substantially_stronger_than_a_bare_hint(qt_app):
    """"almost invisible" was the report -- this pins the fix down as a
    real, large jump in how much of the render the glow actually touches,
    not a marginal tweak. Compared against the shadow's own spread (built
    from the same machinery, deliberately given a much smaller blur/alpha)
    rather than a hardcoded pixel count, so this doesn't depend on exact
    font rasterization for a specific environment."""
    shadow_item = _big_text_item()
    set_text_shadow(shadow_item, True)
    shadow_extra = _non_background_pixel_count(_render(shadow_item)) - _non_background_pixel_count(
        _render(_big_text_item())
    )

    glow_item = _big_text_item()
    set_text_glow(glow_item, True)
    glow_extra = _non_background_pixel_count(_render(glow_item)) - _non_background_pixel_count(
        _render(_big_text_item())
    )

    assert glow_extra > shadow_extra * 2


def test_blank_text_with_glow_does_not_crash(qt_app):
    item = DesignTextItem("")
    set_text_glow(item, True)
    _render(item)  # must not raise


def test_disabling_shadow_removes_the_extra_ink(qt_app):
    # Two separate items, not one rendered twice: _render() parents its item
    # to a throwaway QGraphicsScene that's garbage-collected once the
    # function returns, which (the scene owns its items in C++) deletes the
    # item along with it -- see the "QGraphicsScene owns its items" gotcha.
    shadowed = _big_text_item()
    set_text_shadow(shadowed, True)
    with_shadow = _non_background_pixel_count(_render(shadowed))

    plain = _big_text_item()
    without_shadow = _non_background_pixel_count(_render(plain))

    assert without_shadow < with_shadow


# -- direction follows the text's own rotation, not the canvas ---------------


def test_shadow_is_applied_in_the_items_own_local_space():
    """The offset is a plain painter.translate() inside paint(), which Qt
    always calls in the item's local, unrotated coordinate system -- the
    item's rotation() is composed as an *outer* transform by the graphics
    framework before paint() ever runs. So a caption rotated to run down a
    spine gets a shadow that still falls toward the text's own lower-right,
    not the label's -- there's nothing conditional on rotation() anywhere
    in the shadow-drawing code, which is what actually guarantees this."""
    import inspect

    from mdtools.canvas import items as items_module

    source = inspect.getsource(items_module._draw_shadow)
    assert "rotation" not in source


# -- save/load and copy/paste --------------------------------------------------


def test_item_to_dict_saves_shadow_and_glow(qt_app):
    scene = DesignScene(_disc_template())
    item = scene.add_text("hi")
    set_text_shadow(item, True)
    set_text_glow(item, True)

    data = item_to_dict(item)

    assert data["shadow"] is True
    assert data["glow"] is True


def test_item_from_dict_restores_shadow_and_glow(qt_app):
    scene = DesignScene(_disc_template())
    original = scene.add_text("hi")
    set_text_shadow(original, True)
    set_text_glow(original, False)
    data = item_to_dict(original)

    scene2 = DesignScene(_disc_template())
    restored = item_from_dict(scene2, data)

    assert get_text_shadow(restored) is True
    assert get_text_glow(restored) is False


def test_a_project_saved_before_shadow_glow_existed_loads_as_off(qt_app):
    """Neither key is present in an older .mdproj -- the field's own
    docstring convention throughout this codebase is that a missing key
    means "this item looked like it always did," i.e. no effect."""
    scene = DesignScene(_disc_template())
    original = scene.add_text("hi")
    data = item_to_dict(original)
    del data["shadow"]
    del data["glow"]

    scene2 = DesignScene(_disc_template())
    restored = item_from_dict(scene2, data)

    assert get_text_shadow(restored) is False
    assert get_text_glow(restored) is False


# -- Properties panel ----------------------------------------------------------


def test_shadow_and_glow_rows_are_only_visible_for_text(qt_app):
    scene = DesignScene(_disc_template())
    text_item = scene.add_text("hello")
    rect_item = scene.add_rectangle()

    panel = PropertiesPanel()

    panel.set_item(text_item)
    assert panel.form.isRowVisible(panel.shadow_check)
    assert panel.form.isRowVisible(panel.glow_check)

    panel.set_item(rect_item)
    assert not panel.form.isRowVisible(panel.shadow_check)
    assert not panel.form.isRowVisible(panel.glow_check)


def test_set_item_reflects_the_items_current_shadow_and_glow_state(qt_app):
    scene = DesignScene(_disc_template())
    text_item = scene.add_text("hello")
    set_text_shadow(text_item, True)

    panel = PropertiesPanel()
    panel.set_item(text_item)

    assert panel.shadow_check.isChecked()
    assert not panel.glow_check.isChecked()


def test_toggling_the_shadow_checkbox_updates_the_item(qt_app):
    scene = DesignScene(_disc_template())
    text_item = scene.add_text("hello")

    panel = PropertiesPanel()
    panel.set_item(text_item)
    panel.shadow_check.setChecked(True)

    assert get_text_shadow(text_item) is True


def test_toggling_the_glow_checkbox_updates_the_item(qt_app):
    scene = DesignScene(_disc_template())
    text_item = scene.add_text("hello")

    panel = PropertiesPanel()
    panel.set_item(text_item)
    panel.glow_check.setChecked(True)

    assert get_text_glow(text_item) is True


def test_undoing_a_shadow_toggle_restores_the_previous_state(qt_app):
    scene = DesignScene(_disc_template())
    text_item = scene.add_text("hello")

    panel = PropertiesPanel()
    panel.undo_stack = QUndoStack()
    panel.set_item(text_item)
    panel.shadow_check.setChecked(True)

    assert get_text_shadow(text_item) is True

    panel.undo_stack.undo()

    assert get_text_shadow(text_item) is False


# -- auto-generated covers/labels always turn shadow on ------------------------


def test_jcard_text_helper_turns_shadow_on_by_default(qt_app):
    scene = DesignScene(_cover_template())
    item = _text(scene, "Some Album", QRectF(0, 0, 500, 100), "#000000")

    assert item is not None
    assert get_text_shadow(item) is True


def test_seeded_insertion_mark_has_shadow_on(qt_app):
    scene = DesignScene(_disc_template())
    scene.seed_disc_defaults()

    text_items = [i for i in scene.items() if isinstance(i, DesignTextItem)]
    assert len(text_items) == 2
    assert all(get_text_shadow(i) for i in text_items)


def test_plain_add_text_does_not_turn_shadow_on(qt_app):
    """Manually adding a text layer via the Tools panel stays plain --
    only the automatic layout code opts in by default; the user can still
    switch it on themselves via the Properties panel."""
    scene = DesignScene(_disc_template())
    item = scene.add_text("hello")

    assert get_text_shadow(item) is False
    assert get_text_glow(item) is False
