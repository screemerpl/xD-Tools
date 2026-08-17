from __future__ import annotations

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
    QSlider,
    QToolBar,
)

from mdtools import app_settings, gallery, i18n, mixtape_cover, recent_projects, user_paths
from mdtools.auto_layout import place_cover_on_label, place_logo_on_slider, recolour_insertion_mark
from mdtools.gallery import save_downloaded_cover
from mdtools.jcard_layout import build_jcard
from mdtools.metadata_lookup import MetadataLookupError, find_cover
from mdtools.canvas.items import get_item_name, set_item_name
from mdtools.canvas.scene import DesignScene
from mdtools.canvas.view import DesignView
from mdtools.clipboard import Clipboard
from mdtools.commands import AddItemCommand, DeleteItemsCommand, PropertyEditCommand, SetPixmapCommand, SwapZCommand
from mdtools.constants import mm_to_px
from mdtools.grayscale import BRIGHTNESS_RANGE, CONTRAST_RANGE
from mdtools.io.png_export import export_png, render_scene_to_image
from mdtools.io.project_io import item_from_dict, item_to_dict, load_project, save_project
from mdtools.io.svg_export import export_svg
from mdtools.panels.about_dialog import AboutDialog
from mdtools.panels.asset_gallery_dialog import AssetGalleryDialog
from mdtools.panels.cd_rip_dialog import CdRipDialog
from mdtools.panels.erase_dialog import EraseDiscDialog
from mdtools.panels.folder_record_dialog import FolderRecordDialog
from mdtools.panels import icons
from mdtools.panels.grayscale_export_dialog import GrayscaleExportDialog
from mdtools.panels.layers_panel import LayersPanel
from mdtools.mdrem import disc_title
from mdtools.panels.mdrem_port import resolve_port
from mdtools.panels.metadata_dialog import MetadataDialog
from mdtools.panels.record_dialog import RecordDialog
from mdtools.panels.new_design_dialog import NewDesignDialog
from mdtools.panels.print_dialog import PrintDialog
from mdtools.panels.properties_panel import PropertiesPanel
from mdtools.panels.settings_dialog import SettingsDialog
from mdtools.panels.startup_dialog import StartupDialog
from mdtools.panels.tool_panel import ToolPanel
from mdtools.project import (
    PAGE_COVER,
    PAGE_DISC,
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
JCARD_TEMPLATE = "MiniDisc Cover (J-Card)"


class MainWindow(QMainWindow):
    def __init__(self, show_startup_dialog: bool = True):
        super().__init__()
        # Not "Label Designer" any more: designing labels is one of four
        # things this does, alongside recording a disc from foobar2000,
        # titling it over infrared, and standing in for the deck's remote.
        self.setWindowTitle(self.tr("MDTools - MiniDisc Studio"))
        # Set here too, not just on QApplication in main.py -- so the
        # window has the right icon (title bar/taskbar/alt-tab) even when
        # MainWindow is constructed directly (tests, or any future
        # embedding) rather than only via main()'s normal startup path.
        self.setWindowIcon(QIcon(str(gallery.gallery_dir() / "mdlogo.png")))
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
        self._connected_scenes: set = set()
        self.clipboard = Clipboard()
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
        if not show_startup_dialog or not self._run_startup_flow():
            self._new_design(prompt=False)

    # -- setup --------------------------------------------------------------

    def _build_page_toolbar(self) -> None:
        toolbar = QToolBar(self.tr("Page"), self)
        toolbar.addWidget(QLabel(self.tr("Editing:")))
        self.page_combo = QComboBox()
        self.page_combo.addItem(self.tr("Disc Label"), PAGE_DISC)
        self.page_combo.addItem(self.tr("Cover / J-Card"), PAGE_COVER)
        self.page_combo.currentIndexChanged.connect(self._on_page_combo_changed)
        toolbar.addWidget(self.page_combo)
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
        # it feeds. The three sources -- a CD, whatever foobar already has,
        # and a folder of files -- all end in the same recording.
        recording_menu = self.menuBar().addMenu(self.tr("&Recording"))
        # Hidden rather than disabled without the adapter: like the other
        # MDRem entry points, there is nothing it could usefully do.
        self.record_cd_action = recording_menu.addAction(
            self.tr("Record CD to MiniDisc..."), self._record_cd
        )
        self.record_folder_action = recording_menu.addAction(
            self.tr("Record Folder to MiniDisc..."), self._record_folder
        )
        self.record_action = recording_menu.addAction(
            self.tr("Record to MiniDisc from foobar2000..."), self._record_from_foobar
        )
        recording_menu.addSeparator()
        # Erasing is not recording, but it is what you do to a disc you are
        # about to record over, and it is the same deck and the same
        # adapter -- keeping it here beats a menu of its own for one entry.
        self.erase_disc_action = recording_menu.addAction(
            self.tr("Erase MiniDisc..."), self._erase_disc
        )
        self._sync_mdrem_actions()

        templates_menu = self.menuBar().addMenu(self.tr("&Templates"))
        templates_menu.addAction(self.tr("Manage Templates..."), self._manage_templates)
        templates_menu.addAction(self.tr("Change Template for This Page..."), self._change_page_template)

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

        window_menu = self.menuBar().addMenu(self.tr("&Window"))
        window_menu.addAction(self.tr("Settings..."), self._show_settings)

        help_menu = self.menuBar().addMenu(self.tr("&Help"))
        self._build_language_menu(help_menu)
        help_menu.addAction(self.tr("About MDTools..."), self._show_about)

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
        MDTools" -- it goes back to the startup screen.

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
        loaded/created either way; False only if the user cancelled the
        dialog outright (Cancel/close), in which case __init__ falls back
        to _new_design(prompt=False) exactly like a cancelled
        NewDesignDialog always has."""
        dialog = StartupDialog(recent_projects.recent_projects(), self)
        if dialog.exec() != StartupDialog.DialogCode.Accepted:
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
            disc_template = dialog.selected_disc_template
            cover_template = dialog.selected_cover_template
            if disc_template is None or cover_template is None:
                return False
        else:
            from mdtools.templates import registry

            templates = registry.load_templates()
            if not templates["disc"] or not templates["cover"]:
                return False
            disc_template = templates["disc"][0]
            cover_template = templates["cover"][0]

        disc_scene = DesignScene(disc_template)
        self._populate_new_scene(disc_scene, disc_template, PAGE_DISC)

        cover_scene = DesignScene(cover_template)
        self._populate_new_scene(cover_scene, cover_template, PAGE_COVER)

        self.current_project_path = None
        self.project = Project(
            metadata=ProjectMetadata(),
            pages={PAGE_DISC: disc_scene, PAGE_COVER: cover_scene},
        )
        self._reset_undo_stack()
        self.properties_panel.set_default_text_style(self.project.default_text_style)
        self._sync_grayscale_controls()
        self.page_combo.setCurrentIndex(0)
        self._show_page(PAGE_DISC)
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
        elif page == PAGE_DISC:
            scene.seed_disc_defaults()

    def _change_page_template(self) -> None:
        """Swaps the current page onto a different template.

        Until this existed, a template could only be chosen when the project
        was created -- picking the wrong one meant starting over."""
        if self.project is None:
            return
        scene = self._current_scene()
        if scene is None:
            return

        from mdtools.templates import registry

        kind = "disc" if self.current_page == PAGE_DISC else "cover"
        templates = registry.load_templates()[kind]
        if not templates:
            return
        names = [template.name for template in templates]
        current = scene.template.name
        chosen_name, ok = QInputDialog.getItem(
            self,
            self.tr("Change Template"),
            self.tr("Template for this page:"),
            names,
            names.index(current) if current in names else 0,
            False,
        )
        if not ok:
            return
        template = templates[names.index(chosen_name)]
        if template.name == current:
            return

        answer = QMessageBox.warning(
            self,
            self.tr("Change Template"),
            self.tr(
                "Changing the template clears this page: every layer on it is removed, and the undo history "
                "is reset.\n\nThe other page and the project's metadata are left alone."
            ),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        self.apply_template(self.current_page, template)

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
        self.page_combo.setCurrentIndex(0)
        self._show_page(PAGE_DISC)
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
        # First save proposes "Artist - Album (Year).mdproj" in the
        # projects folder, using the same disc_title() the deck is told, so
        # the file and the disc cannot end up named differently.
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save Project As"),
            user_paths.project_start_path(self.current_project_path, disc_title(self.project.metadata)),
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
        scene = self._current_scene()
        if scene is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export Cut SVG"), self._export_start_path(), self.tr("SVG (*.svg)")
        )
        if not path:
            return
        export_svg(scene, path)
        self.statusBar().showMessage(self.tr("Exported cut outline to {path}").format(path=path), 5000)

    def _export_png(self) -> None:
        scene = self._current_scene()
        if scene is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export Print PNG"), self._export_start_path(), self.tr("PNG (*.png)")
        )
        if not path:
            return
        export_png(scene, path, grayscale=False)
        self.statusBar().showMessage(self.tr("Exported print artwork to {path}").format(path=path), 5000)

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
        export_png(scene, path, grayscale=True, brightness=adjustment.brightness, contrast=adjustment.contrast)
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

    def _project_file_filter(self) -> str:
        # a module-level constant can't use self.tr(), so this is computed
        # per-call instead (cheap, and picks up the active language)
        return self.tr("MDTools Project (*.mdproj)")

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

    def _sync_mdrem_actions(self) -> None:
        """Re-reads the adapter setting into the menu.

        Every other MDRem entry point lives on a dialog that is rebuilt each
        time it opens, so it picks the setting up for free. This one is an
        action built once at startup, and stayed visible after the adapter
        was switched off -- offering to record an album through hardware the
        user had just said they do not have."""
        enabled = app_settings.mdrem_enabled()
        self.record_action.setVisible(enabled)
        # Ripping a CD needs no adapter, but this entry does not stop at
        # ripping -- it goes straight on to record what it ripped, which
        # does. Splitting a rip-only entry out of it would be inventing a
        # feature nobody asked for. Same for loading a folder into
        # foobar2000: on its own it is not a feature anyone asked for.
        self.record_cd_action.setVisible(enabled)
        self.record_folder_action.setVisible(enabled)
        # Erasing is nothing but adapter keypresses, so without one there is
        # not even a partial operation to offer.
        self.erase_disc_action.setVisible(enabled)

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
            self.tr("Restart MDTools for the new language to take full effect."),
            parent=self,
        )
        restart_btn = box.addButton(self.tr("Restart Now"), QMessageBox.ButtonRole.AcceptRole)
        box.addButton(self.tr("Later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is restart_btn:
            self._restart_app()

    @staticmethod
    def _restart_app() -> None:
        """Relaunches MDTools as a brand-new process, then quits this one.
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

    def _record_from_foobar(self) -> None:
        # The whole flow runs through the adapter -- it is what arms the deck
        # and what marks the tracks -- so with the adapter switched off there
        # is nothing here to do. Silent rather than a dialog: the menu entry
        # is hidden in that state, so this is a backstop, not a path anyone
        # is meant to arrive at. Without the adapter, recording means
        # pressing record on the deck and letting its LEVEL-SYNC split the
        # tracks.
        if not app_settings.mdrem_enabled():
            return
        port = resolve_port(self)
        if port is None:
            return
        self._run_record_dialog(port)

    def _record_cd(self) -> None:
        """Recording > Record CD to MiniDisc... -- rips the disc into
        foobar2000's playlist, then records that playlist exactly as the
        entry above does.

        The port is resolved before the rip rather than after it: the rip is
        the expensive half, and discovering there is no adapter to record
        through is worth finding out beforehand."""
        if not app_settings.mdrem_enabled():
            return
        port = resolve_port(self)
        if port is None:
            return
        rip = CdRipDialog(app_settings.foobar_url(), self)
        if rip.exec() != QDialog.DialogCode.Accepted:
            return
        # The rip's own metadata goes forward. Its titles are the ones it
        # wrote into the files, so they say the same thing the playlist
        # does -- what it adds is the artwork it found (or the user picked)
        # while identifying the disc, which nothing in a playlist carries.
        self._run_record_dialog(port, metadata=rip.result_metadata)

    def _record_folder(self) -> None:
        """Recording > Record Folder to MiniDisc... -- loads an album that
        is already on disk into foobar2000's playlist, then records it.

        The same shape as _record_cd, and for the same reasons: the port is
        resolved first (there is no point loading a playlist for a recording
        that cannot happen), and the dialog's own result is the hand-off.
        Unlike the CD, its metadata *is* passed on -- see FolderRecordDialog
        for why files nobody rewrote cannot carry an edit by themselves."""
        if not app_settings.mdrem_enabled():
            return
        port = resolve_port(self)
        if port is None:
            return
        folder = FolderRecordDialog(app_settings.foobar_url(), self)
        if folder.exec() != QDialog.DialogCode.Accepted:
            return
        self._run_record_dialog(port, metadata=folder.result_metadata)

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

    def _run_record_dialog(self, port: str, metadata: ProjectMetadata | None = None) -> None:
        """The recording itself, shared by all three entry points -- by the
        time it runs, "what is in foobar's playlist" is the only input,
        whether a CD put it there, a folder did, or the user did."""
        dialog = RecordDialog(port, app_settings.foobar_url(), self, metadata=metadata)
        dialog.exec()
        # What was just recorded is also what the label should describe, so
        # the playlist's metadata (plus whatever cover art was found for it)
        # is adopted by the project rather than left for the user to retype
        # into the Tools panel's Metadata dialog by hand.
        if dialog.result_metadata is not None and self.project is not None:
            self.project.metadata = dialog.result_metadata
            self._mark_dirty()
            self._auto_layout_project(dialog.result_metadata)

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
                "This replaces everything on both pages -- the disc label and the J-card -- and resets the "
                "undo history.\n\nThe project's metadata is left alone."
            ),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        self._auto_layout_project(metadata)

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

    def _auto_layout_project(self, metadata: ProjectMetadata) -> None:
        """Turns an album into a first draft of both pages: the disc label
        and the J-card.

        After a recording this runs without asking. That is deliberate: the
        recording flow has already asked for confirmation several times
        over, and an extra prompt at the very end -- after the user has
        watched an album go down in real time -- would be noise. The Tools
        panel button, which is a single click out of nowhere, does confirm.
        """
        if self.project is None or not metadata.cover_art:
            return
        self._auto_layout_cover(metadata)
        self._auto_layout_disc_label(metadata)

    def _auto_layout_disc_label(self, metadata: ProjectMetadata) -> None:
        """The full-face template, the cover across it cropped to the cut
        outline, and the MiniDisc logo on the slider sticker."""
        template = self._template_named("disc", FULL_LABEL_TEMPLATE)
        if template is None:
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
        recolour_insertion_mark(scene, metadata.cover_art)

        self.undo_stack.beginMacro(self.tr("Lay Out Disc Label"))
        cover = place_cover_on_label(scene, metadata.cover_art)
        if cover is not None:
            # Behind whatever the template change seeded (the insertion-mark
            # triangle and its label), not on top: a full-bleed cover would
            # otherwise bury them where they'd never be noticed, and hidden
            # layers are a worse starting point than ones needing restyling.
            behind = [item for item in scene.print_items() if item is not cover]
            cover.setZValue(min((item.zValue() for item in behind), default=0.0) - 1.0)
            self.undo_stack.push(AddItemCommand(scene, cover, self.tr("Cover Art")))
        logo_path = gallery.gallery_dir() / "mdlogo.png"
        logo = scene.add_image(str(logo_path)) if logo_path.exists() else None
        if place_logo_on_slider(scene, logo) is not None:
            self.undo_stack.push(AddItemCommand(scene, logo, self.tr("MiniDisc Logo")))
        self.undo_stack.endMacro()

        # The cover is deliberately oversized so it covers the label
        # completely; this is what trims the overhang back to the cut shape.
        self._clip_layers()

    def _auto_layout_cover(self, metadata: ProjectMetadata) -> None:
        """The three-panel J-card: cover art turned onto the front, an
        accent band down the spine, and the track list on the back.

        Deliberately *not* run through Clip Layers, unlike the disc label.
        Nothing here overhangs by more than a pen width, and clipping would
        rasterise the panel blocks and the track list -- turning text that
        is still worth editing into a flat image."""
        template = self._template_named("cover", JCARD_TEMPLATE)
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

    def _edit_metadata(self) -> None:
        if self.project is None:
            return
        dialog = MetadataDialog(self.project.metadata, self)
        if dialog.exec() == MetadataDialog.DialogCode.Accepted and dialog.result_metadata is not None:
            self.project.metadata = dialog.result_metadata
            self._mark_dirty()
