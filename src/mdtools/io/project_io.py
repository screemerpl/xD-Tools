"""Save/load a Project (metadata + disc page + cover page) as a single,
self-contained .mdproj JSON file.

Each page's template spec is embedded (not just referenced by name) so a
project still opens correctly even if the user later edits or deletes that
template from their Template Manager. Images (including the metadata
album cover fetched via "Lookup Track List...") are embedded as
base64-encoded bytes rather than referenced by file path, so a .mdproj
file is fully portable -- moving/renaming/deleting the original source
image afterwards does not break the project.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsTextItem

from mdtools.canvas.items import LAYER_ROLE, get_item_name, get_item_scale, set_item_name, set_item_scale
from mdtools.canvas.scene import DesignScene
from mdtools.project import PAGE_COVER, PAGE_DISC, GrayscaleAdjustment, Project, ProjectMetadata, TextStyle, Track
from mdtools.templates.models import CoverTemplate, DiscTemplate

PROJECT_VERSION = 5


def _pixmap_to_base64_png(item: QGraphicsPixmapItem) -> str:
    buffer = QByteArray()
    device = QBuffer(buffer)
    device.open(QIODevice.OpenModeFlag.WriteOnly)
    item.pixmap().save(device, "PNG")
    device.close()
    return base64.b64encode(bytes(buffer)).decode("ascii")


def item_to_dict(item) -> dict | None:
    scale_x, scale_y = get_item_scale(item)
    common = {
        "x": item.x(),
        "y": item.y(),
        "rotation": item.rotation(),
        "scale_x": scale_x,
        "scale_y": scale_y,
        "z": item.zValue(),
        "name": get_item_name(item),
    }
    if isinstance(item, QGraphicsTextItem):
        return {
            **common,
            "type": "text",
            "text": item.toPlainText(),
            # QFont.toString() -- not just family/size -- so bold, italic,
            # underline, strikeout, weight, etc. survive save/load too.
            "font_spec": item.font().toString(),
            "color": item.defaultTextColor().name(),
        }
    if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
        rect = item.rect()
        return {
            **common,
            "type": "rect" if isinstance(item, QGraphicsRectItem) else "ellipse",
            "w": rect.width(),
            "h": rect.height(),
            "brush_color": item.brush().color().name(),
            "pen_color": item.pen().color().name(),
        }
    if isinstance(item, QGraphicsPixmapItem):
        return {
            **common,
            "type": "image",
            "image_format": "png",
            "image_data_base64": _pixmap_to_base64_png(item),
        }
    return None


def _template_from_dict(data: dict):
    if data.get("kind") == "disc":
        return DiscTemplate(**data)
    return CoverTemplate(**data)


def item_from_dict(scene: DesignScene, item_data: dict):
    """Recreate one item (text/rect/ellipse/image) from `item_to_dict()`
    output, adding it to `scene`. Shared by project load and copy/paste
    (see clipboard.py) so both go through the exact same, already-tested
    reconstruction logic. Returns None if the item couldn't be recreated
    (e.g. an image whose bytes fail to decode)."""
    kind = item_data["type"]
    if kind == "text":
        item = scene.add_text(item_data["text"])
        font = QFont()
        font.fromString(item_data["font_spec"])
        item.setFont(font)
        item.setDefaultTextColor(QColor(item_data["color"]))
        item.setTransformOriginPoint(item.boundingRect().center())
    elif kind in ("rect", "ellipse"):
        item = scene.add_rectangle() if kind == "rect" else scene.add_ellipse()
        item.setRect(0, 0, item_data["w"], item_data["h"])
        brush = item.brush()
        brush.setColor(QColor(item_data["brush_color"]))
        item.setBrush(brush)
        pen = item.pen()
        pen.setColor(QColor(item_data["pen_color"]))
        item.setPen(pen)
        item.setTransformOriginPoint(item.boundingRect().center())
    elif kind == "image":
        raw = base64.b64decode(item_data["image_data_base64"])
        item = scene.add_image_from_data(raw)
        if item is None:
            return None
    else:
        return None
    item.setPos(item_data["x"], item_data["y"])
    item.setRotation(item_data["rotation"])
    set_item_scale(item, item_data.get("scale_x", 1.0), item_data.get("scale_y", 1.0))
    item.setZValue(item_data.get("z", 0.0))
    set_item_name(item, item_data.get("name"))
    return item


def _scene_to_dict(scene: DesignScene) -> dict:
    items = [
        d
        for i in scene.items()
        if i.data(LAYER_ROLE) not in ("cut", "fold") and (d := item_to_dict(i)) is not None
    ]
    return {"template": dict(scene.template.__dict__), "items": items}


def _scene_from_dict(data: dict) -> DesignScene:
    template = _template_from_dict(data["template"])
    scene = DesignScene(template)
    for item_data in data.get("items", []):
        item_from_dict(scene, item_data)
    return scene


def _text_style_to_dict(style: TextStyle) -> dict:
    return {"font_spec": style.font_spec, "color": style.color}


def _text_style_from_dict(data: dict) -> TextStyle:
    return TextStyle(
        font_spec=data.get("font_spec"),
        color=data.get("color"),
    )


def _grayscale_adjustment_to_dict(adjustment: GrayscaleAdjustment) -> dict:
    return {"brightness": adjustment.brightness, "contrast": adjustment.contrast}


def _grayscale_adjustment_from_dict(data: dict) -> GrayscaleAdjustment:
    return GrayscaleAdjustment(brightness=data.get("brightness", 0), contrast=data.get("contrast", 0))


def _metadata_to_dict(metadata: ProjectMetadata) -> dict:
    return {
        "album": metadata.album,
        "artist": metadata.artist,
        "year": metadata.year,
        "tracks": [{"title": t.title, "time_seconds": t.time_seconds} for t in metadata.tracks],
        "cover_art_base64": base64.b64encode(metadata.cover_art).decode("ascii") if metadata.cover_art else None,
    }


def _metadata_from_dict(data: dict) -> ProjectMetadata:
    cover_art_base64 = data.get("cover_art_base64")
    return ProjectMetadata(
        album=data.get("album", ""),
        artist=data.get("artist", ""),
        year=data.get("year"),
        tracks=[Track(title=t["title"], time_seconds=t.get("time_seconds")) for t in data.get("tracks", [])],
        cover_art=base64.b64decode(cover_art_base64) if cover_art_base64 else None,
    )


def project_to_dict(project: Project) -> dict:
    return {
        "version": PROJECT_VERSION,
        "metadata": _metadata_to_dict(project.metadata),
        "pages": {key: _scene_to_dict(scene) for key, scene in project.pages.items()},
        "default_text_style": _text_style_to_dict(project.default_text_style),
        "grayscale_adjustment": _grayscale_adjustment_to_dict(project.grayscale_adjustment),
    }


def save_project(project: Project, path: str | Path) -> None:
    Path(path).write_text(json.dumps(project_to_dict(project), indent=2), encoding="utf-8")


def load_project(path: str | Path) -> Project:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    metadata = _metadata_from_dict(data.get("metadata", {}))
    pages = {key: _scene_from_dict(page_data) for key, page_data in data["pages"].items()}
    for key in (PAGE_DISC, PAGE_COVER):
        if key not in pages:
            raise ValueError(f"Project file is missing its '{key}' page")
    default_text_style = _text_style_from_dict(data.get("default_text_style", {}))
    grayscale_adjustment = _grayscale_adjustment_from_dict(data.get("grayscale_adjustment", {}))
    return Project(
        metadata=metadata, pages=pages, default_text_style=default_text_style, grayscale_adjustment=grayscale_adjustment
    )
