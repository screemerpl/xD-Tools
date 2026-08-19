# Bundled gallery images

Everything in this folder is offered to the user through Insert Asset (see
`src/mdtools/gallery.py`), and used by the automatic layouts.

## cd_digital_audio.svg / cd_digital_audio.png

The "Compact Disc Digital Audio" mark, placed on a burned CD's label by
`src/mdtools/cd_layout.py`.

- Source: Wikimedia Commons, [`File:CDDAlogo.svg`](https://commons.wikimedia.org/wiki/File:CDDAlogo.svg),
  downloaded unmodified from
  <https://upload.wikimedia.org/wikipedia/commons/1/14/CDDAlogo.svg>
  (SHA-1 `d0f8a95acf14d694cfdeb1ee529ade42a97a6b6d`, matching the checksum
  Commons publishes; SHA-256
  `e308a29fb2b70c1833c4693da5102ed5ddc85a1dd3dac87ed28cf8f651288547`).
- Original uploader: Jnavas (English Wikipedia), 3 February 2007,
  described there as being from a Philips graphic file, for identification
  purposes.
- Copyright status on Commons: **public domain** as a text logo
  (`PD-textlogo`) -- it is below the threshold of originality for
  copyright.
- **Trademark**: the same page carries a trademark warning, and it applies.
  This is Philips' certification mark for discs meeting the Red Book
  standard. Putting it on a disc you burned yourself is not a licensed use
  of it, whatever the copyright status of the drawing; it is here because
  it is what a CD label conventionally carries, and the layout that places
  it can have that layer deleted like any other.

`cd_digital_audio.png` is that SVG rendered by `scripts/make_cd_logo.py` --
the raster is what the app actually loads, since `gallery.py` lists raster
files only and `QPixmap` cannot be relied on to read SVG in a frozen build.
Re-run that script to regenerate it; nothing else here is generated.
