from PySide6.QtCore import QPointF

from mdtools.canvas.scene import DesignScene
from mdtools.constants import mm_to_px
from mdtools.templates.models import DiscTemplate


def _full_label(**overrides) -> DiscTemplate:
    defaults = dict(
        name="full label",
        width_mm=69.4,
        height_mm=66.4,
        shape="full_label",
        corner_radius_mm=4.0,
        slider_notch_width_mm=27.5,
        slider_notch_height_mm=17.5,
        slider_notch_corner_radius_mm=2.5,
        slider_notch_top_mm=25.2,
        slider_notch_buffer_mm=0.8,
        slider_travel_mm=18.0,
    )
    defaults.update(overrides)
    return DiscTemplate(**defaults)


def test_full_label_is_a_single_cut_shape(qt_app):
    scene = DesignScene(_full_label())
    assert len(scene.cut_only_items()) == 1


def test_scene_rect_matches_the_label_size_not_an_additive_slider(qt_app):
    scene = DesignScene(_full_label())
    rect = scene.sceneRect()
    assert rect.width() == mm_to_px(69.4) + 20
    assert rect.height() == mm_to_px(66.4) + 20


def test_notch_and_travel_channel_are_cut_out_of_the_label(qt_app):
    scene = DesignScene(_full_label())
    outline_path = scene.cut_only_items()[0].path()

    # base slider footprint (before the 0.8mm buffer): x 41.9..69.4 (flush
    # right), y 25.2..42.7 (26mm from the MD's top, minus the label's own
    # 0.8mm margin)
    slider_center = QPointF(mm_to_px((41.9 + 69.4) / 2), mm_to_px((25.2 + 42.7) / 2))
    assert not outline_path.contains(slider_center)

    # the buffer physically widens the notch by 0.8mm on top/bottom/left --
    # a point just inside that extra margin (buffered left edge is 41.1)
    # must also be cut away, not just the unbuffered footprint
    buffer_zone_point = QPointF(mm_to_px(41.5), mm_to_px(33.95))
    assert not outline_path.contains(buffer_zone_point)

    # just outside the buffer, still solid material
    solid_left_of_notch = QPointF(mm_to_px(40.0), mm_to_px(33.95))
    assert outline_path.contains(solid_left_of_notch)

    # the travel channel continues the cut 18mm below the buffered notch
    # (buffered notch bottom = 42.7 + 0.8 = 43.5; channel runs to 61.5)
    channel_point = QPointF(mm_to_px(55.0), mm_to_px(50.0))
    assert not outline_path.contains(channel_point)

    # past the end of the travel channel, material resumes
    below_channel = QPointF(mm_to_px(55.0), mm_to_px(63.0))
    assert outline_path.contains(below_channel)

    # comfortably elsewhere on the label, well clear of the notch
    elsewhere = QPointF(mm_to_px(10.0), mm_to_px(10.0))
    assert outline_path.contains(elsewhere)


def test_no_notch_when_dimensions_are_zero(qt_app):
    scene = DesignScene(_full_label(slider_notch_width_mm=0.0, slider_notch_height_mm=0.0))
    outline_path = scene.cut_only_items()[0].path()

    slider_center = QPointF(mm_to_px((41.9 + 69.4) / 2), mm_to_px((25.2 + 42.7) / 2))
    assert outline_path.contains(slider_center)  # no hole -- should be solid material


def test_template_clip_path_excludes_the_notch(qt_app):
    scene = DesignScene(_full_label())
    clip = scene.template_clip_path()

    slider_center = QPointF(mm_to_px((41.9 + 69.4) / 2), mm_to_px((25.2 + 42.7) / 2))
    elsewhere = QPointF(mm_to_px(10.0), mm_to_px(10.0))
    assert not clip.contains(slider_center)
    assert clip.contains(elsewhere)


def _full_label_with_slider(**overrides) -> DiscTemplate:
    return _full_label(slider_width_mm=27.5, slider_height_mm=17.5, slider_corner_radius_mm=2.5, **overrides)


def test_with_slider_variant_adds_a_second_independent_cut_shape(qt_app):
    scene = DesignScene(_full_label_with_slider())
    assert len(scene.cut_only_items()) == 2


def test_slider_sticker_is_nested_inside_the_notch_not_beside_the_disc(qt_app):
    scene = DesignScene(_full_label_with_slider())
    main_path, slider_path = (i.path() for i in scene._outline_items)

    # the sticker's own footprint (27.5x17.5, flush right, top at 25.2mm --
    # same as the notch's unbuffered position) sits entirely within the
    # notch's void, not off to the side of the whole disc
    slider_center = QPointF(mm_to_px((41.9 + 69.4) / 2), mm_to_px((25.2 + 42.7) / 2))
    assert slider_path.contains(slider_center)
    assert not main_path.contains(slider_center)

    # the 0.8mm buffer clearance around the sticker (inside the notch, but
    # outside the sticker's own footprint) belongs to neither shape
    buffer_zone_point = QPointF(mm_to_px(41.5), mm_to_px(33.95))
    assert not main_path.contains(buffer_zone_point)
    assert not slider_path.contains(buffer_zone_point)


def test_scene_rect_is_unaffected_by_the_nested_slider_sticker(qt_app):
    with_slider = DesignScene(_full_label_with_slider())
    without_slider = DesignScene(_full_label())
    assert with_slider.sceneRect() == without_slider.sceneRect()


def test_template_clip_path_covers_the_nested_slider_sticker(qt_app):
    scene = DesignScene(_full_label_with_slider())
    clip = scene.template_clip_path()

    slider_center = QPointF(mm_to_px((41.9 + 69.4) / 2), mm_to_px((25.2 + 42.7) / 2))
    assert clip.contains(slider_center)


def test_svg_export_includes_both_shapes_for_the_with_slider_variant(qt_app, tmp_path):
    from mdtools.io.svg_export import export_svg

    scene = DesignScene(_full_label_with_slider())
    out = tmp_path / "full_label_slider.svg"
    export_svg(scene, out)

    svg_text = out.read_text(encoding="utf-8")
    assert svg_text.count("<path") >= 2
