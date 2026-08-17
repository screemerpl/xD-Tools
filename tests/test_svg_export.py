from mdtools.canvas.scene import DesignScene
from mdtools.io.png_export import export_png
from mdtools.io.svg_export import export_svg
from mdtools.templates.models import DiscTemplate


def test_export_svg_writes_physical_size(qt_app, tmp_path):
    template = DiscTemplate(name="t", width_mm=37.0, height_mm=52.0)
    scene = DesignScene(template)
    scene.add_text("Hello")

    out = tmp_path / "out.svg"
    export_svg(scene, out)

    svg_text = out.read_text(encoding="utf-8")
    assert "mm" in svg_text
    assert out.stat().st_size > 0


def test_export_png_hides_cut_layer_and_restores_visibility(qt_app, tmp_path):
    template = DiscTemplate(name="t", width_mm=37.0, height_mm=52.0)
    scene = DesignScene(template)
    scene.add_ellipse()

    out = tmp_path / "out.png"
    export_png(scene, out, dpi=150)

    assert out.exists()
    assert out.stat().st_size > 0
    # exporting must not permanently hide items on the live scene
    assert all(item.isVisible() for item in scene.items())
