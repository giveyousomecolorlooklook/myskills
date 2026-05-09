#!/usr/bin/env python3
"""Convert Warcraft III BLP1 textures to/from PNG.

Supported reads:
- BLP1 JPEG-compressed textures
- BLP1 paletted textures with 0, 1, 4, or 8-bit alpha

Supported writes:
- PNG to BLP1 JPEG-compressed textures, with mipmaps and optional 8-bit alpha
"""

from __future__ import annotations

import argparse
import io
import math
import struct
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment guidance
    raise SystemExit(
        "Pillow is required. Install it with: python -m pip install pillow"
    ) from exc


HEADER_SIZE = 156
PALETTE_SIZE = 256 * 4
MAX_MIPS = 16
MAX_SHARED_JPEG_HEADER = 624


class BlpError(ValueError):
    """Raised when a file is not a supported BLP1 texture."""


def _read_u32_array(data: bytes, offset: int, count: int) -> tuple[int, ...]:
    return struct.unpack_from(f"<{count}I", data, offset)


def _mip_size(width: int, height: int, level: int) -> tuple[int, int]:
    return max(1, width >> level), max(1, height >> level)


def _unpack_alpha(raw: bytes, pixels: int, alpha_bits: int) -> list[int]:
    if alpha_bits == 0:
        return [255] * pixels
    if alpha_bits == 8:
        if len(raw) < pixels:
            raise BlpError("BLP alpha plane is shorter than expected")
        return list(raw[:pixels])
    if alpha_bits == 4:
        needed = (pixels + 1) // 2
        if len(raw) < needed:
            raise BlpError("BLP 4-bit alpha plane is shorter than expected")
        alpha: list[int] = []
        for byte in raw[:needed]:
            alpha.append((byte & 0x0F) * 17)
            if len(alpha) < pixels:
                alpha.append(((byte >> 4) & 0x0F) * 17)
        return alpha
    if alpha_bits == 1:
        needed = (pixels + 7) // 8
        if len(raw) < needed:
            raise BlpError("BLP 1-bit alpha plane is shorter than expected")
        alpha = []
        for byte in raw[:needed]:
            for bit in range(8):
                alpha.append(255 if (byte >> bit) & 1 else 0)
                if len(alpha) == pixels:
                    return alpha
        return alpha
    raise BlpError(f"Unsupported BLP1 alpha depth: {alpha_bits}")


def _find_jpeg_eoi(data: bytes) -> int | None:
    marker = data.find(b"\xff\xd9")
    return None if marker < 0 else marker + 2


def _decode_jpeg_blp(
    data: bytes,
    width: int,
    height: int,
    alpha_bits: int,
    offsets: tuple[int, ...],
    sizes: tuple[int, ...],
    level: int,
) -> Image.Image:
    jpeg_header_size = struct.unpack_from("<I", data, HEADER_SIZE)[0]
    header_start = HEADER_SIZE + 4
    header_end = header_start + jpeg_header_size
    if header_end > len(data):
        raise BlpError("BLP JPEG header extends past end of file")

    offset = offsets[level]
    size = sizes[level]
    if not offset or not size:
        raise BlpError(f"BLP mip level {level} is not present")
    if offset + size > len(data):
        raise BlpError("BLP JPEG mip data extends past end of file")

    jpeg_prefix = data[header_start:header_end]
    mip_payload = data[offset : offset + size]
    jpeg_bytes = jpeg_prefix + mip_payload
    image = Image.open(io.BytesIO(jpeg_bytes)).convert("RGBA")

    mip_w, mip_h = _mip_size(width, height, level)
    if image.size != (mip_w, mip_h):
        image = image.resize((mip_w, mip_h), Image.Resampling.LANCZOS)

    if alpha_bits:
        eoi = _find_jpeg_eoi(jpeg_bytes)
        if eoi is not None:
            trailing = jpeg_bytes[eoi:]
            pixels = mip_w * mip_h
            expected = pixels if alpha_bits == 8 else math.ceil(pixels * alpha_bits / 8)
            if len(trailing) >= expected:
                alpha = Image.new("L", (mip_w, mip_h))
                alpha.putdata(_unpack_alpha(trailing, pixels, alpha_bits))
                image.putalpha(alpha)

    return image


def _decode_paletted_blp(
    data: bytes,
    width: int,
    height: int,
    alpha_bits: int,
    offsets: tuple[int, ...],
    sizes: tuple[int, ...],
    level: int,
) -> Image.Image:
    palette_start = HEADER_SIZE
    palette_end = palette_start + PALETTE_SIZE
    if palette_end > len(data):
        raise BlpError("BLP palette extends past end of file")

    palette = []
    for i in range(256):
        b, g, r, a = data[palette_start + i * 4 : palette_start + i * 4 + 4]
        palette.append((r, g, b, a))

    offset = offsets[level]
    size = sizes[level]
    if not offset or not size:
        raise BlpError(f"BLP mip level {level} is not present")
    if offset + size > len(data):
        raise BlpError("BLP paletted mip data extends past end of file")

    mip_w, mip_h = _mip_size(width, height, level)
    pixels = mip_w * mip_h
    payload = data[offset : offset + size]
    if len(payload) < pixels:
        raise BlpError("BLP index plane is shorter than expected")

    indices = payload[:pixels]
    alpha_plane = payload[pixels:]
    alpha = None
    if alpha_bits:
        expected_alpha_bytes = math.ceil(pixels * alpha_bits / 8)
        if len(alpha_plane) >= expected_alpha_bytes:
            alpha = _unpack_alpha(alpha_plane, pixels, alpha_bits)
    rgba = [
        (
            palette[index][0],
            palette[index][1],
            palette[index][2],
            alpha[pos] if alpha is not None else palette[index][3],
        )
        for pos, index in enumerate(indices)
    ]

    image = Image.new("RGBA", (mip_w, mip_h))
    image.putdata(rgba)
    return image


def read_blp1(path: Path, level: int = 0) -> Image.Image:
    data = path.read_bytes()
    if len(data) < HEADER_SIZE:
        raise BlpError("File is too small to be a BLP1 texture")
    if data[:4] != b"BLP1":
        raise BlpError("Only Warcraft III BLP1 files are supported")

    compression, alpha_bits, width, height, _picture_type, _picture_subtype = struct.unpack_from(
        "<6I", data, 4
    )
    if width <= 0 or height <= 0:
        raise BlpError("BLP has invalid dimensions")
    if not 0 <= level < MAX_MIPS:
        raise BlpError("Mip level must be in the range 0..15")

    offsets = _read_u32_array(data, 28, MAX_MIPS)
    sizes = _read_u32_array(data, 92, MAX_MIPS)

    if compression == 0:
        return _decode_jpeg_blp(data, width, height, alpha_bits, offsets, sizes, level)
    if compression == 1:
        return _decode_paletted_blp(data, width, height, alpha_bits, offsets, sizes, level)
    raise BlpError(f"Unsupported BLP1 compression mode: {compression}")


def _build_mips(image: Image.Image, make_mips: bool) -> list[Image.Image]:
    image = image.convert("RGBA")
    mips = [image]
    if not make_mips:
        return mips

    current = image
    while len(mips) < MAX_MIPS and (current.width > 1 or current.height > 1):
        next_size = (max(1, current.width // 2), max(1, current.height // 2))
        current = current.resize(next_size, Image.Resampling.LANCZOS)
        mips.append(current)
    return mips


def _normalize_blp1_jpeg(data: bytes) -> bytes:
    """Patch Pillow CMYK JPEG into the 4-component JPEG shape used by WC3 BLP1."""
    out = bytearray()
    pos = 0
    while pos < len(data):
        if data[pos] != 0xFF:
            out.extend(data[pos:])
            break

        marker_start = pos
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos >= len(data):
            out.extend(data[marker_start:])
            break

        marker = data[pos]
        pos += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            out.extend(data[marker_start:pos])
            continue

        if pos + 2 > len(data):
            raise BlpError("Truncated JPEG marker")
        length = int.from_bytes(data[pos : pos + 2], "big")
        segment_end = pos + length
        if segment_end > len(data):
            raise BlpError("Truncated JPEG segment")

        # Drop JFIF/Adobe application markers. WC3 BLP1 JPEG samples commonly omit them.
        if marker in (0xE0, 0xEE):
            pos = segment_end
            continue

        segment = bytearray(data[marker_start:segment_end])
        if marker == 0xC0 and len(segment) >= 2 + 2 + 1 + 2 + 2 + 1 + 12:
            component_count_index = 2 + 2 + 1 + 2 + 2
            if segment[component_count_index] == 4:
                component_start = component_count_index + 1
                for i in range(4):
                    segment[component_start + i * 3] = i + 1
        elif marker == 0xDA and len(segment) >= 2 + 2 + 1 + 8:
            component_count_index = 2 + 2
            if segment[component_count_index] == 4:
                component_start = component_count_index + 1
                for i in range(4):
                    segment[component_start + i * 2] = i + 1

        out.extend(segment)
        pos = segment_end
        if marker == 0xDA:
            out.extend(data[pos:])
            break

    return bytes(out)


def _encode_jpeg_payload(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.convert("CMYK").save(buffer, format="JPEG", quality=quality, optimize=False)
    return _normalize_blp1_jpeg(buffer.getvalue())


def _shared_prefix(chunks: list[bytes], max_size: int) -> bytes:
    if not chunks:
        return b""

    limit = min(max_size, min(len(chunk) for chunk in chunks))
    first = chunks[0]
    end = 0
    for i in range(limit):
        value = first[i]
        if any(chunk[i] != value for chunk in chunks[1:]):
            break
        end = i + 1
    return first[:end]


def write_blp1_png_source(
    source: Path,
    dest: Path,
    make_mips: bool = True,
    quality: int = 95,
) -> None:
    if not 1 <= quality <= 100:
        raise BlpError("JPEG quality must be in the range 1..100")

    image = Image.open(source).convert("RGBA")
    mips = _build_mips(image, make_mips)
    alpha_min, _alpha_max = image.getchannel("A").getextrema()
    has_alpha = alpha_min < 255
    alpha_bits = 8 if has_alpha else 0

    encoded_mips = []
    jpeg_chunks = []
    alpha_chunks = []
    for mip in mips:
        jpeg_chunks.append(_encode_jpeg_payload(mip, quality))
        if alpha_bits:
            alpha_chunks.append(mip.getchannel("A").tobytes())
        else:
            alpha_chunks.append(b"")

    shared_header = _shared_prefix(jpeg_chunks, MAX_SHARED_JPEG_HEADER)
    for jpeg_chunk, alpha_chunk in zip(jpeg_chunks, alpha_chunks):
        encoded_mips.append(jpeg_chunk[len(shared_header) :] + alpha_chunk)

    offsets = [0] * MAX_MIPS
    sizes = [0] * MAX_MIPS
    cursor = HEADER_SIZE + 4 + len(shared_header)
    for i, payload in enumerate(encoded_mips):
        offsets[i] = cursor
        sizes[i] = len(payload)
        cursor += len(payload)

    header = struct.pack(
        "<4s6I16I16I",
        b"BLP1",
        0,  # JPEG-compressed
        alpha_bits,
        image.width,
        image.height,
        6,
        1,
        *offsets,
        *sizes,
    )

    dest.write_bytes(header + struct.pack("<I", len(shared_header)) + shared_header + b"".join(encoded_mips))


def convert(
    source: Path,
    dest: Path,
    level: int = 0,
    make_mips: bool = True,
    quality: int = 95,
) -> None:
    src_ext = source.suffix.lower()
    dst_ext = dest.suffix.lower()

    if src_ext == ".blp" and dst_ext == ".png":
        image = read_blp1(source, level=level)
        image.save(dest)
        return
    if src_ext == ".png" and dst_ext == ".blp":
        write_blp1_png_source(source, dest, make_mips=make_mips, quality=quality)
        return
    raise BlpError("Use .blp -> .png or .png -> .blp paths")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert Warcraft III BLP1 textures to/from PNG.")
    parser.add_argument("source", type=Path)
    parser.add_argument("dest", type=Path)
    parser.add_argument("--level", type=int, default=0, help="Mip level to extract when converting BLP to PNG.")
    parser.add_argument("--no-mips", action="store_true", help="Do not generate mipmaps when writing BLP.")
    parser.add_argument(
        "--quality",
        type=int,
        default=95,
        help="JPEG quality when converting PNG to BLP, in the range 1..100.",
    )
    args = parser.parse_args(argv)

    try:
        convert(
            args.source,
            args.dest,
            level=args.level,
            make_mips=not args.no_mips,
            quality=args.quality,
        )
    except (OSError, BlpError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
