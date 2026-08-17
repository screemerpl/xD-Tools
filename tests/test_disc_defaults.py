from PySide6.QtWidgets import QGraphicsTextItem

from mdtools.canvas.scene import DesignScene
from mdtools.templates.models import DiscTemplate


def test_seed_disc_defaults_adds_editable_triangle_and_label(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    scene.seed_disc_defaults()

    items = scene.print_items()
    assert len(items) == 2
    assert all(isinstance(i, QGraphicsTextItem) for i in items)

    texts = {i.toPlainText() for i in items}
    assert texts == {"▲", "INSERT THIS END"}

    for item in items:
        assert item.flags() & item.GraphicsItemFlag.ItemIsMovable
        assert item.flags() & item.GraphicsItemFlag.ItemIsSelectable


def test_new_project_seeds_disc_defaults_but_not_cover(qt_app):
    from mdtools.app_window import MainWindow
    from mdtools.project import PAGE_COVER, PAGE_DISC

    win = MainWindow(show_startup_dialog=False)
    disc_texts = {i.toPlainText() for i in win.project.pages[PAGE_DISC].print_items()}
    assert "INSERT THIS END" in disc_texts

    assert win.project.pages[PAGE_COVER].print_items() == []
