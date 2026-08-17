# doc/

The user manual, built from source rather than written here.

| File | |
|---|---|
| `MDTools-Manual-EN.pdf` | English |
| `MDTools-Manual-PL.pdf` | Polski |
| `MDTools-Manual-JA.pdf` | 日本語 |
| `img/<lang>/` | screenshots, one set per language |
| `img/ir-circuit.png` | the MDRem output stage (language-independent) |

## Rebuilding

```powershell
.venv\Scripts\python scripts\manual\make_screenshots.py   # only when the UI changed
.venv\Scripts\python scripts\manual\build_manual.py       # all three, or pass "pl"
```

**The screenshot step needs a real screen; the build step does not.**
`make_screenshots.py` opens each dialog and grabs it, so it puts windows on
your desktop while it runs, and it cannot be run under
`QT_QPA_PLATFORM=offscreen` -- that platform reports no installed font
families here and every caption comes out as tofu boxes. `build_manual.py`
only renders a `QTextDocument` into a `QPdfWriter`: no window appears, so
the text can be rebuilt at any time, including while MDTools itself is busy
recording.

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
