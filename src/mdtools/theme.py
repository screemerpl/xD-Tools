"""A modern, flat dark theme for the whole application.

Qt's own "Fusion" cross-platform style (already inside PySide6, no new
dependency) plus a hand-written QSS stylesheet, rather than a theme
package -- same "reach for what Qt/the stdlib already gets us there with"
call as metadata_lookup.py picking the iTunes Search API over anything
needing sign-up, or translate.py picking MyMemory's documented public API
over scraping Google Translate.

**Two layers, not one.** `_build_palette()` still sets a QPalette first --
Fusion alone already looks flatter than each OS's native style, and the
palette is what every widget falls back to for anything the stylesheet
below doesn't touch (QMessageBox, native file dialogs, disabled-state
colours, text selection). `_build_stylesheet()` then layers actual QSS on
top for the things a bare palette cannot express at all: rounded corners,
hover/pressed states, focus rings, per-widget borders. A first version
shipped with only the palette -- explicit user follow-up ("this does not
look very nice") asked for more visual polish than a palette alone can
give; QSS was chosen over a pip theme package for the same
zero-dependency reasoning as the palette-only version, and over a
Kvantum-based theme because Kvantum is a Linux/X11-only style engine
needing a compiled system plugin that cannot be bundled into a PyInstaller
Windows build at all (MDTools' primary target).

Every colour used by both layers is defined once, below, so the palette
and the stylesheet can never drift into disagreeing about what "the
background" or "the accent" is.

Deliberately not constructed at import time -- QPalette/QColor are Qt GUI
types, and constructing one before a QApplication exists segfaults (see
CLAUDE.md's "never construct a Qt GUI type at module import time" note).
apply_theme() is only ever called from main(), after QApplication already
exists.

**Deliberately does not touch QGraphicsView's background.** The disc/cover
design canvas (`canvas/view.py`'s `DesignView`) sets its own explicit white
`backgroundBrush` regardless of the app palette -- a physical label design
has to stay legible against white the way it will actually print, not
whatever colour this theme happens to be. Every rule below is scoped to a
specific widget type (QPushButton, QLineEdit, ...), never a blanket
QWidget/QAbstractScrollArea background-color, specifically so nothing here
can leak into the canvas and fight that.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# KDE Breeze's own accent blue -- well-tested for legibility against a dark
# background. Used for links, selection/highlight, checked/focused controls,
# and the QSS accent below, so every "this is interactive" signal in the UI
# reads consistently.
_ACCENT = "#2a82da"
_ACCENT_HOVER = "#3f93e6"
_ACCENT_PRESSED = "#1f6cb8"

_WINDOW = "#353535"
_BASE = "#232323"
_ALT_BASE = "#3a3a3a"
_BORDER = "#4a4a4a"
_BORDER_LIGHT = "#5c5c5c"
_TEXT = "#ffffff"
_DISABLED_TEXT = "#7f7f7f"
_DISABLED_BG = "#3d3d3d"

_RADIUS = "4px"


def _build_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(_WINDOW))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(_BASE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(_WINDOW))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.Text, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(_WINDOW))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(_TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("red"))
    palette.setColor(QPalette.ColorRole.Link, QColor(_ACCENT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("black"))

    # Disabled controls need to actually look disabled against a dark
    # background -- Fusion's own default disabled-state colours are tuned
    # for a light palette and read as barely-dimmed white-on-dark otherwise.
    disabled_text = QColor(_DISABLED_TEXT)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled_text)

    return palette


def _build_stylesheet() -> str:
    return f"""
        QPushButton, QToolButton {{
            background-color: {_WINDOW};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            padding: 5px 12px;
        }}
        QToolButton {{
            /* Icon-only buttons (Tools panel, zoom toolbar) need a tighter
               padding than a labelled push button, or the icon ends up
               swimming in empty space. */
            padding: 4px;
        }}
        QPushButton:hover, QToolButton:hover {{
            background-color: {_ALT_BASE};
            border-color: {_BORDER_LIGHT};
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background-color: {_BASE};
        }}
        QPushButton:checked, QToolButton:checked {{
            background-color: {_ACCENT};
            border-color: {_ACCENT};
        }}
        QPushButton:default {{
            border-color: {_ACCENT};
        }}
        QPushButton:disabled, QToolButton:disabled {{
            background-color: {_DISABLED_BG};
            border-color: {_BORDER};
            color: {_DISABLED_TEXT};
        }}

        QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background-color: {_BASE};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            padding: 3px 6px;
            selection-background-color: {_ACCENT};
            selection-color: black;
        }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
            border-color: {_ACCENT};
        }}
        QLineEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled,
        QDoubleSpinBox:disabled, QComboBox:disabled {{
            background-color: {_DISABLED_BG};
            color: {_DISABLED_TEXT};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 18px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {_BASE};
            border: 1px solid {_BORDER};
            selection-background-color: {_ACCENT};
            selection-color: black;
        }}

        QCheckBox::indicator, QRadioButton::indicator {{
            width: 14px;
            height: 14px;
            border: 1px solid {_BORDER_LIGHT};
            background-color: {_BASE};
        }}
        QRadioButton::indicator {{
            border-radius: 7px;
        }}
        QCheckBox::indicator {{
            border-radius: 3px;
        }}
        QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
            background-color: {_ACCENT};
            border-color: {_ACCENT};
        }}

        QGroupBox {{
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            margin-top: 10px;
            padding-top: 8px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }}

        QTabWidget::pane {{
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
        }}
        QTabBar::tab {{
            background-color: {_WINDOW};
            border: 1px solid {_BORDER};
            border-bottom: none;
            border-top-left-radius: {_RADIUS};
            border-top-right-radius: {_RADIUS};
            padding: 5px 12px;
        }}
        QTabBar::tab:selected {{
            background-color: {_ALT_BASE};
            border-bottom: 2px solid {_ACCENT};
        }}
        QTabBar::tab:!selected:hover {{
            background-color: {_ALT_BASE};
        }}

        QMenuBar {{
            background-color: {_WINDOW};
        }}
        QMenuBar::item:selected {{
            background-color: {_ACCENT};
        }}
        QMenu {{
            background-color: {_WINDOW};
            border: 1px solid {_BORDER};
        }}
        QMenu::item:selected {{
            background-color: {_ACCENT};
            color: black;
        }}
        QMenu::separator {{
            height: 1px;
            background: {_BORDER};
            margin: 4px 6px;
        }}

        QToolBar {{
            background-color: {_WINDOW};
            border: none;
            spacing: 3px;
        }}
        QStatusBar {{
            background-color: {_WINDOW};
        }}
        QDockWidget {{
            titlebar-close-icon: none;
        }}
        QDockWidget::title {{
            background-color: {_ALT_BASE};
            padding: 4px 6px;
        }}

        QProgressBar {{
            background-color: {_BASE};
            border: 1px solid {_BORDER};
            border-radius: {_RADIUS};
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {_ACCENT};
            border-radius: {_RADIUS};
        }}

        QScrollBar:vertical {{
            background: {_WINDOW};
            width: 12px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: {_BORDER_LIGHT};
            border-radius: 5px;
            min-height: 24px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {_ACCENT};
        }}
        QScrollBar:horizontal {{
            background: {_WINDOW};
            height: 12px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: {_BORDER_LIGHT};
            border-radius: 5px;
            min-width: 24px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {_ACCENT};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0;
            height: 0;
            border: none;
        }}

        QHeaderView::section {{
            background-color: {_WINDOW};
            border: none;
            border-right: 1px solid {_BORDER};
            border-bottom: 1px solid {_BORDER};
            padding: 4px 6px;
        }}
        QTreeView, QListView, QTableView {{
            background-color: {_BASE};
            alternate-background-color: {_WINDOW};
            border: 1px solid {_BORDER};
            selection-background-color: {_ACCENT};
            selection-color: black;
        }}

        QSlider::groove:horizontal {{
            background: {_BASE};
            border: 1px solid {_BORDER};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {_ACCENT};
            width: 14px;
            margin: -6px 0;
            border-radius: 7px;
        }}

        QToolTip {{
            background-color: {_ALT_BASE};
            color: {_TEXT};
            border: 1px solid {_BORDER};
            padding: 3px 6px;
        }}
    """


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setPalette(_build_palette())
    app.setStyleSheet(_build_stylesheet())
