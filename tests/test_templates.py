from mdtools.templates import registry
from mdtools.templates.models import CoverTemplate, DiscTemplate


def test_load_templates_returns_builtin_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    templates = registry.load_templates()
    assert templates["disc"] and isinstance(templates["disc"][0], DiscTemplate)
    assert templates["cover"] and isinstance(templates["cover"][0], CoverTemplate)
    assert templates["disc"][0].builtin is True
    assert templates["cover"][0].builtin is True


def test_builtin_defaults_include_a_disc_with_slider_variant(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    templates = registry.load_templates()
    with_slider = next(t for t in templates["disc"] if t.slider_width_mm > 0)
    assert with_slider.slider_width_mm == 27.5
    assert with_slider.slider_height_mm == 17.5
    assert with_slider.slider_corner_radius_mm == 2.5
    assert with_slider.builtin is True
    assert with_slider.verified is True


def test_builtin_defaults_include_a_full_disc_label_variant(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    templates = registry.load_templates()
    full_label = next(t for t in templates["disc"] if t.shape == "full_label")
    assert full_label.width_mm == 69.4
    assert full_label.height_mm == 66.4
    assert full_label.corner_radius_mm == 4.0
    assert full_label.slider_notch_width_mm == 27.5
    assert full_label.slider_notch_height_mm == 17.5
    assert full_label.slider_notch_corner_radius_mm == 2.5
    # The cut's own edges, which is what these two numbers exist to place:
    # 23.5mm below the label's top for the notch, 62 for the end of the
    # channel the shutter sweeps through -- both measured off a cut label.
    assert full_label.slider_notch_top_mm - full_label.slider_notch_buffer_mm == 23.5
    assert full_label.slider_notch_buffer_mm == 0.8
    channel_end = (
        full_label.slider_notch_top_mm
        + full_label.slider_notch_height_mm
        + full_label.slider_notch_buffer_mm
        + full_label.slider_travel_mm
    )
    assert round(channel_end, 6) == 62.0
    assert full_label.builtin is True
    assert full_label.verified is True


def test_builtin_defaults_include_a_full_disc_label_with_slider_variant(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    templates = registry.load_templates()
    with_slider = next(t for t in templates["disc"] if t.shape == "full_label" and t.slider_width_mm > 0)
    assert with_slider.slider_width_mm == 27.5
    assert with_slider.slider_height_mm == 17.5
    assert with_slider.slider_corner_radius_mm == 2.5
    assert with_slider.slider_notch_width_mm == 27.5  # the notch it's nested inside matches its own size
    assert with_slider.builtin is True
    assert with_slider.verified is True


def test_disc_templates_default_to_the_sticker_shape():
    assert DiscTemplate(name="d", width_mm=1, height_mm=1).shape == "sticker"


def test_save_and_reload_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    templates = registry.load_templates()
    templates["disc"][0].width_mm = 70.0
    registry.save_templates(templates)

    reloaded = registry.load_templates()
    assert reloaded["disc"][0].width_mm == 70.0


def test_templates_default_to_no_saved_items():
    assert DiscTemplate(name="d", width_mm=1, height_mm=1).items == []
    assert CoverTemplate(name="c", width_mm=1, height_mm=1).items == []


def test_saved_items_round_trip_through_the_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    templates = registry.load_templates()
    fake_item = {"type": "text", "text": "hello", "font_spec": "Arial,12", "color": "#000000",
                 "x": 0.0, "y": 0.0, "rotation": 0.0, "scale_x": 1.0, "scale_y": 1.0, "z": 0.0}
    templates["disc"].append(DiscTemplate(name="Precreated", width_mm=37.0, height_mm=52.0, items=[fake_item]))
    registry.save_templates(templates)

    reloaded = registry.load_templates()
    saved = next(t for t in reloaded["disc"] if t.name == "Precreated")
    assert saved.items == [fake_item]
