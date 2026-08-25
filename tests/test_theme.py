from PySide6.QtGui import QPalette

from mdtools import theme


def test_apply_theme_switches_to_the_fusion_style(qt_app):
    theme.apply_theme(qt_app)
    # QApplication.setStyleSheet() wraps whatever base style is active in a
    # QStyleSheetStyle proxy, and *that* object's objectName() is always ""
    # -- confirmed directly, not assumed -- so it has to be peeled back to
    # see the base style underneath. Clearing the stylesheet does exactly
    # that without needing to touch apply_theme()'s own internals.
    qt_app.setStyleSheet("")
    assert qt_app.style().objectName().lower() == "fusion"


def test_apply_theme_sets_a_dark_window_colour(qt_app):
    theme.apply_theme(qt_app)
    window_color = qt_app.palette().color(QPalette.ColorRole.Window)
    # Dark, not the light default -- checked as "closer to black than
    # white" rather than pinning the exact RGB, so a later shade tweak
    # doesn't break this test.
    assert window_color.lightness() < 128


def test_apply_theme_applies_a_non_empty_stylesheet(qt_app):
    """The whole point of moving beyond a bare palette -- guards against a
    future refactor accidentally dropping the setStyleSheet() call."""
    theme.apply_theme(qt_app)
    assert qt_app.styleSheet().strip() != ""


def test_the_stylesheet_and_the_palette_agree_on_the_accent_colour(qt_app):
    """Two separate places (QPalette's Highlight/Link roles, and every
    accent-coloured rule in the QSS) both derive from theme._ACCENT --
    this pins that they haven't drifted apart, since nothing else would
    catch that short of eyeballing every widget."""
    theme.apply_theme(qt_app)
    assert theme._ACCENT in qt_app.styleSheet()
    highlight = qt_app.palette().color(QPalette.ColorRole.Highlight)
    assert highlight.name() == theme._ACCENT


def test_highlighted_text_contrasts_with_the_now_darker_accent(qt_app):
    """The old KDE-Breeze accent was light enough for black selected-text
    to read fine on it; the current Discord-Blurple accent is a deep
    indigo, dark enough that it needs light text instead. Checked as
    "light" rather than pinning the exact colour, so a later shade tweak
    within the same family doesn't break this."""
    theme.apply_theme(qt_app)
    highlighted_text = qt_app.palette().color(QPalette.ColorRole.HighlightedText)
    assert highlighted_text.lightness() > 128


def test_the_stylesheet_never_sets_a_blanket_widget_background(qt_app):
    """Regression guard for the canvas-protection reasoning in theme.py's
    own module docstring: a bare `QWidget { background-color: ... }` (or
    QAbstractScrollArea, QGraphicsView's own base class) rule would leak
    into DesignView and fight its explicit white backgroundBrush -- every
    rule here must instead target a specific, named widget type."""
    stylesheet = theme._build_stylesheet()
    for line in stylesheet.splitlines():
        if "{" not in line:
            continue
        selector = line.split("{")[0].strip()
        assert not selector.startswith(("QWidget", "QAbstractScrollArea", "QGraphicsView")), (
            f"blanket background rule targets the canvas too: {selector!r}"
        )
