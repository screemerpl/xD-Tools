"""The cover-art thumbnail, which is also the button for replacing it.

Four dialogs now show the artwork a disc is about to be labelled with -- the
Metadata editor, and all three recording sources -- so this lives in one
place rather than four. Not merely to avoid the duplication: the *rule* it
carries has to be the same everywhere, and it is not obvious.

**Every automatic source guesses.** iTunes returns whatever release its
search matched, which for a reissue, a compilation or a band with a common
name is regularly the wrong sleeve. So the picture itself is the button:
clicking the thing you can see is wrong is where anyone looks first, and it
is the only way out of a bad guess.

**The bytes are validated by trying to load them**, never by trusting the
extension. They end up saved in the project and handed to auto_layout and
palette, neither of which can report back that they were never an image.

No lookup happens in here. Where the artwork comes from -- a search, a
playlist, a folder's own tags -- is each dialog's business; this only ever
displays what it is given and offers to swap it for a local file.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QFileDialog, QFrame, QLabel, QMessageBox

from mdtools import user_paths
from mdtools.gallery import save_downloaded_cover
from mdtools.metadata_lookup import AlbumCandidate, MetadataLookupError, find_cover

SIZE = 100


class CoverPreview(QLabel):
    """Shows `data` (image bytes or None), and swaps it on click."""

    changed = Signal()  # the user chose a different image
    clicked = Signal()  # the picture was pressed and released inside itself

    def __init__(self, size: int = SIZE, parent=None):
        super().__init__(parent)
        self._size = size
        self._data: bytes | None = None
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QFrame.Shape.Box)
        self.setScaledContents(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            self.tr("Click to choose the cover art yourself -- use this when the fetched one is wrong.")
        )
        self._show_placeholder()
        # Wired here rather than by each caller: a preview that silently did
        # nothing when clicked would be the same trap in four places.
        self.clicked.connect(self.choose_file)

    # --- what it holds --------------------------------------------------

    @property
    def data(self) -> bytes | None:
        return self._data

    def set_cover(self, data: bytes | None) -> bool:
        """Holds `data` and displays it; returns whether it could be drawn.

        The two are deliberately separate. Bytes that Qt cannot decode are
        still *kept* -- they came from somewhere that had a reason for them,
        and Pillow (which palette.py reads them with) understands formats
        this preview does not. Only the picture falls back to the
        placeholder.

        The return value exists for the one caller that must be strict:
        choose_file, where an unreadable pick means the user pointed at a
        PDF and should be told, rather than silently saving it into the
        project."""
        self._data = data or None
        if not data:
            self._show_placeholder()
            return False
        pixmap = QPixmap()
        if not pixmap.loadFromData(data):
            self._show_placeholder()
            return False
        self.setText("")
        self.setPixmap(
            pixmap.scaled(
                self._size,
                self._size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        return True

    def _show_placeholder(self) -> None:
        self.setPixmap(QPixmap())
        self.setText(self.tr("No cover\n\n(click to\nchoose one)"))

    # --- replacing it ---------------------------------------------------

    def mouseReleaseEvent(self, event) -> None:
        # Released inside, not merely pressed: a press that wandered off the
        # label before letting go is how anyone cancels a misclick.
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def choose_file(self) -> bool:
        """Replaces the cover with a local image file.

        Overrides whatever a lookup found, without asking: the user clicked
        the picture they can see is wrong."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Choose Cover Art"),
            user_paths.image_start_path(),
            self.tr("Images (*.png *.jpg *.jpeg *.bmp *.webp)"),
        )
        if not path:
            return False
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            QMessageBox.warning(
                self,
                self.tr("Choose Cover Art"),
                self.tr("Could not read the file:\n{error}").format(error=exc),
            )
            return False
        previous = self._data
        if not self.set_cover(data):
            # set_cover already dropped to the placeholder, so put back what
            # was there: a bad pick must not lose a good cover.
            self.set_cover(previous)
            QMessageBox.warning(
                self, self.tr("Choose Cover Art"), self.tr("That file could not be read as an image.")
            )
            return False
        self.changed.emit()
        return True


def fetch_into(
    preview: CoverPreview, artist: str, album: str, track_count: int | None = None
) -> AlbumCandidate | None:
    """Looks up a cover for this album and shows it in `preview`.

    The candidate is returned even when there was no artwork, because it
    also carries a release year the caller may be missing -- the same reason
    metadata_lookup.find_cover hands it back.

    Blocking, with a wait cursor, matching every other lookup in this app:
    it is one occasional call made because somebody opened a window, not a
    live sync (see metadata_lookup's own note). Failure is silent -- artwork
    is a bonus on top of whatever the caller was really doing, and a warning
    box about it would interrupt something that already succeeded.

    Never picks the artwork for a compilation: a search for "Various
    Artists" returns some unrelated record's sleeve, which would then be
    printed on this disc as though it belonged to it. Callers branch on
    ProjectMetadata.is_compilation() before getting here and draw one with
    mixtape_cover instead."""
    if not artist.strip() and not album.strip():
        return None
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        data, chosen = find_cover(artist, album, track_count)
    except MetadataLookupError:
        return None
    finally:
        QApplication.restoreOverrideCursor()
    if data is not None and chosen is not None:
        preview.set_cover(data)
        save_downloaded_cover(chosen.artist_name, chosen.collection_name, data)
    return chosen
