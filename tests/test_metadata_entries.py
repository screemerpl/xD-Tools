from mdtools.project import (
    ProjectMetadata,
    Track,
    metadata_column_entries,
    metadata_menu_entries,
    track_list_two_columns,
)


def test_empty_metadata_has_no_entries():
    assert metadata_menu_entries(ProjectMetadata()) == []


def test_entries_skip_unset_fields_but_include_set_ones():
    metadata = ProjectMetadata(album="Mix Tape", artist="", year=2001)
    labels = [label for label, _ in metadata_menu_entries(metadata)]
    assert "Album Title" in labels
    assert "Year" in labels
    assert "Artist" not in labels


def test_tracks_produce_only_the_full_list_not_individual_entries():
    metadata = ProjectMetadata(tracks=[Track(title="Intro", time_seconds=95), Track(title="Outro")])
    entries = dict(metadata_menu_entries(metadata))

    assert entries == {"Full Track List": "1. Intro (1:35)\n2. Outro"}


def test_two_columns_is_empty_with_no_tracks():
    assert track_list_two_columns(ProjectMetadata()) == []
    assert metadata_column_entries(ProjectMetadata()) == []


def test_two_columns_splits_evenly_and_continues_numbering():
    metadata = ProjectMetadata(tracks=[Track(title=f"Track {i}") for i in range(1, 7)])  # 6 tracks
    columns = track_list_two_columns(metadata)

    assert len(columns) == 2
    assert columns[0] == "1. Track 1\n2. Track 2\n3. Track 3"
    assert columns[1] == "4. Track 4\n5. Track 5\n6. Track 6"


def test_two_columns_puts_the_extra_track_in_the_first_column_for_odd_counts():
    metadata = ProjectMetadata(tracks=[Track(title=f"Track {i}") for i in range(1, 6)])  # 5 tracks
    columns = track_list_two_columns(metadata)

    assert columns[0] == "1. Track 1\n2. Track 2\n3. Track 3"
    assert columns[1] == "4. Track 4\n5. Track 5"


def test_metadata_column_entries_has_a_two_column_track_list_label():
    metadata = ProjectMetadata(tracks=[Track(title="Intro")])
    entries = dict(metadata_column_entries(metadata))
    assert entries["Full Track List (2 Columns)"] == track_list_two_columns(metadata)
