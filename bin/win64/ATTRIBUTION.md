# Bundled command line tools (Windows, x86-64)

MDTools ships these to read and encode audio CDs (Recording > Record CD to
MiniDisc...) and to write them (Recording > Burn Audio CD...). They are
unmodified upstream binaries, executed as separate programs via
`subprocess` -- see `src/mdtools/cdrip.py` and `src/mdtools/cdburn.py`,
which locate them through `cdrip.tools_dir()`.

Nothing is bundled for Linux: all three tools are packaged by every
distribution, and `cdrip.find_tool()` falls through to `PATH` there.

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

## cdrecord (cdrtools)

cdrecord 3.02a10, built 2021-07-23 for Windows (a Cygwin build -- hence
`cygwin1.dll` below). Writes the audio CD-R, disc-at-once, with CD-Text.

cdrdao was the first choice for this and was abandoned for a plain reason:
it has no maintained Windows build. Its last official win32 package is
1.1.5 from around 2004, Cygwin- and ASPI-based, in an OldFiles folder, and
upstream's own Windows instructions are stale. cdrtools is still built for
Windows, and is what the cdrtfe project ships.

- Upstream: <https://sourceforge.net/projects/cdrtools/> (Joerg Schilling)
- Binary taken from the cdrtfe project's own tools folder, which is where
  current Windows builds of cdrtools are published:
  <https://sourceforge.net/projects/cdrtfe/files/tools/binaries/cdrtools/>
  - `cdrtools-3.02a10-bin-win32.rar`
    (SHA-256 `4d6b68e50e26f5826a6b6286a927570457178257d4005f5c5bd8615593f58d02`)
    -- `cdrecord.exe`
    (SHA-256 `4586c7f68ff97b6d0323e761971311e16e54663d946d9c6de0584e6de28d3505`)
- Licence: CDDL-1.0 (cdrecord itself; other cdrtools components are GPL).

### Its runtime dependency

- `cygwin1.dll` -- Cygwin 2.3.1, the POSIX compatibility layer this build of
  cdrecord links against. Taken from the same place,
  <https://sourceforge.net/projects/cdrtfe/files/tools/binaries/cygwin/>,
  `cygwin1.dll_2.3.1.rar`
  (SHA-256 `8dbe90f7050ae53f6eda19cc4a4a6e1057903a763ecee189f69bfa0f09db05eb`),
  giving `cygwin1.dll`
  (SHA-256 `4f7a2e8c5d627cd053850a57fa266271ef6bce01d127d89c222ec3d8db159a47`).
- Licence: GPL-3.0-or-later with the Cygwin linking exception (this predates
  Cygwin's move to LGPL-3.0 in 2.5.2). Upstream: <https://cygwin.com/>.

## netmdcli (linux-minidisc, Jo2003's fork)

Drives a NetMD deck over USB: reads the disc, writes disc and track titles
into its TOC, and (later) sends audio to it. NetMD is a whole second way
of talking to a MiniDisc recorder alongside the MDRem infrared adapter --
see `src/mdtools/netmd.py`.

Jo2003's fork rather than upstream linux-minidisc: it carries fixes to
large-block transfers and to disc/group naming, and it is the build
published for Windows. Statically linked -- it needs no DLL of its own,
unlike everything above.

- Upstream: <https://github.com/Jo2003/netmd> (a fork of
  <https://github.com/glaubitz/linux-minidisc>)
- Binary taken from the cd2netmd release, which ships it in a `toolchain`
  folder alongside the CD tool it is there to serve:
  <https://github.com/Jo2003/cd2netmd/releases/download/v0.4.0/cd2netmd.zip>
  (SHA-256 `136f837f5a25e5f5f799ebf813fa6548c45c03663b8157ae68404f2b6e1919b7`)
  -- `toolchain/netmdcli.exe`
  (SHA-256 `78d9aa8c6617996036e138d3b0626ef479f7a6955e1507b434f8d4448a4357fc`)
- Licence: GPL-2.0-or-later.

**A NetMD deck needs a libusb-compatible driver on Windows.** Sony's own
driver does not expose the device to libusb, so the deck has to be bound
to WinUSB (with Zadig, or the driver cd2netmd_gui installs) before this
tool can see it at all. That is a user-facing setup step, not something
xD-Tools can do for them -- `netmd.py` reports "no NetMD device found"
for both a missing deck and a deck on the wrong driver, because from here
they look identical.

## Source code

Every GPL and CDDL tool here has its complete corresponding source published
by its upstream project at the addresses above, and by MSYS2 (for the
libcdio and flac packages) alongside the binaries listed. netmdcli's source
is the GitHub repository named above, at the tag its release was built
from. cdrtools' source
is on its SourceForge project page and mirrored in the same cdrtfe tools
folder the binary came from, under `tools/source/cdrtools`. No binary here
has been modified.
