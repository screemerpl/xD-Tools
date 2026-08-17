from mdtools.app_window import MainWindow
from mdtools.project import PAGE_COVER, Track


def _win_with_tracks(track_count: int) -> MainWindow:
    win = MainWindow(show_startup_dialog=False)
    win._show_page(PAGE_COVER)  # blank canvas -- disc page auto-seeds an arrow+label
    win.project.metadata.tracks = [Track(title=f"Track {i}") for i in range(1, track_count + 1)]
    return win


def test_insert_metadata_columns_creates_one_layer_per_column(qt_app):
    win = _win_with_tracks(6)
    scene = win._current_scene()

    win._insert_metadata_columns(["1. Track 1\n2. Track 2\n3. Track 3", "4. Track 4\n5. Track 5\n6. Track 6"])

    items = scene.print_items()
    assert len(items) == 2
    texts = {i.toPlainText() for i in items}
    assert texts == {"1. Track 1\n2. Track 2\n3. Track 3", "4. Track 4\n5. Track 5\n6. Track 6"}


def test_insert_metadata_columns_places_them_side_by_side_not_stacked(qt_app):
    win = _win_with_tracks(6)
    scene = win._current_scene()

    win._insert_metadata_columns(["col1", "col2"])

    # print_items() is topmost-first (z-order), not insertion order -- sort
    # by x to check relative placement regardless of that ordering.
    items = sorted(scene.print_items(), key=lambda i: i.x())
    left, right = items
    assert left.toPlainText() == "col1"
    assert right.toPlainText() == "col2"
    assert left.y() == right.y()
    assert right.x() > left.x()


def test_insert_metadata_columns_is_undoable_as_a_single_step(qt_app):
    win = _win_with_tracks(6)
    scene = win._current_scene()

    win._insert_metadata_columns(["col1", "col2"])
    assert len(scene.print_items()) == 2

    win.undo_stack.undo()
    assert scene.print_items() == []

    win.undo_stack.redo()
    assert len(scene.print_items()) == 2


def test_insert_metadata_columns_is_a_no_op_with_no_texts(qt_app):
    win = _win_with_tracks(6)
    scene = win._current_scene()

    win._insert_metadata_columns([])

    assert scene.print_items() == []
    assert not win.undo_stack.canUndo()
