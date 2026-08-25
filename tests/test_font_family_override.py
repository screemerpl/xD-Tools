"""canvas.scene.font_family_override() -- the mechanism behind Toolbar >
"Regenerate with Font...": every DesignScene.add_text() call made while it
is active starts the new item on the given font family, and it restores
the previous state (even nested) once the `with` block exits.
"""

from __future__ import annotations

from mdtools.canvas.scene import DesignScene, font_family_override
from mdtools.templates.models import DiscTemplate


def _scene() -> DesignScene:
    return DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))


def test_add_text_uses_the_application_default_outside_any_override(qt_app):
    scene = _scene()
    item = scene.add_text("hello")
    assert item.font().family() != "Courier New"


def test_add_text_uses_the_overridden_family_while_active(qt_app):
    scene = _scene()
    with font_family_override("Courier New"):
        item = scene.add_text("hello")
    assert item.font().family() == "Courier New"


def test_the_override_is_restored_after_the_with_block(qt_app):
    with font_family_override("Courier New"):
        pass
    scene = _scene()
    item = scene.add_text("hello")
    assert item.font().family() != "Courier New"


def test_nested_overrides_restore_the_outer_one(qt_app):
    scene = _scene()
    with font_family_override("Courier New"):
        with font_family_override("Arial"):
            inner = scene.add_text("inner")
        outer = scene.add_text("outer")
    assert inner.font().family() == "Arial"
    assert outer.font().family() == "Courier New"


def test_none_disables_the_override_without_erroring(qt_app):
    scene = _scene()
    with font_family_override(None):
        item = scene.add_text("hello")
    assert item.font() is not None  # just proving this didn't raise


def test_seed_disc_defaults_text_also_picks_up_the_override(qt_app):
    """seed_disc_defaults()'s insertion-mark triangle/label create their
    text through add_text() like everything else -- the whole point of
    hooking the override in at that one shared method rather than in
    jcard_layout._text() (which they don't go through) is that this needs
    no special-casing to also work."""
    with font_family_override("Courier New"):
        scene = _scene()
        scene.seed_disc_defaults()

    from mdtools.canvas.items import DesignTextItem

    text_items = [i for i in scene.items() if isinstance(i, DesignTextItem)]
    assert text_items
    assert all(item.font().family() == "Courier New" for item in text_items)
