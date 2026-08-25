"""Shared by every dialog/widget that shows an elapsed/remaining time next
to a progress bar -- was copy-pasted verbatim into seven files before this
one existed.
"""

from __future__ import annotations


def mmss(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"
