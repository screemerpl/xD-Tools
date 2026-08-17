from mdtools.app_window import MainWindow
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.panels.startup_dialog import StartupDialog
from mdtools.project import PAGE_COVER, PAGE_DISC
from mdtools.templates import registry


def _skip_straight_to_new_project_dialog(monkeypatch):
    """StartupDialog now appears before NewDesignDialog at startup --
    these tests only care about NewDesignDialog's own behavior, so this
    fakes choosing "New Project..." in the startup dialog (result_path
    stays None) to fall straight through to it."""
    monkeypatch.setattr(StartupDialog, "exec", lambda self: StartupDialog.DialogCode.Accepted)


def _isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")


def test_save_as_template_captures_the_current_pages_layers(qt_app, tmp_path, monkeypatch):
    from mdtools import app_window as app_window_module

    _isolated_registry(tmp_path, monkeypatch)
    monkeypatch.setattr(
        app_window_module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("My Layout", True))
    )

    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_DISC)
    scene = win._current_scene()
    original_item_count = len(scene.print_items())  # the auto-seeded triangle + label
    win._add_text()

    win._save_as_template()

    templates = registry.load_templates()
    saved = next(t for t in templates["disc"] if t.name == "My Layout")
    assert saved.builtin is False
    assert len(saved.items) == original_item_count + 1
    assert saved.width_mm == scene.template.width_mm  # shape cloned from the current template


def test_cancelling_the_name_prompt_saves_nothing(qt_app, tmp_path, monkeypatch):
    from mdtools import app_window as app_window_module

    _isolated_registry(tmp_path, monkeypatch)
    monkeypatch.setattr(app_window_module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("", False)))

    win = MainWindow(show_startup_dialog=False)
    before = len(registry.load_templates()["disc"])

    win._save_as_template()

    assert len(registry.load_templates()["disc"]) == before


def test_an_empty_name_saves_nothing(qt_app, tmp_path, monkeypatch):
    from mdtools import app_window as app_window_module

    _isolated_registry(tmp_path, monkeypatch)
    monkeypatch.setattr(app_window_module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("   ", True)))

    win = MainWindow(show_startup_dialog=False)
    before = len(registry.load_templates()["disc"])

    win._save_as_template()

    assert len(registry.load_templates()["disc"]) == before


def test_saving_from_the_cover_page_appends_to_the_cover_list(qt_app, tmp_path, monkeypatch):
    from mdtools import app_window as app_window_module

    _isolated_registry(tmp_path, monkeypatch)
    monkeypatch.setattr(
        app_window_module.QInputDialog, "getText", staticmethod(lambda *a, **k: ("Cover Layout", True))
    )

    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_COVER)
    win._add_rectangle()

    win._save_as_template()

    templates = registry.load_templates()
    assert any(t.name == "Cover Layout" for t in templates["cover"])
    assert not any(t.name == "Cover Layout" for t in templates["disc"])


def test_new_project_from_a_template_with_items_recreates_them_instead_of_seeding_defaults(qt_app, monkeypatch):
    import copy

    from mdtools.canvas.scene import DesignScene
    from mdtools.io.project_io import item_to_dict

    disc_template = registry.load_templates()["disc"][0]
    scratch_scene = DesignScene(copy.deepcopy(disc_template))
    text_item = scratch_scene.add_text("Custom Layout Text")
    saved_template = copy.deepcopy(disc_template)
    saved_template.name = "Precreated"
    saved_template.items = [item_to_dict(text_item)]

    cover_template = registry.load_templates()["cover"][0]

    def fake_exec(self):
        self.selected_disc_template = saved_template
        self.selected_cover_template = cover_template
        return NewDesignDialog.DialogCode.Accepted

    monkeypatch.setattr(NewDesignDialog, "exec", fake_exec)
    _skip_straight_to_new_project_dialog(monkeypatch)

    win = MainWindow()

    disc_items = win.project.pages[PAGE_DISC].print_items()
    assert len(disc_items) == 1
    assert disc_items[0].toPlainText() == "Custom Layout Text"


def test_new_project_from_a_template_without_items_still_seeds_defaults(qt_app, monkeypatch):
    templates = registry.load_templates()
    disc_template = templates["disc"][0]
    cover_template = templates["cover"][0]
    assert not disc_template.items  # sanity: the built-in has no pre-made layers

    def fake_exec(self):
        self.selected_disc_template = disc_template
        self.selected_cover_template = cover_template
        return NewDesignDialog.DialogCode.Accepted

    monkeypatch.setattr(NewDesignDialog, "exec", fake_exec)
    _skip_straight_to_new_project_dialog(monkeypatch)

    win = MainWindow()

    disc_texts = {i.toPlainText() for i in win.project.pages[PAGE_DISC].print_items()}
    assert "INSERT THIS END" in disc_texts
