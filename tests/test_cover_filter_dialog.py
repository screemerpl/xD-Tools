"""CoverFilterDialog: six clickable, live-rendered previews -- clicking one
both chooses it and closes the dialog.
"""

from __future__ import annotations

import io

from PIL import Image
from PySide6.QtWidgets import QDialog

from mdtools import cover_filters
from mdtools.panels.cover_filter_dialog import CoverFilterDialog


def _cover(colour=(30, 60, 120), size=(120, 120)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, colour).save(out, format="PNG")
    return out.getvalue()


def test_it_shows_one_tile_per_filter_in_order(qt_app):
    dialog = CoverFilterDialog(_cover(), "Disc Label Background")

    grid = dialog.layout().itemAt(1).layout()
    assert grid.count() == len(cover_filters.FILTER_IDS)


def test_no_selection_is_made_until_a_tile_is_clicked(qt_app):
    dialog = CoverFilterDialog(_cover(), "Disc Label Background")

    assert dialog.result_filter_id is None


def test_clicking_a_tile_records_the_choice_and_accepts(qt_app):
    dialog = CoverFilterDialog(_cover(), "Disc Label Background")

    grid = dialog.layout().itemAt(1).layout()
    tile = grid.itemAt(2).widget()  # index 2 -> FILTER_IDS[2], Gaussian Blur
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))

    tile.click()

    assert dialog.result_filter_id == cover_filters.FILTER_IDS[2]
    assert accepted


def test_cancel_leaves_no_selection(qt_app):
    dialog = CoverFilterDialog(_cover(), "Disc Label Background")

    dialog.reject()

    assert dialog.result_filter_id is None


def test_the_window_title_is_whatever_the_caller_passed(qt_app):
    dialog = CoverFilterDialog(_cover(), "Shell Label Background")

    assert dialog.windowTitle() == "Shell Label Background"


def test_every_tile_shows_a_non_empty_preview_icon(qt_app):
    dialog = CoverFilterDialog(_cover(), "Disc Label Background")

    grid = dialog.layout().itemAt(1).layout()
    for index in range(grid.count()):
        tile = grid.itemAt(index).widget()
        assert not tile.icon().isNull()
