"""Templates > "Change Template for This Page...".

Until this existed a template could only be picked when the project was
created, so choosing the wrong one meant starting over. It empties the page
rather than migrating it -- item coordinates mean nothing across a template
of a different size and shape -- which is why the menu action confirms first
and this test file pins the emptying down.
"""

from mdtools.app_window import MainWindow
from mdtools.canvas.scene import DesignScene
from mdtools.commands import AddItemCommand
from mdtools.io.project_io import item_to_dict
from mdtools.project import PAGE_COVER, PAGE_DISC
from mdtools.templates.models import CoverTemplate, DiscTemplate


def _window() -> MainWindow:
    return MainWindow(show_startup_dialog=False)


def _sticker(name: str = "small sticker") -> DiscTemplate:
    return DiscTemplate(name=name, width_mm=37.0, height_mm=52.0, chamfer_mm=3.0, fillet_mm=1.0)


def _full_label(name: str = "full label", items: list | None = None) -> DiscTemplate:
    return DiscTemplate(
        name=name,
        width_mm=69.4,
        height_mm=66.4,
        shape="full_label",
        corner_radius_mm=4.0,
        slider_width_mm=27.5,
        slider_height_mm=17.5,
        slider_corner_radius_mm=2.5,
        slider_notch_width_mm=27.5,
        slider_notch_height_mm=17.5,
        slider_notch_corner_radius_mm=2.5,
        slider_notch_top_mm=25.2,
        items=items or [],
    )


def test_the_page_ends_up_on_the_new_template(qt_app):
    window = _window()

    window.apply_template(PAGE_DISC, _full_label())

    assert window.project.pages[PAGE_DISC].template.name == "full label"


def _texts_on(scene) -> list[str]:
    return [item.toPlainText() for item in scene.print_items() if hasattr(item, "toPlainText")]


def test_the_users_own_layers_are_removed(qt_app):
    """Every layer the user put on the page goes, as the confirmation warns
    -- item coordinates mean nothing across a differently shaped template."""
    window = _window()
    window.project.pages[PAGE_DISC].add_text("Something the user drew")

    window.apply_template(PAGE_DISC, _full_label())

    assert "Something the user drew" not in _texts_on(window.project.pages[PAGE_DISC])


def test_the_insertion_mark_is_re_seeded_onto_the_new_disc_template(qt_app):
    """It is a starting point the user adjusts anyway, so leaving the page
    bare would only mean retyping it -- same layers File > New gives."""
    window = _window()

    window.apply_template(PAGE_DISC, _sticker("another sticker"))

    texts = _texts_on(window.project.pages[PAGE_DISC])
    assert "▲" in texts
    assert "INSERT THIS END" in texts


def test_a_cover_page_gets_no_insertion_mark(qt_app):
    """Seeding is a disc-label convention; a J-card has no "this end first"."""
    window = _window()

    window.apply_template(PAGE_COVER, CoverTemplate(name="plain cover", width_mm=126.0, height_mm=73.0))

    assert window.project.pages[PAGE_COVER].print_items() == []


def test_a_template_carrying_its_own_layers_still_gets_them(qt_app):
    """Same behaviour File > New has for a saved-as-template page.

    The saved item is produced by item_to_dict rather than written out by
    hand, so this cannot drift out of step with the real schema."""
    window = _window()
    scratch = DesignScene(_sticker())
    saved = [item_to_dict(scratch.add_text("From the template"))]

    window.apply_template(PAGE_DISC, _full_label(items=saved))

    assert len(window.project.pages[PAGE_DISC].print_items()) == 1


def test_the_other_page_is_untouched(qt_app):
    window = _window()
    cover_scene = window.project.pages[PAGE_COVER]

    window.apply_template(PAGE_DISC, _full_label())

    assert window.project.pages[PAGE_COVER] is cover_scene


def test_the_undo_history_is_reset(qt_app):
    """Its commands reference items on the scene being discarded -- undoing
    one afterwards would try to put them back into a scene that is gone."""
    window = _window()
    scene = window.project.pages[PAGE_DISC]
    window.undo_stack.push(AddItemCommand(scene, scene.add_text("x"), "add"))
    assert window.undo_stack.count() > 0

    window.apply_template(PAGE_DISC, _full_label())

    assert window.undo_stack.count() == 0


def test_the_discarded_scenes_id_is_forgotten(qt_app):
    """id() is reused after garbage collection -- a stale entry here would
    make some later scene silently skip connecting selectionChanged."""
    window = _window()
    old_id = id(window.project.pages[PAGE_DISC])
    assert old_id in window._connected_scenes

    window.apply_template(PAGE_DISC, _full_label())

    assert old_id not in window._connected_scenes or id(window.project.pages[PAGE_DISC]) == old_id


def test_the_view_follows_the_new_scene_for_the_current_page(qt_app):
    window = _window()

    window.apply_template(PAGE_DISC, _full_label())

    assert window.view.scene() is window.project.pages[PAGE_DISC]
