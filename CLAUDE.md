# MDTools

A PySide6 desktop workbench for MiniDisc. It began as a label designer and
outgrew the name -- **"MDTools - MiniDisc Studio"**, not "Label Designer":

- designs disc labels and cover/J-card inserts, exporting SVG (cut/fold
  shapes only) and PNG (print artwork, clipped to the cut outline) for a
  Cricut cutting machine plus a regular printer;
- with an MDRem infrared adapter, records an album from foobar2000 onto a
  deck with a track mark at every song, writes the disc and track titles
  onto the MiniDisc, and stands in for the deck's remote;
- rips an audio CD to FLAC, identifies it on MusicBrainz from its table of
  contents, loads it into foobar2000 in disc order, and records that.

Keep the window title, Help > About, the README, `pyproject.toml`'s
`description` and the user manual in step when that scope shifts again --
every one of them described a "label designer" long after it stopped being
only that, and each was found separately, at a different time.

**Treat physical accuracy as load-bearing.** Output gets cut with a blade —
mm dimensions and the cut-vs-print separation are not cosmetic details, they
are the actual product. Don't round, approximate, or "simplify" geometry
without checking.

## Stack

- PySide6 (`QGraphicsView`/`QGraphicsScene` as the vector canvas, `QtSvg` for export)
- Pillow (grayscale PNG conversion)
- PyInstaller for standalone builds (`scripts/build_windows.ps1`, `scripts/build_linux.sh`)
- pytest + pytest-qt, run via `.venv/Scripts/python.exe -m pytest -q`

## Layout

```
src/mdtools/
  main.py                  entry point
  app_window.py             MainWindow: page switcher, menus, docks, undo group, wiring
  project.py                Project / ProjectMetadata / Track / TextStyle dataclasses
  commands.py               QUndoCommand subclasses (add/delete/reorder/transform/property-edit)
  clipboard.py              in-memory copy/cut/paste (reuses project_io's item (de)serialization)
  gallery.py                bundled asset gallery (assets/img) + per-user downloaded-covers cache, merged
  metadata_lookup.py         iTunes Search API: track list + release year + cover art, given Album + Artist
  mdrem.py                  MDRem IR adapter: serial protocol, transliteration, upload plan (no Qt UI)
  foobar.py                 foobar2000 via its Beefweb REST API *and* its command line (no Qt UI)
  cdrip.py                  audio CD: drives, TOC, disc ids, rip plan, cdparanoia/flac (no Qt UI)
  musicbrainz.py            identifying a CD from its TOC alone -- a CD carries no text (no Qt UI)
  audio_folder.py           which files in a folder are the album, and in what order (no Qt)
  mixtape_cover.py          draws a cover for a compilation, which by definition has none
  user_paths.py             where every file dialog starts: Documents/MiniDiscProjects, Pictures
  auto_layout.py            places cover art on a disc label and the logo on its slider (no Qt UI beyond items)
  jcard_layout.py           builds the three J-card panels: front cover, spine band, track list (no Qt UI)
  palette.py                background/accent/text colours pulled out of a cover image (Pillow, no Qt)
  i18n/
    __init__.py               language setting persistence + QTranslator install
    mdtools_pl.ts / .qm       Polish translation (pyside6-lupdate/-lrelease output, hand-translated)
    mdtools_ja.ts / .qm       Japanese translation (pyside6-lupdate/-lrelease output, hand-translated)
  canvas/
    scene.py                 DesignScene: template outline + design items
    view.py                  zoomable/pannable view + mouse scale/rotate handles + undo hookup
    items.py                 "cut" vs "print" layer tagging, non-uniform scale helpers
    geometry.py               chamfered/filleted rectangle path builder
  templates/
    models.py                 DiscTemplate / CoverTemplate dataclasses
    registry.py                load/save templates (per-user JSON, seeded from defaults.json, synced on start)
    defaults.json              built-in templates
    template_dialog.py         Template Manager UI
  panels/
    icons.py                     self-drawn QIcon glyphs for the Tools panel's icon-only buttons
    tool_panel.py               icon-only add text/rectangle/image buttons + "insert from metadata" menu + Clip/Bake Layers
    properties_panel.py         edit selected item (position, rotation, multiline text, font, color/probe, reset)
    layers_panel.py             list + select + reorder + rename + delete items
    new_design_dialog.py        disc+cover template pickers for File > New
    metadata_dialog.py          album/artist/year/track-list editor + "Lookup Track List..." + "Upload Tracklist"
    mdrem_port.py               resolve_port(): the saved port, a probe, or a warning -- shared by both entry points
    mdrem_upload_dialog.py      preview-then-write dialog + the worker thread driving an upload
    remote_dialog.py            software Sony MD remote, opened from the startup screen
    record_dialog.py            Recording > Record to MiniDisc from foobar2000: arm, play, watch, hand off to titling
    cd_rip_dialog.py            Recording > Record CD to MiniDisc: read TOC, identify, rip, fill playlist, hand off
    cover_preview.py            the cover thumbnail that is also the button for replacing it, plus its lookup
    folder_record_dialog.py     Recording > Record Folder to MiniDisc: a folder of files into that playlist instead
    erase_dialog.py             Recording > Erase MiniDisc: a guided, ask-the-user-what-you-see erase
    about_dialog.py             Help > About MDTools
    asset_gallery_dialog.py     Insert Asset: pick one of the bundled gallery images
  io/
    svg_export.py               exports just the cut/fold shapes as physically-accurate SVG
    png_export.py               exports print artwork as PNG, clipped to the template outline
    project_io.py               save/load a whole project as one self-contained .mdproj JSON
assets/
  img/                      bundled asset gallery (currently just the MDTools logo) -- see gallery.py
bin/
  win64/                    bundled cdparanoia + flac + their DLLs -- see cdrip.py and its ATTRIBUTION.md
tests/          890+ tests, all offscreen via QT_QPA_PLATFORM=offscreen
doc/            the built user manual (PDF x3) + its generated screenshots -- see doc/README.md
scripts/
  build_windows.ps1 / build_linux.sh   PyInstaller onedir build
  clean_windows.ps1 / clean_linux.sh   remove build/dist/__pycache__/etc.
  manual/
    make_screenshots.py      drives every dialog and grabs it, once per language
    build_manual.py           blocks -> QTextDocument -> QPdfWriter, with a measured TOC
    content_{en,pl,ja}.py     the manual's text, as block lists
```

## Domain model

A **Project** = exactly one Disc Label page + one Cover/J-Card page + metadata
(album/artist/year/tracks) + a project-wide default text style, switchable via
a toolbar dropdown. Saved as a single self-contained `.mdproj` JSON file
(images embedded as base64 PNG, not file paths).

- **Disc template**: 37x52mm rectangle, 3mm chamfer top-left corner, 1mm
  fillet on the other three — given directly by the user, `verified: true`.
- **Disc + slider variant ("MiniDisc Disc Label (with Slider)")**: the same
  disc shape, plus a second, fully independent cut shape for the
  cartridge's write-protect slider label — 27.5mm x 17.5mm, left two
  corners rounded (2.5mm radius), right two corners square. Placed
  `slider_gap_mm` (3mm, a layout choice, not a measured spec) to the right
  of the disc, vertically centered — see `DesignScene._build_disc_outline`.
  Two independent `LAYER_CUT` shapes in one scene means
  `template_clip_path()` must return their *union*, not just the first
  one found, or print content over the slider would get clipped away as if
  it were outside the template. Dimensions user-confirmed, `verified: true`.
- **Full disc label variant ("Full disc label", `shape == "full_label"`)**:
  a completely different `DiscTemplate` outline — a single plain rounded
  rectangle (`corner_radius_mm`, 4mm) covering most of the disc's face,
  69.4mm x 66.4mm (the MD's own measured 71x68mm size inset by a 0.8mm
  margin on all sides), with the write-protect slider's notch *cut into*
  the right edge instead of placed as a separate adjacent shape (compare to
  the plain slider variant above, which adds a second independent
  `LAYER_CUT` shape rather than subtracting a hole from the first one).
  The notch is `slider_notch_width_mm`/`slider_notch_height_mm` (27.5mm x
  17.5mm, same footprint as the other slider label, left corners rounded
  `slider_notch_corner_radius_mm` = 2.5mm), flush against the label's right
  edge, positioned `slider_notch_top_mm` (25.2mm) below the label's own top
  edge — that's the user's measured "26mm from the MD's top edge",
  adjusted for the label's own 0.8mm margin, since the notch position has
  to be expressed in the label's local coordinates, not the MD's.
  `slider_notch_buffer_mm` (0.8mm) then physically enlarges the notch by
  that amount on its top/bottom/left sides (its right side is already
  flush with the label edge, so there's no material there to clear) — a
  real clearance cut, not a print-only keep-out zone, confirmed explicitly
  by the user ("it needs to be cut as well") after an initial ambiguous
  reading of "not printable" as a print-exclusion concept. `slider_travel_mm`
  (18mm) then extends that already-buffered notch further down by the same
  buffered width (confirmed: "it needs to include a buffer"), forming one
  continuous cutout (see `DesignScene._build_full_label_outline`) — the
  slot the slider tab travels through as it's slid between locked/unlocked.
  Built via `QPainterPath.subtracted()` (one `LAYER_CUT` shape with a hole
  in it), unlike the additive slider variant, so `template_clip_path()`
  already excludes the notch correctly with no extra union logic needed.
  Dimensions user-confirmed, `verified: true`.
- **Full disc label + slider variant ("Full disc label (with Slider)")**:
  the same full-label outline (rounded rect + notch cutout) above, plus a
  second, independent `LAYER_CUT` shape for the printable/cuttable slider
  sticker itself — but positioned *inside* the notch's void (flush with the
  label's right edge, aligned to the notch's own unbuffered top) rather
  than beside the whole disc. This reuses the same
  `slider_width_mm`/`slider_height_mm`/`slider_corner_radius_mm` fields the
  plain sticker-shape's adjacent slider label uses — they do double duty,
  meaning something different depending on `shape` (see `DiscTemplate`'s
  docstring); `slider_gap_mm` is unused here since there's no gap, just an
  overlap-by-design placement per explicit user instruction ("the slider
  frame should be positioned in the cutout"). Both shapes end up occupying
  the *same* region of canvas space on purpose — the small sticker nests
  inside the notch's buffer clearance, visible as the gap between the two
  outlines. `template_clip_path()`'s union already makes that nested area
  printable with no extra changes needed. Dimensions user-confirmed,
  `verified: true`.
- **Cover/J-card template ("MiniDisc Cover (J-Card)")**: 126mm wide x 73mm
  tall, 2mm corner radius, fold lines at 58.85mm and 67.15mm from the left
  edge (centering an 8.3mm spine section). User-confirmed against their
  physical case, `verified: true`.
- **Cover/J-card + window variant**: same base dimensions plus a 40x40mm
  rounded-rect (1mm radius) cutout on the *right* side, 10.3mm from the
  right fold line and 3.45mm from the bottom. User-confirmed against their
  physical case, `verified: true`.
- Built-in templates can be edited but not deleted.
- **New built-in templates reach existing installs via
  `registry.sync_builtin_templates()`, called once from `main()` on every
  app start (before `MainWindow` is constructed).** The per-user
  `templates.json` is only ever seeded from the bundled `defaults.json`
  *once*, on first run (`_ensure_user_file()`) — it does not pick up later
  additions to `defaults.json` on its own, so upgrading the app and
  launching the new exe used to leave existing users stuck without any
  built-in template added since their `templates.json` was first created
  (this was being worked around by hand-editing the live file after every
  template addition, until this routine replaced that). The sync is
  strictly additive and matches by `name` — it appends any bundled
  built-in template whose name isn't already present among the user's
  built-ins, and never touches an existing entry, so a built-in the user
  edited via the Template Manager is never silently reverted. It is
  idempotent and safe to run unconditionally on every start (a no-op once
  everything bundled is already present).
- **User-defined templates can also carry pre-made layers.** `DiscTemplate`/
  `CoverTemplate.items` is a `list[dict]`, empty by default, in the exact
  `item_to_dict()` shape `.mdproj` files use. Tools > "Save as Template..."
  (`app_window._save_as_template`) prompts for a name, deep-copies the
  current page's template, fills in `items` from every layer currently on
  that page, and appends it to the registry as a new non-`builtin` template.
  File > New then recreates those layers verbatim via `item_from_dict()`
  (see `_new_design`) instead of the normal empty-page behavior — for a
  disc page specifically, a non-empty `items` list means
  `seed_disc_defaults()` is *skipped entirely*, since the saved snapshot
  already includes (or deliberately omits) the triangle+label. A
  shape-only template (`items == []`) behaves exactly as before.

A new disc page auto-seeds an editable "▲ INSERT THIS END" triangle+label text
pair (only on New, not on Open, and only when the chosen template has no
saved `items` of its own) — the conventional MiniDisc insertion mark.
`seed_disc_defaults()` centers this pair on `template.width_mm` specifically,
not `sceneRect().width()` — the scene rect is wider than the disc shape on
the disc+slider variant, and centering on the whole scene rect would pull
the triangle/label off the actual disc.

## Architecture notes (read before touching these areas)

**i18n: real Qt tr()/QTranslator, not a homegrown dict.** Every user-facing
string in the UI-building code is wrapped in `self.tr("...")` (or, in the two
places outside a QObject method -- `project.py`'s `metadata_menu_entries()`
and `layers_panel.py`'s module-level `_label_for()` -- in
`QCoreApplication.translate("Context", "...")`). This matters because
`pyside6-lupdate` (Qt's string-extraction tool, works fine against Python
source, just needs `-extensions py`) does purely static, literal-string
scanning: `tr()`/`translate()` calls MUST have the literal string directly in
the call, never through an indirection like a custom `_()` wrapper or a
variable, or lupdate won't see it. **Every language listed in
`i18n.AVAILABLE_LANGUAGES` needs this redone** (currently `pl` and `ja`) --
regenerating after adding/changing translatable strings, per language:
```
.venv/Scripts/pyside6-lupdate.exe -extensions py -recursive src/mdtools -ts src/mdtools/i18n/mdtools_pl.ts
.venv/Scripts/pyside6-lupdate.exe -extensions py -recursive src/mdtools -ts src/mdtools/i18n/mdtools_ja.ts
```
then fill in any new `<translation type="unfinished"></translation>` entries
in *each* `.ts` and recompile *each*:
`.venv/Scripts/pyside6-lrelease.exe src/mdtools/i18n/mdtools_pl.ts -qm src/mdtools/i18n/mdtools_pl.qm`
(and the same for `mdtools_ja.ts`/`.qm`). Adding a brand new language
instead: add its code + display name to `i18n.AVAILABLE_LANGUAGES` (the
Help > Language menu builds itself from that dict, no other UI wiring
needed), run `pyside6-lupdate` against a not-yet-existing `mdtools_<code>.ts`
path to create it fresh (every string comes back `unfinished`), translate,
then `pyside6-lrelease` to compile the `.qm` -- and add
`--add-data "src/mdtools/i18n/mdtools_<code>.qm;mdtools/i18n"` to both
`scripts/build_windows.ps1` and `scripts/build_linux.sh` (packaging's own
`pyproject.toml` `package-data` entry is a `*.qm` glob, so *that* side picks
up a new language automatically -- only the PyInstaller `--add-data` flags
need a matching new line per language).

Language switching is **restart-required, not live**: selecting a language
persists the choice and shows a message asking the user to restart -- there's
no `changeEvent`/retranslate-in-place handling anywhere, so already-built
widgets keep showing whatever language was active when they were constructed.
`main.py` installs the translator (via `i18n.install_translator`) once,
before `MainWindow` is constructed. Live in-place retranslation was
considered and deliberately skipped as too large for what it buys --
every panel/dialog would need a `retranslate()` method re-running all its
`self.tr(...)` calls, wired into `changeEvent`, for a purely cosmetic
convenience. The low-cost compromise actually implemented: the
language-changed message box (`_on_language_selected`) now has an
explicit **"Restart Now"** button (alongside "Later") that calls
`MainWindow._restart_app()` -- relaunches MDTools as a brand-new process
via `QProcess.startDetached()`, then calls `QApplication.instance().quit()`
on this one. `_restart_app()` branches on `sys.frozen` (set by PyInstaller)
because `QProcess.startDetached(program, arguments)`'s `arguments` must
**not** include the program name itself (unlike the C `argv[0]`
convention): a frozen build's `sys.executable` already **is** the
program, so `sys.argv[1:]` is correct there, while a plain `python -m
mdtools.main` launch needs the *full* `sys.argv` passed as arguments
(`argv[0]` there is the script path python.exe itself needs, not a
duplicate program name). Tests faking this button flow patch
`QMessageBox.exec`/`clickedButton()` rather than the old
`QMessageBox.information` (a real, un-faked `QMessageBox.exec()` blocks
forever under `QT_QPA_PLATFORM=offscreen` -- see the general gotcha on
this further below) -- see `test_language_menu.py`'s
`test_language_changed_dialog_offers_a_restart_now_button`,
`test_clicking_restart_now_calls_restart_app`, and the two
`test_restart_app_*` tests (frozen vs. not), the latter of which fake
only `QProcess.startDetached`/`QApplication.quit`, deliberately *not*
`QApplication.instance()` itself -- replacing that wholesale breaks
pytest-qt's own plugin, which calls `instance().processEvents()` around
every test.

The language *setting* is stored in `mdtools/i18n/__init__.py`'s
`_settings()`, which deliberately does **not** use plain `QSettings()`
(Windows native-registry format) -- that requires
`QApplication.organizationName` to be set, and setting it changes
`QStandardPaths.AppConfigLocation` (adds an extra folder level), which would
silently relocate `templates.json` away from where
`templates/registry.py` has always read/written it, "losing" any
user-customized templates. Instead it builds an explicit
`QSettings(path, IniFormat)` using that same `AppConfigLocation` directory,
sidestepping organizationName entirely. **Never add
`app.setOrganizationName(...)` without checking this.**

**`install_translator()` installs *two* separate `QTranslator`s, not
one -- a standard `QDialogButtonBox` button (e.g. "Close") was reported
staying in English under Polish.** `mdtools_<code>.qm` (this package's
own compiled translation) only ever covers strings this app's own code
passes through `self.tr(...)`/`QCoreApplication.translate(...)` --
`QDialogButtonBox.StandardButton`'s built-in labels ("Close", "Cancel",
"OK", "Yes", "No", ...) are Qt's *own* strings, translated by Qt's *own*
`qtbase_<code>.qm`, shipped inside the PySide6 wheel itself
(`PySide6/translations/`, located via `QLibraryInfo.path(QLibraryInfo
.LibraryPath.TranslationsPath)`, not this package's own directory).
Installing only the app's own translator therefore left every Qt
standard-button label in English regardless of the selected language --
not a partial-coverage bug in `mdtools_pl.ts`/`mdtools_ja.ts` (neither
file has ever needed a `<source>Close</source>` entry; it isn't this
app's string to translate). The fix keeps a second global,
`_active_qt_translator`, alongside the existing `_active_translator` --
same "must stay alive for the life of the app or it's silently garbage
collected" reasoning as the original. `scripts/build_windows.ps1`/
`build_linux.sh` now also `--add-data` `qtbase_pl.qm`/`qtbase_ja.qm` from
wherever `QLibraryInfo.path(...)` resolves at build time (queried
dynamically via a Python one-liner, not a hardcoded `.venv` path, since
PySide6's own install layout can shift between versions/platforms) into
`PySide6/translations` inside the frozen bundle -- unverified against an
actual frozen build (this was fixed and confirmed working in dev mode via
`python -m mdtools.main` only), but is the correct relative location for
`QLibraryInfo.path()` to find them if PyInstaller's own PySide6 hook
doesn't already bundle Qt's translations directory by default.


**Selection frame is a screen-aligned box, not tilted with the item — a
deliberate tradeoff, not a bug.** `canvas/view.py::_handle_geometry` always
returns an axis-aligned bounding box in scene coordinates (like PowerPoint's
selection box for a rotated shape), and resize handles/edges (corner = both
axes, edge midpoint/line = single axis) measure drag distance directly in
raw scene coordinates rather than un-rotating into the item's own local axes
first. This was an explicit user choice (over "bake rotation into geometry
on release" and "leave the old tilted-frame model alone") after being shown
the tradeoff: at rotation multiples of 180° this behaves perfectly; at other
angles (notably exactly 90°) a screen-horizontal edge drag ends up growing
the item's local-x scale factor, which then renders as a *vertical*
on-screen change, since the local x-axis is no longer horizontal on screen.
This is intentional, not something to silently "fix" without re-confirming
— see the test names/comments in `tests/test_view_handles.py`.

**The selection frame sizes to a pixmap layer's actual visible (opaque)
content, not its full `boundingRect()`.** Clip Layers/Bake Layers never
crop a pixmap's own dimensions -- they make everything outside the
printable area *transparent* (see the Clip Layers/Bake Layers notes
above), so `boundingRect()` on a clipped layer still reports its old,
pre-clip extent, most of which is now empty. `canvas/items.py`'s
`opaque_content_rect(item)` returns the tight bounding rect of a
`QGraphicsPixmapItem`'s non-fully-transparent pixels instead (any other
item type has no "transparent padding" concept, so it's just
`item.boundingRect()` there); `_handle_geometry()` uses this instead of
`item.boundingRect()` for what gets *drawn and hit-tested* as the
frame/handles -- deliberately **not** for `transformOriginPoint()`
(the rotate/scale pivot stays exactly as before; only what you see and can
grab changes). Computed via Pillow's `Image.getbbox()` on the alpha
channel (C-optimized, not a manual per-pixel Python scan -- this needs to
stay fast even for a whole page baked at `BAKE_DPI`) over a `constBits()`
memoryview (no PNG encode/decode round trip), and cached on the item
itself keyed by `pixmap.cacheKey()` (`CONTENT_RECT_ROLE`) since
`drawForeground()` calls this on every repaint while something's selected
-- recomputing it from scratch every frame would visibly stutter. The cache
invalidates itself automatically whenever the pixmap is swapped (a
different pixmap always gets a different `cacheKey()`), so a Clip
Layers/Bake Layers re-run, or `SetPixmapCommand`'s undo/redo, always sees
the right rect with no extra invalidation code needed anywhere.

**Rasterizing a shape in Clip Layers must carry its selected state over to
the replacement item, or the tight-frame fix above never actually gets
seen.** An image being clipped keeps its selection for free --
`SetPixmapCommand` swaps the pixmap on the *same* item, so whatever was
selected stays selected. A rectangle/ellipse being clipped does not: it's
replaced outright by a brand new `QGraphicsPixmapItem`
(`_replacement_pixmap_item()`, since a plain shape item can't hold a
pixmap), and a freshly-constructed item is never selected by default. A
user reported this as "the tight frame fix doesn't work for rectangles" --
what was actually happening was that a selected rectangle lost its
selection (and so its selection frame) the instant Clip Layers ran, so the
opaque-content-tightened frame was never even drawn for it in practice
until the user clicked to re-select -- at which point it *did* draw
correctly, just leaving the impression that clipping a rectangle "loses"
or "doesn't fix" its frame. `_replacement_pixmap_item()` now calls
`new_item.setSelected(item.isSelected())` right after constructing the
replacement, so a rectangle that was selected going into Clip Layers stays
selected (and correctly tight-framed) coming out, exactly like an image.

**Every item in this app is a small subclass (`DesignTextItem`/
`DesignRectItem`/`DesignEllipseItem`/`DesignPixmapItem` in `canvas/
items.py`), not the plain `QGraphicsTextItem`/`QGraphicsRectItem`/etc.,
specifically to suppress Qt's own default selected-state decoration.**
Even after the two fixes above tightened `_handle_geometry()`'s corners to
`opaque_content_rect()`, a selected, clipped layer still visibly showed an
*old-size* frame -- because that frame wasn't ours: `QGraphicsItem`'s base
`paint()` (shared by text/rect/ellipse/pixmap items alike) draws its own
dashed rectangle around the plain `boundingRect()` whenever
`QStyleOptionGraphicsItem.state` has `QStyle.State_Selected` set, entirely
independent of whatever `DesignView.drawForeground()` draws on top. There's
no per-instance way to opt out of that in Qt short of overriding `paint()`,
which requires an actual Python subclass -- so `_NoDefaultSelectionDecoration`
(a mixin) strips `State_Selected` from a *copy* of the style option before
delegating to `super().paint()`, and the four `Design*Item` classes apply
it. Every item-construction site in `scene.py` (`add_text`,
`add_rectangle`, `add_ellipse`, `_add_pixmap_item`,
`_replacement_pixmap_item`, `plan_bake_layers`) uses these instead of the
plain Qt classes; every `isinstance(item, QGraphicsRectItem)`-style check
elsewhere (project_io.py, properties_panel.py, commands.py, ...) keeps
working completely unchanged, since a subclass instance still satisfies
`isinstance` against its plain Qt parent class.
`DesignView.drawForeground()` now also draws its own dashed polygon
connecting the (already-tight) corners, so there's an actual continuous
frame outline again, not just floating corner handles with nothing
suppressing the stale one underneath.

**A rasterized/baked layer's rotate/scale pivot is re-anchored to its own
visible content, not the raw pixmap's full (possibly mostly-transparent)
center.** `_replacement_pixmap_item()`/`plan_bake_layers()` both first
position/scale/rotate the new item anchored at its plain
`boundingRect().center()` (the already-proven-correct math from the
sections above), then call `DesignScene._repivot_to_opaque_content(item,
sx, sy)` to move `transformOriginPoint()` to `opaque_content_rect(item)
.center()` instead -- without shifting any already-correctly-placed
pixels. It does this by reading where the *new* anchor point currently,
correctly, maps to in scene space (`item.mapToScene(content_origin)`,
which works fine even before the item is added to a scene) under the old
anchor, then re-solving `pos()` for that same scene point under the new
one. Skipping this (which the tight-frame fix initially did) left rotation
pivoting around a point that could be far outside the shape's actual
visible extent once most of it had been clipped away -- reported as "the
pivot origin point is incorrect after clipping." Two calls are needed
because `set_item_scale()` reads `transformOriginPoint()` internally to
build its transform matrix -- just calling `setTransformOriginPoint()`
again wouldn't retroactively move the already-baked matrix.

**Undo/Redo + Copy/Cut/Paste.** Scope is deliberately canvas/layer edits
only, per explicit user choice — Project Metadata dialog and Template
Manager edits are NOT undoable. `commands.py` holds `QUndoCommand`
subclasses: `AddItemCommand`, `DeleteItemsCommand`, `SwapZCommand` (reorder),
`TransformCommand` (mouse rotate/scale — deliberately never merges: a full
press-drag-release always pushes exactly once, so there's nothing *within*
one gesture to coalesce, and merging across two separate, completed drags
would be wrong -- see `MoveItemsCommand` below for exactly that bug),
`MoveItemsCommand` (native drag-move *and* arrow-key nudging, both
merge-coalescing consecutive moves of the same item set into one undo
step), and `PropertyEditCommand` — a generic merge-coalescing command used
by every Properties-panel field (and, by the Layers panel's "Rename..."
button, `set_item_name` from `canvas/items.py`) so a burst of spinbox
ticks/typing collapses into one undo step instead of one per tick.

**Both merge-coalescing commands above (`MoveItemsCommand`,
`PropertyEditCommand`) once merged far too eagerly — two entirely separate,
deliberate actions (two distinct mouse drags; two distinct spinbox edits
done minutes apart) would silently collapse into a single undo step
whenever nothing else happened to get pushed onto the stack in between.**
A single Ctrl+Z then undid *both* actions at once, with no way to undo just
the most recent one — reported as "undo doesn't work" when moving an
object. Qt's own merge machinery has no concept of "was this really a
continuation of the same gesture" -- it only checks `id()`/`mergeWith()`,
so that has to be tracked explicitly by each command:
- `MoveItemsCommand.mergeable` (checked as `other.mergeable` inside
  `mergeWith` — only the *incoming* command's flag matters, never `self`'s,
  or a hold's own first tap would refuse to let its later repeats merge
  into it). `_commit_native_move_command` (native mouse drag) always
  constructs its command with `mergeable=False`, since a completed drag
  never represents a continuation of anything. `_nudge_selected` (arrow
  keys) passes `mergeable = event.isAutoRepeat() and <same key still held>`
  — only a genuine OS auto-repeat of the same held key counts as a
  continuation; a fresh, isolated tap does not, even of the same key.
- `PropertyEditCommand` has no equivalent "isAutoRepeat" signal to key off
  of (a spinbox tick and a deliberate re-edit look identical at the Qt
  event level), so it instead uses a short, sliding time window
  (`PROPERTY_EDIT_MERGE_WINDOW_MS`, via a `QElapsedTimer` restarted on
  every successful merge) — long enough to cover a real burst of ticks/
  keystrokes, short enough that coming back later to edit the same field
  again starts a fresh undo step.

Regression coverage: `test_undo_redo.py`'s
`test_two_separate_native_drags_are_each_independently_undoable`,
`test_two_separate_arrow_key_taps_are_each_independently_undoable`,
`test_held_arrow_key_repeats_still_merge_into_one_undo_step`, and
`test_property_edits_separated_by_a_pause_do_not_merge` (the last one
monkeypatches `PROPERTY_EDIT_MERGE_WINDOW_MS` down to keep the test fast
rather than actually sleeping past the real default).

`MainWindow` owns a
`QUndoGroup` (`self.undo_group`) plus one `QUndoStack` per project, swapped
via `_reset_undo_stack()` on New/Open — the Edit menu's Undo/Redo actions
are created once from the *group* (`createUndoAction`/`createRedoAction`)
specifically so they survive that stack-swap; actions created directly from
a stack instance would go stale. `DesignView` and `PropertiesPanel` each get
an `undo_stack` attribute (default `None`, set by MainWindow) so both remain
usable standalone/in tests without any undo history. Copy/Cut/Paste
(`clipboard.py`) reuses `project_io.py`'s `item_to_dict`/`item_from_dict` so
a paste is a true clone via the same (de)serialization used for save/load —
including pasting across pages (disc <-> cover). Edit menu's "Delete" action
deliberately has **no keyboard shortcut** — `DesignView.keyPressEvent`
already handles Delete/Backspace while the canvas has focus, and a
window-level shortcut on top of that would double-fire (two deletes, two
undo entries for one press).

**Export must deselect *before* hiding layers, not after.** PNG/SVG export
render the scene directly (`scene.render(...)`), which paints each item's
own selected-state decoration (Qt's default dashed outline) exactly like
on-screen painting — exporting while something is selected would otherwise
bake that outline into the file. `DesignScene.deselected_for_export()`
(mirrors `hidden_for_export()`) fixes this, but **context-manager order
matters**: always `with scene.deselected_for_export(),
scene.hidden_for_export(...):` — deselect first, hide second. Reversing
that silently breaks restoration, because Qt auto-deselects an item the
instant it's hidden, so if `hidden_for_export` enters first,
`deselected_for_export` captures an already-empty selection with nothing
left to restore afterward.

**File > Print... (`mdtools/printing.py` + `panels/print_dialog.py`) lays
N copies each of both design pages out on one physical sheet (A4/Letter)
and sends it to a real printer via `QtPrintSupport`.** `PrintDialog`
renders the disc and cover scenes once, via the exact same `render_scene_to_image()`
`io/png_export.py` already uses for Export Print PNG (so print artwork can
never diverge from what that export would produce), then shows both as
draggable `QGraphicsPixmapItem`s (`ItemIsMovable | ItemIsSelectable`, Qt's
own native drag -- no need for this app's own resize/rotate handle
machinery, since printing only ever needs repositioning, not scaling) on a
plain `QGraphicsView` page preview. `_PageView.resizeEvent` calls
`fitInView()` on every resize so the whole page is always visible
regardless of the dialog's size -- the scene's own unit scale
(`PrintDialog.PREVIEW_PX_PER_MM`, purely a display constant) only matters
for translating a dragged item's `pos()` back to millimeters, not for
on-screen sizing.

**Each label's true physical size is recovered from its rendered image's
own pixel count and DPI, never from scene coordinates.**
`printing.image_physical_size_mm(image, dpi)` returns `image.width() /
dpi * 25.4` (and the same for height) -- this losslessly inverts
`render_scene_to_image()`'s own `width_px == width_mm * dpi /
screen_dpi()`-based construction, so it stays correct even though a
project's scene coordinates are frozen in whatever Screen DPI was active
when it was built (see the DPI-settings note above on why an open
project doesn't rescale live). Deriving physical size any other way --
e.g. reading `scene.sceneRect()` and converting via the *current*
`screen_dpi()` -- would silently drift the moment Window > Settings'
Screen DPI is changed after a project is already open. Note that the
recovered size is a few mm larger than the template's own
`width_mm`/`height_mm` on both axes -- `render_scene_to_image()` renders
the *whole* `sceneRect()`, which every template outline builder pads by a
small fixed margin around the actual cut shape (see `_build_disc_outline`/
`_build_cover_outline`'s `setSceneRect(QRectF(-10, -10, w + 20, h + 20))`)
-- so this is exactly the same physical footprint Export Print PNG's own
output image already has, not a bug introduced by printing.

**The actual print -- `printing.print_placements()` -- must run with
`printer.setFullPage(True)` already set by the caller**, so the printer's
own `(0, 0)` is the physical page's top-left corner, matching the
dialog's own page-relative placement coordinates; otherwise Qt's default
printer margins would offset everything away from where the preview
showed it. Scaling the `QPainter` by `printer.resolution() / 25.4` up
front makes every subsequent logical unit equal to one millimeter, so
each placement's `drawImage()` call can use its plain `(x_mm, y_mm,
width_mm, height_mm)` rect directly -- Qt's own image scaling handles
turning the source raster into that exact physical size regardless of
the printer's chosen resolution.

Grayscale/color and, when grayscale, brightness/contrast reuse
`mdtools.grayscale.apply_grayscale()` -- the same function the canvas
preview and Export Print PNG (Grayscale) already call through -- so
`PrintDialog`'s own preview can never look different from what actually
prints. Unlike Export Print PNG (Grayscale), there's no separate
pre-print adjustment dialog: the checkbox and sliders live directly in
`PrintDialog` (via `QFormLayout.setRowVisible()` -- plain
`setVisible(False)` on the slider alone leaves its label showing, see the
`QFormLayout` gotcha below), and only get written back onto
`project.grayscale_adjustment` if grayscale was actually checked at the
moment Print succeeded -- printing in color leaves whatever adjustment
was already saved untouched, even if the (then-irrelevant, hidden)
sliders were touched first.

**The Copies spinbox re-packs a fresh grid on every change, via
`printing.build_copies_layout()` -- a pure function, no Qt widget
dependencies, exactly like `canvas/scene.py`'s own `plan_clip_layers()`/
`plan_bake_layers()` separation of "compute the plan" from "the caller
turns it into UI state."** Each label's grid is a simple row-major grid
(`printing._pack_grid()` -- not a general bin-packer; MDTools' two label
shapes are each a single fixed-size rectangle, so a grid already uses the
page about as efficiently as one would, at a fraction of the complexity).
`PrintDialog._relayout_copies()` calls it every time the Copies spinbox or
Page Size combo changes and discards any manual dragging done before that
point -- there's no way to know how a changed copy count should reuse a
previous, different-count arrangement, so it doesn't try to.

**How the disc grid and cover grid relate to each other -- stacked, or
side by side -- is itself searched, not fixed.** `printing._ARRANGEMENTS`
tries, in order: `"vertical"` (the disc block directly above the cover
block, each block using the *entire* printable width --
`_attempt_vertical_blocks()`), then `"horizontal_cover_primary"` /
`"horizontal_disc_primary"` (one label's grid narrowed into a tight
column so the other's grid can sit in the leftover width beside it --
`_attempt_horizontal_blocks()`/`_search_horizontal_split()`).
`build_copies_layout()` tries every arrangement at a given rotation level
before escalating to more rotation (see below) -- changing which side a
block sits on is a smaller, less surprising change than rotating a
label's artwork sideways, so it's preferred first. This exists because
real MiniDisc cover cards are wide enough that a single upright column
already consumes most of the printable width in the "vertical" model,
leaving a usable strip beside it completely empty -- the exact space a
`"horizontal"` arrangement reclaims for the disc grid instead.

**Rotating a label 90 degrees is tried only as a fallback to make a
requested copy count fit -- never as a "more compact anyway" default.**
(Explicit user correction mid-implementation: an earlier version picked
whichever orientation minimized total height, which rotated even a
single copy of a label that's taller than it is wide, for no visible
benefit, purely because rotating it was marginally more compact -- a
surprising, unwanted side effect of just bumping the copy count.)
`printing._ROTATION_COMBOS` tries `(disc_rotated, cover_rotated)` in a
fixed priority order -- `(False, False)` first, then rotating just the
disc, then just the cover, then both -- and `build_copies_layout()` takes
the *first* combination that fits, not the smallest. This guarantees the
natural, upright layout is always used whenever it already fits at all,
regardless of whether some rotated combination would technically be a
few mm more compact; rotation only ever changes the printed result when
the plain layout genuinely doesn't fit. `PrintLayoutError` is raised only
when none of the four combinations fit.

**Each `_LabelItem` owns its own rotation state independently -- rotation
is not a single flag shared by every copy of a label type.**
`_LabelItem.rotated` (a plain instance attribute, seeded from whichever
grid it was created from) plus `width_mm`/`height_mm` *properties* that
report the item's current, rotation-aware footprint (swapped while
`rotated`), and `oriented_raw_image()`, which physically rotates the
*canonical, always-unrotated* `raw_image` on demand
(`QImage.transformed(QTransform().rotate(90))`) rather than baking the
rotation into a shared per-type cache the way an earlier version did.
This was a deliberate redesign, not the original design: the first
version cached one shared "oriented" image per label *type*
(`self._disc_oriented_raw`/`_cover_oriented_raw`), which only supported
rotating *every* copy of a type together. That became untenable once
individual copies needed independent rotation (see the right-click
feature below) -- baking rotation into the pixel data once, per item,
still means every downstream step (grayscale/brightness/contrast, the
preview pixmap, and `printing.print_placements()`'s own paint routine)
stays completely unaware rotation is even a concept; it just sees an
image and a width/height that happen to already be swapped. A 90-degree
rotation is exact (every source pixel maps onto exactly one destination
pixel), so this loses no detail, unlike a rotation at an arbitrary angle
which would need to resample. `PrintDialog._update_displayed_images()`
still caches by `(id(item.raw_image), item.rotated)` *within* a single
call, so N identical copies in the same orientation only get
oriented/grayscaled once per Grayscale/slider change, not once per copy.

**Right-clicking a label rotates that one copy 90 degrees --
`_LabelItem.contextMenuEvent()`.** Deliberately not a
`mousePressEvent`/`RightButton` check: `contextMenuEvent` is the idiomatic
Qt virtual for a `QGraphicsItem`'s right-click, delivered automatically by
the view without any risk of it fighting with `ItemIsMovable`'s own
left-button drag handling. Since `QGraphicsItem` isn't a `QObject`, it has
no signals to emit -- `on_rotated` is a plain callable attribute, set by
`PrintDialog._make_item()` to the dialog's own `_update_displayed_images`,
called after toggling `rotated` so the freshly-rotated pixels/scale show
immediately (and so any grayscale/brightness/contrast currently active
gets reapplied to the new orientation too).

**A copy count that a simple grid can't auto-arrange is never treated as
a hard, blocking error -- three rounds of explicit user correction.**
First: an earlier version's `PrintLayoutError` message interpolated the
raw, English-only exception text (`str(error)`) into an otherwise-
translated Polish/Japanese string, producing a visibly mixed-language
message -- reported directly ("mixed polish and english - this is a
bug"). Second: a user manually proved 4 copies fit on A4 by rotating
individual labels and dragging them tight, while the app's own
grid-packing algorithm reported that count as outright impossible and
reverted the Copies spinbox rather than let the user attempt it. Third,
after the vertical/horizontal arrangement search above and the
`crop_to_template_bounds()` optimization below both landed and the same
4-copy case started fitting *automatically*: the user pointed out the
even deeper fix, that "transparent pixels are not printable," which is
what `crop_to_template_bounds()` actually acts on. Together, the second
and third reports point at the same root cause: proving a simple
rectangle-grid heuristic *can't* find an arrangement is not the same as
an arrangement being genuinely impossible -- both a smarter arrangement
search and a tighter, physically-honest footprint per label closed most
of that gap; freeform manual placement (especially with per-copy
rotation, see above) can still beat the automatic result in edge cases,
which is what the graceful degradation below is for.

**`printing.crop_to_template_bounds()` packs each label using its true
physical cut-shape footprint, not the padded render.** Every template
outline builder pads `sceneRect()` with a small fixed transparent margin
around the actual cut shape (e.g. `_build_disc_outline`'s
`setSceneRect(QRectF(-10, -10, w + 20, h + 20))`) -- purely a rendering/
selection-outline convenience (see the outline-margin note above), with
*no* physical cutting significance. Packing against the full padded
render (as `image_physical_size_mm()` alone reports) wastes that margin
*twice* between every pair of adjacent copies. `crop_to_template_bounds()`
crops a `render_scene_to_image()` output down to `scene.template_clip_path()
.boundingRect()` (mapped into the same device-pixel space
`render_scene_to_image()` itself uses) -- the same path that function
already clips all painting to, so nothing printable is ever lost, only
the guaranteed-transparent margin outside it. `PrintDialog.__init__` runs
every render through this crop before computing `_disc_size_mm`/
`_cover_size_mm`, so every downstream packing decision already reflects
each label's real physical size -- deliberately *not* an arbitrary
opaque-content bounding box (e.g. via Pillow's `getbbox()`, the technique
`canvas/items.py`'s `opaque_content_rect()` uses for the selection-frame
tightening feature): that would depend on what a particular project
happens to have *printed* within the label, which has no relationship to
where the physical material actually gets *cut* -- packing two labels
tighter than their real cut shapes would make adjacent pieces overlap
when cut from the same sheet, a genuine physical-accuracy bug, not an
optimization. `MARGIN_MM` (page edge margin, now 5mm) and
`printing.COPY_GAP_MM` (spacing between copies, now 3mm) were also both
reduced from their original values as part of the same fix -- explicitly
"a layout choice, not a measured spec" (compare
`DiscTemplate.slider_gap_mm`'s own docstring), so free to tighten now
that real cover cards are large enough relative to A4/Letter that every
extra margin/gap mm matters for how many copies fit.

The fix, in `PrintDialog._relayout_copies()`: a `PrintLayoutError` from
`build_copies_layout()` is now just the caller's signal to fall back to
`_layout_with_overflow_at_corner()` -- `printing.max_copies_that_fit()`
finds how many copies *do* pack automatically, those get the real grid
via a second `build_copies_layout()` call, and every copy beyond that is
placed at the page's top-left corner (`(MARGIN_MM, MARGIN_MM)`), stacked
directly on top of each other/the grid. `QMessageBox.warning()` then
explains the situation in one fully-translated, self-contained string --
no exception text embedded anywhere, which is what actually fixes the
mixed-language bug: the underlying `PrintLayoutError`'s own message
remains plain, internal-only English (nothing wrong with that now that
nothing user-facing ever reads `str(error)`). The Copies spinbox is never
reverted -- whatever the user asked for is exactly what's honored, with
placement quality being the only thing that degrades gracefully. Overflow
copies inherit the fitting grid's own rotation decision as a starting
point (not "always upright"), since it's at least as likely to be useful
as any other default, and it's one right-click away from being changed
per-copy regardless.

Regression coverage constructs a real (non-native, PDF-targeting)
`QPrinter` to prove `print_placements()` actually paints and writes real
output -- see `test_printing.py`/`test_print_dialog.py`'s
`_make_fake_printer()` helper, which subclasses `QPrinter` to force
`OutputFormat.PdfFormat` + a temp file path instead of a real system
printer, combined with monkeypatching `QPrintDialog.exec` to skip the
actual modal system dialog. Note: constructing a real `QPrinter` under
`QT_QPA_PLATFORM=offscreen` in this environment prints a noisy "Windows
fatal exception" / thread-stack dump from Python's `faulthandler` to
stderr -- confirmed via direct reproduction that this is an internally
Qt-handled first-chance COM exception (querying the OS's native print
subsystem with no real printer configured), not an actual crash: the
test still completes and passes normally afterward. Don't mistake that
dump for a real failure when reading print-test output.

**"Export PDF..." (next to "Print...") saves exactly what the page
preview currently shows -- same copies, same dragged positions, same
grayscale/color state -- straight to a standalone PDF file, with no
system printer or print dialog involved at all.** `PrintDialog._on_export_pdf()`
reuses `printing.print_placements()` completely unchanged: a `QPrinter`
aimed at a PDF file (`setOutputFormat(QPrinter.OutputFormat.PdfFormat)` +
`setOutputFileName(path)`) paints through the exact same `QPainter` calls
as one aimed at a real printer, so Export PDF's output can never visually
diverge from what Print... would produce for the same on-screen state --
the same "two surfaces must never diverge" reasoning as Clip
Layers/Export PNG reusing each other's paint code elsewhere in this app.
"High quality" here just means reusing the already-DPI-rendered artwork
(`self._disc_raw`/`_cover_raw`, rendered once at Window > Settings'
Default Export DPI) every other print/export path in this dialog already
uses -- there's no separate, heavier render step. `_new_printer()` factors
out the page-size/full-page setup shared by both `_on_print()` and
`_on_export_pdf()`, and `_maybe_save_grayscale_adjustment()` factors out
the "only persist brightness/contrast if Grayscale was actually checked"
rule so both entry points apply it identically. Unlike Print..., a
successful export does *not* close the dialog (`self.accept()` is never
called) -- exporting is a lightweight side action, not a terminal one,
so the user can keep adjusting the layout or also hit Print... afterward
without reopening File > Print... from scratch.

**"Export PNG..." (next to Export PDF...) is the same idea, targeting a
standalone high-DPI PNG instead of a PDF, via a new
`printing.render_page_to_image()` rather than reusing `print_placements()`
directly -- a `QPrinter` needs an actual PDF/native output format, but a
plain image has no such device to paint onto, so this paints onto a
`QImage` sized to the page at the same DPI everything else in this
dialog uses (`self._dpi`) instead.** It shares the *exact* per-placement
paint logic with `print_placements()` (scale the painter to mm-per-unit,
then `drawImage()` into an `(x_mm, y_mm, width_mm, height_mm)` rect) so
the three export paths -- Print, Export PDF, Export PNG -- can never
visually diverge from each other for the same on-screen state. **The
page background is left fully transparent, deliberately not painted
white**, per explicit user request ("The 'paper' should be transparent
not white of course") -- there's no physical paper being represented in
a PNG the way there is for an actual print or a PDF page, so painting
one in would bake in an assumption (opaque white backing) that may not
match whatever the user actually prints this PNG onto later. This is the
same transparent-by-default convention Export Print PNG already uses for
everything outside a single label's own cut outline. Button order in the
dialog (`Export PNG...`, `Export PDF...`, `Print...`) was chosen to keep
the two non-terminal export actions adjacent, per explicit request ("make
Export PNG button close to export PDF").

**`panels/print_dialog.py`'s `PrintDialog`/`_LabelItem`/`_PageView` were
refactored into a shared `_PrintDialogBase` once a second, structurally
different dialog (`MultiprintDialog`, below) needed the exact same page
preview + grayscale controls + Print/Export PDF/Export PNG machinery.**
`_PrintDialogBase` owns everything that doesn't depend on *how* items get
onto the page: the page-size combo, `_build_grayscale_controls()`/
`_build_page_view()`/`_build_action_buttons()` (called by each subclass's
own `__init__`, in whatever order suits its own extra controls -- e.g.
`PrintDialog`'s Copies spinbox needs to sit in `_options_form` before the
grayscale controls, `MultiprintDialog`'s Add/Delete row the same), plus
every handler (`_update_displayed_images`, `_build_placements`,
`_new_printer`, `_on_print`/`_on_export_pdf`/`_on_export_png`,
`_make_item`). Subclasses need only implement `_all_items()` (which
items currently exist -- `PrintDialog`'s `_disc_items + _cover_items`
list-of-copies vs `MultiprintDialog`'s single flat `_items` list) and
`_maybe_save_grayscale_adjustment()` (see below). This mirrors the same
"factor out the part that must never visually diverge between two
callers" reasoning already used throughout this file (Clip Layers/Export
PNG sharing paint code, Print/Export PDF/Export PNG sharing
`print_placements()`'s logic) -- here applied to two whole *dialogs*
rather than two render call sites.

**MultiprintDialog -- launched from the startup screen's "Multiprint..."
button (`panels/startup_dialog.py`), not from an already-open project --
combines disc/cover artwork from several *different* saved `.mdproj`
files onto one physical page.** Per explicit request, it starts
completely empty and has no Copies/auto-layout concept at all: "Add..."
(`_on_add`) browses for a `.mdproj` file, `load_project()`s it, renders +
`crop_to_template_bounds()`s its disc and cover pages exactly like
`PrintDialog` does, and adds both as new, independently draggable/
right-click-rotatable `_LabelItem`s -- dropped at the page's top-left
corner (`(MARGIN_MM, MARGIN_MM)`, in *preview* px), the same "no automatic
arrangement, just place it and let the user drag it into position"
convention `PrintDialog._layout_with_overflow_at_corner` already
established for copies a grid can't auto-fit. "Delete" (`_on_delete`)
removes whichever item(s) are currently selected
(`self.page_scene.selectedItems()`, native Qt click-to-select via
`ItemIsSelectable` -- no custom selection UI needed) -- a no-op if
nothing is selected, not an error. A failed `load_project()` (unreadable/
malformed file) shows `QMessageBox.critical()` (mirroring
`app_window._open_project_path()`'s own `except Exception as exc:`
handling of the exact same call) and adds nothing, rather than partially
adding a broken project's pages.

**`_maybe_save_grayscale_adjustment()` is a no-op in the base class,
overridden only by `PrintDialog`.** `MultiprintDialog` combines several
unrelated, already-saved projects loaded purely to borrow their rendered
artwork -- there is no single project it could persist a brightness/
contrast adjustment onto, and silently rewriting one of the loaded
`.mdproj` files just because Print... was clicked would modify a file the
user never asked to save, which this app never does anywhere else either.
Grayscale/brightness/contrast in `MultiprintDialog` are therefore
genuinely transient, seeded from a fresh, neutral `GrayscaleAdjustment()`
every time the dialog opens, never written back anywhere.

**Asset gallery (`assets/img`, `gallery.py`) uses a different bundling
mechanism than `defaults.json`/`mdtools_pl.qm` — deliberately, per explicit
user request not to embed image bytes into Python source.** `defaults.json`
and the compiled translation live *inside* the `mdtools` package and are
read via `importlib.resources` (works both installed and frozen, since it
goes through the package's own loader). `assets/img` sits *outside* the
package, at the repo root, so `gallery.gallery_dir()` instead branches on
`sys._MEIPASS` (set by a PyInstaller-frozen build to wherever `--add-data`
copied bundled files — `dist/MDTools/_internal/` in the onedir builds this
project uses) vs. `Path(__file__).resolve().parents[2]` in dev mode (repo
root, two levels above `src/mdtools/gallery.py`). Both `build_windows.ps1`
and `build_linux.sh` `--add-data` the whole `assets/img` directory at
`assets/img` (matching what `gallery_dir()` expects under `_MEIPASS`) — a
new image just needs to be dropped into that folder, no code changes.
Insert Asset (Tools panel) opens `AssetGalleryDialog`, which lists whatever
`gallery.list_gallery_images()` finds and inserts the chosen one exactly
like "Add Image..." (`scene.add_image(path)`), so it's a completely normal,
editable image layer afterward — undoable, saved into `.mdproj` as
base64 like any other image, no lingering tie to the gallery.

**Metadata lookup (`metadata_lookup.py`) is this app's only network
access, and deliberately the simplest possible implementation.** "Lookup
Track List..." in `MetadataDialog` (the Tools panel's Metadata...) hits the
iTunes Search API (no API key/signup, chosen explicitly over
MusicBrainz/Discogs for that reason) via plain stdlib `urllib.request` —
synchronous/blocking, not `QtNetwork`'s async `QNetworkAccessManager` —
since this is a single, occasional, user-initiated click, not a live
sync; `MetadataDialog._run_lookup()` covers each blocking call with
`QApplication.setOverrideCursor` and disables the button meanwhile so the
UI still gives feedback.

**Deliberately two separate calls, not one auto-picked "best match" —
album search results are genuinely ambiguous** (a remix/live single
sharing the album's exact title, a deluxe reissue, a tribute-album cover
version by a different artist) enough that silently auto-picking one
regularly picked the wrong release in real testing. `search_albums()`
(`/search?entity=album`) returns *all* `AlbumCandidate`s, ranked by
`_match_score()`: primarily by how well `artistName`/`collectionName`
overlap the given artist/album (case-insensitive substring, since exact
string equality would miss almost every real-world result), with
`track_count` as a **tiebreaker only** — this is what stops a 1-track
remix single from outranking the real album when both name-match equally
well, which is exactly the bug a plain name-similarity score had. If
`search_albums()` returns more than one candidate, `MetadataDialog` shows
them via a plain `QInputDialog.getItem()` picker (label format:
`"{artist} — {album} ({year}, {n} tracks)"`, enough to disambiguate
editions/pressings at a glance) rather than guessing; a single candidate
skips the picker entirely. Once a candidate (or the sole result) is
chosen, `fetch_tracks()` (`/lookup?entity=song`, by that candidate's
`collectionId`) gets the actual track listing (title + duration, sorted
by disc/track number) and release year — falling back to the search
candidate's own year if the lookup response's collection entry lacks one.
`lookup_album()` still exists as a one-shot convenience (auto-picks
`search_albums()`'s top-ranked candidate) for callers that can't offer an
interactive picker, but `MetadataDialog` itself always uses the two-call
form. Both calls can raise `MetadataLookupError` (caught by the dialog
and shown via `QMessageBox.warning`, never left to propagate/crash) for
no-match, network, and bad-response cases alike — one exception type, one
place the UI has to handle. A successful lookup **replaces** the whole
track table and overwrites Year outright, no merge/confirmation step: the
Metadata dialog only commits on OK, so Cancel is already the undo path
(Metadata edits are explicitly outside the QUndoStack's scope regardless
-- see Undo/Redo section below).

**Cover art rides along on the same lookup, and is saved in *two* places
for two different purposes.** Each `AlbumCandidate` from `search_albums()`
also carries `artwork_url` -- iTunes encodes the requested pixel size
right in the URL itself (".../100x100bb.jpg"), so `_upsized_artwork_url()`
does a plain string swap to `600x600bb` (a usable size for actual
cover/print artwork, not just a UI thumbnail; there's no dedicated "give
me a bigger size" API parameter). Once tracks are fetched,
`MetadataDialog._fetch_and_save_cover()` calls
`fetch_artwork(candidate.artwork_url)` and:
1. writes the bytes into `gallery.downloaded_covers_dir()` -- a per-user,
   writable cache (unlike the bundled `assets/img`, which especially in a
   frozen build isn't) that `gallery.list_gallery_images()` merges in
   alongside the bundled gallery. That merge is the entire mechanism
   behind "selectable from the Asset Gallery": a fetched cover needs no
   separate "add to gallery" step or any change to `AssetGalleryDialog` at
   all -- it simply becomes a file `list_gallery_images()` finds, exactly
   like the bundled logo, the moment it's saved. The filename is
   deterministic (`"{artist} - {album}.jpg"`, sanitized via
   `_sanitize_filename()` for filesystem-invalid characters), so
   re-looking-up the same album overwrites rather than accumulates
   duplicates.
2. stores the same bytes on `self._cover_art`, which flows into
   `result_metadata.cover_art` on OK -- **`ProjectMetadata.cover_art` is a
   real field, saved with the project** (`project_io.py`'s
   `_metadata_to_dict`/`_metadata_from_dict` base64-encode it exactly like
   image layers already are, under `"cover_art_base64"`, `None` when
   there's no cover). This is why reopening the Metadata dialog later
   still shows the cover: `MetadataDialog.__init__` seeds
   `self._cover_art` from `metadata.cover_art` and calls
   `_show_cover_bytes()` immediately if it's set, rather than only ever
   displaying a same-session fetch.

Cover art is treated as a bonus, never as a reason to alarm the user: a
missing `artwork_url` or a failed `fetch_artwork()` is caught and
silently skipped in `_fetch_and_save_cover()` -- no warning dialog --
since by that point the track/year lookup this button primarily promises
has already succeeded; only `search_albums()`/`fetch_tracks()` failures
surface a `QMessageBox.warning`.

**The cover preview is itself the button for overriding it
(`_CoverLabel`).** Every automatic source here guesses -- iTunes returns
whatever release its search matched, which for a reissue, a compilation or
a band with a common name is regularly the wrong sleeve -- and there was
previously no way to correct it from this dialog at all. Clicking the
picture opens a file picker; the bytes replace `_cover_art` and flow into
`result_metadata` on OK exactly as a fetched cover does. Two things it does
deliberately: it **validates by trying to load the bytes**
(`_show_cover_bytes()` returns bool) rather than trusting the extension,
because those bytes get saved into the project and later handed to
`auto_layout`/`palette`, neither of which can report back that they were
never an image; and it **only fires on a release inside the label**, so
pressing and dragging off cancels the way it does on any button. A locally
chosen file is *not* written into `downloaded_covers_dir()` -- that cache
exists so fetched art shows up in the Asset Gallery, and the user's own
file is already somewhere they chose.

**Clip Layers (Tools panel) bakes the printable-area cut into layers
themselves, rather than only affecting what export shows.**
`DesignScene.plan_clip_layers()` checks every print layer against
`template_clip_path()`: entirely outside → removed outright, whatever the
type. Partially outside → only images and rectangles get touched (there's
no meaningful way to "clip" a text layer's glyphs), rebuilt as a new
pixmap with everything outside made transparent. Fully inside → left
alone. The three-way test uses `QPainterPath.intersects()` /`.contains()`
against a path built from `item.mapToScene(item.boundingRect())` (a
polygon, not the axis-aligned `sceneBoundingRect()`, so a rotated item's
*actual* footprint is tested, not its looser bounding box). Both the
image and rectangle cases funnel through one helper,
`_rasterized_pixmap()`, which calls the item's own `paint(painter,
QStyleOptionGraphicsItem(), None)` into a transparent pixmap clipped to
the (item-local-space) clip path — this is deliberately the *exact* same
per-item painting `scene.render()` already does for PNG export, just
captured into a standalone pixmap instead of the final image, so "clipped
by Clip Layers" and "clipped by PNG export" can never visually diverge.
A `QGraphicsPixmapItem` gets its pixmap swapped in place (`SetPixmapCommand`,
same item, so any other state — z-value, layer name — survives); a
`QGraphicsRectItem` can't hold a pixmap, so it's replaced outright by a
freshly-built `QGraphicsPixmapItem` at the same rotation/z-value (see
below for *why* not "same position/scale" too) via `AddItemCommand` +
`DeleteItemsCommand` for the old one. All of
it is one `undo_stack.beginMacro()`/`endMacro()` in
`app_window._clip_layers()`, so a single Ctrl+Z undoes the whole
operation regardless of how many layers it touched — matching the
existing Paste/Insert-Metadata-Columns macro pattern, not a new one.
`plan_clip_layers()` itself is pure (never mutates the scene); the
caller is what turns its plan into undoable commands, same separation of
concerns as the rest of `DesignScene`'s `add_*()` methods vs.
`app_window.py`'s command-pushing.

**A clipped rectangle/ellipse is rasterized oversized on purpose, and
positioned by matching centers, not `pos()`.** A rectangle/ellipse has no
native resolution of its own the way a photo does — baking its clip into a
pixmap sized to its plain on-screen (96dpi scene-unit) footprint looked
fine at 100% zoom but came out soft/blocky once printed at export DPI or
zoomed in, since that raster had no more pixel density than the screen
itself. `_rasterized_pixmap()` takes a `supersample` factor for exactly
this (images pass the default `1.0` — their own native pixmap resolution
is already normally well above screen density, so upsampling it would
only blur, never sharpen); `_replacement_pixmap_item()` passes
`DesignScene.SHAPE_RASTER_SUPERSAMPLE` (`ceil(DEFAULT_EXPORT_DPI /
SCREEN_DPI)`, currently 4×) so the rectangle/ellipse's replacement pixmap
gets baked at 4× its on-screen pixel size, comfortably above real print
DPI, then displayed back down to the shape's actual footprint via
`set_item_scale(new_item, 1/4, 1/4)` — the same scale mechanism drag-resize
and `.mdproj` serialization already use, so nothing downstream needs to
know the backing raster is oversized. **This is also why the replacement
item can't just reuse `item.pos()`**: the new pixmap's native (oversized)
size doesn't share an origin with the old rect's own size, so their local
`(0, 0)` points don't correspond the way their *centers* do.
`_replacement_pixmap_item()` instead computes
`item.mapToScene(item.boundingRect().center())` and solves for the new
item's `pos()` so its own center (`pos() + transformOriginPoint()`, which
`set_item_scale()`'s anchored transform and `setRotation()` both leave
fixed regardless of scale/rotation) lands on that same scene point —
correct regardless of the old item's own rotation or accumulated scale.
Getting this wrong once already shipped a real regression: reusing
`get_item_scale(item)` (the *rectangle's own* cumulative resize factor,
already baked into its `rect()` by the fix above) on top of a pixmap that
already included that factor double-scaled the result, and reusing
`item.pos()` directly ignored the oversampled pixmap's different native
size — together making a clipped, previously-resized rectangle balloon to
several times its real size in the wrong place. Regression coverage lives
in `test_item_scale.py`'s and `test_clip_layers.py`'s rasterization tests,
which check the replacement item's actual on-screen footprint/center
against the original item's, not just pixmap pixel dimensions.

**Tools > "Bake Layers" flattens every print layer on the current page into
a single pixmap, reusing the exact same rendering path Export Print PNG
uses.** `io/png_export.py`'s `render_scene_to_image(scene, dpi)` was
factored out of `export_png()` specifically so baked artwork and exported
PNG artwork can never visually diverge (same "clipped by X and clipped by Y
must never diverge" reasoning as Clip Layers reusing an item's own
`paint()` call above). `DesignScene.plan_bake_layers(flattened_image)`
takes that already-rendered image (kept out of `scene.py` on purpose, to
avoid a `canvas` -> `io` import direction) and wraps it in one new
`QGraphicsPixmapItem`, positioned/scaled by the *exact* same
oversized-raster-plus-compensating-scale, match-the-center trick as the
rectangle/ellipse rasterization above — except here the "oversized raster"
*is* the whole flattened page (rendered at `constants.BAKE_DPI`, not screen
DPI) and the target center is `scene.sceneRect().center()`, not a single
old item's. Returns `([], None)` if the page has no print layers at all.
Like `plan_clip_layers()`, it's pure — `app_window._bake_layers()` turns the
result into one undoable macro (`AddItemCommand` for the new flattened
layer + `DeleteItemsCommand` for every old one), so a single Ctrl+Z restores
every original layer exactly as it was, including z-order (each item keeps
its own z-value while detached, same as Clip Layers/Delete).

**`BAKE_DPI` (`constants.py`) is 3x `DEFAULT_EXPORT_DPI` (900, not 300) —
deliberately higher than what a plain Export Print PNG uses.** A baked
layer's resolution is locked in permanently (there's no vector content left
to re-render at a different DPI later, unlike every other export), so a
user reported the first version of this feature (baked at the same 300dpi
as a plain export) as "very poor resolution output." Baking at 3x that
gives real headroom for a later export at a higher DPI, and — since Qt's
`SmoothPixmapTransform` hint downsamples whenever this gets rendered
smaller (on-screen at normal zoom, or into a later 300dpi export) — the
extra resolution also acts as supersampling for fine edges (small text
especially), addressing a companion "text rendering is very bad quality
(no subsampling etc)" report from the same baked output. See
`test_bake_layers_renders_at_bake_dpi_not_the_plain_export_dpi`.

**Undo/redo triggers a Layers-panel refresh even when it doesn't go through
one of `app_window.py`'s own handlers.** Every handler that pushes a
command (`_bake_layers`, `_clip_layers`, `_delete_item`, ...) already calls
`self._refresh_layers()` itself right after — but the Edit menu's Undo/Redo
actions are wired straight to `self.undo_group` (see
`createUndoAction`/`createRedoAction` above), bypassing those handlers
entirely. Without something watching the stack itself, undoing "Bake
Layers" restored every original layer *in the scene* correctly but left the
Layers panel showing only the one (already-undone) baked pixmap layer —
the panel's last explicit refresh, from *right after* baking, never got
invalidated. `_reset_undo_stack()` now connects each fresh
`QUndoStack.indexChanged` to `_on_undo_index_changed()`, which calls
`_refresh_layers()` (re-selecting whatever the scene's own
`selectedItems()` reports, since Qt preserves each item's selected flag
across being removed/re-added) — this fires on *any* index change
regardless of source, so it also covers undoing a plain move/rotate/delete,
not just Bake Layers specifically. Regression coverage lives in
`test_bake_layers.py`'s end-to-end test, which asserts on
`layers_panel.list_widget.count()` directly (not just `scene.print_items()`)
— checking only the scene's state after undo is exactly what let this slip
through the first time.

**Layers panel "Rename..." stores a user-assigned display name on the item
itself, in `canvas/items.py`'s `NAME_ROLE` (alongside `SCALE_ROLE`/
`BASE_RECT_ROLE`), via `get_item_name()`/`set_item_name()`.** `None` means
"no custom name" — `layers_panel._label_for()` only falls back to its
auto-generated label (`"Text: ..."`, `"Rect"`, etc.) when no name is set,
never storing an empty string as if it meant something (`set_item_name`
normalizes blank/whitespace-only input back to `None`). The rename button
opens a plain `QInputDialog.getText()` (matching this app's existing
button-plus-dialog pattern rather than inline list editing) seeded with the
item's current name; `app_window._rename_item()` pushes the result through
`PropertyEditCommand` like every other undoable per-item edit. The name
round-trips through `.mdproj` save/load (`item_to_dict`/`item_from_dict`'s
`"name"` key, defaulting to `None` for older files that predate it) and
through copy/paste (`clipboard.py` reuses the same (de)serialization), so a
renamed layer stays named after a save/reload or a duplicate.

**Arrow-key nudging** (`DesignView._nudge_selected`) moves the selection by
`ARROW_STEP_MM` (0.1mm) per press; holding a key down (OS auto-repeat,
`event.isAutoRepeat()`) switches to the coarser `ARROW_STEP_HELD_MM` (0.5mm)
once `_arrow_hold_timer` (a `QElapsedTimer`, reset on the first non-repeat
press of a key) has run past `ARROW_HOLD_THRESHOLD_MS` (500ms) — so a single
tap stays precise but holding the key still covers distance reasonably
fast. Mouse-drag scale is clamped to `MIN_SCALE`/`MAX_SCALE` in
`canvas/view.py` (currently 0.5%–3000%, i.e. `0.005`–`30.0`) — a deliberate,
user-set range, not an arbitrary default; don't tighten it back down
without checking why it was widened.

**Text font style is stored/passed as a full `QFont`, never as separate
family+size.** `TextStyle.font_spec` (project.py) and every text item's
saved `"font_spec"` (project_io.py) are `QFont.toString()` — round-trips
family, point size, weight, italic, underline, strikeout, and stretch in
one string via `QFont() ; font.fromString(spec)`. This replaced an earlier
`font_family: str` + `font_size: float` pair that silently dropped bold/
italic/underline/strikeout everywhere: the Font... dialog result, the
project-wide "next text layer" default, Reset to Default, and `.mdproj`
save/load. If you're tempted to add a new font-related field anywhere,
don't — thread the whole `QFont` (or its `.toString()`) through instead,
or the next style attribute added to `QFontDialog` will quietly break the
same way. No migration for old `.mdproj` files using the old
`font_family`/`font_size` keys — no released user base yet (same reasoning
as the z-order caveat below).

**A rectangle/ellipse's frame always matches its own fill color -- there
is no separate frame-color control.** `scene.add_rectangle()`'s initial
pen and `properties_panel._set_fill_color()` (the fill-color picker's
apply callback) both set the pen to the *same* `QColor` as the brush,
never a darker/different shade. Previously the pen was set once, at
creation, to `fill.darker(130)` and then never touched again by the color
picker -- so picking a new fill color changed the fill but left the frame
showing the *original* default color forever after, which read as "the
frame is always blue" regardless of what fill was chosen. If a visually
distinct border is wanted later, it needs its own explicit color control
plumbed through the same places (creation, the picker, Reset to Default)
-- don't quietly reintroduce an implicit darker-shade default in just one
of them.

**Color probe (eyedropper) samples whatever is actually on screen, not
scene content directly.** `PropertiesPanel`'s "Probe..." button (next to
"Color...") emits `probe_color_requested`; `MainWindow` wires that to
`DesignView.start_color_probe()` (sets a crosshair cursor and a
`_probing_color` flag) and wires `DesignView.color_probed` back to
`PropertiesPanel.apply_probed_color()` -- the same indirection every
other cross-panel interaction in this app uses, rather than the two
widgets holding direct references to each other. The next left-click,
handled in `DesignView.mousePressEvent` before any of the normal
selection/drag logic runs, calls `self.viewport().grab().toImage()
.pixelColor(event.pos())` -- i.e. it samples the *rendered pixel*,
including the template outline and the unprintable-area hatching
overlay if the click happens to land on one of those, not "the topmost
item's own color property." That's a deliberate simplification (a true
eyedropper samples what's visible, warts and all) rather than doing a
hit-test and reading the item's brush/text color directly. Escape cancels
an in-progress probe. `PropertiesPanel._apply_color()` is the single
shared endpoint both "Color..." (via `QColorDialog`) and "Probe..." funnel
through, so undo-pushing and the text-vs-fill branching logic exist in
exactly one place.

**Tools panel buttons are icon-only, `panels/icons.py`.** `QIcon.fromTheme()`
is unreliable cross-platform and especially in a frozen Windows build (no
freedesktop icon theme exists there at all), so icons are bundled as
files instead, exactly the way the asset gallery's own images are
(`assets/img`, `gallery.py`): outside the `mdtools` package, at
`assets/icons` in the repo root, so swapping one later is just replacing
a file, no code change needed. `icons.icons_dir()` mirrors
`gallery.gallery_dir()`'s dev-vs-frozen-build path resolution exactly
(branches on `sys._MEIPASS`), and both `scripts/build_windows.ps1` /
`build_linux.sh` `--add-data` it the same way.

**All Tools panel buttons are `QToolButton`, not `QPushButton` -- and are
all forced to the exact same `setFixedSize()`.** A plain `QPushButton`
(what `_icon_button()` built previously) reserves extra horizontal
padding for its "3D" bordered look even with no visible text and no
menu, making every button built through it noticeably *wider* than
Insert from Metadata (already a `QToolButton`, for its dropdown menu) --
reported as "other buttons are wider and it looks wrong." Switching
`_icon_button()` to build a `QToolButton` instead mostly fixes this on
its own, but `ToolPanel.__init__` also explicitly sets every button
(collected into `self._toolbar_buttons` as they're created, metadata
button included) to `self.metadata_button.sizeHint()` after they're all
constructed -- guaranteeing pixel-identical sizing regardless of any
per-instance `sizeHint()` drift a particular style/tooltip length might
otherwise introduce, rather than just trusting same-widget-type to be
enough. See `test_tool_panel.py`'s
`test_all_toolbar_buttons_are_the_same_size_as_the_metadata_button`.

**The Tools *dock* itself also needed an explicit width cap -- fixing the
buttons' own size wasn't enough.** `QMainWindow`'s dock layout allocates
a freshly-added dock some width based on its own internal heuristics,
unrelated to the actual content's `sizeHint()` -- even after every button
was made small and uniform (see above), the dock around them was still
wider than needed, leaving dead space beside a narrow column of icon
buttons ("the toolbar itself is a bit too wide"). `_build_docks()` now
reads `self.tool_panel.sizeHint().width()` right after adding the dock
and uses it for two calls: `self.tool_dock.setMaximumWidth(tool_width)`
(so it can never be *pulled* wider than its content needs) and
`self.resizeDocks([self.tool_dock], [tool_width], Qt.Orientation.Horizontal)`
(so it doesn't *start out* wider before anyone touches it -- the max
alone only constrains future resizes, not the initial layout pass).
Deriving `tool_width` from the panel's own `sizeHint()` rather than a
hardcoded pixel constant means this keeps working if the icon/button
size ever changes again later. See `test_view_menu_docks.py`'s
`test_tools_dock_is_no_wider_than_its_buttons_need`.

**Icons were originally self-drawn (plain QPainter primitives tinted
with the current palette's WindowText color) but are now bundled,
colorful SVGs from [Twemoji](https://github.com/twitter/twemoji)
(CC-BY 4.0)** — a user-requested switch to something more visually
distinct than flat single-color glyphs. Each icon function
(`text_icon()`, `rectangle_icon()`, `image_icon()`, `gallery_icon()`,
`metadata_icon()`, `crop_icon()`, `bake_icon()`, `save_icon()`) now just
calls `_load_svg_icon(name)`, which renders `assets/icons/{name}.svg`
into a `QPixmap` via `QtSvg.QSvgRenderer` and wraps it in a `QIcon`.
**Deliberately not `QIcon(path)`** (Qt's SVG *icon engine*, a separate
plugin — `iconengines/qsvgicon` — from the `QtSvg` module itself; not
guaranteed bundled by PyInstaller's default PySide6 hook the way the
`QtSvg` module already demonstrably is via `io/svg_export.py`'s
`QSvgGenerator`, which this app already relies on working in the real
frozen build). Rendering through `QSvgRenderer` directly avoids that
plugin entirely. Like every other Qt-GUI-object constructor in this
codebase, `_load_svg_icon()` must only run after a `QApplication`
exists — called lazily from `ToolPanel.__init__`, never at module import
time. CC-BY 4.0 requires attribution: see `assets/icons/ATTRIBUTION.md`
(which emoji + codepoint each file came from) and the credit line added
to Help > About. The button's original label text still becomes its
tooltip instead of disappearing — `ToolPanel._icon_button()` is the one
place that wires up an icon + tooltip together, so no button ends up
icon-only *without* a tooltip. See `test_icons.py`'s
`test_icons_are_colorful_not_a_single_flat_tint` (a regression guard: a
render producing only one distinct opaque hue would mean the SVG isn't
actually being loaded) and `test_icons_dir_points_at_the_bundled_assets_folder`.

**The zoom toolbar's actions (Zoom Out/In, 100%, Fit, Grayscale) also
got icons from the same bundled Twemoji set** (`zoom_out_icon()`,
`zoom_in_icon()`, `zoom_reset_icon()`, `zoom_fit_icon()`,
`grayscale_icon()`, same `_load_svg_icon()` helper) — unlike the Tools
panel, this toolbar's actions already had a visible text label with no
icon at all, so `_build_page_toolbar()` now explicitly sets
`zoom_toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)`
to keep both the existing text *and* the new icon showing side by side,
rather than risk the toolbar's default/inherited style silently hiding
the text once every action actually has an icon. See
`test_view_zoom.py`'s `test_zoom_toolbar_actions_all_have_a_non_null_icon`.

**Window icon: the existing MiniDisc logo (`assets/img/mdlogo.png`,
600×600), reused rather than a separate small asset.** Qt scales it down
as needed for the title bar/taskbar/alt-tab -- no need to pre-generate
smaller PNGs for that. Set in two places, deliberately: `main.py` calls
`app.setWindowIcon(...)` right after constructing `QApplication` (so
every window in the app inherits it), and `MainWindow.__init__` also
calls `self.setWindowIcon(...)` directly, so the window has the right
icon even when constructed without going through `main()` (tests, or any
future embedding). Both read the path via `gallery.gallery_dir()` (the
same dev-vs-frozen-build resolution the asset gallery itself uses),
rather than duplicating that logic.

**The .exe's own icon (shown in File Explorer/taskbar for the executable
itself, not a window) is a separate concern from the window icon above
-- it has to be baked into the .exe at PyInstaller build time, not set
at runtime.** Windows requires an actual `.ico` (not a plain PNG) for
this, so `assets/img/mdlogo.ico` was generated once via Pillow
(`Image.save(..., sizes=[16,24,32,48,64,128,256])`, a real
multi-resolution ico, not just a single size relabeled) from the same
source PNG, and `scripts/build_windows.ps1` passes it via PyInstaller's
`--icon` flag. Not wired into `build_linux.sh` -- PyInstaller's `--icon`
on Linux mostly has no effect on a plain ELF binary (no built-in icon
resource format the way Windows/macOS executables have), so there was
nothing meaningful to add there for this request.

**The Properties panel's text field is a `QPlainTextEdit`, not a
`QLineEdit`.** A `QGraphicsTextItem` already supports multi-line content
(pasted text, or anything loaded from an older `.mdproj`), but a
`QLineEdit` silently discards newlines on both display and edit — editing
a multi-line text layer through Properties used to be lossy. `text_edit`
is capped at a small fixed height (`setMaximumHeight(80)`, a few lines)
so it doesn't dominate the panel for what's still usually a short label;
`_apply_text()` and `set_item()` use `toPlainText()`/`setPlainText()`
instead of `text()`/`setText()`, but are otherwise unchanged — same
`textChanged` signal, same `_updating` re-entrancy guard.

**`PropertiesPanel.EXTRA_MINIMUM_WIDTH_PX` (40) widens the panel's minimum
width beyond whatever its layout would otherwise naturally settle on** --
`self.setMinimumWidth(self.minimumSizeHint().width() + EXTRA_MINIMUM_WIDTH_PX)`
at the end of `__init__`, deliberately relative rather than a hardcoded
absolute pixel width, so it stays "40px more than the layout's own
natural minimum" even as rows are added/removed later, rather than
silently drifting stale. Confirmed `minimumSizeHint()` itself is unaffected
by the `setMinimumWidth()` call (it still reports the layout's own natural
value afterward), which is what makes computing it this way -- rather than
needing a separately-tracked "before" value -- reliable.

**Zoom toolbar's "Grayscale" button is a purely visual, temporary preview
-- `DesignView.set_grayscale_preview()` -- never a real color-to-grayscale
conversion.** It applies/removes `canvas/view.py`'s `_TrueGrayscaleEffect`
on `self.viewport()`, which desaturates *everything* painted there (design
items, the unprintable-area hatch overlay, selection handles, all of it)
without touching the scene or any item's actual color in any way -- Export
Print PNG (Grayscale) still goes through `io/png_export.py`'s real,
luma-weighted Pillow conversion, completely unaffected by whatever this
toggle's current state is. Wired to a checkable `QAction` in the zoom
toolbar (`_build_page_toolbar()`), next to a new "100%" button
(`DesignView.zoom_reset()`, `set_zoom(1.0)` factored out of `_zoom_by()` so
both share the same clamping/no-op-if-unchanged logic as
`zoom_in()`/`zoom_out()`).

**`_TrueGrayscaleEffect` is a small custom `QGraphicsEffect` subclass, not
`QGraphicsColorizeEffect`** -- the first implementation used the latter
(`color=gray, strength=1.0`, seemingly the obvious built-in choice), but a
user reported "black is not black -- image looks very bright." Confirmed
empirically (rendering solid colors through the effect and reading back
actual pixel values): `QGraphicsColorizeEffect` doesn't do an honest
grayscale conversion at all -- it's meant for a sepia/tinted-photo look,
and even with a fully neutral gray color at full strength it washes
everything toward white (black mapped to `RGB(128, 128, 128)`, not
`RGB(0, 0, 0)`). `_TrueGrayscaleEffect.draw()` instead: grabs
`sourcePixmap(Qt.CoordinateSystem.LogicalCoordinates, offset)` (note:
PySide6 returns the pixmap directly and mutates the `QPoint` passed as
`offset` in place -- it does **not** return `(pixmap, offset)` as a tuple,
despite how the C++ signature might suggest binding it), converts it via
`QImage.convertToFormat(Format_Grayscale8)` (Qt's own native, accurate
luma conversion -- a single fast C++ call, appropriate for something
repainted continuously, unlike the real export's Pillow round-trip), then
recombines the result with the *original* image's alpha channel via
`CompositionMode_DestinationIn` (`Format_Grayscale8` has no alpha channel
of its own, so simply converting back to ARGB would make everything
opaque). Regression coverage renders actual solid-color rectangles through
a real `DesignView` and reads back pixel values directly (`test_view_zoom.py`'s
`test_grayscale_preview_does_not_lighten_black` /
`test_grayscale_preview_desaturates_a_colored_shape`) rather than only
checking that *some* effect object is present, which is exactly the gap
that let the wrong effect ship in the first place.

**Grayscale preview is deliberately read-only, not just a color filter.**
A user could otherwise still select/drag/resize/rotate/delete a layer (or
add a new one, or rename/reorder via the Layers panel) while merely
*previewing* the desaturated look, which defeats the point of a temporary
preview toggle. `DesignView.set_grayscale_preview(True)` now also calls
`scene().clearSelection()` and `self.setInteractive(False)` (Qt's own
flag for "stop forwarding mouse/keyboard events to the scene/items" --
disables click-to-select, native item dragging, and rubber-band
selection in one call); turning it back off restores
`setInteractive(True)`. `mousePressEvent`/`keyPressEvent` also each have
an explicit early-return guard (checking `self._grayscale_effect is not
None`) that skips this app's own handle-drag hit-testing and
Delete/arrow-nudge handling specifically -- belt-and-suspenders on top of
"nothing is selected so those already no-op", in case anything is ever
selected programmatically while the preview is active. `MainWindow`'s
`_on_grayscale_toggled` (now what the toolbar action's `toggled` signal
connects to, instead of `DesignView.set_grayscale_preview` directly) also
disables the Tool panel and Layers panel for the toggle's duration --
the remaining ways to edit a layer that don't go through the canvas at
all. The Properties panel needs no separate call: clearing the
selection above already disables it, via the same
`selectionChanged` -> `_on_selection_changed` -> `properties_panel.set_item(None)`
chain any other deselection goes through. See
`test_view_zoom.py`'s `test_enabling_grayscale_preview_deselects_the_current_item`,
`test_grayscale_preview_disables_canvas_item_interaction`,
`test_grayscale_preview_blocks_delete_and_nudge_even_if_something_got_selected`,
and the Tool/Layers-panel assertions added to
`test_zoom_toolbar_100_percent_and_grayscale_actions_are_wired`.

**Grayscale brightness/contrast is a project-saved setting, shared by
three surfaces that all go through the exact same pixel math.**
`mdtools/grayscale.py` (a new top-level module, not under `canvas/` or
`io/`, specifically so neither of those packages has to import the
other) holds `apply_grayscale(image, brightness=0, contrast=0)` and
`brightness_contrast_lut(brightness, contrast)` -- the actual
desaturation + adjustment pixel math, used identically by:
1. The canvas's own live grayscale preview (`canvas/view.py`'s
   `_TrueGrayscaleEffect`, which now just calls `apply_grayscale()`
   instead of doing its own inline conversion).
2. `GrayscaleExportDialog` (`panels/grayscale_export_dialog.py`) -- shown
   by `app_window._export_png_grayscale()` *before* the save-path
   prompt, with its own live preview (a screen-DPI render of the actual
   scene, re-adjusted on every slider move).
3. The real `export_png(..., grayscale=True, brightness=..., contrast=...)`
   (`io/png_export.py`) -- so what's previewed in the dialog (or on the
   canvas) and what actually gets saved can never visually diverge.

Brightness/contrast are each -100..100 (`BRIGHTNESS_RANGE`/
`CONTRAST_RANGE` in `grayscale.py`), 0 = unchanged. Contrast is applied
first (a multiplicative scale pivoting around mid-gray, 128), then
brightness (a plain multiplicative scale) -- both are baked into a single
256-entry LUT (`brightness_contrast_lut`), applied to a whole grayscale
image buffer via one `bytes.translate()` call rather than a per-pixel
Python loop, which is what keeps this cheap enough for a
continuously-repainted live preview and not just a one-shot export.
`apply_grayscale()`'s LUT step constructs a new `QImage` directly from
the translated byte buffer, then immediately calls `.copy()` on it --
`QImage(data, ...)` borrows that buffer rather than copying it, and
`.copy()` detaches it right away so the image doesn't end up referencing
a Python `bytes` object that's about to go out of scope (the same class
of buffer-lifetime gotcha as `QWidget.setGraphicsEffect()`/`QTranslator`
elsewhere in this codebase, just resolved differently here since the
local variable stays alive for the rest of the same function call
regardless).

Saved as `Project.grayscale_adjustment` (a new `GrayscaleAdjustment`
dataclass in `project.py`, alongside `default_text_style`) --
`io/project_io.py` serializes/deserializes it exactly like
`default_text_style`, defaulting to `GrayscaleAdjustment()` (0, 0) when
loading an older project file that predates the field. `MainWindow` adds
a `brightness_slider`/`contrast_slider` pair (`QSlider`s) to the zoom
toolbar, hidden unless the Grayscale toggle is on
(`_on_grayscale_toggled`) -- moving either
(`_on_grayscale_adjustment_changed`) writes straight into
`self.project.grayscale_adjustment` and calls
`DesignView.set_grayscale_adjustment()` to update the live preview
immediately. `_sync_grayscale_controls()` is the single place that seeds
the sliders (and the live preview) from whatever's currently saved on
the project -- called on New/Open (alongside the existing
`set_default_text_style` call) and again every time Grayscale is turned
on, so switching projects while the toggle happens to already be on
still shows the *new* project's saved values, not the old one's.
Confirming `GrayscaleExportDialog` also flows back through
`_sync_grayscale_controls()`, so an adjustment made from the export
dialog immediately shows up on the toolbar sliders too, not just in the
saved project data.

**The brightness/contrast toolbar sliders must be both hidden AND
disabled while Grayscale preview is off -- hiding alone wasn't enough.**
`QToolBar.addWidget(widget)` wraps each widget in its own
`QWidgetAction`; calling `widget.setVisible(False)` on just the widget
left the wrapping action itself still "visible" as far as the toolbar's
own layout is concerned in some Qt styles. `_build_page_toolbar()` now
keeps the `QWidgetAction`s `addWidget()` returns
(`self._grayscale_control_actions`), and `_on_grayscale_toggled()` toggles
three things together for each slider/label: the widget's visibility,
the widget's enabled state, and the action's visibility -- so the
sliders are genuinely inert, not just covered up, for the whole time the
preview is off. See `test_brightness_contrast_sliders_only_enabled_while_grayscale_is_on`
in `test_view_zoom.py`.

**File > Open Recent (last 5) and a startup "recent projects" screen.**
`mdtools/recent_projects.py` is a new top-level module -- deliberately
not living under `panels/` or `io/`, since both the startup dialog and
`app_window.py`'s File menu need it -- persisting a most-recent-first
list of project file paths the same way `i18n/__init__.py` persists the
language choice: an explicit `QSettings(path, IniFormat)` pointing at the
same `settings.ini` in `AppConfigLocation`, never the default
`QSettings()` (see i18n's own note on why -- `organizationName` side
effects on where `templates.json` lives). `recent_projects()` filters out
any entry whose file no longer exists on disk at read time, so a
moved/deleted project self-heals out of the list rather than leaving a
dead menu entry; `add_recent_project(path)` moves `path` to the front,
dedupes, and trims to `MAX_RECENT` (5). Called from `_open_project_path`
(the new shared loader both File > Open Project... and File > Open
Recent funnel through -- see below), `_save_project`, and
`_save_project_as`, so "recently edited" reflects saves as well as
opens, not just explicit opens.

**Tests that construct a `MainWindow()` now write into the real per-user
`settings.ini` unless isolated -- so `tests/conftest.py` isolates this
for every test automatically**, via an autouse
`_isolated_recent_projects_settings` fixture that redirects
`recent_projects._settings()` to a per-test tmp file (the same pattern
`test_language_menu.py`'s own `isolated_settings` fixture already used
for `i18n._settings()`, just made autouse and global instead of opt-in
per test file, since nearly every test file in this suite constructs a
`MainWindow`).

File menu gained an "Open Recent" submenu, populated on
`aboutToShow` (`_populate_open_recent_menu` -- same lazy-population
pattern as the Tools panel's metadata-insert menu) rather than kept
constantly in sync, so it always reflects whatever's current at the
moment it's opened. `_open_project` (File > Open Project...) was split
into the file-picker prompt plus `_open_project_path(path)` -- the actual
load/error-handling/recent-recording logic, now shared by three entry
points: File > Open Project..., File > Open Recent's per-path actions,
and the new startup dialog below.

**Startup no longer drops straight into New Design's template pickers --
a new `StartupDialog` (`panels/startup_dialog.py`) shows first**, listing
recent projects (double-click, or select + "Open Selected") alongside
"Open Other Project..." (a plain file browse) and "New Project..." (falls
through to the existing `NewDesignDialog` flow, unchanged). Its result is
read from `result_path` after `exec()`: a path string means "the caller
should open that project" (recent-list selection and Browse both set it
the same way -- from `MainWindow`'s perspective they're identical), `None`
means "user chose New Project," and a *rejected* dialog (Cancel/close)
is distinguished by `exec()`'s own return code, not by `result_path`.
`MainWindow._run_startup_flow()` is the new top-level entry point
`__init__` calls instead of going straight to `_new_design(prompt=True)`:
a rejected `StartupDialog` falls back to `_new_design(prompt=False)`
(unverified default templates, same fallback a rejected `NewDesignDialog`
already had), `result_path is not None` calls `_open_project_path()`,
and `result_path is None` (but the dialog itself was accepted) calls
`_new_design(prompt=True)` exactly as before -- so choosing "New
Project..." behaves completely unchanged once you're past this new first
screen. Existing tests that construct a bare `MainWindow()` (relying on
`show_startup_dialog`'s default of `True`) needed updating to also fake
`StartupDialog.exec` (typically just accepting with `result_path` left at
its `None` default) before the already-faked `NewDesignDialog.exec` is
ever reached -- see `test_save_as_template.py`'s
`_skip_straight_to_new_project_dialog` helper and
`test_startup_dialog.py`, which was rewritten around this two-stage flow
(and split UI-only coverage of `StartupDialog` itself out into
`test_startup_dialog_ui.py`).

**DPI values (screen/export/bake) are user-configurable global settings,
not fixed constants -- `mdtools/app_settings.py`, plus a Window >
Settings... dialog (`panels/settings_dialog.py`).** Previously
`constants.py` defined `SCREEN_DPI`/`DEFAULT_EXPORT_DPI`/`BAKE_DPI` as
plain module-level floats computed once at import time.
`app_settings.py` (a new top-level module -- deliberately not living
under `canvas/` or `io/`, since both need it, same reasoning as
`grayscale.py`) now owns these as `screen_dpi()`/`default_export_dpi()`/
`bake_dpi()` functions backed by the same `QSettings(path, IniFormat)` /
`settings.ini` persistence `i18n`/`recent_projects` already use --
`DEFAULT_SCREEN_DPI`/`DEFAULT_EXPORT_DPI`/`DEFAULT_BAKE_DPI` are what
those functions fall back to before the user has ever changed anything
(the exact old fixed values), plus `set_screen_dpi()`/
`set_default_export_dpi()`/`set_bake_dpi()` setters. `constants.py` is
trimmed down to just `MM_PER_INCH` (a true physical constant) and
`mm_to_px()`/`px_to_mm()`, which now call `app_settings.screen_dpi()` on
**every** call rather than a precomputed `PX_PER_MM` -- so a change made
in Settings takes effect on the very next conversion, not just for new
processes. Every other call site that used to import the plain constants
now calls the function instead, at the point of use, so the *current*
setting is always what's used, never a value frozen at import/def time:
`io/png_export.py`'s `render_scene_to_image()`/`export_png()` (both take
`dpi: float | None = None`, resolving to `app_settings.default_export_dpi()`
inside the function body when omitted -- **not** as the parameter's
default value, since a plain `= app_settings.default_export_dpi()`
default expression is only ever evaluated once, at module-def time, and
would never see a later Settings change), `io/svg_export.py`'s
`generator.setResolution()`, `panels/grayscale_export_dialog.py`'s
preview render, and `app_window.py`'s `_bake_layers()`. `canvas/scene.py`'s
`SHAPE_RASTER_SUPERSAMPLE` (a fixed class attribute computed once from
the old constants) became `DesignScene.shape_raster_supersample()`, a
classmethod recomputing `math.ceil(default_export_dpi() / screen_dpi())`
fresh each call, for the same "must never go stale" reason.

**Changing Screen DPI does not retroactively rescale a currently-open
project** -- template outlines and every item's pixel position/size are
already baked into fixed scene coordinates the moment a `DesignScene` is
constructed (via `mm_to_px()` calls made *then*, not continuously
re-evaluated). Only a newly created or freshly reopened project picks up
a changed Screen DPI. `SettingsDialog` says this explicitly right under
that field; Default Export DPI/Bake DPI have no such caveat since
`export_png()`/`render_scene_to_image()`/Bake Layers all resolve the
current setting fresh on every call, with nothing baked in ahead of time.

**Tests needed a second autouse settings-isolation fixture in
`conftest.py`.** `mm_to_px()`/`px_to_mm()` are called by nearly every
test that builds a `DesignScene` (template outlines, item positions,
...) -- without isolating `app_settings._settings()` the same way
`recent_projects._settings()` already was, every test run would read/
write the real per-user `settings.ini`, and a non-96 `screen_dpi` saved
there by a real user would silently break every geometry assertion in
the suite that assumes the default. `_isolated_app_settings` (autouse,
alongside the existing `_isolated_recent_projects_settings`) redirects it
to a fresh per-test tmp file.

**The effect object itself must be kept alive on `self._grayscale_effect`**
-- `QWidget.setGraphicsEffect()` does not itself hold a Python reference to
what it's given (the exact same class of gotcha as `i18n`'s
`_active_translator` and `QTranslator` -- see `i18n/__init__.py`), so a
purely-local effect object was silently garbage-collected the instant
`set_grayscale_preview()` returned, undoing the toggle before anything ever
actually painted with it -- confirmed by a regression test that forces
`gc.collect()` immediately after enabling it and checks the effect is
still there.

**Two save/load bugs found together, from one report ("the track list looks
wrong after reopening -- as if the font were off").** The font was innocent:
`QFont.toString()`/`fromString()` round-trips exactly, fractional point
sizes included. What was actually happening:

1. **`textWidth` was never saved.** `jcard_layout` wraps the track list to
   the panel width; Qt's default is not to wrap, so it came back as long
   unwrapped lines running off the card. Restored **before**
   `transformOriginPoint` in `item_from_dict`, and that order is
   load-bearing: the wrap width decides `boundingRect()`, and the origin is
   that rect's centre.
2. **`transformOriginPoint` was recomputed as `boundingRect().center()`
   rather than saved -- and it is not always that.** `jcard_layout._fit_text()`
   shrinks and wraps a text layer *after* creating it and never re-anchors
   the origin, so a live J-card pivots around a point from before the
   fitting. Those panels are rotated a quarter turn, so a different pivot
   puts the text somewhere else entirely. It is now stored. Reproducing
   what was actually there beats deriving something defensible -- and it
   avoids touching the panel-placement maths, which is correct as it stands.

**Then, prompted by "check the other layer types too": a scaled rectangle or
ellipse was scaled a *second* time on load, and moved.** Unlike text and
images, which scale through a transform, `set_item_scale()` resizes a
shape's own `rect()` and caches the pre-scale size in `BASE_RECT_ROLE` the
first time it is called (see `canvas/items.py`). `"w"`/`"h"` in the file are
the rect as it stood, scaling already included -- so a freshly loaded item,
with nothing cached, adopted that scaled size as its *base*, and the
`set_item_scale()` call at the end of `item_from_dict` multiplied by the
factor again. A 2x-wide rectangle reloaded 4x wide, and since that call also
re-centres the shape, it moved too. Copy/paste shared the bug, going through
the same two functions. Fixed by seeding `BASE_RECT_ROLE` with
`w/scale_x, h/scale_y` before that call -- **derived rather than stored in a
new field, so projects saved before the fix are repaired on load** and there
is no second rule for older files.

**Why none of this was caught: the existing tests compared saved fields, and
every field that was being saved round-tripped perfectly.** The new ones
(`test_item_roundtrip.py`, `test_jcard_roundtrip.py`) compare
`item.mapToScene(item.boundingRect()).boundingRect()` -- where the layer
actually lands on the page -- across a matrix of every item type against
several rotation/scale combinations. Note the matrix deliberately includes
scale `(1.0, 1.0)`: multiplying by one hides a double-scaling bug
completely, and that was the only case previously covered. There is also a
save-twice/load-twice test, since a per-round error compounds, and a check
that a reloaded shape's *base* rect is right, not just its visible size --
getting the appearance right over a wrong base would restore the bug the
moment the user dragged a handle.

**Known caveat:** projects saved before the z-order (`"z"`) field existed in
the `.mdproj` schema load with every item defaulted to z=0 (a tie), so Move
Up/Down appears broken (swapping equal values is a no-op) on old saves
specifically — not a live bug. No migration exists since there's no
released user base yet.

**MDRem support (`mdrem.py` + three panels) writes a project's metadata
onto the MiniDisc itself, over infrared, instead of only printing a label
for it.** MDRem is a separate hardware project (an RP2040 board emulating a
Sony RM-D10P remote, exposed as a USB serial port speaking a line protocol:
`PING`, `SEND <key>`, `TITLEDISC <text>`, `TITLETRACK <n> <text>`). Its own
repo's CLAUDE.md holds the protocol and the measurements quoted below.

Everything about it is **gated behind Window > Settings' "Enable MDRem"
checkbox** -- with it off, neither the Metadata dialog's Upload Tracklist
button nor the startup screen's Remote button is constructed visible at
all. Without hardware they could do nothing but explain themselves, which
is worse than not being there.

**Those two gates are free; the Recording menu's entries are not.** Both
buttons live on dialogs that are rebuilt every time they open, so they read
the setting afresh each time. `record_action` is built once, at startup, and
stayed visible after the adapter was switched off mid-session -- offering to
record an album through hardware the user had just said they do not have,
and with it the "mark tracks through the adapter" option, which is precisely
what someone without an adapter cannot use. `_sync_mdrem_actions()` is now
called both when the menu is built and after Window > Settings closes; it is
the place to extend if any other long-lived widget ever depends on this
setting. `_record_from_foobar()` also returns immediately when the adapter
is off, as a backstop behind the hidden entry -- the flow arms the deck and
marks the tracks over infrared, so there is nothing it could do. Recording
without the adapter means pressing record on the deck and letting its own
LEVEL-SYNC split the tracks, which is not something this app drives.

**Transport is PySide6's own `QtSerialPort`, not pyserial** -- it ships
inside PySide6, so this feature adds nothing to `pyproject.toml` and needs
no new `--add-data`/hidden-import handling in either build script. It's
driven *synchronously* (`waitForReadyRead`, never the `readyRead` signal):
the only caller is a worker thread with no event loop, and a whole upload
blocks for minutes, so it can never run on the GUI thread anyway.

**The deck has no return channel of any kind, and that shapes the whole
feature rather than being a footnote.** Infrared only goes one way, and
this deck's Control A1 bus is unpopulated -- so "sent successfully" can
only ever mean the adapter accepted the command, never that the disc says
what we think it says. Consequences, all deliberate:
- `MDRemUploadDialog` shows **exactly what it will write, before writing
  it** (a two-column tree of label -> final text), rather than reporting
  afterwards.
- Its success message says the titles need checking by eye, in those words.
- Progress is per-step only, driven by which command the worker is on --
  there is no finer signal to report, and the time estimate
  (`mdrem.estimated_seconds`) is openly approximate.

**`mdrem.py` keeps the same "build a plan, let the caller execute it"
split as `DesignScene.plan_clip_layers()` / `printing.build_copies_layout()`.**
`build_upload_plan(metadata)` is pure -- no device, no QApplication -- so
the confirmation UI and the tests both read the same object, and every
rule about what gets sent (transliteration, tracks past the deck's last
selectable number, titles that transliterate to nothing) is testable
without hardware.

**Titles are transliterated to ASCII before sending, and what that costs
is shown up front.** The deck accepts only 0x20-0x7E and the firmware
silently drops the rest, so a Polish or Japanese title would otherwise
arrive quietly mangled. `transliterate()` strips diacritics via NFKD,
maps the letters decomposition doesn't touch (`ł`, `ø`, `ß`, ...) plus the
typographic punctuation iTunes lookups routinely return, and **reports
whatever had no equivalent at all in `dropped`** rather than discarding it
silently -- CJK titles lose everything, and the user deserves to know that
before spending four minutes writing an empty title.

**The adapter is identified by asking it, not by its USB IDs.** The board
reports VID:PID 2E8A:0003, which is both its own bootloader's ID and a
generic Waveshare one -- so `detect_port()` opens each port and sends
`PING`, treating `PONG` as the identity. VID matching only decides which
ports to *try first*. Probing gets its own much shorter timeout
(`DETECT_TIMEOUT_MS`) than normal commands, because a typical Windows box
has several phantom Bluetooth serial ports that accept a connection and
then say nothing -- at the normal timeout, detection alone would take half
a minute.

**A saved port is never silently replaced.** `SettingsDialog._populate_ports()`
keeps a configured port in the combo even when it isn't currently present,
labelled as not connected -- resetting the setting to whatever else happens
to be plugged in would be worse than showing the truth.

**`app_settings.mdrem_enabled()` must not read its value with a plain
`bool()`.** An IniFormat `QSettings` hands a stored bool back as the
*string* `"false"`, and `bool("false")` is `True` -- reading it naively
would make the checkbox impossible to turn off again. Guarded by
`test_mdrem_enabled_survives_a_round_trip_through_the_ini_file`.

**Progress is driven by elapsed time against a per-step estimate, not by
one update per step -- reported as the dialog hanging.** A single title is
a 20-30 second exchange, so updating only when a step *starts* leaves the
bar motionless for that whole time, which is indistinguishable from a
frozen app. A `QTimer` (`_TICK_MS`) instead advances it continuously from
`mdrem.estimated_step_seconds()`, and `_on_step_started` **snaps it back to
the real cumulative position** at every actual step boundary so a step
running long or short can't let the estimate drift onward. The quoted total
is m:ss rather than whole minutes for the same class of reason: rounding to
minutes hid the erase checkbox's effect entirely on a short track list,
where both answers land inside the same minute.

**"Erase existing titles first" maps to the firmware's `TIMING COUNT`,
and is worth roughly half the total time.** The firmware overshoots the
old title's length on purpose (it cannot read the deck back), so clearing
costs ~17 s of the ~25 s a track takes. `_UploadWorker` sends
`TIMING COUNT 0` or `TIMING COUNT DEFAULT_CLEAR_COUNT` explicitly before
every run rather than trusting whatever a previous upload left the board
on -- it keeps that in RAM until reset. Default is *on*: leaving old text
behind is a worse failure than being slow.

**Uploading runs on a `QThread`, unlike `metadata_lookup`'s deliberately
blocking calls.** The deck accepts roughly 3.5 keypresses per second and
every character is its own infrared frame, so a full album takes minutes --
the "single, occasional, user-initiated click" reasoning that justifies
blocking for a one-second web request doesn't stretch that far. The
`MDRemClient` (and so its `QSerialPort`) is constructed **inside
`run()`**, never in the worker's `__init__`: a QObject belongs to the
thread that created it. Cancelling takes effect *between* steps, not
during one -- a single title is a ~20-second blocking exchange and
interrupting it partway would leave the deck sitting in name-edit mode.
**`reject()` must not call `worker.wait()`** -- doing so froze the entire
window for up to 30 s while the current title finished, which is exactly
what "Stop" is supposed to relieve. It instead cancels, says "stopping
after the current title", and returns immediately; `_on_worker_finished`
is the single place the dialog actually closes, whatever ended the run
(success, failure, or Stop). `closeEvent` routes the window's X button
through the same path, so the dialog can never be torn down while a worker
thread is still holding its serial port.

**The eject prompt is not optional politeness.** A MiniDisc deck holds an
edited TOC in volatile memory until the disc is ejected; everything an
upload just wrote is lost if the deck powers off first. `_offer_eject()`
therefore asks right after a successful upload -- asked rather than done
silently, since it physically opens the tray.

**`RemoteDialog` needs no worker thread**, unlike the upload: one key press
is a handful of frames, ~200 ms, short enough to send from the GUI thread.
It holds the port open for the window's lifetime instead of reopening per
press, since opening is far slower than sending. Its Recording group is
kept visually apart from the transport keys on purpose -- on a physical
remote Record is a deliberate reach, and a mouse makes stray clicks much
easier than a thumb does.

**"Record to MiniDisc from foobar2000..." (`foobar.py` +
`panels/record_dialog.py`) records an album from foobar2000 onto a
MiniDisc over S/PDIF and then titles it.** foobar plays; the deck records;
MDTools watches which track is playing and, when the playlist ends, hands
off to the existing Upload Tracklist dialog. Reached from the Recording menu,
hidden unless MDRem is enabled like every other MDRem entry point.

**`foobar.py` talks to the Beefweb Remote Control component
(`foo_beefweb`) over plain stdlib `urllib`** -- same reasoning as
`metadata_lookup.py`, and again no dependency added. The endpoints were
established by probing a live foobar2000 2.25.10 / foo_beefweb 0.10 rather
than from documentation (the published API page renders empty), and the
captured responses are checked in as fixtures in `test_foobar.py`
specifically so a component update that changes the shape is what breaks,
loudly, instead of the feature silently misreading state. Two details worth
keeping: options are set as **flat keys** on `POST /api/player`
(`{"options": {...}}` is answered with a 400), and the column set asks for
**`%album artist%`, not `%artist%`** -- a guest feature credits a different
artist per track, which is right for a track title and wrong for the disc.

**Titles come from the playlist, not from an iTunes lookup, whenever
recording.** What foobar is about to play *is* what will be on the disc, in
that order; a lookup returns whatever release the search matched. Same
reason `MetadataDialog` uses its live field values rather than the saved
project when uploading.

**`RecordDialog` is the last word on what the disc gets called, and it now
shows that**: an editable Artist/Album/Year, a clickable cover, and an
editable Title (and Artist) column, instead of the bare list of track names
and lengths it used to be. The only place to fix a wrong album name was
previously the project's own metadata *after* the recording -- too late for
the titles already written onto the disc. So `_capture_metadata` reads the
**widgets**, not the playlist, and `_offer_titling` reuses that result
rather than rebuilding from the playlist as it did (which would have
discarded every edit at the last step). Two details:
- **The Artist column is read back as well as the Title.** Rebuilding
  tracks from titles alone drops every performer, and with them the only
  thing that makes a compilation one (`ProjectMetadata.is_compilation`) --
  a disc would stop being a mixtape for having been looked at. The
  identical bug was found and fixed in `MetadataDialog` once already.
- **Everything freezes when recording starts** (`_set_fields_editable`):
  what is on screen at that moment is what gets written when it stops.

**The cover is looked up when the playlist loads, not when the album ends.**
The same call, moved. After a recording is the worst possible moment to
discover the search matched the wrong release -- nothing can be done but
retype the album and go round again; now it is on screen while the name can
still be corrected, or the picture clicked. A side effect worth having:
`_capture_metadata` no longer touches the network at all, and it runs the
instant an album finishes, where a hanging lookup would hold up the offer
to write the titles.

**`panels/cover_preview.py` is that picture, shared by four dialogs** (the
Metadata editor and all three recording sources) -- `CoverPreview`, a
QLabel that is also the button for replacing what it shows, plus
`fetch_into()`, the blocking-with-a-wait-cursor lookup that fills it. It
was lifted out of `metadata_dialog.py`'s private `_CoverLabel` when the
second caller appeared. Not merely to avoid duplication: the rules it
carries are the same everywhere and none of them are obvious.
- **Every automatic source guesses**, so the picture must be clickable.
- **`set_cover()` keeps bytes it cannot draw** and reports False rather
  than dropping them. They came from somewhere that had a reason for them,
  and Pillow (which `palette.py` reads a cover with) understands formats Qt
  does not. The one caller that must be strict is `choose_file()`, where an
  unreadable pick means the user pointed at a PDF -- and it puts the
  previous cover back, since a bad pick must not destroy a good one.
- **`fetch_into()` never runs for a compilation.** A search for "Various
  Artists" returns an unrelated record's sleeve; callers branch on
  `is_compilation()` first and draw one with `mixtape_cover` instead.

**`RecordDialog` deliberately has no worker thread**, unlike the upload it
hands off to. Every step here is either instantaneous (one localhost HTTP
call, one infrared frame) or a `QTimer` poll; the genuinely long part --
writing the titles -- already has its own threaded dialog, reused rather
than reimplemented.

**Order matters in the arming sequence, and each step exists because of a
specific failure:**
- `prepare_for_recording()` forces playback order to straight-through-once
  *before* anything starts. Shuffle would put tracks on the disc in an
  order the titles then wouldn't match; repeat would keep recording past
  the end of the album.
- The deck is armed (`SEND RECORD` -> record-pause) and then **the user is
  asked to confirm it actually is**. With no feedback channel, a RECORD
  that never arrived would mean playing a whole album into a deck that
  isn't recording, discovered 40 minutes later.
- The pause is released *first* and playback starts `LEAD_IN_MS` later, so
  the deck is already running when the first note arrives; the gap becomes
  leading silence rather than a clipped intro.
- Cancelling stops **both** ends. Stopping only foobar would leave the deck
  recording silence onto the disc as one long empty track.

**"Stopped" only means the album ended if playback was ever seen running.**
There is a gap between `play()` returning and foobar actually starting;
treating that initial `stopped` as the end would stop the recording
immediately and then offer to title an empty disc. `_started` guards this
(`test_stopped_before_playback_ever_started_is_not_the_end_of_the_album`).
The highest item index reached is tracked too -- a recording cut short is
reported and **not** offered for titling, since those titles would name
tracks that never made it onto the disc.

**Track splitting is done by the adapter, not left to the deck --
`TRACK_MARK_KEY`, sent on every track change.** The deck's own
"LEVEL-SYNC" marks a track when the signal drops to silence and returns,
and a PC's S/PDIF output carries none of the track-boundary subcode a real
CD player sends in the S/PDIF user channel. That works on an ordinary album
and demonstrably fails on a segue: recording *Popular Monster* merged
tracks 1 and 2, which run into each other with no silence between them, and
no deck setting can fix a boundary that has nothing to hear.

Since MDTools already knows exactly when foobar changes track, it sends the
mark itself. **`RECORD` pressed during recording is what adds a track mark**
-- established on an MDS-JE480 by recording, sending it mid-way, and finding
two tracks (`TREC`, the other candidate, was never needed).

Two consequences shaped the implementation:
- **The first track is never marked.** Recording already starts one;
  marking again immediately would leave a fraction-of-a-second track at the
  very start.
- **This conflicts with LEVEL-SYNC rather than complementing it**, so it is
  a checkbox with an explicit warning, not silent behaviour. With both
  active on an album that *does* have gaps, our mark lands on the file
  boundary and the deck's lands when sound resumes -- leaving a stray
  sliver of a track between the two.

The poll interval (`POLL_MS`, 250 ms) is now also the mark's worst-case
lateness, which is why it was halved from the 500 ms that was fine for a
progress bar alone. The serial connection is held open for the whole
session (`_deck`) rather than reopened per key, since opening a port costs
far more than sending and the mark's accuracy depends on how fast it goes
out.

**Album length is checked against the disc before anything starts.** The
track times are known up front, so `DISC_SP_SECONDS` (80 min) turns "the
recording got cut off at minute 80" into a warning beforehand. It only ever
warns -- which recording mode the deck is in (SP/LP2/LP4) can neither be
read nor set through the key table, so it is not MDTools' decision to make.

**"Record CD to MiniDisc..." (`cdrip.py` + `musicbrainz.py` +
`panels/cd_rip_dialog.py`) rips an audio CD into foobar2000's playlist and
then hands over to the flow above, unchanged.** That hand-off is the design:
arming the deck, the lead-in, a track mark at every boundary and titling
afterwards all already exist and are driven by whatever foobar happens to
have in its playlist, so this feature's job is only to make the playlist say
the right thing. `_record_cd` and `_record_from_foobar` share
`_run_record_dialog()`; `RecordDialog` never learns a CD was involved.

`CdRipDialog.result_metadata` *is* handed forward, which it originally was
not. The old reasoning -- the rip writes its titles into the files, so the
playlist already carries them and a second copy could only disagree --
still holds for the titles, and they are the same strings either way. What
a playlist cannot carry is the **artwork**: the disc's cover is now looked
up as soon as MusicBrainz identifies it (and again when a different
pressing is picked from the Release combo), shown in a clickable preview,
and would otherwise be thrown away between the two dialogs and searched
for a second time.

**It rips rather than letting foobar play the CD directly** -- foobar can
open a disc, and that was the shorter path. But then the disc is read in
real time *during* the recording, and a drive stumbling on a scratch at
minute 31 puts that stumble on the MiniDisc, which cannot be patched
afterwards. Ripping first moves every read error to a point where it costs a
re-read and nothing else, which is the whole subject cdparanoia exists for.

**Both tools are bundled binaries in `bin/win64`, not dependencies** --
`cd-paranoia.exe` (libcdio's maintained cdparanoia port) and `flac.exe`,
with their DLLs; provenance, versions and licences are in
`bin/win64/ATTRIBUTION.md`, which is not optional paperwork (both are GPL).
`cdrip.tools_dir()` resolves them exactly like `gallery.gallery_dir()` /
`icons.icons_dir()` -- `sys._MEIPASS` when frozen, repo root in dev --
and `scripts/build_windows.ps1` `--add-data`s the folder. **Nothing is
bundled for Linux and that is deliberate**: both tools are distro packages
there, so `find_tool()` falls through to PATH and no build-script change was
needed. Writing our own CDDA reader over `IOCTL_CDROM_RAW_READ` was
considered and rejected -- jitter correction and re-read logic is what
cdparanoia *is*, and ours would be a worse copy of it.

**Two things about cdparanoia's behaviour were established by running the
bundled binary, not read anywhere, and the code depends on both.** It writes
everything to **stderr**, success included (stdout is reserved for ripped
audio), and **`-Q` exits 0 even when it found no drive at all**. So neither
the exit code nor stdout can decide whether reading the TOC worked -- having
parsed a track table out of the output is the only evidence there is. A rip
proper *does* exit non-zero, which is what `rip_track` checks. See
`test_a_clean_exit_with_no_toc_in_it_is_still_a_failure`.

**Progress within a track comes from the output file's size, and the child's
stderr goes to a file rather than a pipe.** Reading the pipe line by line was
the first implementation and the obvious shape; it has two failure modes the
current one avoids. It assumes cdparanoia terminates its progress output with
newlines (it redraws a bar, and only `-e` promises lines at all), and it makes
**cancelling depend on a line arriving** -- a quiet stretch would leave Stop
doing nothing until the track finished. Not reading the pipe at all is not an
option either: a full pipe buffer blocks the child. A file has no buffer to
fill, so `rip_track` polls the clock (`RIP_POLL_S`, which is therefore also
the worst-case Stop latency) and measures the growing WAV. Progress parsed out
of cdparanoia's own `@ n` field was rejected separately: it means different
things in different builds, while a file's size on disk cannot be misread.
Measuring the file then gives the correctness check for free --
`RipTask.expected_wav_bytes` is what the TOC says the track must weigh
(44 + sectors x 2352), and **a track that came up short fails the rip however
cleanly the process exited**, because a truncated track is not something you
notice after it is on a MiniDisc. The log is deleted on success and **kept on
failure**, where it is the only diagnosis a bad disc gets. Note the ordering
constraint: both deletions happen after the `with open(...)` block, since
Windows refuses to unlink a file that is still open.

**Cancelling a rip is immediate, unlike cancelling an MDRem upload.** There
the worker is mid-way through a blocking exchange that would leave the deck
in name-edit mode; here killing the reader leaves nothing anywhere, and the
partial WAV is deleted on the way out. A failed or cancelled rip must also
**never reach the playlist** -- a half-ripped album loaded into foobar would
be recorded as though it were the whole disc.

**A CD carries no text at all, so identification is `musicbrainz.py`, not
the existing iTunes lookup.** `metadata_lookup.py` takes an artist and album
name, which is exactly what a bare disc cannot supply. MusicBrainz trades a
TOC for one. Two queries, deliberately, because they fail in opposite
directions: the **exact disc id** matches this pressing and nothing else but
only hits if somebody submitted it, while the **fuzzy TOC search**
(`/discid/-?toc=...`) finds releases nobody ever submitted an id for, at the
cost of returning every pressing with the same track lengths. Exact first.
Cover art still comes from `metadata_lookup.find_cover()` -- it already
caches into the asset gallery, and MusicBrainz's artwork is a separate
service. MusicBrainz **refuses requests without an identifying User-Agent**,
so `_USER_AGENT` is not politeness.

**The disc id's 100 fixed hex slots are load-bearing, not padding.** They
are what makes two pressings hash identically regardless of track count, so
it must not be "simplified" to just the tracks that exist. Verified end to
end against the live service while building this: the TOC of Nirvana's
*Nevermind* hashes to `I5l9cCSFccLKFEKS.7wqSZAorPU-`, which musicbrainz.org
resolves to that release -- that string is the test vector in
`test_cdrip.py`, and it is the one expectation in that file that came from
outside it.

**Beefweb cannot be given the ripped files, which is why `foobar.py` now
also drives foobar2000's command line.** `POST /api/playlists/{id}/items/add`
answers **403 "item is not under allowed path"** for anything outside the
music directories configured in foobar's own preferences -- and that list
starts out, and on a normal install stays, empty (`GET /api/browser/roots`
returned `{"roots": []}` on the real install this was built against; adding a
file from the user's own Music folder was refused). `foobar2000.exe /add` has
no such notion. So Beefweb still makes the playlist, clears it and reads back
what landed, and the *files* go in through `add_files_via_cli()`. Splitting
one operation across two transports is not elegant; making every user
configure a whitelist before a CD could be recorded is worse.
`find_foobar_exe()` reads the `App Paths` registry key, and the location is
overridable in Window > Settings.

**`wait_for_item_count()` exists because `/add` returns before foobar has
finished.** The command line is answered as soon as foobar *accepts* the
files; reading and tagging them happens after, so asking for the playlist
immediately reports a count still climbing.

**Tags are written at encode time, and that is what makes the titles
correct downstream.** `flac --tag=...` gets TITLE/ARTIST/ALBUMARTIST/
ALBUM/DATE/TRACKNUMBER, so `foobar.metadata_from_playlist()` -- and
therefore what gets written onto the MiniDisc -- reads the CD's real titles
with no special casing anywhere. Both ARTIST and ALBUMARTIST, since the
record flow reads `%album artist%` for the disc title. Filenames are
zero-padded with the track number in front so disc order survives even if
something along the way sorts them. Tags reach the encoder as **command line
arguments**, so a Polish or Japanese title surviving that trip on Windows is
an assumption about flac.exe's own argv handling, not something this code
can guarantee -- which is why
`test_the_bundled_encoder_writes_non_ascii_tags_without_mangling_them` runs
the real bundled encoder and reads the Vorbis comment block back out of the
FLAC. If that ever stops being true, every title on every ripped disc is
silently wrong.

**Old rips are deleted at the start of the next one, never at the end of a
recording** -- the files stay in foobar's playlist for as long as the user
might replay them, so deleting them when a recording finished would pull
them out from under it (user's explicit choice among the alternatives).
`clean_stale_rip_folders()` only removes folders holding nothing but
`.flac`/`.wav`/`.log`: the rip folder is user-configurable, so it can be
pointed somewhere that also holds something else, and a recursive delete has
no business guessing. Default location is under the system temp folder --
a rip is raw material for a recording, not a music collection.

**The entry is gated behind the MDRem setting like the other recording
entries**, via `_sync_mdrem_actions()`. Ripping needs no adapter, but this
entry does not stop at ripping. The port is resolved *before* the rip, and
foobar's reachability and location are checked before it too: the rip is the
expensive half, and every one of those failures costs minutes if discovered
afterwards and nothing if discovered first.

**Verified end to end on real hardware** (a USB drive, Skillet's *Unleashed*),
after being built blind on a machine with no optical drive at all:
- `cd-paranoia -Q`'s real output matches the parser exactly; that capture is
  now a fixture (`REAL_TOC_OUTPUT`) so a hand-written one can never drift
  from the shape the bundled binary actually produces.
- The **plain drive letter** (`-d F:`) works, so `device_candidates()`' first
  spelling is the one that hits. The `\\.\F:` fallback has therefore never
  been needed in practice -- keep it, but don't take it as load-bearing.
- The disc's identifier (`_dODxWGqmW9J1Ez3UiD8Z1z2JpY-`) resolved on
  musicbrainz.org to the right release with the right track count -- a
  second live-verified vector alongside Nevermind's.
- A ripped track came out **byte-exact against the TOC** (40,560,284 bytes),
  and the tags survived the whole way round: written by flac.exe, read back
  by foobar2000, `metadata_from_playlist()` returning the right artist,
  album, year and titles. That round trip is the thing the MiniDisc's own
  titles depend on.
- Windows' CDFS reports the label **"Audio CD"** for an audio disc, so
  `GetVolumeInformationW` succeeds where the code originally assumed it
  would fail. `has_media` is a usable "something is in there" hint, never
  the authority -- reading the TOC is.

**Speed is the one unwelcome finding: about 3x, i.e. ~80 s for a 3:50
track and ~15 minutes for a 43-minute album.** That is cdparanoia being
thorough on a cheap USB drive, and it is the price of the error correction
this feature exists for. If it ever needs to be faster, the lever is `-Z`
(disable paranoia) -- which trades away exactly the thing that made ripping
preferable to letting foobar play the disc live, so it should be a visible
choice, never a quiet default.

**The Project menu became "Recording", and the metadata editor moved out of
it onto the Tools panel.** The menu held the one dialog used while *designing
a label* next to three that drive a tape deck; nothing but recording is in it
now (`app_window._build_menu`), and `ToolPanel.edit_metadata_requested` opens
`MetadataDialog` from a button beside "Insert from Metadata" -- the album's
details next to the layers built out of them. **Erase MiniDisc... stayed**,
below a separator: it is not recording, but it is what you do to a disc you
are about to record over, through the same deck and the same adapter, and a
menu of its own for one entry would be worse. Every user-facing string that
said "Project > Metadata..." had to change with it -- `app_window`,
`settings_dialog`, `tool_panel`'s own empty-menu placeholder, the README and
all three manuals -- so grep for a menu path before assuming it is still
true.

**"Record Folder to MiniDisc..." (`audio_folder.py` +
`panels/folder_record_dialog.py`) is the third source of a recording, and
structurally the thinnest.** Where `cdrip.py` has to *make* the audio first,
this only has to point foobar2000 at files that already exist: list them,
replace the playlist, read it back, hand off to `RecordDialog` exactly as the
CD flow does.

**Nothing here reads a tag, on purpose.** There is no tag library in this
project and foobar2000 is a better one than anything that could be added for
this -- it has to read the files to play them regardless. So `audio_folder.py`
decides only *which* files and in *what order*, and every title, artist,
album and length comes back out of Beefweb afterwards. Two consequences:

- **`%path%` is appended to `foobar._COLUMNS`** (same "append, never insert"
  rule `%artist%` already followed, so no positional index shifts), feeding
  `PlaylistItem.display_title()` -- the title, else the filename stem.
  foobar substitutes a filename for a missing `%title%` itself, so this is
  usually belt and braces, but a folder of untagged files is exactly what
  this feature is for and a disc of blank track names is not worth risking
  on behaviour nobody here pinned down. `RecordDialog`'s own track list and
  progress line use it too, so what is listed is what gets recorded.
- **Order comes from the filename** (`natural_key`, digit runs compared as
  numbers so `10` follows `9`), because it is the only ordering signal that
  exists before foobar has seen the files. A folder holding tracks *is* the
  album and its subfolders are skipped; only a folder with no audio directly
  in it is recursed into, which is what puts a `CD1`/`CD2` two-disc album in
  disc order without letting somebody pick a library root and silently get
  all of it.

**Three sources decide the album name, in strict order: what the user typed
beats the tags, which beat the folder name.** The middle rung is the one
that is easy to get wrong and did get wrong first time round -- the fields
are *prefilled* from `guess_from_folder_name()` before foobar has read a
single tag, so treating whatever sits in them as the user's word let a folder
called "Disc 1" quietly rename a properly tagged record.
`FolderRecordDialog._resolve()` compares each field against the guess it was
seeded with: still holding it means untouched. A cleared field deliberately
counts as untouched rather than as "no name", since falling back to the tags
is what emptying a wrong guess actually wants.

**This is the only entry point that hands metadata forward to
`RecordDialog(..., metadata=...)`, and it has to.** The CD flow deliberately
does not: it wrote its titles into the files it created, so the playlist
already carries them and one source of truth beats two. A folder is somebody
else's files and *nothing here rewrites them*, so an album name corrected in
this dialog reaches the disc no other way. `_capture_metadata` uses the given
metadata when there is one, and skips its own cover lookup when that metadata
already carries artwork; `_offer_titling` now reuses `result_metadata` rather
than rebuilding from the playlist, which would have thrown the correction
away at the last step.

**It takes two presses, not one -- Load Folder, then Record.** The first
version loaded and accepted in the same click, so the dialog vanished the
instant it had anything to show. What it has to show is the point: which
album the tags turned out to describe, the artwork it will be labelled
with, and the titles foobar read out of the files. Cancelling after the
load leaves the playlist replaced and nothing recorded, which is exactly
what the CD flow does too.

**The load runs on a `QThread`, unlike everything else in this dialog.**
`add_files_via_cli` and `wait_for_item_count` have a 30 second timeout each,
so the worst case is a minute of frozen window -- normally it is a second or
two, but that is not a bet worth taking. **Cancelling is deliberately not
offered**: the playlist has already been cleared, the work is inside
foobar2000, and stopping halfway would leave it holding part of an album
with no indication why. `reject()` says so and returns; `closeEvent` ignores
the X. (Compare `cdrip`'s worker, where cancelling is immediate and right,
and the MDRem upload's, where it takes effect only between steps.)

**`cdrip.ensure_folder()` -- the rip folder is a path somebody typed, so
it routinely names a directory that does not exist.** That is the normal
state before the first rip, not an error, and it used to be left for
whatever came next to trip over: Windows' native folder picker complains
rather than politely falling back when opened on a missing directory. Now
`SettingsDialog` creates it before browsing *and* on OK, and `CdRipDialog`
creates it before ripping. Same "created on demand, at the moment it is
needed" rule as `user_paths.projects_dir()`. A folder that genuinely cannot
be made (a drive that is not there, no write permission) raises
`CdRipError` naming it -- and in Settings that **warns without blocking
OK**, the same rule the MDRem port follows: hardware that is unplugged
right now is a reason to say so, not a reason to refuse the setting.

**Every file dialog starts somewhere deliberate -- `mdtools/user_paths.py`.**
All of them used to pass `""` as the starting directory, which leaves Qt on
the process's working directory: wherever the app was launched from, and for
a frozen build the install folder. Projects landed next to the executable
and exports scattered wherever the last dialog had wandered. The rule now is
the one the OS already sets -- documents in Documents, pictures from
Pictures -- with one named folder of its own,
`Documents/MiniDiscProjects`, because a project is a thing a user should be
able to find again a year later.

- **`QStandardPaths`, never a hand-built `%USERPROFILE%/Documents`**: the
  real folder is localised (Dokumenty, ドキュメント) and can be redirected
  to OneDrive or another drive, and only the OS knows where it is.
- **Created on demand, not at startup.** A folder appearing in someone's
  Documents before they have saved anything is clutter; but a dialog
  pointed at a directory that does not exist falls back somewhere
  arbitrary, so `projects_dir()` creates it at the moment a dialog is about
  to open in it. A read-only Documents falls back to Documents itself
  rather than raising.
- **Derived, not configurable.** The CD rip folder is a setting because it
  holds hundreds of megabytes somebody may need off their system drive;
  these are starting points for a picker, and a preference per dialog would
  be more machinery than the problem deserves.
- **Exports land beside the project** they came from, falling back to the
  projects folder -- the SVG that cuts a design and the PNG that prints it
  are the same job as the `.mdproj`, and the set is only findable at
  cutting time if it stayed together. `PrintDialog` therefore takes a
  `start_dir`; `MultiprintDialog` has no single project to belong to and
  gets the fallback.

**A first save is proposed as "Artist - Album (Year).mdproj", from
`mdrem.disc_title()` -- the same function that composes what the deck is
told.** One function, so the file on disk and the title on the disc cannot
drift into disagreeing about what the album is. It is deliberately **not**
run through `mdrem.transliterate()`: that strips a title to ASCII because
the deck can display nothing else, and mangling "Zażółć" into "Zazolc" on
disk would be carrying a hardware restriction somewhere it does not apply.
Empty metadata suggests no filename at all rather than a bare ".mdproj".

`test_user_paths.py` closes with a blanket guard
(`test_no_dialog_is_left_starting_on_the_working_directory`) that drives
every entry point and asserts none passes an empty directory, so this cannot
quietly regress one dialog at a time.

**Recording > "Erase MiniDisc..." (`panels/erase_dialog.py`) is built around
an admission: we do not know what the ERASE key does.** The firmware's own
findings say `ERASE` (SIRC `0x07DA`) is *recognised* by an MDS-JE480 as a
write command -- sent to a write-protected disc it produced the deck's
protection message, which a wrong code would not have -- but the entire
write group was only ever tested behind the write-protect tab, deliberately
(`RECORD` would otherwise have wiped the test recording), and at three-second
intervals the deck's message never cleared between keys, so **which key does
what was never distinguished**. Shipping "press this to erase your disc" on
that basis would be guessing with someone's recording.

So it is a **guided sequence that asks the user what their deck's display
says** -- STOP, then ERASE, then a question, and only a Yes sends ENTER to
accept. The user's eyes are the only instrument available; this is the same
shape, and the same reasoning, as RecordDialog arming the deck and then
asking whether it really armed. Three details worth keeping:
- **ENTER is a button the user presses, not something sent for them.**
  It used to go out once, automatically, the moment they answered "yes, it
  is asking me" -- and on the real MDS-JE480 that did nothing visible, with
  "maybe it needs it twice?" the obvious next thought and no way to try.
  The deck cannot be read back, so how many presses a given model's menu
  wants is not knowable from here; `ConfirmPromptDialog` hands the key to
  the person who can see the display and stays open so they can press it
  again, counting as it goes. **Done only counts as a confirmed erase if
  ENTER actually went out at least once** -- otherwise it would be a way to
  claim an erase that never happened.
- **A "no" sends CANCEL**, rather than just stopping. Leaving the deck
  parked on a destructive confirmation would arm it for whoever next walks
  past.
- **The question is about the display, never about the outcome.** "Is it
  asking you to confirm?" is observable; "did it work?" is not, and the
  answer decides whether an irreversible key goes out.
- **It offers to eject afterwards**, because an erased TOC is volatile until
  the disc comes out -- exactly as a written one is
  (`MDRemUploadDialog._offer_eject`).

It is deliberately **not tied to the open project**: it acts on whatever
disc is physically in the deck, which has nothing to do with which label is
being designed, so it works with no project open at all.

**A playlist or a CD may be a compilation, and almost everything downstream
assumed an album.** A mixtape takes its album and artist from whichever
track happened to be first, so the disc gets titled after one track's
record, the J-card credits one performer for twelve, and a cover art lookup
keyed on those words returns some unrelated sleeve -- presented as though it
were this disc's. `ProjectMetadata.is_compilation()` is the one predicate
everything else hangs off.

**The detection deliberately is not "do the track artists differ".** That
would call every album with a guest feature a compilation, which is exactly
the mistake `foobar.album_artist()` already exists to avoid. It asks whether
*most* tracks can be attributed to one artist -- the album's own if it has
one, else the commonest track artist -- with `_same_artist()` matching by
substring either way, so "Falling In Reverse" still claims the track
credited to "Falling In Reverse, Jelly Roll". A release credited to Various
Artists says so outright and is taken at its word. **Absence of per-track
artists is not evidence**: a hand-typed or looked-up track list has none,
and stays an ordinary album.

**Getting this wrong is asymmetric, so the negative case carries the
weight.** A compilation misread as an album is a plain-looking cover; an
album misread as a compilation is renamed to Various Artists, has its sleeve
replaced and its J-card rewritten. Half of `test_compilation.py` pins down
the ordinary path being untouched -- see
`test_a_guest_feature_does_not_make_an_album_a_compilation` and
`test_an_ordinary_albums_track_lines_are_unchanged_by_the_artist_field`.

**`Track.artist` is the new field this rests on**, plumbed through
`project_io` (defaulting to `""`, so projects saved before it load as the
ordinary albums they were), `foobar`'s column set (`%artist%` **appended**
to `_COLUMNS`, so every existing positional index keeps its meaning), the
CD rip dialog's own Artist column, and the Metadata dialog's. That last one
was not optional: `_current_metadata()` rebuilds the track list out of the
table, so without a column to hold them, opening the Metadata dialog on a
mixtape and pressing OK silently dropped every performer and the project
stopped being a compilation just for having been looked at.

**`foobar.album_title()` now answers "the album these are all from", not
"track one's album".** Weighed against the tracks that actually carry an
album tag, **not** against the whole playlist -- counting untagged tracks as
votes against would strip the name off a half-tagged ordinary record, which
is a regression on the normal path for the sake of the unusual one.

**`mixtape_cover.render_cover()` draws a cover rather than special-casing
every layout.** It returns ordinary PNG bytes for `metadata.cover_art`, so
`auto_layout`, `jcard_layout`, `palette` and the `.mdproj` all carry on
exactly as they do for a fetched sleeve -- nothing downstream knows. Two
constraints shaped it, both physical:
- **It has to survive grayscale.** Two colours chosen to contrast by hue can
  convert to the same grey, at which point the accent rule disappears into
  its own background. The accent is therefore separated by *luminance*, and
  the search ladder desaturates towards a pale tint when brightness alone
  cannot get there -- which it cannot for blue, carrying 0.0722 of luminance
  against green's 0.7152. `test_background_and_accent_stay_apart_in_grayscale`
  sweeps every hue rather than trusting one sample, and is what caught that.
- **It has to survive being small.** The list is fitted by measurement, and
  each track gets a **hanging indent** -- wrapping "01 Artist - Title" as one
  paragraph puts continuation lines hard against the numbers, where "Heaven"
  on its own line reads as track 03.
An analogous accent hue replaced a complementary one after looking at a
render: hot pink on bottle green was garish where a lifted neighbour reads
as deliberate. The seed is a SHA-1 of the track list, not `hash()`, which is
salted per process and would repaint the cover on every run.

**Where the branch actually goes in: `record_dialog._capture_metadata()` and
`app_window._fetch_cover_into_metadata()`, both immediately before their
`find_cover()` call.** Not inside `find_cover` itself -- Project >
Metadata...'s own "Lookup Track List..." button should still search for
whatever the user typed, because there they asked for a search.

**Templates > "Change Template for This Page..." (`app_window.apply_template`)
swaps a page onto a different template.** Until it existed a template could
only be chosen at File > New, so picking the wrong one meant starting over.

**It empties the page rather than migrating it**, per explicit user
instruction ("zmiana szablonu to wykasowanie jego zawartości i warstw --
dlatego user musi potwierdzić"). Item coordinates are meaningless across a
template of a different size and shape, so the menu action confirms first
and `apply_template` then rebuilds the scene from scratch. Two details that
are easy to get wrong:
- **The undo stack is reset.** Its commands reference items on the scene
  being discarded; undoing one afterwards would try to put them back into a
  scene that no longer exists.
- **The old scene's `id()` is discarded from `_connected_scenes`.** Python
  reuses `id()` after garbage collection, so a stale entry there would make
  some later scene silently skip connecting `selectionChanged`.
- **A disc page re-seeds the insertion-mark triangle and label**, exactly as
  File > New would. An earlier version deliberately didn't ("seeding belongs
  to starting a design, not reshaping one") and that was wrong: the user
  adjusts those two anyway, so leaving the page bare only means retyping
  them. `_populate_new_scene()` is now the single place both File > New and
  a template change go through, so the two can't drift apart again.

**After a recording, the disc page lays itself out (`auto_layout.py` +
`app_window._auto_layout_disc_label`)**: the full-face template, the cover
across it, cropped, and the MiniDisc logo on the slider sticker. The two
placements pull in opposite directions on purpose -- the cover is scaled by
the **larger** ratio so it covers the label completely (its overhang is
exactly what Clip Layers then trims), the logo by the **smaller** one so it
stays inside the slider sticker with room to spare (`LOGO_FILL`). The logo is
placed against the sticker's *right* edge (`LOGO_RIGHT_MARGIN`, ~1.65mm on the
real 27.5mm sticker), vertically centred rather than dead centre, so the rest
of the sticker stays free for whatever the label needs to say.

**The cover is pushed behind whatever the template change seeded.** Since a
template change re-seeds the insertion mark (above), a full-bleed cover added
afterwards would sit on top of it and bury it -- and a layer nobody can see is
a worse starting point than one that needs restyling.

**The insertion mark is recoloured to stay readable over the cover
(`auto_layout.recolour_insertion_mark`).** Keeping it on top was only half
the problem: default black text over a dark full-bleed sleeve is present and
invisible, which reads as the mark having been lost. It becomes black or
white by `palette.readable_text_colour()`. Three things worth keeping:
- **The colour comes from `palette.region_colour()` over the cover's top
  30%, not `dominant_colour()` over all of it.** The mark sits in the top
  quarter of the label; a sleeve that is pale up there and dark below
  averages to a mid-tone describing neither end.
- **Every text layer on the page is recoloured, not the ones matching
  "INSERT THIS END".** This only ever runs immediately after
  `apply_template`, when the mark is the only text there is -- and a literal
  string match would quietly stop working in a translated build or the
  moment anyone edited the text.
- **It is not an undo command.** The items it touches weren't added by one
  either (`apply_template` resets the stack and `_populate_new_scene` adds
  them directly), so there is nothing to undo back to.

This needed `DesignScene.cut_shape_rects()`: `template_clip_path()` unions
every cut shape, which is right for clipping and wrong for *placing*
something on one of them -- fitting a cover to the union of a disc label and
a slider sticker would size it to a rectangle spanning both.

It replaces whatever was on the disc page **without asking** *after a
recording*, per explicit instruction ("robimy ciche kasowanie"): that flow
has already asked for confirmation several times, and one more prompt after
watching an album go down in real time would be noise. Note it switches the
page combo to the disc page first -- Clip Layers operates on whatever page is
*current*, so skipping that would crop the cover page instead.

**The same layout is also a Tools panel button
(`_auto_layout_from_metadata`), for a project that was never recorded** --
otherwise this code was reachable only by recording something. That entry
point **does** confirm first: a single toolbar click wiping a page someone
was working on is a nasty surprise, where the post-recording path is the
tail end of a long, already-confirmed operation. It also fills in missing
cover art (and a missing year) via `find_cover` before deciding it cannot
proceed -- the layout is built around the cover, so without one there is
nothing to gain by clearing the page first.

**The Metadata dialog can also pull its fields straight from foobar2000
("Load from foobar2000").** Same source the record flow uses, available when
nothing is being recorded -- what is queued to play is usually exactly what
the label is for, and it beats a search because these are the real files
with their real tags in their real order. Deliberately **not** gated behind
the MDRem setting, and neither is the foobar2000 URL field in Settings:
reading a playlist needs foobar, not the infrared adapter.

**Picking a release without a picker: `metadata_lookup.best_match()` /
`match_confidence()`.** `MetadataDialog`'s "Lookup Track List..." still shows
the user a list, because a person beats any heuristic; the automated flows
cannot stop and ask, so they score candidates themselves rather than trusting
iTunes' result order. The statistic blends whole-string closeness
(`difflib.SequenceMatcher`) with word overlap -- the first punishes reordering
("Bowie, David"), the second ignores word order entirely -- over strings
normalised to casefolded, unaccented, punctuation-free text with edition noise
("deluxe", "remastered", "single", ...) stripped. **Track count matters**, and
the record flow always knows it: stripping that noise makes "Popular Monster -
Single" score *identically* to "Popular Monster", so without the count there
is nothing left to tell an album from its own single. It also breaks ties in
`best_match`, so the fuller release wins among equals.

**The same automatic layout also builds the J-card (`jcard_layout.py` +
`_auto_layout_cover`).** `DesignScene.fold_panel_rects()` splits the cut
shape at its fold lines into front / spine / back (58.85 / 8.3 / 58.85 mm);
it returns `[]` for anything unfolded, so "no panels" and "not a cover" are
the same case for callers. It targets the **plain** J-card template -- the
window variant would cut a hole through the cover artwork.

**Every colour on the card comes from the cover (`palette.py`).** Pillow
quantises a thumbnail of it; the most common swatch becomes the back
panel's background, and the accent for the spine is scored on vividness,
share of the cover, **and distance from that background**. That last term
is not decoration: scoring on vividness alone picked a muted brown out of a
near-black cover that also held a near-white, and on a spine the one you
can see across the room is the better accent. Text colour is only ever
black or white, chosen by WCAG relative luminance -- an automatically
derived mid-tone would look considered and read badly at print size.

**The front cover is rotated *and* stretched, and the scale factors are
crossed because of a Qt detail.** An item's `transform()` (which
`set_item_scale` writes) is applied **after** its `rotation()`, so by the
time the scale runs the quarter turn has already swapped the axes: filling
a Pw x Ph panel needs `sx = Pw / natural_height`, `sy = Ph / natural_width`.
**Getting this backwards is invisible on a square cover** -- the artwork
still turns, only the panel ends up filled the wrong way round, which is
exactly how it shipped wrong the first time. Aspect ratio is deliberately
not preserved (explicit user instruction): a J-card front is nearly square,
and a letterboxed cover with bands of background looks worse than a
slightly stretched one. Rotation is `-90` so the cover's own top edge runs
down the card's left side.

**The front and back panels are laid out in "reading" coordinates and then
turned** (`reading_size()` / `_place_turned()`). The card goes into the case
a quarter turn round, so what is 58.85mm wide and 73mm tall on the sheet is
73 x 58.85mm to the eye -- and **everything on those panels with an "up" has
to turn with it**, not just the cover. The first version rotated only the
artwork and left the front logo and the whole track list upright, which read
sideways in the case.

**Front and back turn in opposite directions** (`clockwise=` on
`_place_turned`): the card wraps around the case, so turning it over to read
the back puts that panel the other way up. Laying both out anticlockwise --
the obvious thing, and the second version -- left the back upside down.
Each mapping falls straight out of its rotation: anticlockwise, reading-y
becomes the panel's horizontal axis and reading-x its vertical axis measured
up from the bottom (so the item's own *width* is subtracted); clockwise is
the mirror, subtracting its *height*. The spine is turned yet differently
(+90 with no reading-space mapping) because a spine is read with the case
standing up, and it was confirmed as looking right that way.

**The back is more than a track list**, after that first version read as
unfinished: an artist/album heading, a rule in the accent colour (the only
other place that colour appears besides the spine), and a running-time
footer. The track block is also **centred vertically in the space it was
given** -- the font search is capped at `MAX_POINT_SIZE`, so a short album's
list comes out well under its allowance, and centring spreads the slack
instead of leaving one dead band at the bottom.

**A Spotify code on the back was considered and dropped -- don't rebuild
it speculatively.** The scannable image itself is free and needs no
auth (`scannables.scdn.co/uri/plain/{format}/{bg}/{fg}/{width}/{uri}`), but
it needs the album's Spotify *URI*, and the only way to resolve one is the
Spotify Web API, which requires a registered app's client id and secret.
Asked; the user chose to leave it out rather than register one. (MusicBrainz
exposes Spotify links without a key and would be the fallback if this ever
comes back, but not every release has one.)

**Text is fitted by search, not calculation** (`_fit_text`): the height of
wrapped text depends on where Qt breaks the lines, which is not worth
re-deriving. It walks down from `MAX_POINT_SIZE` and takes the first size
that fits, so the result is the largest readable one. Past
`TWO_COLUMN_THRESHOLD` tracks the list switches to the two side-by-side
columns `project.py` already knows how to build -- a single column of
fifteen ends up either unreadably small or taller than the card.

**The J-card page is deliberately *not* run through Clip Layers**, unlike
the disc label. Nothing on it overhangs by more than a pen width (and
export clips to the cut path anyway), while clipping would rasterise the
panel blocks and the track list -- turning text still worth editing into a
flat image.

**Unsaved work is guarded by a plain `_dirty` flag, not
`QUndoStack.isClean()`.** Metadata edits, template changes and the automatic
layouts all alter the project without necessarily leaving anything on the
undo stack (a template change *resets* it), so cleanliness there would
report "unchanged" about a project that very much has changed.
`_mark_dirty()` is called from the undo stack's `indexChanged`, plus each of
those paths; `_mark_saved()` from both save routines and at the end of
New/Open -- **building a new project's pages runs through the undo stack**,
so without that last call a brand-new project looks modified before the user
touches it.

`_may_discard_changes()` is the shared guard (Save / Discard / Cancel) and
returns True immediately when `project is None`, which is what keeps the
startup flow from prompting about a project that doesn't exist yet. It
covers `closeEvent`, `_new_design` and `_open_project_path` -- all three lost
work silently before. **`_save_project`/`_save_project_as` had to start
returning bool** for this: choosing Save and then backing out of the Save As
dialog must *not* close the window, which is exactly the case that would
otherwise lose what the prompt was protecting.

**Closing the window returns to the startup screen; it does not quit.**
**File > Close Project** (Ctrl+W) is the same thing from the menu -- it is
literally `self.close()`, so the guard, the startup loop and the re-show
stay in `closeEvent` rather than being copied. It exists because a File
menu whose only exit was "Exit" hid the split entirely: the first thing
that happened after this shipped was closing from the menu and being
surprised not to come back.

`closeEvent` runs the unsaved-changes guard, then hides the window and loops
`StartupDialog` until the user opens/creates something (window re-shown,
event ignored) or cancels it (the close goes through, and with no other
window the app exits). Quitting outright had exactly one route to it before,
and it took the whole app with it -- opening a different project meant
relaunching MDTools.

Three details that are load-bearing here:
- **`_mark_saved()` is called after the guard passes, before the startup
  screen runs.** The guard has already settled the question; without this,
  `_open_project_path`'s own call to it would ask about the same discarded
  changes a second time.
- **The loop is a loop on purpose.** Backing out of the template picker
  means "not that one", so it returns to the startup screen rather than
  quitting. `_run_startup_flow()` (launch) deliberately does *not* loop -- it
  falls back to `_new_design(prompt=False)`, which is what the startup tests
  pin down, and looping there would spin forever against a monkeypatched
  always-Reject picker.
- **`show_startup_dialog=False` now also means "closing just closes".**
  Every test constructs `MainWindow` that way, and they would all stall on a
  modal dialog with nothing to answer it. File > Exit sets `_quitting` for
  the same reason, and clears it again if the close is refused -- otherwise
  a cancelled Exit would leave the window primed to quit silently on the
  next close.

## PySide6/Qt gotchas hit in this codebase

- **Never construct a Qt GUI type (`QColor`/`QPen`/`QBrush`/`QFont`/...) at
  module import time.** Causes a real segfault (exit 139) if it runs before
  `QApplication` exists. Keep such values as plain strings/constants at
  module scope; construct the Qt object lazily inside the function that
  needs it. Grep for `^[A-Z_]+\s*=\s*Q(Color|Pen|Brush|Font|...)\(` at module
  level before considering a feature done.
- **`QGraphicsView.setScene(scene)` does not keep a Python reference.** If
  the only reference to a `DesignScene` is a local var that goes out of
  scope, the scene gets garbage collected out from under the view
  (`RuntimeError: Internal C++ object (...) already deleted`). Always keep
  the scene itself alive alongside the view.
- **`QFormLayout` field `setVisible(False)` does NOT hide the row's
  label.** Use `form.setRowVisible(widget, visible)` (Qt 6.4+) so label+field
  hide together.
- **`QGraphicsItem.scale()`/`setScale()` is uniform-only** — no native
  independent x/y scale. Non-proportional resize is tracked as our own
  `(sx, sy)` via `item.setData(role, (sx, sy))`. For text/images,
  `set_item_scale()` applies that through
  `item.setTransform(translate(origin) * scale(sx,sy) * translate(-origin))`,
  leaving the native `scale()` property at 1.0. **Rectangles/ellipses are
  the deliberate exception**: they're pure vector geometry with no
  resolution of their own, so scaling them via transform (rather than
  actually resizing `rect()`) is exactly what made Tools > Clip Layers'
  rasterization of an enlarged rectangle come out pixelated — the pixmap
  it built was only ever sized for the tiny original `rect()` (all
  `boundingRect()` ever reported), then stretched on screen to the much
  bigger apparent size. So for anything matching `_RESIZABLE_SHAPES`
  (`QGraphicsRectItem`/`QGraphicsEllipseItem`), `set_item_scale()` instead
  resizes the shape's own `rect()` directly (`base_rect_at_creation_time *
  (sx, sy)`, `base_rect` cached once via `BASE_RECT_ROLE` the first time
  it's scaled) and leaves the transform at identity — `boundingRect()`
  then always reports the *real* current size, so any later
  rasterization renders at full resolution regardless of how much the
  shape was resized. `(sx, sy)` still means the same cumulative-since-
  creation factor either way, so `get_item_scale()`, `TransformCommand`,
  Reset to Default, and `.mdproj` serialization (`scale_x`/`scale_y`) all
  keep working completely unchanged. See `canvas/items.py` — reuse these,
  don't reinvent them. **This alone wasn't the whole fix, though** — two
  more corrections were needed on top of it:
  - Clip Layers' own rasterization of a resized rectangle/ellipse
    (`canvas/scene.py`'s `_replacement_pixmap_item()`) needs its own,
    independent correction — see the "clipped rectangle/ellipse"
    architecture note below for why it can't just reuse `pos()` or
    `get_item_scale(item)` directly once the shape's replacement pixmap is
    deliberately oversampled.
  - `rect()` always starts at local `(0, 0)`, so resizing it in place
    (`setRect(0, 0, base_w*sx, base_h*sy)`) alone keeps the shape's
    top-left corner pinned at `pos()` and only grows toward the
    bottom-right, regardless of which resize handle was actually dragged —
    and leaves `transformOriginPoint()` (what native `setRotation()`
    always pivots around) stale at whatever point it was at creation time,
    so rotating an already-resized shape span around a point nowhere near
    its real current center. `set_item_scale()` now also re-anchors
    `transformOriginPoint()` to the *new* rect's own center and solves
    `pos()` so that same scene point stays fixed — same
    `mapToScene(center) → solve pos() for that point` technique used
    throughout this file, just applied to the plain vector item itself
    this time, not a rasterized replacement. Text/image items were never
    affected (their `boundingRect()` never changes shape from a resize —
    they scale via the transform branch above, anchored at
    `transformOriginPoint()` the whole time), confirmed by
    `test_scaling_a_rectangle_keeps_its_center_fixed_in_scene_space` and
    its ellipse/rotation counterparts in `test_item_scale.py`.
- **`QFontDialog.getFont(initial, parent)` returns `(ok, font)` in this
  PySide6 build, NOT `(font, ok)`** as older-Qt docs/intuition suggest.
  Getting this backwards makes `item.setFont(font)` raise `TypeError` inside
  a button's `clicked` slot, which Qt's slot dispatch swallows (prints
  traceback, keeps running) — so clicking "Font..." silently does nothing,
  no crash, no error dialog. Don't trust documentation/memory for Qt static
  dialog methods with bool out-params — verify the actual return order for
  the specific PySide6 version in use (drive the real dialog via
  `QTimer.singleShot` auto-accept and print the raw tuple).
- **A modal `QMessageBox`/dialog `.exec()` blocks forever under
  `QT_QPA_PLATFORM=offscreen`** with no user to click OK. Always monkeypatch
  it out (e.g. `monkeypatch.setattr(SomeModule.QMessageBox, "information",
  lambda *a, **k: None)`) before exercising a code path that might show one.
- **Re-fetching a `QMenu` via `action.menu()` some time after construction
  can raise `RuntimeError: Internal C++ object (QMenu) already deleted`**,
  even though the exact same call succeeds moments earlier and the menu
  works fine live. Don't test menu wiring by re-querying `QMenu` objects
  through the widget tree after the fact — test the thing you actually care
  about directly (e.g. for dock recovery, assert on
  `dock.toggleViewAction()` rather than hunting through the menu bar).
- **`QGraphicsItem::setVisible(False)` automatically clears the item's
  selected state** (documented Qt behavior, easy to forget) — see the
  export-order note above.
- **`QGraphicsTextItem`'s "default" text color is not black** — it's
  whatever the ambient widget palette's `Text` role resolves to, which is
  white under a dark theme/OS setting. A user reported new text looking
  like "no antialiasing, looks bad" — it was actually white-on-white text,
  invisible except for faint antialiased edge fuzz. Confirmed by checking
  `item.defaultTextColor()` right after construction (it read as pure
  white) and by reproducing with a dark `QPalette` forced onto the
  `QApplication` in a test. Fix: `DesignScene.add_text()` now calls
  `item.setDefaultTextColor(QColor("black"))` explicitly right after
  construction, before `_init_item()` — never rely on the palette default
  for anything meant to render on a light, physical label.
- **Painting antialiased content onto a plain `QImage.Format_ARGB32` is
  lower-precision than painting onto `Format_ARGB32_Premultiplied`.** Qt's
  raster paint engine composites internally in premultiplied space
  regardless of the target format, so a plain (non-premultiplied) target
  forces an extra unpremultiply/repremultiply round-trip per pixel —
  visible mainly on partially-transparent edge pixels, i.e. antialiased
  edges against full transparency. A user reported "text rendering is very
  bad quality (no subsampling etc)" specifically about baked/exported
  artwork (small text against a transparent background is exactly the
  worst case for this); `io/png_export.py`'s `render_scene_to_image()` now
  paints onto `Format_ARGB32_Premultiplied` instead — `QImage.save(...,
  "PNG")` still writes an ordinary (non-premultiplied) PNG regardless of
  which format was used while painting, so this only affects rendering
  precision, not the saved file's pixel format. See
  `test_render_scene_to_image_paints_onto_a_premultiplied_buffer`.

**Test pattern for this app:** `QT_QPA_PLATFORM=offscreen
.venv/Scripts/python.exe -c "..."` for quick manual smoke scripts, plus a
`qt_app` pytest fixture (session-scoped `QApplication`) in
`tests/conftest.py` for the real suite.

## Workflow expectations

- Requests often arrive as dense, multi-part messages (several features/
  fixes at once). Track every item (e.g. with a todo list), implement all
  of them, and don't call the turn done until each has either a passing
  test or an explicitly-flagged reason it's out of scope.
- When something is fixed, prove it (an offscreen smoke script or a new
  regression test) rather than just asserting it's fixed. If something is
  flaky or not fully understood, say so plainly rather than overclaiming.
- **Run only the tests relevant to what you just changed while working; save
  the full suite for the end of the task.** It is an integration/regression
  gate, not a progress check -- re-running all of it after every edit is
  wasted time. (Explicit user instruction.)
- The user runs the real app themselves and reports back concrete, specific
  symptoms — take those reports literally and reproduce them exactly rather
  than generalizing away from the specifics.
- **Physical/geometric specs often arrive in fragments across multiple
  messages, and later corrections can invalidate the entire previous
  reading, not just one number.** The cover template took three rounds to
  pin down: round 1's numbers actually described the 3D box, not the flat
  label; round 2's fix was also wrong; round 3 ("the whole label size
  should be 126x73mm, folding lines make an 8.3mm section in the center")
  was the first complete, unambiguous spec. Don't build adjacent features on
  top of an ambiguous physical reading until the core numbers are confirmed
  final — a good signal a spec is final is the user restating it as one
  clean, self-contained sentence rather than another incremental tweak.
- Don't assume an earlier session's feature request is still wanted without
  checking current state — scope has been actively simplified before (e.g.
  an ellipse/shape tool was added, then explicitly dropped from the UI
  while keeping the underlying scene method for test scaffolding).
- **Refreshing the dev-package zip (a plain "repackage current source" ask)
  needs only a content diff, not a full install+build cycle.** Extract to a
  scratch dir and `diff -rq` against the live source tree (excluding
  `.venv`/`.claude`/`__pycache__`/`.pytest_cache`/`*.egg-info`). Reserve the
  full fresh-venv + `pip install` + pytest + PyInstaller verification for
  when the packaging *approach* itself changes (new files added to the
  include list, a build script edited, etc.) — the first time the zip was
  built, that full pipeline was worth running for real; repeating it on
  every later refresh was explicitly called out as unnecessary.
- **The user manual is generated, and lives in three languages at once.**
  `doc/` holds a PDF per language; the text is in
  `scripts/manual/content_{en,pl,ja}.py` and the figures come from
  `scripts/manual/make_screenshots.py`, which builds a demo project and
  grabs each dialog rather than anyone capturing them by hand. Two things
  follow. First, a UI change that renames a menu item or moves a control
  invalidates **forty-eight screenshots** (sixteen figures x three
  languages), not one -- rerun the generator
  rather than patching a figure. Second, the Polish and Japanese manuals
  show Polish and Japanese screenshots, so the menu names quoted in their
  text have to match `i18n/mdtools_{pl,ja}.ts` exactly; a rename means
  editing the translation *and* the manual text. The generator runs in
  `QStandardPaths` test mode and stubs `mdrem.MDRemClient`/
  `foobar.FoobarClient`, so it can safely run while the real app is using
  the serial port.
- **Adding a new built-in template no longer needs a manual edit of the
  live per-user `templates.json`.** Earlier in this project, every new
  built-in template required hand-editing
  `%LOCALAPPDATA%/MDTools/templates.json` via a one-off script so it
  showed up immediately for real-app testing, since the per-user file is
  normally only seeded from `defaults.json` once, on first run. That gap
  is exactly what `registry.sync_builtin_templates()` (called from
  `main()` on every start) now closes automatically — adding a template to
  `defaults.json` is sufficient; it reaches the live file the next time
  the app runs, no manual sync step needed.
