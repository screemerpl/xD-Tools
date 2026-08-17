"""QUndoCommand classes for the canvas's undo/redo history.

Scope: add/delete/reorder layers, move/rotate/resize (whether via mouse
drag or the Properties panel), and copy/cut/paste. Project Metadata and
Template Manager edits are deliberately out of scope for undo.
"""

from __future__ import annotations

from PySide6.QtCore import QElapsedTimer
from PySide6.QtGui import QPixmap, QUndoCommand

from mdtools.canvas.items import set_item_scale

# How long a PropertyEditCommand stays eligible to absorb a *later* edit to
# the same (item, field) into itself, rather than that edit starting a new
# undo step -- see PropertyEditCommand's docstring. Long enough to cover a
# real burst (rapid spinbox ticks, a few keystrokes), short enough that
# genuinely separate editing sessions -- come back later, edit the same
# field again -- don't silently get folded into the earlier one.
PROPERTY_EDIT_MERGE_WINDOW_MS = 800


class AddItemCommand(QUndoCommand):
    """redo: (re)insert `item` into `scene`; undo: remove it. `item` is
    expected to already exist (freshly created via one of DesignScene's
    add_*() methods) -- the first redo() is a no-op beyond that."""

    def __init__(self, scene, item, text: str = "Add Layer"):
        super().__init__(text)
        self.scene = scene
        self.item = item

    def redo(self) -> None:
        if self.item.scene() is not self.scene:
            self.scene.addItem(self.item)

    def undo(self) -> None:
        if self.item.scene() is self.scene:
            self.scene.removeItem(self.item)


class DeleteItemsCommand(QUndoCommand):
    """redo: remove `items` from `scene`; undo: re-add them. Each item
    keeps its own z-value even while detached, so restoring stacking order
    on undo needs no extra bookkeeping."""

    def __init__(self, scene, items, text: str = "Delete Layer"):
        super().__init__(text)
        self.scene = scene
        self.items = list(items)

    def redo(self) -> None:
        for item in self.items:
            if item.scene() is self.scene:
                self.scene.removeItem(item)

    def undo(self) -> None:
        for item in self.items:
            if item.scene() is not self.scene:
                self.scene.addItem(item)


class SwapZCommand(QUndoCommand):
    """Move-up/move-down is always a swap of two neighbors' z-values, and a
    swap is its own inverse -- redo and undo do the same thing."""

    def __init__(self, item_a, item_b, text: str = "Reorder Layer"):
        super().__init__(text)
        self.item_a = item_a
        self.item_b = item_b

    def _swap(self) -> None:
        z_a, z_b = self.item_a.zValue(), self.item_b.zValue()
        self.item_a.setZValue(z_b)
        self.item_b.setZValue(z_a)

    def redo(self) -> None:
        self._swap()

    def undo(self) -> None:
        self._swap()


class TransformCommand(QUndoCommand):
    """Undoable rotate/scale for a single item -- used for DesignView's
    corner/edge/rotate-handle mouse drags, committed once per completed
    drag gesture (see DesignView._commit_drag_command)."""

    def __init__(self, item, before: dict, after: dict, text: str = "Transform"):
        super().__init__(text)
        self.item = item
        self.before = before
        self.after = after

    def _apply(self, snapshot: dict) -> None:
        self.item.setRotation(snapshot["rotation"])
        set_item_scale(self.item, *snapshot["scale"])

    def redo(self) -> None:
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)


class MoveItemsCommand(QUndoCommand):
    """Undoable position change for one or more items -- used for native
    click-and-drag moves (QGraphicsItem's own ItemIsMovable dragging) and
    for arrow-key nudging (DesignView._nudge_selected). Consecutive moves of
    the exact same set of items merge into one undo step, so holding an
    arrow key down (or a burst of nudges) undoes back to the position from
    before that whole gesture, not one tick at a time.

    `mergeable` marks whether *this* command, when pushed, represents a
    continuation of whatever's already on top of the stack -- Qt's merge
    check only looks at id()/mergeWith(), with no idea of "was this really
    the same continuous gesture as the last one," so that has to be tracked
    explicitly. Only the *incoming* command's flag matters (mergeWith()
    checks `other.mergeable`, never `self.mergeable`) -- the existing
    top-of-stack entry must always stay a valid merge target regardless of
    how it itself was created, or a hold's first tap (necessarily
    mergeable=False, since it must not merge into whatever unrelated
    gesture came before it) would then refuse every later repeat of that
    same hold too.

    A completed mouse drag-and-release always pushes exactly once (there's
    nothing to coalesce within a single drag), so
    `_commit_native_move_command` constructs its command with
    `mergeable=False`: without that, two entirely separate drags of the
    same item -- picked up, dropped, picked up again later, dropped again
    -- would silently merge into ONE undo step (since nothing else happens
    to sit between them on the stack), making a single Ctrl+Z undo *both*
    drags at once and making the second drag look completely unable to be
    undone on its own. Arrow-key nudging passes `mergeable` based on
    `event.isAutoRepeat()` (see `_nudge_selected`) for the same reason: a
    fresh, isolated tap shouldn't silently absorb into whatever nudge
    sequence happened to run before it -- only a genuine OS auto-repeat of
    the same held key should extend the existing entry."""

    _ID = 0x2222E

    def __init__(self, positions_before: dict, positions_after: dict, text: str = "Move", mergeable: bool = True):
        super().__init__(text)
        self.before = positions_before  # {item: (x, y)}
        self.after = positions_after
        self.mergeable = mergeable

    @staticmethod
    def _apply(snapshot: dict) -> None:
        for item, (x, y) in snapshot.items():
            item.setPos(x, y)

    def id(self) -> int:
        return self._ID

    def mergeWith(self, other) -> bool:
        if not isinstance(other, MoveItemsCommand) or not other.mergeable:
            return False
        if set(self.after) != set(other.before):
            return False
        self.after = other.after
        return True

    def redo(self) -> None:
        self._apply(self.after)

    def undo(self) -> None:
        self._apply(self.before)


class SetPixmapCommand(QUndoCommand):
    """Undoable pixmap swap for a QGraphicsPixmapItem -- used by Tools >
    "Clip Layers" to replace an image layer's pixmap with a version
    clipped (made transparent outside the template's printable area)."""

    def __init__(self, item, before: QPixmap, after: QPixmap, text: str = "Clip Image"):
        super().__init__(text)
        self.item = item
        self.before = before
        self.after = after

    def redo(self) -> None:
        self.item.setPixmap(self.after)

    def undo(self) -> None:
        self.item.setPixmap(self.before)


class PropertyEditCommand(QUndoCommand):
    """Generic 'apply an (item, field) snapshot via a callback' command,
    used by the Properties panel for position/rotation/text/font/color
    edits. Consecutive edits to the same field on the same item (every
    tick of a spinbox, a burst of typing) merge into a single undo step,
    so undo jumps straight back to the value before that editing session
    started rather than one tick at a time -- but only *within*
    PROPERTY_EDIT_MERGE_WINDOW_MS of the previous one. Without that time
    cutoff, editing a field, doing something else entirely unrelated that
    never touches the undo stack, then coming back and editing that same
    field again later would still merge into the *original* edit (nothing
    else was pushed in between to break the chain), making the second,
    clearly separate edit impossible to undo on its own -- the same failure
    mode as MoveItemsCommand's `mergeable` flag guards against, just via a
    time window here instead of an explicit gesture-continuation flag,
    since spinbox ticks/typing have no equivalent "isAutoRepeat" signal to
    key off of.

    The callback is expected to be idempotent and side-effect-free beyond
    mutating `item` -- it's called directly by the panel for live visual
    feedback *and* by redo()/undo() when actual undo/redo navigation
    happens (Qt does not call redo() on a command that got merged away).
    """

    _ID = 0x7E57

    def __init__(self, item, field: str, apply_fn, before, after, text: str = "Edit Property"):
        super().__init__(text)
        self.item = item
        self.field = field
        self._apply_fn = apply_fn
        self.before = before
        self.after = after
        self._timer = QElapsedTimer()
        self._timer.start()

    def id(self) -> int:
        return self._ID

    def mergeWith(self, other) -> bool:
        if not isinstance(other, PropertyEditCommand):
            return False
        if other.item is not self.item or other.field != self.field:
            return False
        if self._timer.elapsed() > PROPERTY_EDIT_MERGE_WINDOW_MS:
            return False
        self.after = other.after
        self._timer.start()  # restart -- the merge window slides with each new edit in the burst
        return True

    def redo(self) -> None:
        self._apply_fn(self.item, self.after)

    def undo(self) -> None:
        self._apply_fn(self.item, self.before)
