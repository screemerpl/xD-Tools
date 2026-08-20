# xD-Tools

A PySide6 desktop workbench for three retro music media -- MiniDisc, CD-R
and compact cassette. It has outgrown its own name twice: first as a
MiniDisc "label designer" that had started recording and titling discs,
then as "MDTools" once CD-R and cassette arrived. **"xD-Tools - Retro
Media Studio"**, with the x standing in for M or C.

- designs disc labels, J-cards, case inserts, tray cards and cassette
  shell labels, exporting SVG (cut/fold shapes only) and PNG (print
  artwork, clipped to the cut outline) for a Cricut cutting machine plus a
  regular printer, and prints or exports whole sheets of them itself;
- with an MDRem infrared adapter, records an album from foobar2000 onto a
  MiniDisc deck with a track mark at every song, writes the disc and track
  titles onto the disc, and stands in for the deck's remote;
- rips an audio CD to FLAC, identifies it on MusicBrainz from its table of
  contents, loads it into foobar2000 in disc order, and records that;
- burns an audio CD-R with CD-Text, resampling to Red Book on the way;
- records a cassette side by side, splitting the album where the tape runs
  out -- a deck nothing here can drive, so it tells the user what to press.

**The app is called xD-Tools everywhere a person reads it, and MDTools in
three places where a name is an address.** The visible half was swept in
one go (every `tr()` string, the startup window's title, the file-dialog
filter, the three User-Agents, the comment cdrecord's `.inf` files carry,
and the built program itself -- `xD-Tools.exe`, matching the installer,
which already called itself that). What is deliberately left alone, and
must stay left alone:
- **`app.setApplicationName("MDTools")`** in `main.py`.
  `QStandardPaths.AppConfigLocation` is built from it, so renaming it moves
  `%LOCALAPPDATA%/MDTools` and takes `templates.json`, `settings.ini` and
  the Telegram session with it -- every customised template silently gone.
  The same trap `setOrganizationName` already carries a warning about.
- **The `"MDTools CD Rip"` and `"MDTools Telegram Downloads"` folder
  names** (`app_settings.py`). They exist on people's disks with their
  files in them; a rename would not move anything, it would just start
  looking somewhere else and report the downloads missing.
- **The package, the repository and its URL** (`mdtools`,
  `github.com/screemerpl/MDTools`), which are what they are.

A rename of a translated string makes lupdate see a new string and mark
the old one `vanished` (not `obsolete` -- both forms exist and only the
first was being looked for at one point). The ten translations were
carried across by matching the retired source modulo the rename rather
than by translating ten sentences again.

Keep the window title, Help > About, the README, `pyproject.toml`'s
`description` and the user manual in step when that scope shifts again --
every one of them described a "label designer" long after it stopped being
only that, and each was found separately, at a different time. This file
is the same kind of hazard: the notes below outlive the state they were
written about, so when one says work is outstanding, check before
believing it.

**Treat physical accuracy as load-bearing.** Output gets cut with a blade —
mm dimensions and the cut-vs-print separation are not cosmetic details, they
are the actual product. Don't round, approximate, or "simplify" geometry
without checking.

## Stack

- PySide6 (`QGraphicsView`/`QGraphicsScene` as the vector canvas, `QtSvg`
  for export, `QtSerialPort` for the MDRem adapter, `QtPrintSupport` for
  printing -- all of it inside the one wheel, which is why none of those
  features added a dependency)
- Pillow (grayscale conversion, cover palettes, opaque-content bounds)
- Telethon (the Telegram bot integration, an experimental feature)
- PyInstaller for standalone builds (`scripts/build_windows.ps1`,
  `scripts/build_linux.sh`), NSIS for the Windows installer
  (`scripts/build_installer.ps1`)
- pytest + pytest-qt, run via `.venv/Scripts/python.exe -m pytest -q`

## Layout

```
src/mdtools/
  main.py                  entry point
  app_window.py             MainWindow: page switcher, menus, docks, undo group, wiring
  project.py                Project / ProjectMetadata / Track / TextStyle, media and their pages
  constants.py              MM_PER_INCH plus mm_to_px()/px_to_mm(), which read the DPI setting
  app_settings.py           every global setting: DPI, MDRem, foobar, rip folder, Telegram
  recent_projects.py        the last five projects, for File > Open Recent and the startup screen
  user_paths.py             where every file dialog starts: Documents/MiniDiscProjects, Pictures
  theme.py                  the flat dark theme: one palette and one stylesheet, sharing their colours
  commands.py               QUndoCommand subclasses (add/delete/reorder/transform/property-edit)
  clipboard.py              in-memory copy/cut/paste (reuses project_io's item (de)serialization)
  grayscale.py              the desaturation + brightness/contrast maths, shared by preview and export
  printing.py               sheet layout: pack copies, search arrangements, paint placements (no Qt UI)
  gallery.py                bundled asset gallery (assets/img) + per-user downloaded-covers cache, merged
  metadata_lookup.py         iTunes Search API: track list + release year + cover art, given Album + Artist
  musicbrainz.py            identifying a CD from its TOC alone -- a CD carries no text (no Qt UI)
  embedded_cover.py         the cover art and tags inside a FLAC file, as a last resort (no Qt)
  mixtape_cover.py          draws a cover for a compilation, which by definition has none
  palette.py                background/accent/text colours pulled out of a cover image (Pillow, no Qt)
  mdrem.py                  MDRem IR adapter: serial protocol, transliteration, upload plan (no Qt UI)
  foobar.py                 foobar2000 via its Beefweb REST API *and* its command line (no Qt UI)
  cdrip.py                  audio CD: drives, TOC, disc ids, rip plan, cdparanoia/flac (no Qt UI)
  decode.py                 what an audio file is, and Red Book PCM out of it (no Qt)
  cdburn.py                 audio CD-R: burn plan, *.inf CD-Text, cdrecord (no Qt UI)
  audio_folder.py           which files in a folder are the album, and in what order (no Qt)
  album_sort.py             one folder of downloads split into one folder per album (no Qt)
  tape.py                   where a cassette is turned over: sides, leader tape, lengths (no Qt)
  multidisc.py              where an album too long for one disc is cut into several, and
                            what a disc-number tag means (no Qt)
  telegram_bot.py           Telethon behind one class: sign-in, chat, downloads (experimental)
  translate.py              MyMemory, for showing a bot's message in the user's language
  auto_layout.py            places cover art on a disc label and the logo on its slider (no Qt UI beyond items)
  jcard_layout.py           builds the three J-card panels: front cover, spine band, track list (no Qt UI)
  cd_layout.py              the CD ring, the folded slim-case insert and the jewel case tray card
  tape_layout.py            the cassette inlay (jcard_layout's own card) and a label per side
  _build_credentials.py     gitignored, written by the build scripts -- the Telegram API id/hash
  i18n/
    __init__.py               language setting persistence + QTranslator install (ours and Qt's own)
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
    icons.py                     bundled Twemoji SVGs, rendered through QSvgRenderer
    tool_panel.py               icon-only add text/rectangle/image buttons + "insert from metadata" menu + Clip/Bake Layers
    properties_panel.py         edit selected item (position, rotation, multiline text, font, color/probe, reset)
    layers_panel.py             list + select + reorder + rename + delete items
    startup_dialog.py           the first screen: recent projects, open, new, multiprint, remote
    new_design_dialog.py        File > New: the medium, then one template picker per page it has
    settings_dialog.py          Window > Settings: DPI, MDRem port, foobar, rip folder, experimental
    experimental_settings_dialog.py   whatever an experimental feature needs, kept out of the stable one
    metadata_dialog.py          album/artist/year/track-list editor + "Lookup Track List..." + "Upload Tracklist"
    cover_preview.py            the cover thumbnail that is also the button for replacing it, plus its lookup
    asset_gallery_dialog.py     Insert Asset: pick one of the bundled gallery images
    grayscale_export_dialog.py  brightness/contrast, previewed against the real scene, before the save path
    print_dialog.py             PrintDialog and MultiprintDialog over one shared base: sheets, PDF, PNG
    mdrem_port.py               resolve_port(): the saved port, a probe, or a warning -- shared by both entry points
    mdrem_upload_dialog.py      preview-then-write dialog + the worker thread driving an upload
    remote_dialog.py            software Sony MD remote, from the startup screen or the Recording menu
    record_dialog.py            Recording > Record from foobar2000: arm, play, watch, hand off to titling
    cd_rip_dialog.py            Recording > Record CD: read TOC, identify, rip, fill playlist, hand off
    folder_record_dialog.py     Recording > Record Folder: a folder of files into that playlist instead
    tape_record_dialog.py       Recording > Record Cassette: a side at a time, with the user working the deck
    burn_dialog.py              Recording > Burn Audio CD: the plan, the verdicts, and cdrecord behind a worker
    erase_dialog.py             Recording > Erase MiniDisc: a guided, ask-the-user-what-you-see erase
    telegram_login_dialog.py    signing in as a user account, over a worker with a live asyncio loop
    telegram_chat_dialog.py     the bot conversation, its download queue, and the hand-off to recording
    about_dialog.py             Help > About xD-Tools
  io/
    svg_export.py               exports just the cut/fold shapes as physically-accurate SVG
    png_export.py               exports print artwork as PNG, clipped to the template outline
    project_io.py               save/load a whole project as one self-contained .mdproj JSON
assets/
  img/                      gallery images, the CD Digital Audio mark and the app icons -- see gallery.py
  icons/                    the Twemoji button icons -- see panels/icons.py and ATTRIBUTION.md
bin/
  win64/                    bundled cd-paranoia + flac + cdrecord + sox, with their DLLs -- see ATTRIBUTION.md
tests/          1400+ tests, all offscreen via QT_QPA_PLATFORM=offscreen
doc/            the built user manual (PDF x3) + doc/img, its generated screenshots -- see doc/README.md
scripts/
  build_windows.ps1 / build_linux.sh   PyInstaller onedir build
  build_installer.ps1 + installer/mdtools.nsi   the Windows installer, NSIS over that build
  clean_windows.ps1 / clean_linux.sh   remove build/dist/__pycache__/etc.
  make_app_icon.py / make_cd_logo.py   the .ico and the Digital Audio PNG, generated once each
  manual/
    make_screenshots.py      drives every dialog and grabs it, once per language
    build_manual.py           blocks -> QTextDocument -> QPdfWriter, with a measured TOC
    content_{en,pl,ja}.py     the manual's text, as block lists
```

## Domain model

**A project's pages are a described list, not a fixed pair.** It really was
a pair until 0.2.0, and that assumption had been written into the page
dropdown, the template picker, `load_project()`'s validation and the print
dialog's two named attributes -- so the first request for a third page (a
CD's jewel case back) would have meant touching all of them. `project.py`
now holds `PageKind`/`PAGE_KINDS`/`PAGE_ORDER` and two functions,
`page_template_kind()` (which template family a page takes -- several pages
share "cover") and `page_title()` (what to call it, which depends on the
medium: a MiniDisc's second page is a J-card, a CD's is a case insert).
`Project.ordered_pages()` lists what a project actually has, in PAGE_ORDER
order, with anything unrecognised appended rather than dropped. Adding a
page is then an entry in `PAGE_KINDS` plus a template, which is exactly
what **`PAGE_BACK`** turned out to cost when it arrived a day later: the
jewel case tray card, 151x117.5mm with two 6.5mm spine folds (the strips
that show down the sides of a closed case, with the 138mm panel between
them sitting behind the disc). Measured off a real case -- the first
guess was 150x118 with a 137mm panel -- and `verified: true` since one was
cut and fitted.

Three consequences worth knowing:
- `MainWindow._refresh_page_combo()` fills the dropdown from the project;
  nothing enumerates pages by name any more, and `_change_page_template()`
  asks `page_template_kind()` instead of "is this the disc page?".
- `load_project()` requires a **disc** page and nothing else. A file with a
  third page is a project from a later version, not an error.
- `PrintDialog` carries `list[_Label]` built from `ordered_pages()`.
  Sharing one sheet is a *two-label* arrangement search
  (`printing._ARRANGEMENTS`), so with any other number each label gets its
  own sheet and the checkbox is checked and disabled rather than left
  offering something that cannot happen. Tests build a real three-page
  project by hand (`test_more_than_two_pages.py`), because nothing in the
  app creates one yet and an assumption removed only in principle is not
  removed.

**The case back is optional, and that is the load-bearing part.** A project
without one is the normal case, so nothing may assume it exists:
- File > New offers it as a third combo whose first entry is `(none)`,
  which is the default -- a checkbox beside a combo would have been two
  controls and two states for one question.
- Templates > **Add Page...** / **Remove This Page** add or drop it later.
  Only optional pages can be removed: the disc and cover pages are what a
  project *is*, and `_remove_page()` says so rather than letting a project
  be emptied. Removing resets the undo stack, for the same reason
  `apply_template()` does -- its commands reference items on a scene that
  is about to be discarded.
- The automatic layout fills it **only when the project has one**, and
  **does not change its template**, unlike the disc and cover halves which
  re-template the page they lay out. That page exists because the user
  added it and chose its shape; replacing that with whatever this method
  preferred would undo their choice.

`cd_layout.build_case_back()` is the two existing layouts meeting on one
sheet rather than a third one: `jcard_layout.place_spine()` for each of the
two side strips, `place_back()` for the panel between them. Both spines get
the same caption on purpose -- which side of a case is visible depends on
how it was shelved, and a card naming the album on only one of them is a
card that is often facing the wrong way.

A **Project** = one Disc Label page + one Cover/J-Card page + metadata
(album/artist/year/tracks) + a project-wide default text style + the physical
**medium** it is for (`Project.medium`, `MEDIUM_MD` / `MEDIUM_CD`), switchable via
a toolbar dropdown. Saved as a single self-contained `.mdproj` JSON file
(images embedded as base64 PNG, not file paths).

- **Disc template**: 37x52mm rectangle, 3mm chamfer top-left corner, 1mm
  fillet on the other three — given directly by the user, `verified: true`.
- **Disc + slider variant ("MiniDisc Disc Label (with Slider)")**: the same
  disc shape, plus a second, fully independent cut shape for the
  cartridge's sliding dust shutter label — 27.5mm x 17.5mm, left two
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
  margin on all sides), with the sliding shutter's notch *cut into*
  the right edge instead of placed as a separate adjacent shape (compare to
  the plain slider variant above, which adds a second independent
  `LAYER_CUT` shape rather than subtracting a hole from the first one).
  The notch is `slider_notch_width_mm`/`slider_notch_height_mm` (27.5mm x
  17.5mm, same footprint as the other slider label, left corners rounded
  `slider_notch_corner_radius_mm` = 2.5mm), flush against the label's right
  edge, positioned `slider_notch_top_mm` (24.3mm) below the label's own top
  edge. **These two numbers are set by where the cut lands, not by what
  they are called** — the buffer below moves the actual edge 0.8mm up from
  whatever this says, so 24.3 puts the cut at **23.5mm** below the label's
  top, which is what the user measured off a cut label. The first reading
  (26mm from the MD's own top edge, converted to 25.2 in label
  coordinates) put the top of the notch 1mm too low, and was reported
  after cutting one. So: change either number and check the *edge*, which
  is what `test_builtin_defaults_include_a_full_disc_label_variant` now
  asserts rather than the raw fields.
  `slider_notch_buffer_mm` (0.8mm) then physically enlarges the notch by
  that amount on its top/bottom/left sides (its right side is already
  flush with the label edge, so there's no material there to clear) — a
  real clearance cut, not a print-only keep-out zone, confirmed explicitly
  by the user ("it needs to be cut as well") after an initial ambiguous
  reading of "not printable" as a print-exclusion concept. `slider_travel_mm`
  (19.4mm) then extends that already-buffered notch further down by the same
  buffered width (confirmed: "it needs to include a buffer"), forming one
  continuous cutout (see `DesignScene._build_full_label_outline`) — the
  channel the shutter sweeps through as the deck pushes it open. It ends
  **62mm** below the label's top, measured the same way as the 23.5 above.
  Built via `QPainterPath.subtracted()` (one `LAYER_CUT` shape with a hole
  in it), unlike the additive slider variant, so `template_clip_path()`
  already excludes the notch correctly with no extra union logic needed.
  Dimensions user-confirmed, `verified: true`.
- **What the "slider" actually is: the cartridge's sliding dust shutter,
  not the write-protect tab** — corrected by the user while reading the
  manual ("Slider ten od naklejki nie sluzy do zabezpieczenia przed
  zapisem a do ochrony przeciwkurzowej"). Everything written here and in
  the manual had called it a write-protect slider, which is a different
  part: a small catch on the cartridge's edge that never gets a label.
  **The geometry was right anyway, and the 18mm `slider_travel_mm` is why**
  — a write-protect tab has no reason to need clearance swept across the
  disc's *face*, whereas a shutter does, which is exactly what that
  measurement was for. So this was purely a naming/explanation error, with
  nothing to re-measure. Fixed in the manual (all three languages, plus a
  note there explaining the part and why the channel must clear its whole
  travel), in `auto_layout.py`/`canvas/scene.py`/`templates/models.py`
  docstrings, and here. **The field names (`slider_*`,
  `slider_notch_*`) and the template names ("... (with Slider)") were
  deliberately left alone**: "slider" on its own is still accurate, and the
  template names in particular are the *match key*
  `registry.sync_builtin_templates()` uses (it appends any bundled built-in
  whose `name` isn't already among the user's), so renaming one would hand
  every existing install a duplicate template alongside the one they may
  have customised. Every remaining "write-protect tab"/"write-protected
  disc" mention — `erase_dialog.py`, `record_dialog.py`,
  `remote_dialog.py`, and the MDRem erase findings further down — is about
  the real write-protect catch and is correct as written.
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
- **CD-R support: the medium is a project-level choice, not a per-page one.**
  `Project.medium` is picked once in `NewDesignDialog` (a combo above the two
  template pickers) and decides which templates that dialog and Templates >
  "Change Template for This Page..." offer at all -- `DiscTemplate.medium` /
  `CoverTemplate.medium` carry the same value, defaulting to `"md"` so every
  template and every `.mdproj` written before CD support existed stays a
  MiniDisc one (that is the truth about them, not a fallback). A project holds
  exactly one disc page and one cover page, so an unfiltered picker would let
  a J-card onto a CD project -- two pages describing different physical
  objects, with nothing to notice it until something got cut.
- **CD disc label (`shape == "cd_label"`)**: a plain annulus -- one circle with
  the spindle hole `subtracted()` out of it, the same single-cut-shape-with-a-
  hole approach `full_label` uses for its shutter notch (and *not* the additive
  two-shapes approach the slider variant uses), so `template_clip_path()`
  refuses to print into the hole with no extra handling anywhere.
  `outer_diameter_mm` / `hole_diameter_mm` define it; `width_mm`/`height_mm` are
  kept equal to the outer diameter so everything that reasons about a
  template's physical footprint (printing, copy packing,
  `crop_to_template_bounds()`) keeps working untouched. Every `slider_*` field
  is meaningless here -- a CD has no cartridge -- and the Template Manager
  hides those rows for this shape. `seed_disc_defaults()` also returns early
  for a CD medium: the "▲ INSERT THIS END" mark says which end of a *cartridge*
  goes into the deck, and a disc dropped onto a spindle has no such end.
- **Where the CD dimensions came from, and the corrections they carried.**
  The user delegated the first pass ("to mozesz sobie znalezc sam w
  internecie"), so unlike every MiniDisc template these started from
  industry sources rather than a ruler: 118mm outer, standard-hub hole
  41mm, and a folded insert of 242 x 120mm folded at 121. **All three of
  those numbers were later replaced by measured ones** and the templates
  are now `verified: true`: the disc label is **117mm outer with a 35mm
  hole**, and the folded insert **240 x 120mm folded at 120** -- two panels
  the same size as the front insert, which is what it always should have
  been (120 beside 121 described one case in two ways, and was spotted
  while reviewing what was still unverified). Its name still says
  "(Standard Hub)" though the hole is no longer the 41mm standard one:
  `sync_builtin_templates()` matches built-ins **by name**, so renaming one
  hands every existing install a duplicate beside the copy they may have
  customised -- the same reason the "... (with Slider)" names were left
  alone. **A slim jewel case takes only a front insert, 120 x 120mm -- not
  124 x 124, and it has no tray card at all**: 124mm is the height of the
  case body, not of the paper (which sits under tabs), and the back of a
  slim case is the bare plastic tray, with no pocket and no spine. So the
  track list gets a *folded* insert instead: right panel is the cover, left
  panel the track list, folded once and read through the clear back of the
  case. That maps straight onto the existing `fold_offsets_mm` machinery,
  so it needed no new page-count concept. The jewel case tray card
  (151 x 117.5, a 138mm panel between two 6.5mm spines) was the last CD
  template to be verified; every built-in template is `verified: true`
  now.
- **The automatic layout branches on the medium** (`_auto_layout_project()`):
  a MiniDisc project gets the full-face label and the J-card, a CD project
  gets `_auto_layout_cd_disc_label()` and `_auto_layout_cd_insert()`. Both
  halves of each target templates *by name*, so the branch is not cosmetic --
  running the MiniDisc layout on a CD project would replace its pages with
  MiniDisc shapes rather than laying them out.
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
variable, or lupdate won't see it. **The flip side of that same rule, easy
to miss because the string argument right next to it looks perfectly
literal: the `tr()` *call itself* also can't be nested inside an f-string's
`{...}` interpolation** (`f"<b>{self.tr('x')}</b>"`) -- lupdate sees zero
occurrences, not merely an unfinished one; call `tr()` on its own line
first and interpolate the *result* instead. Found the hard way twice (see
the Telegram bot integration notes below) -- grep for `f["'].*\{self\.tr\(`
after adding a heading/label built this way. **Every language listed in
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

**Landscape, and a sheet per label -- both forced by a CD project.**
Printing was portrait-only, on the stated reasoning that both MiniDisc
designs fit a portrait sheet comfortably. A CD project breaks that twice
over: its folded slim-case insert is 242mm wide, which no portrait sheet
takes upright (it fits only turned a quarter turn), and the disc label plus
that insert exceed A4's 287mm printable length side by side, so **they
cannot share one sheet in either orientation** -- 242 + 3 + 118 = 363.
`oriented_page_size()` is the one place the paper is turned, so the preview,
`_new_printer()`'s `setPageOrientation()` and a PNG export can never disagree
about which way round it is.

`build_sheet_layout()` packs one label type alone on a page -- the plain-grid
half of `build_copies_layout()` without the two-label arrangement search,
keeping the same "rotation is a fallback, never a default" rule -- and
raises `PrintLayoutError` when not even one copy fits, which is a real
answer rather than a failure to try. `print_sheets()` then prints several
pages in **one** job with `newPage()` between them: a QPainter can only be
opened on a QPrinter once, and starting a second job would ask the printer
dialog again or overwrite the PDF just written. Empty sheets are skipped
rather than emitted blank.

**The preview shows one sheet at a time** (`PrintDialog.sheets()` /
`_show_current_sheet()`), because what is on screen has to be a page that
will actually come out, not a composite of two that will not. Items on the
other sheet are *hidden*, never removed, so flipping back and forth keeps
their positions, rotations and images. Export PNG writes one file per sheet
(`name-1.png`, `name-2.png`) since a PNG holds one page and exporting only
the first would silently lose half a project; a single sheet still writes
exactly the filename that was asked for.

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
form.

**`best_match()` returns None when nothing is actually a match, and the
test for that is two-part.** Found by a user pointing at a folder of
Falling In Reverse's *Popular Monster* -- an album iTunes does not carry at
all -- and getting a one-track cover version of the title track by an
unrelated artist, whose sleeve was then shown as this disc's. Verified live
while fixing: the same search for *Nevermind* used to hand back **Drake's
"Honestly, Nevermind"**, because the real album is not in iTunes' album
search results either.
- `MIN_MATCH_CONFIDENCE` (0.70) on the blended score. A genuine hit is 0.85
  without a known track count and past 0.90 with one; the failing case was
  0.605.
- `MIN_ARTIST_SIMILARITY` (0.40) on the artist alone, and this is the one
  that does the real work -- the blend cannot carry it, because a perfect
  title (0.55) plus a track count that happens to agree (0.15) already
  reaches 0.70 with the artist contributing nothing. Measured against the
  live results: every wrong artist scored under 0.15, while "Falling In
  Reverse & Jelly Roll" against "Falling In Reverse" scores 0.68 and
  "Bowie, David" against "David Bowie" 0.73. Skipped when the caller gave
  no artist, since there is then nothing to judge.

Returning nothing is the point: a wrong *edition* is a nuisance, a wrong
*record* is somebody else's artwork printed on this disc -- and the callers
have a better place to look anyway (`embedded_cover`). Both calls can raise `MetadataLookupError` (caught by the dialog
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

**`mdtools/theme.py` (`apply_theme()`, called once from `main.py` right
after `QApplication` construction) replaces Qt's per-OS default look with a
modern, flat, dark theme -- explicit user request, in two stages.** The
first version was Fusion (already inside PySide6, zero new dependency)
plus a hand-set `QPalette` -- flatter and more uniform than each OS's
native style on its own, dark with a blue (`#2a82da`, KDE Breeze's own
accent) `Highlight`/`Link` colour. Explicit follow-up ("this does not look
very nice") asked for more polish than a bare palette can express --
rounded corners, hover/pressed states, focus rings -- so `theme.py` grew a
second layer, a hand-written QSS stylesheet (`_build_stylesheet()`)
layered on top via `app.setStyleSheet(...)`, while keeping the palette
(`_build_palette()`) as the fallback every widget still uses for whatever
the stylesheet doesn't touch (`QMessageBox`, native file dialogs,
disabled-state colours, text selection). **Kvantum was asked for
explicitly and rejected**: it's a Linux/X11-only Qt style engine needing a
compiled system-level plugin (via qt5ct/qt6ct), which cannot be bundled
into a PyInstaller Windows build at all -- MDTools' primary target -- and
would need the user's own machine to have it installed system-wide even on
the Linux build. A pip-installable theme package (e.g. PyQtDarkTheme/
qt-material) was offered as a third option and passed over for the same
zero-extra-dependency reasoning the palette-only version was chosen for
originally.

**Every colour is a module-level constant used by *both* layers, so the
palette and the stylesheet can never quietly disagree about what "the
accent" is.** `_ACCENT`/`_WINDOW`/`_BASE`/etc. are plain hex strings (not
pre-built `QColor`s -- see the standing "never construct a Qt GUI type at
module import time" rule) interpolated directly into the QSS f-string and
also fed to `QColor(...)` for the palette's `Highlight`/`Link` roles;
`test_the_stylesheet_and_the_palette_agree_on_the_accent_colour` pins this
down directly rather than trusting it by inspection.

**Every QSS rule targets a specific, named widget type -- never a blanket
`QWidget`/`QAbstractScrollArea`/`QGraphicsView` selector.** The disc/cover
design canvas (`canvas/view.py`'s `DesignView`) already sets its own
explicit white `backgroundBrush` regardless of the app palette, added
pre-emptively when the palette-only dark theme first landed, since a
physical label design has to stay legible against white the way it will
actually print, not whatever colour this theme happens to be -- a blanket
background rule in the new stylesheet would fight that exact protection.
`test_the_stylesheet_never_sets_a_blanket_widget_background` guards this
by parsing every selector line out of `_build_stylesheet()`'s own output
and asserting none of them starts with one of those three names, rather
than trusting every future edit to remember the rule by convention alone.

**`scripts/manual/make_screenshots.py` needed the exact same
`theme.apply_theme(app)` call `main.py` makes, or the manual's screenshots
would silently keep showing Qt's old default light theme forever.** It
builds its own `QApplication` rather than importing `main()`, so the two
never shared this call automatically -- caught only because the
screenshots were being regenerated for an unrelated reason (a Telegram
dialog change) right after the Fusion/palette theme first landed, not
from any test (there is no way to compare a generated PNG against "what
the real running app currently looks like" in an automated test). See
`doc/README.md`'s own "Two things worth knowing before editing" section,
which documents this pitfall directly so it's remembered the next time
`main.py` gains another app-wide, purely visual setup step.

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

**Tracks above 25 are written like any other now, and the erase choice
is said per command -- both because the firmware grew the API for it
(2026-08-20), not because anything here got cleverer. Verified through
MDTools the same day, on a real 56-track disc: nothing reported as
skipped and every title landed on its own track, tracks 26-56 included.** Two changes, and
the reasoning behind each is the firmware's own repo, whose CLAUDE.md
holds the measurements:
- **`MAX_TRACK` is 99, not 25.** 25 was the number of *keys on the
  remote*, never a limit of the disc -- a MiniDisc TOC holds 254 tracks
  and an LP2/LP4 recording routinely passes 25. The firmware now types a
  higher number instead of pressing one key (`>25`, then its digits on the
  same keys tracks 1-10 use), confirmed on an MDS-JE480 for tracks 37, 42,
  44 and 50. Nothing in MDTools spells that out: `TITLETRACK <n>` takes
  the whole range and the firmware picks the spelling. **99 is where we
  stop anyway, and it is a real edge, not caution**: the deck's number
  field commits by itself on the *second* digit (established by leaving
  ten seconds before an ENTER that turned out to be unnecessary), so a
  three-digit number would select the first two digits' track and write
  this title over that one's. The firmware warns and sends regardless,
  which is right for a diagnostic tool; here a wrong track number destroys
  a good title on a disc nothing can read back, so those stay reported as
  `skipped_tracks`.
- **`UploadStep.command` is a method taking `clearing`, and the worker no
  longer sends `TIMING COUNT`.** That global lives in the board's RAM
  until it is reset, so the same command meant different things depending
  on what the previous session left behind -- a host wanting certainty had
  to write it before every upload and hope nothing got in between. The
  firmware's `TITLETRACKCLEAR` / `TITLETRACKNOCLEAR` (and the same pair on
  `TITLEDISC`) say it per command and ignore the global, which removes the
  shared state rather than managing it. The estimate is unchanged: `CLEAR`
  clears `max(COUNT, len(title) + 8)` with `COUNT` at its default 40,
  which is exactly what `estimated_step_seconds()` already computed --
  `DEFAULT_CLEAR_COUNT` is now documentation of the firmware's default
  rather than something we set.

**`TITLETRACKNEXT` exists and is deliberately not used.** It skips the
number entirely -- press NEXT, name whatever the deck landed on -- so it
is one press instead of four and has no dependence on `>25` at all, which
makes it the only route to a track past 99 if that ever matters. It is
also the route with no redundancy: `TITLETRACK` opens with STOP and a
track number, so a lost first press still lands on the right track,
whereas one swallowed NEXT silently shifts *every remaining title by one*
with nothing able to report it. That already happened once on the
firmware's own bench (`ST45TEST44`, from a TOC wait 1 s too short). With
no feedback channel, the redundant route is the right default.

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

**A second, deeper "looks frozen" report -- this time the whole window, not
just the progress bar -- turned out to be a real GIL-starvation bug in
`MDRemClient.command()`, not a progress-reporting cosmetic.** `_UploadWorker`
already runs on its own `QThread` (see above), which is the architecturally
correct fix for keeping a blocking `QSerialPort` call off the GUI thread --
but `_read_line()` used to hand `waitForReadyRead()` the *entire* remaining
budget in one call, up to the whole 180 s `TITLE_TIMEOUT_MS` while waiting
on the deck's reply to a title write. A Python `QThread.run()` override
calling into a wrapped Qt blocking method is not guaranteed to release the
GIL for that call's own duration -- PySide/Shiboken sometimes does not, a
known, occasionally-buggy behavior with real reports against exactly this
shape of code (a custom `QThread` subclass making a long blocking call),
and not something verifiable from this codebase alone for `QtSerialPort`
specifically. If the GIL isn't released, every other Python thread --
including the GUI thread's own event loop, and so every Python-level
repaint/slot in the *entire app*, not just this dialog -- is starved for
exactly as long as that one wait call runs, which reads precisely as "the
whole window is frozen" rather than "this dialog's progress bar isn't
moving."

The fix, in `mdrem.py`: both `_read_line()`'s `waitForReadyRead()` and the
new `_wait_for_bytes_written()` helper now poll in a loop, each individual
call capped to `_POLL_CHUNK_MS` (200 ms) rather than ever being given the
full remaining deadline at once. This bounds the *worst case* to one chunk
regardless of whether the GIL is actually released underneath -- a single
blocked call that short is imperceptible either way, where 180 s is not.
The overall per-command timeout is unchanged (still governed by the same
`deadline`/`time.monotonic()` arithmetic as before, just checked more
often), and so is when `cancel()` can take effect -- still only between
whole commands, never mid-exchange, since interrupting a title write
partway would leave the deck's own firmware mid-edit, a protocol concern
this chunking has nothing to do with and does not change.

**No existing test exercised this code path at all** -- every prior MDRem
test (`test_mdrem_ui.py`, `test_record_dialog.py`, `test_erase_dialog.py`)
fakes the *whole* `MDRemClient` with a plain Python stand-in, never
touching `command()`'s/`_read_line()`'s real internals against anything
resembling `QSerialPort`. `test_mdrem.py` gained a `_FakePort` (mimicking
just the `QSerialPort` surface `MDRemClient` actually touches, including
its nested `DataBits`/`Parity`/`StopBits`/`FlowControl`/`OpenModeFlag`
enums, since `mdrem.py` references those off the module-level `QSerialPort`
name directly, not off an instance) plus a `_FakeClock` that replaces
`time.monotonic()` so a 180 s deadline can be exercised without a slow
test. `queue_line(line, deliver_after=N)` lets a test force a reply to only
"arrive" after N polls, which is what
`test_a_slow_reply_is_polled_in_bounded_chunks_not_one_long_wait` uses to
assert directly on `len(port.readyread_calls)` and that every individual
call was `<= _POLL_CHUNK_MS` -- the actual regression this whole fix is
about, not just "does a normal exchange still work."

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

**The remote has two modes, and the split is not "basic and advanced".**
Asked for directly ("czemu na pilocie nie mamy wszystkich mozliwych
klawiszy"). **Standard mode is the physical RM-D10P, key for key** --
which is what the window always was, and why keys were missing: the plastic
remote has no key for them either. Extended mode (`extended_check`, saved
as `app_settings.mdrem_extended_remote()`) adds every remaining code the
firmware's table resolves: tracks 11-25, `CHAR`/`NUM`, `CLEAR2`, `DPRE`,
and a Disc Editing group holding `ERASE`/`DIVIDE`. Four things worth
knowing:
- **What each added key is worth knowing about is in its tooltip**, from
  `_hint_for()` -- `CLEAR2` does nothing in name-edit mode wherever the
  cursor is, `DPRE` is recognised as a recording command but was never
  told apart from the rest of that group, `ERASE` asks on the deck's own
  display and needs ENTER. Those are findings from the firmware's bench,
  and a key labelled "Clear 2" with nothing else said is a trap.
- **`_hint_for()` is a chain of `if`s returning literal
  `QCoreApplication.translate(...)` calls, not a dict on `_Key`.** lupdate
  scans statically: a string reaching `translate()` through a dataclass
  field is invisible to it. Same rule as everywhere else here, in its less
  obvious form.
- **Tracks stop at 25 even though titling now goes to 99.** A track up to
  25 is one code, which is what a button stands for; past that the number
  is *typed* (`>25` and its digits), which is a sequence and belongs to
  `TITLETRACK`.
- **Two columns.** Stacked, extended mode came to 1032px tall -- taller
  than a laptop screen, at which point Qt squeezes the groups rather than
  the window and the track numbers stop being legible. Standard mode is
  short either way, but it shares the layout: a remote whose keys move
  when a checkbox is ticked would be worse than one slightly wider than it
  needs to be.

**Extended mode also types, from the PC's own keyboard -- there is no text
box and no on-screen QWERTY, and both were tried and rejected in that
order.** A text box plus a Type button was the first attempt and was
turned down flat ("to nie maja byc przyciski na UI tylko obsluga samej
klawiatury"); an on-screen keyboard grid was rejected long before, when
this dialog was first built, and for the reason that still holds -- the
RM-D10P has keys because a deck has none, and a computer running this
already has better ones. So `keyPressEvent` sends each keystroke as it
happens. Four details, each of which is a real failure avoided:
- **A space cannot go through `SEND`.** The firmware splits that command's
  arguments on whitespace, so the argument would simply be missing --
  `TEXT` with a lone space fails the same way, since `handle_line` skips
  every space after the command word. `mdrem.character_command()` sends
  the character's own code instead (`RAW 61D20 20`), which is the one
  place this repo restates the `0x61D00 | ascii` formula rather than
  asking the firmware by name. A `SPACE` key name in the firmware would
  retire it.
- **The ASCII fast path in `_type()` exists for that same character.**
  `transliterate()` ends by stripping, which is right for a title and
  turns a pressed space bar into nothing at all, so anything the deck can
  already show goes as it is and only the rest is transliterated.
- **`MIN_CHARACTER_GAP_S` (0.15) paces the keystrokes**, matching the gap
  the firmware leaves inside its own `TEXT`. The deck counts a press only
  after three frames *and* a clear pause; two characters sent back to back
  read as **one key held down**, which is the difference between wrong and
  slow. Only the remainder is waited out, so ordinary typing never waits
  -- fingers are slower than 150 ms. `event.isAutoRepeat()` is dropped for
  the same reason.
- **Nothing in the window may hold the keyboard focus.** Every button was
  already `NoFocus`; the checkbox and the Close button were not, and a
  focused checkbox eats the space bar to toggle itself while a focused
  button eats space and Enter. Guarded by
  `test_nothing_in_the_window_takes_the_keyboard_focus`.

Backspace maps to `DELETE` (which takes the character *under* the cursor,
not the one before it -- the deck has no backspace), Enter to `ENTER`, and
Left/Right to `SCANREV`/`SCANFWD`, which move the cursor in name-edit mode
rather than seeking. Escape is deliberately left alone and still closes
the window. `_EDITING_KEYS` is keyed by plain `int` and looked up as one:
a Qt enum member is not reliably equal to its own numeric value across
PySide versions, and `Qt.Key(n)` raises outright for a key code the enum
has no name for -- which real keyboards do produce.

**Recording > "Remote Control..." reaches the exact same `RemoteDialog`
from inside an already-open project, not just the startup screen --
reported directly.** Before this, using the remote while a project was
open meant closing that project first (back to the startup screen, the
only place it was reachable), for a dialog that has nothing to do with
which label is being designed -- the same "not recording, but the same
deck/adapter" reasoning `_erase_disc()` already established for Erase
MiniDisc, right next to it in the menu. `_open_remote_control()` is the
same three-line shape as `_erase_disc()`: `resolve_port()`, bail if
`None`, construct and `exec()` the dialog. `remote_action` is gated by
`_sync_mdrem_actions()` exactly like the other MDRem entries (hidden
rather than disabled, same "there is nothing it could usefully do without
the adapter" convention) -- the startup screen's own Remote button is
unaffected and still exists, this is a second, independent entry point to
the same dialog, not a replacement.

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

**`mdtools/embedded_cover.py` is the last resort behind the search: the
picture inside the files themselves.** A folder of FLACs ripped from
somebody's own CDs routinely carries the sleeve, and it is certainly the
right one for *this* release where a search result is a guess about it --
but it is still the fallback, on purpose: embedded art is whatever the
ripper attached (often a 300px scan, sometimes a photo of the disc) while
iTunes returns a clean 600x600, which is what a printed label wants. Both
`FolderRecordDialog._fetch_cover` and `RecordDialog._ensure_cover` try it
only when `fetch_into` came back empty; the latter reaches the files
through `PlaylistItem.path`, so an ordinary foobar playlist gets it too,
not just a loaded folder.

**It parses FLAC's PICTURE block directly -- no tag library.** A page of
struct unpacking against a format frozen since 2007 is a smaller thing to
own than a dependency, the same call already made for the MusicBrainz disc
id. Front cover (type 3) wins over any other picture, and the 32x32 file
icons (types 1 and 2) are never used. **ID3v2's APIC frame is deliberately
not attempted** -- three frame layouts, unsynchronisation and optional
compression -- so an MP3 folder simply reports no embedded art rather than
being read badly. `test_embedded_cover.py` checks the parser against
hand-built blocks *and* against a file written by the bundled `flac.exe`
with `--picture=`, because a fixture written from the specification can
agree with itself perfectly and still misread what the real encoder
produces.

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

**Verified on the deck on 2026-08-20: the multi-disc MiniDisc recording
was run end to end with a real two-disc album (Bajm, *Best Of 1978-2018*,
17 + 17 tracks) and behaved as intended.** That covers the part with the
most moving pieces -- the split, a disc recorded and titled without being
asked, the eject, the prompt, the second disc -- and it is the reason the
sorting and the playlist reordering underneath it were measured against
the live foobar2000 first (see the notes below on both).

**Still not through real hardware: the two CD flows.** Burning an album
across several CD-Rs and ripping a set as one album have only ever been
exercised against stand-ins. cdrecord's own `-dummy` ("Simulate only" in
the dialog) runs the whole sequence with the laser off, prompts between
discs included, and is the cheap way to try the first of them.

**This work is 0.3.1, not 0.4.0** -- the user's own call, and not to be
released yet. 0.4.0 is game-media covers, which is a different subject.

**A double album: "Record across several discs" (`multidisc.py` + the
option on `RecordDialog`).** 150 minutes is two MiniDiscs, and a MiniDisc
cannot be turned over the way a cassette can -- so the whole sequence above
runs once per disc: record, wait two seconds, write that disc's titles
*without asking*, eject, ask for a blank one, repeat. Only MiniDisc and, if
it is ever wanted, CD; a cassette already has `tape.py`'s two sides and was
explicitly excluded.

**The asking is what is deliberately removed, and it is the whole point of
the feature.** An album is forty minutes of real time and nobody sits
through it, so a confirmation between the last note and the titles going
out would leave the deck holding an untitled disc until somebody came back
-- which on a MiniDisc is worse than it sounds, since an edited TOC lives
in volatile memory until the disc is ejected. `MDRemUploadDialog` therefore
grew `unattended=True`: it starts on a zero-delay `QTimer.singleShot`
rather than on its Start button, ejects without asking (`_eject(ask=...)`,
which is what `_offer_eject` became), and calls `accept()` on itself from
`_on_worker_finished` so the flow behind it can carry on. What that gives
up is the preview that dialog exists for, so it is paid for beforehand:
every title, and every character the deck cannot show, is on
`RecordDialog`'s own table before the first note plays. A *failed* upload
deliberately does not close and does not advance -- `succeeded` is read
back after `exec()`, and the run stops there rather than ejecting an
untitled disc and asking for the next as though nothing had happened.

**`multidisc.split_discs()` is the same "plan it, let the caller execute
it" split as `mdrem.build_upload_plan()`/`tape.split_sides()`, and follows
tape's two rules**: the running order is never changed (a disc break is a
cut, not a repacking), and the split is balanced rather than the first disc
filled to the brim -- disc two is a whole disc either way, so cramming
disc one only costs the listener a lopsided record. It takes the *fewest*
discs that fit and then minimises the longest one (binary search for the
smallest limit `n` parts can respect, then fill greedily up to it), rather
than scoring every possible cut the way `tape._best_break()` can afford to
with exactly one break to place.

**The capacity is stated, never guessed.** `disc_minutes_spin` defaults to
80 (SP) and the tooltip says LP2 is 160 -- because which mode the deck is
in can neither be read nor set through the MDRem key table, which is the
same reason `DISC_SP_SECONDS` only ever warns. For the same reason the
option is **not** ticked automatically for an album over 80 minutes,
tempting as that is: on a deck set to LP2 that album fits on one disc, and
turning a one-disc recording into a two-disc one on an assumption is
deciding something the warning only points at. The warning does now name
the option, and hides itself while it is on.

**`RecordDialog._multi()` means "the option is on *and* the plan really has
more than one disc"**, so an album that fits keeps the plain single-disc
path (one question about titling, no disc column, no `[1/2]`) whatever the
checkbox says -- nothing downstream has to ask twice.

Details that are load-bearing:
- **The first track of every disc is never marked.** `_begin_disc()` sets
  `_marked_index = first`, for exactly the reason the first track of a
  single-disc recording is never marked: the deck opens a track of its own
  when recording starts, and marking again immediately leaves a
  fraction-of-a-second track at the front.
- **A disc ends by `set_stop_after_current_track`, armed on the transition
  *into* its last track** -- the cassette's own side-break mechanism, for
  the same reason (the flag applies to whatever is playing when it is
  read, so arming it at the start would end the disc after track one).
  `_poll()` also stops the moment it sees an index past the disc's last:
  if the flag did not take, ending here costs a fraction of the next track,
  where letting it run would put the whole of the next disc onto this one.
- **The disc title carries `[n/total]`** (`_disc_metadata`, appended to the
  album name). Two discs of the same album titled identically are
  indistinguishable on a shelf, and the disc title is the only text a
  MiniDisc carries about itself. The tracks are *sliced out of the captured
  whole*, not taken from the plan, so a title corrected in the table is the
  one that reaches the deck -- and slicing is also what renumbers them:
  track 16 of the album is track 1 of disc two, which is how the deck
  numbers it. (It also keeps every disc well under `mdrem.MAX_TRACK`,
  though that is a side effect and not the fix for it -- and since that
  limit became 99 it is not a consideration at all.)
- **`result_metadata` stays the whole album**, every disc of it: the label
  describes the record, not one of its discs.

**Breaks placed by hand, and moving tracks -- both from the same request.**
"Start Disc Here" makes the selected track the first of a new disc and
"Split Automatically" hands the split back to the arithmetic. Placing one
by hand **starts from the breaks already on screen** rather than from none:
a three-disc album has two boundaries, and moving one must not throw the
other away and leave the user to place them all again -- so moving a
boundary is placing the new one and removing the old, which is what the
button's own text spells out for whichever row is selected. Once placed,
they are sticky (`_manual_breaks`), because the arithmetic would otherwise
put its own break back the moment the capacity changed.

**The album's own order comes from the files, before anybody touches
anything -- `foobar.sort_by_disc_and_track()` / `disc_breaks()`, applied in
`RecordDialog._load_playlist()`.** A double album dropped into foobar2000
as one folder does not arrive in album order: both discs number their
tracks from one, so foobar's own sort interleaves them. Measured against a
real 34-track two-disc album in the live install, the playlist came back
sorted *alphabetically by title*; sorted by `%discnumber%` then
`%tracknumber%` it comes out as disc 1's seventeen tracks followed by disc
2's, with the break at index 17. `%discnumber%` is **appended** to
`_COLUMNS`, like every column added before it, so no positional index
shifts.

Three rules keep it from doing harm:
- **A list where nothing carries either number is returned untouched.** No
  tags means no opinion, and a playlist somebody assembled by hand beats
  an order invented here. (This is also the whole of the answer to "only
  when the input is FLAC files": the numbers come from foobar's own
  columns, so any format it can read is covered, and anything untagged
  simply leaves the order alone.)
- **A file missing a track number sinks to the end of its disc**, never to
  the front, and ties keep the order they arrived in -- an odd untagged
  file cannot displace the album.
- **A missing disc number counts as disc 1**, which is exactly what a
  single-disc album's files look like.

**A track list handed in by the caller is parallel to the *old* order and
has to be permuted with it.** `RecordDialog` receives `metadata` from
Record Folder and the Telegram hand-off, built from the files as they sat
on disk; sorting `self._items` without permuting `metadata.tracks` the same
way put one track's title against another track's file -- reported as "the
tracks are in the wrong order, and so is the split", which is what it looks
like from the table. The permutation is taken from the sort itself
(`id()`-keyed positions of the items before it) rather than recomputed, and
applied to `self._given_metadata` before `self._seed` is built from it.

**Sorting the table is only half of it: foobar has to be put into that
order too, and it is, as the dialog opens** (`_push_order_now`, deferred by
a zero-delay `QTimer.singleShot` so the window is up and the status line
readable while the rebuild blocks). Leaving it until Start would work --
`_apply_order_to_foobar()` runs there anyway -- but it would leave the
playlist on screen in foobar2000 disagreeing with the table in MDTools
until a button was pressed, which is the exact confusion that produced the
wrong-track recording in the first place. It runs only when sorting
actually moved something, so an album already in order costs nothing.

**The disc numbers seed the split *and* tick the box.** `_manual_breaks`
starts as `disc_breaks()`, so a two-CD album is offered *the album's own*
split rather than one worked out from running times, and "Record across
several discs" is ticked for it. Leaving that to the user was the first
version and was reported as broken on sight: with the box clear the Disc
column stays hidden, so the table read `01..17, 01..17` with nothing on
screen explaining the repeat. **This is not the same case as an album that
merely overruns 80 minutes, which is still left unticked** -- that one is
an assumption about the deck's recording mode, which cannot be read from
here, whereas a disc number is the album stating what it is. Unticking
puts the whole thing on one disc (which is what LP2 is for), and "Split
Automatically" hands the division back to the arithmetic. The summary line
says where the split came from.

**Up/Down reorder the recording, which means reordering foobar2000's
playlist** -- the recording *is* foobar playing its own playlist, so a
table reordered only here would title the disc in one order and record it
in another, the exact failure the "the playlist is what will be recorded"
rule exists to avoid. `_apply_order_to_foobar()` does it in two ways, in
this order:

1. **`foobar.reorder_playlist()` -- moving the items where they already
   are.** Beefweb's `POST /api/playlists/{id}/items/move` was found by
   probing the live install (204 for `move`/`sort`/`copy`, 405 for a made-up
   route, so these are real endpoints) and its semantics measured there
   too: `targetIndex` inserts the moved items *before* that position and
   leaves everything else in its relative order, so pulling each track
   forward in turn arrives at exactly the order asked for. This touches no
   files, clears nothing and needs neither foobar's executable nor the
   tracks still being where they were -- a failure costs nothing. Each move
   is simulated locally as it goes, because a playlist's indices shift
   under every one of them.
2. **`foobar.replace_current_playlist()` -- the rebuild**, only when
   moving cannot be done at all. It empties the playlist before it can
   refill it, which is why it is no longer the first move. It goes through
   the command line (Beefweb's own add endpoint refuses any file outside
   foobar's configured music folders, which on a normal install is every
   file there is) and **verifies the order that actually landed rather than
   trusting it** -- see the note below on why that is not paranoia.

`reorder_playlist()` declines outright when any entry has no path: they all
normalise to the same string, so the check at the end would report success
having moved nothing -- which is exactly the shape of failure this whole
area keeps producing. Beyond that: it only ever runs when a row was
actually moved, and an order that neither route can reach stops the
recording rather than letting it proceed against a playlist foobar does not
have. `_move_selected()` moves the
seed's own track list alongside `_items`, since everything downstream pairs
the two by index.

**The track table grew a `Disc` column at index 0**, hidden unless there is
more than one disc -- the same shape as the cassette dialog's `Side`
column. Every read of a row is therefore one index further along than it
was; `COL_DISC`/`COL_NUMBER`/`COL_TITLE`/`COL_ARTIST`/`COL_LENGTH` exist so
that shift is stated once rather than counted at each call site.

**Every recording backs foobar2000's own output volume off to
`RECORDING_VOLUME_DB` (-5.0dB) first, via a new `FoobarClient.set_volume()`
-- explicit user request, headroom against clipping on the digital
transfer.** `_start()` calls it right alongside `prepare_for_recording()`/
`stop()`, before `_arm_deck()` -- so this applies uniformly to every
"record via foobar" entry point (plain foobar record, the CD-rip hand-off,
the folder-record hand-off), since they all share this one `RecordDialog`.
Confirmed live, not just from documentation (the same rigor this module's
own header already holds itself to): `GET /api/player`'s own `"volume"`
object reports `{"isMuted", "max": 0.0, "min": -100.0, "type": "db",
"value"}`, and `POST /api/player` with a flat `{"volume": db}` body (same
convention `prepare_for_recording()`'s own flat keys already use) sets it
-- read back afterward to confirm the value actually landed, not just that
the request returned 204. Deliberately does not touch `isMuted`: a muted
player staying muted isn't this call's business.

**Nothing in the recording flow depends on how the audio actually reaches
the deck -- which is why the analogue inputs work with no code at all, and
why the sample rate is a manual note rather than a check.** MDTools presses
the deck's keys over infrared and watches foobar2000's playlist; the audio
path is entirely outside that loop. So recording through the deck's
*analogue* line inputs needs nothing added or branched on anywhere -- it
just costs two extra conversions plus whatever the sound card's output
stage adds, before ATRAC has even started, and makes the deck's input
selector and recording level the user's problem (a digital input has
neither). Documented in the manual's "Analogue instead, if you have to",
deliberately not enforced or detected in code.

The digital path does have one real failure mode, and it is left to the
manual for the same reason: a MiniDisc is 44.1 kHz/16-bit stereo and the
deck's digital input expects to be fed exactly that, so a 96 kHz or 24-bit
stream -- which is what a modern player outputs from hi-res files unless
something is told to convert them -- can be refused outright or drop out
partway, with no way for the deck to report either (same one-way-infrared
limitation as everything else here). The fix belongs in foobar2000:
Resampler (SoX) in the DSP chain at 44100 Hz, output device at 16-bit
stereo, which passes an ordinary 44.1/16 CD rip through untouched. **A
check inside MDTools was considered and rejected**: Beefweb reports the
*playing file's* sample rate, never the output device's format or what the
DSP chain does on the way there, so "this file is 96 kHz" would be a false
alarm for exactly the people who already have the resampler configured
correctly -- the ones who would see it most often.

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

**foobar2000 does not keep the order it is handed on the command line, and
believing it did put the wrong track on a MiniDisc.** Reported live,
mid-recording: an album whose tracks had been reordered in the record
dialog was recorded from foobar's own order instead. `add_files_via_cli()`'s
docstring used to state the opposite as fact ("foobar adds a batch in the
order it receives it"); measured against the live install on 2026-08-19,
handing it `11, 01, 02...` in one `/add` call appends them **sorted by
filename**, so the reordered track went straight back where it started
while MDTools went on playing by its own indices. Nothing in the API turns
that off. Two things follow, and both are in `replace_current_playlist()`:
- **The order is read back and compared, by path** (`_same_order()`,
  normalised for case and separators, since the path we ask with and the
  path `%path%` reports come from opposite sides of the same filesystem).
  Comparing titles would not do -- two tracks can share one.
- **One file per `/add` call is the fallback that works**, measured the
  same way in the same session: a batch of one has nothing to sort against
  and each lands after the last, so the order survives exactly. It costs a
  process per track, which is why the single batch is still tried first and
  kept whenever it happens to come out right (a CD rip's zero-padded names,
  or any album already in filename order, never reach the fallback).
If even that does not produce the order asked for, it **raises rather than
returning**: every caller is about to record or burn what is in that
playlist, and a wrong order found afterwards is a disc that cannot be
un-recorded. Note this also quietly fixed a latent bug in the folder and
Telegram flows, which sort their files with `natural_key` (so `9` before
`10`) and then handed them to foobar, whose own sort is lexicographic.

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

**Burning an audio CD-R (`decode.py` + `cdburn.py`) is the same
plan-then-execute split as ripping, and the planning half is where every
decision lives.** `build_burn_plan()` needs no drive, no QApplication and no
files beyond the ones being burned; it returns every reason a disc cannot be
written *attached to the plan* rather than raised, because the dialog has to
show them all at once, next to the tracks they are about -- stopping at the
first bad file would make fixing an album a matter of one failed attempt per
problem. Those reasons are **codes, not sentences** (`NOT_RED_BOOK`,
`TOO_SHORT`, `TOO_LONG_FOR_DISC`, ...), for the same reason
`decode.AudioProperties.mismatches()` returns bare field names: the wording
has to be translated and neither module has any Qt in it.

**Reading a file's properties is deliberately separate from decoding it.** A
CD-R holds 44.1kHz/16-bit stereo and nothing else, so every source file is
measured against that *before* the disc is committed. `decode._ensure_pcm()`
is the single place that decides which tool runs; every caller above it
thinks only in terms of "a path to Red Book WAV".

**Resampling is SoX, and the choice was measured rather than assumed.** A
48kHz/24-bit album is what a download normally is -- the first real burn
attempt hit exactly that and was refused, because `flac.exe` cannot
resample. ffmpeg was chosen first (it would have brought MP3/M4A/Opus), then
measured: its Windows builds are ~128MB of DLLs, `avcodec` alone 68MB, past
the size GitHub warns about and in every clone forever. SoX does the one
thing needed in 6MB. `convert_command()` is `rate -v` (high-quality
resampler) plus `dither`, which is what makes 24->16 bits sound like the
recording rather than like quantisation noise; effects come *after* the
output file, which is SoX's own argument order.

**What that costs, stated plainly because it was got wrong once:** this SoX
package **cannot read MP3**. The format is in its own list, but decoding one
needs `libmad-0.dll` loaded at runtime and the official release does not ship
it -- established by running it (writing an MP3 fails with "Unable to load
LAME encoder library"). `CONVERTIBLE_SUFFIXES` therefore excludes `.mp3` on
purpose: promising it would turn a clear "unsupported" into a failure half
way through a burn. Dropping a **32-bit** `libmad-0.dll` beside `sox.exe`
would enable it with no code change.

**SoX lives in `bin/win64/sox/`, not beside the other tools, and that is
load-bearing.** It is a 32-bit build; cd-paranoia and flac are 64-bit MSYS2
builds. Unpacking it alongside them overwrote `libwinpthread-1.dll` with a
32-bit copy of the same name -- which happened not to break cd-paranoia only
because it does not import that DLL directly. `zlib1.dll` and
`libpng16-16.dll` collide just as easily. Windows resolves an executable's
DLLs from its own directory first, so one folder per architecture keeps each
set with its own binary; `decode.sox_path()` looks there before falling back
to PATH, and `test_sox_is_kept_apart_from_the_64_bit_tools` guards it.

**A wrong sample rate is a *note*, not a problem, when something can fix
it.** `BurnPlan.notes` is a second list beside `problems`, because `can_burn`
hangs on the latter and a note must never disable the button: with SoX
present a 48kHz track shows "will be converted to 44100 Hz / 16-bit" and the
burn proceeds; without it, the same track is `NOT_RED_BOOK` and blocks.

**CD-Text goes through `mdrem.transliterate()` -- the MiniDisc titler's own
function.** The spec allows ISO-8859-1 (and MS-JIS), but what a given player
does with either is a guess, and that function's contract is already exactly
the one wanted: strip to ASCII and *report* what had no equivalent instead of
dropping it silently. A Japanese title therefore comes back empty with its
characters listed, before the disc is written rather than after -- the same
promise `MDRemUploadDialog` makes about a title going onto a MiniDisc.

**The burner is cdrecord, not cdrdao, and that was forced rather than
chosen.** cdrdao's `.toc` file is a nicer fit for describing a whole disc,
but it has no maintained Windows build: the last official win32 package is
1.1.5 from around 2004 (Cygwin + ASPI, in an OldFiles folder), and
upstream's Windows instructions are stale. cdrecord (cdrtools 3.02a10) is
still built for Windows -- the cdrtfe project publishes those builds -- does
disc-at-once audio with CD-Text, and is packaged by every Linux
distribution, so one tool covers both platforms. See
`bin/win64/ATTRIBUTION.md` for provenance and licence (CDDL, plus GPL
`cygwin1.dll`: that build is a Cygwin one).

**CD-Text goes in through a `*.inf` file beside each WAV** (`-text
-useinfo`), whose field names come from cdrecord's own manual page shipped
in that same package, not from guesswork. Two rules that manual states and
`_inf_quote()` follows: a value runs from the *first* single quote on the
line to the *last*, and **needs no escaping in between** -- so an apostrophe
inside a title must be left alone (escaping it would put a backslash on the
disc), while one at the very end has to be dropped, since there is no escape
sequence to reach for. Filenames stay bare and cdrecord runs with the work
folder as its working directory: the Windows build is a Cygwin one, so
handing it native paths invites translation surprises for nothing, and each
`.inf` has to sit beside its WAV regardless.

**What was established by running the bundled binary, not read anywhere.**
The same discipline cd-paranoia's own surprises taught this project:
- `-scanbus` prints the device list on **stdout** while its warnings go to
  stderr, and two thirds of the lines it prints are not drives (`*` for an
  empty slot, plus a `HOST ADAPTOR` entry).
- The six **"Insufficient privileges" warnings are noise**: `-checkdrive`
  still talked to the drive, and a `-eject` run physically opened the tray.
  The drive obeys cdrecord with no elevation. Reporting one of those lines
  as the reason a burn failed would send the user chasing a permissions
  problem they do not have, which is what `_NOISE` in `_last_useful_line()`
  is for.
- An empty drive answers `-minfo` with "medium not present" and exits 255.
- **`-eject` opens the tray even when the run fails** -- seen on a dry run
  that stopped at "No disk". So it belongs only on the burn command;
  `scan_command()` and `disc_info_command()` must never carry it, or merely
  looking at the drive would spit the disc out.
The real output of the first two is checked in as fixtures in
`test_cdburn.py` (`REAL_SCANBUS_OUTPUT`, `REAL_NO_DISC_OUTPUT`), the same
reason `test_cdrip.py` keeps `REAL_TOC_OUTPUT`. **Still an assumption**,
marked at its own site: the shape of the progress line during an actual
write.

**`burn()` mirrors `cdrip.rip_track()` exactly** -- child output to a *file*
rather than a pipe (an undrained pipe blocks the child; reading it line by
line makes cancelling depend on a line arriving), poll the clock, keep the
log on failure and delete it on success. **The one thing that is not the same
is what cancelling costs**: stopping a rip leaves nothing anywhere, while
stopping a burn leaves a disc that is neither blank nor finished and a CD-R
cannot be rewritten. `burn()` still does what it is told immediately -- the
warning belongs to the dialog. `simulate=True` (cdrecord's `-dummy`) is a
real dry run and exists at this level, not only in the UI, because a wasted
CD-R is this feature's version of a bad cut.

**Verified end to end on real hardware, on 2026-08-19**: a 12-track
48kHz/24-bit album resampled by SoX, written disc-at-once by cdrecord to a
CD-R in an HL-DT-ST DVDRAM GP20N, and read back with `cdrecord -vv -toc` --
12 tracks, lead-out at 41:47, and **`CD-Text len: 634`**, which is the one
thing a `-dummy` run could never show. The scratch WAVs and their `.inf`
files were still in the burn folder afterwards and `burn.log` was gone,
which is only true on the success path.

**One real bug came out of that first burn, and only from comparing the two
halves against each other:** `BurnTrack.sectors` counted `frames / 588`,
which is only true at 44.1 kHz -- so a 48 kHz album was planned as taking
8.8% more disc than it does (45:29 against the 41:45 that came off it). It
now counts `duration_seconds * 75`, because what reaches the CD is the
*resampled* audio. The two agree exactly at 44.1 kHz, which is why it hid
until a hi-res album turned up. It only ever overestimated, so nothing was
ever written past the end of a disc -- but it would have refused an album
that fits.

**Everything that cannot be verified without a disc degrades to "unknown",
never to an error.** `list_burners()` asks cdrecord itself for device names
instead of constructing them (`0,0,0` is scsibus,target,lun as libscg
numbers them -- not derivable from a drive letter), `parse_disc_info()`
treats an unrecognised field as unknown and lets the burn try anyway, and
`parse_progress()` returning None means "no progress information", never a
failure. A burn that finishes correctly with a motionless progress bar is a
cosmetic problem; one that stops because the output read differently would
be a wasted disc. `build_windows.ps1` needed no change for the new binaries
-- it already `--add-data`s the whole `bin/win64` folder.

**Disc breaks are only meaningful once the tracks are in disc order, and
forgetting that offered a 34-track album as 26 discs.** Reported on sight
from the burn dialog. `breaks_from_disc_numbers()` says "a break is where
the number changes", which is right for an album in its own order and
catastrophic for one in filename order: both discs of a set number their
tracks from one, so a folder holding both arrives as `2, 1, 2, 1, ...` and
a break falls at almost every track. The recording dialog never showed it
because it sorts its playlist first. So:
- **`multidisc.order_by_disc_and_track()` is the single rule**, taking
  (disc, track) pairs and returning the order, used by
  `foobar.sort_by_disc_and_track()` for a playlist and by
  `audio_folder.disc_and_track_order()` for files on disk. Two answers to
  "what order is this album in" is exactly the disagreement that produced
  the bug.
- **`BurnDialog` sorts its sources in `__init__`**, before anything is
  measured or split.
- `audio_folder.disc_breaks()` now says in its own docstring that it
  assumes disc order, since it cannot tell.

**The burn dialog carries the recording dialog's table controls, because
they are the same job.** Reported directly -- the burn window had a Disc
column and a checkbox but no way to move a track or place a break, while
the recording window had all of it. Move Up/Move Down, "Start Disc
Here"/"Do Not Start Disc Here" and "Split Automatically" are now in both,
with the same behaviour: hand-placed breaks are sticky and start from the
ones already on screen, and "Split Automatically" hands the division back.
The one difference is what a move costs: the recording flow has to push a
reordered playlist into foobar2000, while a burn hands the files to
cdrecord itself, so here the table simply *is* the disc's running order.

**A set of discs, on both sides of the CD flow.** The same `multidisc.py`
split now drives three media, and the two CD halves each got the half of it
they needed:

**Burning across several CD-Rs** -- "Burn across several discs" on
`BurnDialog`, plus "One disc holds" (80 minutes, or 74 for an older blank;
stated rather than guessed, exactly as the MiniDisc side states its
recording mode). `build_disc_plans()` returns one `BurnPlan` per disc --
a list of one for an ordinary album, so nothing about a single-disc burn
changed -- and the burn runs them in order, ejecting between discs
whatever the Eject checkbox says, because the tray has to open for the next
blank to go in. Details worth keeping:
- **The files are measured once.** `decode.analyze` is memoised across the
  whole call, so splitting an album costs no extra reads of it.
- **The split leaves room for the lead-in**, since `BurnPlan.total_sectors`
  counts one: splitting against the raw stated capacity would produce discs
  that then do not fit.
- **Every disc's CD-Text says which disc it is** (`[1/2]` appended to the
  album), for the same reason the MiniDisc titles do: two discs of one
  album carrying identical text are two discs nobody can tell apart.
- **Each disc gets its own scratch folder.** Track numbering restarts on
  every disc, so one shared folder would leave a longer disc's WAVs sitting
  beside a shorter one's.
- **The next disc is started from `_on_worker_finished`, never from
  `_on_succeeded`** -- the worker is still running there, and its own
  `finished` would clear away the newly started one. The recording flow's
  multi-disc chain has the same shape for the same reason.
- **`can_burn` is checked for every disc**, not for the album: the whole
  thing overrunning is the point, and each disc of it still has to fit.

**Ripping a set as one album** -- "Rip several discs as one album" on
`CdRipDialog`. Each disc is read, identified and ripped on its own, and the
dialog then asks for the next; what carries across is what makes it one
album rather than several:
- **`cdrip.build_rip_plan()` takes a `disc_number`**, which writes
  DISCNUMBER *and* puts the disc in front of the filename. Both are
  load-bearing: the tag is what puts the album back into its own order
  afterwards (`foobar.sort_by_disc_and_track`, and `audio_folder.disc_breaks`
  for the burn), and the prefix is what stops disc two's `01 - ...` landing
  on top of disc one's in the folder they share. A single-disc rip passes
  nothing and is byte-for-byte what it was.
- **One folder for the set**, fixed by the first disc. MusicBrainz
  routinely identifies the second disc as its own release ("... [Disc 2]"),
  and a folder per disc would be two albums.
- **The album, artist and year are put back after each identification**,
  for the same reason. The *titles* are the new disc's own -- those are
  what the lookup is for.
- **`clean_stale_rip_folders()` runs only before the first disc.** It keeps
  the folder about to be written, so running it again would in principle be
  harmless -- but it is the routine that deletes rips, and pointing it at a
  folder that already holds half the album is not a risk worth taking.
- **The playlist is loaded with every disc's files**, not the last disc's:
  `_RipWorker` takes `playlist_paths` for exactly this, and what gets
  recorded afterwards is the album.

**`BurnDialog` is `RecordDialog`'s sibling, and the two differences are
both consequences of the disc being one-shot.** Same editable
album/artist/year, same clickable cover, same editable Title/Artist columns,
same rule that what is on screen when the button is pressed is what gets
written (`track_sources()` reads the *widgets*, never the list it was
constructed with). But: **everything knowable is shown before the button** --
per-track verdicts for anything that is not Red Book or is shorter than the
standard's four seconds, the album's length against the disc's, and every
character CD-Text will have to drop -- because a CD-R cannot be edited after
the fact the way a MiniDisc's TOC can, so "find out on playback" is not a
place to learn any of it. And **stopping is offered but never quietly**:
cancelling during the decode stage costs a scratch folder, cancelling while
the laser is writing leaves a disc that is neither blank nor finished, so
`reject()` asks in those words first. It still never calls `worker.wait()`
on the GUI thread -- the rule the MDRem upload dialog established the hard
way. "Simulate" (cdrecord's own `-dummy`, the laser off) is offered rather than
buried: it is the only way to rehearse a burn without spending a disc.

**`BurnDialog._ensure_cover()` looks the artwork up, which the burn flow did
not do at all at first** -- reported directly ("czemu tu nie ma okladki w
oknie burn?"). The folder gave it names and a year and nothing else, so the
cover box sat empty even for files that carried one, and the album reached
the label with no artwork. It now follows exactly the order `RecordDialog`
established: a search first (iTunes returns a clean 600x600, which is what a
printed label wants), then the sleeve embedded in the files, and never a
search at all for a compilation -- "Various Artists" returns somebody else's
record.

**The tool warning and the plan summary are two labels, deliberately.** A
missing cdrecord must not hide what the plan says about the album -- installing
a tool and re-encoding a hi-res track are separate jobs, and the user may do
them in either order.

**Burning is not gated behind `mdrem_enabled()`**, unlike every other entry
in the Recording menu: it needs the drive, not the infrared adapter. The two
entries (`_burn_cd_from_folder`, `_burn_cd_from_foobar`) both end in
`_run_burn_dialog()`, which after a successful burn *offers* the album to
the open project rather than applying it -- this is reachable with any
project open, including one that has nothing to do with the disc just
written, so unlike the post-recording layout (which follows a flow already
confirmed several times over) it asks, and it does nothing at all unless the
open project is a CD one.

**`audio_folder.album_from_folder()` is the one place in this project that
reads tags without foobar2000, and the module's own docstring used to swear
it never would.** That rule was written for the *recording* path, where the
files go into foobar's playlist first and every title comes back out of
Beefweb -- foobar has to read them to play them, so adding a tag library for
that would have been a dependency for nothing. A burn has no player in the
loop at all: the files go straight to cdrecord, so there is nothing else to
ask what a track is called. It reads FLAC's comment block through
`embedded_cover.flac_tags()` (the parser this project already owns) and
falls back to the filename stem for anything else -- a disc of blank track
names being a worse outcome than one named after its files. Album, artist
and year are decided by majority vote over the files that actually carry the
tag, so one guest-credited track cannot rename the record (the same rule
`foobar.album_title()` and `album_sort._group_display_name()` already
follow), falling back to `guess_from_folder_name()`.

**The Recording menu follows two things now: the adapter setting *and* the
open project's medium** (`_sync_mdrem_actions()`, re-run after Window >
Settings closes and after every File > New / Open, since that is when a
medium can change). A MiniDisc project is not offered "Burn Audio CD"; a CD
project is offered neither the remote, nor erasing, nor the three
record-to-MiniDisc entries. **This is a change of principle, not tidying**:
erasing, the remote and recording all act on whatever disc is physically in
the deck, which has nothing to do with which label is open -- an
independence that was itself deliberate (see the erase dialog's notes). It
loses to a menu that matches the project in front of you, which is what was
asked for. With no project open at all -- only reachable before the startup
screen is answered -- nothing is hidden on medium grounds, because there is
no medium yet.

**Burning is the exception that keeps its own rule**: `burn_folder_action`
and `burn_foobar_action` follow the medium but *not* the adapter, because a
burn needs the drive and not the infrared. The same rule governs the
Telegram entries -- `_burn_from_telegram_downloads()` and the chat dialog's
own "Burn Downloaded Album to CD..." button are ungated, while their
recording twins stay behind `mdrem_enabled()`. Copying the recording gate
across would have hidden CD burning from exactly the person most likely to
want it: somebody with no adapter at all.

`TelegramChatDialog` therefore reports *which* button finished it
(`downloaded_action`, `RECORD` / `BURN`) alongside `downloaded_folder` -- a
folder alone cannot say, since a downloaded album can go to either medium --
and both buttons share `_finish_with()`, so the auto-sort that stops a
multi-album folder being treated as one album cannot apply to one and not
the other. `app_window._burn_folder()` was split out of
`_burn_cd_from_folder()` for that hand-off exactly as `_record_folder_dialog()`
was, and `_burn_cd_from_folder()` stays zero-argument so the menu action
cannot hand it `QAction.triggered`'s `checked` bool.

**Two names were wrong and are fixed.** The page switcher said "Cover /
J-Card" on a CD project, naming a MiniDisc part that project does not have;
`_relabel_cover_page()` rides along on the same medium sync and says "Case
Insert" there. And every pixmap layer read as "DesignPixmap" in the Layers
panel: `layers_panel._label_for()`'s fallback stripped "QGraphics"/"Item"
off the class name, which was right while these were plain Qt classes and
broke silently when they became `DesignPixmapItem` and friends (added to
suppress Qt's own selection decoration -- see canvas/items.py). It now names
what an item *is*, by isinstance, and falls back to the old trick only for
anything unrecognised.

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

**Choosing a folder loads it; the only button is Record.** Two earlier
shapes were both wrong. The first loaded and accepted in the same click, so
the dialog vanished the instant it had anything to show -- and what it has
to show is the point: which album the tags turned out to describe, the
artwork it will be labelled with, and the titles foobar read out of the
files. The second put a "Load Folder" button in front of that, which the
user rejected in one sentence: picking a folder in this dialog *is* the
decision, so asking them to then press a button was asking them to confirm
something they had already done. `set_folder()` therefore calls `_load()`,
Record stays disabled until foobar has actually taken the files, and the
status line says up front that browsing will replace the playlist.
Cancelling after the load leaves the playlist replaced and nothing
recorded, exactly as the CD flow does.

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

**`cd_layout.py` lays out a CD project's two pages, and leans on the
MiniDisc layouts rather than restating them.** `auto_layout.place_cover_on_label()`
already scales artwork to cover a cut shape (deliberately overshooting, since
Clip Layers is what trims it), and `jcard_layout.place_back()` already builds
a track-list panel out of the cover's own colours. What is genuinely
different is physical, and each difference is one decision:

- **The disc is a ring.** Nothing can be printed across the hub, so text
  lives in bands above and below it, each only as wide as the circle is at
  that height -- `_chord_rect()` takes the chord at whichever band edge is
  *further* from the centre, since using the nearer one would push text past
  the cut line. `test_a_band_never_reaches_outside_the_circle` checks the
  corners against the radius rather than trusting an inset.
- **The label's artwork is lightened** (`lighten()`, Pillow, blend towards
  white) rather than having a translucent white rectangle laid over it: the
  result is one ordinary image layer that can be moved or replaced, not two
  layers whose stacking order quietly matters. It is the same problem
  `recolour_insertion_mark()` solves for a MiniDisc, at a scale where
  recolouring the text is not enough.
- **The accent is scored against white, not against the sleeve's dominant
  colour** -- because white is what it will be read on once the artwork
  underneath has been lightened. Scoring it the J-card's way picked a pale
  yellow: correct against dark navy, invisible on the label.
- **The insert is read upright**, unlike a J-card, which goes into its case a
  quarter turn round. That is the only reason `place_back()` grew a `turned`
  flag instead of this module getting a second copy of the panel logic. It
  also grew `heading_scale`, because those heading bands are millimetre
  constants chosen for a J-card's narrow panel, and a slim-case insert is
  twice as wide -- at 1.0 the heading looked lost above a full-height track
  list.
- **Which panel is which follows from the fold**: crease in the middle, left
  half folded behind the right, so the right half faces out at the front and
  the left half through the clear back of the tray. Both stay upright --
  folding about a vertical crease and then reading the other side flips
  left-right twice, which cancels.

**Two bugs here were found by looking at the render, not by reading the
code, and they share one cause.** An item scaled by `set_item_scale()`
carries a transform anchored at its own centre, so `pos()` is *not* its
visible top-left. Placing by `pos()` put the Digital Audio mark half off the
disc -- where Clip Layers removed it outright as being outside the cut shape,
so it did not look misplaced, it was simply absent -- and left the insert's
cover floating in the middle of its panel with white either side. Everything
in this module now positions by the item's real footprint
(`item.mapToScene(item.boundingRect()).boundingRect()`), the same technique
`auto_layout._move_centre_to()` documents, and the tests assert on where
items *land*.

**The "Compact Disc Digital Audio" mark is a real asset, not a drawing.** An
attempt to draw it from memory produced something that plainly was not the
logo (reported in one sentence: "to twoje logo w ogole nie przypomina
oryginalu"). It now comes from Wikimedia Commons' `CDDAlogo.svg`, downloaded
unmodified -- SHA-1 verified against what Commons publishes -- with
provenance, the public-domain-as-a-text-logo status and the trademark note in
`assets/img/ATTRIBUTION.md`. `scripts/make_cd_logo.py` renders it to the PNG
the app actually loads, because `gallery.py` lists raster files only and
`QPixmap` cannot be relied on to read SVG in a frozen build (the same
reasoning `panels/icons.py` gives for going through `QSvgRenderer`). **That
script must not be run under `QT_QPA_PLATFORM=offscreen`** if it ever draws
text again: PySide6 ships no fonts and offscreen finds no system font
directory, so text comes out as empty boxes -- which is exactly how the first
version rendered.

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
  quitting. `_run_startup_flow()` (launch) deliberately does *not* loop --
  see `startup_cancelled` below for what a direct Cancel/close of the
  *first* `StartupDialog` now means there instead; choosing "New Project..."
  and then backing out of the *template picker* still falls back to
  `_new_design(prompt=False)`, which is what the startup tests pin down,
  and looping on that specific sub-case would spin forever against a
  monkeypatched always-Reject picker.

**`self.startup_cancelled` -- Cancel/close on the very first `StartupDialog`
now means "quit", not "silently start an untitled project anyway".**
Reported directly as making the button useless: the original behaviour let
`_run_startup_flow()` return `False` for *any* reason (the dialog itself
rejected, a chosen recent project failing to load, the template picker
being cancelled after choosing "New Project..."), and `__init__` treated
every one of those identically -- fall back to `_new_design(prompt=False)`
and show the main window regardless of what was actually clicked. Only the
*first* case is really "I want out" (the same thing Cancel already means
when `_return_to_startup()`'s own loop is showing this dialog again after a
project closes -- see above); the other two are more local cancellations
that should keep their original fallback behaviour. `_run_startup_flow()`
now sets `startup_cancelled = True` itself, but *only* in the branch where
`StartupDialog.exec()` itself doesn't return `Accepted` -- `__init__`'s own
`elif not self._run_startup_flow() and not self.startup_cancelled:` is what
keeps the other two `False`-returning cases falling back to a fresh default
project exactly as before. `main.py` checks the flag *before* ever calling
`window.show()`:
```python
window = MainWindow()
if window.startup_cancelled:
    return 0
window.show()
```
so a cancelled first launch never paints a window at all, rather than
flashing one open only to immediately quit. Regression coverage:
`test_startup_dialog.py`'s
`test_cancelling_the_startup_dialog_outright_means_quit_not_a_blank_project`
(the actual bug) alongside
`test_cancelling_new_project_after_choosing_new_falls_back_to_default_templates`
(now also asserting `startup_cancelled is False`, pinning down that the
*other* cancellation path is unaffected).
- **`show_startup_dialog=False` now also means "closing just closes".**
  Every test constructs `MainWindow` that way, and they would all stall on a
  modal dialog with nothing to answer it. File > Exit sets `_quitting` for
  the same reason, and clears it again if the close is refused -- otherwise
  a cancelled Exit would leave the window primed to quit silently on the
  next close.

**Experimental features live behind their own menu, their own settings
dialog, and one flag -- Window > Settings' "Show experimental features"
checkbox (`app_settings.experimental_features_enabled()`).** With it off,
`app_window.py`'s `self.experimental_menu` (built once at startup, an empty
menu until a feature lands in it) is hidden via `menuAction().setVisible()`
-- a `QMenu` has no `setVisible()` of its own, `menuAction()` is the actual
`QAction` placing it on the menu bar, and hiding *that* is what hides the
whole menu. `_sync_experimental_menu()` re-reads the flag both at menu-build
time and after Window > Settings closes, same "built once, needs an
explicit re-sync" reasoning as `_sync_mdrem_actions()`. Explicit user
decision: whatever settings an experimental feature needs get their own
dialog (`panels/experimental_settings_dialog.py`'s `ExperimentalSettingsDialog`,
reached from an "Experimental Settings..." entry inside the menu itself, so
it needs no separate gating -- the entry only exists while the menu does)
rather than rows bolted onto the main `SettingsDialog`, so the stable
dialog never carries half-finished feature configuration and a second
experimental feature later gets its own section in the same dialog instead
of either one accumulating unrelated checkboxes.

**Telegram bot integration (`telegram_bot.py` + `panels/telegram_login_dialog.py`
+ `panels/experimental_settings_dialog.py` + `panels/telegram_chat_dialog.py`).**
Built in two phases -- account settings and sign-in first, then the chat
dialog itself -- and both are described below, in that order. The feature
is searching/downloading an album from a Telegram bot the *user runs
themselves*, then handing the files to the existing Record Folder to
MiniDisc flow exactly like any other folder of files. **Explicitly
declined, discussed and refused outright**: any integration with public
bots that redistribute copyrighted albums without authorization (e.g.
`@HiFiAudioBot`) -- downloading from those is receiving an infringing copy
regardless of whether the user separately owns the physical media, which is
legally distinct from ripping your own disc (see the CD-ripping features
above). This plan and the code it produced are for a bot the user controls.

**Why a real user login, not a bot token.** Telegram's Bot API forbids one
bot from messaging another bot -- MDTools can't send a search command to
the user's bot as a bot itself and get a reply. To talk to a bot the way a
person would in the Telegram app, this has to sign in as an actual
Telegram *user account* (phone number + code, optionally a 2FA password)
over the MTProto client protocol, via **Telethon** (pure Python, asyncio,
no required C extension, so it stays easy to freeze with PyInstaller).
That needs its own API ID/API Hash pair from https://my.telegram.org -- a
credential for the application acting as a client, completely unrelated to
whatever bot token the user's own bot uses internally; MDTools never needs
the bot's token at all.

**MDTools' builds carry their own registered API ID/Hash, but it is
**injected at build time and never written into the source tree** --
`app_settings._bundled_telegram_credentials()`.** Explicit user request in
two stages: first "hardcode it so nobody has to go get their own", then
"can it be stored securely in the exe". The honest answer to the second is
**no, and no tooling changes that**: the value must be reconstructed in
plaintext to be sent to Telegram, so any build carrying it yields it to
`strings`, a debugger, or a look at the handshake. Obfuscation would be a
speed bump presented as security, so it was offered as such and not chosen.
What build-time injection *does* solve is the one exposure that is genuinely
irreversible: this repo has a public remote, and a credential in git history
survives a rewrite (forks, caches). So the credentials live outside version
control, and the resolution order is:

1. the per-user override in `settings.ini` (`set_telegram_api_id()`/
   `set_telegram_api_hash()`) -- an explicit user choice always wins;
2. `MDTOOLS_TELEGRAM_API_ID`/`_HASH` in the environment (CI, or a dev who
   would rather not keep a file);
3. `mdtools/_build_credentials.py`, which `scripts/build_windows.ps1`/
   `build_linux.sh` generate from those same variables before running
   PyInstaller, and which is **gitignored** -- keeping one locally is also
   how a dev-mode run gets working credentials. Both scripts leave an
   existing untracked file alone when the variables are unset, so a local
   dev setup is never clobbered by a build, and warn (rather than fail) when
   there is neither.

**Missing credentials are a supported state, not an error.** A build made
without them simply cannot sign in until the user supplies their own, which
is what `ExperimentalSettingsDialog._sign_in()`'s guard and
`app_window._open_telegram_bot_chat()`'s second check both say explicitly --
the latter reports a missing bot username and missing credentials
*separately*, since they fail for unrelated reasons and have different
fixes, and telling someone to "set the bot username" when the credentials
are what is missing would send them to a field that is already correct.
`test_the_credentials_are_not_hardcoded_anywhere_in_the_source_tree` is the
regression guard for the property that actually matters: it scans the
package for a bare 32-hex-digit literal (the shape of an api_hash) and fails
if one is committed. Worth keeping in mind that none of this makes the
credentials a *secret* -- an API ID/Hash identifies the *application* to
Telegram's MTProto API, not the end user; the genuinely sensitive per-user
artefact is the Telethon session at `telegram_session_path()`, and the real
risk from a leaked app id is Telegram rate-limiting or banning it, which the
per-user override above is the escape hatch for. `_open_telegram_bot_chat()`'s own
precondition check narrowed accordingly: API ID/Hash are effectively
always set now, so in practice only a missing bot username still trips it
-- the guard message was updated to say so rather than continuing to
mention two credentials that can no longer actually be missing.

**`ExperimentalSettingsDialog` shows no API ID/Hash rows at all** --
follow-up report ("wciaz w eksperymentalnych ustawieniach widze parametery
API"). Pre-filling two credential boxes with values the user neither
obtained nor needs to know about only invited the question of what they
were for, so both `QLineEdit`s and the my.telegram.org instructions block
are gone; the dialog now starts straight at Bot username. `_sign_in()`
reads `app_settings.telegram_api_id()`/`telegram_api_hash()` directly
instead of from fields, and `_on_accept()` no longer writes them, so a
hand-edited override in `settings.ini` survives pressing OK (guarded by
`test_accepting_leaves_the_api_credentials_untouched`). The empty-credential
guard in `_sign_in()` stays even though the UI can no longer produce that
state -- it is reachable only by deliberately blanking the keys in
`settings.ini`, which is exactly the case worth keeping a clear message
for. Where they live, for reference: the built-in pair in
`app_settings.py` (source, and so the frozen `.exe`), the optional
override under `telegram_api_id`/`telegram_api_hash` in
`%LOCALAPPDATA%/MDTools/settings.ini`, and the separate Telethon session
database at `telegram_session_path()` (`telegram.session`, beside that
same ini).

**`_LoginWorker` (in `telegram_login_dialog.py`) needs a persistent asyncio
event loop, unlike every other `QThread` in this codebase.** Every existing
worker (`_UploadWorker`/`_RipWorker`/`_LoadWorker`) does one bounded job in
`run()` and finishes. This one can't: Telethon's `sign_in()` needs the
*same* `TelegramClient` instance that called `send_code_request()` (the
phone-code-hash is cached on the instance, not the session file) --
disconnecting and reconnecting between "code sent" and "code entered" would
silently trigger a second, wasted code request and risk the user typing a
now-stale code. So `run()` starts its own event loop and keeps it alive
across however long the user takes to read an SMS and type it in (and,
for a 2FA account, a password after that). The GUI thread hands a
code/password into the coroutine blocked on `await queue.get()` via
`loop.call_soon_threadsafe(queue.put_nowait, value)` -- the standard way to
cross an asyncio loop's thread boundary. `submit_code()`/`submit_password()`/
`cancel()` all wait on a `threading.Event` (`_ready`) before scheduling,
guarding the narrow startup race between `QThread.start()` returning and
`run()` actually creating the loop/queues -- in practice unreachable by a
human, but real in a fast test calling these back to back. `cancel()`
follows `MDRemUploadDialog`'s rule: it only takes effect at the next point
the flow is waiting on a queue, not mid network call, and `reject()` never
calls `worker.wait()` on the GUI thread (that's what froze the MDRem upload
dialog for real once already) -- it asks the worker to stop and returns
immediately, and `_on_worker_finished` closes the dialog once the thread
actually exits.

**`TelegramBotClient` (in `telegram_bot.py`) takes a client object as a
constructor parameter rather than building one itself** -- dependency
injection, so its whole request-code/submit-code/2FA-password/signed-in
state machine is unit-tested against a `FakeTelethonClient` test double
(`tests/test_telegram_bot.py`) with no real network or Telegram account
involved, and `telegram_login_dialog.py`'s own tests can substitute the
same fake via `create_telethon_client()` (the *only* place that imports and
constructs the real `telethon.TelegramClient`) to drive the real `QThread`
end to end. Every Telethon exception is translated into one `TelegramError`
at this boundary -- `SessionPasswordNeededError` from `submit_code()` is
deliberately *not* treated as an error (it returns
`SignInResult.PASSWORD_REQUIRED`; 2FA is normal, expected behaviour, not a
failure).

**`app_settings.telegram_session_path()` is derived from `_settings()
.fileName()`'s own parent, not recomputed independently via a second call
to the underlying `AppConfigLocation` lookup.** The autouse
`_isolated_app_settings` conftest fixture isolates every setting in this
module by monkeypatching `_settings()` alone; a path computed any other way
would silently point at the real per-user config directory even under that
isolation, both in tests and by design (this file is Telethon's session
database, equivalent to a live login to the user's real account -- it
belongs beside `settings.ini`, never touched by any cleanup routine, never
embedded in a `.mdproj`, and worth calling out plainly: API ID/Hash and this
session are stored/kept in plain-text/unencrypted form, same as every other
credential-shaped setting in this app -- there's no secret-storage
mechanism anywhere in this codebase).

**Phase 2 -- the actual chat dialog (`panels/telegram_chat_dialog.py`) --
is built.** A generic mini-chat with the bot: shows whatever it sends
(text, inline buttons, a file attachment), lets the user reply, downloads
any file offered, and hands the download folder to
`FolderRecordDialog` exactly like a folder picked by hand -- reached from
Experimental > "Download Album from Telegram Bot...".

**`telegram_bot.py` gained a `ChatMessage` dataclass and five more
`TelegramBotClient` methods (`resolve_bot`, `send_text`, `start_watching`,
`click`, `download`), all following the same boundary rule as Phase 1's
sign-in methods: nothing outside this module ever touches a raw Telethon
object.** `TelegramBotClient` now caches every message it has sent or seen
in a `dict[id, RawMessage]` (`_remember()`), because `click()`/`download()`
need the *raw* message back (their own `.click()`/`.download_media()` do
the real work) while everything above this module only ever holds a plain
integer id. `send_text()` runs its result through the exact same
`_remember()`/`ChatMessage` path an incoming message does, so the dialog
renders our own sent messages and the bot's replies through one code path,
not two. Verified against the installed Telethon (1.44.0) directly rather
than trusted from memory: `message.out` is a real instance attribute set
in `Message.__init__` but invisible to `dir()`; `message.buttons` is
`list[list[MessageButton]]` or `None`; `message.file` is a `File` (`.name`/
`.size`) or `None`; `download_media(file=an_existing_directory, ...)`
picks the message's own suggested filename inside it (checked via
`os.path.isdir` internally -- the caller is responsible for that directory
already existing, same "create it, then use it" rule as
`cdrip.ensure_folder()`).

**`_ChatWorker` extends `_LoginWorker`'s persistent-event-loop pattern from
a one-shot exchange to a *running conversation*.** Same shape (event loop
created in `run()`, client constructed inside it), but instead of finishing
after one exchange it loops for as long as the dialog is open, dispatching
between two `asyncio.Queue`s: incoming bot messages (fed by Telethon's own
`events.NewMessage(chats=entity, incoming=True)` handler -- delivered *on
the worker's own loop/thread*, so no `call_soon_threadsafe` needed for that
direction) and outgoing commands from the GUI thread (send text / click a
button / download a file), which *does* need it, via the same
`_ready.wait()` guard + `loop.call_soon_threadsafe(queue.put_nowait, ...)`
shape `_LoginWorker.submit_code()` already established.

**The single costliest lesson of this phase: a `QThread` that loops
forever (unlike every one-shot worker elsewhere in this codebase) turns
"forgot to mock the client in one test" into a silent, output-less process
crash, not a normal test failure.** `TelegramChatDialog` originally started
its worker straight from `__init__` (auto-connect on open). A test that
substitutes a fake `_worker` object to check `reject()`/`accept()`'s own
shutdown logic (mirroring `test_mdrem_ui.py`'s `BusyWorker` pattern) still
lets construction start a *real* `_ChatWorker` first -- and because that
worker is parented to the dialog (`parent=self`), Qt keeps its C++ object
alive via the parent/child tree regardless of the Python attribute being
reassigned to the fake. Without a mocked client, that orphaned real worker
tries to connect to actual Telegram servers with fake credentials in the
background; and because `_ChatWorker.run()` never returns on its own (no
`_flow()` exit condition short of `cancel()`), it is still "running" when
Python's garbage collector eventually collects the now-unreferenced dialog
sometime later -- at which point **Qt aborts the whole process with
`qFatal()`, not a Python exception**, which is why this showed up as pytest
silently producing zero output and exiting, not a traceback. Two fixes,
both worth keeping in mind for *any* future persistent-loop worker in this
codebase:
- `start_connecting()` is a separate, explicit method, never called from
  `__init__` -- plain construction of `TelegramChatDialog` is now always
  inert (no thread, no network), so any test that just wants to inspect
  initial widget state can't trip over this by accident.
  `app_window._open_telegram_bot_chat()` calls it explicitly, right after
  construction and before `exec()`.
- Every test that *does* call `start_connecting()` must stop the worker
  again (`dialog.reject()`, then pump the Qt event loop until
  `dialog._worker is None`) before the test function returns -- see
  `test_telegram_chat_dialog.py`'s `_shutdown()` helper, called from every
  end-to-end test's `finally` block, and its module docstring for the full
  story. `_LoginWorker`-based tests never needed this because that worker
  finishes on its own after one exchange; anything shaped like
  `_ChatWorker` (loops until cancelled) always will.

**Both `accept()` and `reject()` need the same graceful-shutdown treatment
on `TelegramChatDialog`, unlike `TelegramLoginDialog` (which only ever
needed it on `reject()`).** The login dialog's worker finishes on its own
once signed in, so closing it via "Close" after success never has a live
worker to stop. The chat worker never finishes on its own -- both
"Record Downloaded Albums..." (`accept()`) and "Close" (`reject()`) can be
clicked while it's still happily looping, so both are routed through one
shared `_close_with(finish)` that cancels the worker and defers calling
`finish` (`super().accept`/`super().reject`) until `_on_worker_finished`
confirms the thread actually exited -- never `worker.wait()` on the GUI
thread, same rule as everywhere else this pattern appears.

**The hand-off to Record Folder to MiniDisc reuses `FolderRecordDialog`
completely unchanged, via a new optional parameter on the existing
recording entry point.** `_record_folder()` (the plain menu action) split
into a thin, zero-argument wrapper and `_record_folder_dialog(initial_folder:
Path | None = None)`, which calls `FolderRecordDialog.set_folder()` (already
public, already what the interactive Browse button itself calls) before
`exec()` when a folder is already known -- skipping the browse step
entirely rather than duplicating any of `FolderRecordDialog`'s own
tag-reading/cover-lookup/metadata-reconciliation logic. **The zero-arg
wrapper is not just tidiness**: `menu.addAction(text, callback)` connects
`QAction.triggered`'s `checked: bool` straight through to a Python
callable's positional parameters when the callable's signature allows one,
so wiring the menu directly to `_record_folder_dialog` would have handed
`initial_folder=True/False` on every click -- a real, easy-to-miss
PySide/Qt signal-connection gotcha, not a hypothetical one; see the note
in "PySide6/Qt gotchas" below. Still gated on `app_settings.mdrem_enabled()`
exactly like the plain menu entry, since the actual recording step still
needs the adapter regardless of where the folder came from -- the "Continue
to Record Folder..." button is disabled (with a tooltip) rather than hidden
when it's off, since unlike a menu action it has no `_sync_mdrem_actions()`
equivalent to hide it dynamically.

**Two follow-ups landed after real usage: a bot's photo wasn't showing at
all, and messages stayed in whatever language the bot wrote them in.**

**A Telegram *photo* (sent through the picture picker) has no filename
attribute at all -- reported as "images aren't visible" in the chat
dialog.** `File.name` looks for a `DocumentAttributeFilename`, which only
a real `Document` carries, so a photo's `ChatMessage.file_name`/`file_size`
stayed `None` -- meaning it fell through *both* the buttons branch and the
file/Download branch in `_MessageWidget`, rendering as nothing at all.
`ChatMessage.is_photo` (from `bool(message.photo)`, a real Telethon
attribute distinct from `.document`) is its own flag rather than being
inferred from a missing filename, precisely so nothing downstream has to
know that distinction exists. `TelegramBotClient.download_bytes()` (new,
alongside `download()`) uses Telethon's `file=bytes` sentinel for an
in-memory download -- confirmed via source read (`file is bytes` checked
throughout `telethon/client/downloads.py`) -- since a preview's whole point
is being seen immediately, not saved to disk first. `_ChatWorker` triggers
this automatically (fire-and-forget, via `asyncio.ensure_future` on its own
loop -- not awaited, and a failure is silently skipped, same "a missing
preview isn't worth interrupting the chat over" rule the rest of this
dialog already follows) the moment a photo message arrives, and
`_MessageWidget.set_photo()` scales it down to `_PHOTO_MAX_WIDTH` (320px)
if wider before displaying it.

**Automatic translation (`mdtools/translate.py`) -- explicit user request,
not something inferred.** Every incoming (never outgoing) bot text message
is translated into whatever `mdtools.i18n.current_language()` currently is
and shown as a second, italic line underneath the original -- which is
never replaced, since a translation can be wrong and the original may carry
information (an exact command, a filename) a translation would obscure.
**MyMemory** (mymemory.translated.net), not Google Translate's unofficial
endpoint (what the popular `googletrans` package scrapes) -- explicitly
chosen over it after being asked, for the same reason `metadata_lookup.py`
picked the iTunes Search API over anything needing sign-up: a genuinely
free, *documented* public API needing no key at all, rather than an
undocumented, unsupported scrape that could break or start refusing
requests without notice (a real tradeoff, not just caution -- MyMemory's
quality is noticeably rougher on some inputs, confirmed by hand against the
live API: "Hello, how are you?" came back completely untranslated because
its top corpus match happened to be a bad one, while realistic
bot-style sentences translated correctly). MyMemory's `langpair` **requires
an explicit source** -- `autodetect|<target>` works, a blank/omitted source
is rejected outright with a 403, confirmed against the live service, not
assumed from docs.

**Translation runs through `loop.run_in_executor(None, ...)`, not a direct
`await`, because `mdtools.translate.translate()` is a plain blocking
`urllib.request` call (same shape as `metadata_lookup.py`'s own), and
`_ChatWorker`'s event loop has to keep dispatching other incoming
messages/clicks/downloads while a translation is in flight.** That module
doesn't know or care it's being called from inside an asyncio loop --
exactly the same "this module doesn't assume async; the caller keeps it
off the loop" split already established between `mdtools.telegram_bot`
(genuinely async, Telethon-native) and everything else's blocking-call
convention elsewhere in this codebase.

**Two more follow-ups from real usage: the transcript didn't auto-scroll,
and clicking a button surfaced a raw, alarming-looking Telegram error.**

**Auto-scroll is wired to `QScrollBar.rangeChanged`, not a
`QTimer.singleShot(0, ...)` after inserting a widget.** The first version
did the latter and was reported as "the window doesn't scroll down on its
own" -- a 0ms timer and Qt's own layout recomputation for the
just-inserted widget aren't ordered relative to each other, so the scroll
could fire *before* the transcript's real new size (and so its real new
scrollbar maximum) existed, silently scrolling to the *previous* bottom
and leaving the newest message off-screen. `rangeChanged(min, max)` only
ever fires once the scrollable range has actually changed to reflect the
new content, which is the standard, correct Qt idiom for "always follow a
growing scroll area" -- connected once in `__init__`, so it also covers a
widget growing *after* being added (e.g. a photo preview finishing load),
not just a brand new message.

**Clicking an inline button surfaced Telethon's raw `DataInvalidError`
("Encrypted data invalid") -- confirmed, by reading Telethon's own
`Message.click()`/`MessageButton.click()` source, that this is a genuine
Telegram *server-side* rejection (RPC error `DATA_INVALID`) of that
button's `callback_data`, not a client-side bug.** `message.click(i, j)`
is `self._buttons[i][j].click()`, and `self._buttons` is the *exact same*
list object the public `.buttons` property returns -- i.e. the row/col
`_MessageWidget` renders and what `TelegramBotClient.click()` later
indexes into can never disagree, so there is no off-by-one/stale-index bug
to find here. The alarming stock wording is just Telegram's own published
description for that error code, not a description of what actually went
wrong (nothing about MTProto session security is implicated).
`telegram_bot._describe()` translates `DataInvalidError` specifically into
a message that says roughly that, instead of the raw RPC text -- the same
"translate the handful of failures a user is actually likely to hit"
pattern the other known errors there already follow. **The actual root
cause turned out to be a real gap in this codebase, found from the user's
own follow-up report -- see immediately below.**

**`start_watching()` only ever listened for brand new messages
(`events.NewMessage`), never edits to a message already sent
(`events.MessageEdited`) -- and plenty of bots build a "menu" by editing
one message's text/buttons in place (Telegram's own
editMessageText/editMessageReplyMarkup) as the user navigates, rather than
sending a fresh message every step.** Reported as "the buttons don't do
anything in MDTools, but the bot clearly does something (visible on my
phone)" -- and this is also the real explanation for the `DataInvalidError`
right above, not just a coincidental second bug: once the bot edits its
message, Telegram invalidates the *old* button's `callback_data`
server-side, but MDTools' local cache (`TelegramBotClient._messages`) never
saw the edit and kept serving the stale pre-edit object -- so a click sent
the now-invalid old data, which the server correctly rejected. Two
mechanical facts made the fix small: `events.MessageEdited` is a *subclass*
of `events.NewMessage` (confirmed via its MRO) sharing the same `.message`
shape, so `start_watching()`'s existing single handler function covers both
event types with one extra `add_event_handler()` registration; and routing
an edit through the same `_remember()` the new-message path already uses
*overwrites* that id's cache entry with the freshly edited object for
free, which is what actually fixes the click -- no separate "handle an
edit" branch needed in `TelegramBotClient` at all. The dialog-side fix
(`_on_message_received`, `panels/telegram_chat_dialog.py`) does need its
own branch, though: Telegram keeps a message's id across an edit, so the
same id arriving again means "replace this widget's content in its
current position", not "append a new widget at the bottom" -- appending
would have both left the transcript showing a wrong, stale duplicate *and*
reordered the conversation as though an edit were a brand new message.

**A quick-commands row (`/start`, `/help`) sends through the exact same
`worker.send_text()` the free-text box uses** -- so a one-click shortcut
for the two near-universal bot commands shows up in the transcript
identically to anything typed by hand, no special-cased rendering path.

**Album sorting (`album_sort.py` + "Sort into Album Folders" +
`embedded_cover.flac_tags()`), a "Record Downloaded Albums..." picker for
more than one downloaded album, and an "Open Download Folder" button --
from real usage downloading multiple albums in one chat session.**
`embedded_cover.py` gained `flac_tags()` (reads the `VORBIS_COMMENT`
block) alongside its existing `flac_pictures()`, sharing a new
`_iter_flac_blocks()` generator so the two never duplicate the actual
binary walk. **Load-bearing detail, easy to get wrong by analogy with
`PICTURE`'s block**: `VORBIS_COMMENT`'s own internal lengths are
little-endian (Ogg Vorbis's own comment format, carried as-is inside an
otherwise big-endian FLAC metadata block) -- confirmed against the bundled
`flac.exe`'s real output, not just the written spec, same rigor
`flac_pictures()`'s own real-encoder test already applied.
`album_sort.sort_downloads()` groups a session folder's flat files by
`ALBUM` tag first (decided with the user over other options -- reliable
regardless of arrival order, but only for tagged FLACs), falling back to
*arrival batches* (`batches_from_arrival_order()`: files that arrived as
one unbroken run of file-messages, no other kind of message in between)
for anything untagged -- so non-FLAC files and untagged FLACs still get
grouped, at the cost of being wrong if a bot interleaves a status message
between two tracks of the same album. Returns `[]` and moves nothing at
one group or fewer, which is also what makes a second click, or a
single-album session, a safe no-op with no special-casing needed at the
call site. Folder names go through `cdrip.sanitize_filename()`, not
`user_paths`'s copy -- the latter imports QtCore, which would break this
module's own no-Qt rule, the same reasoning `cdrip.py`'s own copy of that
function already documents.

**Sorting has to work *incrementally*, and the "a single album needs no
folder of its own" guard originally broke exactly that -- reported
directly: two albums were already sorted into folders, a third was
downloaded, and sorting again said "nothing to sort".** Since downloads
accumulate in one folder across every session (see the per-session-folder
note below), "some albums already in subfolders, one album's worth of new
tracks still loose in the root" is the *normal* state after the first
sort -- not a reason to skip the move. `_create_folders_and_move()`'s
`len(groups) <= 1` early return fired unconditionally, so that third
album's files stayed flat while `pick_album_folder()` offered only the two
pre-existing subfolders: the newest album was both unsorted *and*
unrecordable, with the UI claiming everything was fine. The guard is now
`len(groups) <= 1 and not has_album_subfolders(root)` -- one album alone in
a still-unsorted folder genuinely needs no nesting, but once anything has
been sorted, a lone new group is the opposite case. `sort_downloads()`/
`sort_folder()`'s own `len(flat_files) < 2` fast paths had the identical
flaw (a one-track album arriving into an already-sorted folder was stranded
before grouping even ran) and are now just `if not flat_files`, leaving the
real decision to `_create_folders_and_move()`. **Idempotency never depended
on either guard**: both callers only look at files still sitting directly in
`root`, so anything already moved into a subfolder is simply invisible to a
repeat call -- which is what
`test_sorting_an_already_sorted_folder_with_nothing_new_is_still_a_no_op`
pins down alongside the three tests for the bug itself.

**Grouping keys strictly on the ALBUM tag, never on artist+album --
reported directly: a featured-artist credit on one track ("Skillet, Lacey
Sturm") landed in its own folder, apart from the rest of the same record
tagged plainly "Skillet".** The original version keyed each file's group
by its own `f"{artist} - {album}"`, so any per-track ARTIST variance --
which is exactly what a guest feature is -- produced two different dict
keys for what both files agree is one album. Fixed the same way
`ProjectMetadata.is_compilation()`/`foobar.album_artist()` already handle
this same class of problem elsewhere in this codebase: the album's
*identity* comes from the ALBUM tag alone (grouping), and the artist half
of the folder's *name* is decided afterward, from every track in that
group, not from whichever track happened to be read first
(`_group_display_name()`, `Counter.most_common()` over every ARTIST value
seen in the group -- a single collab credit is normally the minority
value, so it loses the vote rather than forking the folder).
`read_album_tag()` also now prefers an ALBUMARTIST tag over ARTIST when a
file has one, same "the album's own credited performer, not whoever's on
this one track" reasoning `foobar.album_artist()` uses -- but that alone
isn't sufficient, since plenty of real-world downloaded files simply have
no ALBUMARTIST tag at all, only a per-track ARTIST that varies on a
collab, which is why the majority-vote fallback still has to exist even
with the ALBUMARTIST preference in place.

**"Record Downloaded Albums..." used to look permanently disabled with
no explanation -- reported directly.** `_update_continue_button()` is now
the single place deciding both its enabled state and its tooltip, called
from both `_on_ready()` (so the reason is visible the moment the dialog
connects, not just after the first download) and `_on_download_finished()`
-- adapter-off takes priority over nothing-downloaded-yet, since fixing
the latter wouldn't help until the former is also fixed. `_on_continue_clicked()`
only asks *which* album (`QInputDialog.getItem()`) when the session folder
actually holds more than one subfolder -- zero or exactly one is already
handled correctly by `audio_folder.list_audio_files()`'s own existing
"recurse only if nothing sits directly in the folder" rule, so there is
nothing else to change for those cases. **It now also calls
`album_sort.sort_downloads()` itself, unconditionally, right before that
check** -- reported directly ("czy ten przycisk automatycznie sortuje
albumy w folderze przed otwarciem okna nagrywania?"). Before this,
clicking straight through to record without first pressing "Sort into
Album Folders" by hand left a multi-album session's files still flat, so
`pick_album_folder()` saw zero subfolders and silently handed back the
whole mixed folder as a single "album" -- mixing every downloaded album's
tracks into one recording with no warning at all. Safe to call
unconditionally because `sort_downloads()` is already idempotent and a
no-op for a single album (`_create_folders_and_move()`'s `len(groups) <=
1` guard) -- there is nothing to special-case at the call site for "only
one album" or "already sorted".

**`pick_album_folder()`'s two strings were using `parent.tr(...)`, which
is wrong for a plain module-level function -- found only by testing it,
not by inspection.** `QObject.tr()` resolves its translation *context* from
the object's own runtime class (confirmed by installing a translator with
two candidate contexts and reading back which one actually won: calling
`parent.tr(...)` where `parent` is a `TelegramChatDialog` instance
resolves under context `"TelegramChatDialog"`, never the literal `"parent"`
identifier `pyside6-lupdate`'s static scan records it under). That
mismatch means a translation supplied under whatever context lupdate
happened to invent would never actually be found at runtime -- and it
would only have gotten worse once `app_window.py`'s "Record from Telegram
Downloads..." action (added later, see below) reused this same helper from
`MainWindow`, since the same two source strings would then need looking up
under a *third*, different context depending on which class happened to
call it. Fixed by
switching to `QCoreApplication.translate("TelegramChatDialog", "...")` --
a fixed, explicit context, exactly the pattern this codebase's own i18n
notes already establish for a translatable string in a plain module-level
function (see project.py's `metadata_menu_entries()` and
layers_panel.py's module-level `_label_for()`). Re-running
`pyside6-lupdate` after the fix confirmed it: the two strings' existing
Polish/Japanese translations carried over automatically onto the new,
correct `TelegramChatDialog` context via lupdate's own same-text
heuristic, and the old `parent`-context entries were marked obsolete.

**"Sort into Album Folders" and "Record Downloaded Albums..." are also
disabled for as long as *any* download is still in flight, not just
whenever nothing has finished yet.** Reported directly. `self._active_downloads:
set[int]` tracks every message id between `download_started` and
`download_finished`/`download_failed` (added/discarded in
`_on_download_started`/`_on_download_finished`/`_on_download_failed`, which
now all call both `_update_sort_button()` and `_update_continue_button()`).
Both buttons check it first -- sorting mid-download could act on a folder
about to gain one more file the sort call already missed, and recording
mid-download risks starting a MiniDisc recording one track short of the
album that's still arriving. `_active_downloads` is discarded on failure
too, not just success, so one failed download doesn't permanently wedge
either button disabled for the rest of the session -- a retry (which goes
through the same `download_started`/`finished`/`failed` signals as an
original download, since `_on_download_requested` calls the same
`_worker.download_file()` -> `_run_download()` path) re-adds and
re-clears it exactly the same way.

**Downloads no longer land in a fresh, timestamped subfolder per chat
session -- explicit user request.** `_flow()` used to build `session_folder`
as `self._download_root / f"telegram-{datetime.now():%Y%m%d-%H%M%S}"`; it
is now just `self._download_root` (the one folder configured in
Experimental Settings) directly, `mkdir(parents=True, exist_ok=True)`'d in
place. Every chat session's downloads now accumulate in the same physical
folder instead of scattering across a new one every time the dialog is
reopened, which is what makes "Sort into Album Folders" (and the two new
standalone Experimental actions below) actually useful across sessions
rather than only within whichever one happens to still be open. The
`session_folder`/`_session_folder` name stayed as-is throughout the file
despite no longer being session-*scoped* on disk -- it is still correctly
"the folder this dialog instance is working with", and renaming it
everywhere (queue items, download tracking, the Open Download Folder
button, every test) was judged not worth the diff for what is now purely a
naming nuance, not a behavioural one.

**Two new Experimental menu actions reach the same operations without ever
opening the bot chat at all -- reported directly as missing.**
`app_window._sort_telegram_downloads()` ("Sort Telegram Downloads into
Album Folders...") and `_record_from_telegram_downloads()` ("Record from
Telegram Downloads...") both act on `Path(app_settings.telegram_download_folder())`
directly, `mkdir(parents=True, exist_ok=True)`'d the same "created on
demand, at the moment it's needed" way `cdrip.ensure_folder()`/
`user_paths.projects_dir()` already are -- there is nothing to sort in a
folder that doesn't exist yet, but no reason to fail over that either.
Neither is gated behind `telegram_chat_action`'s local-session-file check
(`_sync_experimental_menu()`) -- sorting or recording what has already
been downloaded needs no bot connection or sign-in at all, only files
already on disk. `_sort_telegram_downloads()` calls `album_sort.sort_folder()`
(the standalone, tag-only sibling of `sort_downloads()` -- no chat, so no
`message_order`/arrival-batch fallback to lean on) and reports the result
via the same `QMessageBox.information()` wording `TelegramChatDialog._sort_downloads()`
already uses. `_record_from_telegram_downloads()` sorts first too, silently
-- same reasoning as `_on_continue_clicked()`'s own auto-sort fix above: a
folder still holding more than one album's worth of files flat would
otherwise be handed to `pick_album_folder()` (imported from
`telegram_chat_dialog.py`, the exact module-level helper the "Choose
Album" i18n-context fix above was written in anticipation of this reuse)
as if it were a single album -- then calls `self._record_folder_dialog(folder)`,
the same hand-off `_open_telegram_bot_chat()` already uses.

**A file attachment renders *only* in a download queue panel on the right
(`_DownloadQueueItem`, in a `QSplitter` beside the transcript) -- never in
the transcript itself, and downloads at most `_MAX_CONCURRENT_DOWNLOADS`
(3) at once, both by explicit request after the transcript got buried under
one row per track of a whole album.** `_ChatWorker._run_download()` now
opens with `async with self._download_semaphore:` (an `asyncio.Semaphore`,
created in `run()` alongside the worker's other asyncio primitives for the
same "must belong to this thread's own loop" reason those already are) --
everything past that line only runs once a slot is actually free, and
`download_started` (new signal) fires right after acquiring it, which is
what tells a queue row to move from "Queued" to "Downloading". Speed is
derived from consecutive `download_progress` callbacks
(`_DownloadQueueItem.set_progress()`), not reported by Telethon directly,
and throttled to recompute at most every `_SPEED_UPDATE_INTERVAL_S` (0.5s)
-- a raw per-callback delta is noisy (a tiny byte count over a tiny time
slice). `_MessageWidget` lost its entire file-row branch (Download
button, progress bar, status label) to `_DownloadQueueItem`; `_on_message_received()`
now branches on `message.file_name` *before* building any transcript
widget at all, routing to a new `_on_file_message()` instead -- but
arrival-order bookkeeping (`self._message_order`) still has to happen
unconditionally either way, since `album_sort.batches_from_arrival_order()`
needs every message's position, file or not.

**`pyside6-lupdate`'s static scanner does not see a `self.tr(...)` call
nested inside an f-string's `{...}` interpolation at all -- not a partial
miss, a silent zero-scan.** Found by actually grepping the compiled `.ts`
for a string this session had *just* added
(`f"<b>{self.tr('Downloads')}</b>"`) and finding it completely absent, not
merely unfinished -- which is what led to checking every other f-string-
wrapped `tr()` call in the codebase and finding a second, **pre-existing**
one (`experimental_settings_dialog.py`'s "Telegram bot" section header,
sitting untranslated since Phase 1 without ever showing up as a missing
string in any `lupdate` run's own summary count, since it was never seen
as a translatable string to begin with). Both fixed the same way: call
`self.tr(...)` on its own line first, assign the *result* into the
f-string, never the `tr()` call itself. Grep for `f["'].*\{self\.tr\(` to
check for a regression -- this codebase's own existing i18n workflow docs
already say "the literal string directly in the call, never through an
indirection like ... a variable", which covers the *string argument*
losing its indirection; this is the narrower, easier-to-miss flip side of
that same rule -- the *call itself* also can't be indirected through
nesting inside an f-string, even though the string argument right next to
it is perfectly literal.

## Compact cassette

**The third medium, and the first that cannot hold an album in one piece
or be driven at all.** `MEDIUM_TAPE`, three pages (`PAGE_COVER` J-card +
`PAGE_SIDE_A` + `PAGE_SIDE_B`), a recording flow where **the deck is
operated by the user and MDTools only says what to press**.

**`project.MEDIUM_PAGES` is what made a third medium data rather than a
change everywhere.** A medium declares its pages as `MediumPage(page,
optional=False)` tuples; `medium_pages(medium)` reads it.
`NewDesignDialog` builds one template row per page from that (rows created
once for every page *any* medium can have, hidden via
`QFormLayout.setRowVisible` for the ones this medium lacks) and reports
**`selected_templates: dict[page, template]`** -- this replaced the old
`selected_disc_template`/`selected_cover_template`/`selected_back_template`
trio, so anything faking that dialog in a test sets the dict.
`disc_combo`/`cover_combo`/`back_combo`/`disc_label`/`cover_label` remain as
named properties onto `_rows`, because "the disc row" is still worth
naming. `app_window._new_design()`, Add Page... and Remove Page all read
`medium_pages()` now: a cassette is offered no disc page, and which pages
cannot be removed is "the ones this medium marks required", not a
hardcoded (disc, cover) pair.

**`tape.py` decides where the album is turned over -- pure logic, no Qt,
shared by the labels and the recording.** `split_sides(tracks,
total_minutes)` tries every possible break in the *unchanged* running
order and takes the most balanced one that fits; if none fits it returns
the least-overrunning break with `fits` False, because running a few
seconds into the run-out is the user's call (same rule as the MiniDisc
flow's 80-minute warning). Two physical facts drive it:
- **A stated length is both sides together**: a C60 is 30 minutes a side,
  so `side_seconds()` halves it and every check is per side.
- **Every side starts with leader tape, which is not magnetic.**
  `LEADER_SECONDS` (10, the user's own number) of silence is recorded
  first, on *each* side, and comes out of that side's usable time.
`suggested_length()` offers the shortest stocked cassette that fits, and
returns None for an untimed track list rather than guessing. C120 is
deliberately not offered -- the tape is thin enough to stretch and jam.

**Which tape a project is for is saved on the project
(`Project.tape_total_minutes`, round-tripped by `project_io`), not asked
for twice.** The recording dialog writes back the length actually used, so
the shell labels split exactly where the recording did. A label that says
side B starts at track seven, and a recording that turned over after track
six, would each be defensible alone and wrong together.

**`tape_layout.py`: the inlay card is `jcard_layout`'s own card.** A
cassette J-card folds about *vertical* creases into front / spine / flap
and is read a quarter turn round on the sheet -- structurally identical to
the MiniDisc J-card, so `place_front_cover`/`place_spine`/`place_back` are
reused rather than restated. Two things are its own:
- **`build_side_label()`** -- `place_back()` with that side's tracks
  substituted (so a label reads as part of the same set as the flap), plus
  a big side letter in the accent colour down the left. **Each side's
  tracks are numbered from one**, which is what the deck's own counter
  will agree with. It refuses a folded page, and `_page_rect()` uses
  `cut_shape_rects()`, not `sceneRect()`, or everything would be laid out
  against the outline builder's transparent margin.
- **The flap takes three columns** (`FLAP_COLUMNS`), because it is 102mm
  along and 24mm deep: in two columns a normal album's list bottomed out
  at `MIN_POINT_SIZE` and rendered as a grey band. `place_back()` gained a
  `columns` parameter (0 = decide from the track count, as before) and
  `project.track_list_columns(metadata, n)` generalised
  `track_list_two_columns`, which now delegates to it.
- No format logo on the card: a cassette's own marks belong to the shell,
  and inventing one would put a badge on the paper that no real inlay has.

**`TapeRecordDialog` (`panels/tape_record_dialog.py`) needs no adapter and
no drive, so `_sync_mdrem_actions()` gates `record_tape_action` on the
medium alone** -- like the burning entries, never on `mdrem_enabled()`.
Per side: the user presses RECORD and clicks (the only confirmation that
exists), ten seconds of silence run down, foobar plays that side, the user
is told to stop and flip. Three details worth keeping:
- **`FoobarClient.set_stop_after_current_track()`** is new, and it is what
  makes the side break clean. Armed on the transition *into* the side's
  last track, never at the start (the flag applies to whatever is playing
  when it is read). Watching for the playlist to move past the boundary
  instead always records the first fraction of the next track onto the end
  of the side, because a poll can only notice a change after it happened.
- **The cassette length is frozen with the other fields once recording
  starts** -- changing it would move a side break that is already half on
  the tape.
- **Cancelling stops foobar and then says the deck is still recording**,
  because there is no second end to stop from here.

**The templates started as unverified standards rather than
measurements**: `Cassette J-Card` 101.6 x 101.6mm, folds at 65.1 and 77.8
(the 4" x 4" flat card every cassette printer works to: front 2 9/16",
spine 1/2", tuck-in flap 15/16"), and `Cassette Shell Label` 88.9 x
42.9mm. Both are `medium: "tape"` and reach existing installs through
`registry.sync_builtin_templates()`. **The shell label's numbers above are
the guess, not what shipped** -- see "The shell label, once it had been
measured" at the end of this section for the 90 x 40.8mm it actually is,
and why a rectangle with two round holes was wrong in kind. Both are
`verified: true` now.

**The app describes itself as three media now** -- window title
("xD-Tools - Retro Media Studio"), Help > About, README and
`pyproject.toml`. The Polish and Japanese translations and the manual
(all three languages, with regenerated screenshots) were carried through
with it and are current -- `pyside6-lupdate` reports no new strings, and
`defaults.json` holds no `verified: false` template.

### Round two on the cassette

Five things, all from looking at the real thing:

**A shell label is cut around the reel hubs**, and until it was, it was a
plain rectangle with a track list on it -- reported in one sentence
("przecież kaseta ma wycięcia okrągłe gdzie wchodzą rolki"). `CoverTemplate`
gained `hub_diameter_mm` / `hub_spacing_mm` / `hub_centre_from_top_mm`, and
`_build_cover_outline()` subtracts the two circles from the cut path -- one
path with holes in it, the way `cd_label`'s spindle hole and `full_label`'s
shutter notch already are, so `template_clip_path()` refuses to print into a
hub opening with nothing else to change. `Cassette Shell Label` became
90 x 46mm with 24mm holes 45mm apart at this point -- **superseded again**
once it was measured properly: see "The shell label, once it had been
measured" below, where the two holes turn out to be one opening.

**The label carries the sleeve, and its text runs across.** The artwork is
the whole sticker, washed towards white by `cd_layout.lighten()` (at 0.68 --
heavier than a CD label's, because the type on this one is smaller), and
`_auto_layout_tape()` now runs Clip Layers over each side page: that is what
trims the deliberate overhang *and* punches the hub holes through the
artwork. `tape_layout._label_bands()` returns the three pieces of a label
that are not a hole -- the band above the openings, the gutter between them,
the band below -- computed from the template's own hub geometry, so a
corrected measurement moves the text with it. Artist + album go on top, the
side letter fills the gutter (`_fill()`, grown *after* fitting: the font
search caps at `MAX_POINT_SIZE`, which is right for a track list and leaves
a single letter rattling around), and the tracks run along the bottom as one
horizontal line rather than a column -- a label four times wider than it is
tall has no room for a list.

**"label" is a third template family** (`registry.KINDS`), because the side
pages took the "cover" family and File > New would happily give a cassette
three J-cards -- reported directly. Same `CoverTemplate` dataclass, a
different family; `PAGE_KINDS` maps both side pages to it, and the Template
Manager grows an Add > Shell label entry plus the three hub rows (visible
only for that kind). `registry._rehome_moved_builtins()` moves a built-in
whose family changed, **replacing it with the bundled version rather than
carrying the old one across** -- a built-in that changed family here also
changed shape, so its old dimensions describe nothing. This is the one place
sync overwrites instead of appending.

**Every recording source reaches whichever medium is open.** There is no
separate cassette entry any more: `record_cd_action` / `record_folder_action`
/ `record_action` / `telegram_record_action` rename themselves in
`_sync_mdrem_actions()` ("Record CD to Cassette...") and are visible for a
cassette *without* the adapter, because a cassette deck is driven by hand.
`_run_record_dialog()` branches on the project's medium -- a rip is a rip
whichever machine it ends up on, so the branch belongs there and not in four
callers. `_resolve_recording_port()` returns `""` (a real answer) when no
port is needed, which is why callers test it with `is None`.

**A cassette's two shell labels share a sheet; the J-card gets its own.**
`PrintDialog._sheet_groups()` is the general form of "one sheet per label":
a pair that belongs together goes through the same two-label arrangement
search a MiniDisc project's own pages use. Placements are keyed by page
(`by_page`) before being handed to `_rebuild_items()`, since grouping means
the order they are computed in no longer matches `self._labels`.

**Two more from looking at it: the inlay is split by side, and the dialogs
on the way to a recording name the right machine.**

`place_back()` grew `track_columns` (text the caller has already arranged
into columns, which sets the column count) and `heading` (drop the
artist/album block and its rule). `tape_layout.side_track_columns()` builds
a SIDE A block and a SIDE B block from the same `TapePlan` the shell labels
use, so the card says where the tape is turned over -- the one thing it
knows and the reader does not. `build_jcard(..., plan=...)`; without a plan
the whole album is still listed straight through.

The flap also stopped printing at `MIN_POINT_SIZE`, from two changes:
`BACK_PADDING_MM` is now multiplied by `min(1.0, heading_scale)` (6mm of top
and bottom margin is a quarter of a 24mm flap, and only a shallow panel
shrinks -- a CD insert scales *up*, where a wider margin is right), and the
flap passes `heading=False` since the spine beside it already names the
album twice. 12 tracks went from 3.5pt (the floor, and overlapping the
running-time footer) to 4.75pt with nothing overlapping.

`project.medium_name()` is the one place a medium is named on screen, and
`CdRipDialog`/`FolderRecordDialog` take a `medium` argument that is *only*
wording -- the work is identical, but a window headed "Record CD to
MiniDisc" in front of a cassette project tells the user something untrue.
It also gates the 80-minute SP warning, which is a MiniDisc's answer and not
a tape's.

**The shell label, once it had been measured, and one thing it forced.**
The guessed 88.9 x 42.9 rectangle with two round holes was wrong in kind,
not only in size. Measured: **90 x 40.8mm** -- 15.5mm of material above the
opening, the 16mm opening itself, 9.3 below, which is where the height
comes from. Top corners cut off at 45 degrees (`top_chamfer_mm`, and the
6mm is **the cut line itself**, so it takes 4.24 off each edge -- that is
what a ruler laid along the cut reads), bottom ones rounded 1.5.

**The opening is one shape, not two holes** -- a hole for each reel hub
*and*, between them, the window the tape is watched through, so a label
bridging that gap would cover the tape. `DesignScene.reel_window_path()`
builds it as a rounded rectangle whose radius is half its height, which is
exactly two half-circles joined by the rectangle between them, and
subtracts it the same way the CD label's spindle hole is subtracted.

That geometry moved the layout, and this is the part worth remembering:
**the middle of the label no longer exists**, so the side letter cannot sit
between the reels. `_label_bands()` now returns the band above the opening,
the column *beside* it and the band below; the tracks take the deeper band
(15.5mm) and the album's own name the shallower one (9.3). The top band is
also inset by the chamfer's own leg on each side -- a full-width block at
the very top would otherwise begin inside a corner that has been cut off,
which is what `test_nothing_is_printed_where_the_reel_holes_are` caught.

Both cassette templates are now **`verified: true`** -- the J-card was cut
and fitted, the label measured off a real shell.

**`PrintDialog` grew "Print This Sheet..."**, beside Print... and visible
only while the labels are on separate sheets (`current_sheet_index()`
returns None otherwise, and `MultiprintDialog` never has a choice to make).
It exists because a printer's own dialog counts pages of a *job*, and each
sheet only becomes a page once the job has been built -- so reprinting the
one that jammed had meant printing the whole set again. `_on_print()` and
`_on_print_current_sheet()` both go through one `_print(sheets)`.

**The tray card, after it was measured and looked at.** 151 x 117.5mm --
a 138mm panel fold to fold, between the two 6.5mm spines, which were
right first time. Its own two corrections are worth keeping:
- **`place_back()` grew `track_fill`** (default 1.0, the tray card passes
  `BACK_TRACK_FILL` = 0.7). The list is fitted into that share of the
  leftover space and then centred in *all* of it, so the slack is shared
  above and below. At 1.0 a twelve-track album stretched across 138mm read
  as a poster rather than as a sleeve -- reported directly. Every other
  caller is unchanged: on a J-card flap or a shell label the list has to
  work to fit at all, and there is no slack to leave.
- **`cd_layout.place_back_logo()`** puts the Digital Audio mark in the
  panel's bottom-*right* corner, because place_back's own footer (the year
  and the running time) already holds the bottom-left. Positioned by the
  item's footprint rather than `pos()`, like everything else scaled by
  `set_item_scale()` here.

**The Windows installer -- `scripts/build_installer.ps1` +
`scripts/installer/mdtools.nsi`.** NSIS (zlib licence, `winget install
NSIS.NSIS`) rather than WiX or Inno Setup: it packages a plain directory
tree, which is exactly what PyInstaller's onedir mode produces, and an MSI
would buy Group Policy deployment nobody asked for at the price of a much
heavier toolchain. The build script reads `__version__` out of the package
rather than restating it, and reduces it to numbers for NSIS's
`VIProductVersion`, which takes four numeric parts and would refuse
"0.3.0-rc2". 144MB of onedir compresses to ~43MB solid LZMA.

Two things are deliberately absent, and both would be easy to add wrongly:
- **No licence page** -- this repo has no LICENSE file, and an installer is
  not the place to invent one.
- **No `.mdproj` file association** -- `main.py` ignores `sys.argv`, so
  double-clicking a project would open the app on its startup screen rather
  than on that project. Worth adding the day the app learns to open a file
  it was handed, and not before.

Uninstalling removes the install directory (guarded on `MDTools.exe`
actually being in it, so a hand-edited `$INSTDIR` cannot take a recursive
delete with it), the shortcuts and the registry keys -- and leaves
`%LOCALAPPDATA%/MDTools` alone, since the templates, settings and Telegram
session in there are the user's, not the installer's.

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
- **A `QThread` whose C++ object gets garbage collected while `isRunning()`
  is still True aborts the whole process with `qFatal()` -- no Python
  traceback, just silent process death.** Only a real risk for a worker
  that loops indefinitely rather than finishing on its own (e.g.
  `telegram_chat_dialog.py`'s `_ChatWorker`, which runs until `cancel()`'d,
  unlike every one-shot worker elsewhere in this codebase) -- being parented
  to a dialog (`parent=self`) keeps the C++ object alive via Qt's own
  object tree regardless of whatever a Python variable currently points at,
  so even reassigning `dialog._worker` to something else doesn't stop an
  earlier real worker from still running in the background until the
  dialog itself is destroyed. See the Telegram bot integration notes above
  for the full incident (a missing test mock let this happen for real) and
  the two-part fix: never auto-start a persistent-loop worker from
  `__init__` (so plain construction stays inert), and every test that does
  start one must stop it again (cancel + wait for the thread to actually
  exit) before the test function returns.
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
- **`menu.addAction(text, callback)` (and `QAction.triggered.connect(callback)`
  generally) passes `QAction.triggered`'s `checked: bool` straight through
  to `callback` if its signature accepts a positional argument there --
  including an *optional* one.** A callback like `def _record_folder_dialog
  (self, initial_folder: Path | None = None)` connected directly to a menu
  action would silently receive `initial_folder=True`/`False` on every
  click, not the intended default of `None` -- Qt/PySide's signal-slot
  introspection matches arity, it does not know an optional parameter was
  meant to stay unset. `app_window.py`'s `_record_folder()` is a thin,
  zero-argument wrapper kept specifically so the menu never connects
  directly to the parameterized `_record_folder_dialog()` -- see the
  Telegram bot integration notes above for where this was caught.
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
  invalidates **sixty-nine screenshots** (twenty-three figures x three
  languages), not one -- rerun the generator
  rather than patching a figure. Second, the Polish and Japanese manuals
  show Polish and Japanese screenshots, so the menu names quoted in their
  text have to match `i18n/mdtools_{pl,ja}.ts` exactly; a rename means
  editing the translation *and* the manual text. The generator runs in
  `QStandardPaths` test mode and stubs `mdrem.MDRemClient`/
  `foobar.FoobarClient`, so it can safely run while the real app is using
  the serial port. **The Telegram figures need no stub at all** -- both
  dialogs are inert until an explicit action starts their worker
  (`TelegramChatDialog.start_connecting()`, and `TelegramLoginDialog` only
  on "Send code"), so plain construction opens no socket; the chat
  transcript is then filled by handing synthetic `ChatMessage`s straight to
  the dialog's own signal handlers, i.e. the real rendering code driven with
  fake data. `_capture_telegram()` also creates two real (empty) `.flac`
  files in a throwaway download folder, because Sort/Record enable
  themselves from what is actually on disk -- without them the figure shows
  three greyed-out buttons the manual points at.
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
