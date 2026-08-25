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


def test_experimental_features_are_off_by_default():
    assert app_settings.experimental_features_enabled() is False


def test_experimental_features_flag_round_trips():
    app_settings.set_experimental_features_enabled(True)
    assert app_settings.experimental_features_enabled() is True

    app_settings.set_experimental_features_enabled(False)
    assert app_settings.experimental_features_enabled() is False


def test_experimental_features_flag_survives_the_ini_string_bool_gotcha():
    """An IniFormat QSettings hands a stored bool back as the text
    "false"/"true" -- bool("false") is True, so reading this naively would
    make the checkbox impossible to turn back off. Same gotcha mdrem_enabled
    already guards against."""
    app_settings.set_experimental_features_enabled(False)
    assert app_settings.experimental_features_enabled() is False


def test_mm_to_px_uses_the_current_screen_dpi_setting():
    app_settings.set_screen_dpi(96.0)
    at_96 = mm_to_px(10)

    app_settings.set_screen_dpi(192.0)
    at_192 = mm_to_px(10)

    assert at_192 == at_96 * 2


def test_px_to_mm_is_the_inverse_of_mm_to_px_at_any_screen_dpi():
    app_settings.set_screen_dpi(150.0)
    assert abs(px_to_mm(mm_to_px(37.0)) - 37.0) < 1e-9


# --- Telegram bot integration (experimental) --------------------------------


def test_telegram_api_credentials_come_from_the_environment_when_set(monkeypatch):
    """Build-time injection, source #1 -- see
    app_settings._bundled_telegram_credentials(). Deliberately tested through
    the environment rather than against a hardcoded constant: there is no
    longer one to compare with, which is the whole point (the credentials are
    kept out of the source tree so they never reach git history)."""
    monkeypatch.setenv("MDTOOLS_TELEGRAM_API_ID", "1234")
    monkeypatch.setenv("MDTOOLS_TELEGRAM_API_HASH", "abcd")

    assert app_settings.telegram_api_id() == "1234"
    assert app_settings.telegram_api_hash() == "abcd"


def test_a_users_own_override_beats_the_bundled_credentials(monkeypatch):
    monkeypatch.setenv("MDTOOLS_TELEGRAM_API_ID", "1234")
    monkeypatch.setenv("MDTOOLS_TELEGRAM_API_HASH", "abcd")
    app_settings.set_telegram_api_id("mine")
    app_settings.set_telegram_api_hash("mysecret")

    assert app_settings.telegram_api_id() == "mine"
    assert app_settings.telegram_api_hash() == "mysecret"


def test_a_build_without_credentials_reports_them_empty_rather_than_failing(monkeypatch):
    """A supported state, not an error: the user simply has to supply their
    own before signing in, which the sign-in guard says explicitly."""
    monkeypatch.delenv("MDTOOLS_TELEGRAM_API_ID", raising=False)
    monkeypatch.delenv("MDTOOLS_TELEGRAM_API_HASH", raising=False)
    monkeypatch.setattr(app_settings, "_bundled_telegram_credentials", lambda: ("", ""))

    assert app_settings.telegram_api_id() == ""
    assert app_settings.telegram_api_hash() == ""


def test_the_credentials_are_not_hardcoded_anywhere_in_the_source_tree():
    """The property that actually keeps them out of git. Scans the package
    for a bare 32-hex-digit literal, the shape of a Telegram api_hash --
    `_build_credentials.py` is gitignored and so excluded."""
    import re
    from pathlib import Path

    package = Path(app_settings.__file__).parent
    hash_like = re.compile(r"['\"][0-9a-f]{32}['\"]")
    offenders = [
        path.relative_to(package).as_posix()
        for path in package.rglob("*.py")
        if path.name != "_build_credentials.py" and hash_like.search(path.read_text(encoding="utf-8"))
    ]

    assert offenders == [], f"an api_hash-shaped literal is committed in: {offenders}"


def test_audio_output_device_is_empty_by_default():
    """Empty means "the OS default", both for a fresh install and for
    audio_engine.resolve_output_device()'s own fallback."""
    assert app_settings.audio_output_device() == ""


def test_audio_output_device_round_trips():
    app_settings.set_audio_output_device("Speakers (Realtek(R) Audio)")

    assert app_settings.audio_output_device() == "Speakers (Realtek(R) Audio)"


def test_tape_audio_output_device_is_empty_by_default():
    assert app_settings.tape_audio_output_device() == ""


def test_tape_audio_output_device_round_trips_independently_of_the_md_one():
    """A MiniDisc deck typically wants a digital output and a cassette
    deck an analogue one -- two different settings, not one shared."""
    app_settings.set_audio_output_device("SPDIF Out (Realtek)")
    app_settings.set_tape_audio_output_device("Line Out (Realtek)")

    assert app_settings.audio_output_device() == "SPDIF Out (Realtek)"
    assert app_settings.tape_audio_output_device() == "Line Out (Realtek)"


def test_recording_gain_defaults_to_minus_5_db():
    assert app_settings.recording_gain_db() == -5.0
    assert app_settings.recording_gain_db() == app_settings.DEFAULT_RECORDING_GAIN_DB


def test_recording_gain_round_trips():
    app_settings.set_recording_gain_db(-3.5)

    assert app_settings.recording_gain_db() == -3.5


def test_telegram_bot_username_and_phone_are_empty_by_default():
    assert app_settings.telegram_bot_username() == ""
    assert app_settings.telegram_phone() == ""


def test_telegram_settings_round_trip():
    app_settings.set_telegram_api_id("123456")
    app_settings.set_telegram_api_hash("deadbeefcafef00d")
    app_settings.set_telegram_bot_username("@my_bot")
    app_settings.set_telegram_phone("+1 555 0100")

    assert app_settings.telegram_api_id() == "123456"
    assert app_settings.telegram_api_hash() == "deadbeefcafef00d"
    assert app_settings.telegram_bot_username() == "@my_bot"
    assert app_settings.telegram_phone() == "+1 555 0100"


def test_last_regenerate_font_family_is_none_before_anything_is_chosen():
    assert app_settings.last_regenerate_font_family() is None


def test_last_regenerate_font_family_round_trips():
    app_settings.set_last_regenerate_font_family("Courier New")
    assert app_settings.last_regenerate_font_family() == "Courier New"


def test_the_session_path_is_derived_not_stored_and_lives_beside_settings_ini():
    path = app_settings.telegram_session_path()
    assert path.name == "telegram.session"
    from pathlib import Path

    assert path.parent == Path(app_settings._settings().fileName()).parent
