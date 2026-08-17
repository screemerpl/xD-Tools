import json

from mdtools.templates import registry
from mdtools.templates.models import CoverTemplate, DiscTemplate


def test_fresh_install_has_nothing_new_to_add(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    # first ever load seeds the user file with the full bundled defaults --
    # sync should find nothing missing
    registry.load_templates()

    changed = registry.sync_builtin_templates()

    assert changed is False


def test_adds_a_builtin_missing_from_an_older_users_file(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    all_builtin_names = {t.name for t in registry.load_templates()["disc"]}

    # simulate a pre-upgrade templates.json that only knows about the very
    # first built-in disc template (as if it were seeded by an older app
    # version, before later built-ins were added to defaults.json)
    old_only = registry.load_templates()["disc"][0]
    (tmp_path / "templates.json").write_text(
        json.dumps({"disc": [dict(old_only.__dict__)], "cover": []}, indent=2), encoding="utf-8"
    )

    changed = registry.sync_builtin_templates()

    assert changed is True
    reloaded_names = {t.name for t in registry.load_templates()["disc"]}
    assert reloaded_names == all_builtin_names


def test_never_overwrites_an_already_present_builtin_even_if_user_edited_it(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    templates = registry.load_templates()
    templates["disc"][0].width_mm = 999.0  # simulate a Template Manager edit
    registry.save_templates(templates)

    registry.sync_builtin_templates()

    assert registry.load_templates()["disc"][0].width_mm == 999.0


def test_preserves_user_created_non_builtin_templates(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    templates = registry.load_templates()
    templates["disc"].append(DiscTemplate(name="My Custom Disc", width_mm=10.0, height_mm=10.0, builtin=False))
    templates["cover"].append(CoverTemplate(name="My Custom Cover", width_mm=10.0, height_mm=10.0, builtin=False))
    registry.save_templates(templates)

    registry.sync_builtin_templates()

    reloaded = registry.load_templates()
    assert any(t.name == "My Custom Disc" and not t.builtin for t in reloaded["disc"])
    assert any(t.name == "My Custom Cover" and not t.builtin for t in reloaded["cover"])


def test_calling_it_twice_in_a_row_is_a_no_op_the_second_time(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "user_templates_path", lambda: tmp_path / "templates.json")
    old_only = registry.load_templates()["disc"][0]
    (tmp_path / "templates.json").write_text(
        json.dumps({"disc": [dict(old_only.__dict__)], "cover": []}, indent=2), encoding="utf-8"
    )

    assert registry.sync_builtin_templates() is True
    assert registry.sync_builtin_templates() is False
