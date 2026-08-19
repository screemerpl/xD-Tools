# xD-Tools

A desktop workbench for retro music media: MiniDisc, CD-R and compact
cassette. (The x stands in for M or C -- which started as a joke and then
turned out to be the description.)

**Design** labels and inserts for any of them -- a MiniDisc's sticker and
J-card, a CD's ring label and case inserts, or a cassette's inlay card and a
sticker for each side -- exporting standards-compliant SVG (cut lines) and
PNG (print artwork) for use with Cricut Design Space and a regular printer.

**Record and title** -- with an MDRem infrared adapter, record an album
straight from foobar2000 with a track mark at every song, write the disc and
track titles onto the MiniDisc itself, lay out both labels from the album's
own artwork, and use the software remote to drive the deck.

**Record from a CD** -- pick an optical drive, and xD-Tools extracts the disc
to FLAC with the bundled cdparanoia and flac, identifies it on MusicBrainz
from its table of contents, loads the tracks into foobar2000 in disc order,
and hands over to the same recording flow.

**Record from a folder** -- point xD-Tools at an album you already have on
disk, in any format foobar2000 plays, and it loads those files into the
playlist in filename order and records them the same way.

**Burn an audio CD** -- point it at a folder or at foobar2000's playlist and
it writes a Red Book CD-R with the bundled cdrecord, disc-at-once, with
CD-Text titles. Anything that is not already 44.1 kHz / 16-bit stereo (a
hi-res download, say) is resampled by the bundled SoX on the way, and the
plan says so per track before the disc is committed -- a CD-R cannot be
edited afterwards.

**Record a cassette** -- pick the tape you have (C46 to C100) and xD-Tools
works out where the album is turned over, balancing the two sides rather
than filling the first. It records ten seconds of silence past the leader,
plays exactly that side's tracks -- telling foobar2000 to stop at the break
rather than catching it afterwards -- and then says, in as many words, to
stop the deck and turn the cassette over. The deck itself stays yours to
operate: xD-Tools presses nothing.

**Mixtapes too** -- a disc or playlist whose tracks are by different artists
is recognised as a compilation, credited to Various Artists rather than to
whoever happened to be first, and given a cover drawn from its own track
list, since there is no sleeve to look up.

## Manual

A full user manual lives in [`doc/`](doc/), as a PDF in each of the three
languages the app itself speaks:
[English](doc/xD-Tools-Manual-EN.pdf),
[Polski](doc/xD-Tools-Manual-PL.pdf),
[日本語](doc/xD-Tools-Manual-JA.pdf).
It is generated -- text and screenshots both -- see [`doc/README.md`](doc/README.md)
for how to rebuild it.

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
  foobar.py               foobar2000 over its Beefweb REST API, plus its command line
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
    record_dialog.py         record from foobar2000 onto the deck, then title it
    cd_rip_dialog.py         rip a CD into foobar2000's playlist, then record it
    folder_record_dialog.py  load a folder of audio files into that playlist instead
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
  track numbers, play modes, display and titling keys.

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

### Recording a whole album from foobar2000

**Recording > Record to MiniDisc from foobar2000...** does the whole job in
one go: it arms the deck, plays the album out of foobar2000 over S/PDIF,
watches it to the end, then writes the titles.

You need foobar2000 running with the **Beefweb Remote Control**
(`foo_beefweb`) component enabled -- that is how xD-Tools reads the playlist
and knows which track is playing. Its address is configurable in
**Window > Settings...** if you moved it off the default port.

Load the album in foobar2000, connect its S/PDIF output to the deck, then:

1. xD-Tools shows the playlist, its total time, and warns if it won't fit on
   an 80-minute disc in SP mode.
2. It sets foobar to play straight through once (no shuffle, no repeat) and
   tells the deck to start recording.
3. **It asks you to confirm the deck really is in record-pause** -- there is
   no way for it to check, and getting this wrong wastes the whole album.
4. Recording runs; you can follow which track is going down and how much is
   left. Stopping stops both foobar and the deck.
5. When the album ends it offers to write the titles, taken from the
   playlist itself rather than from an online lookup -- that is exactly what
   went onto the disc, in that order.
6. The album, artist, year and track list become the project's metadata,
   its cover art is looked up, and **the disc label lays itself out**: the
   full-face template, the cover cropped to the cut outline, and the
   MiniDisc logo on the write-protect slider sticker. Note this **replaces
   whatever was on the disc page** -- it is a starting point to adjust, not
   an addition to your design.

Two caveats:

- **Leave "Mark tracks through the adapter" ticked, and turn LEVEL-SYNC off
  on the deck.** Left to itself the deck starts a new track when the sound
  drops to silence and comes back, which silently merges any two songs that
  run into each other. xD-Tools instead sends a track mark at the exact
  moment foobar changes track. Running both at once is what causes trouble:
  each marks a slightly different spot and you get a sliver of a track in
  between.
- **Set the recording mode (SP/LP2) on the deck yourself.** xD-Tools has no
  reliable way to read or change it.

### Recording an album from a folder of files

**Recording > Record Folder to MiniDisc...** records an album that is already
on disk. Browse to the folder, and xD-Tools loads those files into foobar2000
and hands over to the recording above -- the same arming, track marks and
titling.

- **Which files**: anything foobar2000 plays (FLAC, MP3, M4A, OGG, Opus,
  WAV, ...). Artwork, cue sheets and logs are ignored.
- **What order**: the filenames, compared so `10` follows `9` rather than
  `1`. A folder that holds tracks *is* the album and its subfolders are left
  alone; only a folder with no audio directly in it is looked inside, which
  is what puts a two-disc album kept as `CD1`/`CD2` in disc order.
- **Where the titles come from**: the files' own tags, read by foobar2000
  rather than by xD-Tools -- it is the better tag reader of the two and has
  to read them anyway to play them. A file with no title tag is recorded
  under its filename.
- **The album and artist** start out guessed from the folder's name
  (`Artist - Album (Year)`), are replaced by the tags as soon as the tracks
  load, and are replaced again by anything you type over them. That is the
  only way a correction reaches the disc: nothing here writes to your files.

Loading a folder **empties foobar2000's current playlist**, exactly as
recording a CD does.

### Filling in metadata from foobar2000

You don't have to be recording to use foobar2000 as a metadata source.
**Metadata... > Load from foobar2000** fills in the album, artist,
year and the whole track list from whatever is in foobar's current playlist,
then looks up the cover art for it. Handy when you ripped a CD and just want
a label for it -- the tags on the actual files beat a search, and the track
order is guaranteed to be the one you have.

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

**Templates > Change Template for This Page...** switches the page you're on
to a different template -- previously only possible when creating a project.

**It clears the page**: every layer on it is removed and the undo history is
reset, so it asks for confirmation first. The other page and the project's
metadata are left alone. A disc page then starts again the way a new one
does, with the "▲ INSERT THIS END" triangle and label ready to reposition.

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
