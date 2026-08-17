"""In-memory copy/paste of canvas items.

Reuses the exact same serialization project files use (item_to_dict /
item_from_dict), so a paste is a true independent clone -- including a
paste onto the *other* page (disc <-> cover), since the clipboard only
holds plain dicts, not live item references.
"""

from __future__ import annotations

from mdtools.io.project_io import item_from_dict, item_to_dict

PASTE_OFFSET_PX = 10  # nudge so a paste doesn't land exactly on top of the original


class Clipboard:
    def __init__(self):
        self._items: list[dict] = []

    def copy(self, items) -> None:
        self._items = [d for i in items if (d := item_to_dict(i)) is not None]

    def has_content(self) -> bool:
        return bool(self._items)

    def paste_into(self, scene) -> list:
        """Adds clones of whatever was last copied to `scene`, offset
        slightly and raised above everything else, preserving their
        relative stacking order. Returns the newly created items."""
        pasted = []
        for data in self._items:
            offset_data = dict(data, x=data.get("x", 0) + PASTE_OFFSET_PX, y=data.get("y", 0) + PASTE_OFFSET_PX)
            item = item_from_dict(scene, offset_data)
            if item is not None:
                pasted.append(item)

        base_z = scene.next_print_z()
        for offset, item in enumerate(pasted):
            item.setZValue(base_z + offset)
        return pasted
