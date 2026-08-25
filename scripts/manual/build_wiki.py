"""Builds the English user manual as a set of GitHub wiki pages.

Reuses content_en.py directly -- the same block list build_manual.py
turns into the PDF -- so the wiki can never drift from the PDF's own
text. One page per chapter, a Home page with the table of contents, and
a _Sidebar page (GitHub's own always-visible nav) generated from the
same chapter list.

    python scripts/manual/build_wiki.py <path-to-wiki-checkout>

The path is a local clone of the repo's own wiki
(`git clone https://github.com/<owner>/<repo>.wiki.git`) -- this script
only writes files into it; committing and pushing is left to the caller,
same division of labour build_manual.py has with the PDF it writes into
doc/.

Markdown, unlike the PDF's HTML, needs almost no translation for the
inline marks: **bold**, *italic* and `literal` are GitHub Markdown's own
syntax already. note/warn/tip become GitHub's own alert blockquotes
(`> [!NOTE]` and friends), which render with an icon with no CSS needed.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import content_en  # noqa: E402

IMG_DIR = ROOT / "doc" / "img"

_ALERT_KIND = {"note": "NOTE", "warn": "WARNING", "tip": "TIP"}


def _slug(title: str) -> str:
    """A wiki page's filename *is* its URL and its default sidebar
    entry, so this has to be stable across regenerations -- rerunning
    this script must overwrite the same pages, not create new ones
    beside stale copies under a slightly different slug."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
    return slug


def _page_filename(index: int, title: str) -> str:
    # Numbered so the plain, unstyled "Pages" list GitHub shows as a
    # fallback (if _Sidebar.md is ever missing) still reads top to
    # bottom in the manual's own order rather than alphabetically.
    return f"{index:02d}-{_slug(title)}.md"


def _inline(text: str) -> str:
    """The content files' inline marks are already GitHub Markdown's
    own (**bold**, *italic*, `literal`) -- nothing to translate, unlike
    build_manual.py's HTML path. A literal single newline mid-paragraph
    (used for a forced line break, e.g. a summary line followed by its
    explanation) needs a trailing double-space to stay a line break
    rather than collapsing into the next sentence, which is what a bare
    newline does in Markdown."""
    return text.replace("\n", "  \n")


def _table(head: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    for row in rows:
        # A cell's own literal "|" (none in this manual today, but a
        # table cell breaking the row silently if one is ever added is
        # exactly the kind of bug that is invisible until it happens)
        # has to be escaped, or it reopens the row.
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    return "\n".join(lines)


def _alert(kind: str, text: str) -> str:
    label = _ALERT_KIND.get(kind, "NOTE")
    body = "\n".join(f"> {line}" for line in _inline(text).split("\n"))
    return f"> [!{label}]\n{body}"


def _figure(key: str, caption: str) -> str:
    path = IMG_DIR / "en" / f"{key}.png"
    if not path.exists():
        path = IMG_DIR / f"{key}.png"
    if not path.exists():
        print(f"  ! missing figure: {key}")
        return ""
    return f"![{caption}](img/{path.name})\n\n*{_inline(caption)}*"


def render_blocks(blocks: list) -> list[str]:
    parts: list[str] = []
    for block in blocks:
        kind, value = next(iter(block.items()))
        if kind == "h2":
            parts.append(f"## {_inline(value)}")
        elif kind == "p":
            parts.append(_inline(value))
        elif kind == "ul":
            parts.append("\n".join(f"- {_inline(item)}" for item in value))
        elif kind == "ol":
            parts.append("\n".join(f"{i}. {_inline(item)}" for i, item in enumerate(value, start=1)))
        elif kind == "table":
            parts.append(_table(value["head"], value["rows"]))
        elif kind in ("note", "warn", "tip"):
            parts.append(_alert(kind, value))
        elif kind == "fig":
            figure = _figure(value[0], value[1])
            if figure:
                parts.append(figure)
        else:
            raise ValueError(f"unknown block: {kind}")
    return parts


def _copy_images(out_dir: Path) -> None:
    """Every figure the book actually references, English only -- a
    wiki page is not the trilingual PDF, and copying doc/img wholesale
    would drag two other languages' screenshots into a wiki that never
    shows them."""
    img_out = out_dir / "img"
    img_out.mkdir(parents=True, exist_ok=True)
    used_keys = {
        value[0]
        for chapter in content_en.BOOK
        for block in chapter["blocks"]
        for kind, value in [next(iter(block.items()))]
        if kind == "fig"
    }
    for key in used_keys:
        src = IMG_DIR / "en" / f"{key}.png"
        if not src.exists():
            src = IMG_DIR / f"{key}.png"
        if not src.exists():
            continue
        shutil.copyfile(src, img_out / src.name)


def build(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _copy_images(out_dir)

    pages: list[tuple[str, str]] = []  # (title, filename)
    for index, chapter in enumerate(content_en.BOOK, start=1):
        title = chapter["title"]
        filename = _page_filename(index, title)
        body = "\n\n".join(render_blocks(chapter["blocks"]))
        (out_dir / filename).write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        pages.append((title, filename))
        print(f"  {filename}")

    home_lines = [
        f"# {content_en.TITLE} — {content_en.SUBTITLE}",
        "",
        content_en.TITLE_NOTE + ".",
        "",
        f"_{content_en.VERSION_LINE}, {content_en.AUTHOR_LINE}_",
        "",
        "## Contents",
        "",
    ]
    # GitHub resolves a wiki cross-link with or without ".md", but the
    # extension-less form is its own documented convention for wiki
    # links specifically -- unlike the "img/..." figure paths above,
    # which are real relative file paths, not wiki page links, and keep
    # their extension.
    home_lines += [
        f"{i}. [{title}]({Path(filename).stem})" for i, (title, filename) in enumerate(pages, start=1)
    ]
    (out_dir / "Home.md").write_text("\n".join(home_lines) + "\n", encoding="utf-8")
    print("  Home.md")

    sidebar_lines = [f"**{content_en.TITLE}**", ""]
    sidebar_lines += [f"- [{title}]({Path(filename).stem})" for title, filename in pages]
    (out_dir / "_Sidebar.md").write_text("\n".join(sidebar_lines) + "\n", encoding="utf-8")
    print("  _Sidebar.md")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: build_wiki.py <path-to-wiki-checkout>")
        return 1
    build(Path(argv[1]))
    print("\nDone. Review the checkout, then commit and push it yourself.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
