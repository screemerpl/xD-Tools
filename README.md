# xD-Tools

A desktop workbench for retro music media: MiniDisc, CD-R and compact
cassette. (The x stands in for M or C -- which started as a joke and then
turned out to be the description.)

**Design** labels and inserts for any of them -- a MiniDisc's sticker and
J-card, a CD's ring label and case inserts, or a cassette's inlay card and a
sticker for each side -- exporting standards-compliant SVG (cut lines) and
PNG (print artwork) for use with Cricut Design Space and a regular printer.

**Record and title** -- with an MDRem infrared adapter, record an album from
a CD or a folder of files, with a track mark at every song, write the disc
and track titles onto the MiniDisc itself, lay out both labels from the
album's own artwork, and use the software remote to drive the deck. xD-Tools
decodes and plays the audio itself (no external player involved).

**Record from a CD** -- pick an optical drive, and xD-Tools extracts the disc
to FLAC with the bundled cdparanoia, identifies it on MusicBrainz from its
table of contents, and hands the ripped files over to the same recording
flow, in disc order.

**Record from a folder** -- point xD-Tools at an album you already have on
disk and it reads those files' own tags directly, in filename order, and
records them the same way.

**Burn an audio CD** -- point it at a folder of files and it writes a Red
Book CD-R with the bundled cdrecord, disc-at-once, with CD-Text titles.
Anything that is not already 44.1 kHz / 16-bit stereo (a hi-res download,
say) is resampled by xD-Tools' own audio engine on the way, and the plan
says so per track before the disc is committed -- a CD-R cannot be edited
afterwards.

**Record a cassette** -- pick the tape you have (C46 to C100) and xD-Tools
works out where the album is turned over, balancing the two sides rather
than filling the first. It records ten seconds of silence past the leader,
plays exactly that side's tracks, and then says, in as many words, to stop
the deck and turn the cassette over. The deck itself stays yours to
operate: xD-Tools presses nothing.

**Mixtapes too** -- a disc or playlist whose tracks are by different artists
is recognised as a compilation, credited to Various Artists rather than to
whoever happened to be first, and given a cover drawn from its own track
list, since there is no sleeve to look up.

## Manual

The same manual is also on the
**[GitHub Wiki](https://github.com/screemerpl/xD-Tools/wiki)**, one page per
chapter, English only -- start at
[Getting started](https://github.com/screemerpl/xD-Tools/wiki/02-Getting-started)
or jump straight to
[Troubleshooting](https://github.com/screemerpl/xD-Tools/wiki/18-Troubleshooting).

A full user manual also lives in [`doc/`](doc/), as a PDF in each of the three
languages the app itself speaks:
[English](doc/xD-Tools-Manual-EN.pdf),
[Polski](doc/xD-Tools-Manual-PL.pdf),
[日本語](doc/xD-Tools-Manual-JA.pdf).
It is generated -- text and screenshots both -- see [`doc/README.md`](doc/README.md)
for how to rebuild it.

## Installing on Windows

`scripts/build_installer.ps1` wraps the PyInstaller build in an NSIS
installer -- `dist/xD-Tools-<version>-setup.exe`, one file, no Python and
no Qt to install first. It puts the app in `Program Files`, adds a Start
Menu entry (and optionally a desktop shortcut), and registers a proper
entry in Add/Remove Programs.

```powershell
winget install NSIS.NSIS          # once
./scripts/build_installer.ps1     # builds the app, then the installer
./scripts/build_installer.ps1 -SkipBuild   # installer only, reusing dist/
```

Uninstalling leaves `%LOCALAPPDATA%\MDTools` alone -- your templates,
settings and language choice survive a reinstall.

## Stack

- **PySide6 (Qt for Python)** for the GUI. Chosen over Tkinter/CustomTkinter
  because the design canvas needs real vector graphics (`QGraphicsView` /
  `QGraphicsScene`), precise text/shape manipulation, and native SVG export
  (`QtSvg`) -- all first-class in Qt and runs identically on Windows and Linux.
- **Pillow** for image handling beyond Qt's built-in codecs (available for
  future image-processing features).
- **PyInstaller** to produce a standalone `.exe` (Windows) / binary (Linux).
- **pytest** + **pytest-qt** for tests.

## Project layout

```
src/mdtools/
  constants.py          mm <-> px conversion helpers
  main.py                entry point
  app_window.py           main window: page switcher, menus, docks, wiring
  project.py              Project / ProjectMetadata / Track dataclasses
  mdrem.py                MDRem infrared adapter: serial protocol, upload plan
  audio_engine.py         FLAC decode/encode, resampling, dithering, playback (soundfile/soxr/sounddevice)
  tracks.py               track list + metadata from files' own tags (no external player)
  cdrip.py                audio CD: drives, table of contents, extraction to FLAC
  musicbrainz.py          identifying a CD from its table of contents
  audio_folder.py         which files in a folder are the album, and in what order
  mixtape_cover.py        draws a cover for a compilation, from its track list
  canvas/
    scene.py              DesignScene: template outline + design items
    view.py                zoomable/pannable view + mouse scale/rotate handles
    items.py               "cut" vs "print" layer tagging helpers
    geometry.py            chamfered/filleted rectangle path builder
  templates/
    models.py              DiscTemplate / CoverTemplate dataclasses
    registry.py             load/save templates (per-user JSON, seeded from defaults.json)
    defaults.json           built-in templates (see warning below)
    template_dialog.py      Template Manager UI
  panels/
    tool_panel.py           add text/rectangle/image buttons + "insert from metadata" menu
    properties_panel.py     edit selected item (position, rotation, text, font size, color)
    layers_panel.py         list + select + reorder + delete items
    new_design_dialog.py     disc+cover template pickers for File > New
    metadata_dialog.py       album/artist/year/track-list editor
    record_dialog.py         record onto the deck (own playback engine), then title it
    cd_rip_dialog.py         rip a CD to FLAC, then hand the files to record_dialog
    folder_record_dialog.py  read a folder of audio files' own tags instead
  io/
    svg_export.py           exports just the cut/fold shapes as physically-accurate SVG
    png_export.py           exports print artwork as PNG, clipped to the template outline
    project_io.py            save/load a whole project as one self-contained .mdproj JSON
bin/win64/              bundled cdparanoia + flac (Windows only) -- see its ATTRIBUTION.md
tests/
scripts/
  build_windows.ps1
  build_linux.sh
```

## A project = one disc label + one cover, plus metadata

Every project has exactly two pages -- a **Disc Label** and a **Cover /
J-Card** -- switchable via the dropdown in the toolbar. **File > New...**
asks for one template of each kind to start both. **Metadata...** in the Tools
panel opens a dialog for album title, artist, year of release, and an optional
track list (title + optional mm:ss time) -- handy to have next to the
J-card while laying out the tracklist text.

**File > Save** (Ctrl+S) writes everything -- both pages' designs *and* any
images you've placed (embedded as base64 PNG, not by file path) -- into a
single `.mdproj` JSON file, reusing the current file once one exists.
**Save As...** (Ctrl+Shift+S) always prompts for a location. Moving/
renaming the project file afterwards, or deleting the original image you
imported, doesn't break it.

**File > Close Project** (Ctrl+W), and the window's close button, go back to
the startup screen rather than quitting -- switching to another project
doesn't mean relaunching xD-Tools. Unsaved changes are asked about first. To
leave for good, use **File > Exit**, or cancel the startup screen.

## Disc label geometry

The disc template is a **37 x 52 mm rectangle** with a **3 mm chamfer**
(straight diagonal cut) on the top-left corner and a **1 mm fillet**
(rounded corner) on the other three -- this was given directly and is
trusted as-is (`verified: true`). The cover/J-card template's dimensions
are still an **unverified placeholder** -- open **Templates > Manage
Templates**, measure your physical case, correct width/height/fold
positions, and tick "Verified" once confirmed. The status bar warns
whenever the page you're viewing uses an unverified template.

Built-in templates (marked `[built-in]` in the Template Manager) can be
edited but not deleted, so there's always at least one disc and one cover
template available for File > New; templates you add yourself can be
deleted freely.

A new disc page starts with a "▲" triangle and an "INSERT THIS END" label
near the top -- the conventional MiniDisc insertion-orientation marking.
Both are ordinary text items: move, restyle, or delete them like anything
else. Loading an existing saved project never re-adds them.

## Editing

- **Tools** panel: add text, a color-filled rectangle, or an image, or
  insert text straight from the project's metadata (album title, artist,
  year, or any track) via **Insert from Metadata** -- fill that in first
  via **Metadata...**, the button next to it.
- Click an item to select it; drag its **body** to move it. **Properties**
  only shows the fields that actually apply to the selected item's type:
  text gets Text/Font size/Font.../Color, shapes get Color, images get
  neither. **Font...** opens the full system font-picker (family, size,
  weight, italic, ...) for text.
- Drag a **corner handle** (blue square) to resize -- by default width and
  height change independently (a non-proportional stretch); hold **Ctrl**
  to scale proportionally instead. Drag the **handle above it** (blue
  circle) to rotate; hold **Ctrl** while rotating to snap to 10-degree
  steps, handy for exact 90/180-degree turns. These handles are drawn on
  top of everything -- including the red/blue template cut/fold lines,
  which always render above your artwork so you can see them while
  positioning things -- but neither the handles nor that top-of-stack
  render order affects the exported SVG/PNG.
- **Zoom In** / **Zoom Out** / **Fit** buttons on the toolbar (or Ctrl +
  mouse wheel, or Ctrl+= / Ctrl+- ) control the canvas view.
- Select a layer in **Layers** -- either from the list or by clicking it on
  the canvas -- and use **Move Up** / **Move Down** to reorder it
  (front-to-back stacking) or **Delete Layer** (or press Delete/Backspace
  on the canvas) to remove it. Only things you've added can be managed this
  way -- the template outline itself isn't a layer.

## Workflow

1. **File > New...** and pick a disc template and a cover template.
2. Switch between **Disc Label** / **Cover / J-Card** with the toolbar
   dropdown; each has its own independent design.
3. **Metadata...** in the Tools panel to fill in album/artist/year/tracks.
4. **File > Export Print PNG...** -- your artwork at 300 DPI by default,
   clipped to the template's cut outline (transparent outside it, including
   the chamfered/filleted-away corners). Print this normally.
5. **File > Export Cut SVG...** -- just the current page's cut/fold shapes,
   nothing else, in real physical units. Import into Cricut Design Space,
   align it with the printed PNG using Print Then Cut, and cut.
6. **File > Save** (Ctrl+S) to keep working later (single `.mdproj` file).

## Writing titles onto the disc itself (MDRem)

xD-Tools can also write the album and track names onto the MiniDisc, not
just onto a printed label -- via **MDRem**, a small RP2040 board that
emulates a Sony RM-D10P infrared remote and connects over USB.

Turn it on in **Window > Settings...** ("Enable MDRem IR remote adapter"),
pick the serial port, or press **Detect** to have xD-Tools ask each port
whether an adapter answers. Two things then appear:

- **Metadata... > Upload Tracklist** writes the disc title
  (`Artist - Album (Year)`) and every track name onto the disc. It shows
  exactly what it will write first, then works through it with a progress
  bar.
- **Remote...** on the startup screen opens a software remote -- transport,
  track numbers, play modes, display and titling keys. That is the physical
  Sony remote, key for key; **Extended mode** adds everything else the
  adapter can send -- tracks up to 25, the deck's own character entry, the
  keys that erase or divide a track -- and turns your own keyboard into the
  deck's, typing straight into a title as you press the keys.

Worth knowing before you use it:

- **It is slow.** The deck accepts about three and a half keypresses per
  second and every character is its own infrared frame, so a full album
  takes three to four minutes. That is the deck's limit, not the adapter's
  -- the original Sony remote was no faster. The point is that you type on
  a real keyboard and walk away, instead of spelling titles out by hand.
- **Untick "Erase existing titles first" on a freshly recorded disc.**
  Clearing the old title is the slowest part of writing a new one and
  roughly doubles the total time, but it is only needed when there is
  something to replace -- leave it ticked when overwriting existing
  titles, or the old text stays behind.
- **Titles are converted to plain ASCII.** MiniDisc decks only display
  0x20-0x7E, so accented letters lose their marks (`Zażółć` -> `Zazolc`)
  and anything with no Latin equivalent at all is dropped. The upload
  dialog lists those characters before writing anything.
- **Nothing can be verified.** The deck has no way to talk back, so a
  successful upload only means every command was sent -- check the result
  on the deck itself.
- **Eject when you're done.** A deck keeps edited titles in volatile
  memory until the disc is ejected; the upload dialog offers to do it.
- Aim the adapter at the deck's remote sensor and leave it undisturbed for
  the whole upload.

### How a recording works

Both **Record CD to MiniDisc...** and **Record Folder to MiniDisc...** end
in the same recording window, once the files are ready (ripped, or read
off disk -- see the two sections below). xD-Tools decodes and plays those
files itself, with no external player involved:

1. xD-Tools shows the track list, its total time, and warns if it won't fit
   on an 80-minute disc in SP mode.
2. It tells the deck to start recording.
3. **It asks you to confirm the deck really is in record-pause** -- there is
   no way for it to check, and getting this wrong wastes the whole album.
4. Recording runs; you can follow which track is going down and how much is
   left. Stopping stops both playback and the deck.
5. When the album ends it offers to write the titles, taken from the track
   list itself rather than from an online lookup -- that is exactly what
   went onto the disc, in that order.
6. The album, artist, year and track list become the project's metadata,
   its cover art is looked up, and **the disc label lays itself out**: the
   full-face template, the cover cropped to the cut outline, and the
   MiniDisc logo on the sliding dust shutter's sticker. Note this **replaces
   whatever was on the disc page** -- it is a starting point to adjust, not
   an addition to your design.

Two caveats:

- **Leave "Mark tracks through the adapter" ticked, and turn LEVEL-SYNC off
  on the deck.** Left to itself the deck starts a new track when the sound
  drops to silence and comes back, which silently merges any two songs that
  run into each other. xD-Tools instead sends a track mark at the exact
  sample playback crosses into the next track. Running both at once is what
  causes trouble: each marks a slightly different spot and you get a sliver
  of a track in between.
- **Set the recording mode (SP/LP2) on the deck yourself.** xD-Tools has no
  reliable way to read or change it.
- **Which sound card output plays the audio, and how loud**, are both set
  in **Window > Settings...** ("Audio output device" and "Recording gain").

### An album across several discs

A double album does not fit on a MiniDisc, and a MiniDisc cannot be turned
over. **Record across several discs**, in the recording window, records it a
disc at a time: one disc, then -- two seconds after its last track, without
asking -- its titles, then eject, then a prompt for the next blank. Each disc
is titled `Album [1/2]`, `Album [2/2]`, and its tracks are numbered from one,
which is how the deck numbers them anyway.

Where the album is cut comes from the files when they say so: the track
list is put into disc-then-track order as the window opens (a two-disc set
dropped into one folder arrives interleaved, because both discs number
their tracks from one), and the splits are placed where the disc numbers
say. Otherwise the album is
divided as evenly as its running order allows, into the fewest discs that
fit. **Move Up/Down**, **Start Disc Here** and **Split Automatically** adjust
any of it by hand.

The same option exists on both CD flows: **Burn across several discs** writes
a long album onto as many CD-Rs as it needs, ejecting between them and asking
for the next blank, and **Rip several discs as one album** copies a boxed set
into one folder as a single album, tagging each file with the disc it came
from.

### Recording an album from a folder of files

**Recording > Record Folder to MiniDisc...** records an album that is already
on disk. Browse to the folder, and xD-Tools reads those files' own tags
directly and hands over to the recording above -- the same arming, track
marks and titling.

- **Which files**: FLAC, MP3, M4A, OGG, Opus, WAV, and the other common
  lossless/lossy formats. Artwork, cue sheets and logs are ignored.
- **What order**: the filenames, compared so `10` follows `9` rather than
  `1`. A folder that holds tracks *is* the album and its subfolders are left
  alone; only a folder with no audio directly in it is looked inside, which
  is what puts a two-disc album kept as `CD1`/`CD2` in disc order.
- **Where the titles come from**: the files' own tags, read directly with
  `mutagen`. A file with no title tag is recorded under its filename.
- **The album and artist** start out guessed from the folder's name
  (`Artist - Album (Year)`), are replaced by the tags as soon as the tracks
  load, and are replaced again by anything you type over them. That is the
  only way a correction reaches the disc: nothing here writes to your files.

### Filling in metadata from a folder

You don't have to be recording to use a folder as a metadata source.
**Metadata... > Import from Folder...** fills in the album, artist,
year and the whole track list from a folder's own tags, then looks up the
cover art for it. Handy when you ripped a CD and just want a label for it --
the tags on the actual files beat a search, and the track order is
guaranteed to be the one you have.

**If the cover that comes back is the wrong one, click it.** The preview in
the Metadata dialog is a button: it opens a file picker so you can point at
the right sleeve yourself. Both automatic sources guess, and for a reissue,
a compilation or a band with a common name they regularly guess wrong.

### Building both labels from the metadata

The **magic wand** button in the Tools panel lays out the whole project --
the same thing the recording flow ends with, for a project you never
recorded. If there is no cover art yet, it looks one up first.

**Disc label**: the full-face template, the cover cropped to the cut
outline, and the MiniDisc logo on the write-protect slider. The "▲ INSERT
THIS END" mark stays on top of the artwork and switches to black or white,
whichever is readable against the top of that particular cover.

**J-card**: the three panels of the case insert, with every colour taken
from the cover itself.

- *Front* -- the cover art, turned a quarter turn so its top edge runs down
  the left side of the card, stretched to fill the panel, with a small
  MiniDisc logo in the corner.
- *Spine* -- a band in an accent colour picked out of the cover, carrying
  the year, album and artist turned to read down it, plus the logo.
- *Back* -- the cover's most common colour, with the numbered track list
  (split into two columns once the list gets long).

It **replaces both pages** and resets the undo history, so it asks before
doing it. Fill in album and artist in **Metadata...** first -- that
is what it searches by. Everything it produces is ordinary layers: move,
restyle or delete them like anything else.

### Changing a template on an existing project

The **Template** dropdown on the toolbar, next to the page selector, lists
every template available for the page you're on -- previously only possible
when creating a project. Picking one of your own (built with **Save as
Template...** or added in the Template Manager) switches the page onto it
right away; picking a built-in one asks first, offering **Empty Template** or,
where the page's automatic layout actually has a generator for that exact
template, **Generated from Metadata**.

**Either way it clears the page**: every layer on it is removed and the undo
history is reset, so a built-in choice asks for confirmation first. The other
page and the project's metadata are left alone. A disc page started empty
then begins again the way a new one does, with the "▲ INSERT THIS END"
triangle and label ready to reposition.

Adding or removing an optional page (a CD project's case back) is the **+**/
**-** pair right beside the page selector.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m mdtools.main
```

(or `.venv/bin/...` on Linux/macOS)

## Tests

```
.venv\Scripts\python -m pytest
```

## Building a standalone executable

```powershell
scripts\build_windows.ps1   # -> dist\xD-Tools\xD-Tools.exe
```

```bash
scripts/build_linux.sh      # -> dist/xD-Tools/xD-Tools
```

## License

GPL-3.0-or-later -- see [`LICENSE`](LICENSE).
