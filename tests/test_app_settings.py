from mdtools import app_settings
from mdtools.constants import mm_to_px, px_to_mm

# Settings are isolated to a per-test tmp file automatically by conftest.py's
# autouse _isolated_app_settings fixture -- no local fixture needed here.


def test_defaults_before_anything_is_set():
    assert app_settings.screen_dpi() == app_settings.DEFAULT_SCREEN_DPI
    assert app_settings.default_export_dpi() == app_settings.DEFAULT_EXPORT_DPI
    assert app_settings.bake_dpi() == app_settings.DEFAULT_BAKE_DPI


def test_setters_persist_and_are_read_back():
    app_settings.set_screen_dpi(120.0)
    app_settings.set_default_export_dpi(600.0)
    app_settings.set_bake_dpi(1200.0)

    assert app_settings.screen_dpi() == 120.0
    assert app_settings.default_export_dpi() == 600.0
    assert app_settings.bake_dpi() == 1200.0


def test_mm_to_px_uses_the_current_screen_dpi_setting():
    app_settings.set_screen_dpi(96.0)
    at_96 = mm_to_px(10)

    app_settings.set_screen_dpi(192.0)
    at_192 = mm_to_px(10)

    assert at_192 == at_96 * 2


def test_px_to_mm_is_the_inverse_of_mm_to_px_at_any_screen_dpi():
    app_settings.set_screen_dpi(150.0)
    assert abs(px_to_mm(mm_to_px(37.0)) - 37.0) < 1e-9
