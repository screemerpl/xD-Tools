from mdtools.canvas.scene import DesignScene
from mdtools.panels.properties_panel import EXTRA_MINIMUM_WIDTH_PX, PropertiesPanel
from mdtools.templates.models import DiscTemplate


def test_minimum_width_is_wider_than_the_layouts_own_natural_minimum(qt_app):
    panel = PropertiesPanel()

    assert panel.minimumWidth() == panel.minimumSizeHint().width() + EXTRA_MINIMUM_WIDTH_PX


def test_font_size_spin_is_only_visible_for_text_items(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")
    image_item = scene.add_image_from_data(_tiny_png())

    panel = PropertiesPanel()

    # the panel is never shown in this test, so isVisible() would be False
    # regardless of setVisible() calls -- isVisibleTo(panel) reflects the
    # widget's own explicit visibility, ignoring that its ancestor chain
    # was never displayed on screen.
    panel.set_item(text_item)
    assert panel.font_size_spin.isVisibleTo(panel)

    panel.set_item(image_item)
    assert not panel.font_size_spin.isVisibleTo(panel)


def test_image_hides_every_text_specific_row_including_its_label(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    image_item = scene.add_image_from_data(_tiny_png())

    panel = PropertiesPanel()
    panel.set_item(image_item)

    for widget in (panel.text_edit, panel.font_size_spin, panel.font_btn, panel.color_row):
        assert not panel.form.isRowVisible(widget), f"{widget.objectName() or widget} row should be hidden for images"


def test_rectangle_shows_color_but_not_text_rows(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    rect_item = scene.add_rectangle()

    panel = PropertiesPanel()
    panel.set_item(rect_item)

    assert panel.form.isRowVisible(panel.color_row)
    assert not panel.form.isRowVisible(panel.text_edit)
    assert not panel.form.isRowVisible(panel.font_size_spin)
    assert not panel.form.isRowVisible(panel.font_btn)


def test_text_item_shows_all_text_rows(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")

    panel = PropertiesPanel()
    panel.set_item(text_item)

    for widget in (panel.text_edit, panel.font_size_spin, panel.font_btn, panel.color_row):
        assert panel.form.isRowVisible(widget)


def test_text_field_is_a_multiline_editor(qt_app):
    from PySide6.QtWidgets import QPlainTextEdit

    panel = PropertiesPanel()
    assert isinstance(panel.text_edit, QPlainTextEdit)


def test_multiline_text_round_trips_through_the_properties_panel(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("line one\nline two")

    panel = PropertiesPanel()
    panel.set_item(text_item)

    assert panel.text_edit.toPlainText() == "line one\nline two"

    panel.text_edit.setPlainText("changed one\nchanged two\nchanged three")

    assert text_item.toPlainText() == "changed one\nchanged two\nchanged three"


def test_changing_font_size_spin_resizes_the_text_item_font(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")

    panel = PropertiesPanel()
    panel.set_item(text_item)
    panel.font_size_spin.setValue(48)

    assert text_item.font().pointSizeF() == 48


def test_font_button_applies_the_chosen_font(qt_app, monkeypatch):
    from PySide6.QtGui import QFont

    from mdtools.panels import properties_panel as properties_panel_module

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")

    chosen = QFont("Courier New", 22)
    # NOTE: PySide6's QFontDialog.getFont returns (ok, font), not (font, ok) --
    # confirmed empirically against the real dialog (see
    # test_font_button_works_with_the_real_qfontdialog below, which exercises
    # the actual API instead of a stub and is what caught this the first time).
    monkeypatch.setattr(
        properties_panel_module.QFontDialog, "getFont", staticmethod(lambda *a, **k: (True, chosen))
    )

    panel = PropertiesPanel()
    panel.set_item(text_item)
    panel.font_btn.click()

    assert text_item.font().family() == "Courier New"
    assert text_item.font().pointSizeF() == 22
    assert panel.font_size_spin.value() == 22


def test_font_button_applies_bold_italic_underline_and_strikeout_too(qt_app, monkeypatch):
    """The Font... dialog lets the user set more than family/size -- bold,
    italic, underline, strikeout, weight. All of that must reach the actual
    item (the on-canvas preview), not just family/size."""
    from PySide6.QtGui import QFont

    from mdtools.panels import properties_panel as properties_panel_module

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")

    chosen = QFont("Courier New", 22)
    chosen.setBold(True)
    chosen.setItalic(True)
    chosen.setUnderline(True)
    chosen.setStrikeOut(True)
    monkeypatch.setattr(properties_panel_module.QFontDialog, "getFont", staticmethod(lambda *a, **k: (True, chosen)))

    panel = PropertiesPanel()
    panel.set_item(text_item)
    panel.font_btn.click()

    assert text_item.font().bold()
    assert text_item.font().italic()
    assert text_item.font().underline()
    assert text_item.font().strikeOut()


def test_undoing_a_font_change_restores_the_full_previous_style(qt_app, monkeypatch):
    from PySide6.QtGui import QFont, QUndoStack

    from mdtools.panels import properties_panel as properties_panel_module

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")
    original_font = text_item.font()
    original_font.setItalic(True)
    text_item.setFont(original_font)

    bold_font = QFont("Courier New", 22)
    bold_font.setBold(True)
    monkeypatch.setattr(
        properties_panel_module.QFontDialog, "getFont", staticmethod(lambda *a, **k: (True, bold_font))
    )

    panel = PropertiesPanel()
    panel.undo_stack = QUndoStack()
    panel.set_item(text_item)
    panel.font_btn.click()
    assert text_item.font().bold()

    panel.undo_stack.undo()

    assert not text_item.font().bold()
    assert text_item.font().italic()  # the pre-existing style, not just family/size, came back


def test_font_button_works_with_the_real_qfontdialog(qt_app):
    """Drives the actual QFontDialog (accepting it via a timer) instead of
    stubbing the static method -- a stub only checks our own assumption
    about getFont()'s return order, not whether that assumption matches
    the real API. This test is what caught getFont() actually returning
    (ok, font), not (font, ok), which silently crashed inside the button's
    click handler (swallowed by Qt's slot exception handling) and made the
    Font... button look like it simply did nothing."""
    import sys

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QFontDialog

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")

    panel = PropertiesPanel()
    panel.set_item(text_item)

    def accept_the_dialog():
        for widget in QApplication.instance().topLevelWidgets():
            if isinstance(widget, QFontDialog):
                widget.setCurrentFont(_a_real_installed_font())
                widget.accept()
                return

    # a wrong return-tuple order crashes inside the click handler; Qt's slot
    # dispatch swallows that exception (prints it, keeps running) rather
    # than raising here, so the test must capture it via excepthook instead
    # of relying on an exception propagating out of font_btn.click().
    caught = []
    original_hook = sys.excepthook
    sys.excepthook = lambda *exc_info: caught.append(exc_info)
    try:
        QTimer.singleShot(50, accept_the_dialog)
        panel.font_btn.click()  # blocks until accept_the_dialog() runs
    finally:
        sys.excepthook = original_hook

    assert not caught, f"applying the chosen font raised: {caught}"
    assert text_item.font().family() == _a_real_installed_font().family()


def _a_real_installed_font():
    from PySide6.QtGui import QFont, QFontDatabase

    families = QFontDatabase.families()
    return QFont(families[0]) if families else QFont()


def test_reset_to_default_clears_rotation_and_scale(qt_app):
    from mdtools.canvas.items import get_item_scale, set_item_scale

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_rectangle()
    item.setRotation(42)
    set_item_scale(item, 2.5, 0.4)

    panel = PropertiesPanel()
    panel.set_item(item)
    panel.reset_btn.click()

    assert item.rotation() == 0
    assert get_item_scale(item) == (1.0, 1.0)


def test_reset_to_default_restores_rectangle_fill_color(qt_app):
    from PySide6.QtGui import QColor

    from mdtools.canvas.scene import DEFAULT_RECT_FILL_HEX

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_rectangle()
    brush = item.brush()
    brush.setColor(QColor("purple"))
    item.setBrush(brush)

    panel = PropertiesPanel()
    panel.set_item(item)
    panel.reset_btn.click()

    assert item.brush().color().name() == QColor(DEFAULT_RECT_FILL_HEX).name()


def test_reset_to_default_resets_text_to_projects_default_style(qt_app):
    from PySide6.QtGui import QFont

    from mdtools.project import TextStyle

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_text("hello")
    item.setRotation(30)

    default_font = QFont("Courier New")
    default_font.setPointSizeF(30.0)
    default_font.setBold(True)
    default_font.setItalic(True)

    panel = PropertiesPanel()
    panel.set_default_text_style(TextStyle(font_spec=default_font.toString(), color="#00ff00"))
    panel.set_item(item)
    panel.reset_btn.click()

    assert item.rotation() == 0
    assert item.font().family() == "Courier New"
    assert item.font().pointSizeF() == 30.0
    assert item.font().bold()
    assert item.font().italic()
    assert item.defaultTextColor().name() == "#00ff00"


def test_changing_font_size_updates_the_panels_remembered_default_and_emits_signal(qt_app):
    from PySide6.QtGui import QFont

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    item = scene.add_text("hello")

    panel = PropertiesPanel()
    panel.set_item(item)

    received = []
    panel.text_style_changed.connect(received.append)
    panel.font_size_spin.setValue(31)

    assert len(received) == 1

    received_font = QFont()
    received_font.fromString(received[0].font_spec)
    assert received_font.pointSizeF() == 31

    default_font = QFont()
    default_font.fromString(panel._default_text_style.font_spec)
    assert default_font.pointSizeF() == 31


def test_picking_a_color_on_a_text_item_updates_the_default_but_shape_color_does_not(qt_app, monkeypatch):
    from mdtools.panels import properties_panel as properties_panel_module

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")
    rect_item = scene.add_rectangle()

    from PySide6.QtGui import QColor

    monkeypatch.setattr(properties_panel_module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("#123456")))

    panel = PropertiesPanel()
    panel.set_item(text_item)
    panel.color_btn.click()
    assert panel._default_text_style.color == "#123456"

    # a color change on a *shape* (not text) must not touch the remembered
    # text default -- it's a per-item fill, unrelated to future text styling.
    panel.set_item(rect_item)
    panel.color_btn.click()
    assert panel._default_text_style.color == "#123456"


def test_color_dialog_is_preseeded_with_the_text_items_current_color(qt_app, monkeypatch):
    from PySide6.QtGui import QColor

    from mdtools.panels import properties_panel as properties_panel_module

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")
    text_item.setDefaultTextColor(QColor("#00ff00"))

    captured = {}

    def fake_get_color(*args, **kwargs):
        captured["initial"] = args[0] if args else kwargs.get("initial")
        return QColor("#00ff00")

    monkeypatch.setattr(properties_panel_module.QColorDialog, "getColor", staticmethod(fake_get_color))

    panel = PropertiesPanel()
    panel.set_item(text_item)
    panel.color_btn.click()

    assert captured["initial"].name() == "#00ff00"


def test_color_dialog_is_preseeded_with_the_shapes_current_fill_color(qt_app, monkeypatch):
    from PySide6.QtGui import QColor

    from mdtools.panels import properties_panel as properties_panel_module

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    rect_item = scene.add_rectangle()
    original_name = rect_item.brush().color().name()

    captured = {}

    def fake_get_color(*args, **kwargs):
        captured["initial"] = args[0] if args else kwargs.get("initial")
        return QColor(original_name)

    monkeypatch.setattr(properties_panel_module.QColorDialog, "getColor", staticmethod(fake_get_color))

    panel = PropertiesPanel()
    panel.set_item(rect_item)
    panel.color_btn.click()

    assert captured["initial"].name() == original_name


def test_picking_a_fill_color_also_updates_the_frame_to_match(qt_app, monkeypatch):
    from PySide6.QtGui import QColor

    from mdtools.panels import properties_panel as properties_panel_module

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    rect_item = scene.add_rectangle()

    monkeypatch.setattr(
        properties_panel_module.QColorDialog, "getColor", staticmethod(lambda *a, **k: QColor("red"))
    )

    panel = PropertiesPanel()
    panel.set_item(rect_item)
    panel.color_btn.click()

    assert rect_item.brush().color().name() == QColor("red").name()
    assert rect_item.pen().color().name() == QColor("red").name()


def test_probe_button_emits_a_request_signal_instead_of_opening_a_dialog(qt_app):
    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    rect_item = scene.add_rectangle()

    panel = PropertiesPanel()
    panel.set_item(rect_item)

    requested = []
    panel.probe_color_requested.connect(lambda: requested.append(1))
    panel.probe_btn.click()

    assert requested == [1]


def test_apply_probed_color_updates_a_rectangles_fill_and_frame(qt_app):
    from PySide6.QtGui import QColor

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    rect_item = scene.add_rectangle()

    panel = PropertiesPanel()
    panel.set_item(rect_item)
    panel.apply_probed_color(QColor("lime"))

    assert rect_item.brush().color().name() == QColor("lime").name()
    assert rect_item.pen().color().name() == QColor("lime").name()


def test_apply_probed_color_updates_a_text_items_color(qt_app):
    from PySide6.QtGui import QColor

    scene = DesignScene(DiscTemplate(name="t", width_mm=37.0, height_mm=52.0))
    text_item = scene.add_text("hello")

    panel = PropertiesPanel()
    panel.set_item(text_item)
    panel.apply_probed_color(QColor("lime"))

    assert text_item.defaultTextColor().name() == QColor("lime").name()


def test_apply_probed_color_does_nothing_without_a_colorable_item_selected(qt_app):
    from PySide6.QtGui import QColor

    panel = PropertiesPanel()
    panel.apply_probed_color(QColor("lime"))  # no selected item -- must not raise


def _tiny_png() -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("blue"))
    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(device, "PNG")
    device.close()
    return bytes(buffer)
