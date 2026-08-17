"""English text of the user manual. See build_manual.py for the block
vocabulary ("p", "ul", "ol", "table", "fig", "note", "warn", "tip", "h2").

Inline marks: **bold**, `literal`.
"""

TITLE = "MDTools"
SUBTITLE = "MiniDisc Studio - User Manual"
TITLE_NOTE = "Designing labels, recording discs, and titling them - with the MDRem infrared adapter"
COVER_CAPTION = "What talks to what: commands over USB, keys over infrared, audio over S/PDIF."
VERSION_LINE = "Version 0.1.0"
AUTHOR_LINE = 'Artur "Screemer" Jakubowicz'
DATE_LINE = "August 2026"
TOC_TITLE = "Contents"
FOOTER_LEFT = "MDTools - MiniDisc Studio - User Manual"

BOOK = [
    # ------------------------------------------------------------------
    {
        "title": "What this is",
        "blocks": [
            {"p": "MDTools is a desktop workbench for MiniDisc. It started as a label designer and grew "
                  "into four tools that share one project file:"},
            {"ul": [
                "**Design** the sticker that goes on the disc and the J-card insert that goes in the case, "
                "and export them ready to print and cut.",
                "**Record** a whole album from foobar2000 onto a MiniDisc, with a proper track mark at "
                "every song.",
                "**Title** the disc: write the album name and every track name onto the MiniDisc itself, "
                "so the deck's own display shows them.",
                "**Drive the deck** from a software remote - transport, track numbers, play modes.",
            ]},
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
                    ["Designing and printing", "MDTools, a printer, and - for cutting - a Cricut machine "
                                               "or a steady hand with scissors."],
                    ["Titling a disc", "An MDRem adapter on a USB port, and a Sony MiniDisc deck it can be "
                                       "aimed at."],
                    ["Recording an album", "The above, plus foobar2000 with the Beefweb component, and a "
                                           "digital (S/PDIF) cable from the computer to the deck."],
                ],
            }},
            {"note": "Everything in this manual was worked out against a **Sony MDS-JE480**. Other Sony "
                     "decks that accept the RM-D10P keyboard protocol should behave the same way, but the "
                     "timings in particular were measured on that one."},
            {"h2": "One thing to understand up front"},
            {"p": "The deck cannot answer. Infrared only travels one way, and this model's Control A1 bus "
                  "is not connected inside. So MDTools can send a command, but it can never find out "
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
            {"p": "If you have the packaged build, run `MDTools.exe`. From source:"},
            {"ul": [
                "`python -m venv .venv`",
                "`.venv\\Scripts\\pip install -e \".[dev]\"`",
                "`.venv\\Scripts\\python -m mdtools.main`",
            ]},
            {"h2": "Choosing a language"},
            {"p": "**Help > Language** offers English, Polski and Japanese. The change needs a restart, "
                  "and the dialog offers to do it for you."},
            {"h2": "The startup screen"},
            {"p": "MDTools opens on a short list of what you might want to do: reopen one of the last few "
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
            {"p": "To leave MDTools altogether, use **File > Exit**, or cancel the startup screen when it "
                  "reappears."},
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
                  "metadata. Below the separator are the four page-wide operations - Clip Layers, Bake "
                  "Layers, Save as Template and Auto-Layout. Every button is icon-only; hover for its "
                  "name."},
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
                  "and where it folds. MDTools ships with six."},
            {"table": {
                "head": ["Template", "What it is"],
                "rows": [
                    ["MiniDisc Disc Label", "The classic 37 x 52 mm sticker for the front of the disc, "
                                            "with a 3 mm chamfer on the top-left corner and rounded "
                                            "corners elsewhere."],
                    ["MiniDisc Disc Label (with Slider)", "The same, plus a separate small sticker for "
                                                          "the write-protect slider."],
                    ["Full disc label", "A label covering the whole 71 x 68 mm face of the cartridge, "
                                        "inset by a 0.8 mm margin."],
                    ["Full disc label (with Slider)", "The full face plus the slider sticker, nested into "
                                                      "the notch it sits on. This is what the automatic "
                                                      "layout uses."],
                    ["MiniDisc Cover (J-Card)", "The three-panel insert for the case: front, spine, back."],
                    ["MiniDisc Cover (J-Card + Window)", "The same with a cut-out window."],
                ],
            }},
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
            {"p": "**Project > Metadata...** holds the album title, artist, year and track list. It is "
                  "worth filling in even if you are only designing a label: the track list can be dropped "
                  "onto the artwork as text, and the automatic layout and the disc titling both read from "
                  "here."},
            {"fig": ("metadata", "Project > Metadata, with cover art fetched and a track list loaded.")},
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
            {"p": "Fill in album and artist in Project > Metadata... first - that is what it searches by. "
                  "If there is no cover art yet it looks one up before starting."},
            {"warn": "It **replaces both pages** and resets the undo history, so it asks for confirmation "
                     "first. The metadata itself is left alone."},
            {"h2": "What it builds"},
            {"p": "**The disc label**: the full-face template, the cover art stretched across it and then "
                  "cropped to the cut outline, and the MiniDisc logo on the write-protect slider sticker. "
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
            {"p": "The design leaves MDTools as two files that describe the same object in two ways."},
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
            {"h2": "Turning it on in MDTools"},
            {"p": "**Window > Settings...**, tick **Enable MDRem IR remote adapter**, and choose the "
                  "serial port."},
            {"fig": ("settings", "Window > Settings. The foobar2000 address is separate from the adapter.")},
            {"p": "**Detect** asks every serial port on the machine whether an MDRem answers on it. It has "
                  "to work that way: the board reports the USB ID `2E8A:0003`, which is also its own "
                  "bootloader's and other Waveshare boards', so the only reliable identification is the "
                  "device replying to a `PING`."},
            {"p": "Two things appear once the checkbox is ticked: **Upload Tracklist** in Project > "
                  "Metadata..., **Remote...** on the startup screen, and **Record to MiniDisc from "
                  "foobar2000...** in the Project menu."},
            {"note": "The foobar2000 address on the same page is deliberately *not* tied to the checkbox - "
                     "reading a playlist needs foobar2000, not the infrared adapter."},
        ],
    },
    # ------------------------------------------------------------------
    {
        "title": "The software remote",
        "blocks": [
            {"p": "**Remote...** on the startup screen opens a stand-in for the deck's own remote control, "
                  "laid out the way a physical one is."},
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
            {"p": "**Project > Metadata... > Upload Tracklist** writes the disc title and every track name "
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
            {"p": "**Project > Record to MiniDisc from foobar2000...** does the whole job in one go: it "
                  "arms the deck, plays the album out of foobar2000, watches it to the end, writes the "
                  "titles, and lays out both labels from the album's own artwork."},
            {"h2": "Setting up"},
            {"ol": [
                "Install the **Beefweb Remote Control** component (`foo_beefweb`) in foobar2000. That is "
                "how MDTools reads the playlist and follows what is playing. Its default address, "
                "`http://localhost:8880`, is what MDTools expects; change it in Window > Settings... if "
                "you moved it.",
                "Connect the computer's **S/PDIF** output - optical or coaxial - to the deck's digital "
                "input. This carries the audio; the USB link carries only commands.",
                "Load the album into foobar2000's current playlist, in the order you want it on the disc.",
                "Put a blank or erasable disc in the deck, tab closed, and set the recording mode (SP or "
                "LP2) **on the deck** - MDTools cannot read or change it.",
                "Turn **LEVEL-SYNC off** on the deck. See below.",
                "Aim the adapter at the deck's remote sensor and leave it there.",
            ]},
            {"fig": ("record", "The playlist as it will be recorded, in that order.")},
            {"h2": "What happens"},
            {"ol": [
                "MDTools shows the playlist and its total time, and warns if it will not fit on an "
                "80-minute disc in SP.",
                "It sets foobar to play straight through once - no shuffle, no repeat - so the disc "
                "cannot end up in a different order than the titles.",
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
            {"p": "So MDTools sends a track mark itself, at the exact moment foobar changes track - that "
                  "is the **Mark tracks through the adapter** checkbox, and it should stay ticked."},
            {"warn": "**Turn LEVEL-SYNC off on the deck when you use it.** Running both marks the same "
                     "boundary twice, a fraction of a second apart, and leaves a sliver of a track "
                     "stranded between them. They fight; they do not co-operate."},
            {"h2": "Recording mode and length"},
            {"p": "An MD holds 80 minutes in SP. MDTools warns when the playlist is longer than that, but "
                  "it can only warn - LP2 and LP4 have to be set on the deck itself, and there is no way "
                  "to read back which mode it is in."},
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
                  "time - close the other MDTools window, dialog, or terminal that is using it."},
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
            {"p": "MDTools drives all of this for you. It is documented here for anyone wanting to talk to "
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
