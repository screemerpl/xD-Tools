"""The Metadata dialog's "Import from Folder..." button -- filling the
fields from an album folder's own tags instead of from a search or (as it
used to) from foobar2000's current playlist.

Deliberately separate from the record flow's own capture: this one is
useful when nothing is being recorded at all, and it must work with no
foobar2000 involved at all -- explicit user request, replacing the old
"Load from foobar2000" button.
"""

from pathlib import Path

import mutagen.flac
import numpy as np
import pyflac
import pytest
import soundfile as sf

from mdtools.metadata_lookup import AlbumCandidate, MetadataLookupError
from mdtools.panels import metadata_dialog as metadata_module
from mdtools.panels.metadata_dialog import MetadataDialog
from mdtools.project import ProjectMetadata


def _make_tagged_flac(path: Path, tags: dict[str, str], seconds: float = 0.1) -> None:
    samples = np.zeros((int(44100 * seconds), 2), dtype=np.int16)
    wav = path.with_suffix(".wav")
    sf.write(wav, samples, 44100, subtype="PCM_16")
    encoder = pyflac.FileEncoder(input_file=str(wav), output_file=str(path))
    encoder.process()
    audio = mutagen.flac.FLAC(str(path))
    for name, value in tags.items():
        audio[name] = value
    audio.save()
    wav.unlink()


def _album_folder(tmp_path: Path, *tracks: dict[str, str]) -> Path:
    folder = tmp_path / "album"
    folder.mkdir()
    for i, tags in enumerate(tracks, start=1):
        _make_tagged_flac(folder / f"{i:02d}.flac", tags)
    return folder


@pytest.fixture
def quiet_dialogs(monkeypatch):
    """A real QMessageBox.exec blocks forever offscreen -- see the standing
    note about this in CLAUDE.md."""
    shown: list[tuple] = []
    for name in ("warning", "information"):
        monkeypatch.setattr(metadata_module.QMessageBox, name, lambda *a, **k: shown.append(a))
    return shown


@pytest.fixture
def no_cover(monkeypatch):
    monkeypatch.setattr(metadata_module, "find_cover", lambda *a, **k: (None, None))


def _pick(monkeypatch, folder: Path | None) -> None:
    monkeypatch.setattr(
        metadata_module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(folder or ""))
    )


def test_the_folder_fills_every_field(qt_app, monkeypatch, tmp_path, quiet_dialogs, no_cover):
    folder = _album_folder(
        tmp_path,
        {"TITLE": "Prequel", "ARTIST": "Falling In Reverse", "ALBUMARTIST": "Falling In Reverse", "ALBUM": "Popular Monster", "DATE": "2024"},
        {"TITLE": "Popular Monster", "ARTIST": "Falling In Reverse", "ALBUMARTIST": "Falling In Reverse", "ALBUM": "Popular Monster", "DATE": "2024"},
    )
    _pick(monkeypatch, folder)
    dialog = MetadataDialog(ProjectMetadata())

    dialog._load_from_folder()

    assert dialog.album_edit.text() == "Popular Monster"
    assert dialog.artist_edit.text() == "Falling In Reverse"
    assert dialog.year_spin.value() == 2024
    assert [dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())] == [
        "Prequel",
        "Popular Monster",
    ]


def test_loading_replaces_the_old_track_list_rather_than_appending(qt_app, monkeypatch, tmp_path, quiet_dialogs, no_cover):
    folder = _album_folder(tmp_path, {"TITLE": "One", "ARTIST": "A", "ALBUM": "B"})
    _pick(monkeypatch, folder)
    dialog = MetadataDialog(
        ProjectMetadata(album="Old", artist="Old", tracks=[metadata_module.Track("Stale"), metadata_module.Track("Also stale")])
    )

    dialog._load_from_folder()

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "One"


def test_an_empty_folder_says_so_instead_of_blanking_the_fields(qt_app, monkeypatch, tmp_path, quiet_dialogs, no_cover):
    empty = tmp_path / "empty"
    empty.mkdir()
    _pick(monkeypatch, empty)
    dialog = MetadataDialog(ProjectMetadata())
    dialog.album_edit.setText("Untouched")

    dialog._load_from_folder()

    assert quiet_dialogs, "the user must be told why nothing happened"
    assert dialog.album_edit.text() == "Untouched"


def test_cancelling_the_folder_picker_changes_nothing(qt_app, monkeypatch, quiet_dialogs, no_cover):
    _pick(monkeypatch, None)
    dialog = MetadataDialog(ProjectMetadata())
    dialog.album_edit.setText("Untouched")

    dialog._load_from_folder()

    assert dialog.album_edit.text() == "Untouched"
    assert not quiet_dialogs, "cancelling is not a failure worth a dialog"


def test_a_guest_feature_does_not_get_counted_as_a_compilation(qt_app, monkeypatch, tmp_path, quiet_dialogs, no_cover):
    """Reuses foobar.metadata_from_playlist()'s own compilation-naming
    logic unchanged -- this is really a regression guard that the folder
    path is wired through that shared code, not a second copy of it."""
    folder = _album_folder(
        tmp_path,
        {"TITLE": "A", "ARTIST": "Skillet", "ALBUM": "Unleashed", "ALBUMARTIST": "Skillet"},
        {"TITLE": "B", "ARTIST": "Skillet, Lacey Sturm", "ALBUM": "Unleashed", "ALBUMARTIST": "Skillet"},
    )
    _pick(monkeypatch, folder)
    dialog = MetadataDialog(ProjectMetadata())

    dialog._load_from_folder()

    assert dialog.artist_edit.text() == "Skillet"
    assert dialog.album_edit.text() == "Unleashed"


def test_cover_art_is_fetched_for_what_was_loaded(qt_app, monkeypatch, tmp_path, quiet_dialogs):
    folder = _album_folder(tmp_path, {"TITLE": "Prequel", "ARTIST": "Falling In Reverse", "ALBUMARTIST": "Falling In Reverse", "ALBUM": "Popular Monster"})
    _pick(monkeypatch, folder)
    chosen = AlbumCandidate(
        collection_id=1, artist_name="Falling In Reverse", collection_name="Popular Monster", year=2024, track_count=1
    )
    monkeypatch.setattr(metadata_module, "find_cover", lambda *a, **k: (b"JPEG", chosen))
    monkeypatch.setattr(metadata_module, "save_downloaded_cover", lambda *a, **k: tmp_path / "c.jpg")
    dialog = MetadataDialog(ProjectMetadata())

    dialog._load_from_folder()

    assert dialog._cover_art == b"JPEG"


def test_a_failed_cover_lookup_still_keeps_the_track_list(qt_app, monkeypatch, tmp_path, quiet_dialogs):
    """Artwork is a bonus on top of what the button actually promises."""
    folder = _album_folder(
        tmp_path,
        {"TITLE": "Prequel", "ARTIST": "Falling In Reverse", "ALBUMARTIST": "Falling In Reverse", "ALBUM": "Popular Monster"},
        {"TITLE": "Popular Monster", "ARTIST": "Falling In Reverse", "ALBUMARTIST": "Falling In Reverse", "ALBUM": "Popular Monster"},
    )
    _pick(monkeypatch, folder)

    def boom(*args, **kwargs):
        raise MetadataLookupError("no network")

    monkeypatch.setattr(metadata_module, "find_cover", boom)
    dialog = MetadataDialog(ProjectMetadata())

    dialog._load_from_folder()

    assert dialog.table.rowCount() == 2
    assert dialog._cover_art is None


def test_the_remembered_folder_is_used_as_the_start_and_then_updated(qt_app, monkeypatch, tmp_path, no_cover):
    """Same "back where the last album came from" convention
    FolderRecordDialog's own browse button already follows."""
    from mdtools import app_settings

    folder = _album_folder(tmp_path, {"TITLE": "A", "ARTIST": "B", "ALBUM": "C"})
    app_settings.set_music_folder(str(tmp_path))
    seen_start = []

    def fake_pick(parent, caption, start):
        seen_start.append(start)
        return str(folder)

    monkeypatch.setattr(metadata_module.QFileDialog, "getExistingDirectory", staticmethod(fake_pick))
    dialog = MetadataDialog(ProjectMetadata())

    dialog._load_from_folder()

    assert seen_start == [str(tmp_path)]
    assert app_settings.music_folder() == str(tmp_path)  # folder's own parent
