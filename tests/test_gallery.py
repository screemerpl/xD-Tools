from mdtools import gallery


def _isolate_covers_dir(tmp_path, monkeypatch, name="covers-unused"):
    """Most of these tests care only about gallery_dir(); point the
    (also real, per-user) downloaded_covers_dir() somewhere empty and
    isolated so it can never leak real files into these assertions."""
    covers_dir = tmp_path / name
    covers_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(gallery, "downloaded_covers_dir", lambda: covers_dir)
    return covers_dir


def test_list_gallery_images_finds_the_bundled_logo():
    # exercises the real assets/img folder shipped with the repo -- this is
    # the one thing that must actually be true, everything else is tested
    # against an isolated tmp_path folder below.
    images = gallery.list_gallery_images()
    assert any(p.name == "mdlogo.png" for p in images)


def test_list_gallery_images_is_empty_for_a_missing_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(gallery, "gallery_dir", lambda: tmp_path / "does-not-exist")
    _isolate_covers_dir(tmp_path, monkeypatch)
    assert gallery.list_gallery_images() == []


def test_list_gallery_images_only_includes_known_image_extensions(tmp_path, monkeypatch):
    (tmp_path / "picture.png").write_bytes(b"")
    (tmp_path / "photo.JPG").write_bytes(b"")  # extension matching is case-insensitive
    (tmp_path / "notes.txt").write_bytes(b"")
    (tmp_path / "readme.md").write_bytes(b"")
    monkeypatch.setattr(gallery, "gallery_dir", lambda: tmp_path)
    _isolate_covers_dir(tmp_path, monkeypatch)

    names = {p.name for p in gallery.list_gallery_images()}
    assert names == {"picture.png", "photo.JPG"}


def test_list_gallery_images_is_sorted_by_filename(tmp_path, monkeypatch):
    for name in ("c.png", "a.png", "b.png"):
        (tmp_path / name).write_bytes(b"")
    monkeypatch.setattr(gallery, "gallery_dir", lambda: tmp_path)
    _isolate_covers_dir(tmp_path, monkeypatch)

    names = [p.name for p in gallery.list_gallery_images()]
    assert names == ["a.png", "b.png", "c.png"]


def test_list_gallery_images_merges_bundled_and_downloaded_covers(tmp_path, monkeypatch):
    bundled_dir = tmp_path / "bundled"
    bundled_dir.mkdir()
    (bundled_dir / "logo.png").write_bytes(b"")
    monkeypatch.setattr(gallery, "gallery_dir", lambda: bundled_dir)

    covers_dir = _isolate_covers_dir(tmp_path, monkeypatch, name="covers")
    (covers_dir / "artist - album.jpg").write_bytes(b"")

    names = {p.name for p in gallery.list_gallery_images()}
    assert names == {"logo.png", "artist - album.jpg"}


def test_downloaded_covers_dir_is_created_if_missing(tmp_path, monkeypatch):
    from PySide6.QtCore import QStandardPaths

    monkeypatch.setattr(QStandardPaths, "writableLocation", staticmethod(lambda loc: str(tmp_path)))

    covers_dir = gallery.downloaded_covers_dir()

    assert covers_dir == tmp_path / "covers"
    assert covers_dir.is_dir()
