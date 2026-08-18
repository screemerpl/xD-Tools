"""album_sort.py -- grouping a session folder's flat downloads into
per-album subfolders, tag first, arrival-batch fallback second."""

from __future__ import annotations

from pathlib import Path

from mdtools import album_sort


def _touch(root: Path, name: str) -> Path:
    path = root / name
    path.write_bytes(b"x")
    return path


# --- read_album_tag -------------------------------------------------------


def test_read_album_tag_prefers_albumartist_over_artist(tmp_path, monkeypatch):
    path = _touch(tmp_path, "a.flac")
    monkeypatch.setattr(
        album_sort.embedded_cover,
        "flac_tags",
        lambda p: {"ALBUM": "Unleashed", "ARTIST": "Skillet, Lacey Sturm", "ALBUMARTIST": "Skillet"},
    )
    assert album_sort.read_album_tag(path) == ("Skillet", "Unleashed")


def test_read_album_tag_falls_back_to_artist_without_albumartist(tmp_path, monkeypatch):
    path = _touch(tmp_path, "a.flac")
    monkeypatch.setattr(
        album_sort.embedded_cover, "flac_tags", lambda p: {"ALBUM": "Unleashed", "ARTIST": "Skillet"}
    )
    assert album_sort.read_album_tag(path) == ("Skillet", "Unleashed")


# --- batches_from_arrival_order -----------------------------------------


def test_a_single_unbroken_run_is_one_batch():
    downloaded = {1: Path("a.flac"), 2: Path("b.flac"), 3: Path("c.flac")}
    batches = album_sort.batches_from_arrival_order([1, 2, 3], downloaded)
    assert batches == [[Path("a.flac"), Path("b.flac"), Path("c.flac")]]


def test_a_non_file_message_splits_the_run():
    downloaded = {1: Path("a.flac"), 3: Path("b.flac")}
    # id 2 is a plain text/button message -- no entry in `downloaded`.
    batches = album_sort.batches_from_arrival_order([1, 2, 3], downloaded)
    assert batches == [[Path("a.flac")], [Path("b.flac")]]


def test_leading_and_trailing_non_file_messages_are_ignored():
    downloaded = {2: Path("a.flac")}
    batches = album_sort.batches_from_arrival_order([1, 2, 3], downloaded)
    assert batches == [[Path("a.flac")]]


def test_no_file_messages_at_all_is_no_batches():
    assert album_sort.batches_from_arrival_order([1, 2, 3], {}) == []


def test_empty_arrival_order_is_no_batches():
    assert album_sort.batches_from_arrival_order([], {}) == []


# --- sort_downloads -------------------------------------------------------


def test_one_group_total_moves_nothing(tmp_path, monkeypatch):
    """A single downloaded album -- whether by shared tag or by being one
    unbroken batch -- has no reason to be nested under its own subfolder."""
    a = _touch(tmp_path, "a.flac")
    b = _touch(tmp_path, "b.flac")
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: ("Caskets", "Lost Souls"))

    result = album_sort.sort_downloads(tmp_path, {1: a, 2: b}, [1, 2])

    assert result == []
    assert a.exists() and b.exists()  # untouched, still directly in root


def test_fewer_than_two_files_moves_nothing(tmp_path):
    a = _touch(tmp_path, "a.flac")
    assert album_sort.sort_downloads(tmp_path, {1: a}, [1]) == []
    assert album_sort.sort_downloads(tmp_path, {}, []) == []


# --- sorting incrementally, into an already-sorted folder -------------------
#
# Reported directly: two albums were already sorted into folders, a third
# was downloaded, and sorting again said "nothing to sort" -- because that
# third album was a single group and the guard for "one album needs no
# folder of its own" fired unconditionally. Its files stayed flat in the
# root, so the album was both unsorted and invisible to the recording
# picker, which offered only the two pre-existing folders.


def test_a_newly_arrived_album_is_sorted_even_though_it_is_the_only_loose_one(tmp_path, monkeypatch):
    tags = {
        "a.flac": ("Caskets", "Lost Souls"),
        "b.flac": ("Skillet", "Unleashed"),
        "c.flac": ("Nirvana", "Nevermind"),
    }
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    a = _touch(tmp_path, "a.flac")
    b = _touch(tmp_path, "b.flac")

    first = album_sort.sort_downloads(tmp_path, {1: a, 2: b}, [1, 2])
    assert len(first) == 2, "precondition: the first two albums sort normally"

    # The third album arrives afterwards and is, on its own, a single group.
    c = _touch(tmp_path, "c.flac")
    result = album_sort.sort_downloads(tmp_path, {3: c}, [3])

    assert [p.name for p in result] == ["Nirvana - Nevermind"]
    assert (tmp_path / "Nirvana - Nevermind" / "c.flac").exists()
    assert not c.exists(), "it must not be left loose in the root"


def test_sort_folder_also_sorts_a_lone_newly_arrived_album(tmp_path, monkeypatch):
    tags = {
        "a.flac": ("Caskets", "Lost Souls"),
        "b.flac": ("Skillet", "Unleashed"),
        "c.flac": ("Nirvana", "Nevermind"),
    }
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    _touch(tmp_path, "a.flac")
    _touch(tmp_path, "b.flac")
    assert len(album_sort.sort_folder(tmp_path)) == 2, "precondition"

    _touch(tmp_path, "c.flac")
    result = album_sort.sort_folder(tmp_path)

    assert [p.name for p in result] == ["Nirvana - Nevermind"]
    assert (tmp_path / "Nirvana - Nevermind" / "c.flac").exists()


def test_a_single_loose_track_is_sorted_when_the_folder_is_already_sorted(tmp_path, monkeypatch):
    """The `len(flat_files) < 2` fast path had the same flaw as the
    one-group guard: a one-track album arriving into an already-sorted
    folder was stranded by it before grouping even ran."""
    tags = {
        "a.flac": ("Caskets", "Lost Souls"),
        "b.flac": ("Skillet", "Unleashed"),
        "single.flac": ("Nirvana", "Nevermind"),
    }
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    _touch(tmp_path, "a.flac")
    _touch(tmp_path, "b.flac")
    album_sort.sort_folder(tmp_path)

    _touch(tmp_path, "single.flac")
    result = album_sort.sort_folder(tmp_path)

    assert [p.name for p in result] == ["Nirvana - Nevermind"]
    assert (tmp_path / "Nirvana - Nevermind" / "single.flac").exists()


def test_sorting_an_already_sorted_folder_with_nothing_new_is_still_a_no_op(tmp_path, monkeypatch):
    """The relaxed guard must not turn a repeat click into busywork: with
    nothing loose in the root there is still nothing to do, existing
    subfolders or not."""
    tags = {"a.flac": ("Caskets", "Lost Souls"), "b.flac": ("Skillet", "Unleashed")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    _touch(tmp_path, "a.flac")
    _touch(tmp_path, "b.flac")
    album_sort.sort_folder(tmp_path)

    assert album_sort.sort_folder(tmp_path) == []


def test_sort_downloads_also_sees_files_an_earlier_session_left_loose(tmp_path, monkeypatch):
    """Found while auditing for more of the same class of bug, and it is the
    same failure with a different trigger: `downloaded`/`message_order`
    describe only the *current* dialog session, so once downloads started
    accumulating in one shared folder, an earlier session's unsorted files
    were invisible here -- nothing got sorted and the recording picker then
    handed over the whole mixed root as a single "album"."""
    tags = {
        "a1.flac": ("Caskets", "Lost Souls"),
        "a2.flac": ("Caskets", "Lost Souls"),
        "b1.flac": ("Skillet", "Unleashed"),
    }
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    # Session 1 downloaded these and the user never pressed Sort.
    _touch(tmp_path, "a1.flac")
    _touch(tmp_path, "a2.flac")
    # Session 2 downloads one more album; only *it* is tracked now.
    b1 = _touch(tmp_path, "b1.flac")

    result = album_sort.sort_downloads(tmp_path, {5: b1}, [5])

    assert sorted(p.name for p in result) == ["Caskets - Lost Souls", "Skillet - Unleashed"]
    assert (tmp_path / "Caskets - Lost Souls" / "a1.flac").exists()
    assert (tmp_path / "Skillet - Unleashed" / "b1.flac").exists()
    assert not any(p.is_file() for p in tmp_path.iterdir()), "nothing may be left loose to mix into a recording"


def test_untracked_untagged_leftovers_go_to_unsorted_rather_than_staying_loose(tmp_path, monkeypatch):
    """Untagged *and* with no arrival information (an earlier session's
    leftovers). Leaving them loose would let the recording picker sweep them
    up alongside a real album, which is the whole failure being fixed."""
    monkeypatch.setattr(
        album_sort, "read_album_tag", lambda p: ("Skillet", "Unleashed") if p.name == "b.flac" else ("", "")
    )
    _touch(tmp_path, "orphan.mp3")
    b = _touch(tmp_path, "b.flac")

    result = album_sort.sort_downloads(tmp_path, {5: b}, [5])

    assert sorted(p.name for p in result) == ["Skillet - Unleashed", "Unsorted"]
    assert (tmp_path / "Unsorted" / "orphan.mp3").exists()


def test_non_audio_files_are_never_moved(tmp_path, monkeypatch):
    """The download folder is user-configurable, and only files that can
    actually end up on a disc are worth relocating. A first version swept
    *every* loose file into a group, which turned an unrelated `.ini` sitting
    in the folder into a bogus second "album" -- and would just as happily
    have moved a cover image the bot sent alongside the tracks."""
    tags = {"a.flac": ("Caskets", "Lost Souls"), "b.flac": ("Skillet", "Unleashed")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    _touch(tmp_path, "a.flac")
    _touch(tmp_path, "b.flac")
    _touch(tmp_path, "cover.jpg")
    _touch(tmp_path, "notes.txt")

    result = album_sort.sort_folder(tmp_path)

    assert sorted(p.name for p in result) == ["Caskets - Lost Souls", "Skillet - Unleashed"]
    assert (tmp_path / "cover.jpg").exists(), "a cover image must be left exactly where it was"
    assert (tmp_path / "notes.txt").exists()


def test_loose_audio_files_reports_only_audio(tmp_path):
    _touch(tmp_path, "track.flac")
    _touch(tmp_path, "track.mp3")
    _touch(tmp_path, "cover.jpg")
    (tmp_path / "Some Album").mkdir()

    assert [p.name for p in album_sort.loose_audio_files(tmp_path)] == ["track.flac", "track.mp3"]


def test_loose_audio_files_and_has_album_subfolders_tolerate_a_missing_folder(tmp_path):
    """Both are read by the chat dialog to decide button state, which can
    happen before anything has ever been downloaded."""
    missing = tmp_path / "not-there"
    assert album_sort.loose_audio_files(missing) == []
    assert album_sort.has_album_subfolders(missing) is False


def test_has_album_subfolders_ignores_loose_files(tmp_path):
    _touch(tmp_path, "a.flac")
    assert album_sort.has_album_subfolders(tmp_path) is False

    (tmp_path / "Some Album").mkdir()
    assert album_sort.has_album_subfolders(tmp_path) is True


def test_grouping_by_album_tag_takes_priority(tmp_path, monkeypatch):
    a1 = _touch(tmp_path, "a1.flac")
    a2 = _touch(tmp_path, "a2.flac")
    b1 = _touch(tmp_path, "b1.flac")
    b2 = _touch(tmp_path, "b2.flac")

    tags = {
        a1: ("Caskets", "Lost Souls"),
        a2: ("Caskets", "Lost Souls"),
        b1: ("Skillet", "Unleashed"),
        b2: ("Skillet", "Unleashed"),
    }
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p])

    # All four arrived as one unbroken run -- if arrival-batch grouping won
    # instead of the tag, this would produce one folder, not two.
    result = album_sort.sort_downloads(tmp_path, {1: a1, 2: a2, 3: b1, 4: b2}, [1, 2, 3, 4])

    names = sorted(p.name for p in result)
    assert names == ["Caskets - Lost Souls", "Skillet - Unleashed"]
    assert (tmp_path / "Caskets - Lost Souls" / "a1.flac").exists()
    assert (tmp_path / "Caskets - Lost Souls" / "a2.flac").exists()
    assert (tmp_path / "Skillet - Unleashed" / "b1.flac").exists()
    assert (tmp_path / "Skillet - Unleashed" / "b2.flac").exists()
    assert not a1.exists()  # moved, not copied


def test_a_featured_artist_credit_does_not_split_the_album(tmp_path, monkeypatch):
    """Regression: reported directly -- a track credited to "Skillet, Lacey
    Sturm" (a guest feature) used to land in its own folder, apart from the
    rest of the same album tagged plainly "Skillet", because grouping used
    to key on artist+album per file rather than ALBUM alone."""
    a1 = _touch(tmp_path, "a1.flac")
    a2 = _touch(tmp_path, "a2.flac")
    collab = _touch(tmp_path, "a3.flac")

    tags = {
        a1: ("Skillet", "Unleashed"),
        a2: ("Skillet", "Unleashed"),
        collab: ("Skillet, Lacey Sturm", "Unleashed"),
    }
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p])

    # A second, genuinely different album so there is something for the
    # majority-vote naming to prove itself against -- with only one album
    # total, sort_downloads() would no-op regardless of whether the bug is
    # present.
    b1 = _touch(tmp_path, "b1.flac")
    b2 = _touch(tmp_path, "b2.flac")
    tags[b1] = ("Caskets", "Lost Souls")
    tags[b2] = ("Caskets", "Lost Souls")

    result = album_sort.sort_downloads(
        tmp_path, {1: a1, 2: a2, 3: collab, 4: b1, 5: b2}, [1, 2, 3, 4, 5]
    )

    names = sorted(p.name for p in result)
    assert names == ["Caskets - Lost Souls", "Skillet - Unleashed"]
    assert (tmp_path / "Skillet - Unleashed" / "a1.flac").exists()
    assert (tmp_path / "Skillet - Unleashed" / "a2.flac").exists()
    assert (tmp_path / "Skillet - Unleashed" / "a3.flac").exists()


def test_sort_folder_a_featured_artist_credit_does_not_split_the_album(tmp_path, monkeypatch):
    a1 = _touch(tmp_path, "a1.flac")
    a2 = _touch(tmp_path, "a2.flac")
    collab = _touch(tmp_path, "a3.flac")
    b1 = _touch(tmp_path, "b1.flac")

    tags = {
        a1: ("Skillet", "Unleashed"),
        a2: ("Skillet", "Unleashed"),
        collab: ("Skillet, Lacey Sturm", "Unleashed"),
        b1: ("Caskets", "Lost Souls"),
    }
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p])

    result = album_sort.sort_folder(tmp_path)

    names = sorted(p.name for p in result)
    assert names == ["Caskets - Lost Souls", "Skillet - Unleashed"]
    unleashed = sorted(p.name for p in (tmp_path / "Skillet - Unleashed").iterdir())
    assert unleashed == ["a1.flac", "a2.flac", "a3.flac"]


def test_untagged_files_fall_back_to_arrival_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: ("", ""))
    a1 = _touch(tmp_path, "a1.mp3")
    a2 = _touch(tmp_path, "a2.mp3")
    b1 = _touch(tmp_path, "b1.mp3")

    # id 10 is a non-file message (a status update) separating the batches.
    result = album_sort.sort_downloads(tmp_path, {1: a1, 2: a2, 11: b1}, [1, 2, 10, 11])

    names = sorted(p.name for p in result)
    assert names == ["Album 1", "Album 2"]
    assert (tmp_path / "Album 1" / "a1.mp3").exists()
    assert (tmp_path / "Album 1" / "a2.mp3").exists()
    assert (tmp_path / "Album 2" / "b1.mp3").exists()


def test_tagged_and_untagged_files_can_both_be_grouped_in_one_pass(tmp_path, monkeypatch):
    tagged = _touch(tmp_path, "tagged.flac")
    untagged1 = _touch(tmp_path, "untagged1.mp3")
    untagged2 = _touch(tmp_path, "untagged2.mp3")

    def fake_tag(path):
        return ("Caskets", "Lost Souls") if path == tagged else ("", "")

    monkeypatch.setattr(album_sort, "read_album_tag", fake_tag)

    result = album_sort.sort_downloads(
        tmp_path, {1: tagged, 2: untagged1, 3: untagged2}, [1, 2, 3]
    )

    names = sorted(p.name for p in result)
    assert names == ["Album 1", "Caskets - Lost Souls"]
    assert (tmp_path / "Caskets - Lost Souls" / "tagged.flac").exists()
    assert (tmp_path / "Album 1" / "untagged1.mp3").exists()
    assert (tmp_path / "Album 1" / "untagged2.mp3").exists()


def test_a_second_call_after_sorting_is_a_no_op(tmp_path, monkeypatch):
    """Anything already moved into a subfolder is no longer "directly in
    root", so it is simply invisible to a repeat call -- no special-casing
    needed at the call site for "already sorted"."""
    tags = {"a.flac": ("Caskets", "Lost Souls"), "b.flac": ("Skillet", "Unleashed")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    a = _touch(tmp_path, "a.flac")
    b = _touch(tmp_path, "b.flac")

    first = album_sort.sort_downloads(tmp_path, {1: a, 2: b}, [1, 2])
    assert len(first) == 2

    moved_a = tmp_path / "Caskets - Lost Souls" / "a.flac"
    moved_b = tmp_path / "Skillet - Unleashed" / "b.flac"
    second = album_sort.sort_downloads(tmp_path, {1: moved_a, 2: moved_b}, [1, 2])
    assert second == []


def test_untagged_and_unbatched_single_files_do_not_get_grouped_together(tmp_path, monkeypatch):
    """Two files with no shared tag and no shared arrival batch (a
    non-file message separates them) stay two separate single-file
    "albums" -- sort_downloads still creates two folders for them, since
    that is two groups, not one."""
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: ("", ""))
    a = _touch(tmp_path, "a.mp3")
    b = _touch(tmp_path, "b.mp3")

    result = album_sort.sort_downloads(tmp_path, {1: a, 3: b}, [1, 2, 3])

    assert len(result) == 2


# --- sort_folder (standalone, no chat session) --------------------------


def test_sort_folder_groups_by_tag_alone(tmp_path, monkeypatch):
    tags = {"a.flac": ("Caskets", "Lost Souls"), "b.flac": ("Skillet", "Unleashed")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    _touch(tmp_path, "a.flac")
    _touch(tmp_path, "b.flac")

    result = album_sort.sort_folder(tmp_path)

    names = sorted(p.name for p in result)
    assert names == ["Caskets - Lost Souls", "Skillet - Unleashed"]
    assert (tmp_path / "Caskets - Lost Souls" / "a.flac").exists()
    assert (tmp_path / "Skillet - Unleashed" / "b.flac").exists()


def test_sort_folder_puts_every_untagged_file_in_one_unsorted_folder(tmp_path, monkeypatch):
    # One tagged file alongside three untagged ones, so there is a second
    # group for "Unsorted" to be distinguishable from (with only one group
    # total, _create_folders_and_move() would move nothing at all).
    tags = {"tagged.flac": ("Caskets", "Lost Souls")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags.get(p.name, ("", "")))
    _touch(tmp_path, "a.mp3")
    _touch(tmp_path, "b.mp3")
    _touch(tmp_path, "c.mp3")
    _touch(tmp_path, "tagged.flac")

    result = album_sort.sort_folder(tmp_path)

    names = sorted(p.name for p in result)
    assert names == ["Caskets - Lost Souls", "Unsorted"]
    unsorted_files = sorted(p.name for p in (tmp_path / "Unsorted").iterdir())
    assert unsorted_files == ["a.mp3", "b.mp3", "c.mp3"]


def test_sort_folder_with_only_one_group_moves_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: ("Caskets", "Lost Souls"))
    a = _touch(tmp_path, "a.flac")
    b = _touch(tmp_path, "b.flac")

    result = album_sort.sort_folder(tmp_path)

    assert result == []
    assert a.exists() and b.exists()


def test_sort_folder_with_fewer_than_two_files_moves_nothing(tmp_path):
    _touch(tmp_path, "a.flac")
    assert album_sort.sort_folder(tmp_path) == []


def test_sort_folder_ignores_subfolders_already_sorted(tmp_path, monkeypatch):
    """A second call only sees files still directly in root -- same
    idempotency guarantee sort_downloads() gives, via the same shared
    _create_folders_and_move()."""
    tags = {"a.flac": ("Caskets", "Lost Souls"), "b.flac": ("Skillet", "Unleashed")}
    monkeypatch.setattr(album_sort, "read_album_tag", lambda p: tags[p.name])
    _touch(tmp_path, "a.flac")
    _touch(tmp_path, "b.flac")

    first = album_sort.sort_folder(tmp_path)
    assert len(first) == 2

    second = album_sort.sort_folder(tmp_path)
    assert second == []
