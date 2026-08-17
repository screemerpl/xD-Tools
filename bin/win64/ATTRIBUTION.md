# Bundled command line tools (Windows, x86-64)

MDTools ships these to read and encode audio CDs (Project > Record CD to
MiniDisc...). They are unmodified upstream binaries, executed as separate
programs via `subprocess` -- see `src/mdtools/cdrip.py`, which locates them
through `tools_dir()`.

Nothing is bundled for Linux: both tools are packaged by every distribution,
and `cdrip.find_tool()` falls through to `PATH` there.

## cd-paranoia (libcdio-paranoia)

cdparanoia III release 10.2, built against libcdio 2.2.0. The maintained
GNU libcdio port of Xiph.Org's cdparanoia -- reads CD digital audio with
jitter correction and re-reads on damaged sectors.

- Upstream: <https://www.gnu.org/software/libcdio/>
- Binaries taken from the MSYS2 mingw64 repository,
  <https://repo.msys2.org/mingw/mingw64/>:
  - `mingw-w64-x86_64-libcdio-paranoia-10.2+2.0.2-1-any.pkg.tar.zst`
    (SHA-256 `298bf8ef059f2d07448480a63fe6dd3f9c159303244e2e391d4737349db0abde`)
    -- `cd-paranoia.exe`, `libcdio_cdda-2.dll`, `libcdio_paranoia-2.dll`
  - `mingw-w64-x86_64-libcdio-2.2.0-1-any.pkg.tar.zst`
    (SHA-256 `0261143ccec15938b2e6268e2b55dd6b33538443c54a8aa79fac31895599a94f`)
    -- `libcdio-19.dll`
- Licence: GPL-3.0-or-later (cdparanoia itself is GPL-2.0-or-later).

### Its runtime dependencies, same source

- `libiconv-2.dll`, `libcharset-1.dll` -- GNU libiconv 1.19, LGPL-2.1-or-later,
  from `mingw-w64-x86_64-libiconv-1.19-1-any.pkg.tar.zst`
- `libwinpthread-1.dll` -- mingw-w64 winpthreads, MIT/BSD-style, from
  `mingw-w64-x86_64-libwinpthread-git-12.0.0.r747.g1a99f8514-1-any.pkg.tar.zst`

## flac

flac 1.5.0, the reference FLAC encoder from Xiph.Org.

- Upstream: <https://xiph.org/flac/>
- Binary taken from the official Windows release,
  <https://downloads.xiph.org/releases/flac/flac-1.5.0-win.zip>
  (SHA-256 `53f1500f0d6e7c61379d7fee50d4a9f7f504c650009506d9ba015530d76c0dde`),
  `Win64/flac.exe` and `Win64/libFLAC.dll`.
- Licence: the `flac` command line tool is GPL-2.0-or-later; `libFLAC` is
  BSD-3-Clause.

## Source code

Both GPL tools' complete corresponding source is published by their upstream
projects at the addresses above, and by MSYS2 alongside the binary packages
listed here. Neither binary has been modified.
