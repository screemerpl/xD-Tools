from mdtools.templates import registry, template_dialog
from mdtools.templates.template_dialog import TemplateManagerDialog


def test_builtin_template_cannot_be_deleted(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    # _delete_selected shows a blocking modal QMessageBox when refusing to
    # delete a built-in template; stub it out so the test doesn't hang.
    monkeypatch.setattr(template_dialog.QMessageBox, "information", lambda *a, **k: None)

    dialog = TemplateManagerDialog()
    before = len(dialog.templates["disc"])

    dialog.list_widget.setCurrentRow(0)  # the built-in disc template
    assert dialog.del_btn.isEnabled() is False

    dialog._delete_selected()
    assert len(dialog.templates["disc"]) == before


def test_user_added_template_can_be_deleted(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()
    dialog._add_template("disc")

    # adding should have selected the template it just created
    kind, added_template = dialog.list_widget.currentItem().data(1)
    assert kind == "disc"
    assert added_template.builtin is False
    assert dialog.del_btn.isEnabled() is True

    before = len(dialog.templates["disc"])
    dialog._delete_selected()
    assert len(dialog.templates["disc"]) == before - 1


def test_disc_with_slider_editor_exposes_and_updates_slider_fields(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QDoubleSpinBox

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()

    row = next(
        i
        for i in range(dialog.list_widget.count())
        if dialog.list_widget.item(i).data(1)[1].slider_width_mm > 0
    )
    dialog.list_widget.setCurrentRow(row)
    _, template = dialog.list_widget.item(row).data(1)

    spins = dialog.editor_container.findChildren(QDoubleSpinBox)
    slider_width_spin = next(s for s in spins if s.value() == template.slider_width_mm)
    slider_width_spin.setValue(30.0)

    assert template.slider_width_mm == 30.0


def test_shape_combo_toggles_between_sticker_and_full_label_fields(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QComboBox, QDoubleSpinBox

    from mdtools.templates.models import DiscTemplate

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()
    dialog.templates["disc"].append(
        DiscTemplate(name="Full", width_mm=69.4, height_mm=66.4, shape="full_label", slider_notch_top_mm=25.2)
    )
    dialog._refresh_list(select_index=len(dialog.templates["disc"]) - 1)

    # identified by what it holds, not by how many entries it has -- the
    # editor grew a second combo (Medium) and the shape combo a third entry.
    shape_combo = next(
        c
        for c in dialog.editor_container.findChildren(QComboBox)
        if "sticker" in [c.itemData(i) for i in range(c.count())]
    )
    assert shape_combo.currentData() == "full_label"

    form = shape_combo.parentWidget().layout()
    chamfer_spin = next(s for s in dialog.editor_container.findChildren(QDoubleSpinBox) if s.value() == 3.0)
    notch_top_spin = next(s for s in dialog.editor_container.findChildren(QDoubleSpinBox) if s.value() == 25.2)

    assert form.isRowVisible(notch_top_spin) is True
    assert form.isRowVisible(chamfer_spin) is False

    shape_combo.setCurrentIndex(0)  # switch to "sticker"
    assert dialog.templates["disc"][-1].shape == "sticker"
    assert form.isRowVisible(chamfer_spin) is True
    assert form.isRowVisible(notch_top_spin) is False

    shape_combo.setCurrentIndex(1)  # back to "full_label"
    assert dialog.templates["disc"][-1].shape == "full_label"
    assert form.isRowVisible(notch_top_spin) is True
    assert form.isRowVisible(chamfer_spin) is False


def test_editor_shows_a_hint_when_the_template_has_pre_made_layers(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QLabel

    from mdtools.templates.models import DiscTemplate

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()
    dialog.templates["disc"].append(
        DiscTemplate(name="Precreated", width_mm=37.0, height_mm=52.0, items=[{"type": "text"}, {"type": "text"}])
    )
    dialog._refresh_list(select_index=len(dialog.templates["disc"]) - 1)

    labels = [w.text() for w in dialog.editor_container.findChildren(QLabel)]
    assert any("2" in text for text in labels)


def test_editor_shows_no_hint_for_a_plain_shape_only_template(qt_app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QLabel

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()
    dialog.list_widget.setCurrentRow(0)  # the plain built-in disc template, no saved items

    labels = [w.text() for w in dialog.editor_container.findChildren(QLabel)]
    assert not any("pre-made" in text for text in labels)


def test_the_dialog_actually_has_its_save_and_cancel_buttons(qt_app, tmp_path, monkeypatch):
    """They were built and then thrown away: the layout holding them was
    handed to setLayout() on a dialog that already had one, which Qt
    refuses. The window could only be closed with the X -- so every
    template edit was silently discarded, and there was no save button to
    find ("gdzie jest przycisk zapisu?")."""
    from PySide6.QtWidgets import QDialogButtonBox

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()

    box = dialog.findChild(QDialogButtonBox)
    assert box is not None, "the button row never reached the dialog"
    assert box.button(QDialogButtonBox.StandardButton.Save) is not None
    assert box.button(QDialogButtonBox.StandardButton.Cancel) is not None


def test_saving_writes_the_edits_to_the_template_file(qt_app, tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()
    dialog.list_widget.setCurrentRow(0)
    _kind, template = dialog.list_widget.item(0).data(1)
    template.name = "Renamed By The Test"

    dialog._on_accept()

    assert any(t.name == "Renamed By The Test" for t in registry.load_templates()["disc"])


def test_the_medium_filter_narrows_the_list(qt_app, tmp_path, monkeypatch):
    from mdtools.project import MEDIUM_CD

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()
    everything = dialog.list_widget.count()

    dialog.medium_filter.setCurrentIndex(dialog.medium_filter.findData(MEDIUM_CD))

    shown = [dialog.list_widget.item(i).data(1)[1] for i in range(dialog.list_widget.count())]
    assert shown and all(t.medium == MEDIUM_CD for t in shown)
    assert len(shown) < everything


def test_a_new_template_takes_the_medium_being_filtered_for(qt_app, tmp_path, monkeypatch):
    """And is selected by identity, not by a row worked out from list
    arithmetic -- which a filtered list makes wrong."""
    from mdtools.project import MEDIUM_CD

    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    dialog = TemplateManagerDialog()
    dialog.medium_filter.setCurrentIndex(dialog.medium_filter.findData(MEDIUM_CD))

    dialog._add_template("cover")

    _kind, template = dialog.list_widget.currentItem().data(1)
    assert template.medium == MEDIUM_CD
    assert template.name == dialog.tr("New Cover")
