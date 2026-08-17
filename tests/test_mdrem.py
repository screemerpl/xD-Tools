"""The parts of MDRem support that need no hardware and no QApplication:
text conversion, disc-title formatting, and building the upload plan."""

from mdtools import app_settings, mdrem
from mdtools.project import ProjectMetadata, Track


def _album(tracks: list[str], **kwargs) -> ProjectMetadata:
    defaults = dict(album="Lost Souls", artist="Caskets", year=2021)
    defaults.update(kwargs)
    return ProjectMetadata(tracks=[Track(t) for t in tracks], **defaults)


# --- transliteration -------------------------------------------------------


def test_plain_ascii_is_left_alone():
    result = mdrem.transliterate("Hopes & Dreams (2021)")
    assert result.text == "Hopes & Dreams (2021)"
    assert not result.is_lossy


def test_accented_latin_letters_lose_their_marks():
    assert mdrem.transliterate("Björk Homogénic").text == "Bjork Homogenic"


def test_polish_letters_including_the_ones_decomposition_does_not_touch():
    """NFKD turns ą into a+combining mark, but ł is its own letter with no
    decomposition at all -- it needs the explicit map, and used to vanish."""
    assert mdrem.transliterate("Zażółć gęślą jaźń").text == "Zazolc gesla jazn"
    assert mdrem.transliterate("ŁÓDŹ").text == "LODZ"


def test_typographic_punctuation_becomes_its_ascii_equivalent():
    # Exactly what an iTunes metadata lookup routinely returns.
    assert mdrem.transliterate("Don’t Look Back — “Live”").text == 'Don\'t Look Back - "Live"'


def test_characters_with_no_equivalent_are_reported_not_silently_dropped():
    result = mdrem.transliterate("日本語 title")
    assert result.text == "title"
    assert result.dropped == ["日", "本", "語"]
    assert result.is_lossy


def test_dropped_characters_are_listed_once_each():
    assert mdrem.transliterate("日日日").dropped == ["日"]


# --- disc title ------------------------------------------------------------


def test_disc_title_is_artist_album_year():
    assert mdrem.disc_title(_album([])) == "Caskets - Lost Souls (2021)"


def test_disc_title_skips_whatever_is_missing():
    assert mdrem.disc_title(_album([], artist="", year=None)) == "Lost Souls"
    assert mdrem.disc_title(_album([], album="", artist="")) == "2021"
    assert mdrem.disc_title(_album([], album="", artist="", year=None)) == ""


# --- upload plan -----------------------------------------------------------


def test_plan_writes_the_disc_title_then_one_step_per_track():
    plan = mdrem.build_upload_plan(_album(["The Only Ones", "Glass Heart"]))
    assert [step.command for step in plan.steps] == [
        "TITLEDISC Caskets - Lost Souls (2021)",
        "TITLETRACK 1 The Only Ones",
        "TITLETRACK 2 Glass Heart",
    ]


def test_plan_transliterates_and_collects_every_dropped_character():
    plan = mdrem.build_upload_plan(_album(["日本", "Zażółć"], album="Ünïcode"))
    assert plan.steps[-1].command == "TITLETRACK 2 Zazolc"
    assert plan.dropped == ["日", "本"]


def test_tracks_past_the_decks_last_selectable_number_are_skipped_not_sent():
    """The firmware has no key code for tracks beyond MAX_TRACK, so there
    is no way to select them on the deck -- reported rather than dropped."""
    titles = [f"Track {i}" for i in range(1, mdrem.MAX_TRACK + 3)]
    plan = mdrem.build_upload_plan(_album(titles))

    commands = [step.command for step in plan.steps]
    assert f"TITLETRACK {mdrem.MAX_TRACK} Track {mdrem.MAX_TRACK}" in commands
    assert not any(f"TITLETRACK {mdrem.MAX_TRACK + 1}" in c for c in commands)
    assert plan.skipped_tracks == [f"Track {mdrem.MAX_TRACK + 1}", f"Track {mdrem.MAX_TRACK + 2}"]


def test_a_track_whose_title_is_entirely_unsupported_is_not_sent_as_an_empty_title():
    plan = mdrem.build_upload_plan(_album(["日本語"]))
    assert [s.command for s in plan.steps] == ["TITLEDISC Caskets - Lost Souls (2021)"]


def test_plan_numbering_follows_the_track_list_not_the_sendable_subset():
    """A track that transliterates to nothing must not shift the numbers of
    the ones after it -- track 3 is still TRACK3 on the deck."""
    plan = mdrem.build_upload_plan(_album(["One", "日本語", "Three"]))
    assert [s.command for s in plan.steps][1:] == ["TITLETRACK 1 One", "TITLETRACK 3 Three"]


def test_empty_metadata_gives_an_empty_plan():
    plan = mdrem.build_upload_plan(ProjectMetadata())
    assert plan.is_empty


def test_estimate_grows_with_the_amount_being_written():
    short = mdrem.build_upload_plan(_album(["A"]))
    long = mdrem.build_upload_plan(_album(["A", "B", "C", "D"]))
    assert mdrem.estimated_seconds(long) > mdrem.estimated_seconds(short) > 0


def test_skipping_the_erase_step_roughly_halves_the_estimate():
    """Clearing overshoots the old title's length on purpose (the deck
    can't be read back), so it dominates the time for short titles."""
    plan = mdrem.build_upload_plan(_album(["The Only Ones", "Glass Heart"]))
    with_clear = mdrem.estimated_seconds(plan, clearing=True)
    without = mdrem.estimated_seconds(plan, clearing=False)
    assert without < with_clear / 2


# --- settings --------------------------------------------------------------


def test_mdrem_enabled_survives_a_round_trip_through_the_ini_file():
    """Regression guard: QSettings(IniFormat) hands a bool back as the
    *string* "false", and bool("false") is True -- reading this naively
    would make the setting impossible to turn off again."""
    app_settings.set_mdrem_enabled(True)
    assert app_settings.mdrem_enabled() is True
    app_settings.set_mdrem_enabled(False)
    assert app_settings.mdrem_enabled() is False


def test_mdrem_is_off_and_portless_until_configured():
    assert app_settings.mdrem_enabled() is False
    assert app_settings.mdrem_port() == ""


def test_mdrem_port_round_trips():
    app_settings.set_mdrem_port("COM7")
    assert app_settings.mdrem_port() == "COM7"
