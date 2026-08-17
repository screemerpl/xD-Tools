from mdtools.metadata_lookup import AlbumCandidate, LookupResult, LookupTrack, MetadataLookupError
from mdtools.panels import metadata_dialog as metadata_dialog_module
from mdtools.panels.metadata_dialog import TIME_COL, TITLE_COL, MetadataDialog
from mdtools.project import ProjectMetadata


def test_lookup_button_appears_above_the_year_field(qt_app):
    """Year isn't used for the lookup itself (only Album + Artist are), so
    the button belongs directly under those two fields, above Year -- not
    below the whole form."""
    from PySide6.QtWidgets import QFormLayout

    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist"))
    form = dialog.findChild(QFormLayout)

    positions = {
        "artist": form.getWidgetPosition(dialog.artist_edit)[0],
        "lookup": form.getWidgetPosition(dialog.lookup_btn)[0],
        "year": form.getWidgetPosition(dialog.year_spin)[0],
    }
    assert positions["artist"] < positions["lookup"] < positions["year"]


def test_lookup_without_album_or_artist_shows_a_message_and_does_nothing(qt_app, monkeypatch):
    monkeypatch.setattr(metadata_dialog_module.QMessageBox, "information", lambda *a, **k: None)
    called = []
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda *a, **k: called.append(1))

    dialog = MetadataDialog(ProjectMetadata(album="", artist="Someone"))
    dialog._lookup_tracks()

    assert called == []


def test_no_matching_album_shows_a_warning(qt_app, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        metadata_dialog_module.QMessageBox, "warning", lambda self, title, text: warnings.append(text)
    )
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: [])

    dialog = MetadataDialog(ProjectMetadata(album="Nothing", artist="Nobody"))
    dialog._lookup_tracks()

    assert len(warnings) == 1
    assert "Nothing" in warnings[0] and "Nobody" in warnings[0]


def test_a_single_candidate_is_used_without_prompting(qt_app, monkeypatch):
    candidate = AlbumCandidate(collection_id=1, artist_name="Old Artist", collection_name="Old Album", year=2001, track_count=10)
    result = LookupResult(year=2001, tracks=[LookupTrack(title="Only Track", time_seconds=100)])

    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: [candidate])
    captured = {}

    def fake_fetch_tracks(collection_id, fallback_year=None):
        captured["collection_id"] = collection_id
        return result

    monkeypatch.setattr(metadata_dialog_module, "fetch_tracks", fake_fetch_tracks)

    def fail_if_called(*a, **k):
        raise AssertionError("QInputDialog.getItem should not be called for a single candidate")

    monkeypatch.setattr(metadata_dialog_module.QInputDialog, "getItem", staticmethod(fail_if_called))

    dialog = MetadataDialog(ProjectMetadata(album="Old Album", artist="Old Artist"))
    dialog._lookup_tracks()

    assert captured["collection_id"] == 1
    assert dialog.year_spin.value() == 2001
    assert dialog.table.item(0, TITLE_COL).text() == "Only Track"


def test_lookup_updates_album_and_artist_fields_from_the_chosen_candidate(qt_app, monkeypatch):
    """The candidate's own metadata is authoritative -- if what the user
    typed differs (capitalization, a "The" prefix, a remaster suffix), the
    fields should be corrected to match what was actually found, not left
    showing the original typed-in text."""
    candidate = AlbumCandidate(
        collection_id=1, artist_name="The Real Artist", collection_name="The Real Album (Remaster)",
        year=2001, track_count=10,
    )
    result = LookupResult(year=2001, tracks=[LookupTrack(title="Only Track", time_seconds=100)])

    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: [candidate])
    monkeypatch.setattr(metadata_dialog_module, "fetch_tracks", lambda *a, **k: result)

    dialog = MetadataDialog(ProjectMetadata(album="real album", artist="real artist"))
    dialog._lookup_tracks()

    assert dialog.album_edit.text() == "The Real Album (Remaster)"
    assert dialog.artist_edit.text() == "The Real Artist"


def test_multiple_candidates_prompts_and_uses_the_chosen_one(qt_app, monkeypatch):
    candidates = [
        AlbumCandidate(collection_id=1, artist_name="Artist", collection_name="Album (Single)", year=2005, track_count=1),
        AlbumCandidate(collection_id=2, artist_name="Artist", collection_name="Album", year=1998, track_count=12),
    ]
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: candidates)

    result = LookupResult(year=1998, tracks=[LookupTrack(title="Real Track", time_seconds=200)])
    captured = {}

    def fake_fetch_tracks(collection_id, fallback_year=None):
        captured["collection_id"] = collection_id
        return result

    monkeypatch.setattr(metadata_dialog_module, "fetch_tracks", fake_fetch_tracks)

    def fake_get_item(self, title, label, items, current=0, editable=True):
        # simulate the user picking the second (real album) entry
        return items[1], True

    monkeypatch.setattr(metadata_dialog_module.QInputDialog, "getItem", staticmethod(fake_get_item))

    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist"))
    dialog._lookup_tracks()

    assert captured["collection_id"] == 2
    assert dialog.year_spin.value() == 1998
    assert dialog.table.item(0, TITLE_COL).text() == "Real Track"


def test_cancelling_the_picker_leaves_everything_untouched(qt_app, monkeypatch):
    candidates = [
        AlbumCandidate(collection_id=1, artist_name="Artist", collection_name="Album A", year=2005, track_count=1),
        AlbumCandidate(collection_id=2, artist_name="Artist", collection_name="Album B", year=1998, track_count=12),
    ]
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: candidates)

    def fetch_should_not_be_called(*a, **k):
        raise AssertionError("fetch_tracks should not run if the picker was cancelled")

    monkeypatch.setattr(metadata_dialog_module, "fetch_tracks", fetch_should_not_be_called)
    monkeypatch.setattr(
        metadata_dialog_module.QInputDialog, "getItem", staticmethod(lambda *a, **k: ("", False))
    )

    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist", year=1990))
    dialog._add_track()
    dialog.table.item(0, TITLE_COL).setText("Kept Track")

    dialog._lookup_tracks()

    assert dialog.year_spin.value() == 1990
    assert dialog.table.item(0, TITLE_COL).text() == "Kept Track"


def test_fetch_failure_shows_a_warning_and_leaves_existing_tracks_alone(qt_app, monkeypatch):
    candidate = AlbumCandidate(collection_id=1, artist_name="Artist", collection_name="Album", year=2000, track_count=10)
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: [candidate])

    warnings = []
    monkeypatch.setattr(
        metadata_dialog_module.QMessageBox, "warning", lambda self, title, text: warnings.append(text)
    )

    def broken_fetch(collection_id, fallback_year=None):
        raise MetadataLookupError("network broke")

    monkeypatch.setattr(metadata_dialog_module, "fetch_tracks", broken_fetch)

    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist"))
    dialog._add_track()
    dialog.table.item(0, TITLE_COL).setText("Kept Track")

    dialog._lookup_tracks()

    assert warnings == ["network broke"]
    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, TITLE_COL).text() == "Kept Track"


def test_lookup_button_is_re_enabled_after_a_failed_search(qt_app, monkeypatch):
    monkeypatch.setattr(metadata_dialog_module.QMessageBox, "warning", lambda *a, **k: None)

    def broken_search(artist, album):
        raise MetadataLookupError("boom")

    monkeypatch.setattr(metadata_dialog_module, "search_albums", broken_search)

    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist"))
    dialog._lookup_tracks()

    assert dialog.lookup_btn.isEnabled() is True


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


def test_successful_lookup_saves_and_displays_the_cover_art(qt_app, tmp_path, monkeypatch):
    candidate = AlbumCandidate(
        collection_id=1,
        artist_name="Cover Artist",
        collection_name="Cover Album",
        year=2000,
        track_count=10,
        artwork_url="https://example.com/cover.jpg",
    )
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: [candidate])
    monkeypatch.setattr(
        metadata_dialog_module, "fetch_tracks", lambda *a, **k: LookupResult(year=2000, tracks=[])
    )
    monkeypatch.setattr(metadata_dialog_module, "fetch_artwork", lambda url: _tiny_png())
    monkeypatch.setattr(metadata_dialog_module, "downloaded_covers_dir", lambda: tmp_path)

    dialog = MetadataDialog(ProjectMetadata(album="Cover Album", artist="Cover Artist"))
    dialog._lookup_tracks()

    saved = list(tmp_path.glob("*.jpg"))
    assert len(saved) == 1
    assert saved[0].name == "Cover Artist - Cover Album.jpg"
    assert not dialog.cover_label.pixmap().isNull()


def test_a_missing_artwork_url_never_calls_fetch_artwork(qt_app, monkeypatch):
    candidate = AlbumCandidate(
        collection_id=1, artist_name="Artist", collection_name="Album", year=2000, track_count=10, artwork_url=None
    )
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: [candidate])
    monkeypatch.setattr(
        metadata_dialog_module, "fetch_tracks", lambda *a, **k: LookupResult(year=2000, tracks=[])
    )

    def fail_if_called(*a, **k):
        raise AssertionError("fetch_artwork should not run without an artwork_url")

    monkeypatch.setattr(metadata_dialog_module, "fetch_artwork", fail_if_called)

    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist"))
    dialog._lookup_tracks()  # must not raise


def test_a_failed_artwork_fetch_is_silently_ignored(qt_app, monkeypatch):
    candidate = AlbumCandidate(
        collection_id=1,
        artist_name="Artist",
        collection_name="Album",
        year=2000,
        track_count=10,
        artwork_url="https://example.com/cover.jpg",
    )
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: [candidate])
    monkeypatch.setattr(
        metadata_dialog_module,
        "fetch_tracks",
        lambda *a, **k: LookupResult(year=2000, tracks=[LookupTrack(title="A Track", time_seconds=None)]),
    )

    def broken_fetch_artwork(url):
        raise MetadataLookupError("no artwork")

    monkeypatch.setattr(metadata_dialog_module, "fetch_artwork", broken_fetch_artwork)

    warnings = []
    monkeypatch.setattr(
        metadata_dialog_module.QMessageBox, "warning", lambda self, title, text: warnings.append(text)
    )

    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist"))
    dialog._lookup_tracks()  # must not raise

    assert warnings == []  # a cover-art failure is not surfaced as an error
    assert dialog.table.item(0, TITLE_COL).text() == "A Track"


def _tiny_png_bytes() -> bytes:
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


def test_a_previously_saved_cover_is_shown_immediately_on_open(qt_app):
    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist", cover_art=_tiny_png_bytes()))
    assert not dialog.cover_label.pixmap().isNull()


def test_accepting_carries_the_cover_art_into_result_metadata(qt_app, tmp_path, monkeypatch):
    candidate = AlbumCandidate(
        collection_id=1,
        artist_name="Artist",
        collection_name="Album",
        year=2000,
        track_count=10,
        artwork_url="https://example.com/cover.jpg",
    )
    cover_bytes = _tiny_png_bytes()
    monkeypatch.setattr(metadata_dialog_module, "search_albums", lambda artist, album: [candidate])
    monkeypatch.setattr(
        metadata_dialog_module, "fetch_tracks", lambda *a, **k: LookupResult(year=2000, tracks=[])
    )
    monkeypatch.setattr(metadata_dialog_module, "fetch_artwork", lambda url: cover_bytes)
    monkeypatch.setattr(metadata_dialog_module, "downloaded_covers_dir", lambda: tmp_path)

    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist"))
    dialog._lookup_tracks()
    dialog._on_accept()

    assert dialog.result_metadata.cover_art == cover_bytes


def test_reopening_with_a_saved_cover_and_accepting_without_a_new_lookup_keeps_it(qt_app):
    cover_bytes = _tiny_png_bytes()
    dialog = MetadataDialog(ProjectMetadata(album="Album", artist="Artist", cover_art=cover_bytes))

    dialog._on_accept()

    assert dialog.result_metadata.cover_art == cover_bytes
