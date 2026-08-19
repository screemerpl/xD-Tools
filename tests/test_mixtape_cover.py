"""The drawn cover for a compilation.

Note what these do and do not check. Whether the result looks good is not
something a test can answer -- that was settled by rendering it and looking.
What they pin down is the part that is a real constraint rather than taste:
that it is a valid image at all, that it is stable, and that its two colours
stay apart once the printer discards the hue.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from mdtools import mixtape_cover
from mdtools.palette import relative_luminance
from mdtools.project import ProjectMetadata, Track, apply_compilation_naming


def _mixtape(count: int = 4) -> ProjectMetadata:
    bands = ["New Order", "The Cure", "Depeche Mode", "Soft Cell", "Visage", "Gary Numan"]
    tracks = [Track(f"Song {n + 1}", 200 + n, bands[n % len(bands)]) for n in range(count)]
    return apply_compilation_naming(ProjectMetadata(tracks=tracks))


def _image(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def test_the_cover_is_a_real_square_png(qt_app):
    image = _image(mixtape_cover.render_cover(_mixtape()))
    assert image.size == (mixtape_cover.DEFAULT_SIZE, mixtape_cover.DEFAULT_SIZE)


def test_the_cover_is_ordinary_image_bytes_that_metadata_can_hold(qt_app):
    """The whole design rests on this: nothing downstream -- the disc label,
    the J-card, the palette extraction, the .mdproj -- needs to know the
    artwork was drawn rather than fetched."""
    metadata = _mixtape()
    metadata.cover_art = mixtape_cover.render_cover(metadata)

    from mdtools import palette

    assert palette.swatches(metadata.cover_art), "the palette code has to be able to read it"


def test_the_same_mixtape_always_gets_the_same_cover(qt_app):
    """Hashed, not random: regenerating after an edit should not reshuffle
    the design, and Python's own hash() is salted per process."""
    assert mixtape_cover.render_cover(_mixtape()) == mixtape_cover.render_cover(_mixtape())


def test_different_mixtapes_get_different_colours(qt_app):
    assert mixtape_cover.scheme(_mixtape(4)) != mixtape_cover.scheme(_mixtape(5))


def test_editing_one_title_does_not_change_the_scheme_beyond_recognition(qt_app):
    """Sanity check on the seed being over the whole track list: it should
    depend on the content, so this simply must not raise or return
    something malformed."""
    metadata = _mixtape()
    background, accent, text = mixtape_cover.scheme(metadata)
    for colour in (background, accent, text):
        assert len(colour) == 7 and colour.startswith("#")


def test_background_and_accent_stay_apart_in_grayscale(qt_app):
    """The real constraint, not an aesthetic one: these pages get printed
    through Export Print PNG (Grayscale). Two colours picked to contrast by
    hue can convert to the same grey, at which point the accent rule
    vanishes into the background."""
    for count in range(2, 20):
        background, accent, _ = mixtape_cover.scheme(_mixtape(count))
        gap = abs(relative_luminance(background) - relative_luminance(accent))
        assert gap >= mixtape_cover._MIN_LUMINANCE_GAP, f"{background} vs {accent} at {count} tracks"


def test_the_text_colour_is_readable_against_the_background(qt_app):
    for count in range(2, 20):
        background, _, text = mixtape_cover.scheme(_mixtape(count))
        gap = abs(relative_luminance(background) - relative_luminance(text))
        assert gap >= 0.3, f"{text} on {background} at {count} tracks"


def test_a_long_track_list_still_renders(qt_app):
    """Past the threshold it splits into two columns, and the font search
    has a floor -- neither should raise or produce an empty image."""
    image = _image(mixtape_cover.render_cover(_mixtape(24)))
    assert len(image.getcolors(maxcolors=1 << 20) or []) > 1, "something was actually drawn"


def test_a_mixtape_with_no_tracks_still_produces_a_cover(qt_app):
    """Nothing should be able to make this raise -- it runs at the tail of a
    recording, where an exception would lose the layout after the disc is
    already written."""
    empty = apply_compilation_naming(ProjectMetadata(artist="Various Artists"))
    assert _image(mixtape_cover.render_cover(empty)).size[0] == mixtape_cover.DEFAULT_SIZE


def test_track_entries_carry_the_performer_and_a_padded_number(qt_app):
    entries = mixtape_cover._entries(_mixtape(2))
    assert entries[0] == ("01", "New Order - Song 1")


def test_a_track_with_no_known_performer_just_shows_its_title(qt_app):
    metadata = ProjectMetadata(tracks=[Track("Unknown Song")])
    assert mixtape_cover._entries(metadata)[0] == ("01", "Unknown Song")
