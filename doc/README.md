# doc/

The user manual, built from source rather than written here.

| File | |
|---|---|
| `xD-Tools-Manual-EN.pdf` | English |
| `xD-Tools-Manual-PL.pdf` | Polski |
| `xD-Tools-Manual-JA.pdf` | 日本語 |
| `img/<lang>/` | screenshots, one set per language |
| `img/ir-circuit.png` | the MDRem output stage (language-independent) |

## Rebuilding

```powershell
.venv\Scripts\python scripts\manual\make_screenshots.py   # only when the UI changed
.venv\Scripts\python scripts\manual\build_manual.py       # all three, or pass "pl"
```

**Neither step should be run with `QT_QPA_PLATFORM=offscreen` forced --
run both with whatever the normal, default platform plugin is.**
`make_screenshots.py` opens each dialog and grabs it, so it visibly puts
windows on your desktop while it runs, and it cannot be run offscreen at
all: that platform reports no installed font families here, and every
caption comes out as tofu boxes. `build_manual.py` never opens a window --
it only renders a `QTextDocument` into a `QPdfWriter` -- which reads as
"therefore safe under offscreen" but isn't: the missing-font-database
problem is about the platform plugin's font enumeration, not about whether
a window is shown, and it hits `QTextDocument` painting exactly the same
way. Confirmed directly -- run under `QT_QPA_PLATFORM=offscreen`,
`build_manual.py` silently produced PDFs where *every* glyph, English
included, painted as a solid black box instead of a character, in all
three languages, with no error or warning of any kind. Rebuilding with the
default platform plugin (i.e. no `QT_QPA_PLATFORM` override) produced
correct text immediately. `build_manual.py` can still be run while xD-Tools
itself is busy recording -- that part of the original reasoning holds --
just not with the platform forced to offscreen.

**The screenshot script must never reach the network either.** The demo
album is invented so the figures regenerate identically anywhere, offline --
and the recording dialogs now look a cover up as soon as they open, which
would break that (and leave every preview empty, since a real search
correctly finds nothing for an album that does not exist). `fetch_into` is
stood in for per importing module, alongside the serial-port and foobar2000
stand-ins.

**The Telegram figures need no stand-in at all**, unlike those. Both
dialogs are inert until an explicit action starts their worker
(`TelegramChatDialog.start_connecting()`, and `TelegramLoginDialog` only on
"Send code"), so plain construction opens no socket; `_capture_telegram()`
then fills the transcript by handing synthetic `ChatMessage`s straight to
the dialog's own signal handlers -- the real rendering code driven with
fake data. It also writes two real (empty) `.flac` files into a throwaway
download folder, because Sort and Record enable themselves from what is
actually on disk, and without them the figure shows three greyed-out
buttons the manual points at.

The text lives in `scripts/manual/content_{en,pl,ja}.py` as a list of
blocks; `build_manual.py` turns those into a `QTextDocument` and paints it
onto a `QPdfWriter`. No LaTeX, no extra dependencies — everything used is
already needed by the app itself.

## Two things worth knowing before editing

**The screenshots are generated, not captured.** Three languages means
every figure is needed three times over, and a hand-taken set goes stale
the moment a label changes. `make_screenshots.py` builds a demo project
from an invented album, drives each dialog, and grabs it. It runs in
`QStandardPaths` test mode and stubs out the serial port and foobar2000,
so it cannot disturb the real settings or grab a port that a recording is
using.

**The menu names in the text must match the translations.**
`src/mdtools/i18n/mdtools_{pl,ja}.ts` is the source of truth — the Polish
and Japanese manuals show Polish and Japanese screenshots, so a mismatch
is visible immediately. Re-check the affected strings there when you
rename a menu item.

**`make_screenshots.py` must apply the app's theme the same way `main.py`
does.** It builds its own `QApplication` rather than importing `main()`, so
adding `theme.apply_theme(app)` to one didn't automatically reach the
other -- caught only because the screenshots were regenerated for an
unrelated reason (a Telegram dialog change) right after the Fusion/dark
theme landed, and would otherwise have kept shipping every figure in Qt's
old default light theme, silently out of step with what the real app has
looked like since. If `main.py` ever gains another app-wide, purely visual
setup step, mirror it here too.
