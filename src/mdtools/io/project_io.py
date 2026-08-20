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

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsTextItem

from mdtools.canvas.items import (
    BASE_RECT_ROLE,
    LAYER_ROLE,
    get_item_name,
    get_item_scale,
    get_text_glow,
    get_text_shadow,
    set_item_name,
    set_item_scale,
    set_text_glow,
    set_text_shadow,
)
from mdtools.canvas.scene import DesignScene
from mdtools.project import (
    MEDIUM_MD,
    PAGE_DISC,
    GrayscaleAdjustment,
    Project,
    ProjectMetadata,
    TextStyle,
    Track,
)
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
        # Saved rather than recomputed on load, because it is not always
        # boundingRect().center(). jcard_layout shrinks and wraps a text
        # layer *after* creating it and never re-anchors the origin, so a
        # live J-card pivots around a point from before the fitting. Load
        # used to recompute the centre, which is a different point -- and
        # since those panels are rotated a quarter turn, a different pivot
        # puts the text somewhere else entirely. Reproducing what was
        # actually there beats deriving something defensible.
        "origin_x": item.transformOriginPoint().x(),
        "origin_y": item.transformOriginPoint().y(),
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
            # The wrap width, or -1 for "do not wrap" (Qt's own default).
            # Without this a wrapped block comes back as unwrapped single
            # lines -- see item_from_dict, and the J-card note there.
            "text_width": item.textWidth(),
            "shadow": get_text_shadow(item),
            "glow": get_text_glow(item),
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
        # Restored *before* the origin point below, and that ordering is
        # load-bearing: the wrap width is what decides boundingRect(), and
        # the origin is that rect's centre. Setting it afterwards would
        # pivot the item around the centre of the much wider unwrapped
        # block.
        #
        # Missing from files written before this was saved, which is what
        # made a reloaded J-card track list look wrong: jcard_layout wraps
        # it to the panel width, the width was dropped on save, and it came
        # back as long unwrapped lines running off the panel. -1 is Qt's own
        # "no wrapping", so an older project loads exactly as it always did.
        text_width = float(item_data.get("text_width", -1.0))
        if text_width > 0:
            item.setTextWidth(text_width)
        item.setTransformOriginPoint(item.boundingRect().center())
        # Missing from files written before shadow/glow existed -- False for
        # both is what those items already looked like.
        set_text_shadow(item, bool(item_data.get("shadow", False)))
        set_text_glow(item, bool(item_data.get("glow", False)))
    elif kind in ("rect", "ellipse"):
        item = scene.add_rectangle() if kind == "rect" else scene.add_ellipse()
        width, height = item_data["w"], item_data["h"]
        item.setRect(0, 0, width, height)
        # A scaled rectangle/ellipse used to come back scaled *twice*.
        #
        # Unlike text and images, which scale through a transform,
        # set_item_scale() resizes a shape's own rect() and remembers the
        # pre-scale size in BASE_RECT_ROLE the first time it is asked to
        # (see canvas/items.py). "w"/"h" in the file are the rect as it
        # stood, which already includes the scaling -- so a freshly created
        # item, with no base rect cached yet, adopted that scaled size as
        # its base and the set_item_scale() call at the end of this function
        # multiplied it by the factor a second time. A 2x-wide rectangle
        # reloaded 4x wide, and because that call also re-centres the shape,
        # it moved as well.
        #
        # Seeding the base rect with the size *before* scaling makes that
        # call reproduce exactly what was saved. Deliberately derived rather
        # than stored in a new field, so projects written before this fix
        # are repaired on load too -- there is no version of the file that
        # needs a different rule.
        scale_x = item_data.get("scale_x", 1.0) or 1.0
        scale_y = item_data.get("scale_y", 1.0) or 1.0
        item.setData(BASE_RECT_ROLE, QRectF(0, 0, width / scale_x, height / scale_y))
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
    # After the per-type branches, each of which sets a centred origin as a
    # default, and before rotation/scale, both of which pivot on it. Absent
    # from older files, which then keep the recomputed centre they have
    # always loaded with.
    if "origin_x" in item_data:
        item.setTransformOriginPoint(QPointF(item_data["origin_x"], item_data["origin_y"]))
    item.setPos(item_data["x"], item_data["y"])
    item.setRotation(item_data["rotation"])
    set_item_scale(item, item_data.get("scale_x", 1.0), item_data.get("scale_y", 1.0))
    item.setZValue(item_data.get("z", 0.0))
    set_item_name(item, item_data.get("name"))
    return item


def scene_to_dict(scene: DesignScene) -> dict:
    """A page's template plus every print item on it, as one JSON-ready
    dict -- the unit `project_to_dict()`/`load_project()` save/load one
    page as, and also what MainWindow's "Regenerate with Font..." preview
    snapshots a page to before rebuilding it, so a cancelled preview can be
    rebuilt right back via `scene_from_dict()` rather than needing its own,
    separate undo path (apply_template(), which every auto-layout call goes
    through, already resets the undo stack -- there is no QUndoStack entry
    to undo() back to)."""
    items = [d for i in scene.print_items() if (d := item_to_dict(i)) is not None]
    return {"template": dict(scene.template.__dict__), "items": items}


def scene_from_dict(data: dict) -> DesignScene:
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
        "tracks": [
            {"title": t.title, "time_seconds": t.time_seconds, "artist": t.artist} for t in metadata.tracks
        ],
        "cover_art_base64": base64.b64encode(metadata.cover_art).decode("ascii") if metadata.cover_art else None,
    }


def _metadata_from_dict(data: dict) -> ProjectMetadata:
    cover_art_base64 = data.get("cover_art_base64")
    return ProjectMetadata(
        album=data.get("album", ""),
        artist=data.get("artist", ""),
        year=data.get("year"),
        # "artist" defaults to "" for projects saved before compilations
        # were a concept -- they load as ordinary albums, which is what
        # they were.
        tracks=[
            Track(title=t["title"], time_seconds=t.get("time_seconds"), artist=t.get("artist", ""))
            for t in data.get("tracks", [])
        ],
        cover_art=base64.b64decode(cover_art_base64) if cover_art_base64 else None,
    )


def project_to_dict(project: Project) -> dict:
    return {
        "version": PROJECT_VERSION,
        "metadata": _metadata_to_dict(project.metadata),
        "pages": {key: scene_to_dict(scene) for key, scene in project.pages.items()},
        "default_text_style": _text_style_to_dict(project.default_text_style),
        "grayscale_adjustment": _grayscale_adjustment_to_dict(project.grayscale_adjustment),
        "medium": project.medium,
        "tape_total_minutes": project.tape_total_minutes,
    }


def save_project(project: Project, path: str | Path) -> None:
    Path(path).write_text(json.dumps(project_to_dict(project), indent=2), encoding="utf-8")


def load_project(path: str | Path) -> Project:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    metadata = _metadata_from_dict(data.get("metadata", {}))
    pages = {key: scene_from_dict(page_data) for key, page_data in data["pages"].items()}
    # Whatever pages the file holds, in the order it holds them -- not a
    # fixed pair. A file *without* a disc page is still a broken file, but
    # one with a third page is a project from a later version, not an
    # error, and the app can show what it does understand.
    if PAGE_DISC not in pages:
        raise ValueError(f"Project file is missing its '{PAGE_DISC}' page")
    default_text_style = _text_style_from_dict(data.get("default_text_style", {}))
    grayscale_adjustment = _grayscale_adjustment_from_dict(data.get("grayscale_adjustment", {}))
    return Project(
        metadata=metadata,
        pages=pages,
        default_text_style=default_text_style,
        grayscale_adjustment=grayscale_adjustment,
        # A project file written before CD-R support existed has no medium
        # in it and is a MiniDisc project.
        medium=data.get("medium", MEDIUM_MD),
        # A project saved before cassettes existed is not a cassette, so
        # what this says about it does not matter -- the default keeps it
        # a number rather than a None every reader has to guard against.
        tape_total_minutes=float(data.get("tape_total_minutes", 90.0)),
    )
