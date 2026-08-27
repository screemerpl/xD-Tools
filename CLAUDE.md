# xD-Tools

A PySide6 desktop workbench for three retro music media — MiniDisc, CD-R
and compact cassette: designs disc labels/J-cards/case inserts/tray
cards/cassette shell labels (SVG cut shapes + PNG print artwork for a
Cricut plus a regular printer); records an album onto a MiniDisc via an
MDRem infrared adapter with track marks and disc/track titling; rips an
audio CD to FLAC, IDs it via MusicBrainz, and records that; burns an audio
CD-R with CD-Text; records a cassette side by side (a deck nothing here
can drive, so it tells the user what to press).

> **Full history and reasoning archive:** `docs/CLAUDE_HISTORY.md` is the
> complete, unabridged version of this file — every incident, every
> discarded alternative, every round of user correction, in full prose.
> This file states the *current, load-bearing* facts and rules only. If
> something here seems to lack justification, or you need the story behind
> *why*, check the archive before assuming a decision is arbitrary or
> reversible.

## Naming — read before renaming anything

App is **"xD-Tools"** everywhere a person reads it (every `tr()` string,
window title, file-dialog filter, User-Agents, `.exe` name). It is
**"MDTools" in three places where a name is an address, and must stay
that way**:
- `app.setApplicationName("MDTools")` in `main.py` — renaming moves
  `%LOCALAPPDATA%/MDTools` (`QStandardPaths.AppConfigLocation`), silently
  losing every user's `templates.json`/`settings.ini`/Telegram session.
- The `"MDTools CD Rip"` / `"MDTools Telegram Downloads"` folder names in
  `app_settings.py` — real files exist there on real disks.
- The Python package (`mdtools`) — an import path.

Repo is `github.com/screemerpl/xD-Tools` (renamed 2026-08-20; GitHub
redirects the old URL, but use the new one, including in
`musicbrainz.py`'s User-Agent). Keep the window title, Help > About,
README, `pyproject.toml`'s `description`, and the user manual in sync
whenever scope changes — this has been missed before, repeatedly, each in
a different place.

**Treat physical accuracy as load-bearing.** Output is cut with a blade —
mm dimensions and the cut-vs-print separation are the actual product.
Don't round, approximate, or "simplify" geometry without checking.

## Stack

- PySide6 (`QGraphicsView`/`QGraphicsScene` canvas, `QtSvg`, `QtSerialPort`
  for MDRem, `QtPrintSupport` — all in the one wheel, no extra deps)
- Pillow (grayscale, cover palettes, opaque-content bounds)
- Telethon (Telegram bot integration, experimental)
- PyInstaller (`scripts/build_windows.ps1`/`build_linux.sh`) + NSIS
  (`scripts/build_installer.ps1`) for the Windows installer
- pytest + pytest-qt: `.venv/Scripts/python.exe -m pytest -q`

## Layout

```
src/mdtools/
  main.py                  entry point
  app_window.py             MainWindow: page switcher, menus, docks, undo group, wiring
  project.py                Project / ProjectMetadata / Track / TextStyle, media and their pages
  constants.py              MM_PER_INCH plus mm_to_px()/px_to_mm(), which read the DPI setting
  app_settings.py           every global setting: DPI, MDRem, rip folder, Telegram, audio devices
  recent_projects.py        the last N projects, for File > Open Recent and the startup screen
  user_paths.py             where every file dialog starts: Documents/XDProjects, Pictures
  theme.py                  the flat dark (Discord-style) theme: one palette and one stylesheet
  commands.py               QUndoCommand subclasses (add/delete/reorder/transform/property-edit)
  clipboard.py              in-memory copy/cut/paste (reuses project_io's item (de)serialization)
  grayscale.py              the desaturation + brightness/contrast maths, shared by preview and export
  printing.py               sheet layout: pack copies, search arrangements, paint placements (no Qt UI)
  gallery.py                bundled asset gallery (assets/img) + per-user downloaded-covers cache, merged
  metadata_lookup.py         iTunes Search API: track list + release year + cover art; Deezer for an artist photo
  musicbrainz.py            identifying a CD from its TOC alone -- a CD carries no text (no Qt UI)
  embedded_cover.py         the cover art and tags inside a FLAC file, as a last resort (no Qt)
  mixtape_cover.py          draws a cover for a compilation, which by definition has none
  palette.py                background/accent/text colours pulled out of a cover image (Pillow, no Qt)
  cover_filters.py          six background treatments (brighten/blur/posterize/halftone/pixelate/none), pure Pillow
  mdrem.py                  MDRem IR adapter: serial protocol, transliteration, upload plan (no Qt UI)
  audio_engine.py           FLAC decode/encode, resampling, dithering, realtime playback (soundfile/soxr/sounddevice, no Qt)
  tracks.py                 track list + album/artist/year from files' own tags -- no external player (no Qt)
  cdrip.py                  audio CD: drives, TOC, disc ids, rip plan, cdparanoia/flac (no Qt UI)
  decode.py                 what an audio file is, and Red Book PCM out of it (no Qt)
  cdburn.py                 audio CD-R: burn plan, *.inf CD-Text, cdrecord (no Qt UI)
  audio_folder.py           which files in a folder are the album, and in what order (no Qt)
  album_sort.py             one folder of downloads split into one folder per album, and
                            where a just-downloaded file belongs (no Qt)
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
  i18n/                     __init__.py (language + QTranslator, ours and Qt's own), mdtools_{pl,ja}.ts/.qm
  canvas/
    scene.py                 DesignScene: template outline + design items
    view.py                  zoomable/pannable view + mouse scale/rotate handles + undo hookup
    items.py                 "cut" vs "print" layer tagging, non-uniform scale helpers, text shadow/glow
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
    new_design_dialog.py        File > New: medium, then one template picker per page (remembers last choice)
    settings_dialog.py          Window > Settings: DPI, MDRem port, rip folder, audio devices, experimental
    experimental_settings_dialog.py   whatever an experimental feature needs, kept out of the stable one
    metadata_dialog.py          album/artist/year/track-list editor + "Lookup Track List..." + "Upload Tracklist"
    cover_preview.py            the cover thumbnail that is also the button for replacing it, plus its lookup
    cover_filter_dialog.py      pick a background treatment for a disc/shell label, from a live preview per option
    asset_gallery_dialog.py     Insert Asset: pick one of the bundled gallery images
    grayscale_export_dialog.py  brightness/contrast, previewed against the real scene, before the save path
    print_dialog.py             PrintDialog and MultiprintDialog over one shared base: sheets, PDF, PNG
    mdrem_port.py               resolve_port(): the saved port, a probe, or a warning -- shared by both entry points
    mdrem_upload_dialog.py      preview-then-write dialog + the worker thread driving an upload
    remote_dialog.py            software Sony MD remote, reachable from Window menu or startup screen
    record_dialog.py            Recording > Record to MiniDisc: arm, play (own AudioPlayer), watch, hand off to titling
    playback_bridge.py          crosses AudioPlayer's realtime callback thread onto the GUI thread (QObject + Signals)
    decode_worker.py            decoding/resampling/dithering a disc or tape side, off the GUI thread
    cd_rip_dialog.py            Source > Rip Audio CD: read TOC, identify, rip -- and stop there (#16)
    folder_record_dialog.py     Recording > Record Folder: read a folder's own tags directly instead
    tape_record_dialog.py       Recording > Record Cassette: a side at a time, with the user working the deck
    burn_dialog.py              Recording > Burn Audio CD: the plan, the verdicts, and cdrecord behind a worker
    erase_dialog.py             Erase MiniDisc button (on the record dialog): fixed sequence behind one confirm
    telegram_login_dialog.py    signing in as a user account, over a worker with a live asyncio loop
    telegram_chat_dialog.py     the bot conversation, its download queue + summary (mirrored into the main window's bar), and the hand-off to recording
    about_dialog.py             Help > About xD-Tools
  io/
    svg_export.py               exports just the cut/fold shapes as physically-accurate SVG
    png_export.py               exports print artwork as PNG, clipped to the template outline
    project_io.py               save/load a whole project as one self-contained .mdproj JSON
assets/
  img/                      gallery images, the CD Digital Audio mark and the app icons -- see gallery.py
  icons/                    the Twemoji button icons -- see panels/icons.py and ATTRIBUTION.md
bin/
  win64/                    bundled cd-paranoia + cdrecord, with their DLLs -- see ATTRIBUTION.md
tests/          1700+ tests, all offscreen via QT_QPA_PLATFORM=offscreen
doc/            the built user manual (PDF x3) + doc/img, its generated screenshots -- see doc/README.md
docs/
  CLAUDE_HISTORY.md         the full, unabridged version of this file
scripts/
  build_windows.ps1 / build_linux.sh   PyInstaller onedir build
  build_installer.ps1 + installer/mdtools.nsi   the Windows installer, NSIS over that build
  clean_windows.ps1 / clean_linux.sh   remove build/dist/__pycache__/etc.
  make_app_icon.py / make_cd_logo.py   the .ico and the Digital Audio PNG, generated once each
  manual/
    make_screenshots.py      drives every dialog and grabs it, once per language;
                             --only <figures> / --list redo just what changed
    build_manual.py           blocks -> QTextDocument -> QPdfWriter, with a measured TOC
    content_{en,pl,ja}.py     the manual's text, as block lists
```

## Domain model

**A project's pages are a described list, not a fixed pair** (`project.py`:
`PageKind`/`PAGE_KINDS`/`PAGE_ORDER`, `page_template_kind()`, `page_title()`,
`Project.ordered_pages()`). Adding a page is an entry in `PAGE_KINDS` plus a
template — proven by `PAGE_BACK` (the CD jewel-case tray card) landing as a
pure data addition. `MainWindow._refresh_page_combo()` fills the dropdown
from the project; nothing enumerates pages by name. `load_project()`
requires only a **disc** page — a third page is a later-version file, not an
error. `PrintDialog` shares one sheet only for a two-label arrangement;
any other count gets one sheet per label.

**Optional pages (the CD case back) are the normal absence, not a special
case.** File > New defaults to `(none)`; the toolbar's **+**/**-** buttons
add/drop it later (only optional pages can be removed — disc/cover pages
*are* the project). Auto-layout fills the case back only when it exists,
and never changes its template (unlike disc/cover, which re-template on
every auto-layout run).

**Medium is a project-level choice** (`Project.medium`: `MEDIUM_MD` /
`MEDIUM_CD` / `MEDIUM_TAPE`), picked once in `NewDesignDialog`, which
filters every template picker to that medium so a J-card can never land on
a CD project. Auto-layout (`_auto_layout_project()`) branches on medium by
**template name**, and skips a page whose template is custom (user's own,
may carry saved layers) or a renamed built-in (nothing matches it by name).

### Templates — dimensions (all `verified: true` unless noted)

- **MD disc label**: 37×52mm, 3mm chamfer top-left, 1mm fillet other three.
- **MD disc + slider**: same disc + a second cut shape 27.5×17.5mm
  (left corners rounded 2.5mm, right square), `slider_gap_mm`=3mm to its
  right, vertically centered. `template_clip_path()` unions both shapes.
- **MD full disc label** (`shape=="full_label"`): single rounded-rect
  outline 69.4×66.4mm, `corner_radius_mm`=4mm, with the shutter notch **cut
  into** the right edge (not a separate shape): 27.5×17.5mm,
  `slider_notch_corner_radius_mm`=2.5mm, `slider_notch_top_mm`=24.3mm (puts
  the cut edge at 23.5mm below the label's own top — that's the number that
  was actually measured; check the *edge*, not the raw field, if this ever
  moves). `slider_notch_buffer_mm`=0.8mm enlarges the notch on 3 sides (a
  real cut clearance, confirmed explicitly — "it needs to be cut as well").
  `slider_travel_mm`=19.4mm extends the buffered notch further down,
  ending 62mm below the label's top — the channel the shutter sweeps
  through. Built via `QPainterPath.subtracted()`.
- **MD full disc label + slider**: full-label outline + a second,
  independent cut shape for the printable sticker, positioned *inside* the
  notch's own void (deliberate overlap, not a gap) — reuses
  `slider_width_mm`/`slider_height_mm`/`slider_corner_radius_mm`, which do
  double duty depending on `shape`.
- **What "slider" means**: the cartridge's sliding **dust shutter**, not
  the write-protect tab (a different, unlabeled part) — corrected mid-
  session; field/template names were deliberately left alone since
  `registry.sync_builtin_templates()` matches built-ins **by name**, and
  renaming would duplicate every user's template.
- **MD cover/J-card**: 126×73mm, 2mm corner radius, folds at 58.85mm and
  67.15mm from the left (an 8.3mm spine).
- **MD cover/J-card + window**: same + a 40×40mm rounded-rect (1mm radius)
  cutout, 10.3mm from the right fold, 3.45mm from the bottom.
- **CD disc label** (`shape=="cd_label"`): annulus, `outer_diameter_mm`=117,
  `hole_diameter_mm`=35 (subtracted, same technique as the shutter notch).
  `slider_*` fields are meaningless here (hidden in Template Manager) — a
  CD has no cartridge.
- **CD slim-case front insert**: 120×120mm (not 124×124 — that's the case
  *body*, the paper sits under tabs).
- **CD slim-case folded insert** (track list): 240×120mm, folded at 120mm
  (two equal panels — right = cover, left = track list, read through the
  case's clear back).
- **CD jewel-case tray card** (`case_back` kind): 151×117.5mm, a 138mm
  panel between two 6.5mm spines.
- **Cassette J-card**: 101.6×101.6mm, folds at 65.1mm and 77.8mm.
- **Cassette shell label** (`label` kind, its own registry family): 90×
  40.8mm, top corners chamfered 45° (leg length ≈4.24mm off each edge),
  bottom corners rounded 1.5mm. Opening is **one shape**, not two holes —
  a rounded rect (radius = half its height) bridging both reel hubs *and*
  the tape window between them, subtracted from the cut path
  (`DesignScene.reel_window_path()`). Text lives in the band above/beside/
  below that opening (`tape_layout._label_bands()`), never across it.

**A CD jewel case gets the tray card + front insert; a slim case gets only
the folded front insert (no tray card).** Both `CoverTemplate`-shaped;
`registry.KINDS` has a separate `"case_back"` family so a tray card and a
slim-case insert can't be picked in each other's place. `"label"` is a
third family, split out the same way, for the cassette shell label (vs.
J-card `"cover"`).

**`registry.sync_builtin_templates()`** (called once from `main()`, every
start, before `MainWindow`) is what makes a new built-in template reach
existing installs — the per-user `templates.json` is only ever seeded from
`defaults.json` **once**, on first run, so this closes that gap. Strictly
additive: appends any bundled built-in whose *name* isn't already present,
never touches an existing (possibly user-edited) entry. Idempotent, safe
on every start.

**User templates can carry pre-made layers** (`items: list[dict]`, the
`.mdproj` item shape). Tools > "Save as Template..." captures the current
page's layers; File > New recreates them verbatim — for a disc page, a
non-empty `items` skips `seed_disc_defaults()` entirely.

A new disc page auto-seeds an editable "▲ INSERT THIS END" triangle+label
(New only, not Open, and only if the template's own `items` is empty) —
centered on `template.width_mm`, not the wider scene rect (which the
slider variant pads).

### foobar2000 / SoX retirement (2026-08-24)

**Neither foobar2000 nor SoX is a dependency any more.** Recording (MD,
cassette, CD rip, folder record, Telegram hand-off) now plays through
`audio_engine.AudioPlayer` directly — decodes via `load_for_playback()`
(cassette, whose analogue line-out doesn't need this app's own bit-depth
quantising) or **`load_for_recording()`** (MD, whose digital S/PDIF input
needs exactly Red Book PCM the same as a CD-R burn — resampled *and*
noise-shape-dithered to 16-bit via the same `_resample_and_dither_to_
int16()` core `resample_and_dither_to_red_book()` uses, not left as an
undithered float32 buffer for some downstream driver to truncate badly).
Fires `on_track_boundary`/`on_finished` from the realtime audio callback
(sample-accurate, not poll-bounded). `tracks.py` replaced the metadata half
of the old `foobar.py` (deleted): `PlaylistItem`, `sort_by_disc_and_track`,
`disc_breaks`, `metadata_from_playlist`, all pure-Python/mutagen, no
external app. `panels/playback_bridge.py`'s `PlaybackBridge(QObject)`
(`track_boundary`/`finished` Signals) is the one real piece of new
Qt-threading code — `AudioPlayer`'s callbacks run on PortAudio's own
thread; emitting through a GUI-thread-affine QObject makes Qt's default
`AutoConnection` become a safe queued connection automatically.

**Decoding a disc/side runs on a worker thread** (`panels/decode_worker.py`,
`DecodeWorker`). Both recording dialogs still decode everything *before*
anything starts moving — the MD deck is armed and record-paused first, a
cassette deck is about to roll onto tape, so decoding afterwards would put
its own duration onto the medium as silence. What changed is the thread:
`load_for_recording()` on the GUI thread froze the whole window for the
length of the work — **measured at 20s for a 12-track album**, with a
single `processEvents()` per track as the only relief — and was reported
as exactly that. Now `start()` returns in 0.1ms and the GUI services
events throughout. `cancel()` lands **between tracks** (it raises out of
the loader's own per-file progress callback), so a Stop mid-decode sets
`_closing`, cancels, and lets `finished` close the window — never
`wait()` on the GUI thread. A cancelled decode emits neither `decoded`
nor `failed`, and `_on_decoded()` drops a result that arrives after a
Stop. `TapeRecordDialog.is_busy()` counts `_preparing` as busy for the
same reason every worker here does: closing out from under a live
QThread is the silent process abort.

**Multi-disc/side boundaries are now exact, not polled**: `_begin_disc()`/
`_begin_playback()` hand `AudioPlayer` only that disc/side's own buffers,
so playback simply ends where the buffer queue ends — no `stop_after_
current_track` arming needed. `on_track_boundary` never fires for index 0
by construction (no special-casing needed to avoid double-marking track 1).

**⚠ `AudioPlayer._callback()` must only fire `on_finished()` once per
`play()` call.** PortAudio calls this callback continuously for as long as
the stream stays open; nothing stops the stream once the queue empties, so
without a guard, *every subsequent callback* (~10-20ms, indefinitely) fires
`on_finished()` again. Real, shipped bug: the MD "Upload Tracklist" window
reopening in a loop after recording finished — each stray firing
independently rescheduled its own titling dialog. Fixed with a
`_finished_called` flag, reset each `play()`. If `AudioPlayer` is ever
touched again, do not remove this guard.

**`RecordDialog._title_single_disc()`/multi-disc titling both run
unattended** (`MDRemUploadDialog(..., unattended=True)`) — no confirmation
between the album ending and titles going out (nobody sits through a whole
recording); a single-disc run used to ask twice (write titles? then
eject?), now matches the multi-disc flow's own "nobody is here to ask"
rule. Erase MiniDisc (`erase_dialog.py`) is a fixed, blind sequence — Stop,
Erase, Enter×2, Eject — behind one confirmation, **each key paced by a
0.25s gap** (sent back-to-back too fast for the deck to keep up,
reported directly). Both are deliberate trade-offs vs. an older, more
cautious guided flow — see the archive if a different deck needs different
handling.

**A recording backs output volume off `RECORDING_VOLUME_DB` first** —
now `app_settings.recording_gain_db()` (default -5dB, user-configurable),
applied by `AudioPlayer(gain_db=...)` itself, not an external app.

**Old rips/downloads are never automatically deleted, anywhere, ever.**
`cdrip.py` used to have a `clean_stale_rip_folders()` that `shutil.rmtree()`d
subfolders it guessed were "stale rip output" — this **deleted a real
user's permanently-organized album folders** when the rip/download folder
setting was merged into one shared location. The function is gone
entirely, not replaced with a safer version. **Nothing in this codebase
may delete files from the shared audio/rip folder
(`app_settings.cd_rip_folder()`) or any other user storage location,
automatically, ever, for any reason.** If a future feature seems to need
folder cleanup, that is a sign to stop and ask, not to write it.

### CD rip / burn

Both are plan-then-execute (`build_rip_plan()`/`build_burn_plan()`, no Qt,
no drive needed to construct). **Ripping and recording are two separate
steps, in two separate menus** (#16, then split the rest of the way by
explicit request): Source > "Rip Audio CD..." rips, identifies via
MusicBrainz, offers the album's metadata to the open project, and ends —
it resolves no MDRem port and opens no recording dialog. Recording those
files is Recording > "Record from Rip/Download Folder to {medium}...",
the same entry a Telegram download is recorded from, since both land in
`app_settings.cd_rip_folder()`. `CdRipDialog` therefore names no machine
in its title any more (its `medium` still decides the 80-minute MiniDisc
warning and the wording about where edited titles end up).

**"Read Disc" is off until there is a disc in the selected drive** —
`CdDrive.has_media` (Windows' own answer: "something is in there", never
"an audio CD is in there", which only reading the TOC settles; always
True elsewhere). The disc goes in *after* the window opens, so the drives
are re-listed on a `_DRIVE_POLL_MS` timer that runs only while the window
is shown and nothing is ripping, and acts only when the listing actually
changed — otherwise the dropdown would reshuffle under the user's hand
and the status line would eat whatever a read or a lookup just wrote.

Bundled Windows binaries (`bin/win64/`, see `ATTRIBUTION.md` — both GPL):
`cd-paranoia.exe` (ripping, real error correction — ~3x realtime, the
price of it) and `cdrecord.exe` (burning, DAO + CD-Text). Both write
progress to a **file**, not a pipe (an undrained pipe blocks the child);
`cd-paranoia` writes everything to **stderr** including success, and `-Q`
exits 0 even with no drive found — parsing the TOC out of the output is
the only real signal. Track order for a burn/rip-as-one-album must come
from `multidisc.order_by_disc_and_track()`, not filename order (two discs
of one album both number tracks from 1 — a plain filename sort produces
`2,1,2,1,...` and puts a break at nearly every track).

CD-Text goes through `mdrem.transliterate()` (ASCII-only, reports what got
dropped) — the same function the MiniDisc titler uses, so both surfaces
promise the same thing about a title going onto a disc.

MusicBrainz identification: exact disc-ID lookup first, fuzzy TOC search as
fallback; needs a real, identifying User-Agent (`musicbrainz.py`) or
requests are refused.

### Compilations / mixtapes

`ProjectMetadata.is_compilation()` — true when **most** tracks can't be
attributed to one artist (substring match against the album's own artist
if present, else the commonest track artist), **not** "do any two tracks'
artists differ" (that would flag any album with one guest feature).
Absence of per-track artists is not evidence either way. Getting this
wrong toward "compilation" is the costly direction (renames the disc,
replaces the cover, rewrites the J-card), so most test coverage guards the
*ordinary-album* path staying untouched.

### Recording sources & devices

Three independent recording sources all end at the same `RecordDialog`/
`TapeRecordDialog`: MD/cassette recording proper, CD rip, folder record —
plus a Telegram-bot download hand-off. **MiniDisc and cassette each have
their own audio output device setting**
(`app_settings.audio_output_device()`/`tape_audio_output_device()`) — a
digital S/PDIF feed for one deck and an analogue line-out for the other are
routinely different physical outputs.

**`audio_engine.list_output_devices()` is filtered to one PortAudio host
API (`_PREFERRED_HOST_API_NAME = "Windows WDM-KS"`)**, not every API —
PortAudio otherwise enumerates the *same* physical device once per host API
(MME/DirectSound/WASAPI/WDM-KS), quadrupling the Settings dropdown.
WDM-KS, not WASAPI, was picked after confirming live that the user's real
S/PDIF passthrough device is *only* exposed under WDM-KS (WASAPI shows a
differently-named entry for the same hardware) — it's also the more direct
kernel-streaming path, closer to "bypass the Windows mixer." Falls back to
every device (no filter) if that host API isn't present at all (e.g. not
Windows). `resolve_output_device()` inherits the filter automatically
(it just iterates `list_output_devices()`).

## Architecture notes (read before touching these areas)

**i18n: real Qt `tr()`/`QTranslator`, not a homegrown dict.**
`pyside6-lupdate -extensions py -recursive src/mdtools -ts
src/mdtools/i18n/mdtools_{pl,ja}.ts`, then fill any `unfinished`
translations, then `pyside6-lrelease` to compile the `.qm`. Two rules
`lupdate`'s static scanner needs, both easy to violate without an error:
1. The literal string must be directly inside the `tr()`/`translate()`
   call — never through a variable or a custom wrapper.
2. **The `tr()` call itself cannot be nested inside an f-string's `{...}`**
   (`f"<b>{self.tr('x')}</b>"` — lupdate sees *zero* occurrences, not a
   partial one). Call `tr()` on its own line, interpolate the result.
   Hit twice already in this codebase — grep `f["'].*\{self\.tr\(` after
   adding any heading built this way.
Outside a QObject method, use `QCoreApplication.translate("Context",
"...")` with an explicit, fixed context string — never `parent.tr(...)`
from a plain function (`parent.tr()`'s context is the *caller's* runtime
class, which silently changes if a second, different class ever calls the
same helper).

Language switching is **restart-required**, not live — no
retranslate-on-the-fly machinery. `install_translator()` installs **two**
translators: this app's own `mdtools_<code>.qm`, and Qt's own
`qtbase_<code>.qm` (from `QLibraryInfo`'s translations path) for built-in
strings like `QDialogButtonBox`'s "Close"/"Cancel" — easy to forget the
second one exists. The language *setting* uses an explicit
`QSettings(path, IniFormat)` pointed at `AppConfigLocation`, **not** plain
`QSettings()` — that requires `organizationName`, which would relocate
`templates.json`. **Never add `app.setOrganizationName(...)` without
checking this.**

**Selection frame is axis-aligned in scene space, not tilted with a
rotated item** (`canvas/view.py::_handle_geometry`) — deliberate, explicit
tradeoff (like PowerPoint), confirmed with the user after being shown it
breaks cleanly only at 180°-multiple rotations. Do not "fix" this without
re-confirming.

**A pixmap layer's selection frame sizes to its actual opaque content, not
`boundingRect()`** — Clip Layers/Bake Layers make out-of-bounds pixels
transparent rather than cropping, so the old bounding rect included dead
space. `canvas/items.py`'s `opaque_content_rect()` (Pillow `getbbox()` on
the alpha channel, cached by `pixmap.cacheKey()`) is what `_handle_geometry`
uses instead — **not** for `transformOriginPoint()`, which stays the
original pivot. A rasterized shape (Clip Layers on a rect/ellipse, or Bake
Layers) must carry over both the item's **selected state** and a
**re-anchored pivot** to its opaque content's own center, or the tight
frame/rotation silently regresses — see `_repivot_to_opaque_content()`.
Every item class also mixes in `_NoDefaultSelectionDecoration` to suppress
Qt's own dashed selection box (drawn regardless of any custom
`drawForeground()` painting), or the stale full-size box shows underneath
the correct tight one.

**Rectangles/ellipses resize their own `rect()`, not a transform** — the
one deliberate exception to "non-uniform scale is a stored `(sx,sy)` plus a
transform" (see the PySide6 gotchas section). Resizing via transform kept a
rasterized clip of an enlarged rectangle pixelated (the backing pixmap was
still sized to the tiny original `rect()`). `set_item_scale()` special-
cases `QGraphicsRectItem`/`QGraphicsEllipseItem` to resize `rect()`
directly (`BASE_RECT_ROLE` caches the pre-scale size) and **re-anchor
`transformOriginPoint()` to the new rect's center**, solving `pos()` so the
same scene point stays fixed — getting either half wrong reintroduces a
real, shipped bug (a resized-then-clipped rectangle ballooning/jumping).

**Undo/Redo is scoped to canvas/layer edits only** (explicit choice) — not
Project Metadata or Template Manager. `MainWindow.undo_group` (one
`QUndoStack` per project) backs the Edit menu's actions, created from the
*group* so they survive a stack swap on New/Open. Two merge-coalescing
commands (`MoveItemsCommand`, `PropertyEditCommand`) **must not merge two
genuinely separate user actions into one undo step** — this shipped wrong
once (`mergeable` flag gated on real OS auto-repeat for arrow-key nudging;
`PROPERTY_EDIT_MERGE_WINDOW_MS` sliding-time-window for property edits).
`TransformCommand` (mouse rotate/scale) never merges at all. Undo/redo must
also refresh the Layers panel on **any** index change
(`QUndoStack.indexChanged`), not just from handlers that already call
`_refresh_layers()` — Undo/Redo bypasses those handlers via the group.

**Export must deselect before hiding layers** (`with
scene.deselected_for_export(), scene.hidden_for_export(...):` — that
order, not reversed) — hiding an item auto-deselects it in Qt, so
reversing the order loses the selection `deselected_for_export()` needed
to restore.

**Printing** (`printing.py` + `panels/print_dialog.py`): each label's true
physical size comes from its *rendered image's own pixel count ÷ DPI*
(`image_physical_size_mm()`), never from scene coordinates (which are
frozen at whatever Screen DPI built them). `crop_to_template_bounds()`
packs against the template's real cut-shape footprint (its
`sceneRect()` padding is a rendering convenience, not physically real) —
packing against the padded render wastes that margin twice between every
pair of copies. Rotation is a **fallback only, never a default** even if
it would pack tighter (`_ROTATION_COMBOS` tries upright first, escalates
only if needed) — rotating a label that already fits, purely because it's
marginally more compact, was a real regression once. A copy count the
grid can't auto-arrange degrades gracefully
(`_layout_with_overflow_at_corner`) rather than refusing the count
outright — auto-arrangement failing is not proof an arrangement is
impossible; the user may still drag copies into a tighter manual layout.
`PrintDialog`/`MultiprintDialog` share a `_PrintDialogBase`; a CD project's
folded insert forces landscape + one-sheet-per-label (too wide for a
portrait sheet, and the two labels together exceed A4's printable length).

**Clip Layers / Bake Layers** both render through the *exact* paint code
PNG export already uses (`render_scene_to_image()`), so "clipped by X" and
"clipped by export" can never visually diverge. Clip Layers rasterizes a
partially-outside rect/ellipse at `SHAPE_RASTER_SUPERSAMPLE`× (≈4×,
`DEFAULT_EXPORT_DPI/SCREEN_DPI`) — oversized on purpose, since a shape has
no native resolution of its own; positioned by matching **centers**
(`mapToScene(boundingRect().center())`), never `pos()` (the oversized
pixmap's own origin doesn't correspond to the old shape's). Bake Layers
renders the whole page at `BAKE_DPI` = 3×`DEFAULT_EXPORT_DPI` (900, not
300) — deliberately higher than a plain export, both for later re-export
headroom and because Qt's smooth downsampling acts as supersampling for
fine text (a first version baked at 300dpi and text/edges looked poor). A
window-template J-card's cover art needs baking too (its own artwork isn't
naturally cropped to the die-cut hole) — `_bake_cover_window()` bakes
**only the image layer**, not the whole page (the track list/panels stay
editable text).

**Text shadow/glow** (`canvas/items.py`, `DesignTextItem.paint()`) are
per-item bool flags, painted underneath the real text as cached, blurred
bitmaps (Pillow) — **in the item's own local, unrotated space**, so a
rotated caption's shadow direction rotates with it for free. Colour is
auto-picked (`readable_text_colour()` against the text colour itself).
Every auto-generated label/cover turns shadow on by default; manually
added text stays plain (opt-in via Properties).

**`cover_filters.py`'s strengths are counts across the image, never
pixel sizes.** A cover arrives from iTunes/Deezer/MusicBrainz/embedded
FLAC art/the user's own files at whatever size that source provides, so
an absolute constant (a 14px mosaic block, a 6px blur radius, a 10px dot
cell — the original values) made each filter hit a small cover far
harder than a large one: pixelate kept 0.91 of a 300px cover but 0.99 of
a 1200px one, and was reported as "almost unrecognizable". `_divide()`
turns a division count into a pixel size against the image's *shorter*
side. Pixelate also averages each block (`BOX`) rather than sampling one
pixel of it (`NEAREST`), which is what a mosaic actually is. Halftone's
`HALFTONE_CELLS` is capped by (smallest cover worth supporting ≈300px) ÷
`_HALFTONE_MIN_CELL_PX` — ask for more and small covers clamp to the
minimum and stop matching large ones, defeating the point. **Do not
reintroduce a pixel-sized constant here.** `BRIGHTEN_AMOUNT` is the
deliberate exception at 0.55, matching `cd_layout.LIGHTEN`: it is a
legibility control, not a stylistic one (label text prints over it, and
a lighter wash leaves dark covers unreadable).

**Cover/palette derivation**: `palette.py` pulls background/accent/text
out of a cover image (Pillow quantize + WCAG luminance for text). Every
auto-generated page (disc label, CD ring, J-card, cassette shell/J-card)
must derive its palette **the same way** — a shipped bug had the disc
label scoring its accent against flat white while the case back/insert
scored it against the actual (lightened) background, producing two
different colours for one album; `build_disc_label()` now computes the
identical triple `place_back()`/`build_side_label()` already did. If a new
auto-generated surface is added, reuse the existing palette call, don't
write a new one.

**MDRem** (`mdrem.py` + 3 panels): `QtSerialPort`, driven synchronously in
`_ChatWorker`/upload-worker threads — no return channel from the deck at
all, so every write is "sent, unconfirmed," shown as such in the UI.
Titles are transliterated to ASCII (`transliterate()`, reports what got
dropped). `MAX_TRACK` = 99 (the firmware types multi-digit numbers now,
not limited to the remote's own 25 keys) — but **99 is a real ceiling**:
the deck's number field commits on the *second* digit, so a 3-digit
number would misfire onto the wrong track; tracks past 99 are reported
`skipped_tracks`, never guessed at. `_read_line()`/`_wait_for_bytes_
written()` poll in bounded ~200ms chunks rather than handing a whole
multi-minute timeout to one blocking Qt call — a single unchunked
blocking call **starved the whole GUI thread** (Python's GIL isn't
guaranteed released across a `QThread`-wrapped blocking call), reported as
"the whole window is frozen," not just the dialog. `MDRemUploadDialog`'s
`unattended=True` mode (no Start button, no eject prompt, self-`accept()`s
when its worker finishes) is what both single- and multi-disc automatic
titling ride on.

**Telegram bot integration** (`telegram_bot.py` + 3 panels, experimental,
gated behind Settings' checkbox): signs in as a real **user account**
(Telethon/MTProte), not a bot token — a bot can't message another bot.
`_ChatWorker` is a `QThread` with its own **persistent** asyncio event
loop (unlike every one-shot worker elsewhere) — it must never be
auto-started from `__init__` (plain construction must stay inert), and
every test that starts it **must** stop it again before returning, or a
QThread destroyed while still "running" aborts the whole process with no
Python traceback. Downloads are capped at `_MAX_CONCURRENT_DOWNLOADS`=3
via an `asyncio.Semaphore`, shown in a queue panel with an aggregate
summary line (counts/overall %/speed, fed by the same signals each row
already reacts to). `album_sort.py` groups downloaded files by `ALBUM` tag
(majority-vote for the folder's display artist, not the first file seen —
a guest-feature credit must not fork the folder) with an arrival-order
fallback for untagged files; **idempotent and safe to call repeatedly**
(a lone new file arriving into an already-sorted folder must still get
picked up, not just "already sorted, nothing to do").

**A download is filed as it arrives, not left in a heap for Sort.** It is
written into a staging subfolder (`cdrip.DOWNLOAD_STAGING_DIRNAME`,
reserved alongside burning's own `burn` scratch dir so nothing ever
offers it as an album), and only once complete are its tags read and the
file moved into `root/Artist - Album` by `album_sort.place_download()` —
tags cannot be read from a partial file, and a half-written track sitting
loose in the shared folder is something the album picker would offer and
a sort would file away as finished. Placement reuses the *same*
`read_album_tag()`/`_group_display_name()`/`sanitize_filename()` chain a
later sort uses, so a track placed on arrival and one placed by Sort can
never land in two similarly-named folders. Only FLAC has tags read today
(MP3/Ogg are the next session's work); anything unplaceable goes to the
root exactly as before, and Sort still deals with it. **Placement never
overwrites** — a taken name gains a " (2)" — for the same reason nothing
here deletes from that folder.

**Credentials are never hardcoded in the source tree.** The Telegram
API ID/Hash resolve in order: per-user `settings.ini` override → env vars
→ gitignored `_build_credentials.py` (written by the build scripts). A
build without any of these is a supported state (sign-in simply unusable
until the user supplies their own), not an error.
`test_the_credentials_are_not_hardcoded_anywhere_in_the_source_tree`
guards this by scanning for a bare 32-hex-digit literal.

**Theme** (`theme.py`) — Fusion style + a hand-written QSS stylesheet, one
palette, **no switcher, no second theme, no Settings toggle** (explicit:
"no changes of themes - just create one and use as default"). Currently a
Discord-style dark palette (recolored 2026-08-25 from an earlier
KDE-Breeze-blue palette) — Blurple accent `#5865f2`, three background
layers, off-white text, hover/press **darken** (not lighten). Every colour
is a single module-level constant used by both the palette and the QSS, so
they can never drift apart (`test_the_stylesheet_and_the_palette_agree_on_
the_accent_colour`). **Never a blanket `QWidget`/`QAbstractScrollArea`/
`QGraphicsView` selector** — the design canvas sets its own explicit white
background regardless of the app theme (a label must stay legible against
white the way it prints), and a blanket rule would fight that
(`test_the_stylesheet_never_sets_a_blanket_widget_background`).
**`scripts/make_app_icon.py` keeps its own, independent copy of the accent
colour** (no import relationship with `theme.py`) — a future accent change
must update and re-run that script too (real platform plugin, not
offscreen — PySide6 ships no fonts, offscreen has none to find), or the
taskbar/`.exe` icon silently keeps the old colour. Bundled monochrome
Twemoji icons (only `zoom_in`/`zoom_out` are single-fill) are tinted to
`theme._TEXT` at *render time* (`icons._load_svg_icon_tinted`,
`CompositionMode_SourceIn`), never by hand-editing the bundled SVG —
regressed once already when a theme recolor happened to land the toolbar
background almost exactly on the icon's own hardcoded dark fill.

**File dialogs all start somewhere deliberate** (`user_paths.py`) — never
`""` (which falls back to the process's working directory). Documents/
Pictures/Music via `QStandardPaths` (localised, redirectable — never a
hand-built path); `XDProjects` is the one named folder of its own,
created on demand, never at startup. Exports land beside the project.

**Grayscale/brightness/contrast** (`grayscale.py`) is one function
(`apply_grayscale()`) shared by the live canvas preview
(`_TrueGrayscaleEffect` — a **custom** `QGraphicsEffect`, not
`QGraphicsColorizeEffect`, which doesn't do honest grayscale and washes
black toward mid-grey), the pre-export adjustment dialog, and the real PNG
export — so preview and output can never visually diverge. The preview
toggle is **read-only** while active (deselects, disables canvas
interaction, disables the Tool/Layers panels) so nothing can be edited
mid-preview.

**Startup flow**: `StartupDialog` (recent projects / open / new) runs
before any project exists; closing a project's window returns to it rather
than quitting (`_may_discard_changes()` guards every path that could lose
work — New, Open, window close, and **the language-restart flow**, which
used to silently discard unsaved changes by calling `QApplication.quit()`
directly, bypassing `closeEvent`). Cancelling the *very first* startup
dialog means quit (`startup_cancelled`); cancelling a later one (e.g. the
template picker after choosing New) falls back to default templates —
these are deliberately different outcomes, keep them that way.

**`apply_template()` empties a page and rebuilds it from scratch**
(confirmed first — changing template size/shape makes old item coordinates
meaningless) — always resets the undo stack (its commands reference items
about to be discarded) and re-seeds the MD insertion mark on a disc page.
The page toolbar's Template dropdown is what calls this now (the old
Templates-menu action is gone); a **built-in** template asks
Empty/Generated-from-Metadata/Cancel first, a **custom** one (the user's
own) applies immediately with no prompt.

**Multi-disc/side splitting** (`multidisc.py`, `tape.py`) is
plan-then-execute, never repacking the running order, and balanced (not
"fill the first one to the brim"). Manual disc/side breaks are sticky and
start from whatever's already placed, not reset to none.

**Recording progress is mirrored into the main window** (#27,
`panels/recording_progress_bar.py` + `panels/hideable_dialog.py`): a bar
below the design view, above the status bar, showing overall *and*
per-track progress plus Stop and "Show recording window". Each operation
dialog (`RecordDialog`, `TapeRecordDialog`, `BurnDialog`, `CdRipDialog`,
`MDRemUploadDialog`, `MetadataDialog` proxying its titling, and
`TelegramChatDialog` mirroring its download-queue status) keeps its own
bar and additionally emits `running_changed`/`overall_progress_changed`/
`track_progress_changed`/`visibility_changed`, plus `request_stop()`/
`request_show()` — one shape, asserted in
`tests/test_operation_dialog_contract.py`, so `_drive_recording_bar()`
never needs to know which dialog it holds. **No per-track progress for
burning** (cdrecord writes a disc as one continuous DAO stream), titling,
or a Telegram download queue (several files can be in flight at once,
with no single "current" one) — those four deliberately do not define
`track_progress_changed`, and a test guards that.

**The bar is visible for an attached dialog's whole lifetime** —
`_drive_recording_bar()` → `recording_bar.attach()` shows it,
`_release_recording_bar()` → `stop()` is the *only* thing that hides it.
Tying visibility to `running_changed` instead shipped broken twice over:
a dialog hidden before its operation started left no bar and so no way
back to it, and an operation's own quiet moments (finished but waiting
to be closed, between discs) took the bar — including "Show recording
window" — away from a still-open hidden dialog. Both reported directly.
**The bar carries the only route back to a hidden window, so it must
outlive every pause in the work it reports on.** Anything emitting
`running_changed(True)` from its own constructor/starter (as
`TelegramChatDialog.start_connecting()` does) must be wired up *before*
that call or the emission is missed entirely.

**The bar has exactly one owner.** `_drive_recording_bar()` declines if
another dialog already holds it, and `_release_recording_bar()` declines
to put it away unless the dialog releasing it is the owner. Every
hideable operation asks `_guard_no_concurrent_operation()` first so two
of those can't overlap — but **`MetadataDialog` deliberately opens
without that guard** (editing metadata mid-rip is ordinary), and it used
to seize the bar on the way in and switch it off on the way out, taking
a running rip's progress and its way back with it. Reported exactly that
way. It is also *not* an operation, only a proxy for the
`MDRemUploadDialog` its "Upload Tracklist" opens, so it takes the bar
via `_drive_recording_bar_for_metadata()` **only while that upload
runs** — holding it for the editor's whole lifetime both put up a
"Waiting…" bar for something that wasn't happening and made
`_guard_no_concurrent_operation()` see *itself*, which permanently
refused Upload Tracklist with a "still running" box and nothing running
(hence the guard's `ignoring` parameter and `_new_metadata_dialog()`).

**Hide keeps an operation running; two things exist only because of
that.** `exec_hideable()` is what survives a Hide at all (see the gotcha
below — a bare `hide()` ends `exec()`), and because the main window is
then usable mid-operation, `_guard_no_concurrent_operation()` refuses
both a second operation *and* closing the main window while one runs —
quitting out from under a live worker thread is the silent
`QThread`-destroyed process abort. **Only one recording/rip/burn/upload
may ever be in flight**; `MainWindow._active_recording_dialog` is what
both guards read, and it means "an operation that owns the MDRem port /
drive / progress bar is in flight" — *not* merely "one of these dialogs
is open". That distinction is load-bearing: `MetadataDialog` is open far
longer than it is uploading, and while it wrongly counted as in-flight
it refused its own Upload Tracklist (see above).
`TelegramChatDialog` shares this same guard even though a chat session
touches none of those physical resources — what it *does* share with the
other six is the one bottom progress bar itself, which only one dialog
can ever be wired into at a time, and reusing the existing guard was
simpler and safer than inventing a second, parallel single-owner
mechanism just for it.

## PySide6/Qt gotchas hit in this codebase

- **Never construct a Qt GUI type** (`QColor`/`QPen`/`QBrush`/`QFont`/
  `QPalette`/...) **at module import time** — segfaults if it runs before
  `QApplication` exists. Keep such values as plain strings/constants at
  module scope; construct lazily inside a function. Grep
  `^[A-Z_]+\s*=\s*Q(Color|Pen|Brush|Font|...)\(` at module level before
  calling a feature done.
- **`QGraphicsView.setScene(scene)` does not keep a Python reference** —
  a scene with no other live reference gets garbage collected out from
  under the view (`RuntimeError: ... already deleted`). Keep the scene
  alive alongside the view explicitly.
- **A `QThread` whose C++ object is GC'd while `isRunning()` is still True
  aborts the whole process with `qFatal()`** — no Python traceback, silent
  process death. Only a real risk for a worker that loops indefinitely
  (e.g. `_ChatWorker`) rather than finishing on its own — never
  auto-start such a worker from `__init__`, and every test that starts one
  must explicitly stop + wait for it before returning.
- **`QFormLayout` field `setVisible(False)` does not hide the row's
  label** — use `form.setRowVisible(widget, visible)` (Qt 6.4+).
- **`QGraphicsItem.scale()`/`setScale()` is uniform-only** — non-uniform
  resize is a stored `(sx, sy)` applied via a transform anchored at
  `transformOriginPoint()` (`set_item_scale()`), except rectangles/
  ellipses, which resize `rect()` directly instead (see Architecture notes
  above for why).
- **`QFontDialog.getFont(initial, parent)` returns `(ok, font)` in this
  PySide6 build, not `(font, ok)`** — getting this backwards raises
  `TypeError` inside a `clicked` slot, which Qt's dispatch silently
  swallows (prints a traceback, keeps running, button does nothing
  visible). Don't trust memory/docs for a Qt static dialog's bool
  out-param order — verify against the actual installed PySide6 version.
- **`menu.addAction(text, callback)` / `QAction.triggered.connect(cb)`
  passes `triggered`'s `checked: bool` straight through to `cb` if its
  signature accepts a positional arg there — including an *optional*
  one.** A callback with a default parameter connected directly to a menu
  action silently receives `True`/`False` instead of its intended default.
  Use a thin zero-argument wrapper when the real handler takes an
  optional parameter.
- **A modal `QMessageBox`/dialog `.exec()` blocks forever under
  `QT_QPA_PLATFORM=offscreen`** — no user to click anything. Always
  monkeypatch it out before exercising a code path that might show one.
  **This is not just a test-hygiene nicety**: a test that calls a real
  `QTimer.singleShot()` (instead of faking `QTimer`) leaves a *live* timer
  on the shared `QApplication`'s event loop after the test function
  returns — harmless-looking in isolation, but deep into a full suite run,
  once real wall-clock time has actually elapsed, it fires for real during
  some *later*, unrelated test's own event processing, potentially opening
  a real, unfaked modal dialog and recursing. Shipped once: 8 tests each
  leaking one such timer nested the whole suite 8 levels deep and ground
  it to a near-0%-CPU standstill (diagnosed with `py-spy dump --pid ...`).
  Always fake `QTimer` in a test that reaches a deferred `singleShot`.
- **A re-fetched `QMenu` via `action.menu()` can raise `RuntimeError:
  ... already deleted`** even right after working live — test the actual
  behavior you care about (e.g. `dock.toggleViewAction()`), not by
  re-querying menu objects through the widget tree after the fact.
- **`QGraphicsItem::setVisible(False)` auto-clears the item's selected
  state** — relevant to export's deselect-before-hide ordering above.
- **`QGraphicsTextItem`'s default text colour is not black** — it's
  whatever the ambient palette's `Text` role resolves to (white under a
  dark theme), so unstyled text can render invisible (white-on-white).
  `DesignScene.add_text()` calls `setDefaultTextColor(QColor("black"))`
  explicitly, since design output is meant to print on a light label.
- **Painting onto plain `QImage.Format_ARGB32` is lower-precision than
  `Format_ARGB32_Premultiplied`** for antialiased edges against
  transparency (Qt's raster engine composites in premultiplied space
  regardless, forcing an extra round-trip on a non-premultiplied target).
  `render_scene_to_image()` paints onto the premultiplied format; `.save()`
  still writes an ordinary PNG regardless.
- **`QDialog.hide()` called from inside that dialog's own `exec()` makes
  `exec()` return** — `QDialog::setVisible(false)` exits the modal event
  loop. It does *not* call `done()`, so no result is set and no
  `finished` is emitted: the call site just gets `Rejected` back and
  reads it as a cancel. Shipped once (#27's Hide button): hiding a CD rip
  took the rip window *and* the main window's progress bar with it while
  cd-paranoia carried on in a worker nobody could reach. Anything that
  needs to hide a dialog and keep it running goes through
  `panels/hideable_dialog.py`'s `exec_hideable()`, never a bare `exec()`.
- **A widget added to a `QToolBar` via `addWidget()` is wrapped in a
  `QWidgetAction`, and one added while hidden stays *disabled* even after
  it is shown again** — leaving buttons visible but dead, since
  `QAbstractButton.click()` does nothing on a disabled button. Separately,
  under `QT_QPA_PLATFORM=offscreen` such a widget never hides again once
  shown, through either its own `setVisible()` or its action's. Both bit
  the same feature (#27) in a row. Put a composite bar in an **ordinary
  layout**, not a toolbar, whenever its children's visibility or enabled
  state has to change at runtime.

**Test pattern for this app:** `QT_QPA_PLATFORM=offscreen
.venv/Scripts/python.exe -c "..."` for quick smoke scripts; a session-
scoped `qt_app` pytest fixture in `tests/conftest.py` for the real suite.
`app_settings`/`recent_projects` settings are isolated to a per-test tmp
file by autouse conftest fixtures — `templates.json`/`registry.py` is
**not** isolated the same way (tests read the real per-user file), so a
combo's display text can carry an unpredictable "(unverified dimensions)"
suffix depending on real disk state — match by the underlying template's
own `.name`, never by a combo's display text, in any test touching it.

## Workflow expectations

- Requests often arrive as dense, multi-part lists. Track every item (a
  todo list), implement all of them, and don't call the turn done until
  each has a passing test or an explicitly-flagged reason it's out of
  scope.
- Prove a fix (a regression test, or an offscreen smoke script) rather
  than just asserting it's fixed. Say plainly when something is flaky or
  not fully understood, rather than overclaiming.
- **Run only the tests relevant to what you just changed while working;
  save the full suite for the end of the task** — it's an integration
  gate, not a progress check.
- `scratchpad/` in the repo root is the user's own build/test logs. It is
  untracked and *not* in `.gitignore`, so it shows up as untracked
  forever — never `git add -A`/`git add .`, stage files by name.
- The user runs the real app and reports back concrete, specific
  symptoms — reproduce them exactly rather than generalizing away from
  the specifics.
- **One reported symptom can have several independent causes; fixing the
  first one found and shipping is how a bug gets reported twice.** "The
  progress bar disappears" turned out to be three separate defects
  (visibility tied to the wrong signal, a signal connected after the
  emission it needed, and no ownership of the bar at all), and chasing
  the third surfaced a fourth, unreported one. After a fix, ask what
  *else* could produce the same symptom before calling it done.
- **Measure a perceptual/geometric change instead of eyeballing it.** A
  complaint like "the filters are too strong" invites lowering a
  constant, which here would have left the actual defect (strength
  varying with the source image's resolution) untouched. Scoring the
  output against the input across several input sizes is what exposed
  it, and is cheap: a throwaway script in the scratchpad, not a test.
  This applies to anything in `cover_filters.py`, `grayscale.py`,
  `palette.py` or the `*_layout.py` modules, where "tuned by eye"
  constants are common and a plausible-looking number can hide a
  structural bug.
- **Physical/geometric specs often arrive in fragments across multiple
  messages, and a later correction can invalidate the *entire* previous
  reading, not just one number.** Don't build adjacent features on an
  ambiguous physical spec until it's confirmed final — a good signal it's
  final is the user restating it as one clean, self-contained sentence.
- Don't assume an earlier session's feature request is still wanted
  without checking current state — scope has been actively simplified
  before.
- **A dev-package zip refresh (plain "repackage current source") needs
  only a content diff** (extract + `diff -rq` against the live tree,
  excluding `.venv`/`.claude`/`__pycache__`/etc.) — reserve a full fresh-
  venv + install + pytest + PyInstaller cycle for when the packaging
  *approach* itself changes.
- **The user manual is generated and trilingual** — a UI text/menu change
  invalidates screenshots in *all three* languages at once; regenerate via
  `scripts/manual/make_screenshots.py` rather than patching one image, and
  keep the PL/JA manual text in step with `i18n/mdtools_{pl,ja}.ts`'s own
  menu-name translations. **Redo only the figures that actually changed**:
  `make_screenshots.py --only cd-rip,settings` (`--list` names them all,
  grouped by the section that produces them; a group nothing was asked
  from is skipped outright, and every other file is left byte-for-byte
  alone so the diff shows only what moved). A new figure must be added to
  `FIGURE_GROUPS` or `save()` refuses it. **Deferred, by explicit user preference**: don't
  run `pyside6-lupdate`/regenerate the manual mid-feature-set — batch it
  once the whole set of changes has settled, not after every individual
  string change.
- **A new built-in template reaches existing installs automatically** via
  `registry.sync_builtin_templates()` (see Domain model above) — no manual
  per-user `templates.json` edit needed any more.
