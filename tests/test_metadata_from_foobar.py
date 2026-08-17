"""Project > Metadata...'s "Load from foobar2000" button -- filling the
fields from a playlist instead of from a search.

Deliberately separate from the record flow's own capture: this one is
useful when nothing is being recorded at all, so it must work on its own
and must never be gated behind the MDRem adapter setting.
"""

import pytest

from mdtools import app_settings, foobar
from mdtools.metadata_lookup import AlbumCandidate, MetadataLookupError
from mdtools.panels import metadata_dialog as metadata_module
from mdtools.panels.metadata_dialog import MetadataDialog
from mdtools.panels.settings_dialog import SettingsDialog
from mdtools.project import ProjectMetadata


class FakeFoobar:
    def __init__(self, items=None, error: Exception | None = None):
        self._items = items or []
        self._error = error

    def current_playlist(self):
        if self._error:
            raise self._error
        return foobar.Playlist(id="p1", title="Default", item_count=len(self._items), is_current=True)

    def playlist_items(self, playlist_id, limit=500):
        if self._error:
            raise self._error
        return self._items


def _items(*titles: str) -> list[foobar.PlaylistItem]:
    return [
        foobar.PlaylistItem.from_columns([str(i), title, "Falling In Reverse", "Popular Monster", "2024", "200"])
        for i, title in enumerate(titles, start=1)
    ]


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


def _with_foobar(monkeypatch, fake: FakeFoobar) -> MetadataDialog:
    monkeypatch.setattr(metadata_module.foobar, "FoobarClient", lambda *a, **k: fake)
    return MetadataDialog(ProjectMetadata())


def test_the_playlist_fills_every_field(qt_app, monkeypatch, quiet_dialogs, no_cover):
    dialog = _with_foobar(monkeypatch, FakeFoobar(_items("Prequel", "Popular Monster")))

    dialog._load_from_foobar()

    assert dialog.album_edit.text() == "Popular Monster"
    assert dialog.artist_edit.text() == "Falling In Reverse"
    assert dialog.year_spin.value() == 2024
    assert [dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())] == [
        "Prequel",
        "Popular Monster",
    ]


def test_loading_replaces_the_old_track_list_rather_than_appending(qt_app, monkeypatch, quiet_dialogs, no_cover):
    monkeypatch.setattr(metadata_module.foobar, "FoobarClient", lambda *a, **k: FakeFoobar(_items("One")))
    dialog = MetadataDialog(
        ProjectMetadata(album="Old", artist="Old", tracks=[metadata_module.Track("Stale"), metadata_module.Track("Also stale")])
    )

    dialog._load_from_foobar()

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "One"


def test_an_unreachable_foobar_warns_and_changes_nothing(qt_app, monkeypatch, quiet_dialogs, no_cover):
    dialog = _with_foobar(monkeypatch, FakeFoobar(error=foobar.FoobarError("connection refused")))
    dialog.album_edit.setText("Untouched")

    dialog._load_from_foobar()

    assert quiet_dialogs, "the user must be told why nothing happened"
    assert dialog.album_edit.text() == "Untouched"


def test_an_empty_playlist_says_so_instead_of_blanking_the_fields(qt_app, monkeypatch, quiet_dialogs, no_cover):
    dialog = _with_foobar(monkeypatch, FakeFoobar([]))
    dialog.album_edit.setText("Untouched")

    dialog._load_from_foobar()

    assert quiet_dialogs
    assert dialog.album_edit.text() == "Untouched"


def test_cover_art_is_fetched_for_what_was_loaded(qt_app, monkeypatch, quiet_dialogs, tmp_path):
    chosen = AlbumCandidate(
        collection_id=1, artist_name="Falling In Reverse", collection_name="Popular Monster", year=2024, track_count=2
    )
    monkeypatch.setattr(metadata_module, "find_cover", lambda *a, **k: (b"JPEG", chosen))
    monkeypatch.setattr(metadata_module, "save_downloaded_cover", lambda *a, **k: tmp_path / "c.jpg")
    dialog = _with_foobar(monkeypatch, FakeFoobar(_items("Prequel")))

    dialog._load_from_foobar()

    assert dialog._cover_art == b"JPEG"


def test_a_failed_cover_lookup_still_keeps_the_track_list(qt_app, monkeypatch, quiet_dialogs):
    """Artwork is a bonus on top of what the button actually promises."""

    def boom(*args, **kwargs):
        raise MetadataLookupError("no network")

    monkeypatch.setattr(metadata_module, "find_cover", boom)
    dialog = _with_foobar(monkeypatch, FakeFoobar(_items("Prequel", "Popular Monster")))

    dialog._load_from_foobar()

    assert dialog.table.rowCount() == 2
    assert dialog._cover_art is None


def test_the_foobar_address_setting_is_not_disabled_with_the_ir_adapter(qt_app, monkeypatch):
    """Reading a playlist needs foobar2000, not the MDRem adapter -- tying
    the two together disabled a setting the user still needs."""
    monkeypatch.setattr(SettingsDialog, "_populate_ports", lambda self, selected: None)
    app_settings.set_mdrem_enabled(False)

    dialog = SettingsDialog()

    assert dialog.foobar_url_edit.isEnabled()
    assert not dialog._mdrem_port_widget.isEnabled()
