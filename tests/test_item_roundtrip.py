"""Every layer type has to come back exactly as it went in.

Two separate bugs lived here, found because a J-card looked wrong after
being reopened:

- a wrapped text layer lost its wrap width and its pivot (see
  test_jcard_roundtrip.py);
- **a scaled rectangle or ellipse was scaled a second time on load**, and
  moved, because the file stores the already-resized rect and
  set_item_scale() adopted that as the shape's pre-scale size.

Neither showed up in the existing per-field tests, because every field that
was being saved round-tripped perfectly. These compare where a layer
actually lands on the page instead.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QBuffer
from PySide6.QtGui import QColor, QImage

from mdtools.canvas.items import BASE_RECT_ROLE, get_item_scale, set_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.clipboard import PASTE_OFFSET_PX, Clipboard
from mdtools.io.project_io import item_from_dict, item_to_dict
from mdtools.templates.registry import load_templates


def _png(width: int = 80, height: int = 40) -> bytes:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("red"))
    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def _template():
    return load_templates()["cover"][0]


def _make(scene: DesignScene, kind: str):
    if kind == "text":
        return scene.add_text("Some text layer")
    if kind == "rect":
        return scene.add_rectangle()
    if kind == "ellipse":
        return scene.add_ellipse()
    return scene.add_image_from_data(_png())


def _footprint(item) -> tuple:
    """Where the layer actually sits on the page -- what the eye compares,
    and the only measure that catches a wrong pivot and a wrong size at
    once."""
    rect = item.mapToScene(item.boundingRect()).boundingRect()
    return (round(rect.x(), 2), round(rect.y(), 2), round(rect.width(), 2), round(rect.height(), 2))


# rotation, scale x, scale y. (1.0, 1.0) is included because multiplying by
# one hides a double-scaling bug completely -- it was the only case the old
# tests covered.
TRANSFORMS = [
    (0, 1.0, 1.0),
    (0, 2.0, 0.5),
    (90, 1.0, 1.0),
    (37, 2.0, 0.5),
    (-90, 1.6, 1.6),
]


@pytest.mark.parametrize("kind", ["text", "rect", "ellipse", "image"])
@pytest.mark.parametrize("rotation,scale_x,scale_y", TRANSFORMS)
def test_a_layer_lands_in_the_same_place_after_a_round_trip(qt_app, kind, rotation, scale_x, scale_y):
    source = DesignScene(_template())
    item = _make(source, kind)
    item.setPos(100, 60)
    item.setRotation(rotation)
    set_item_scale(item, scale_x, scale_y)
    before = _footprint(item)

    target = DesignScene(_template())
    restored = item_from_dict(target, item_to_dict(item))

    assert _footprint(restored) == before
    assert get_item_scale(restored) == (scale_x, scale_y)


@pytest.mark.parametrize("kind", ["rect", "ellipse"])
def test_a_scaled_shape_is_not_scaled_again_on_load(qt_app, kind):
    """The bug itself, stated plainly: a rectangle stretched to twice its
    width came back four times as wide."""
    source = DesignScene(_template())
    item = _make(source, kind)
    set_item_scale(item, 2.0, 0.5)
    width, height = item.rect().width(), item.rect().height()

    target = DesignScene(_template())
    restored = item_from_dict(target, item_to_dict(item))

    assert (restored.rect().width(), restored.rect().height()) == (width, height)


@pytest.mark.parametrize("kind", ["rect", "ellipse"])
def test_a_reloaded_shape_remembers_what_size_it_was_before_scaling(qt_app, kind):
    """Not just the visible size -- the base rect behind it, which is what
    the next resize is measured against. Getting the appearance right while
    leaving a wrong base would put the bug back the moment the user dragged
    a handle."""
    source = DesignScene(_template())
    item = _make(source, kind)
    original = item.rect()
    set_item_scale(item, 3.0, 3.0)

    target = DesignScene(_template())
    restored = item_from_dict(target, item_to_dict(item))
    set_item_scale(restored, 1.0, 1.0)  # as if the user resized it back

    assert round(restored.rect().width(), 3) == round(original.width(), 3)
    assert round(restored.rect().height(), 3) == round(original.height(), 3)
    assert restored.data(BASE_RECT_ROLE) is not None


@pytest.mark.parametrize("kind", ["text", "rect", "ellipse", "image"])
def test_loading_twice_over_does_not_drift(qt_app, kind):
    """Save, open, save again, open again. A per-round error of any size
    compounds, so this catches what a single round trip can hide."""
    scene = DesignScene(_template())
    item = _make(scene, kind)
    item.setPos(80, 45)
    item.setRotation(30)
    set_item_scale(item, 1.5, 0.75)
    before = _footprint(item)

    once_scene = DesignScene(_template())
    once = item_from_dict(once_scene, item_to_dict(item))
    twice_scene = DesignScene(_template())
    twice = item_from_dict(twice_scene, item_to_dict(once))

    assert _footprint(twice) == before


@pytest.mark.parametrize("kind", ["rect", "ellipse"])
def test_pasting_a_scaled_shape_does_not_double_it_either(qt_app, kind):
    """Copy/paste goes through the same two functions, so it had the same
    bug -- pasting a stretched rectangle produced a bigger one."""
    scene = DesignScene(_template())
    item = _make(scene, kind)
    item.setPos(50, 50)
    set_item_scale(item, 2.5, 2.0)
    before = _footprint(item)

    clipboard = Clipboard()
    clipboard.copy([item])
    target = DesignScene(_template())
    pasted = clipboard.paste_into(target)

    assert len(pasted) == 1
    # Position is deliberately nudged by PASTE_OFFSET_PX so a paste does not
    # land exactly on top of the original; the *size* is what was doubling.
    x, y, width, height = _footprint(pasted[0])
    assert (width, height) == before[2:]
    assert (x, y) == pytest.approx((before[0] + PASTE_OFFSET_PX, before[1] + PASTE_OFFSET_PX))


def test_an_unscaled_shape_is_unaffected_by_the_repair(qt_app):
    """The overwhelmingly common case has to be untouched: no scaling means
    the base rect and the rect are the same thing."""
    scene = DesignScene(_template())
    item = scene.add_rectangle()
    before = _footprint(item)

    target = DesignScene(_template())
    restored = item_from_dict(target, item_to_dict(item))

    assert _footprint(restored) == before
    assert restored.rect() == item.rect()


def test_a_shape_saved_with_a_zero_scale_does_not_divide_by_it(qt_app):
    """A malformed or hand-edited file should not take the loader down."""
    scene = DesignScene(_template())
    data = item_to_dict(scene.add_rectangle())
    data["scale_x"], data["scale_y"] = 0.0, 0.0

    assert item_from_dict(DesignScene(_template()), data) is not None
