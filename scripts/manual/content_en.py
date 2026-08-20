"""English text of the user manual. See build_manual.py for the block
vocabulary ("p", "ul", "ol", "table", "fig", "note", "warn", "tip", "h2").

Inline marks: **bold**, `literal`.
"""

TITLE = "xD-Tools"
SUBTITLE = "Retro Media Studio - User Manual"
TITLE_NOTE = "Designing labels, recording MiniDiscs and cassettes, burning CD-Rs, and titling discs"
COVER_CAPTION = "What talks to what: commands over USB, keys over infrared, audio over S/PDIF."
VERSION_LINE = "Version 0.3.0"
AUTHOR_LINE = 'Artur "Screemer" Jakubowicz'
DATE_LINE = "August 2026"
TOC_TITLE = "Contents"
FOOTER_LEFT = "xD-Tools - Retro Media Studio - User Manual"

BOOK = [
    # ------------------------------------------------------------------
    {
        "title": "What this is",
        "blocks": [
            {"p": "xD-Tools is a desktop workbench for retro music media: MiniDisc, CD-R and compact "
                  "cassette. (The x stands in for M or C - which began as a joke and turned out to be "
                  "the description.) It started as a label designer and grew into a handful of tools "
                  "that share one project file:"},
            {"ul": [
                "**Design** the labels: a MiniDisc's sticker and J-card, a CD's ring label and case "
                "inserts, or a cassette's inlay card and a sticker for each side - and export them "
                "ready to print and cut.",
                "**Record** a whole album from foobar2000 onto a MiniDisc, with a proper track mark at "
                "every song.",
                "**Burn** an audio CD-R from a folder or from foobar2000's playlist, with CD-Text titles.",
                "**Record a cassette** side by side, with the album split where it fits and the deck "
                "left to you - xD-Tools says what to press.",
                "**Title** a MiniDisc: write the album name and every track name onto the disc itself, "
                "so the deck's own display shows them.",
                "**Drive the deck** from a software remote - transport, track numbers, play modes.",
            ]},
            {"p": "**Which medium a project is for is chosen once, when you create it**, and everything "
                  "follows from that: which templates you are offered, what the second page is called, "
                  "and which entries the Recording menu shows. A MiniDisc project is never offered CD "
                  "burning, and a CD project is never offered the deck's remote."},
            {"p": "The first of those needs nothing but the computer. The other three need **MDRem**: a "
                  "small RP2040 board that pretends to be a Sony RM-D10P infrared remote and plugs into "
                  "USB. Everything MDRem-related is optional and switched off until you turn it on."},
            {"fig": ("signal-chain", COVER_CAPTION)},
            {"p": "Three separate links, and it is worth being clear about which carries what. The USB "
                  "cable carries commands and nothing else - no audio ever travels over it. The infrared "
                  "beam carries keypresses, exactly as a handheld remote would. The audio takes the third "
                  "path entirely, over S/PDIF, and is needed only when recording."},
            {"h2": "What you need"},
            {"table": {
                "head": ["For", "You need"],
                "rows": [
                    ["Designing and printing", "xD-Tools, a printer, and - for cutting - a Cricut machine "
                                               "or a steady hand with scissors."],
                    ["Titling a disc", "An MDRem adapter on a USB port, and a Sony MiniDisc deck it can be "
                                       "aimed at."],
                    ["Recording an album", "The above, plus foobar2000 with the Beefweb component, and a "
                                           "digital (S/PDIF) cable from the computer to the deck - or an "
                                           "analogue one, at a real cost in quality."],
                ],
            }},
            {"note": "Everything in this manual was worked out against a **Sony MDS-JE480**. Other Sony "
                     "decks that accept the RM-D10P keyboard protocol should behave the same way, but the "
                     "timings in particular were measured on that one."},
            {"h2": "One thing to understand up front"},
            {"p": "The deck cannot answer. Infrared only travels one way, and this model's Control A1 bus "
                  "is not connected inside. So xD-Tools can send a command, but it can never find out "
                  "whether the deck did it."},
            {"p": "That shapes the whole MDRem half of the program: it shows you exactly what it is about "
                  "to do before it does it, it errs on the side of doing too much rather than too little "
                  "(clearing an old title with more keypresses than can possibly be needed), and when it "
                  "reports success it means \"everything was sent\", never \"the disc now says this\". "
                  "Check the deck's display yourself."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Getting started",
        "blocks": [
            {"h2": "Installing"},
            {"p": "If you have the packaged build, run `xD-Tools.exe`. From source:"},
            {"ul": [
                "`python -m venv .venv`",
                "`.venv\\Scripts\\pip install -e \".[dev]\"`",
                "`.venv\\Scripts\\python -m mdtools.main`",
            ]},
            {"h2": "Choosing a language"},
            {"p": "**Help > Language** offers English, Polski and Japanese. The change needs a restart, "
                  "and the dialog offers to do it for you."},
            {"h2": "The startup screen"},
            {"p": "xD-Tools opens on a short list of what you might want to do: reopen one of the last few "
                  "projects, browse for another one, or start a new one."},
            {"fig": ("startup", "The startup screen. Remote... only appears once the adapter is enabled.")},
            {"ul": [
                "**Open Selected** / double-click - reopen a recent project.",
                "**Open Other Project...** - browse for a `.mdproj` file anywhere.",
                "**New Project...** - pick a template for each of the two pages.",
                "**Multiprint...** - put artwork from several different projects on one sheet of paper. "
                "This one does not open a project at all; it is a standalone job.",
                "**Remote...** - the software remote. Also standalone, and only shown when MDRem is "
                "enabled.",
            ]},
            {"h2": "A project is two pages plus metadata"},
            {"p": "Every project holds exactly one **Disc Label** design and one **Cover / J-Card** "
                  "design, switched with the dropdown at the top left of the main window. Alongside them "
                  "it holds the album title, artist, year and track list - which the label designs, the "
                  "titling and the automatic layout all draw on."},
            {"fig": ("new-project", "File > New asks for one template of each kind.")},
            {"p": "**File > Save** (Ctrl+S) writes all of that - both designs, the metadata, and any "
                  "images you placed - into a single `.mdproj` file. Images are embedded, not linked, so "
                  "moving the project or deleting the original picture cannot break it."},
            {"h2": "Closing a project"},
            {"p": "**File > Close Project** (Ctrl+W) brings the startup screen back rather than quitting, "
                  "so moving on to another disc is not a trip through relaunching the program. The "
                  "window's own close button does the same thing. If there are unsaved changes you are "
                  "asked about them first."},
            {"p": "To leave xD-Tools altogether, use **File > Exit**, or cancel the startup screen when it "
                  "reappears."},
            {"h2": "Where your projects are saved"},
            {"p": "The first time you save, xD-Tools proposes **Documents\\MiniDiscProjects** and a file "
                  "name built from the album itself - `Skillet - Unleashed (2016).mdproj`. That is the "
                  "same line the deck is told to display, so the file on your computer and the title on "
                  "the disc agree with each other."},
            {"p": "Other file dialogs start somewhere sensible too: **Add Image...** and cover art open "
                  "in your Pictures folder, and the SVG, PNG and PDF exports open **next to the project "
                  "they came from**, so the design and the files that cut and print it stay together."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "The main window",
        "blocks": [
            {"fig": ("main-disc", "The disc label page, laid out automatically from an album.")},
            {"h2": "The canvas"},
            {"p": "The middle of the window is the page you are editing, drawn at its real physical size. "
                  "The red and blue lines are the template's cut and fold lines - they are always drawn "
                  "on top of your artwork so you can see where the edges are, and they never appear in an "
                  "exported PNG. The hatched area outside them is the part that gets cut away."},
            {"ul": [
                "**Zoom In / Zoom Out / 100% / Fit** on the toolbar, or Ctrl with the mouse wheel, or "
                "Ctrl+= and Ctrl+-.",
                "**Grayscale** previews the page the way a black-and-white print will look, with "
                "brightness and contrast sliders that appear next to it. It is view-only - the canvas "
                "goes read-only while it is on - and what you dial in here is what Export Print PNG "
                "(Grayscale) will use.",
            ]},
            {"h2": "The three panels"},
            {"p": "**Tools** (left) adds things to the page: text, a filled rectangle, an image from a "
                  "file, an image from the built-in gallery, or text taken straight from the project's "
                  "metadata. **Metadata...** - the album's own details - lives here too, beside the "
                  "layers it feeds. Below the separator are the four page-wide operations - Clip "
                  "Layers, Bake Layers, Save as Template and Auto-Layout. Every button is icon-only; "
                  "hover for its name."},
            {"p": "**Properties** (top right) edits whatever is selected, and shows only the fields that "
                  "apply to it: text gets its content, size, font and colour; a rectangle gets a colour; "
                  "an image gets neither. **Probe...** picks a colour off the canvas itself, which is how "
                  "you match text to a colour in the cover art."},
            {"p": "**Layers** (bottom right) lists everything on the page, front to back. Select, rename, "
                  "reorder with Move Up / Move Down, or delete. The template outline is not a layer and "
                  "cannot be touched here."},
            {"note": "All three panels can be closed and reopened from the **View** menu, and dragged out "
                     "into floating windows."},
            {"h2": "Moving, scaling and rotating"},
            {"ul": [
                "Drag an item's **body** to move it.",
                "Drag a **corner handle** (blue square) to resize. By default width and height change "
                "independently; hold **Ctrl** to keep the proportions.",
                "Drag the **circle above it** to rotate. Hold **Ctrl** to snap to 10-degree steps, which "
                "is how you get an exact quarter turn.",
                "Delete or Backspace removes the selection.",
            ]},
            {"p": "Everything goes through undo (Ctrl+Z), including the automatic layouts."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Templates",
        "blocks": [
            {"p": "A template is the physical shape of the thing you are printing: its size, its corners, "
                  "and where it folds. xD-Tools ships with six."},
            {"table": {
                "head": ["Template", "What it is"],
                "rows": [
                    ["MiniDisc Disc Label", "The classic 37 x 52 mm sticker for the front of the disc, "
                                            "with a 3 mm chamfer on the top-left corner and rounded "
                                            "corners elsewhere."],
                    ["MiniDisc Disc Label (with Slider)", "The same, plus a separate small sticker for "
                                                          "the cartridge's sliding shutter."],
                    ["Full disc label", "A label covering the whole 71 x 68 mm face of the cartridge, "
                                        "inset by a 0.8 mm margin, with the shutter cut out of it."],
                    ["Full disc label (with Slider)", "The full face plus the shutter sticker, nested into "
                                                      "the cutout it sits in. This is what the automatic "
                                                      "layout uses."],
                    ["MiniDisc Cover (J-Card)", "The three-panel insert for the case: front, spine, back."],
                    ["MiniDisc Cover (J-Card + Window)", "The same with a cut-out window."],
                ],
            }},
            {"note": "The **shutter** is the sliding panel on the cartridge that keeps dust off the disc - "
                     "the deck pushes it aside to reach the surface. It is not the write-protect tab, which "
                     "is a separate small catch on the cartridge's edge and never gets a label. Because the "
                     "shutter has to keep sliding, the full-face templates cut a channel for its whole "
                     "travel rather than just its resting position: a label over that channel would jam it "
                     "shut."},
            {"fig": ("templates", "Templates > Manage Templates.")},
            {"h2": "Verified and unverified"},
            {"p": "A template is marked **Verified** once its dimensions have been checked against a real "
                  "part. When you are looking at a page whose template is not verified, the status bar "
                  "says so - measure your own case, correct the numbers here, and tick the box before "
                  "cutting anything for real."},
            {"h2": "Making your own"},
            {"p": "Built-in templates can be edited but not deleted, so File > New always has something to "
                  "offer. Ones you add yourself can be deleted freely."},
            {"p": "**Tools > Save as Template...** captures the current page's shape *and everything on "
                  "it* as a new template, so a layout you like can be the starting point for the next "
                  "disc."},
            {"h2": "Adding and removing pages"},
            {"p": "A project starts with two pages -- the disc label and the cover -- and a CD project "
                  "can have a third: the **case back**, the tray card that sits behind the disc, with a "
                  "printed strip down each side of the case. It is offered when the project is created "
                  "(the **Case back** row, which starts at *(none)*), and can be added or dropped later "
                  "from **Templates > Add Page...** and **Remove This Page**."},
            {"note": "The disc label and the cover are part of every project and cannot be removed. Only "
                     "the optional pages can, and removing one deletes everything on it -- so it asks "
                     "first, and resets the undo history afterwards."},
            {"h2": "Changing a template later"},
            {"p": "**Templates > Change Template for This Page...** switches the page you are on to a "
                  "different one."},
            {"warn": "This **clears the page**: every layer on it is removed and the undo history is "
                     "reset. It asks first. The other page and the metadata are untouched."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Metadata and cover art",
        "blocks": [
            {"p": "**Metadata...** in the Tools panel holds the album title, artist, year and track "
                  "list. It is "
                  "worth filling in even if you are only designing a label: the track list can be dropped "
                  "onto the artwork as text, and the automatic layout and the disc titling both read from "
                  "here."},
            {"fig": ("metadata", "The Metadata dialog, with cover art fetched and a track list loaded.")},
            {"h2": "Three ways to fill it in"},
            {"ol": [
                "**By hand.** Add Track, type, and reorder with Move Up / Move Down. Times are optional "
                "and written as mm:ss.",
                "**Lookup Track List...** searches the iTunes catalogue for the album and artist you "
                "typed, and fills in the track list, the year and the cover art. If more than one release "
                "matches you are asked which.",
                "**Load from foobar2000** takes everything from whatever is loaded in foobar's current "
                "playlist, then looks up cover art for it.",
            ]},
            {"tip": "**Load from foobar2000 is usually the better source.** Those are the actual files you "
                    "are about to record, with their actual tags, in the actual order - a search can "
                    "return a different edition with a different track order."},
            {"h2": "Cover art"},
            {"p": "A fetched cover is saved in two places: with the project, so it is still there next "
                  "time you open it, and in the per-user gallery, so **Tools > Insert Asset...** can drop "
                  "it onto a page like any other image."},
            {"tip": "**If the cover that comes back is wrong, click it.** The preview is a button: it "
                    "opens a file picker so you can point at the right sleeve yourself. Both automatic "
                    "sources guess, and for a reissue, a compilation or a band with a common name they "
                    "regularly guess wrong - a search has no way of knowing which pressing you are "
                    "holding."},
            {"h2": "When there is nothing good to be found"},
            {"p": "xD-Tools would rather show no cover than the wrong one. A result has to match the "
                  "album title **and** the artist before it is accepted: a title on its own is not "
                  "enough, because a cover version of the title track by somebody else matches that "
                  "perfectly. When nothing clears the bar, the preview stays empty - which is the "
                  "honest answer, and one click away from being put right."},
            {"p": "There is one more place to look first, though. FLAC files often carry the sleeve "
                  "inside them, and most rips of your own CDs do. When a search comes back with "
                  "nothing usable, that picture is used instead. It is certainly the right sleeve for "
                  "that release; it comes second only because it is often a smaller scan than the "
                  "600-pixel artwork a search returns. MP3 files are not read this way."},
            {"h2": "Putting metadata onto the page"},
            {"p": "The metadata button in the Tools panel inserts any single field - album, artist, year - "
                  "or the whole numbered track list, as a text layer. It can also insert the track list "
                  "as **two side-by-side columns**, which is what a long list needs to fit on a J-card "
                  "back panel."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Automatic layout",
        "blocks": [
            {"p": "The **magic wand** in the Tools panel builds both pages from the album's own artwork "
                  "and track list. It is the fastest route from \"I have a disc\" to \"I have something "
                  "to print\"."},
            {"p": "Fill in album and artist in **Metadata...** first - that is what it searches by. "
                  "If there is no cover art yet it looks one up before starting."},
            {"warn": "It **replaces both pages** and resets the undo history, so it asks for confirmation "
                     "first. The metadata itself is left alone."},
            {"h2": "What it builds"},
            {"p": "**The disc label**: the full-face template, the cover art stretched across it and then "
                  "cropped to the cut outline, and the MiniDisc logo on the shutter sticker. "
                  "The insertion-orientation triangle and its label stay on top of the artwork rather "
                  "than being buried under it."},
            {"p": "That mark also **changes colour to suit the cover**: black or white, whichever stays "
                  "readable against the top of that particular sleeve. Left at its default black it was "
                  "still there over a dark full-bleed cover, just invisible, which looks exactly like "
                  "having lost it."},
            {"fig": ("main-jcard", "The J-card, with every colour taken from the cover itself.")},
            {"p": "**The J-card**, in three panels:"},
            {"ul": [
                "**Front** - the cover art, turned a quarter turn so its top edge runs down the left side "
                "of the card, filling the panel, with a small MiniDisc logo in the corner.",
                "**Spine** - a band in an accent colour picked out of the cover, carrying the year, album "
                "and artist turned to read down it.",
                "**Back** - the cover's most common colour, with the numbered track list, split into two "
                "columns once the list gets long, and the running time at the foot.",
            ]},
            {"p": "The front and back are turned in *opposite* directions on purpose: the card wraps "
                  "around the case, so the back ends up the other way up."},
            {"note": "Everything it produces is ordinary layers. Move them, restyle them, delete them - "
                     "it is a first draft, not a finished design."},
            {"h2": "The case back, if there is one"},
            {"p": "A CD project with a case back gets that laid out too: the album and artist run down "
                  "**both** side strips -- which side of a case is visible depends on how it was shelved "
                  "-- with the track list on the panel between them, in the cover's own colours."},
            {"fig": ("cd-back", "The tray card: a printed strip down each side of the case, the track "
                                "list on the panel that sits behind the disc.")},
            {"note": "Unlike the other two pages, this one keeps whatever template you gave it. It only "
                     "exists because you added it and chose its shape, and the layout has no business "
                     "undoing that."},
            {"h2": "Clip Layers and Bake Layers"},
            {"p": "**Clip Layers** trims everything to the printable area: layers entirely outside it are "
                  "removed, images that hang over the edge are cut back to it. The automatic disc layout "
                  "uses this to trim the deliberately oversized cover down to the cut outline."},
            {"p": "**Bake Layers** flattens the whole page into a single image, exactly as the PNG export "
                  "would render it. Useful for locking a finished design; note that a baked layer's "
                  "resolution is fixed for good, which is why it renders at a higher DPI than a normal "
                  "export."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Printing and cutting",
        "blocks": [
            {"h2": "The two exports"},
            {"p": "The design leaves xD-Tools as two files that describe the same object in two ways."},
            {"table": {
                "head": ["Export", "Contains", "For"],
                "rows": [
                    ["**Export Print PNG...**", "Your artwork, at 300 DPI by default, clipped to the "
                                                "template outline - transparent outside it, including the "
                                                "chamfered and rounded-away corners.", "Printing."],
                    ["**Export Cut SVG...**", "Only the cut and fold lines of the current page, in real "
                                              "physical units. No artwork.", "The cutting machine."],
                    ["**Export Print PNG (Grayscale)...**", "The same artwork converted to grey, with a "
                                                            "brightness/contrast dialog and a live "
                                                            "preview first.", "Mono printers."],
                ],
            }},
            {"h2": "The Cricut route"},
            {"ol": [
                "Export the PNG and print it on your sticker or card stock.",
                "Import the SVG into Cricut Design Space.",
                "Use **Print Then Cut**: the machine finds the printed sheet's registration and cuts the "
                "SVG's outline exactly onto it.",
            ]},
            {"p": "The SVG carries real millimetres, so nothing needs scaling by hand at the other end."},
            {"h2": "Orientation, and one label per sheet"},
            {"p": "The Print window has a **Page Size** and an **Orientation**. Landscape is not "
                  "decoration: a CD's folded slim-case insert is 242mm wide, and no portrait sheet takes "
                  "it upright - on a portrait A4 it can only be printed turned a quarter turn."},
            {"p": "**Each label on its own sheet** does what it says, and for a CD project it is switched "
                  "on for you. The reason is arithmetic rather than taste: a CD label (118mm) beside that "
                  "insert (242mm) needs 363mm of a sheet that offers 287mm, so the two cannot share one "
                  "however they are turned. With the option on, the preview shows one sheet at a time - "
                  "the **Showing** box picks which - and printing, Export PDF and Export PNG all walk both. "
                  "A PNG holds one page, so exporting two sheets writes two files, numbered."},
            {"fig": ("cd-print", "A CD project's print layout: the disc label on its own sheet, the "
                                 "folded insert on another.")},
            {"h2": "Printing directly"},
            {"p": "**File > Print...** skips the export step: it lays several copies of both pages onto "
                  "one sheet of A4 or Letter, auto-arranged into a grid you can then drag around by hand. "
                  "Right-clicking a copy turns it 90 degrees, which is often what makes one more fit."},
            {"fig": ("print", "File > Print. The preview is the physical sheet.")},
            {"p": "From here you can send it to a real printer, or save exactly what is shown as a PDF or "
                  "a PNG."},
            {"p": "**Multiprint...**, on the startup screen, does the same thing across *different* "
                  "projects - add artwork from several saved `.mdproj` files onto one sheet, so a stack "
                  "of discs is one print run instead of six."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "The MDRem adapter",
        "blocks": [
            {"p": "MDRem is a Waveshare RP2040-Zero board with an infrared LED on it, running firmware "
                  "that emulates a **Sony RM-D10P** - the keyboard remote Sony sold in the mid-nineties "
                  "for typing titles onto MiniDiscs. It appears on the computer as an ordinary serial "
                  "port."},
            {"h2": "The hardware"},
            {"table": {
                "head": ["Pin", "Role"],
                "rows": [
                    ["GPIO12", "Infrared output, into the transistor's base resistor."],
                    ["GPIO13", "Input, used only by the firmware's `SELFTEST` self-check."],
                    ["GPIO16", "The board's own RGB status LED."],
                ],
            }},
            {"p": "The LED is driven by an NPN transistor as a low-side switch, because tens of "
                  "milliamps cannot be pulled through a GPIO pin directly. Power comes from VBUS, not "
                  "the 3.3 V regulator."},
            {"fig": ("ir-circuit", "The output stage: S9014, Rb = 470 ohm, Rd = 47 ohm (about 72 mA).")},
            {"tip": "**If the range is poor, look at Rd first.** At 100 ohm (about 34 mA) the deck had to "
                    "be within a centimetre or two and aimed precisely; at 47 ohm it works from a "
                    "comfortable 20-30 cm. Do not go below about 33 ohm - 100 mA is the S9014's limit."},
            {"h2": "The status LED"},
            {"table": {
                "head": ["Colour", "Meaning"],
                "rows": [
                    ["White", "Starting up."],
                    ["Green", "Ready; the last command succeeded."],
                    ["Blue", "Transmitting infrared."],
                    ["Red", "The last command failed. Stays lit until something succeeds."],
                    ["Purple", "Hardware initialisation failed - the adapter is not working."],
                ],
            }},
            {"h2": "Turning it on in xD-Tools"},
            {"p": "**Window > Settings...**, tick **Enable MDRem IR remote adapter**, and choose the "
                  "serial port."},
            {"fig": ("settings", "Window > Settings. The foobar2000 address is separate from the adapter.")},
            {"p": "**Detect** asks every serial port on the machine whether an MDRem answers on it. It has "
                  "to work that way: the board reports the USB ID `2E8A:0003`, which is also its own "
                  "bootloader's and other Waveshare boards', so the only reliable identification is the "
                  "device replying to a `PING`."},
            {"p": "Three things appear once the checkbox is ticked: **Upload Tracklist** in the "
                  "Metadata dialog, **Remote...** on the startup screen, and the whole **Recording** "
                  "menu - all three ways of recording a disc, Remote Control... and Erase MiniDisc..."},
            {"note": "The foobar2000 address on the same page is deliberately *not* tied to the checkbox - "
                     "reading a playlist needs foobar2000, not the infrared adapter."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "The software remote",
        "blocks": [
            {"p": "The software remote is a stand-in for the deck's own remote control, laid out the way a "
                  "physical one is. It opens from either **Remote...** on the startup screen or "
                  "**Recording > Remote Control...** - the second exists because reaching for the remote "
                  "should not mean closing the project you are working on."},
            {"fig": ("remote", "The remote window. The status line reports what was sent, not what happened.")},
            {"table": {
                "head": ["Group", "Keys"],
                "rows": [
                    ["Transport", "Previous, Play, Next, scan back, Pause, scan forward, Stop, Power, Eject."],
                    ["Tracks", "1 to 10, selected directly. Higher numbers exist in the firmware but have "
                               "no button here - use >25 on the deck."],
                    ["Play Mode", "Continuous, Shuffle, Program, Repeat, A-B, >25."],
                    ["Display", "Display, Scroll."],
                    ["Titling", "Name, Enter, Delete, Cancel."],
                    ["Recording", "Record, Music Sync, T.Rec, D.Rec, A.Space, M.Scan."],
                ],
            }},
            {"p": "The Recording group is kept well away from the transport keys on purpose: on a real "
                  "remote Record is a deliberate reach, and a mouse makes an accidental press far easier "
                  "than a thumb does."},
            {"warn": "The status line says **Sent**, never **Done**. The deck cannot report back. If "
                     "nothing happens, the most likely causes are aim and distance - see the "
                     "troubleshooting chapter."},
            {"tip": "**Record pressed while the deck is already recording adds a track mark.** That is how "
                    "the automatic recording splits a gapless album, and you can use it by hand the same "
                    "way."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Writing titles onto the disc",
        "blocks": [
            {"p": "**Metadata... > Upload Tracklist** writes the disc title and every track name "
                  "onto the MiniDisc itself. The disc title is assembled as `Artist - Album (Year)`, "
                  "skipping whatever is not filled in."},
            {"fig": ("upload", "Everything is shown before anything is written.")},
            {"h2": "Before it starts"},
            {"p": "The list is exactly what will be written, already converted. Read it: this is the only "
                  "chance to notice a title that came out wrong, because afterwards nothing can tell you "
                  "what actually landed on the disc."},
            {"h2": "It is slow, and that is the deck"},
            {"p": "The deck accepts about three and a half keypresses per second, and every character is "
                  "its own infrared frame. A full album takes three to four minutes. The original Sony "
                  "remote was no faster - contemporary reviews complained about it. The point is that you "
                  "type on a real keyboard and walk away."},
            {"table": {
                "head": ["Job", "Roughly"],
                "rows": [
                    ["One track title, on a disc with old titles to clear", "about 25 s"],
                    ["One track title, on a freshly recorded disc", "about 12 s"],
                    ["A whole album, clearing first", "3 to 4 minutes"],
                ],
            }},
            {"h2": "Erase existing titles first"},
            {"p": "Clearing the old title is the single slowest part of writing a new one and roughly "
                  "doubles the total time. It is on by default because leaving it off over an existing "
                  "title leaves the old text behind, with the new text running into it."},
            {"tip": "**Turn it off on a disc you just recorded.** There is nothing there to erase, and it "
                    "very nearly halves the wait. The recording flow turns it off for you."},
            {"p": "Because the old title cannot be read back, clearing deliberately overshoots: it sends "
                  "more delete presses than the new title could possibly need. Extra deletes on an empty "
                  "field cost nothing."},
            {"h2": "Titles are converted to plain ASCII"},
            {"p": "MiniDisc decks only display characters 0x20 to 0x7E. Accented letters lose their marks "
                  "- `Zazolc gesla jazn` - and anything with no Latin equivalent at all is dropped. The "
                  "dialog lists the dropped characters before writing anything."},
            {"note": "**Japanese titles do not work**, even though MiniDisc is a Japanese format. The "
                     "deck's own katakana is reachable only through its native entry method - the CHAR "
                     "key plus the jog dial - which is a different input path entirely and takes ten "
                     "seconds a character. Transliterate instead."},
            {"h2": "Eject when it finishes"},
            {"warn": "**A deck holds edited titles in volatile memory until the disc is ejected.** Pull "
                     "the power first and everything you just wrote is gone. The dialog offers to eject "
                     "for you when it is done - say yes."},
            {"h2": "Tracks past 25"},
            {"p": "The firmware's key table stops at track 25, so there is no way to select a higher track "
                  "on the deck at all. Those titles are listed as skipped rather than silently dropped."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Recording an album from foobar2000",
        "blocks": [
            {"p": "**Recording > Record to MiniDisc from foobar2000...** does the whole job in one go: it "
                  "arms the deck, plays the album out of foobar2000, watches it to the end, writes the "
                  "titles, and lays out both labels from the album's own artwork."},
            {"note": "**This needs the MDRem adapter, and the menu entry only appears once it is enabled "
                     "in Window > Settings...** The adapter is what puts the deck into record and what "
                     "marks the tracks. Without one, recording means pressing record on the deck yourself "
                     "and letting its own LEVEL-SYNC decide where the tracks begin - xD-Tools has no part "
                     "in that."},
            {"h2": "Setting up"},
            {"ol": [
                "Install the **Beefweb Remote Control** component (`foo_beefweb`) in foobar2000. That is "
                "how xD-Tools reads the playlist and follows what is playing. Its default address, "
                "`http://localhost:8880`, is what xD-Tools expects; change it in Window > Settings... if "
                "you moved it.",
                "Connect the computer's **S/PDIF** output - optical or coaxial - to the deck's digital "
                "input. This carries the audio; the USB link carries only commands.",
                "Set foobar2000's output to **44.1 kHz, 16-bit, stereo** - see below.",
                "Load the album into foobar2000's current playlist, in the order you want it on the disc.",
                "Put a blank or erasable disc in the deck, tab closed, and set the recording mode (SP or "
                "LP2) **on the deck** - xD-Tools cannot read or change it.",
                "Turn **LEVEL-SYNC off** on the deck. See below.",
                "Aim the adapter at the deck's remote sensor and leave it there.",
            ]},
            {"h2": "The format going into the deck"},
            {"p": "A MiniDisc is 44.1 kHz, 16-bit stereo, and the deck's digital input expects to be fed "
                  "that. Hand it a 96 kHz or 24-bit stream - which is what a modern player happily outputs "
                  "if the files are high-resolution and nothing is told to convert them - and the deck may "
                  "simply refuse it, or drop out partway. It cannot tell xD-Tools that it has, either."},
            {"p": "So convert on the computer, where it is free to get right: install foobar2000's "
                  "**Resampler (SoX)** component, add it to the DSP chain and set it to **44100 Hz**, and "
                  "set the output device to **16-bit stereo**. Files already at 44.1/16 pass through "
                  "untouched, so this costs nothing on an ordinary CD rip and saves the awkward case."},
            {"h2": "Analogue instead, if you have to"},
            {"p": "The deck's **analogue** line inputs work too, and xD-Tools drives the recording exactly "
                  "the same way - it presses the deck's keys, which does not depend on how the audio "
                  "arrives. **The quality is considerably worse**, though, and unavoidably so: the sound "
                  "leaves the sound card as analogue and is digitised again by the deck, so it picks up "
                  "two extra conversions and whatever noise the card's output stage adds, before ATRAC has "
                  "even started. Use S/PDIF whenever the deck has it."},
            {"p": "Going analogue also means setting the deck's input selector to analogue and its "
                  "recording level by hand - a digital input has neither to worry about."},
            {"fig": ("record", "The playlist as it will be recorded, in that order.")},
            {"h2": "What the window shows"},
            {"p": "The album, artist and year the disc will be titled with, the cover art it will be "
                  "labelled with, and the track list - all of it editable. **This is the last place to "
                  "correct any of it**: once the recording has run, those titles are already on the "
                  "disc. The cover is looked up as the window opens rather than when the album ends, "
                  "for the same reason. Everything freezes the moment recording starts."},
            {"p": "Fill in the **Artist** column only when the tracks are by different performers. On "
                  "an ordinary album it stays empty; on a compilation it is what tells xD-Tools the "
                  "disc is one."},
            {"h2": "What happens"},
            {"ol": [
                "xD-Tools shows the playlist and its total time, and warns if it will not fit on an "
                "80-minute disc in SP.",
                "It sets foobar to play straight through once - no shuffle, no repeat - so the disc "
                "cannot end up in a different order than the titles, and sets foobar's own volume to "
                "-5 dB to leave the deck some headroom.",
                "It tells the deck to start recording, then **asks you to confirm the deck really is in "
                "record-pause**. It cannot check, and getting this wrong means playing a whole album into "
                "a deck that is not recording and finding out forty minutes later.",
                "It releases the pause, and a moment later starts playback - in that order, so the deck "
                "is already running when the first note arrives.",
                "Recording runs. You can watch which track is going down and how much is left. Stop stops "
                "both ends.",
                "When the album ends it offers to write the titles, taken from the playlist itself.",
                "Finally the album, artist, year and track list become the project's metadata, cover art "
                "is looked up, and **both pages lay themselves out**.",
            ]},
            {"warn": "That last step **replaces whatever was on both pages**. After a recording it does "
                     "not ask - you have just sat through several prompts and watched an album go down in "
                     "real time, and one more would be noise."},
            {"h2": "Track marks: the important part"},
            {"p": "A CD player tells the deck where the tracks are, in the S/PDIF subcode. **A computer "
                  "does not.** Left to itself the deck falls back on LEVEL-SYNC: it starts a new track "
                  "whenever the sound drops to silence and comes back."},
            {"p": "That fails on any album where one song runs into the next. Two songs with no gap "
                  "between them are recorded as one long track, and no amount of editing afterwards makes "
                  "that pleasant."},
            {"p": "So xD-Tools sends a track mark itself, at the exact moment foobar changes track - that "
                  "is the **Mark tracks through the adapter** checkbox, and it should stay ticked."},
            {"warn": "**Turn LEVEL-SYNC off on the deck when you use it.** Running both marks the same "
                     "boundary twice, a fraction of a second apart, and leaves a sliver of a track "
                     "stranded between them. They fight; they do not co-operate."},
            {"h2": "Recording mode and length"},
            {"p": "An MD holds 80 minutes in SP. xD-Tools warns when the playlist is longer than that, but "
                  "it can only warn - LP2 and LP4 have to be set on the deck itself, and there is no way "
                  "to read back which mode it is in."},
            {"h2": "An album that takes more than one disc"},
            {"p": "A double album does not fit on a MiniDisc, and a MiniDisc cannot be turned over the "
                  "way a cassette can. **Record across several discs** records it a disc at a time "
                  "instead: one disc, its titles, eject, the next blank, and so on."},
            {"p": "Tick it and the track list gains a **Disc** column showing where the album is cut, "
                  "with a line underneath saying how full each disc ends up. **One disc holds** is the "
                  "number that decides it - 80 minutes in SP, 160 in LP2. xD-Tools cannot read which "
                  "mode the deck is in, so that number is yours to state."},
            {"ol": [
                "Each disc is recorded exactly as a single one is: armed, confirmed, played, marked.",
                "**Two seconds after the last track of that disc, the titles go out by themselves** - "
                "no question, no button. Nobody sits through forty minutes of album, and a MiniDisc "
                "keeps an edited title list in memory only until the disc is ejected.",
                "The disc is ejected, and xD-Tools asks you to put the next blank one in.",
                "The last disc finishes the same way and the run ends.",
            ]},
            {"note": "Each disc is titled with the album's name and **[1/2]**, **[2/2]** after it. Two "
                     "discs of one album titled identically are two discs nobody can tell apart on a "
                     "shelf. The tracks on each are numbered from one, which is how the deck numbers "
                     "them anyway."},
            {"warn": "The preview that Upload Tracklist normally shows is given up here - there is "
                     "nobody at the machine to read it. That is why every title, and every character "
                     "the deck cannot show, is on screen in this window **before** the first note "
                     "plays."},
            {"h2": "Where the album is cut, and in what order"},
            {"p": "xD-Tools puts the playlist into the album's own order as the window opens: by disc "
                  "number first, then by track number, both read from the files themselves. A "
                  "two-disc set dropped into foobar2000 as one folder arrives interleaved, because both "
                  "discs number their tracks from one - this is what puts it right, and foobar2000's own "
                  "playlist is reordered to match, since that is what actually gets played."},
            {"p": "If the files say how many discs there are, the splits are placed where they say and "
                  "the option is ticked for you. Otherwise the album is divided as evenly as its running "
                  "order allows, into the fewest discs that fit."},
            {"ul": [
                "**Move Up** / **Move Down** change the order the album is recorded in.",
                "**Start Disc Here** makes the selected track the first of a new disc; pressed again on "
                "the same track, it takes that split away.",
                "**Split Automatically** throws away the splits you placed and works them out again.",
            ]},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Recording a CD",
        "blocks": [
            {"p": "**Recording > Record CD to MiniDisc...** copies an audio CD onto a MiniDisc. It reads "
                  "the disc, works out what album it is, extracts every track to a file, loads those "
                  "files into foobar2000 in the right order, and then hands over to the recording you "
                  "already know - the same arming, the same track marks, the same titling."},
            {"note": "**This needs the MDRem adapter too**, and the menu entry only appears once it is "
                     "enabled. Reading a CD does not need it, but this entry does not stop at reading "
                     "one: it goes straight on to record what it read."},
            {"h2": "Why it copies the disc first"},
            {"p": "foobar2000 can play a CD directly, and letting it do so would be simpler. But then "
                  "the disc is being read in real time, during the recording, with nothing to fall back "
                  "on - a drive stumbling over a scratch at minute 31 puts that stumble on the "
                  "MiniDisc, and a MiniDisc recording is not something you can patch afterwards."},
            {"p": "Copying first moves every read error to a point where it costs a re-read and nothing "
                  "else. xD-Tools uses **cdparanoia** for this, built precisely to keep working at a "
                  "damaged disc until it gets the audio right, and **flac** to store the result. Both "
                  "ship with xD-Tools; there is nothing to install."},
            {"fig": ("cd-rip", "The disc read, identified, and ready to copy.")},
            {"h2": "Step by step"},
            {"ol": [
                "Put the CD in the drive and choose the drive from the list. **Refresh** looks again if "
                "you plugged one in after opening the window.",
                "Press **Read Disc**. xD-Tools reads the table of contents and looks the disc up on "
                "MusicBrainz, which identifies it from the lengths of its tracks - a CD carries no text "
                "of its own.",
                "Check what came back. If several pressings match, pick the right one from "
                "**Release**; the track titles and the cover art change with it.",
                "Correct anything wrong. The titles are editable, and they are what gets written into "
                "the files and later onto the MiniDisc.",
                "Press **Rip and Record**. When the copy finishes, the recording window opens by "
                "itself.",
            ]},
            {"note": "A disc that is not in MusicBrainz - anything home-burned, and plenty of obscure "
                     "releases - simply comes back with numbered placeholder titles for you to type "
                     "over. Nothing else about the process changes."},
            {"h2": "How long it takes"},
            {"p": "Expect roughly **fifteen minutes for a full album**, about three times faster than "
                  "playing it. That is cdparanoia being careful, and it is the price of the error "
                  "correction that made copying worth doing in the first place. The recording itself "
                  "then takes as long as the album does, because it happens in real time."},
            {"h2": "When the disc is a compilation"},
            {"p": "A mixtape is not an album, and treating it like one goes wrong in visible ways: the "
                  "disc gets named after whichever track happened to be first, the J-card credits one "
                  "performer for twelve, and a cover art search returns some unrelated record's "
                  "sleeve."},
            {"p": "So xD-Tools checks. If most of the tracks cannot be attributed to a single artist, it "
                  "credits the disc to **Various Artists**, names it `Mixtape` unless the release has a "
                  "name of its own, prints each performer beside their track on the J-card, and "
                  "**draws a cover from the track list** instead of looking one up."},
            {"p": "Fill in the **Artist** column yourself when you know a disc is a compilation and "
                  "MusicBrainz did not say so - that column is what the check reads."},
            {"note": "An album with a guest feature on one track is **not** a compilation, and is not "
                     "treated as one. The test is whether most tracks belong to the same artist, not "
                     "whether the credits vary at all."},
            {"p": "The same applies when recording from foobar2000: a playlist of unrelated tracks is "
                  "recognised the same way, with the same result."},
            {"h2": "Where the copied files go"},
            {"p": "Into your temporary folder by default, under `xD-Tools CD Rip`, one folder per album. "
                  "It is created if it is not there, so a folder you have only typed into Settings and "
                  "never made is not a problem. "
                  "They are raw material for a recording rather than a music collection - one album is "
                  "a few hundred megabytes - and Window > Settings... can point that somewhere else."},
            {"p": "They are **not** deleted when the recording finishes, because foobar2000 still has "
                  "them in its playlist and you may want to play them again. The previous copy is "
                  "cleared out when you start the next one."},
            {"warn": "Loading the copied tracks into foobar2000 **empties its current playlist**. "
                     "Anything you had queued up there is gone, so move it elsewhere first if you want "
                     "to keep it."},
            {"h2": "A set of several CDs"},
            {"p": "**Rip several discs as one album** copies a boxed set as one album rather than as "
                  "two unrelated ones. Each disc is read, identified and ripped on its own, and xD-Tools "
                  "then asks for the next."},
            {"ul": [
                "They all land in **one folder**, the one the first disc made. A later disc is often "
                "identified under a title of its own - \"... [Disc 2]\" - and a folder per disc would "
                "be two albums.",
                "The album, artist and year stay the ones from the first disc. The **titles** are each "
                "disc's own, which is what the lookup is for.",
                "Every file is tagged with the disc it came from, and carries that number in its name. "
                "That is what lets everything afterwards - the playlist, a recording, a burn - put the "
                "set back in its own order.",
                "When you stop adding discs, foobar2000's playlist holds the whole set, and the "
                "recording that follows records all of it.",
            ]},
            {"note": "You can stop after any disc: the question offers to carry on or to record what has "
                     "been ripped so far."},
        ],
    },
    {
        "title": "Burning an audio CD",
        "blocks": [
            {"p": "Recording > **Burn Audio CD from Folder...** or **from foobar2000...** writes a real "
                  "Red Book audio CD-R - the kind any CD player will play - from files you already have. "
                  "No infrared adapter is involved: this is the drive's job, so these two entries stay "
                  "available even with MDRem switched off."},
            {"fig": ("burn", "The burn window: what will be written, and what it will be called.")},
            {"h2": "What the window shows"},
            {"p": "The album's name, artist and year, an editable title and artist per track, and a cover "
                  "you can click to replace - the same window the recording flow uses, and the same rule: "
                  "**what is on screen when you press Burn is what gets written**, both onto the disc as "
                  "CD-Text and into the project you design the label from."},
            {"p": "The line under the track list gives the album's length against what the disc holds. "
                  "The **Status** column is the part worth reading before you press anything."},
            {"h2": "Why a track can refuse to be burned"},
            {"p": "A CD holds 44.1 kHz, 16-bit, stereo audio and nothing else. Two Red Book rules can stop "
                  "a burn outright, and the window says so per track rather than letting you find out on "
                  "playback:"},
            {"ul": [
                "a track shorter than **four seconds**, which some players will not play;",
                "more than **99 tracks**, or an album longer than the disc.",
            ]},
            {"note": "A file that is merely at the wrong rate is not a refusal. A 48 kHz / 24-bit download "
                     "- which is what most of them are - says \"will be converted to 44100 Hz / 16-bit\" and "
                     "is resampled on the way to the disc by the bundled SoX. The conversion happens in a "
                     "scratch folder; your own files are never touched."},
            {"h2": "Titles on the disc: CD-Text"},
            {"p": "The album and track names are written onto the CD as CD-Text, which players that "
                  "support it will show. It carries plain ASCII, so accented letters lose their marks the "
                  "same way MiniDisc titles do - and anything with no equivalent at all is listed in the "
                  "window **before** you burn, rather than quietly dropped."},
            {"h2": "Simulate first, if you like"},
            {"p": "**Simulate only** runs the whole sequence with the laser off. It takes as long as a real "
                  "burn and proves the drive, the speed and the files, without spending a disc. Worth doing "
                  "once on a new drive."},
            {"warn": "A CD-R cannot be rewritten. Once writing starts, the disc is either finished or "
                     "wasted - which is why the window asks before starting, and asks again if you press "
                     "Stop while the laser is on. Stopping during the earlier \"Preparing audio\" stage "
                     "costs nothing at all."},
            {"h2": "The label, afterwards"},
            {"p": "When the burn finishes, the album's details are offered to the open project if it is a "
                  "CD one. Say yes and the Tools panel's automatic layout has everything it needs: the "
                  "cover, the artist, the year and the track list."},
            {"fig": ("cd-label", "The disc label: the cover lightened across the ring, with the hub cut "
                                 "out and the Digital Audio mark at the foot.")},
            {"fig": ("cd-insert", "The folded slim-case insert: cover on the right panel, track list on "
                                  "the left. Folded down the middle, the left half shows through the back "
                                  "of the case.")},
            {"h2": "What you need"},
            {"ul": [
                "A CD writer. It is found by asking cdrecord, not by guessing - if the **Burner** box is "
                "empty, check the drive is connected and press **Refresh**.",
                "A blank CD-R. A disc that already holds something cannot take a fresh burn.",
                "Nothing else: cdrecord and SoX are bundled on Windows.",
            ]},
            {"h2": "An album that takes more than one disc"},
            {"p": "**Burn across several discs** writes a long album onto as many CD-Rs as it needs. "
                  "**One disc holds** is what that depends on: 80 minutes on an ordinary blank, 74 on an "
                  "older one."},
            {"p": "The track list gains a **Disc** column showing where the album is cut, and the "
                  "summary gives each disc's own length. Every disc is measured against the disc it goes "
                  "on - the album overrunning is the point - so the Burn button stays off until each of "
                  "them fits."},
            {"ol": [
                "Each disc is written and then ejected, whatever **Eject when finished** says: the tray "
                "has to open for the next blank to go in.",
                "xD-Tools asks you to put that blank in, and writes the next disc.",
                "You can stop at any of those questions; the discs already written are finished.",
            ]},
            {"note": "Each disc's CD-Text carries the album's name with **[1/2]**, **[2/2]** after it, "
                     "for the same reason MiniDisc titles do."},
            {"p": "Where the cut falls comes from the files when they say - a ripped boxed set carries "
                  "its disc numbers, and those are honoured rather than balanced over. The same four "
                  "buttons as the recording window are here too: **Move Up**, **Move Down**, **Start "
                  "Disc Here** and **Split Automatically**."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Recording a folder of files",
        "blocks": [
            {"p": "**Recording > Record Folder to MiniDisc...** records an album you already have on "
                  "disk. Point it at the folder it is in, and xD-Tools loads those files into foobar2000 "
                  "in the right order and hands over to the recording you already know - the same "
                  "arming, the same track marks, the same titling."},
            {"note": "**This needs the MDRem adapter too**, and the entry only appears once it is "
                     "enabled. Loading a folder does not need one; going on to record what was loaded "
                     "does."},
            {"fig": ("folder-record", "The folder read, and what foobar2000 made of its tags.")},
            {"h2": "Step by step"},
            {"ol": [
                "Press **Browse...** and choose the folder the album is in. It is loaded into "
                "foobar2000 straight away - choosing it is the decision, so there is nothing further "
                "to confirm. FLAC, MP3 and everything else foobar2000 plays are recognised; anything "
                "that is not audio - artwork, a cue sheet, a log - is ignored.",
                "Check the order. It comes from the filenames, compared so that `10` follows `9` "
                "rather than `1`. If it is wrong, the filenames are what to fix.",
                "Check the album and artist. They are guessed from the folder's own name to start "
                "with, and whatever the files are tagged with replaces that guess as soon as the "
                "tracks are loaded. Type over either if both are wrong.",
                "Look at what came back: the titles foobar read out of the files, and the cover "
                "art - searched for first, and taken from inside the FLAC files themselves if the "
                "search found nothing good.",
                "Press **Record**. It only becomes available once foobar has actually taken the "
                "tracks.",
            ]},
            {"h2": "Where the titles come from"},
            {"p": "From the files - read by foobar2000 rather than by xD-Tools, which is the better tag "
                  "reader of the two and has to read them anyway in order to play them. A file with no "
                  "title tag is recorded under its filename: the honest answer, and usually a usable "
                  "one."},
            {"p": "The album and artist shown in this window are what gets written onto the disc and "
                  "onto the label, so a correction is worth making before you press the button. "
                  "Nothing is ever written back into your files."},
            {"h2": "A subfolder per disc"},
            {"p": "A folder with tracks in it *is* the album, and its subfolders are left alone - a "
                  "scans or bonus directory does not join the running order. Only when the folder "
                  "itself holds no audio at all does xD-Tools look inside, which is what makes a "
                  "two-disc album kept as `CD1` and `CD2` come out in disc order."},
            {"warn": "Loading a folder **empties foobar2000's current playlist**, exactly as recording "
                     "a CD does. Move anything you had queued up there elsewhere first."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Recording a cassette",
        "blocks": [
            {"p": "**Recording > Record to Cassette from foobar2000...** records an album onto a "
                  "compact cassette, one side at a time. It is the odd one out among the recording "
                  "flows, and in a way that decides everything about it: **the deck is yours to "
                  "operate**. There is no adapter for a tape deck and no cable that presses its "
                  "buttons, so xD-Tools plays the right tracks at the right moment and tells you, in "
                  "as many words, what to press and when."},
            {"note": "This needs **no MDRem adapter** - only foobar2000. The entry appears whenever the "
                     "open project is a cassette one, whether or not the adapter is switched on."},
            {"fig": ("tape-record", "The split, the tape it was worked out for, and the instruction "
                                    "waiting to be acted on.")},
            {"h2": "Choosing the tape"},
            {"p": "A stated length is both sides together: a C60 is thirty minutes a side, not sixty. "
                  "Pick the cassette you actually have from the **Cassette** box and the album is split "
                  "again as you do - the Side column in the track list, and the summary underneath it, "
                  "both follow immediately."},
            {"p": "The shortest tape the album fits is pre-selected when the window opens. That is a "
                  "suggestion about the album, not about your shelf: change it to whatever is in the "
                  "box."},
            {"h2": "Where the tape is turned over"},
            {"p": "xD-Tools never rearranges the running order. The only choice is which track the "
                  "break falls after, and every possible break is tried: the one that leaves the two "
                  "sides closest in length wins, among those that fit. Filling side A to the brim and "
                  "leaving side B half empty saves no tape at all - the cassette is the same length "
                  "either way - so there is nothing to be gained by it."},
            {"p": "If nothing fits, the least-overrunning break is used anyway and the window says by "
                  "how much. Running a few seconds into the run-out is your call to make, exactly as "
                  "an album longer than a MiniDisc's eighty minutes is."},
            {"warn": "Tracks with no running time cannot be weighed, so the album is split down the "
                     "middle by count and the window says so. Check that against the tape before you "
                     "start."},
            {"h2": "The ten seconds of silence"},
            {"p": "Every side of a cassette begins with leader tape - a few inches of plain plastic "
                  "spliced on to take the wear of being wound around the hub. It is not magnetic, so "
                  "nothing recorded onto it survives. xD-Tools therefore records **ten seconds of "
                  "silence** at the start of each side before the music begins, and those ten seconds "
                  "come out of what that side holds."},
            {"h2": "Step by step, per side"},
            {"ol": [
                "Check the album, the artist, the year and the cover - they are what the labels will "
                "be printed from, and they freeze the moment recording starts.",
                "Put the cassette in, wound to the start of the side, and put the deck into record. "
                "Set its input to whatever foobar2000 is feeding it, and set its level.",
                "Press the button. That click is the only confirmation there is that the deck is "
                "really rolling - nothing here can see it.",
                "Ten seconds of silence run down while the leader passes.",
                "The side plays. foobar2000 is told to stop when the side's last track ends, rather "
                "than being caught afterwards - which is what keeps the first second of the next "
                "track off the end of the side.",
                "Stop the deck, take the cassette out and turn it over, put it back into record, and "
                "press the button again for side B.",
            ]},
            {"tip": "**Stop** stops foobar2000 and says so - it cannot stop the deck, which will "
                    "happily go on recording silence. That is the one thing only you can do."},
            {"h2": "The audio path"},
            {"p": "Out of the computer and into the deck's line inputs, as an ordinary analogue "
                  "recording. Nothing in this window depends on how it gets there: the deck's input "
                  "selector, its recording level and its noise reduction are all yours to set, and "
                  "xD-Tools neither knows nor asks about any of them."},
            {"p": "Set the level with the loudest passage of the album, not the first ten seconds of "
                  "it. Tape distorts gradually rather than abruptly, so a little too hot is a warmer "
                  "recording and a lot too hot is a muddy one."},
            {"h2": "Afterwards"},
            {"p": "When both sides are done the album is adopted by the open project and its three "
                  "pages are laid out - the inlay card and a label for each side, split exactly where "
                  "the recording was. The tape you chose is saved with the project, so the labels and "
                  "the recording can never disagree about where side B starts."},
            {"fig": ("tape-jcard", "The inlay card: cover, spine, and the track list on the tuck-in "
                                   "flap under a heading per side.")},
            {"p": "The **shell labels** are the other two pages, and they are cut with a round hole "
                  "for each reel hub - the deck's spindles come up through them, so a label without "
                  "them would be stuck over the drive. The sleeve goes across the whole sticker, "
                  "washed out so the text over it stays readable, and the holes are punched through "
                  "it. The side letter sits between them; that side's tracks run along the bottom, "
                  "numbered from one so they agree with the deck's own counter."},
            {"fig": ("tape-label", "A shell label: the sleeve, the holes the reels turn in, and this "
                                   "side's tracks.")},
            {"p": "In **File > Print...** the two shell labels share one sheet - they are the same "
                  "sticker printed twice, cut at the same time and stuck on opposite faces of one "
                  "tape - and the inlay card, four times the size, takes the next sheet."},
            {"fig": ("tape-print", "Both stickers on one sheet, with the inlay on the sheet after it.")},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Erasing a disc",
        "blocks": [
            {"p": "**Recording > Erase MiniDisc...** clears the disc in the deck. It works on whatever is "
                  "physically loaded, so it does not care which project is open, or whether one is."},
            {"warn": "There is no undo, and xD-Tools cannot see the result. Make sure the disc in the "
                     "deck is the one you mean, and that its write-protect tab is closed."},
            {"h2": "Why it asks what you can see"},
            {"p": "This is the one operation where xD-Tools does not know what its own command does. The "
                  "**Erase** key is recognised by the deck as a write command - that much was confirmed "
                  "- but which editing menu it opens was never established, because the write keys "
                  "could only be tested safely on a protected disc, where the deck answers every one of "
                  "them with the same complaint."},
            {"p": "Rather than guess with your recording, xD-Tools sends Erase and then asks what the "
                  "deck's display says. If it is showing something like **All Erase?**, press **Send "
                  "Enter** and watch the display - the window stays open, so you can press it again. "
                  "Some decks want it more than once, and there is no way for xD-Tools to find that "
                  "out: the deck never answers back. Press **Done** when the disc is blank, or "
                  "**Nothing Happened** to back the deck out of whatever menu it is sitting in."},
            {"fig": ("erase", "It sends the command, then asks what the deck is showing.")},
            {"note": "As with titling, an erase lives in the deck's memory until the disc is ejected. "
                     "xD-Tools offers to eject afterwards - take it, or the disc keeps its old contents "
                     "should the deck lose power."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Experimental: downloading from a Telegram bot",
        "blocks": [
            {"warn": "Everything in this chapter is **experimental** and hidden until you ask for it. It "
                     "works, but it is newer and less exercised than the rest of the program, and the way "
                     "it is presented may still change."},
            {"p": "xD-Tools can hold a conversation with a Telegram bot **you run yourself**, download the "
                  "files it sends, and hand the result to Record Folder to MiniDisc - so a download becomes "
                  "a recorded, titled disc without leaving the program."},
            {"warn": "This is for a bot you control. Downloading albums from a public bot that "
                     "redistributes music without the rights holder's permission is not what this is for, "
                     "and owning the CD does not make it legal - that covers copying your own disc, not "
                     "taking a copy from a stranger."},
            {"h2": "Turning it on"},
            {"p": "**Window > Settings** has a **Show experimental features** checkbox. Tick it and an "
                  "**Experimental** menu appears in the menu bar; untick it and the menu disappears again. "
                  "Nothing behind it runs while it is off."},
            {"fig": ("experimental-settings", "Experimental > Experimental Settings. Experimental features "
                                             "keep their own settings window."),},
            {"p": "**Experimental > Experimental Settings...** is where the bot lives. Two fields matter:"},
            {"ul": [
                "**Bot username** - the bot you want to talk to, `@something`.",
                "**Download folder** - where files land. It defaults to a folder under your system "
                "temporary directory, on the grounds that a download is raw material for a recording "
                "rather than a music library. Point it anywhere you like.",
            ]},
            {"note": "There is no API ID or API Hash to fill in. xD-Tools carries its own, so signing in is "
                     "the only step. If a build ever ships without them it says so plainly instead of "
                     "failing to connect."},
            {"h2": "Signing in"},
            {"p": "xD-Tools signs in as **your own Telegram account**, not as a bot. That is not a design "
                  "preference: Telegram's Bot API forbids one bot from messaging another, so the only way "
                  "to talk to your bot the way a person would is to be a person."},
            {"fig": ("telegram-login", "Sign in to Telegram. Phone number, then the code Telegram sends "
                                       "you, then a password if you use two-step verification."),},
            {"p": "**Sign in to Telegram...** asks for your phone number, then the code Telegram sends to "
                  "your other devices, then - if you have two-step verification on - your password. It is "
                  "the same sequence the Telegram app itself uses."},
            {"warn": "The sign-in is saved locally, in `telegram.session` next to xD-Tools' own settings. "
                     "That file is equivalent to being logged in to your account: it is not encrypted, and "
                     "it is not something to copy onto another machine or send to anyone."},
            {"h2": "The conversation"},
            {"p": "**Experimental > Download Album from Telegram Bot...** opens a plain chat. It appears "
                  "only once a sign-in has been saved."},
            {"fig": ("telegram-chat", "The chat, with the download queue on the right."),},
            {"p": "Deliberately a plain chat rather than a search box: your bot's commands are yours, and "
                  "xD-Tools cannot know them. So it shows whatever the bot sends and lets you drive it - "
                  "text, its inline buttons, and any file it attaches. **Quick commands** sends `/start` or "
                  "`/help` with one click, since almost every bot understands those."},
            {"p": "Two conveniences worth knowing. Whatever the bot writes is **translated underneath the "
                  "original**, into whichever language xD-Tools is set to - the original stays, because a "
                  "translation can be wrong and an exact command or filename is better read as sent. And a "
                  "bot that edits its own message to build a menu, rather than sending a new one each time, "
                  "is followed correctly: the message changes in place, as it does on your phone."},
            {"h2": "The download queue"},
            {"p": "Files never appear in the conversation - they go to the **queue on the right**, which is "
                  "the only place a file's name, size, progress and speed are shown. A whole album arriving "
                  "as twenty attachments would otherwise bury the conversation under twenty near-identical "
                  "rows."},
            {"p": "Downloading starts by itself, and at most three files download at once. A failed one "
                  "gets a **Retry** button rather than disappearing."},
            {"h2": "From download to disc"},
            {"p": "Files from every session pile up in the one download folder, so several albums end up "
                  "side by side. **Sort into Album Folders** separates them: one subfolder per album, named "
                  "from the tags, with anything untagged grouped by when it arrived."},
            {"note": "Sorting only ever moves audio files. A cover image the bot sent alongside the tracks, "
                     "or anything else already in that folder, is left exactly where it is."},
            {"p": "**Record Downloaded Albums...** then goes to the recording flow. It sorts first, so you "
                  "cannot accidentally record two albums onto one disc, and asks which album if there is "
                  "more than one. From there it is the ordinary Record Folder to MiniDisc window described "
                  "two chapters ago - which is also why this needs the MDRem adapter, even though "
                  "downloading does not."},
            {"p": "**Open Download Folder** opens it in your file manager, for a look before recording."},
            {"p": "Both operations are also on the menu without opening the chat at all, for files "
                  "downloaded earlier: **Sort Telegram Downloads into Album Folders...** and **Record from "
                  "Telegram Downloads...**"},
            {"tip": "Both buttons go quiet while anything is still downloading - sorting or recording "
                    "half-written files would be worse than waiting."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Troubleshooting",
        "blocks": [
            {"h2": "The deck ignores everything"},
            {"ol": [
                "**Check the adapter is alive.** Its status LED should be green. Purple means the "
                "firmware could not start the hardware at all.",
                "**Check it is transmitting.** Point the adapter's LED at a phone camera - infrared shows "
                "up as a violet-white dot. The firmware's `BEAM` command lights it steadily for two "
                "seconds, which is long enough to see; a single command is 45 ms and invisible.",
                "**Check the aim and the distance.** The working range is roughly 20-30 cm, straight at "
                "the deck's remote sensor. If you need to be closer than that, the LED current is too "
                "low - see the Rd note in the MDRem chapter.",
                "**Check the port.** Window > Settings... > Detect. If nothing answers, the adapter is "
                "not enumerating - try a different cable.",
            ]},
            {"h2": "\"Not connected\" in the remote window"},
            {"p": "Something else already has the serial port open. Only one program can hold it at a "
                  "time - close the other xD-Tools window, dialog, or terminal that is using it."},
            {"h2": "The new title has the old one stuck on the end"},
            {"p": "**Erase existing titles first** was unticked, or the old title was longer than the "
                  "clearing allowed for. Run the upload again with it ticked."},
            {"h2": "Two songs ended up as one track"},
            {"p": "They run into each other with no silence between them, and LEVEL-SYNC had nothing to "
                  "hear. Record again with **Mark tracks through the adapter** ticked and LEVEL-SYNC off "
                  "on the deck."},
            {"h2": "Every track got the same title"},
            {"p": "This was a real bug and is fixed, but the underlying deck behaviour is worth knowing: "
                  "the deck is a state machine with no way to ask it anything, and a track number sent "
                  "while it is paused does not take. That is why the titling sequence sends **Stop** "
                  "first - it puts the deck in a known state instead of assuming one."},
            {"h2": "Nothing was saved to the disc"},
            {"p": "Titles live in the deck's memory until the disc is ejected. Eject it."},
            {"h2": "foobar2000 cannot be reached"},
            {"ul": [
                "foobar2000 is running.",
                "The **Beefweb Remote Control** component is installed *and enabled*.",
                "The address in Window > Settings... matches Beefweb's port.",
            ]},
            {"h2": "The printed label is the wrong size"},
            {"p": "Check the printer is not scaling to fit - it must print at 100%. If the canvas itself "
                  "looks the wrong physical size on screen, that is **Screen DPI** in Window > "
                  "Settings..., which affects the display only, not the export."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "Appendix: the MDRem command set",
        "blocks": [
            {"p": "The adapter speaks plain text over its virtual serial port at 115200 baud. Every "
                  "command answers with a single line - `OK`, `PONG`, or `ERR <reason>` - so a program can "
                  "parse the reply without knowing the command. Lines beginning with `;` are diagnostics."},
            {"p": "xD-Tools drives all of this for you. It is documented here for anyone wanting to talk to "
                  "the adapter directly, from a terminal or their own script."},
            {"table": {
                "head": ["Command", "Does"],
                "rows": [
                    ["`PING`", "Answers `PONG`. This is how the adapter is identified."],
                    ["`HELP`", "Lists the commands."],
                    ["`KEY <name>`", "Reports a key's code and bit count. Sends nothing."],
                    ["`SEND <name>`", "Sends a named key, or a single character."],
                    ["`RAW <hex> [bits]`", "Sends an arbitrary code. `bits` defaults to 20."],
                    ["`DUMP <hex> [bits]`", "Prints the mark/space timings. Sends nothing."],
                    ["`TITLEDISC <text>`", "Writes the disc title."],
                    ["`TITLETRACK <n> <text>`", "Writes track n's title."],
                    ["`TIMING ...`", "Adjusts the timings - including `TIMING COUNT`, the number of "
                                     "delete presses used to clear a title."],
                    ["`SELFTEST`", "Checks the carrier. Needs a jumper from GPIO12 to GPIO13."],
                    ["`GPIOTEST`", "Continuity test for that jumper alone."],
                    ["`BEAM [ms]`", "Steady carrier, 2000 ms by default - visible in a phone camera."],
                    ["`BLINK [cycles]`", "The same, blinking, which is easier to spot."],
                ],
            }},
            {"note": "`SEND A` and `SEND a` are **different codes**. Single characters are "
                     "case-sensitive on purpose; key names are not."},
            {"h2": "How the protocol works"},
            {"p": "Sony SIRC: a 40 kHz carrier at roughly one-third duty, bits sent least-significant "
                  "first, a 2400 microsecond start mark, and frames repeating every 45 ms. A '1' is a "
                  "1200 microsecond mark, a '0' is 600. Like a real remote, each keypress is sent three "
                  "times."},
            {"p": "The character codes are 20-bit, `0x61D00` with the ASCII value in the low byte - the "
                  "RM-D10P's own keyboard protocol. The deck's own function keys (Play, Stop, Record, "
                  "Enter) are **12-bit** codes from a different block. Sending those as 20-bit produces a "
                  "completely different frame and the deck ignores it."},
            {"h2": "Things that were tried and do not work"},
            {"ul": [
                "**Katakana.** The obvious theory - that the character codes are `0x61D00` plus a JIS "
                "X 0201 byte, which would put half-width katakana in the unused upper half - was tested "
                "against a real deck and refuted. A control 'A' appeared; none of the katakana codes did "
                "anything.",
                "**Delete outside name-edit mode.** On a paused track it does nothing at all. Titles can "
                "only be cleared after Name.",
                "**Holding a key down to clear faster.** The deck's auto-repeat clears four characters in "
                "1.09 s - 272 ms each - against 285 ms for individual presses. About three and a half "
                "edit operations per second is a hard ceiling.",
            ]},
        ],
    },
]
