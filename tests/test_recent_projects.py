from mdtools import recent_projects

# Settings are isolated to a per-test tmp file automatically by conftest.py's
# autouse _isolated_recent_projects_settings fixture -- no local fixture
# needed here.


def _touch(path) -> str:
    path.write_text("{}", encoding="utf-8")
    return str(path)


def test_no_recent_projects_by_default():
    assert recent_projects.recent_projects() == []


def test_adding_a_project_makes_it_the_most_recent(tmp_path):
    a = _touch(tmp_path / "a.mdproj")
    b = _touch(tmp_path / "b.mdproj")

    recent_projects.add_recent_project(a)
    recent_projects.add_recent_project(b)

    assert recent_projects.recent_projects() == [b, a]


def test_re_adding_an_existing_entry_moves_it_to_the_front_without_duplicating(tmp_path):
    a = _touch(tmp_path / "a.mdproj")
    b = _touch(tmp_path / "b.mdproj")

    recent_projects.add_recent_project(a)
    recent_projects.add_recent_project(b)
    recent_projects.add_recent_project(a)

    assert recent_projects.recent_projects() == [a, b]


def test_list_is_trimmed_to_max_recent(tmp_path):
    paths = [_touch(tmp_path / f"p{i}.mdproj") for i in range(recent_projects.MAX_RECENT + 3)]
    for path in paths:
        recent_projects.add_recent_project(path)

    result = recent_projects.recent_projects()
    assert len(result) == recent_projects.MAX_RECENT
    assert result == list(reversed(paths))[: recent_projects.MAX_RECENT]


def test_a_deleted_projects_entry_is_dropped_from_the_list(tmp_path):
    a = _touch(tmp_path / "a.mdproj")
    b = _touch(tmp_path / "b.mdproj")
    recent_projects.add_recent_project(a)
    recent_projects.add_recent_project(b)

    (tmp_path / "b.mdproj").unlink()

    assert recent_projects.recent_projects() == [a]
