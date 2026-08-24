from __future__ import annotations

import contextlib
import copy
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QActionGroup, QColor, QFont, QIcon, QKeySequence, QUndoGroup, QUndoStack
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QToolBar,
)

from mdtools import album_sort, app_settings, cover_filters, gallery, i18n, mixtape_cover, recent_projects, user_paths
from mdtools.auto_layout import (
    build_sticker_label,
    place_cover_on_label,
    place_logo_on_slider,
    recolour_insertion_mark,
)
from mdtools.gallery import save_downloaded_cover
from mdtools.jcard_layout import build_jcard, has_cover_window
from mdtools.metadata_lookup import MetadataLookupError, find_artist_photo, find_cover
from mdtools.canvas.items import get_item_name, set_item_name
from mdtools.canvas.scene import DesignScene, font_family_override
from mdtools.canvas.view import DesignView
from mdtools.clipboard import Clipboard
from mdtools.commands import AddItemCommand, DeleteItemsCommand, PropertyEditCommand, SetPixmapCommand, SwapZCommand
from mdtools.constants import mm_to_px
from mdtools.grayscale import BRIGHTNESS_RANGE, CONTRAST_RANGE
from mdtools.io.png_export import export_png, render_scene_to_image
from mdtools.io.project_io import item_from_dict, item_to_dict, load_project, save_project, scene_from_dict, scene_to_dict
from mdtools.io.svg_export import export_svg
from mdtools.panels.about_dialog import AboutDialog
from mdtools.panels.add_page_dialog import AddPageDialog
from mdtools.panels.asset_gallery_dialog import AssetGalleryDialog
from mdtools.panels.cd_rip_dialog import CdRipDialog
from mdtools.panels.cover_filter_dialog import CoverFilterDialog
from mdtools.panels.erase_dialog import EraseDiscDialog
from mdtools.panels.experimental_settings_dialog import ExperimentalSettingsDialog
from mdtools.audio_folder import album_from_folder
from mdtools.cd_layout import CdLayoutError, build_case_back, build_disc_label, build_front_insert, build_insert
from mdtools import tape
from mdtools.tape_layout import TapeLayoutError, build_side_label
from mdtools.tape_layout import build_jcard as build_tape_jcard
from mdtools.panels.burn_dialog import BurnDialog
from mdtools.panels.folder_record_dialog import FolderRecordDialog
from mdtools.panels import icons
from mdtools.panels.grayscale_export_dialog import GrayscaleExportDialog
from mdtools.panels.layers_panel import LayersPanel
from mdtools.mdrem import disc_title
from mdtools.panels.mdrem_port import resolve_port
from mdtools.panels.metadata_dialog import MetadataDialog
from mdtools.panels.record_dialog import RecordDialog
from mdtools.panels.regenerate_font_dialog import RegenerateFontDialog
from mdtools.panels.tape_record_dialog import TapeRecordDialog
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.panels.print_dialog import PrintDialog
from mdtools.panels.properties_panel import PropertiesPanel
from mdtools.panels.remote_dialog import RemoteDialog
from mdtools.panels.settings_dialog import SettingsDialog
from mdtools.panels.startup_dialog import StartupDialog
from mdtools.panels.telegram_chat_dialog import TelegramChatDialog, pick_album_folder
from mdtools.panels.tool_panel import ToolPanel
from mdtools.project import (
    MEDIUM_CD,
    MEDIUM_MD,
    MEDIUM_TAPE,
    PAGE_BACK,
    PAGE_COVER,
    PAGE_DISC,
    PAGE_ORDER,
    PAGE_SIDE_A,
    PAGE_SIDE_B,
    medium_name,
    medium_pages,
    page_template_kind,
    page_title,
    GrayscaleAdjustment,
    Project,
    ProjectMetadata,
    TextStyle,
    metadata_column_entries,
    metadata_menu_entries,
)
from mdtools.templates.template_dialog import TemplateManagerDialog

# The built-in templates the automatic layout targets: the full-face disc
# label with its slider sticker, and the plain three-panel J-card (the
# window variant would cut a hole through the cover artwork).
FULL_LABEL_TEMPLATE = "Full disc label (with Slider)"
# The same full-face label, minus the slider cutout/sticker -- built by the
# exact same _auto_layout_disc_label(), just with no slider shape for the
# MiniDisc logo to land on (auto_layout.place_logo_on_slider() already
# no-ops gracefully when there's nothing to place it on).
FULL_LABEL_NO_SLIDER_TEMPLATE = "Full disc label"
# The small chamfered "sticker" disc label -- a different shape from the
# full-face templates above, built by _auto_layout_sticker_label() instead
# of _auto_layout_disc_label() (see auto_layout.build_sticker_label()).
# The no-slider twin is the same relationship FULL_LABEL_NO_SLIDER_TEMPLATE
# has to FULL_LABEL_TEMPLATE: same layout, no slider to fill.
STICKER_TEMPLATE = "MiniDisc Disc Label (with Slider)"
STICKER_NO_SLIDER_TEMPLATE = "MiniDisc Disc Label"
JCARD_TEMPLATE = "MiniDisc Cover (J-Card)"
# The same three-panel card with a 40x40mm die-cut window in it. Built by
# the exact same _auto_layout_cover(), which hands build_jcard() a card
# turned end-for-end: the window has to fall on the *artwork* (a die-cut
# sleeve showing the disc through the front of the case) rather than
# through the middle of the track list, so the front and back panels swap
# over and every element on all three rotates the other way. See
# jcard_layout.window_on_track_panel(), which is what actually decides it
# from the template's own geometry.
JCARD_WINDOW_TEMPLATE = "MiniDisc Cover (J-Card + Window)"
# The CD equivalents. The folded insert rather than the flat front, because
# it is the one with somewhere to put a track list.
CD_LABEL_TEMPLATE = "CD Disc Label (Standard Hub)"
CD_INSERT_TEMPLATE = "CD Slim Case Insert (Folded, 2 Panels)"
# The same insert, minus the fold -- built by the exact same
# _auto_layout_cd_insert(), just placing the cover across the whole card
# instead of just its right panel (see cd_layout.build_front_insert()).
CD_INSERT_FRONT_TEMPLATE = "CD Slim Case Insert (Front)"
# The cassette's: one inlay card and the same sticker twice, once per face.
TAPE_JCARD_TEMPLATE = "Cassette J-Card"
TAPE_LABEL_TEMPLATE = "Cassette Shell Label"


# What a saved project's suggested filename ends with, so a shelf of them
# says which machine each one is for at a glance. "MC" is what a cassette
# release has been called on its own spine since the format was sold.
MEDIUM_SUFFIXES = {MEDIUM_MD: "MD", MEDIUM_CD: "CD", MEDIUM_TAPE: "MC"}


class MainWindow(QMainWindow):
    def __init__(self, show_startup_dialog: bool = True):
        super().__init__()
        # Not "Label Designer" any more, and not MiniDisc-only either:
        # designing labels is one of several
        # things this does, alongside recording a disc, titling it over
        # infrared, and standing in for the deck's remote.
        # "xD-Tools": the x stands in for M or C, which is the joke and
        # also, now, the truth -- it does MiniDisc and CD alike.
        self.setWindowTitle(self.tr("xD-Tools - Retro Media Studio"))
        # Set here too, not just on QApplication in main.py -- so the
        # window has the right icon (title bar/taskbar/alt-tab) even when
        # MainWindow is constructed directly (tests, or any future
        # embedding) rather than only via main()'s normal startup path.
        self.setWindowIcon(QIcon(str(gallery.gallery_dir() / "xdtools.png")))
        self.resize(1100, 720)

        self.project: Project | None = None
        self.current_page: str = PAGE_DISC
        self.current_project_path: str | None = None
        self._dirty = False
        # Whether this window has a startup screen to fall back to. Also
        # decides what closing it means (see closeEvent) -- a window built
        # without the startup flow, i.e. every test, must still close when
        # asked rather than putting up a dialog nothing will answer.
        self._has_startup_screen = show_startup_dialog
        # Set only by File > Exit: that means leave, not "go back".
        self._quitting = False
        # Set when the very first StartupDialog is cancelled outright --
        # main() checks this before ever calling show(), so Cancel on first
        # launch actually quits instead of silently creating an untitled
        # project anyway. See _run_startup_flow()'s own docstring.
        self.startup_cancelled = False
        self._connected_scenes: set = set()
        self.clipboard = Clipboard()
        # Which CoverFilterDialog choice a disc/shell label was last built
        # with, this session -- _reused_cover_filter() reads it so
        # "Regenerate with Font..." and a full re-layout don't re-ask a
        # question that's already been answered for this project. Session-
        # only, deliberately not saved into the .mdproj: the filter itself
        # is already baked into whatever image is on the page, this is only
        # ever needed again if something asks to *rebuild* that page.
        self._last_cover_filter_id: str | None = None
        self._reusing_cover_filter = False
        # One QUndoStack per project (undo history for a discarded project's
        # items isn't meaningful); QUndoGroup gives the Edit menu's
        # Undo/Redo actions a stable identity that survives swapping the
        # active stack out from under them (see _reset_undo_stack).
        self.undo_group = QUndoGroup(self)
        self.undo_stack: QUndoStack | None = None

        self.view = DesignView()
        self.setCentralWidget(self.view)

        self._build_page_toolbar()
        self._build_docks()
        self._build_menu()

        # show_startup_dialog=False skips the modal startup prompt (used by
        # tests, which would otherwise hang waiting for it); real usage
        # always wants it so the user can reopen a recent project or pick
        # templates before anything renders.
        if not show_startup_dialog:
            self._new_design(prompt=False)
        elif not self._run_startup_flow() and not self.startup_cancelled:
            # _run_startup_flow() sets startup_cancelled itself, and only
            # for a direct Cancel/close of the StartupDialog itself -- see
            # its own docstring. Any *other* reason it returned False (the
            # template picker was cancelled after choosing "New Project...",
            # or a chosen recent project failed to open) still falls back to
            # a fresh default project exactly as before; only the outer
            # dialog's own Cancel changed meaning.
            self._new_design(prompt=False)

    # -- setup --------------------------------------------------------------

    def _build_page_toolbar(self) -> None:
        toolbar = QToolBar(self.tr("Page"), self)
        toolbar.addWidget(QLabel(self.tr("Editing:")))
        self.page_combo = QComboBox()
        # Filled from whatever pages the open project actually has -- see
        # _refresh_page_combo(). It used to be these two entries, written
        # in here once and relabelled in place; a project with a third page
        # had nowhere to appear.
        self.page_combo.currentIndexChanged.connect(self._on_page_combo_changed)
        toolbar.addWidget(self.page_combo)
        # Add/remove a page -- used to be Templates > "Add Page..."/"Remove
        # This Page"; moved beside the page selector they act on, as a
        # plain +/- pair rather than two menu entries. Both still go
        # through _add_page()/_remove_page(), which already ask their own
        # questions (which page to add, confirming a removal) -- nothing
        # about the underlying behaviour changed, only where it's reached
        # from.
        self.add_page_btn = QPushButton(self.tr("+"))
        self.add_page_btn.setFixedWidth(28)
        self.add_page_btn.setToolTip(self.tr("Add Page..."))
        self.add_page_btn.clicked.connect(self._add_page)
        toolbar.addWidget(self.add_page_btn)
        self.remove_page_btn = QPushButton(self.tr("-"))
        self.remove_page_btn.setFixedWidth(28)
        self.remove_page_btn.setToolTip(self.tr("Remove This Page"))
        self.remove_page_btn.clicked.connect(self._remove_page)
        toolbar.addWidget(self.remove_page_btn)
        toolbar.addWidget(QLabel(self.tr("Template:")))
        self.template_combo = QComboBox()
        # Filled from the registry, filtered to the current page's own
        # template kind and the project's medium -- see
        # _refresh_template_combo(). Usually one entry (there's normally
        # only one built-in per page/medium), plus any custom ones the
        # user has cloned or saved -- see _on_template_combo_changed() for
        # what picking a different one actually does.
        #
        # A page's own kind (disc/cover/label/case_back) changes with the
        # page selector, and their template names vary a lot in length --
        # "CD Disc Label (Standard Hub)" against "CD Jewel Case Back (Tray
        # Card)" against just "sticker". Qt's default AdjustToContentsOnFirstShow
        # locks the combo's width to whatever happened to be in it the
        # first time it was shown, which then truncates every longer name
        # that shows up later -- AdjustToContents keeps it sized to
        # whatever is actually selected right now.
        self.template_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.template_combo.currentIndexChanged.connect(self._on_template_combo_changed)
        toolbar.addWidget(self.template_combo)
        self.regenerate_btn = QPushButton(self.tr("Regenerate"))
        self.regenerate_btn.setToolTip(
            self.tr("Rebuild this page from the project's metadata, with its default fonts and styling")
        )
        self.regenerate_btn.clicked.connect(self._regenerate_current_page)
        toolbar.addWidget(self.regenerate_btn)
        self.regenerate_font_btn = QPushButton(self.tr("Regenerate with Font..."))
        self.regenerate_font_btn.clicked.connect(self._open_regenerate_font_dialog)
        toolbar.addWidget(self.regenerate_font_btn)
        self.addToolBar(toolbar)

        zoom_toolbar = QToolBar(self.tr("Zoom"), self)
        # Icon + text together (not the Tools panel's icon-only style --
        # these actions never had a tooltip-only convention, so dropping
        # the visible label would be a bigger UX change than "add icons").
        zoom_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        zoom_toolbar.addAction(icons.zoom_out_icon(), self.tr("Zoom Out"), self.view.zoom_out)
        self.zoom_label = QLabel("100%")
        zoom_toolbar.addWidget(self.zoom_label)
        zoom_toolbar.addAction(icons.zoom_in_icon(), self.tr("Zoom In"), self.view.zoom_in)
        zoom_toolbar.addAction(icons.zoom_reset_icon(), self.tr("100%"), self.view.zoom_reset)
        zoom_toolbar.addAction(icons.zoom_fit_icon(), self.tr("Fit"), self.view.fit_to_window)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        zoom_toolbar.addSeparator()
        grayscale_action = zoom_toolbar.addAction(icons.grayscale_icon(), self.tr("Grayscale"))
        grayscale_action.setCheckable(True)
        grayscale_action.setToolTip(
            self.tr("Temporarily preview the canvas in grayscale -- view only, click again to restore color")
        )
        grayscale_action.toggled.connect(self._on_grayscale_toggled)

        # Brightness/contrast sliders -- only ever shown while the
        # Grayscale preview above is on (see _on_grayscale_toggled), since
        # they only affect the grayscale preview/export, not the normal
        # color view. Values mirror -- and, on change, are written back
        # into -- self.project.grayscale_adjustment (see
        # _on_grayscale_adjustment_changed/_sync_grayscale_controls), the
        # same setting Export Print PNG (Grayscale)'s pre-export dialog
        # seeds itself from and saves back to.
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(*BRIGHTNESS_RANGE)
        self.brightness_slider.setFixedWidth(90)
        self.brightness_slider.setToolTip(self.tr("Grayscale preview/export brightness"))
        self.brightness_slider.valueChanged.connect(self._on_grayscale_adjustment_changed)

        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(*CONTRAST_RANGE)
        self.contrast_slider.setFixedWidth(90)
        self.contrast_slider.setToolTip(self.tr("Grayscale preview/export contrast"))
        self.contrast_slider.valueChanged.connect(self._on_grayscale_adjustment_changed)

        self._grayscale_controls = (
            QLabel(self.tr("Brightness:")),
            self.brightness_slider,
            QLabel(self.tr("Contrast:")),
            self.contrast_slider,
        )
        # addWidget() wraps each widget in its own QWidgetAction -- hiding
        # just the widget (setVisible(False)) leaves that action itself
        # still "visible" as far as the toolbar's own layout/overflow menu
        # is concerned, in some Qt styles. Hiding the action too, and
        # disabling the widget on top of that, is what actually makes the
        # sliders both invisible AND inert (not just unclickable because
        # they're covered) for the whole time Grayscale preview is off.
        self._grayscale_control_actions = [zoom_toolbar.addWidget(w) for w in self._grayscale_controls]
        for widget, action in zip(self._grayscale_controls, self._grayscale_control_actions):
            widget.setVisible(False)
            widget.setEnabled(False)
            action.setVisible(False)

        self.addToolBar(zoom_toolbar)

    def _build_docks(self) -> None:
        self.tool_panel = ToolPanel()
        self.tool_panel.add_text_requested.connect(self._add_text)
        self.tool_panel.add_rectangle_requested.connect(self._add_rectangle)
        self.tool_panel.add_image_requested.connect(self._add_image)
        self.tool_panel.insert_asset_requested.connect(self._insert_asset)
        self.tool_panel.clip_layers_requested.connect(self._clip_layers)
        self.tool_panel.bake_layers_requested.connect(self._bake_layers)
        self.tool_panel.save_as_template_requested.connect(self._save_as_template)
        self.tool_panel.auto_layout_requested.connect(self._auto_layout_from_metadata)
        self.tool_panel.edit_metadata_requested.connect(self._edit_metadata)
        self.tool_panel.metadata_menu.aboutToShow.connect(self._populate_metadata_menu)
        self.tool_panel.metadata_text_requested.connect(self._insert_metadata_text)
        self.tool_panel.metadata_columns_requested.connect(self._insert_metadata_columns)
        self.tool_dock = QDockWidget(self.tr("Tools"), self)
        self.tool_dock.setWidget(self.tool_panel)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.tool_dock)
        # QMainWindow's dock layout otherwise allocates this dock a chunk
        # of the window's width based on internal heuristics unrelated to
        # its content's actual sizeHint -- left alone, a narrow column of
        # small icon-only buttons ends up with a lot of dead space beside
        # it. Capping the max width at the panel's own sizeHint (rather
        # than a hardcoded pixel constant) keeps this correct if the
        # button/icon size ever changes later; resizeDocks() forces the
        # *initial* width to match immediately, since the max alone only
        # stops it from being wider, not from starting out that way.
        tool_width = self.tool_panel.sizeHint().width()
        self.tool_dock.setMaximumWidth(tool_width)
        self.resizeDocks([self.tool_dock], [tool_width], Qt.Orientation.Horizontal)

        self.properties_panel = PropertiesPanel()
        self.properties_panel.text_style_changed.connect(self._on_default_text_style_changed)
        self.properties_panel.probe_color_requested.connect(self.view.start_color_probe)
        self.view.color_probed.connect(self.properties_panel.apply_probed_color)
        self.properties_dock = QDockWidget(self.tr("Properties"), self)
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.properties_dock)

        self.layers_panel = LayersPanel()
        self.layers_panel.item_selected.connect(self._select_item)
        self.layers_panel.delete_requested.connect(self._delete_item)
        self.layers_panel.move_up_requested.connect(self._move_item_up)
        self.layers_panel.move_down_requested.connect(self._move_item_down)
        self.layers_panel.rename_requested.connect(self._rename_item)
        self.layers_dock = QDockWidget(self.tr("Layers"), self)
        self.layers_dock.setWidget(self.layers_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.layers_dock)

        self.view.items_deleted.connect(self._on_items_deleted)

    def _build_menu(self) -> None:
        # Held on self for the same reason open_recent_menu and
        # _language_actions are: re-fetching a QMenu through the menu bar
        # later hands back a wrapper whose C++ object has been collected.
        self.file_menu = file_menu = self.menuBar().addMenu(self.tr("&File"))
        file_menu.addAction(self.tr("New..."), self._new_design)
        file_menu.addAction(self.tr("Open Project..."), self._open_project)
        self.open_recent_menu = file_menu.addMenu(self.tr("Open Recent"))
        self.open_recent_menu.aboutToShow.connect(self._populate_open_recent_menu)
        file_menu.addAction(self.tr("Save"), self._save_project).setShortcut(QKeySequence.StandardKey.Save)
        file_menu.addAction(self.tr("Save As..."), self._save_project_as).setShortcut(QKeySequence("Ctrl+Shift+S"))
        file_menu.addSeparator()
        file_menu.addAction(self.tr("Import Metadata from Project..."), self._import_metadata)
        file_menu.addSeparator()
        file_menu.addAction(self.tr("Export Cut SVG..."), self._export_svg)
        file_menu.addAction(self.tr("Export Print PNG..."), self._export_png)
        file_menu.addAction(self.tr("Export Print PNG (Grayscale)..."), self._export_png_grayscale)
        file_menu.addSeparator()
        file_menu.addAction(self.tr("Print..."), self._print_project).setShortcut(QKeySequence.StandardKey.Print)
        file_menu.addSeparator()
        # Both ways out, next to each other. The window's close button has
        # gone back to the startup screen since it stopped quitting, but a
        # menu offering only "Exit" hid that entirely -- which is exactly
        # how it was found: from the menu, expecting to come back.
        file_menu.addAction(self.tr("Close Project"), self._close_project).setShortcut(
            QKeySequence.StandardKey.Close
        )
        file_menu.addAction(self.tr("Exit"), self._exit_app)

        edit_menu = self.menuBar().addMenu(self.tr("&Edit"))
        undo_action = self.undo_group.createUndoAction(self, self.tr("&Undo"))
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(undo_action)
        redo_action = self.undo_group.createRedoAction(self, self.tr("&Redo"))
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.tr("Cut"), self._cut_selected).setShortcut(QKeySequence.StandardKey.Cut)
        edit_menu.addAction(self.tr("Copy"), self._copy_selected).setShortcut(QKeySequence.StandardKey.Copy)
        edit_menu.addAction(self.tr("Paste"), self._paste).setShortcut(QKeySequence.StandardKey.Paste)
        # No shortcut here: DesignView's own keyPressEvent already handles
        # Delete/Backspace while the canvas has focus (see canvas/view.py).
        # A window-level shortcut on this action would fire *in addition to*
        # that, deleting twice / pushing two undo entries for one press.
        edit_menu.addAction(self.tr("Delete"), self._delete_selected)

        # Nothing but recording lives here. It was "Project" and held the
        # metadata editor as well, which put the one dialog used while
        # designing a label in the same menu as three that drive a tape
        # deck; the editor is now a Tools panel button, next to the layers
        # it feeds. The two sources -- a CD, and a folder of files -- both
        # end in the same recording. There used to be a separate "Burn
        # Audio CD from ..." action beside the folder entry; that collapsed
        # into this one (see _record_folder_dialog), which dispatches to
        # burning instead of recording on a CD project -- one "Record"
        # entry per source, doing whatever the open project's medium calls
        # for, rather than making the user pick the right one of two.
        #
        # A third entry, "Record to MiniDisc from foobar2000...", used to
        # sit here for whatever was already queued in a separately-running
        # foobar2000 -- retired along with the rest of the foobar2000
        # integration (see RecordDialog's own module docstring): there is
        # no "whatever's queued in some other app" concept once recording
        # decodes and plays its own files.
        recording_menu = self.menuBar().addMenu(self.tr("&Recording"))
        # Hidden rather than disabled without the adapter (on a MiniDisc/
        # cassette project -- a CD project needs no adapter at all, so
        # these stay visible for it regardless): like the other MDRem entry
        # points, there is nothing it could usefully do.
        self.record_cd_action = recording_menu.addAction(
            self.tr("Record CD to MiniDisc..."), self._record_cd
        )
        self.record_folder_action = recording_menu.addAction(
            self.tr("Record Folder to MiniDisc..."), self._record_folder
        )
        recording_menu.addSeparator()
        # Erasing is not recording, but it is what you do to a disc you are
        # about to record over, and it is the same deck and the same
        # adapter -- keeping it here beats a menu of its own for one entry.
        self.erase_disc_action = recording_menu.addAction(
            self.tr("Erase MiniDisc..."), self._erase_disc
        )
        # The software remote used to be reachable only from the startup
        # screen (closing the current project just to press a transport key
        # was the only way to it) -- reported directly. Same "not recording,
        # same deck/adapter" reasoning as Erase just above.
        self.remote_action = recording_menu.addAction(
            self.tr("Remote Control..."), self._open_remote_control
        )
        # _sync_mdrem_actions() is deliberately *not* called here: it also
        # gates two entries in the Experimental menu, which is built
        # further down. It runs once both menus exist.

        # Changing a page's template, and adding/removing a page, both moved
        # to the page toolbar -- the Template dropdown next to the page
        # selector, and the +/- buttons beside it (see _build_page_toolbar).
        templates_menu = self.menuBar().addMenu(self.tr("&Templates"))
        templates_menu.addAction(self.tr("Manage Templates..."), self._manage_templates)

        view_menu = self.menuBar().addMenu(self.tr("&View"))
        view_menu.addAction(self.tr("Zoom In"), self.view.zoom_in).setShortcut(QKeySequence.StandardKey.ZoomIn)
        view_menu.addAction(self.tr("Zoom Out"), self.view.zoom_out).setShortcut(QKeySequence.StandardKey.ZoomOut)
        view_menu.addAction(self.tr("Fit to Window"), self.view.fit_to_window)
        view_menu.addSeparator()
        # toggleViewAction() is a checkable action tied to the dock's own
        # visibility -- it un-checks itself if the user closes or hides the
        # dock (including undocking it and closing the floating window),
        # and checking it again brings the dock right back.
        view_menu.addAction(self.tool_dock.toggleViewAction())
        view_menu.addAction(self.properties_dock.toggleViewAction())
        view_menu.addAction(self.layers_dock.toggleViewAction())

        # Gated by Window > Settings' "Show experimental features" checkbox
        # so nobody sees an in-development feature unless they opted in.
        # See _sync_experimental_menu().
        self.experimental_menu = self.menuBar().addMenu(self.tr("Experi&mental"))
        self.experimental_menu.addAction(
            self.tr("Experimental Settings..."), self._show_experimental_settings
        )
        # Hidden until a Telegram session actually exists -- see
        # _sync_experimental_menu(); there is nothing this could usefully
        # do without one, same "hidden rather than disabled" convention
        # _sync_mdrem_actions() already follows for its own entries.
        self.telegram_chat_action = self.experimental_menu.addAction(
            self.tr("Download Album from Telegram Bot..."), self._open_telegram_bot_chat
        )
        # Neither of these needs a live chat session at all -- both just act
        # on whatever has already accumulated in the one configured
        # download folder (see telegram_chat_dialog.py's own note on why
        # that folder is no longer a fresh one per session). Not gated
        # behind the Telegram-session check telegram_chat_action uses,
        # since sorting/recording what's already on disk needs no bot
        # connection either.
        self.experimental_menu.addAction(
            self.tr("Sort Telegram Downloads into Album Folders..."), self._sort_telegram_downloads
        )
        # Recording and burning collapsed into this one entry -- it
        # dispatches to whichever the open project's medium calls for (see
        # _record_from_telegram_downloads -> _record_folder_dialog), the
        # same "just Record" shape the Recording menu's own entries follow.
        self.telegram_record_action = self.experimental_menu.addAction(
            self.tr("Record from Telegram Downloads..."), self._record_from_telegram_downloads
        )
        self._sync_experimental_menu()
        # Both menus exist now, so the adapter/medium gating can run.
        self._sync_mdrem_actions()

        window_menu = self.menuBar().addMenu(self.tr("&Window"))
        window_menu.addAction(self.tr("Settings..."), self._show_settings)

        help_menu = self.menuBar().addMenu(self.tr("&Help"))
        self._build_language_menu(help_menu)
        help_menu.addAction(self.tr("About xD-Tools..."), self._show_about)

    def _reset_undo_stack(self) -> None:
        """A fresh, empty undo history for the just-created/opened project.
        Old items' undo history isn't meaningful once they belong to a
        discarded project, so we don't try to preserve it across New/Open."""
        old_stack = self.undo_stack
        self.undo_stack = QUndoStack(self)
        # Undo/Redo navigation doesn't only happen through MainWindow's own
        # handlers (each of which already calls _refresh_layers() itself
        # right after pushing) -- the Edit menu's Undo/Redo actions are
        # wired straight to the QUndoGroup and bypass those handlers
        # entirely, so without this the Layers panel kept showing whatever
        # it last displayed right after the original action, not whatever
        # state undo/redo actually left the scene in (e.g. undoing "Bake
        # Layers" restored every original layer in the scene, but the
        # panel kept listing just the one baked pixmap layer).
        self.undo_stack.indexChanged.connect(self._on_undo_index_changed)
        self.undo_group.addStack(self.undo_stack)
        self.undo_group.setActiveStack(self.undo_stack)
        if old_stack is not None:
            self.undo_group.removeStack(old_stack)
        self.view.undo_stack = self.undo_stack
        self.properties_panel.undo_stack = self.undo_stack

    def _on_undo_index_changed(self, index: int) -> None:
        scene = self._current_scene()
        selected = scene.selectedItems() if scene is not None else []
        self._refresh_layers(select=selected[0] if selected else None)
        self._mark_dirty()

    # -- unsaved-changes tracking ---------------------------------------------

    def _mark_dirty(self) -> None:
        """Something about the project changed since it was last saved.

        A plain flag rather than QUndoStack.isClean(): metadata edits,
        template changes and the automatic layouts all alter the project
        without necessarily going through the undo stack, so cleanliness
        there would say "unchanged" about a project that very much has."""
        self._dirty = self.project is not None

    def _mark_saved(self) -> None:
        self._dirty = False

    def _may_discard_changes(self) -> bool:
        """Asks before throwing away unsaved work. True means carry on.

        Returns True immediately when there is nothing to lose, which is
        also what keeps the startup flow (no project yet) from prompting."""
        if self.project is None or not self._dirty:
            return True

        answer = QMessageBox.question(
            self,
            self.tr("Unsaved Changes"),
            self.tr("This project has changes that have not been saved.\n\nSave them before continuing?"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Save:
            return self._save_project()
        return answer == QMessageBox.StandardButton.Discard

    def closeEvent(self, event) -> None:
        """Closing the window means "done with this project", not "done with
        xD-Tools" -- it goes back to the startup screen.

        Quitting outright had one route to it and no way back: shut the
        window to open a different project and the whole app went with it.
        File > Exit still leaves for good, and so does cancelling the
        startup screen, which is where "I actually want out" now lives."""
        if not self._may_discard_changes():
            event.ignore()
            return
        if self._quitting or not self._has_startup_screen:
            super().closeEvent(event)
            return

        # The prompt above has settled the question either way, and the
        # project is about to be replaced -- without this, the startup
        # screen's own load would ask about the same changes a second time.
        self._mark_saved()
        self.hide()
        if self._return_to_startup():
            self.show()
            event.ignore()
            return
        super().closeEvent(event)

    def _return_to_startup(self) -> bool:
        """The startup screen again, after a project is closed. True if a
        project was opened or created and the window should stay.

        Loops rather than asking once: backing out of the template picker
        means "not that one", and quitting the whole app over it would be a
        startling answer to a cancelled dialog."""
        while True:
            dialog = StartupDialog(recent_projects.recent_projects(), self)
            if dialog.exec() != StartupDialog.DialogCode.Accepted:
                return False
            if dialog.result_path is not None:
                if self._open_project_path(dialog.result_path):
                    return True
                continue  # the failure was already reported; offer the list again
            if self._new_design(prompt=True):
                return True

    def _close_project(self) -> None:
        """File > Close Project -- back to the startup screen.

        Deliberately just `close()`, so it is the same code path as the
        window's close button rather than a parallel copy of it: the
        unsaved-changes guard, the startup loop and the re-show all live in
        closeEvent and stay in one place."""
        self.close()

    def _exit_app(self) -> None:
        """File > Exit -- leave, rather than returning to the startup screen.

        The flag is cleared again if the close is refused, or the next click
        on the window's own close button would quietly quit instead."""
        self._quitting = True
        if not self.close():
            self._quitting = False

    # -- page / scene wiring ---------------------------------------------------

    def _current_scene(self) -> DesignScene | None:
        return self.project.pages[self.current_page] if self.project else None

    def _on_page_combo_changed(self, index: int) -> None:
        page = self.page_combo.itemData(index)
        if page is not None:
            self._show_page(page)

    def _show_page(self, page: str) -> None:
        self.current_page = page
        scene = self._current_scene()
        if scene is None:
            return
        self.view.setScene(scene)
        if id(scene) not in self._connected_scenes:
            scene.selectionChanged.connect(self._on_selection_changed)
            self._connected_scenes.add(id(scene))
        self.view.fit_to_window()
        self._refresh_layers()
        self.properties_panel.set_item(None)
        self._warn_if_unverified(scene)
        self._refresh_template_combo()

    def _warn_if_unverified(self, scene: DesignScene) -> None:
        if not scene.template.verified:
            message = self.tr(
                "'{name}' has unverified placeholder dimensions -- measure your physical "
                "media/case and correct it in Templates > Manage Templates before cutting "
                "anything for real."
            ).format(name=scene.template.name)
            self.statusBar().showMessage(message, 0)
        else:
            self.statusBar().clearMessage()

    def _refresh_layers(self, select: object = None) -> None:
        scene = self._current_scene()
        if scene is not None:
            self.layers_panel.refresh(scene.print_items(), select=select)

    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_label.setText(f"{round(zoom * 100)}%")

    def _on_grayscale_toggled(self, enabled: bool) -> None:
        """Grayscale preview is meant to be look-only -- see
        DesignView.set_grayscale_preview, which already clears the canvas
        selection and disables item interaction there. Disabling the Tool
        panel and Layers panel here too closes the remaining ways to edit
        a layer (adding a new one, renaming/deleting/reordering) while
        the preview is active; the Properties panel needs no separate
        call since it already disables itself once the selection clear
        above propagates through _on_selection_changed.

        The brightness/contrast sliders only make sense -- and should only
        be active -- while the preview is actually on, so they're shown
        AND enabled in lockstep with it (both the widget and its wrapping
        toolbar QWidgetAction -- see _build_page_toolbar for why both);
        showing them also re-syncs their values from the current
        project's saved GrayscaleAdjustment (_sync_grayscale_controls),
        in case a different project was opened since they were last
        shown."""
        self.view.set_grayscale_preview(enabled)
        self.tool_panel.setEnabled(not enabled)
        self.layers_panel.setEnabled(not enabled)
        for widget, action in zip(self._grayscale_controls, self._grayscale_control_actions):
            widget.setVisible(enabled)
            widget.setEnabled(enabled)
            action.setVisible(enabled)
        if enabled:
            self._sync_grayscale_controls()

    def _sync_grayscale_controls(self) -> None:
        """Seeds the toolbar's brightness/contrast sliders (and the live
        grayscale preview) from whatever's saved on the current project --
        called whenever a project is created/opened, and again whenever
        the Grayscale toggle is turned on, so the sliders always reflect
        the *current* project's saved adjustment rather than wherever they
        happened to be left from a previously open one."""
        adjustment = self.project.grayscale_adjustment if self.project else GrayscaleAdjustment()
        for slider, value in ((self.brightness_slider, adjustment.brightness), (self.contrast_slider, adjustment.contrast)):
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        self.view.set_grayscale_adjustment(adjustment.brightness, adjustment.contrast)

    def _on_grayscale_adjustment_changed(self) -> None:
        adjustment = GrayscaleAdjustment(brightness=self.brightness_slider.value(), contrast=self.contrast_slider.value())
        if self.project is not None:
            self.project.grayscale_adjustment = adjustment
            self._mark_dirty()
        self.view.set_grayscale_adjustment(adjustment.brightness, adjustment.contrast)

    def _on_selection_changed(self) -> None:
        scene = self._current_scene()
        items = scene.selectedItems() if scene else []
        selected = items[0] if items else None
        self.properties_panel.set_item(selected)
        # keep the Layers list in sync even when the selection changed via
        # a canvas click rather than through the Layers panel itself --
        # otherwise Move Up/Down act on a stale or empty list selection.
        self.layers_panel.select_item(selected)

    def _select_item(self, item) -> None:
        scene = self._current_scene()
        if scene is None:
            return
        scene.clearSelection()
        if item is not None:
            item.setSelected(True)

    # -- actions --------------------------------------------------------------

    def _run_startup_flow(self) -> bool:
        """Shown once, at launch: StartupDialog offers reopening one of
        the last few edited projects, browsing for a different one, or
        starting a brand-new design. Returns True if a project ended up
        loaded/created either way.

        Returns False for two different reasons, only one of which sets
        startup_cancelled: a direct Cancel/close of *this* dialog means the
        same thing it already means everywhere else it appears
        (_return_to_startup()'s own "I actually want out") -- the original
        behaviour instead silently created an untitled project regardless
        of what was clicked, reported directly as making the button
        useless. Choosing "New Project..." and then cancelling the
        template picker, or a chosen recent project failing to open, is a
        different, more local cancellation -- startup_cancelled stays
        False, and __init__ falls back to a fresh default project exactly
        as it always has for those."""
        dialog = StartupDialog(recent_projects.recent_projects(), self)
        if dialog.exec() != StartupDialog.DialogCode.Accepted:
            self.startup_cancelled = True
            return False
        if dialog.result_path is not None:
            return self._open_project_path(dialog.result_path)
        return self._new_design(prompt=True)

    def _new_design(self, prompt: bool = True) -> bool:
        """Returns True if a project was actually created (False if the
        user canceled the dialog, or no templates are available)."""
        if not self._may_discard_changes():
            return False
        if prompt:
            dialog = NewDesignDialog(self)
            if dialog.exec() != NewDesignDialog.DialogCode.Accepted:
                return False
            medium = dialog.selected_medium
            chosen = dict(dialog.selected_templates)
            if not chosen:
                return False
        else:
            from mdtools.templates import registry

            templates = registry.load_templates()
            # The unprompted fallback (a cancelled startup screen, or a
            # first launch with nothing chosen) stays on MiniDisc: it is
            # what this app defaulted to before other media existed, and
            # picking one for the user out of template file order would be
            # arbitrary.
            medium = MEDIUM_MD
            chosen = {}
            for entry in medium_pages(medium):
                available = [
                    t
                    for t in templates[page_template_kind(entry.page)]
                    if getattr(t, "medium", MEDIUM_MD) == medium
                ]
                if available:
                    chosen[entry.page] = available[0]
                elif not entry.optional:
                    return False

        pages = {}
        for entry in medium_pages(medium):
            template = chosen.get(entry.page)
            if template is None:
                continue  # an optional page nobody asked for
            scene = DesignScene(template)
            self._populate_new_scene(scene, template, entry.page)
            pages[entry.page] = scene

        self.current_project_path = None
        self.project = Project(metadata=ProjectMetadata(), pages=pages, medium=medium)
        self._reset_undo_stack()
        self.properties_panel.set_default_text_style(self.project.default_text_style)
        self._sync_grayscale_controls()
        # A new project can be for the other medium than the last one, and
        # both the Recording menu and the page names follow the medium.
        self._sync_mdrem_actions()
        self.current_page = self.project.ordered_pages()[0]
        self._refresh_page_combo()
        self._show_page(self.current_page)
        # Building the pages above ran through the undo stack, which marks
        # the project dirty -- but a project this new has nothing to lose.
        self._mark_saved()
        return True

    def _populate_new_scene(self, scene: DesignScene, template, page: str) -> None:
        """Gives a freshly built scene its starting layers.

        Shared by File > New and by changing a page's template, so the two
        can't drift apart: a template that carries its own saved layers gets
        exactly those, and a disc page that doesn't gets the conventional
        insertion-mark triangle and label. Re-seeding those on a template
        change is deliberate -- they are a starting point the user adjusts
        anyway, so leaving the page bare only means retyping them.
        """
        if template.items:
            for item_data in template.items:
                item_from_dict(scene, item_data)
        elif page_template_kind(page) == "disc":
            scene.seed_disc_defaults()

    def _add_page(self) -> None:
        """Adds one of the pages this project does not have yet.

        Only optional pages can be added, which today means the case back:
        the disc and cover pages are created with the project. The template
        is picked from the family that page takes, so this needs no list of
        its own -- see project.page_template_kind().

        One dialog asks all of it -- which page, which template, and empty
        or built from the metadata. It was two `QInputDialog`s and no third
        question at all; both were reported together (see AddPageDialog's
        own docstring).
        """
        if self.project is None:
            return
        allowed = {entry.page for entry in medium_pages(self.project.medium)}
        missing = [page for page in PAGE_ORDER if page in allowed and page not in self.project.pages]
        if not missing:
            QMessageBox.information(
                self,
                self.tr("Add Page"),
                self.tr("This project already has every page it can have."),
            )
            return

        dialog = AddPageDialog(
            pages=[(page, page_title(page, self.project.medium)) for page in missing],
            templates_for=self._templates_for_page,
            can_generate=self._can_auto_generate_page,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        page = dialog.selected_page
        chosen = dialog.selected_template
        if page is None or chosen is None:
            return

        template = copy.deepcopy(chosen)
        scene = DesignScene(template)
        self._populate_new_scene(scene, template, page)
        self.project.pages[page] = scene
        self._mark_dirty()
        self.current_page = page
        self._refresh_page_combo()
        self._show_page(page)
        if dialog.generate:
            # The page exists and is on screen by now, which is what this
            # needs: every _auto_layout_* method works on a page the
            # project already has, and some of them switch to it and run
            # Clip Layers.
            self._generate_page_from_metadata(page, template)

    def _templates_for_page(self, page: str) -> list:
        """Every template `page` can take, for this project's medium.

        The page's own family decides the list (project.page_template_kind
        -- several pages share "cover"), and the medium filters it, or a CD
        project would be offered a MiniDisc J-card. The same pairing
        _refresh_template_combo() and NewDesignDialog already read, kept in
        one method now that AddPageDialog needs it per page change too.
        """
        from mdtools.templates import registry

        if self.project is None:
            return []
        return [
            template
            for template in registry.load_templates().get(page_template_kind(page), [])
            if getattr(template, "medium", MEDIUM_MD) == self.project.medium
        ]

    def _remove_page(self) -> None:
        """Removes the page on screen, if it is one the project can do
        without.

        The disc and cover pages are what a project *is*; only the optional
        ones can go. Everything on the page goes with it, so this confirms
        first and resets the undo stack afterwards -- the same reasoning
        apply_template() gives for the same problem.
        """
        if self.project is None:
            return
        page = self.current_page
        required = {entry.page for entry in medium_pages(self.project.medium) if not entry.optional}
        if page in required:
            QMessageBox.information(
                self,
                self.tr("Remove Page"),
                self.tr("That page is part of every project of this kind and cannot be removed."),
            )
            return

        answer = QMessageBox.warning(
            self,
            self.tr("Remove Page"),
            self.tr(
                "Remove the {page} page? Everything on it is deleted, and the undo history is reset."
            ).format(page=page_title(page, self.project.medium)),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return

        scene = self.project.pages.pop(page)
        # id() is reused after garbage collection, so a stale entry here
        # could make a future scene skip connecting selectionChanged.
        self._connected_scenes.discard(id(scene))
        self._reset_undo_stack()
        self._mark_dirty()
        self.current_page = self.project.ordered_pages()[0]
        self._refresh_page_combo()
        self._show_page(self.current_page)

    def apply_template(self, page: str, template) -> None:
        """Replaces a page's scene with a fresh one on `template`.

        The page is emptied rather than migrated: item coordinates are
        meaningless across a template of a different size and shape, and the
        user has already confirmed they want it gone. A template that
        carries its own saved layers gets those, exactly as File > New does;
        a disc page deliberately does *not* re-seed the insertion-mark
        triangle, which belongs to starting a design rather than reshaping
        one.

        The undo stack is reset because its commands reference items on the
        scene being discarded -- undoing one afterwards would try to put
        them back into a scene that no longer exists.
        """
        old_scene = self.project.pages.get(page)
        if old_scene is not None:
            # id() is reused after garbage collection, so a stale entry here
            # could make a future scene skip connecting selectionChanged.
            self._connected_scenes.discard(id(old_scene))

        scene = DesignScene(template)
        self._populate_new_scene(scene, template, page)
        self.project.pages[page] = scene
        self._reset_undo_stack()
        self._mark_dirty()
        if page == self.current_page:
            self._show_page(page)

    def _on_default_text_style_changed(self, style: TextStyle) -> None:
        if self.project is not None:
            self.project.default_text_style = style
            self._mark_dirty()

    def _apply_default_text_style(self, item) -> None:
        """New text layers pick up whatever font/color the user last set on
        a text item in this project (see PropertiesPanel.text_style_changed),
        including bold/italic/underline/strikeout/weight -- not just family
        and size."""
        style = self.project.default_text_style if self.project else TextStyle()
        if not style.is_set():
            return
        if style.font_spec:
            font = QFont()
            font.fromString(style.font_spec)
            item.setFont(font)
        if style.color:
            item.setDefaultTextColor(QColor(style.color))
        item.setTransformOriginPoint(item.boundingRect().center())

    def _add_text(self) -> None:
        scene = self._current_scene()
        if scene:
            item = scene.add_text()
            self._apply_default_text_style(item)
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Add Text")))
            self._refresh_layers()

    def _add_rectangle(self) -> None:
        scene = self._current_scene()
        if scene:
            item = scene.add_rectangle()
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Add Rectangle")))
            self._refresh_layers()

    def _delete_item(self, item) -> None:
        scene = self._current_scene()
        if scene is None or item is None:
            return
        self.undo_stack.push(DeleteItemsCommand(scene, [item], self.tr("Delete Layer")))
        self._refresh_layers()
        self.properties_panel.set_item(None)

    def _move_item_up(self, item) -> None:
        scene = self._current_scene()
        if scene is None or item is None:
            return
        neighbor = scene.neighbor_above(item)
        if neighbor is None:
            return
        self.undo_stack.push(SwapZCommand(item, neighbor))
        self._refresh_layers(select=item)

    def _move_item_down(self, item) -> None:
        scene = self._current_scene()
        if scene is None or item is None:
            return
        neighbor = scene.neighbor_below(item)
        if neighbor is None:
            return
        self.undo_stack.push(SwapZCommand(item, neighbor))
        self._refresh_layers(select=item)

    def _rename_item(self, item) -> None:
        scene = self._current_scene()
        if scene is None or item is None:
            return
        before = get_item_name(item)
        name, ok = QInputDialog.getText(self, self.tr("Rename Layer"), self.tr("Layer name:"), text=before or "")
        if not ok:
            return
        after = name.strip() or None
        if after == before:
            return
        set_item_name(item, after)
        self.undo_stack.push(PropertyEditCommand(item, "name", set_item_name, before, after, self.tr("Rename Layer")))
        self._refresh_layers(select=item)

    def _copy_selected(self) -> None:
        scene = self._current_scene()
        if scene is None:
            return
        selected = scene.selectedItems()
        if selected:
            self.clipboard.copy(selected)

    def _cut_selected(self) -> None:
        scene = self._current_scene()
        if scene is None:
            return
        selected = scene.selectedItems()
        if not selected:
            return
        self.clipboard.copy(selected)
        self.undo_stack.push(DeleteItemsCommand(scene, selected, self.tr("Cut")))
        self._refresh_layers()
        self.properties_panel.set_item(None)

    def _paste(self) -> None:
        scene = self._current_scene()
        if scene is None or not self.clipboard.has_content():
            return
        self.undo_stack.beginMacro(self.tr("Paste"))
        pasted_items = self.clipboard.paste_into(scene)
        for item in pasted_items:
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Paste")))
        self.undo_stack.endMacro()
        scene.clearSelection()
        for item in pasted_items:
            item.setSelected(True)
        self._refresh_layers()

    def _delete_selected(self) -> None:
        scene = self._current_scene()
        if scene is None:
            return
        selected = scene.selectedItems()
        if not selected:
            return
        self.undo_stack.push(DeleteItemsCommand(scene, selected, self.tr("Delete Layer")))
        self._refresh_layers()
        self.properties_panel.set_item(None)

    def _on_items_deleted(self) -> None:
        self._refresh_layers()
        self.properties_panel.set_item(None)

    def _populate_metadata_menu(self) -> None:
        entries = metadata_menu_entries(self.project.metadata) if self.project else []
        column_entries = metadata_column_entries(self.project.metadata) if self.project else []
        self.tool_panel.set_metadata_entries(entries, column_entries)

    def _insert_metadata_text(self, text: str) -> None:
        scene = self._current_scene()
        if scene:
            item = scene.add_text(text)
            self._apply_default_text_style(item)
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Insert Metadata Text")))
            self._refresh_layers()

    def _insert_metadata_columns(self, texts: list) -> None:
        """Inserts one text layer per column, placed left-to-right so they
        read as side-by-side columns rather than stacked on top of each
        other (scene.add_text() always centers a fresh item)."""
        scene = self._current_scene()
        if not scene or not texts:
            return
        gap = mm_to_px(5)
        self.undo_stack.beginMacro(self.tr("Insert Metadata Text"))
        base_pos = None
        x_offset = 0.0
        for text in texts:
            item = scene.add_text(text)
            self._apply_default_text_style(item)
            if base_pos is None:
                base_pos = item.pos()
            item.setPos(base_pos.x() + x_offset, base_pos.y())
            x_offset += item.boundingRect().width() + gap
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Insert Metadata Text")))
        self.undo_stack.endMacro()
        self._refresh_layers()

    def _add_image(self) -> None:
        scene = self._current_scene()
        if not scene:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Add Image"), user_paths.image_start_path(), self.tr("Images (*.png *.jpg *.jpeg *.bmp)")
        )
        if not path:
            return
        item = scene.add_image(path)
        if item is not None:
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Add Image")))
        self._refresh_layers()

    def _insert_asset(self) -> None:
        scene = self._current_scene()
        if not scene:
            return
        dialog = AssetGalleryDialog(self)
        if dialog.exec() != AssetGalleryDialog.DialogCode.Accepted or not dialog.selected_path:
            return
        item = scene.add_image(dialog.selected_path)
        if item is not None:
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Insert Asset")))
        self._refresh_layers()

    def _clip_layers(self) -> None:
        scene = self._current_scene()
        if not scene:
            return
        items_to_remove, images_to_reclip, shapes_to_rasterize = scene.plan_clip_layers()
        if not items_to_remove and not images_to_reclip and not shapes_to_rasterize:
            return

        label = self.tr("Clip Layers")
        self.undo_stack.beginMacro(label)
        for item, new_pixmap in images_to_reclip:
            self.undo_stack.push(SetPixmapCommand(item, item.pixmap(), new_pixmap, self.tr("Clip Image")))
        for old_item, new_item in shapes_to_rasterize:
            self.undo_stack.push(AddItemCommand(scene, new_item, label))
            self.undo_stack.push(DeleteItemsCommand(scene, [old_item], label))
        if items_to_remove:
            self.undo_stack.push(DeleteItemsCommand(scene, items_to_remove, label))
        self.undo_stack.endMacro()
        self._refresh_layers()

    def _bake_layers(self) -> None:
        scene = self._current_scene()
        if not scene or not scene.print_items():
            return
        image = render_scene_to_image(scene, dpi=app_settings.bake_dpi())
        old_items, new_item = scene.plan_bake_layers(image)
        if new_item is None:
            return

        label = self.tr("Bake Layers")
        self.undo_stack.beginMacro(label)
        self.undo_stack.push(AddItemCommand(scene, new_item, label))
        self.undo_stack.push(DeleteItemsCommand(scene, old_items, label))
        self.undo_stack.endMacro()
        self._refresh_layers(select=new_item)

    def _import_metadata(self) -> None:
        if self.project is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Import Metadata from Project"),
            user_paths.project_start_path(None),
            self._project_file_filter(),
        )
        if not path:
            return
        try:
            other = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, self.tr("Import Metadata"), self.tr("Could not read project:\n{error}").format(error=exc))
            return
        self.project.metadata = other.metadata
        self.statusBar().showMessage(self.tr("Imported metadata from {path}").format(path=path), 5000)

    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Open Project"), user_paths.project_start_path(None), self._project_file_filter()
        )
        if not path:
            return
        self._open_project_path(path)

    def _open_project_path(self, path: str) -> bool:
        """Loads and switches to the project at `path`, recording it as
        the most-recently-used one. Shared by File > Open Project..., File
        > Open Recent, and the startup dialog's "reopen a recent project"
        list, so all three go through the exact same loading/error-
        handling logic. Returns True on success, False if the file
        couldn't be loaded (a dialog is shown either way)."""
        if not self._may_discard_changes():
            return False
        try:
            project = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, self.tr("Open Project"), self.tr("Could not open project:\n{error}").format(error=exc))
            return False
        self.current_project_path = path
        self.project = project
        self._reset_undo_stack()
        self.properties_panel.set_default_text_style(self.project.default_text_style)
        self._sync_grayscale_controls()
        # An opened project may be for the other medium than the one that
        # was open a moment ago; the menu and the page names follow it.
        self._sync_mdrem_actions()
        self.current_page = self.project.ordered_pages()[0]
        self._refresh_page_combo()
        self._show_page(self.current_page)
        recent_projects.add_recent_project(path)
        self._mark_saved()
        return True

    def _populate_open_recent_menu(self) -> None:
        self.open_recent_menu.clear()
        paths = recent_projects.recent_projects()
        if not paths:
            placeholder = self.open_recent_menu.addAction(self.tr("(No Recent Projects)"))
            placeholder.setEnabled(False)
            return
        for path in paths:
            action = self.open_recent_menu.addAction(Path(path).name)
            action.setToolTip(path)
            action.triggered.connect(lambda checked=False, p=path: self._open_project_path(p))

    def _save_project(self) -> bool:
        """True once the project is actually on disk.

        The return value matters: "save, then close" must not close when the
        user backs out of the Save As dialog."""
        if self.project is None:
            return False
        if self.current_project_path is None:
            return self._save_project_as()
        save_project(self.project, self.current_project_path)
        recent_projects.add_recent_project(self.current_project_path)
        self._mark_saved()
        self.statusBar().showMessage(self.tr("Saved {path}").format(path=self.current_project_path), 5000)
        return True

    def _save_project_as(self) -> bool:
        if self.project is None:
            return False
        # First save proposes "Artist - Album (Year) -CD.mdproj" in the
        # projects folder: disc_title() is the same string the deck is
        # told, so the file and the disc cannot end up named differently,
        # and the medium is appended because the same album is very likely
        # to exist on both -- two files that would otherwise collide on the
        # one name.
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Project As"),
            user_paths.project_start_path(self.current_project_path, self._suggested_project_name()),
            self._project_file_filter(),
        )
        if not path:
            return False
        save_project(self.project, path)
        self.current_project_path = path
        recent_projects.add_recent_project(path)
        self._mark_saved()
        self.statusBar().showMessage(self.tr("Saved {path}").format(path=path), 5000)
        return True

    def _export_svg(self) -> None:
        if self.project is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export Cut SVG"), self._export_start_path(), self.tr("SVG (*.svg)")
        )
        if not path:
            return
        for page in self.project.ordered_pages():
            export_svg(self.project.pages[page], self._paged_export_path(path, page))
        self.statusBar().showMessage(self.tr("Exported cut outline to {path}").format(path=path), 5000)

    def _export_png(self) -> None:
        if self.project is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export Print PNG"), self._export_start_path(), self.tr("PNG (*.png)")
        )
        if not path:
            return
        for page in self.project.ordered_pages():
            export_png(self.project.pages[page], self._paged_export_path(path, page), grayscale=False)
        self.statusBar().showMessage(self.tr("Exported print artwork to {path}").format(path=path), 5000)

    # Every page of the project (disc, cover, and whatever else the medium
    # adds) is exported in one go, since a cut-and-print set is only useful
    # as a whole -- exporting just whichever page happened to be on screen
    # silently left the rest of the set behind. Each page gets its own file,
    # named after the page it is so the set can't be shuffled once saved.
    _EXPORT_PAGE_SUFFIXES = {
        PAGE_DISC: "disc",
        PAGE_COVER: "cover",
        PAGE_BACK: "case-back",
        PAGE_SIDE_A: "label-a",
        PAGE_SIDE_B: "label-b",
    }

    def _paged_export_path(self, path: str, page: str) -> str:
        base = Path(path)
        suffix = self._EXPORT_PAGE_SUFFIXES.get(page, page)
        return str(base.with_name(f"{base.stem}-{suffix}{base.suffix}"))

    def _export_png_grayscale(self) -> None:
        """Unlike the plain color export above, grayscale export first
        shows GrayscaleExportDialog -- a brightness/contrast adjustment
        with its own live preview -- before the usual save-path prompt.
        Whatever the user confirms there is written back onto the current
        project (and mirrored onto the toolbar sliders/live preview) so
        it's remembered for next time, exactly like every other
        project-level setting in this app."""
        scene = self._current_scene()
        if scene is None:
            return
        adjustment = self.project.grayscale_adjustment if self.project else GrayscaleAdjustment()
        dialog = GrayscaleExportDialog(scene, adjustment, self)
        if dialog.exec() != GrayscaleExportDialog.DialogCode.Accepted:
            return
        adjustment = dialog.result_adjustment
        if self.project is not None:
            self.project.grayscale_adjustment = adjustment
        self._sync_grayscale_controls()

        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export Print PNG (Grayscale)"), self._export_start_path(), self.tr("PNG (*.png)")
        )
        if not path:
            return
        for page in self.project.ordered_pages():
            export_png(
                self.project.pages[page],
                self._paged_export_path(path, page),
                grayscale=True,
                brightness=adjustment.brightness,
                contrast=adjustment.contrast,
            )
        self.statusBar().showMessage(self.tr("Exported print artwork to {path}").format(path=path), 5000)

    def _print_project(self) -> None:
        """File > Print... -- lays both the disc and cover designs out on
        one physical page (A4/Letter) the user can drag into position,
        with a grayscale/color choice, then sends the result to a real
        printer. See panels/print_dialog.py."""
        if self.project is None:
            return
        dialog = PrintDialog(self.project, self, self._export_start_path())
        dialog.exec()

    def _suggested_project_name(self) -> str:
        """"Artist - Album (Year) -MD", or -CD.

        Empty when the metadata is empty: user_paths.project_start_path()
        treats that as "suggest no filename at all" rather than offering a
        bare " -MD.mdproj".
        """
        title = disc_title(self.project.metadata)
        if not title:
            return ""
        return f"{title} -{MEDIUM_SUFFIXES.get(self.project.medium, 'MD')}"

    def _project_file_filter(self) -> str:
        # a module-level constant can't use self.tr(), so this is computed
        # per-call instead (cheap, and picks up the active language)
        return self.tr("xD-Tools Project (*.mdproj)")

    def _manage_templates(self) -> None:
        dialog = TemplateManagerDialog(self)
        dialog.exec()

    def _show_settings(self) -> None:
        """Window > Settings... -- global, user-level app settings (DPI
        values), unrelated to any particular project. See
        mdtools.app_settings and panels/settings_dialog.py."""
        dialog = SettingsDialog(self)
        dialog.exec()
        self._sync_mdrem_actions()
        self._sync_experimental_menu()

    def _sync_mdrem_actions(self) -> None:
        """Re-reads two things into the Recording menu: whether there is an
        adapter, and which medium the open project is for.

        Every other MDRem entry point lives on a dialog that is rebuilt each
        time it opens, so it picks the setting up for free. These are
        actions built once at startup, and stayed visible after the adapter
        was switched off -- offering to record an album through hardware the
        user had just said they do not have.

        The medium half was asked for separately: a MiniDisc project has no
        use for "Burn Audio CD", and a CD project none for the deck's remote
        or for erasing an MD. Worth being clear that this *is* a change of
        principle rather than tidying -- erasing, the remote and the three
        record entries all act on whatever disc is physically in the deck,
        which has nothing to do with which label is open (see the erase
        dialog's own notes). It is hidden here anyway, because a menu that
        matches the project in front of you is worth more than that
        independence, which nothing but this menu ever exposed.

        With no project open at all -- only reachable before the startup
        screen has been answered -- nothing is hidden on medium grounds: at
        that point there is no medium to follow.
        """
        adapter = app_settings.mdrem_enabled()
        medium = self.project.medium if self.project is not None else None
        self._refresh_page_combo()
        for_md = medium in (None, MEDIUM_MD)
        for_cd = medium in (None, MEDIUM_CD)

        # Ripping a CD needs no adapter, but this entry does not stop at
        # ripping -- it goes straight on to record what it ripped, which
        # does. Splitting a rip-only entry out of it would be inventing a
        # feature nobody asked for. Same for reading a folder's own tags:
        # on its own it is not a feature anyone asked for.
        # A cassette deck is driven by the person in front of it, so a
        # cassette project needs no adapter for either of these -- the two
        # sources are the same two either way, and only the machine at
        # the end of them changes. Which is why they are one set of entries
        # that rename themselves, not two sets where one is always hidden.
        for_tape = medium == MEDIUM_TAPE
        # "Record CD to..." has no burning twin (there is no "burn a CD
        # from a CD rip" flow), so it keeps the adapter-only rule.
        self.record_cd_action.setText(
            self.tr("Record CD to {medium}...").format(medium=self._recording_target_name())
        )
        self.record_cd_action.setVisible(for_tape or (adapter and for_md))
        # Record Folder... dispatches to burning internally when the open
        # project is a CD one (see _record_folder_dialog) -- collapsing
        # what used to be a separate "Burn Audio CD from ..." action beside
        # it into one entry that always says "Record" and does whatever
        # the medium calls for. Burning needs the drive, not the adapter,
        # so this stays visible for a CD project even with MDRem switched
        # off.
        self.record_folder_action.setText(
            self.tr("Record Folder to {medium}...").format(medium=self._recording_target_name())
        )
        self.record_folder_action.setVisible(for_tape or for_cd or (adapter and for_md))
        # Erasing and the remote are nothing but adapter keypresses, so
        # without one there is not even a partial operation to offer.
        self.erase_disc_action.setVisible(adapter and for_md)
        self.remote_action.setVisible(adapter and for_md)

        # The Experimental menu's hand-off is the same operation reached
        # from a different place, so it follows exactly the same rule --
        # reported as not changing with the medium. "Download Album from
        # Telegram Bot..." and "Sort Telegram Downloads..." are untouched:
        # downloading and tidying files belong to neither medium.
        self.telegram_record_action.setText(
            self.tr("Record from Telegram Downloads to {medium}...").format(
                medium=self._recording_target_name()
            )
        )
        self.telegram_record_action.setVisible(for_tape or for_cd or (adapter and for_md))

    def _recording_target_name(self) -> str:
        """What a recording lands on, for a menu entry to name.

        Deliberately the medium rather than the machine: "Cassette" reads
        the way "MiniDisc" already does, and neither says "deck" -- the
        entry is about what comes out of it."""
        return medium_name(self._recording_medium())

    def _recording_medium(self) -> str:
        """Which medium a recording started now would land on."""
        return self.project.medium if self.project is not None else MEDIUM_MD

    def _refresh_page_combo(self) -> None:
        """Rebuilds the page dropdown from the open project.

        One list, from `Project.ordered_pages()`, named by
        `project.page_title()` -- so a project with a third page needs
        nothing here, and a page's name can follow the medium (a CD's
        second page is a case insert, not a J-card) without this having to
        know which pages exist.

        The current page is kept if the project still has it, and falls
        back to the first one if it does not.
        """
        if self.project is None:
            return
        wanted = self.current_page
        self.page_combo.blockSignals(True)
        self.page_combo.clear()
        for page in self.project.ordered_pages():
            self.page_combo.addItem(page_title(page, self.project.medium), page)
        index = self.page_combo.findData(wanted)
        self.page_combo.setCurrentIndex(index if index >= 0 else 0)
        self.page_combo.blockSignals(False)
        chosen = self.page_combo.currentData()
        if chosen is not None and chosen != self.current_page:
            self._show_page(chosen)

    def _template_choices_for_current_page(self) -> list:
        """Every template that could be picked for the page on screen --
        the current page's own kind (disc/cover/label/case_back), filtered
        to the project's medium so a CD project is never offered a J-card
        by name alone. Shared by the toolbar dropdown's own refresh and by
        what picking an entry in it actually does, so the two can never
        disagree about which templates exist."""
        if self.project is None:
            return []
        from mdtools.templates import registry

        kind = page_template_kind(self.current_page)
        return [
            t
            for t in registry.load_templates()[kind]
            if getattr(t, "medium", MEDIUM_MD) == self.project.medium
        ]

    def _refresh_template_combo(self) -> None:
        """Rebuilds the toolbar's Template dropdown from the page on
        screen -- usually one entry (there's normally only a single
        built-in template per page/medium), plus whatever the user has
        cloned or saved of their own.

        Selecting the current page's own template by *name*, not identity:
        `scene.template` is whatever object was handed to DesignScene when
        the page was built, never the same Python object a fresh
        registry.load_templates() call returns.
        """
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        scene = self._current_scene()
        if scene is None:
            self.template_combo.blockSignals(False)
            return
        templates = self._template_choices_for_current_page()
        current_name = scene.template.name
        for template in templates:
            self.template_combo.addItem(template.name, template.name)
        index = self.template_combo.findData(current_name)
        if index < 0:
            # The page's own template isn't among the current choices at
            # all (e.g. it was since deleted from the registry) -- show
            # what is actually on screen rather than silently jumping to
            # the first entry, which would make picking anything else
            # look like a no-op the first time.
            self.template_combo.addItem(current_name, current_name)
            index = self.template_combo.count() - 1
        self.template_combo.setCurrentIndex(index)
        self.template_combo.blockSignals(False)

    def _auto_layout_template_names_for_page(self, page: str) -> set[str]:
        """Every template name the *content* generator for `page` actually
        knows how to build -- the other half of _auto_layout_method_for_
        page(): that one says what to run, this one says which template(s)
        it can run against. "Generated from Metadata" is only ever offered
        in the Template dropdown when the template being switched to is
        one of these. An empty set means no known algorithm exists yet for
        this page under the current medium.

        Most pages have exactly one -- most _auto_layout_* methods above
        look their own template up by one fixed name rather than accepting
        whatever is currently on the page. Four are exceptions: the
        MiniDisc disc label, where _auto_layout_disc_label() can build
        either the full-face label or its "(with Slider)" twin (see its
        own docstring for why that's safe -- the slider-logo placement
        already no-ops gracefully with nothing to place it on); the small
        chamfered sticker label, the same story one level down --
        _auto_layout_sticker_label() building either
        STICKER_TEMPLATE or STICKER_NO_SLIDER_TEMPLATE; and the CD
        insert, where _auto_layout_cd_insert() can build either the folded
        two-panel insert or the front-only one (see its own docstring --
        the front-only build is just the folded one's right-panel cover
        placement, stretched across the whole unfolded card instead); and
        the MiniDisc J-card, where _auto_layout_cover() can build either
        the plain card or the die-cut window variant (build_jcard() turns
        the card end-for-end for the latter, so the window lands on the
        artwork instead of through the track list).

        The case back has no entry here on purpose -- see
        _can_auto_generate_page(), which checks it structurally instead,
        because build_case_back() itself works from whatever three-panel
        shape is already on the page rather than demanding one template by
        name.
        """
        if self.project is None:
            return set()
        if self.project.medium == MEDIUM_TAPE:
            return {
                PAGE_COVER: {TAPE_JCARD_TEMPLATE},
                PAGE_SIDE_A: {TAPE_LABEL_TEMPLATE},
                PAGE_SIDE_B: {TAPE_LABEL_TEMPLATE},
            }.get(page, set())
        if self.project.medium == MEDIUM_CD:
            return {
                PAGE_DISC: {CD_LABEL_TEMPLATE},
                PAGE_COVER: {CD_INSERT_TEMPLATE, CD_INSERT_FRONT_TEMPLATE},
            }.get(page, set())
        return {
            PAGE_DISC: {
                FULL_LABEL_TEMPLATE,
                FULL_LABEL_NO_SLIDER_TEMPLATE,
                STICKER_TEMPLATE,
                STICKER_NO_SLIDER_TEMPLATE,
            },
            PAGE_COVER: {JCARD_TEMPLATE, JCARD_WINDOW_TEMPLATE},
        }.get(page, set())

    def _can_auto_generate_page(self, page: str, template) -> bool:
        """Whether "Generated from Metadata" is a real option once `page`
        is switched onto `template`.

        Every automatic layout in this file is written against one or more
        specific, hardcoded templates (see
        _auto_layout_template_names_for_page) -- there is no generic "fill
        any shape in" algorithm, so switching to a template nothing here
        knows how to build for would make that button a silent no-op.
        Disabling it is the honest answer until a real generator for that
        template exists.

        The case back is the one page with no fixed target template --
        build_case_back() works from whatever three-panel shape is
        already there (see its own docstring), so the check here is
        structural (two fold lines, i.e. three panels) instead of a name
        match.
        """
        if page == PAGE_BACK:
            return len(getattr(template, "fold_offsets_mm", None) or []) == 2
        return template.name in self._auto_layout_template_names_for_page(page)

    def _on_template_combo_changed(self, index: int) -> None:
        """Picking a different entry in the toolbar's Template dropdown.

        A custom (non-builtin) template is applied outright -- it is
        already the user's own choice, saved via Tools > "Save as
        Template..." or the Template Manager, so there's nothing left to
        ask; the page becomes exactly what that template holds, same as
        File > New does for a template carrying items. A built-in
        template asks first, because it is shared and picking one is
        typically not a one-off -- and offers a choice File > New never
        needed: start the page empty, or, where a generator for this
        exact template exists, build it fresh from the project's own
        metadata.
        """
        if self.project is None or index < 0:
            return
        name = self.template_combo.itemData(index)
        if name is None:
            return
        scene = self._current_scene()
        if scene is not None and name == scene.template.name:
            return  # the refresh landing here again, not a real choice
        template = next((t for t in self._template_choices_for_current_page() if t.name == name), None)
        if template is None:
            self._refresh_template_combo()
            return

        if not template.builtin:
            self.apply_template(self.current_page, template)
            return

        self._offer_template_replacement(template)

    def _offer_template_replacement(self, template) -> None:
        """The question a built-in template asks in the toolbar dropdown:
        start the page empty, or build it fresh from the project's own
        metadata -- see _can_auto_generate_page() for why that second
        option isn't always available."""
        page = self.current_page
        can_generate = self._can_auto_generate_page(page, template)

        box = QMessageBox(self)
        box.setWindowTitle(self.tr("Change Template"))
        box.setText(
            self.tr(
                "Switch this page to \"{name}\"? Everything currently on it is removed, and the "
                "undo history is reset."
            ).format(name=template.name)
        )
        empty_btn = box.addButton(self.tr("Empty Template"), QMessageBox.ButtonRole.AcceptRole)
        generate_btn = box.addButton(self.tr("Generated from Metadata"), QMessageBox.ButtonRole.AcceptRole)
        generate_btn.setEnabled(can_generate)
        if not can_generate:
            generate_btn.setToolTip(
                self.tr(
                    "There is no automatic layout for this template yet -- it can still be used "
                    "as a blank starting point."
                )
            )
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(cancel_btn)
        box.exec()
        clicked = box.clickedButton()

        if clicked is empty_btn:
            self.apply_template(page, template)
            return
        if clicked is generate_btn and can_generate:
            self._generate_page_from_metadata(page, template)
            return
        # Cancel, or the dialog was otherwise dismissed -- the page is
        # untouched, but the dropdown already shows the template that was
        # merely being considered, so it has to be put back.
        self._refresh_template_combo()

    def _generate_page_from_metadata(self, page: str, template) -> None:
        """Switches `page` onto `template` and builds it from the
        project's own metadata -- the "Generated from Metadata" half of
        _offer_template_replacement(), split out because the case back
        needs an explicit template swap first (build_case_back() never
        does one itself, see _can_auto_generate_page()) while every other
        page's own _auto_layout_* method already applies its target
        template internally.

        Shares the same "is there actually anything to build from"
        guards _auto_layout_from_metadata() uses -- there is no point
        clearing the page for a generator that has nothing to draw.
        """
        metadata = self.project.metadata
        if not metadata.album and not metadata.artist:
            QMessageBox.information(
                self,
                self.tr("Change Template"),
                self.tr("Fill in the album and artist in the Tools panel's Metadata... first."),
            )
            self._refresh_template_combo()
            return

        if not metadata.cover_art:
            self._fetch_cover_into_metadata(metadata)
        if not metadata.cover_art:
            QMessageBox.warning(
                self,
                self.tr("Change Template"),
                self.tr(
                    "No cover art could be found for this album, and the layout is built around "
                    "it. Add an image yourself, or fetch one with the Metadata dialog's lookup."
                ),
            )
            self._refresh_template_combo()
            return

        if page == PAGE_BACK:
            self.apply_template(page, template)
        # disc_template_name/cover_template_name: the exact template the
        # user just picked in the dropdown, not whatever happens to be on
        # the page right now (still the *old* one at this point, for every
        # page but the case back) -- only meaningful for the two pages
        # with more than one buildable template, silently ignored
        # everywhere else.
        method = self._auto_layout_method_for_page(
            page, disc_template_name=template.name, cover_template_name=template.name
        )
        if method is None:
            self._refresh_template_combo()
            return
        method(metadata)
        # Belt and suspenders: every _auto_layout_* method above applies
        # its own template internally and that already refreshes this
        # combo via apply_template() -> _show_page(). But some of them can
        # still bail out before doing so (e.g. the cover-background picker
        # being cancelled midway) -- in that case the dropdown's own
        # selection has already moved to the template that was merely
        # being considered, and needs putting back to whatever is actually
        # on the page.
        self._refresh_template_combo()

    def _sync_experimental_menu(self) -> None:
        """Shows/hides the whole Experimental menu per Window > Settings'
        "Show experimental features" checkbox -- same "built once at
        startup, so it needs an explicit re-sync after Settings closes"
        reasoning as _sync_mdrem_actions() above. A QMenu itself has no
        setVisible(); menuAction() is the QAction that actually places it
        on the menu bar, and hiding that is what hides the whole menu.

        The Telegram chat entry gets a second, independent gate on top:
        a local Telegram session file existing at all. Fast and local
        (same optimistic convention ExperimentalSettingsDialog's own status
        label uses -- no network round trip just to build a menu), not a
        promise the session is still valid; TelegramChatDialog's own live
        is_authorized() check is what actually decides that once opened."""
        self.experimental_menu.menuAction().setVisible(app_settings.experimental_features_enabled())
        self.telegram_chat_action.setVisible(app_settings.telegram_session_path().exists())

    def _show_experimental_settings(self) -> None:
        ExperimentalSettingsDialog(self).exec()
        # Signing in happens inside this dialog (its own "Sign in to
        # Telegram..." button) -- without this, the chat entry would stay
        # hidden until the next full app restart even though a session now
        # exists.
        self._sync_experimental_menu()

    def _open_telegram_bot_chat(self) -> None:
        """Experimental > Download Album from Telegram Bot... -- opens a
        generic chat with the bot the user configured, then hands off to
        Record Folder to MiniDisc. See panels/telegram_chat_dialog.py.

        Guards on API ID/Hash/bot username all being set -- all three are
        required before a connection attempt is even meaningful, and this
        is the point where a not-yet-configured user finds out rather than
        watching the dialog fail to connect.

        The bot username and the API credentials are reported separately
        because they fail for unrelated reasons and have different fixes: a
        missing username is something the user simply has not filled in yet,
        while missing credentials mean this build was made without them (see
        app_settings._bundled_telegram_credentials()) and the only way
        forward is registering an app of one's own. Telling someone to "set
        the bot username" when the credentials are what is missing would
        send them to a field that is already correct."""
        if not app_settings.telegram_bot_username():
            QMessageBox.information(
                self,
                self.tr("Download Album from Telegram Bot"),
                self.tr("Set the bot username first, in Experimental > Experimental Settings..."),
            )
            return
        if not (app_settings.telegram_api_id() and app_settings.telegram_api_hash()):
            QMessageBox.information(
                self,
                self.tr("Download Album from Telegram Bot"),
                self.tr(
                    "This build has no Telegram API credentials. Register an app at my.telegram.org and "
                    "add its API ID and API Hash to settings.ini to sign in."
                ),
            )
            return

        dialog = TelegramChatDialog(
            app_settings.telegram_api_id(),
            app_settings.telegram_api_hash(),
            app_settings.telegram_bot_username(),
            Path(app_settings.telegram_download_folder()),
            self,
        )
        dialog.start_connecting()
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.downloaded_folder is not None:
            # One "Record Downloaded Albums..." button now, whatever the
            # project's medium: _record_folder_dialog dispatches to burning
            # itself on a CD project, the same as every other entry point.
            self._record_folder_dialog(Path(dialog.downloaded_folder))

    def _sort_telegram_downloads(self) -> None:
        """Experimental > Sort Telegram Downloads into Album Folders... --
        the same operation TelegramChatDialog's own "Sort into Album
        Folders" button runs, but reachable without opening a chat at all.

        Acts on the one configured download folder directly (created on
        demand, same "created at the moment it's actually needed" rule as
        cdrip.ensure_folder()/user_paths.projects_dir() -- there's nothing
        to sort in a folder that doesn't exist yet, but no reason to fail
        over that either), not a browsed folder: since downloads no longer
        land in a fresh per-session subfolder (see telegram_chat_dialog.py),
        this is the one place everything accumulates, and sort_folder()
        already groups by ALBUM tag alone with no session bookkeeping
        needed."""
        root = Path(app_settings.telegram_download_folder())
        root.mkdir(parents=True, exist_ok=True)
        folders = album_sort.sort_folder(root)
        if not folders:
            # Two genuinely different reasons for "nothing moved", and saying
            # "only one album" for both is what made this confusing to read
            # in the already-sorted case (reported in those terms: "pokazuje
            # ze nie ma nic do sortowania bo dwa juz sa posortowane"). A
            # single unmoved album is still loose at this point, so asking
            # the folder afterwards tells the two apart unambiguously.
            if album_sort.loose_audio_files(root):
                message = self.tr("These tracks all belong to one album -- there is nothing to separate.")
            else:
                message = self.tr("Everything is already sorted into album folders.")
            QMessageBox.information(self, self.tr("Sort into Album Folders"), message)
            return
        QMessageBox.information(
            self,
            self.tr("Sort into Album Folders"),
            self.tr("Sorted into {count} album folders.").format(count=len(folders)),
        )

    def _record_from_telegram_downloads(self) -> None:
        """Experimental > Record from Telegram Downloads... -- records
        whatever has already been downloaded through the Telegram bot chat,
        without opening the bot chat itself.

        Sorts first (silently, same reasoning as
        TelegramChatDialog._on_continue_clicked()'s own auto-sort fix: a
        folder still holding more than one album's worth of files flat
        would otherwise be handed to pick_album_folder() as if it were a
        single album, mixing every downloaded album's tracks into one
        recording), then asks which album only when there's genuinely more
        than one to choose from."""
        folder = self._pick_telegram_album()
        if folder is not None:
            self._record_folder_dialog(folder)

    def _pick_telegram_album(self) -> Path | None:
        """Which downloaded album to act on, sorted first.

        The sort is silent and unconditional, for the reason
        TelegramChatDialog._on_continue_clicked()'s own auto-sort fix
        records: a folder still holding more than one album's worth of
        files flat would otherwise be handed to pick_album_folder() as if
        it were a single album, mixing every downloaded album's tracks
        together. Asking which album only happens when there is genuinely
        more than one.
        """
        root = Path(app_settings.telegram_download_folder())
        root.mkdir(parents=True, exist_ok=True)
        album_sort.sort_folder(root)
        folder, ok = pick_album_folder(self, root)
        return folder if ok else None

    def _save_as_template(self) -> None:
        """Captures the current page's template shape plus every layer on
        it (text/shapes/images, exactly as item_to_dict() would save them
        into a .mdproj) as a new user-defined template of the same kind
        (disc/cover), so File > New can recreate this whole layout later."""
        scene = self._current_scene()
        if scene is None:
            return

        name, ok = QInputDialog.getText(
            self, self.tr("Save as Template"), self.tr("Template name:"), QLineEdit.EchoMode.Normal
        )
        name = name.strip()
        if not ok or not name:
            return

        new_template = copy.deepcopy(scene.template)
        new_template.name = name
        new_template.builtin = False
        new_template.items = [d for i in scene.print_items() if (d := item_to_dict(i)) is not None]

        from mdtools.templates import registry

        # self.current_page is already "disc"/"cover" -- the same keys
        # registry.load_templates() uses.
        templates = registry.load_templates()
        templates[self.current_page].append(new_template)
        registry.save_templates(templates)

        self.statusBar().showMessage(self.tr("Saved template '{name}'").format(name=name), 5000)

    def _build_language_menu(self, help_menu) -> None:
        # Keyed by language code and stored on self (rather than only being
        # reachable by walking the menu bar later) so both real usage and
        # tests can address a specific action directly -- re-fetching a
        # QMenu/QAction via menu-bar introspection some time after
        # construction is a known-flaky pattern in this codebase.
        self._language_actions: dict[str, object] = {}
        language_menu = help_menu.addMenu(self.tr("Language"))
        group = QActionGroup(self)
        group.setExclusive(True)
        current = i18n.current_language()
        for code, name in i18n.AVAILABLE_LANGUAGES.items():
            action = language_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(code == current)
            action.triggered.connect(lambda checked, c=code: self._on_language_selected(c))
            group.addAction(action)
            self._language_actions[code] = action
        help_menu.addSeparator()

    def _on_language_selected(self, code: str) -> None:
        if code == i18n.current_language():
            return
        i18n.set_language(code)
        box = QMessageBox(
            QMessageBox.Icon.Information,
            self.tr("Language Changed"),
            self.tr("Restart xD-Tools for the new language to take full effect."),
            parent=self,
        )
        restart_btn = box.addButton(self.tr("Restart Now"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self.tr("Later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is restart_btn:
            # _restart_app() quits this instance via QApplication.quit(),
            # which never runs closeEvent()/its own unsaved-changes guard --
            # without this check, restarting silently discarded whatever
            # hadn't been saved yet.
            if not self._may_discard_changes():
                return
            self._restart_app()

    @staticmethod
    def _restart_app() -> None:
        """Relaunches xD-Tools as a brand-new process, then quits this one.
        There's no live-retranslation machinery in this codebase (every
        widget sets its text once, from self.tr(...), at construction
        time only -- see i18n/__init__.py's own "restart required" note),
        so this is the low-cost stand-in for that: an explicit button
        right on the message that already tells the user a restart is
        needed, instead of leaving them to close and reopen the app
        themselves.

        QProcess.startDetached(program, arguments)'s `arguments` must NOT
        include the program name itself (unlike the C argv[0] convention)
        -- a frozen (PyInstaller) build's sys.executable IS the program,
        so sys.argv[1:] is correct there, but a plain `python -m
        mdtools.main` launch needs the full sys.argv (argv[0] is the
        script path python.exe itself needs, not a duplicate program
        name) passed to the interpreter as arguments instead."""
        if getattr(sys, "frozen", False):
            QProcess.startDetached(sys.executable, sys.argv[1:])
        else:
            QProcess.startDetached(sys.executable, sys.argv)
        QApplication.instance().quit()

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    def _recording_needs_an_adapter(self) -> bool:
        """Whether this project's recording goes through the MDRem adapter.

        A cassette's does not: xD-Tools presses nothing, it plays the tracks
        and says what to do. So every source below resolves a port only
        when there is a MiniDisc at the end of it."""
        return self.project is None or self.project.medium != MEDIUM_TAPE

    def _resolve_recording_port(self) -> str | None:
        """The port to record through, or None to abandon the flow.

        Returns "" -- a real answer, not a failure -- when no port is
        needed at all, so a caller can tell "nothing to resolve" from "the
        user has no adapter"; both are falsy, which is exactly the bug that
        would follow from checking truthiness instead of `is None`.
        """
        if not self._recording_needs_an_adapter():
            return ""
        if not app_settings.mdrem_enabled():
            return None
        return resolve_port(self)

    def _record_cd(self) -> None:
        """Recording > Record CD to MiniDisc... -- rips the disc to tagged
        FLAC files, then records those files exactly as the entry below
        does.

        The port is resolved before the rip rather than after it: the rip is
        the expensive half, and discovering there is no adapter to record
        through is worth finding out beforehand."""
        port = self._resolve_recording_port()
        if port is None:
            return
        rip = CdRipDialog(self, medium=self._recording_medium())
        if rip.exec() != QDialog.DialogCode.Accepted:
            return
        # The rip's own metadata goes forward. Its titles are the ones it
        # wrote into the files, so they say the same thing the files
        # themselves do -- what it adds is the artwork it found (or the
        # user picked) while identifying the disc, which a tag does not
        # carry.
        self._run_record_dialog(port, rip.result_paths, metadata=rip.result_metadata)

    def _record_folder(self) -> None:
        """Recording > Record Folder to MiniDisc... -- the plain menu entry,
        with nothing already picked to skip browsing for. A thin,
        zero-argument wrapper kept separate from _record_folder_dialog()
        itself: QAction.triggered passes a `checked` bool that Qt's
        signal/slot introspection could otherwise land in
        _record_folder_dialog's own `initial_folder` parameter if that were
        connected directly."""
        self._record_folder_dialog()

    def _record_folder_dialog(self, initial_folder: Path | None = None) -> None:
        """Recording > Record Folder to MiniDisc... -- reads the tags of an
        album that is already on disk, then records those files.

        The same shape as _record_cd, and for the same reasons: the port is
        resolved first (there is no point reading a folder for a recording
        that cannot happen), and the dialog's own result is the hand-off.
        Unlike the CD, its metadata *is* passed on -- see FolderRecordDialog
        for why files nobody rewrote cannot carry an edit by themselves.

        `initial_folder`, when given, skips FolderRecordDialog's own
        interactive browse step by calling its already-public set_folder()
        before showing it -- used by the Telegram bot chat's hand-off,
        where the folder is already known rather than something to ask the
        user to pick. The plain menu entry (initial_folder=None) is
        unaffected -- FolderRecordDialog behaves exactly as before, browse
        step included.

        On a CD project this dispatches straight to burning instead --
        "Record Folder to {medium}..." is one entry now, collapsed from a
        separate "Record" and "Burn" pair, and does whatever the medium
        calls for rather than making the user pick the right one."""
        if self._recording_medium() == MEDIUM_CD:
            self._burn_cd_from_folder(initial_folder)
            return
        port = self._resolve_recording_port()
        if port is None:
            return
        folder = FolderRecordDialog(self, medium=self._recording_medium())
        if initial_folder is not None:
            folder.set_folder(initial_folder)
        if folder.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_record_dialog(port, folder.result_paths, metadata=folder.result_metadata)

    # -- burning a CD-R ---------------------------------------------------

    def _burn_cd_from_folder(self, initial_folder: Path | None = None) -> None:
        """The burning half of "Record Folder to {medium}..." on a CD
        project (see _record_folder_dialog, which this is now reached
        through rather than through a menu entry of its own).

        No adapter, no foobar2000, no playlist: a burn hands the files
        straight to cdrdao, so a folder is all this needs -- which is why
        audio_folder.album_from_folder() reads the FLAC tags itself instead
        of routing through a player the way the recording flows do.

        `initial_folder`, when given (the Telegram hand-off), skips the
        browse step exactly like _record_folder_dialog's own parameter of
        the same name."""
        if initial_folder is not None:
            self._burn_folder(initial_folder)
            return
        # Same starting point as Record Folder to MiniDisc...: back where
        # the last album came from, since the next one is very likely a
        # sibling of it.
        remembered = app_settings.music_folder()
        start = remembered if remembered and Path(remembered).is_dir() else user_paths.music_start_path()
        folder = QFileDialog.getExistingDirectory(self, self.tr("Choose Album Folder"), start)
        if not folder:
            return
        self._burn_folder(Path(folder))

    def _burn_folder(self, folder: Path) -> None:
        """Burns a folder that is already known, with no browse step.

        Split out of _burn_cd_from_folder for the Telegram hand-off, the
        same way _record_folder_dialog was.
        """
        album = album_from_folder(folder)
        if not album.tracks:
            QMessageBox.warning(
                self,
                self.tr("Burn Audio CD"),
                self.tr("There are no audio files in that folder."),
            )
            return
        self._run_burn_dialog(
            [(track.path, track.title, track.artist) for track in album.tracks],
            album=album.album,
            artist=album.artist,
            year=album.year,
        )

    def _run_burn_dialog(self, sources, *, album: str, artist: str, year) -> None:
        """Shows the burn dialog and, if a disc was written, offers what was
        written to the open project.

        Offered rather than applied: unlike the post-recording layout (which
        follows a flow the user has already confirmed several times over),
        this can be reached with any project open, including one that has
        nothing to do with the disc just burned.
        """
        dialog = BurnDialog(sources, album=album, artist=artist, year=year, parent=self)
        if dialog.exec() != BurnDialog.DialogCode.Accepted or dialog.result_metadata is None:
            return
        if self.project is None or self.project.medium != MEDIUM_CD:
            return

        answer = QMessageBox.question(
            self,
            self.tr("Burn Audio CD"),
            self.tr("Put this album's details into the open project, ready to design its label?"),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Ok,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        self.project.metadata = dialog.result_metadata
        self._mark_dirty()

    def _erase_disc(self) -> None:
        """Recording > Erase MiniDisc... -- clears the disc in the deck.

        Deliberately not tied to the open project: it acts on whatever is
        physically in the deck, which has nothing to do with which label is
        being designed. Same backstop as the other MDRem entries, since the
        whole operation is adapter keypresses."""
        if not app_settings.mdrem_enabled():
            return
        port = resolve_port(self)
        if port is None:
            return
        EraseDiscDialog(port, self).exec()

    def _open_remote_control(self) -> None:
        """Recording > Remote Control... -- the same software remote the
        startup screen's own Remote button opens, now reachable without
        having to close whatever project is currently open first.

        Deliberately not tied to the open project, same as Erase MiniDisc
        just above: it drives the deck directly and has nothing to do with
        which label is being designed."""
        port = resolve_port(self)
        if port is None:
            return
        RemoteDialog(port, self).exec()

    def _run_record_dialog(
        self, port: str, paths: list[Path], metadata: ProjectMetadata | None = None
    ) -> None:
        """The recording itself, shared by every entry point -- by the time
        it runs, `paths` (which files, in which order) is the only input,
        whether a CD rip produced them, a folder did, or the Telegram bot
        did.

        Which machine it goes to is the project's business, not the
        source's: a rip is a rip whether it ends up on a MiniDisc or on
        side A of a C90, so the branch belongs here rather than in every
        caller."""
        if self.project is not None and self.project.medium == MEDIUM_TAPE:
            self._run_tape_record_dialog(paths, metadata)
            return
        dialog = RecordDialog(port, paths, self, metadata=metadata)
        dialog.exec()
        # What was just recorded is also what the label should describe, so
        # its metadata (plus whatever cover art was found for it) is
        # adopted by the project rather than left for the user to retype
        # into the Tools panel's Metadata dialog by hand.
        if dialog.result_metadata is not None and self.project is not None:
            self.project.metadata = dialog.result_metadata
            self._mark_dirty()
            self._prompt_post_recording_layout()

    def _run_tape_record_dialog(
        self, paths: list[Path], metadata: ProjectMetadata | None = None
    ) -> None:
        """The cassette's own recording: two sides, and a user who is told
        what to press rather than a deck that is driven.

        No port and no drive, so nothing was resolved on the way in.
        """
        minutes = (
            self.project.tape_total_minutes if self.project is not None else tape.DEFAULT_LENGTH.total_minutes
        )
        dialog = TapeRecordDialog(paths, self, metadata=metadata, total_minutes=minutes)
        dialog.exec()
        if dialog.result_metadata is None or self.project is None:
            return
        self.project.metadata = dialog.result_metadata
        # The tape that was actually used, so the shell labels split where
        # the recording did rather than where a default would have.
        self.project.tape_total_minutes = dialog.total_minutes
        self._mark_dirty()
        self._prompt_post_recording_layout()

    def _prompt_post_recording_layout(self) -> None:
        """After a recording, the project's metadata has already been
        adopted from what was just played -- but the label itself is no
        longer built automatically (explicit user request: this used to
        silently regenerate the disc/cover layout right after recording,
        which could clobber a layout already being worked on). Point at
        the Tools panel's Metadata... editor and the magic wand button
        instead, so building the label from that metadata stays a
        deliberate click rather than something that just happens."""
        QMessageBox.information(
            self,
            self.tr("Recording Finished"),
            self.tr(
                "The album's metadata has been filled in from the recording. Review it in "
                "the Tools panel's Metadata... dialog, then click the magic wand button "
                "there to lay out the label."
            ),
        )

    def _auto_layout_from_metadata(self) -> None:
        """Tools panel: build the disc label from the project's metadata,
        with no recording involved.

        Unlike the post-recording path this one confirms first. There the
        user has just sat through several prompts and watched an album go
        down in real time; here it is a single click on a toolbar button,
        where wiping a page the user had been working on would be a nasty
        surprise."""
        if self.project is None:
            return
        metadata = self.project.metadata
        if not metadata.album and not metadata.artist:
            QMessageBox.information(
                self,
                self.tr("Auto-Layout Disc Label"),
                self.tr("Fill in the album and artist in the Tools panel's Metadata... first."),
            )
            return

        if not metadata.cover_art:
            self._fetch_cover_into_metadata(metadata)
        if not metadata.cover_art:
            QMessageBox.warning(
                self,
                self.tr("Auto-Layout Disc Label"),
                self.tr(
                    "No cover art could be found for this album, and the layout is built around it. Add an "
                    "image yourself, or fetch one with the Metadata dialog's lookup."
                ),
            )
            return

        answer = QMessageBox.warning(
            self,
            self.tr("Auto-Layout"),
            self.tr(
                "This replaces everything on {pages} and resets the undo history.\n\nThe project's "
                "metadata is left alone."
            ).format(pages=self._auto_layout_page_names()),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        self._auto_layout_project(metadata)

    def _auto_layout_page_names(self) -> str:
        """The pages this layout is about to overwrite, by name.

        It used to say "both pages -- the disc label and the J-card"
        regardless: on a CD project that named a MiniDisc part the project
        does not have, and it counted wrong the moment a case back existed.
        Built from the project instead, so it cannot go stale again.
        """
        pages = [page for page in self.project.ordered_pages() if page in self._auto_layout_pages()]
        names = [page_title(page, self.project.medium) for page in pages]
        if len(names) > 1:
            return self.tr("{first} and {last}").format(
                first=", ".join(names[:-1]), last=names[-1]
            )
        return names[0] if names else ""

    def _auto_layout_pages(self) -> set[str]:
        """Which pages the automatic layout writes to.

        The case back is included only when the project has one -- it is
        optional, and the layout leaves it alone otherwise.
        """
        if self.project.medium == MEDIUM_TAPE:
            return {PAGE_COVER, PAGE_SIDE_A, PAGE_SIDE_B}
        pages = {PAGE_DISC, PAGE_COVER}
        if self.project.medium == MEDIUM_CD and PAGE_BACK in self.project.pages:
            pages.add(PAGE_BACK)
        return pages

    def _fetch_cover_into_metadata(self, metadata: ProjectMetadata) -> None:
        """Looks up cover art for metadata that has none yet, filling in a
        missing year while it is at it. Silent on failure -- the caller
        checks whether it worked and says something more useful."""
        # A compilation is not something that can be looked up -- see
        # record_dialog._capture_metadata for why searching anyway is worse
        # than not searching. It gets a cover drawn from its own track list.
        if metadata.is_compilation():
            metadata.cover_art = mixtape_cover.render_cover(metadata)
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            data, chosen = find_cover(metadata.artist, metadata.album, len(metadata.tracks))
        except MetadataLookupError:
            return
        finally:
            QApplication.restoreOverrideCursor()

        if chosen is not None and metadata.year is None:
            metadata.year = chosen.year
        if data is None or chosen is None:
            return
        metadata.cover_art = data
        save_downloaded_cover(chosen.artist_name, chosen.collection_name, data)

    def _export_start_path(self) -> str:
        """Exports land beside the project they came from, or in the
        projects folder if it has never been saved -- the SVG that cuts a
        design and the PNG that prints it are the same job as the .mdproj,
        and the set is only findable at cutting time if they stayed
        together."""
        return user_paths.export_start_path(self.current_project_path)

    def _template_named(self, kind: str, name: str):
        from mdtools.templates import registry

        return next((t for t in registry.load_templates()[kind] if t.name == name), None)

    def _generator_template_name_for_page(self, page: str) -> str | None:
        """The template already on `page`, if an automatic layout can build
        that one -- otherwise None, meaning "leave this page alone".

        This is what stops a whole-project layout (the Tools panel's magic
        wand, and the layout offered after a recording) from imposing its
        own idea of which template each page should have. Both used to call
        each `_auto_layout_*` method with no template name at all, so every
        one of them fell back to its own hardcoded default and *replaced*
        whatever the user had chosen -- a project deliberately set up with
        the small sticker disc label came back with the full-face one,
        every time. Reported directly, for the magic wand and then for the
        post-recording layout, which is one bug: they are the same method.

        Two answers mean "skip":
        - **A custom template.** It is the user's own, may carry its own
          saved layers, and nothing here knows how to build it -- explicit
          instruction ("if custom template is selected autogenerate should
          not generate this page"). Note a *renamed* built-in reads as
          buildable-by-name only if the name still matches, which is the
          same rule the Template dropdown already applies.
        - **A built-in nothing can generate**, which after the J-card
          window variant landed means only a built-in the user has renamed
          through the Template Manager.

        Anything else returns its own name, which the caller passes back as
        both `disc_template_name` and `cover_template_name` -- each is
        consumed only by the page kind that has more than one buildable
        template and ignored otherwise, exactly as
        "Regenerate with Font..." already does it.
        """
        if self.project is None:
            return None
        scene = self.project.pages.get(page)
        template = getattr(scene, "template", None)
        if template is None:
            return None
        if not getattr(template, "builtin", False):
            return None
        if not self._can_auto_generate_page(page, template):
            return None
        return template.name

    def _generate_page_up_to_its_template(self, page: str, metadata: ProjectMetadata) -> bool:
        """Rebuild `page` onto the template it already has, or do nothing.

        Returns whether it built anything, so a caller can tell "skipped
        on purpose" from "built" -- see _generator_template_name_for_page
        for when it skips.
        """
        name = self._generator_template_name_for_page(page)
        if name is None:
            return False
        method = self._auto_layout_method_for_page(page, disc_template_name=name, cover_template_name=name)
        if method is None:
            return False
        method(metadata)
        return True

    def _auto_layout_project(self, metadata: ProjectMetadata) -> None:
        """Turns an album into a first draft of the project's pages: the
        disc label and the J-card, or a CD's ring label, case insert and --
        if there is one -- its case back.

        After a recording this runs without confirming first. That is
        deliberate: the recording flow has already asked for confirmation
        several times over, and an extra "are you sure" at the very end --
        after the user has watched an album go down in real time -- would
        be noise. The Tools panel button, which is a single click out of
        nowhere, does confirm.

        One thing it *does* still ask either way: any disc/shell label this
        touches prompts for a background treatment via
        _choose_cover_background() before it is built -- that is a real
        creative choice with six visibly different outcomes, not a "did you
        mean to do this" the user has already answered by getting this far.
        """
        if self.project is None or not metadata.cover_art:
            return
        if self.project.medium == MEDIUM_TAPE:
            self._auto_layout_tape(metadata)
            return
        # Every page below is built *onto the template it already has*,
        # and skipped when that template is the user's own -- see
        # _generator_template_name_for_page. The page order is unchanged
        # (the disc label goes last on a CD because it switches the page
        # combo and runs Clip Layers).
        if self.project.medium == MEDIUM_CD:
            self._generate_page_up_to_its_template(PAGE_COVER, metadata)
            # Only if the project has one: the case back is optional, and
            # laying out a page that does not exist is not a thing to do
            # quietly or loudly.
            if PAGE_BACK in self.project.pages:
                self._generate_page_up_to_its_template(PAGE_BACK, metadata)
            self._generate_page_up_to_its_template(PAGE_DISC, metadata)
            return
        self._generate_page_up_to_its_template(PAGE_COVER, metadata)
        self._generate_page_up_to_its_template(PAGE_DISC, metadata)

    def _choose_cover_background(self, cover_art: bytes, title: str) -> bytes | None:
        """Shows CoverFilterDialog for `cover_art` and returns the filtered
        PNG bytes the user picked, or None if they closed/cancelled it --
        callers treat None as "skip building this label" rather than
        silently falling back to some default treatment.

        Every disc-shaped or shell-shaped label prints the cover full-bleed
        behind text (unlike a J-card or CD insert's front panel, where the
        cover *is* the point) -- this is the one thing all three of them
        share, so the dialog is offered from exactly the three call sites
        that place a cover this way, not from the cover/J-card/insert
        layouts.

        While `_reused_cover_filter()` is active, this skips the dialog
        entirely and reuses whichever filter was last chosen this session
        (see "Regenerate with Font..." -- rebuilding every page with a new
        font must not re-ask a question about background treatment that has
        already been answered)."""
        if self._reusing_cover_filter:
            filter_id = self._last_cover_filter_id or cover_filters.FILTER_NONE
            return cover_filters.apply_cover_filter(cover_art, filter_id)
        dialog = CoverFilterDialog(cover_art, title, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result_filter_id is None:
            return None
        self._last_cover_filter_id = dialog.result_filter_id
        return cover_filters.apply_cover_filter(cover_art, dialog.result_filter_id)

    @contextlib.contextmanager
    def _reused_cover_filter(self):
        """See _choose_cover_background()'s docstring -- scopes "don't ask,
        reuse the last answer" to exactly the call this wraps."""
        previous = self._reusing_cover_filter
        self._reusing_cover_filter = True
        try:
            yield
        finally:
            self._reusing_cover_filter = previous

    def _auto_layout_disc_label(self, metadata: ProjectMetadata, *, template_name: str | None = None) -> None:
        """The full-face template, the cover across it cropped to the cut
        outline, and the MiniDisc logo on the slider sticker.

        `template_name` defaults to the "(with Slider)" variant -- the
        canonical first draft every "build the whole project" caller wants
        (`_auto_layout_project`, the Tools panel's magic wand, the
        post-recording layout). Passing `FULL_LABEL_NO_SLIDER_TEMPLATE`
        instead builds the exact same way, just without a slider shape for
        the MiniDisc logo to land on: `place_logo_on_slider()` already
        returns None gracefully for a template with no slider (see its own
        docstring), so no logo item is ever added rather than something
        having to notice and remove one afterwards."""
        template = self._template_named("disc", template_name or FULL_LABEL_TEMPLATE)
        if template is None:
            return

        # Asked before anything on the page changes, so cancelling leaves
        # it completely untouched rather than mid-way through a template
        # swap with no cover to show for it.
        background = self._choose_cover_background(metadata.cover_art, self.tr("Disc Label Background"))
        if background is None:
            return

        # Clip Layers works on the *current* page, so the disc page has to be
        # the one on screen before any of this runs.
        self.page_combo.setCurrentIndex(self.page_combo.findData(PAGE_DISC))
        self.apply_template(PAGE_DISC, template)
        scene = self.project.pages[PAGE_DISC]

        # Before the cover goes on, while the only text on the page is the
        # insertion mark the template change just seeded. Not an undo command:
        # those items were not added by one either (apply_template resets the
        # stack and seeds them directly), so there is nothing to undo back to.
        # Sampled from the *filtered* artwork, not the raw cover -- that is
        # what actually ends up behind this text, and a filter that changes
        # how bright the top of the cover reads (or replaces it outright,
        # e.g. halftone) has to be what this decision is based on.
        recolour_insertion_mark(scene, background)

        self.undo_stack.beginMacro(self.tr("Lay Out Disc Label"))
        cover = place_cover_on_label(scene, background)
        if cover is not None:
            # Behind whatever the template change seeded (the insertion-mark
            # triangle and its label), not on top: a full-bleed cover would
            # otherwise bury them where they'd never be noticed, and hidden
            # layers are a worse starting point than ones needing restyling.
            behind = [item for item in scene.print_items() if item is not cover]
            cover.setZValue(min((item.zValue() for item in behind), default=0.0) - 1.0)
            self.undo_stack.push(AddItemCommand(scene, cover, self.tr("Cover Art")))
        logo_path = gallery.gallery_dir() / "mdlogo.png"
        # Only added when there's actually a slider shape to place it on --
        # place_logo_on_slider() already no-ops for a template without one
        # (see its own docstring), but scene.add_image() itself doesn't
        # know that, so calling it unconditionally would leave an
        # unpositioned, un-undo-tracked orphan image sitting on the scene
        # for the no-slider variant.
        if len(scene.cut_shape_rects()) >= 2 and logo_path.exists():
            logo = scene.add_image(str(logo_path))
            if place_logo_on_slider(scene, logo) is not None:
                self.undo_stack.push(AddItemCommand(scene, logo, self.tr("MiniDisc Logo")))
        self.undo_stack.endMacro()

        # The cover is deliberately oversized so it covers the label
        # completely; this is what trims the overhang back to the cut shape.
        self._clip_layers()

    def _auto_layout_sticker_label(self, metadata: ProjectMetadata, *, template_name: str | None = None) -> None:
        """The small chamfered "sticker" disc label: cover art across the
        face, a top band carrying the insertion mark, and a bottom band
        carrying Artist / a rule / Album + the year -- the same
        background/accent/ink palette the J-card's back panel uses, scaled
        down to fit a label a fraction of that panel's size. See
        auto_layout.build_sticker_label() for where the actual layout
        happens; this method is the same shape as _auto_layout_disc_label()
        just above, targeting a different template family.

        `template_name` defaults to the "(with Slider)" variant, matching
        _auto_layout_disc_label()'s own default for the full-face
        templates. Passing `STICKER_NO_SLIDER_TEMPLATE` instead builds the
        exact same way, just without a slider shape for the cover snippet
        or the MiniDisc logo to land on -- build_sticker_label() and
        place_logo_on_slider() both already no-op gracefully for a
        template with no slider.
        """
        template = self._template_named("disc", template_name or STICKER_TEMPLATE)
        if template is None:
            return

        background = self._choose_cover_background(metadata.cover_art, self.tr("Disc Label Background"))
        if background is None:
            return

        # Clip Layers works on the *current* page, so the disc page has to be
        # the one on screen before any of this runs.
        self.page_combo.setCurrentIndex(self.page_combo.findData(PAGE_DISC))
        self.apply_template(PAGE_DISC, template)
        scene = self.project.pages[PAGE_DISC]

        self.undo_stack.beginMacro(self.tr("Lay Out Disc Label"))
        for item in build_sticker_label(scene, metadata, background_art=background):
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Disc Label")))

        logo_path = gallery.gallery_dir() / "mdlogo.png"
        # Same "only when there's actually a slider" guard
        # _auto_layout_disc_label() uses, and for the same reason: calling
        # scene.add_image() unconditionally would leave an unpositioned,
        # un-undo-tracked orphan image on the no-slider variant.
        if len(scene.cut_shape_rects()) >= 2 and logo_path.exists():
            logo = scene.add_image(str(logo_path))
            if place_logo_on_slider(scene, logo) is not None:
                self.undo_stack.push(AddItemCommand(scene, logo, self.tr("MiniDisc Logo")))
        self.undo_stack.endMacro()

        # The cover is deliberately oversized so it covers the label (and
        # the slider) completely; this is what trims the overhang back to
        # each cut shape.
        self._clip_layers()

    def _auto_layout_cover(self, metadata: ProjectMetadata, *, template_name: str | None = None) -> None:
        """The three-panel J-card: cover art turned onto the front, an
        accent band down the spine, and the track list on the back.

        `template_name` defaults to the plain card. Passing
        `JCARD_WINDOW_TEMPLATE` instead builds the die-cut window variant,
        which is the same call throughout -- build_jcard() reads the window
        off the template it was given and turns the whole card end-for-end
        for it, so the hole falls on the artwork rather than through the
        middle of the track list. Nothing here has to know that happened.

        Deliberately *not* run through Clip Layers, unlike the disc label.
        Nothing here overhangs by more than a pen width, and clipping would
        rasterise the panel blocks and the track list -- turning text that
        is still worth editing into a flat image. That holds for the window
        variant too: the window is a hole in the *cut* path, so export and
        the cutter both already take it out of the artwork, with nothing to
        bake into the layer itself."""
        template = self._template_named("cover", template_name or JCARD_TEMPLATE)
        if template is None:
            return

        self.apply_template(PAGE_COVER, template)
        scene = self.project.pages[PAGE_COVER]
        logo_path = gallery.gallery_dir() / "mdlogo.png"

        card = build_jcard(scene, metadata, str(logo_path))
        if not card.items:
            return
        self.undo_stack.beginMacro(self.tr("Lay Out J-Card"))
        for item in card.items:
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("J-Card")))
        self.undo_stack.endMacro()

        if has_cover_window(template):
            self._bake_cover_window(scene)

    def _bake_cover_window(self, scene) -> None:
        """Bake a die-cut window into the cover artwork, and nothing else.

        The artwork spans the window deliberately, and export already takes
        the hole out of it at render time -- but the *layer* still carries
        those pixels, so on screen the window is invisible and the card
        looks exactly like the plain one. Reported directly ("artwork is not
        cropped to the window").

        Deliberately **not** self._clip_layers(), which is the whole-page
        operation: that also rasterises the panel background blocks, whose
        own overhang past the card's rounded corners falls outside the cut
        line and so is never printed anyway (the plain J-card has had that
        same harmless overhang all along). Turning those into pixmaps is
        exactly what the "a J-card is not run through Clip Layers" rule
        exists to prevent. Only pixmap layers are rebuilt here, which on
        this page means the cover image alone -- every text layer and every
        panel block stays editable, and no page switch is needed either,
        since this works on the scene it is handed rather than on whichever
        page happens to be on screen.
        """
        _removed, images, _shapes = scene.plan_clip_layers()
        if not images:
            return
        label = self.tr("Clip Layers")
        self.undo_stack.beginMacro(label)
        for item, new_pixmap in images:
            self.undo_stack.push(SetPixmapCommand(item, item.pixmap(), new_pixmap, self.tr("Clip Image")))
        self.undo_stack.endMacro()
        self._refresh_layers()

    def _auto_layout_cd_disc_label(self, metadata: ProjectMetadata) -> None:
        """The ring: the cover lightened across the whole face, the album's
        details in the bands clear of the hub, and the Digital Audio mark.

        Same shape as _auto_layout_disc_label, including the trip through
        Clip Layers at the end -- the artwork is deliberately oversized so
        it covers the disc, and that is what trims it back to the ring (and
        cuts the spindle hole out of it).
        """
        template = self._template_named("disc", CD_LABEL_TEMPLATE)
        if template is None:
            return

        background = self._choose_cover_background(metadata.cover_art, self.tr("Disc Label Background"))
        if background is None:
            return

        # Clip Layers works on the *current* page.
        self.page_combo.setCurrentIndex(self.page_combo.findData(PAGE_DISC))
        self.apply_template(PAGE_DISC, template)
        scene = self.project.pages[PAGE_DISC]

        logo_path = gallery.gallery_dir() / "cd_digital_audio.png"
        try:
            items = build_disc_label(
                scene,
                metadata,
                str(logo_path) if logo_path.exists() else None,
                background_art=background,
            )
        except CdLayoutError:
            return

        self.undo_stack.beginMacro(self.tr("Lay Out Disc Label"))
        for item in items:
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Disc Label")))
        self.undo_stack.endMacro()

        self._clip_layers()

    def _auto_layout_cd_case_back(self, metadata: ProjectMetadata) -> None:
        """The tray card, if this project has one.

        Unlike the other two halves this does *not* change the page's
        template: the back page only exists because the user added it and
        chose its shape, and replacing that with whichever template this
        method preferred would undo their choice. It lays out whatever is
        already there, and does nothing if that page is not a three-panel
        card.
        """
        scene = self.project.pages.get(PAGE_BACK)
        if scene is None:
            return
        logo_path = gallery.gallery_dir() / "cd_digital_audio.png"
        try:
            items = build_case_back(scene, metadata, str(logo_path) if logo_path.exists() else None)
        except CdLayoutError:
            return

        self.undo_stack.beginMacro(self.tr("Lay Out Case Back"))
        for item in items:
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Case Back")))
        self.undo_stack.endMacro()

    def _auto_layout_cd_insert(self, metadata: ProjectMetadata, *, template_name: str | None = None) -> None:
        """The folded slim-case insert: cover on the right panel always;
        the left panel is the track list, or -- if this project also has a
        case back -- the artist's name, year and photo instead, since the
        track list already lives on the tray card and repeating it here
        would just be the same list twice (see cd_layout.build_insert).

        `template_name` defaults to the folded, two-panel insert -- the
        canonical first draft every "build the whole project" caller wants.
        Passing `CD_INSERT_FRONT_TEMPLATE` instead builds the exact same
        cover placement (cd_layout.build_front_insert(), which reuses
        place_insert_cover() unchanged) across the *whole* card rather than
        just its right panel: there is no fold, so there is nowhere for a
        track list or artist panel to go, and the artist-photo lookup is
        skipped outright rather than fetching a photo with no panel to put
        it on.

        Not run through Clip Layers, for the same reason the J-card is not:
        nothing overhangs, and clipping would rasterise a track list that is
        still worth editing.
        """
        is_front_only = template_name == CD_INSERT_FRONT_TEMPLATE
        template = self._template_named("cover", template_name or CD_INSERT_TEMPLATE)
        if template is None:
            return

        has_case_back = not is_front_only and PAGE_BACK in self.project.pages
        artist_photo = None
        if has_case_back:
            # A network lookup, so the same wait-cursor courtesy
            # _fetch_cover_into_metadata already extends to the album cover
            # lookup -- this one is silent on failure by design (see
            # metadata_lookup.find_artist_photo), so there is nothing to
            # report either way, just a cursor while it runs.
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                artist_photo = find_artist_photo(metadata.artist)
            finally:
                QApplication.restoreOverrideCursor()

        self.apply_template(PAGE_COVER, template)
        scene = self.project.pages[PAGE_COVER]

        try:
            if is_front_only:
                items = build_front_insert(scene, metadata)
            else:
                items = build_insert(scene, metadata, has_case_back=has_case_back, artist_photo=artist_photo)
        except CdLayoutError:
            return

        self.undo_stack.beginMacro(self.tr("Lay Out Case Insert"))
        for item in items:
            self.undo_stack.push(AddItemCommand(scene, item, self.tr("Case Insert")))
        self.undo_stack.endMacro()

    def _tape_plan(self, metadata: ProjectMetadata) -> tape.TapePlan:
        """Where the split falls is `tape.split_sides()`'s answer, not this
        window's -- the same function the recording flow uses to decide when
        to ask the user to turn the tape over. That is the point of sharing
        it: a label that says side B starts at track seven, and a recording
        that turns over after track six, would each be defensible alone and
        wrong together.

        Which tape it is for comes from the project (`tape_total_minutes`),
        set by the recording flow and saved with the file -- so a label laid
        out after recording splits exactly where the recording did, and one
        laid out before it uses the same default the recording dialog will
        open on."""
        return tape.split_sides(metadata.tracks, self.project.tape_total_minutes)

    def _auto_layout_tape(self, metadata: ProjectMetadata) -> None:
        """The inlay card, and a shell label for each side of the tape.

        Each of the three pages is skipped when its own template is not one
        an automatic layout can build -- see
        _generator_template_name_for_page. The two shell labels are handled
        together rather than one call each, so the background-treatment
        question is still asked once for the pair; passing only the sides
        that are actually going to be built also means a project whose
        labels both use a custom template is never asked it at all.
        """
        plan = self._tape_plan(metadata)
        if self._generator_template_name_for_page(PAGE_COVER) is not None:
            self._auto_layout_tape_jcard(metadata, plan)
        sides = tuple(
            page
            for page in (PAGE_SIDE_A, PAGE_SIDE_B)
            if self._generator_template_name_for_page(page) is not None
        )
        if sides:
            self._auto_layout_tape_sides(metadata, plan, pages=sides)

    def _auto_layout_tape_jcard(self, metadata: ProjectMetadata, plan: tape.TapePlan) -> None:
        jcard = self._template_named("cover", TAPE_JCARD_TEMPLATE)
        if jcard is None:
            return
        self.apply_template(PAGE_COVER, jcard)
        scene = self.project.pages[PAGE_COVER]
        try:
            items = build_tape_jcard(scene, metadata, plan=plan)
        except TapeLayoutError:
            items = []
        if items:
            self.undo_stack.beginMacro(self.tr("Lay Out J-Card"))
            for item in items:
                self.undo_stack.push(AddItemCommand(scene, item, self.tr("J-Card")))
            self.undo_stack.endMacro()

    def _auto_layout_tape_sides(
        self, metadata: ProjectMetadata, plan: tape.TapePlan, pages: tuple[str, ...] = (PAGE_SIDE_A, PAGE_SIDE_B)
    ) -> None:
        """A shell label for each side named in `pages` -- both by default,
        or just one (see "Regenerate with Font..."'s preview, which only
        ever wants to touch the single page currently on screen).

        Asked once regardless of how many sides that ends up being, not
        once per side -- both shell labels carry the same photo, just
        cropped by a different hole/band arrangement, so asking twice would
        be the same question asked twice in a row. Cancelling skips the
        shell label(s); anything else this call doesn't touch (the J-card)
        is left alone.
        """
        label = self._template_named("label", TAPE_LABEL_TEMPLATE)
        if label is None:
            return
        background = self._choose_cover_background(metadata.cover_art, self.tr("Shell Label Background"))
        if background is None:
            return
        sides = {PAGE_SIDE_A: plan.sides[0], PAGE_SIDE_B: plan.sides[1]}
        for page in pages:
            if page not in self.project.pages:
                continue
            side = sides[page]
            # Clip Layers works on the *current* page, so the label has to
            # be the one on screen before any of this runs.
            self.page_combo.setCurrentIndex(self.page_combo.findData(page))
            self.apply_template(page, copy.deepcopy(label))
            scene = self.project.pages[page]
            try:
                items = build_side_label(scene, metadata, side, background_art=background)
            except TapeLayoutError:
                continue
            self.undo_stack.beginMacro(self.tr("Lay Out Shell Label"))
            for item in items:
                self.undo_stack.push(AddItemCommand(scene, item, self.tr("Shell Label")))
            self.undo_stack.endMacro()
            # The sleeve is laid on deliberately oversized, and the label
            # has two holes cut in it for the reel hubs -- clipping is what
            # trims the overhang *and* punches those holes through the
            # artwork, so the sticker does not cover the drive.
            self._clip_layers()

    # -- Regenerate with Font... ---------------------------------------------

    def _auto_layout_method_for_page(
        self, page: str, *, disc_template_name: str | None = None, cover_template_name: str | None = None
    ):
        """Which single-page auto-layout call rebuilds `page`, for whichever
        medium the project currently is -- the mapping "Regenerate with
        Font..."'s preview and the Template dropdown's "Generated from
        Metadata" both use to rebuild only the page in question. None means
        this page has no automatic layout of its own (should not happen
        for a page a real project actually has, but a template gone
        missing already makes every one of these a silent no-op, and this
        is no different).

        `disc_template_name`/`cover_template_name` only matter for the
        pages with more than one template a generator can build (see
        _auto_layout_template_names_for_page) -- a MiniDisc disc page (the
        full-face label or the small sticker label, and each of those has
        its own "(with Slider)" twin besides -- see
        _auto_layout_minidisc_disc_label()), a MiniDisc cover page (the
        plain J-card or the die-cut window variant) and a CD cover page
        (the folded two-panel insert or the front-only one). Each says
        which of its page's templates to build, and both are silently
        ignored everywhere else. Left `None`,
        _auto_layout_minidisc_disc_label()/_auto_layout_cover()/
        _auto_layout_cd_insert() each fall back to their own default (the
        "(with Slider)" full-face disc label, the plain J-card, the folded
        insert) on their own, which keeps every *other* caller (the
        full-project layout, the Tools panel's magic wand, the
        post-recording layout -- none of which go through this method at
        all) built exactly as before."""
        metadata = self.project.metadata
        if self.project.medium == MEDIUM_TAPE:
            plan = self._tape_plan(metadata)
            return {
                PAGE_COVER: lambda m: self._auto_layout_tape_jcard(m, plan),
                PAGE_SIDE_A: lambda m: self._auto_layout_tape_sides(m, plan, pages=(PAGE_SIDE_A,)),
                PAGE_SIDE_B: lambda m: self._auto_layout_tape_sides(m, plan, pages=(PAGE_SIDE_B,)),
            }.get(page)
        if self.project.medium == MEDIUM_CD:
            return {
                PAGE_DISC: self._auto_layout_cd_disc_label,
                PAGE_COVER: lambda m: self._auto_layout_cd_insert(m, template_name=cover_template_name),
                PAGE_BACK: self._auto_layout_cd_case_back,
            }.get(page)
        return {
            PAGE_DISC: lambda m: self._auto_layout_minidisc_disc_label(m, template_name=disc_template_name),
            PAGE_COVER: lambda m: self._auto_layout_cover(m, template_name=cover_template_name),
        }.get(page)

    def _auto_layout_minidisc_disc_label(self, metadata: ProjectMetadata, *, template_name: str | None = None) -> None:
        """Routes to whichever of the two MiniDisc disc-label families
        `template_name` actually names: _auto_layout_disc_label() for the
        full-face label (either variant), _auto_layout_sticker_label() for
        the small chamfered sticker (either variant). `None` -- every
        caller except the Template dropdown's "Generated from Metadata"
        and "Regenerate with Font..." -- defaults to the full-face label,
        matching _auto_layout_disc_label()'s own default and so every
        pre-existing caller's behaviour."""
        if template_name in (STICKER_TEMPLATE, STICKER_NO_SLIDER_TEMPLATE):
            self._auto_layout_sticker_label(metadata, template_name=template_name)
        else:
            self._auto_layout_disc_label(metadata, template_name=template_name)

    def _snapshot_page(self, page: str) -> dict:
        return scene_to_dict(self.project.pages[page])

    def _restore_page(self, page: str, snapshot: dict) -> None:
        """Rebuilds `page` from a snapshot taken by _snapshot_page() --
        the undo path for "Regenerate with Font..."'s preview. The real
        regenerate always goes through apply_template(), which resets the
        undo stack entirely (its commands would reference items on a scene
        that's about to be discarded), so there is no QUndoStack entry to
        undo() back to; rebuilding straight from a saved snapshot is the
        same technique a project's own save/load already relies on."""
        old_scene = self.project.pages.get(page)
        if old_scene is not None:
            self._connected_scenes.discard(id(old_scene))
        self.project.pages[page] = scene_from_dict(snapshot)
        self._reset_undo_stack()
        self._mark_dirty()
        if page == self.current_page:
            self._show_page(page)

    def _regeneration_metadata(self, title: str) -> ProjectMetadata | None:
        """The metadata a single-page rebuild needs, or None with the reason
        already on screen.

        Shared by the toolbar's "Regenerate" and "Regenerate with Font..."
        buttons, whose preconditions are identical: an album to build from,
        and cover art, which every one of these layouts is built around.
        """
        metadata = self.project.metadata
        if not metadata.album and not metadata.artist:
            QMessageBox.information(
                self,
                title,
                self.tr("Fill in the album and artist in the Tools panel's Metadata... first."),
            )
            return None
        if not metadata.cover_art:
            self._fetch_cover_into_metadata(metadata)
        if not metadata.cover_art:
            QMessageBox.warning(
                self,
                title,
                self.tr(
                    "No cover art could be found for this album, and the layout is built around it. Add "
                    "an image yourself, or fetch one with the Metadata dialog's lookup."
                ),
            )
            return None
        return metadata

    def _regenerate_current_page(self) -> None:
        """Toolbar > "Regenerate": rebuild the current page from the
        project's metadata with its own default styling.

        The same call "Regenerate with Font..." makes, minus the font
        substitution -- so this is the way back to a page's default look
        after a font has been tried on it, as well as the quickest way to
        rebuild a page that has been edited into a corner. It confirms
        first for the same reason that one does: it clears the page and
        resets the undo history.

        The template is not changed: whatever is on the page is what gets
        rebuilt, which for a custom template means there is nothing to do
        (see _generator_template_name_for_page).
        """
        if self.project is None:
            return
        scene = self._current_scene()
        if scene is None:
            return
        page = self.current_page
        title = self.tr("Regenerate")
        name = self._generator_template_name_for_page(page)
        if name is None:
            QMessageBox.information(
                self,
                title,
                self.tr(
                    "This page's template is not one the automatic layout knows how to build, so there "
                    "is nothing to regenerate. Pick a built-in template for this page first."
                ),
            )
            return
        metadata = self._regeneration_metadata(title)
        if metadata is None:
            return
        answer = QMessageBox.warning(
            self,
            title,
            self.tr("Are you sure? This rebuilds this page from the metadata, and resets the undo history."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        method = self._auto_layout_method_for_page(page, disc_template_name=name, cover_template_name=name)
        if method is None:
            return
        with self._reused_cover_filter():
            method(metadata)
        self._refresh_layers()

    def _open_regenerate_font_dialog(self) -> None:
        """Toolbar > "Regenerate with Font...": preview a different font on
        the current page, then, only if accepted and confirmed, rebuild
        that one page -- and only that page -- with it.

        Preview and the final regenerate are the *same* auto-layout call
        (whichever one _auto_layout_method_for_page() maps the current page
        to) every other automatic layout in this app already goes through
        (font_family_override() substitutes the font those calls' own text
        creation uses; _reused_cover_filter() stops them from re-asking a
        background-treatment question this project has already answered),
        so nothing here can show one thing in the preview and build another
        for real.
        """
        if self.project is None:
            return
        scene = self._current_scene()
        if scene is None:
            return
        page = self.current_page
        metadata = self.project.metadata
        # Captured once, up front: which of the (possibly several)
        # templates a page's generator can build is whatever is already on
        # the page *before* this ran, and both Preview and the final
        # rebuild must keep rebuilding that same one -- e.g. a MiniDisc
        # disc label built without its slider must not silently gain one
        # back just because its font changed. Passed as both kwargs below;
        # each is only consumed by whichever page kind actually has more
        # than one buildable template, and ignored otherwise.
        current_template_name = scene.template.name

        if self._regeneration_metadata(self.tr("Regenerate with Font")) is None:
            return

        dialog = RegenerateFontDialog(self)
        preview_snapshot: dict | None = None

        def _run_preview(family: str) -> None:
            nonlocal preview_snapshot
            method = self._auto_layout_method_for_page(
                page, disc_template_name=current_template_name, cover_template_name=current_template_name
            )
            if method is None:
                return
            if preview_snapshot is None:
                preview_snapshot = self._snapshot_page(page)
            else:
                # Restore the true original first, not the previous
                # preview -- two Previews in a row (font A, then font B)
                # must not compound onto each other.
                self._restore_page(page, preview_snapshot)
            with font_family_override(family), self._reused_cover_filter():
                method(metadata)
            self._refresh_layers()

        dialog.preview_requested.connect(_run_preview)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        chosen_family = dialog.selected_family

        if accepted:
            answer = QMessageBox.warning(
                self,
                self.tr("Regenerate with Font"),
                self.tr(
                    'Are you sure? This regenerates this label using "{family}", and resets the undo '
                    "history."
                ).format(family=chosen_family),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                # Rebuilt fresh rather than just "keeping" whatever Preview
                # left on screen -- Preview may never have run at all (OK
                # pressed with no Preview click first), and rebuilding is
                # cheap and exactly idempotent with what Preview itself
                # already does, so there is no reason to special-case it.
                method = self._auto_layout_method_for_page(
                page, disc_template_name=current_template_name, cover_template_name=current_template_name
            )
                if method is not None:
                    with font_family_override(chosen_family), self._reused_cover_filter():
                        method(metadata)
                    self._refresh_layers()
                return

        # Cancelled outright, or backed out of the confirmation -- put the
        # page back exactly how it looked before Preview was ever clicked.
        if preview_snapshot is not None:
            self._restore_page(page, preview_snapshot)
            self._refresh_layers()

    def _edit_metadata(self) -> None:
        if self.project is None:
            return
        dialog = MetadataDialog(self.project.metadata, self, medium=self.project.medium)
        if dialog.exec() == MetadataDialog.DialogCode.Accepted and dialog.result_metadata is not None:
            self.project.metadata = dialog.result_metadata
            self._mark_dirty()
