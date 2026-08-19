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


# The template families, and what each one is built from. "label" arrived
# with the cassette: a shell sticker is the same rectangle a cover is, so
# it shares CoverTemplate -- but it is not interchangeable with one, and
# keeping them one family let File > New offer a J-card for a page that
# wants a sticker.
KINDS = ("disc", "cover", "label")
_MODELS = {"disc": DiscTemplate, "cover": CoverTemplate, "label": CoverTemplate}


def _parse(data: dict) -> dict[str, list]:
    return {
        kind: [_MODELS[kind](**dict(item)) for item in data.get(kind, [])] for kind in KINDS
    }


def load_templates() -> dict[str, list]:
    path = _ensure_user_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    return _parse(data)


def save_templates(templates: dict[str, list]) -> None:
    def to_dict(t):
        d = dict(t.__dict__)
        return d

    data = {kind: [to_dict(t) for t in templates.get(kind, [])] for kind in KINDS}
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

    changed = _rehome_moved_builtins(current, bundled)
    for kind in KINDS:
        existing_builtin_names = {t.name for t in current[kind] if t.builtin}
        for template in bundled[kind]:
            if template.builtin and template.name not in existing_builtin_names:
                current[kind].append(template)
                changed = True

    if changed:
        save_templates(current)
    return changed


def _rehome_moved_builtins(current: dict[str, list], bundled: dict[str, list]) -> bool:
    """Moves a built-in that has since changed family, keeping the user's
    own edits to it.

    Only ever needed when a template family is split, which happened once:
    the cassette shell label started life as a "cover" and became a
    "label", and a copy left behind in the old family is exactly the bug
    that split fixes -- it would go on being offered where a J-card
    belongs.

    The bundled version replaces the old entry rather than the old entry
    being carried across, and that is deliberate: a built-in that has
    changed family has changed *shape* -- this one grew the two holes a
    cassette's reel hubs come up through -- so its old dimensions no
    longer describe anything. This is the one case where sync overwrites
    instead of appending, and it is why it is kept to built-ins whose
    family actually moved.
    """
    home = {t.name: (kind, t) for kind in KINDS for t in bundled[kind] if t.builtin}
    changed = False
    for kind in KINDS:
        for template in list(current[kind]):
            wanted = home.get(template.name)
            if not template.builtin or wanted is None or wanted[0] == kind:
                continue
            current[kind].remove(template)
            current[wanted[0]].append(wanted[1])
            changed = True
    return changed
