"""Loads/saves label templates.

Templates ship with unverified placeholder dimensions (see defaults.json).
On first run they are copied into a per-user, writable JSON file so edits
made in the Template Manager persist across app updates.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

from PySide6.QtCore import QStandardPaths

from mdtools.templates.models import CoverTemplate, DiscTemplate

_BUNDLED_DEFAULTS = "defaults.json"


def user_templates_path() -> Path:
    config_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "templates.json"


def _bundled_defaults_text() -> str:
    return resources.files("mdtools.templates").joinpath(_BUNDLED_DEFAULTS).read_text(encoding="utf-8")


def _ensure_user_file() -> Path:
    path = user_templates_path()
    if not path.exists():
        path.write_text(_bundled_defaults_text(), encoding="utf-8")
    return path


def _parse(data: dict) -> dict[str, list]:
    discs = [DiscTemplate(**{k: v for k, v in item.items()}) for item in data.get("disc", [])]
    covers = [CoverTemplate(**{k: v for k, v in item.items()}) for item in data.get("cover", [])]
    return {"disc": discs, "cover": covers}


def load_templates() -> dict[str, list]:
    path = _ensure_user_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    return _parse(data)


def save_templates(templates: dict[str, list]) -> None:
    def to_dict(t):
        d = dict(t.__dict__)
        return d

    data = {
        "disc": [to_dict(t) for t in templates.get("disc", [])],
        "cover": [to_dict(t) for t in templates.get("cover", [])],
    }
    user_templates_path().write_text(json.dumps(data, indent=2), encoding="utf-8")


def sync_builtin_templates() -> bool:
    """Adds any built-in template from the bundled defaults.json that
    isn't already present (matched by name) in the user's templates.json
    -- e.g. a new template shipped by an app update, which would otherwise
    never appear for someone who already has a templates.json from an
    older version (that file is only ever seeded once, on first run --
    see _ensure_user_file -- so it doesn't pick up later additions to
    defaults.json on its own).

    Existing entries are never touched, including built-ins the user has
    since edited via the Template Manager -- this only ever appends,
    never overwrites, so no edit is at risk of being silently reverted.
    Safe to call unconditionally on every app start. Returns True if
    anything was added.
    """
    current = load_templates()
    bundled = _parse(json.loads(_bundled_defaults_text()))

    changed = False
    for kind in ("disc", "cover"):
        existing_builtin_names = {t.name for t in current[kind] if t.builtin}
        for template in bundled[kind]:
            if template.builtin and template.name not in existing_builtin_names:
                current[kind].append(template)
                changed = True

    if changed:
        save_templates(current)
    return changed
