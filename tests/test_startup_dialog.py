from mdtools import recent_projects
from mdtools.app_window import MainWindow
from mdtools.io.project_io import save_project
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.panels.startup_dialog import StartupDialog
from mdtools.project import PAGE_COVER, PAGE_DISC, ProjectMetadata
from mdtools.templates import registry


def _fake_new_project_choice(disc, cover):
    def fake_exec(self):
        self.selected_disc_template = disc
        self.selected_cover_template = cover
        return NewDesignDialog.DialogCode.Accepted

    return fake_exec


def test_startup_shows_the_startup_dialog_first(qt_app, monkeypatch):
    """Choosing "New Project..." in StartupDialog (result_path stays None)
    falls through to the existing NewDesignDialog template-picker flow --
    the entry point changed, but what happens once "New Project" is chosen
    is unchanged."""
    templates = registry.load_templates()
    chosen_disc = templates["disc"][0]
    chosen_cover = templates["cover"][-1]  # not just the default, to prove it's really used

    monkeypatch.setattr(StartupDialog, "exec", lambda self: StartupDialog.DialogCode.Accepted)
    monkeypatch.setattr(NewDesignDialog, "exec", _fake_new_project_choice(chosen_disc, chosen_cover))

    win = MainWindow()  # show_startup_dialog defaults to True

    assert win.project.pages[PAGE_DISC].template.name == chosen_disc.name
    assert win.project.pages[PAGE_COVER].template.name == chosen_cover.name


def test_choosing_a_recent_project_in_the_startup_dialog_opens_it_directly(qt_app, monkeypatch, tmp_path):
    other = MainWindow(show_startup_dialog=False)
    other.project.metadata = ProjectMetadata(album="Recent Album", artist="Recent Artist")
    path = tmp_path / "recent.mdproj"
    save_project(other.project, path)

    def fake_exec(self):
        self.result_path = str(path)
        return StartupDialog.DialogCode.Accepted

    monkeypatch.setattr(StartupDialog, "exec", fake_exec)

    def fail_if_shown(self):
        raise AssertionError("NewDesignDialog should not appear when a recent project was chosen")

    monkeypatch.setattr(NewDesignDialog, "exec", fail_if_shown)

    win = MainWindow()

    assert win.project.metadata.album == "Recent Album"
    assert win.current_project_path == str(path)


def test_cancelling_the_startup_dialog_outright_means_quit_not_a_blank_project(qt_app, monkeypatch):
    """Reported directly as making Cancel useless: it used to silently
    create an untitled project and show the main window regardless of what
    was clicked. Cancel here now means the same thing it already means
    when returning to the startup screen after closing a project -- "I
    actually want out" -- which main.py acts on via startup_cancelled
    before ever calling show()."""
    monkeypatch.setattr(StartupDialog, "exec", lambda self: StartupDialog.DialogCode.Rejected)

    def fail_if_shown(self):
        raise AssertionError("NewDesignDialog should not appear if the startup dialog was cancelled outright")

    monkeypatch.setattr(NewDesignDialog, "exec", fail_if_shown)

    win = MainWindow()

    assert win.startup_cancelled is True
    assert win.project is None


def test_cancelling_new_project_after_choosing_new_falls_back_to_default_templates(qt_app, monkeypatch):
    """Different from cancelling the StartupDialog itself: the user
    positively chose "New Project..." (accepting StartupDialog), and only
    backed out of the *template picker* -- that is a more local
    cancellation than "I want out", so it must not be treated as
    startup_cancelled and must not quit."""
    monkeypatch.setattr(StartupDialog, "exec", lambda self: StartupDialog.DialogCode.Accepted)
    monkeypatch.setattr(NewDesignDialog, "exec", lambda self: NewDesignDialog.DialogCode.Rejected)

    win = MainWindow()

    assert win.startup_cancelled is False
    assert win.project is not None
    assert win.project.pages[PAGE_DISC] is not None
    assert win.project.pages[PAGE_COVER] is not None


def test_show_startup_dialog_false_skips_both_dialogs_entirely(qt_app, monkeypatch):
    def fail_if_shown(self):
        raise AssertionError("dialog should not be shown when show_startup_dialog=False")

    monkeypatch.setattr(StartupDialog, "exec", fail_if_shown)
    monkeypatch.setattr(NewDesignDialog, "exec", fail_if_shown)

    win = MainWindow(show_startup_dialog=False)

    assert win.project is not None


def test_startup_dialog_is_seeded_with_the_current_recent_projects_list(qt_app, monkeypatch, tmp_path):
    path = str(tmp_path / "existing.mdproj")
    (tmp_path / "existing.mdproj").write_text("{}", encoding="utf-8")
    recent_projects.add_recent_project(path)

    captured = {}

    def fake_init(self, recent_paths, parent=None):
        captured["recent_paths"] = recent_paths
        self.result_path = None

    monkeypatch.setattr(StartupDialog, "__init__", fake_init)
    monkeypatch.setattr(StartupDialog, "exec", lambda self: StartupDialog.DialogCode.Rejected)

    MainWindow()

    assert captured["recent_paths"] == [path]
