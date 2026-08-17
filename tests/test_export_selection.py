from mdtools.canvas.scene import DesignScene
from mdtools.io.png_export import export_png
from mdtools.io.svg_export import export_svg
from mdtools.templates.models import DiscTemplate


def _scene_with_selected_item():
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_rectangle()
    item.setSelected(True)
    return scene, item


def test_png_export_deselects_during_render_and_restores_selection_after(qt_app, tmp_path, monkeypatch):
    scene, item = _scene_with_selected_item()

    captured = {}
    original_render = scene.render

    def spy_render(*args, **kwargs):
        captured["selected_during_render"] = list(scene.selectedItems())
        return original_render(*args, **kwargs)

    monkeypatch.setattr(scene, "render", spy_render)

    export_png(scene, tmp_path / "out.png", dpi=96)

    assert captured["selected_during_render"] == []
    assert item.isSelected()  # restored once export is done


def test_svg_export_deselects_during_render_and_restores_selection_after(qt_app, tmp_path, monkeypatch):
    scene, item = _scene_with_selected_item()

    captured = {}
    original_render = scene.render

    def spy_render(*args, **kwargs):
        captured["selected_during_render"] = list(scene.selectedItems())
        return original_render(*args, **kwargs)

    monkeypatch.setattr(scene, "render", spy_render)

    export_svg(scene, tmp_path / "out.svg")

    assert captured["selected_during_render"] == []
    assert item.isSelected()
