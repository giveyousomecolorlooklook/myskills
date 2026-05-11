---
name: user-blp1-converter
description: Convert Warcraft III BLP1 texture files to PNG and convert PNG images back to Warcraft III BLP1. Use when working with .blp game textures, Warcraft III icons/assets, BLP1 JPEG-compressed textures, BLP1 paletted textures, or round-tripping image assets between .blp and .png.
---

# BLP1 Converter

## Quick Start

Use the bundled Python script for deterministic conversion:

```powershell
python C:\Users\admin\.codex\skills\user-blp1-converter\scripts\convert_blp1.py input.blp output.png
python C:\Users\admin\.codex\skills\user-blp1-converter\scripts\convert_blp1.py input.png output.blp
python C:\Users\admin\.codex\skills\user-blp1-converter\scripts\convert_blp1.py input.png output.blp --quality 95
```

The script auto-detects direction from file extensions. It requires Pillow:

```powershell
python -m pip install pillow
```

## Capabilities

- Read Warcraft III `BLP1` JPEG-compressed textures and write PNG.
- Read JPEG `BLP1` files that store alpha in a 4-component BGRA-style JPEG payload, as well as files with an external alpha plane after the JPEG mip data.
- Read Warcraft III `BLP1` paletted textures with 0, 1, 4, or 8-bit alpha and write PNG.
- Write PNG input only as Warcraft III `BLP1` JPEG-compressed textures. This avoids the 256-color palette limit but is lossy.
- Encode PNG alpha in the 4th component of the BGRA-style JPEG payload so generated `.blp` files display correctly in Warcraft III BLP viewers.
- Generate mipmaps by default when writing BLP; pass `--no-mips` to write only the base image.
- Use a shared JPEG header plus per-mip JPEG chunks, matching the common BLP1 JPEG layout used by community tools: 4-component JPEG data without JFIF/Adobe app markers.

## Byte-Level Round Trips

Do not claim byte-identical `PNG -> BLP -> PNG` output. PNG file bytes include encoder choices and chunks that are not represented in normal Warcraft III BLP1 image data. JPEG-compressed BLP1 is also lossy, including the embedded alpha channel, so validate visual quality or pixel error rather than file-byte equality.

## Validation Workflow

After converting, verify both directions with the script itself:

```powershell
python C:\Users\admin\.codex\skills\user-blp1-converter\scripts\convert_blp1.py source.blp source.png
python C:\Users\admin\.codex\skills\user-blp1-converter\scripts\convert_blp1.py source.png roundtrip.blp
python C:\Users\admin\.codex\skills\user-blp1-converter\scripts\convert_blp1.py roundtrip.blp roundtrip.png
```

If conversion fails, inspect the first 4 bytes and header fields. This skill intentionally targets `BLP1`; reject `BLP2` or other formats unless the user asks to extend the converter.
