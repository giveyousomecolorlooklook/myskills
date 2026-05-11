#!/usr/bin/env python3
"""Remove green/chroma backgrounds and write alpha PNG cutouts."""

from __future__ import annotations

import argparse
import glob
import math
import os
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageFilter


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return low if value < low else high if value > high else value


def parse_key(value: str) -> tuple[int, int, int]:
    parts = value.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("key must be R,G,B")
    try:
        rgb = tuple(int(p.strip()) for p in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("key must contain integers") from exc
    if any(c < 0 or c > 255 for c in rgb):
        raise argparse.ArgumentTypeError("key values must be 0..255")
    return rgb  # type: ignore[return-value]


def expand_inputs(patterns: Sequence[str]) -> list[Path]:
    out: list[Path] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            out.extend(Path(m) for m in matches)
        else:
            out.append(Path(pattern))
    return sorted({p.resolve() for p in out if p.exists() and p.is_file()})


def border_pixels(image: Image.Image, width: int) -> Iterable[tuple[int, int, int]]:
    w, h = image.size
    px = image.load()
    bw = max(1, min(width, w // 2, h // 2))
    for y in range(h):
        for x in range(w):
            if x < bw or y < bw or x >= w - bw or y >= h - bw:
                r, g, b = px[x, y][:3]
                yield r, g, b


def estimate_key(image: Image.Image, border_width: int) -> tuple[int, int, int]:
    candidates = []
    for r, g, b in border_pixels(image, border_width):
        if g >= 80 and g > max(r, b) + 25:
            candidates.append((r, g, b))
    if not candidates:
        candidates = list(border_pixels(image, border_width))
    buckets = Counter((r // 4, g // 4, b // 4) for r, g, b in candidates)
    bucket, _ = buckets.most_common(1)[0]
    selected = [
        (r, g, b)
        for r, g, b in candidates
        if (r // 4, g // 4, b // 4) == bucket
    ]
    selected.sort()
    mid = len(selected) // 2
    rs = sorted(p[0] for p in selected)
    gs = sorted(p[1] for p in selected)
    bs = sorted(p[2] for p in selected)
    return rs[mid], gs[mid], bs[mid]


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 1.0 if x >= edge1 else 0.0
    t = clamp((x - edge0) / (edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def recover_foreground(
    rgb: tuple[int, int, int],
    key: tuple[int, int, int],
    bg_fraction: float,
    despill_strength: float,
) -> tuple[int, int, int]:
    fg_fraction = 1.0 - bg_fraction
    if fg_fraction <= 0.0:
        return 0, 0, 0
    recovered = []
    for c, k in zip(rgb, key):
        recovered.append(int(round(clamp((c - bg_fraction * k) / fg_fraction, 0, 255))))
    r, g, b = recovered
    if despill_strength > 0 and g > max(r, b):
        neutral_g = max(r, b)
        g = int(round(g + (neutral_g - g) * clamp(despill_strength)))
    return r, g, b


def contract_alpha(alpha: Image.Image, pixels: int) -> Image.Image:
    if pixels <= 0:
        return alpha
    mask = alpha
    for _ in range(pixels):
        mask = mask.filter(ImageFilter.MinFilter(3))
    return mask


def cutout_image(
    image: Image.Image,
    key: tuple[int, int, int],
    transparent_floor: float,
    despill_strength: float,
    edge_contract: int,
) -> Image.Image:
    src = image.convert("RGB")
    w, h = src.size
    key_dom = max(20, key[1] - max(key[0], key[2]))
    low = max(8.0, key_dom * 0.05)
    high = max(low + 1.0, key_dom * transparent_floor)
    hard_green = max(45.0, key_dom * 0.28)
    hard_g = max(70.0, key[1] * 0.58)

    out = Image.new("RGBA", (w, h))
    src_px = src.load()
    out_px = out.load()
    alpha = Image.new("L", (w, h), 255)
    alpha_px = alpha.load()

    for y in range(h):
        for x in range(w):
            r, g, b = src_px[x, y]
            dominance = g - max(r, b)
            bg_fraction = smoothstep(low, high, dominance)
            if g >= hard_g and dominance >= hard_green and max(r, b) <= max(80, key[1] * 0.38):
                bg_fraction = 1.0
            if bg_fraction >= 0.985:
                a = 0
                fr, fg, fb = 0, 0, 0
            else:
                a = int(round(255 * (1.0 - bg_fraction)))
                if a >= 250:
                    a = 255
                    fr, fg, fb = r, g, b
                    if despill_strength > 0 and fg > max(fr, fb) + 4:
                        neutral_g = max(fr, fb)
                        fg = int(round(fg + (neutral_g - fg) * clamp(despill_strength)))
                else:
                    fr, fg, fb = recover_foreground((r, g, b), key, bg_fraction, despill_strength)
                    if a <= 4:
                        a = 0
                        fr, fg, fb = 0, 0, 0
            out_px[x, y] = (fr, fg, fb, a)
            alpha_px[x, y] = a

    if edge_contract > 0:
        contracted = contract_alpha(alpha, edge_contract)
        contracted_px = contracted.load()
        out_px = out.load()
        for y in range(h):
            for x in range(w):
                a = contracted_px[x, y]
                r, g, b, old_a = out_px[x, y]
                if a == 0:
                    out_px[x, y] = (0, 0, 0, 0)
                elif a != old_a:
                    out_px[x, y] = (r, g, b, a)
    return out


def checker_preview(image: Image.Image, tile: int = 24) -> Image.Image:
    rgba = image.convert("RGBA")
    w, h = rgba.size
    bg = Image.new("RGB", (w, h), "white")
    px = bg.load()
    for y in range(h):
        for x in range(w):
            shade = 210 if ((x // tile) + (y // tile)) % 2 else 245
            px[x, y] = (shade, shade, shade)
    bg.paste(rgba, (0, 0), rgba)
    return bg


def validate(image: Image.Image) -> dict[str, int | str]:
    rgba = image.convert("RGBA")
    total = rgba.size[0] * rgba.size[1]
    transparent = 0
    partial = 0
    fringe = 0
    alpha_min = 255
    alpha_max = 0
    data = rgba.get_flattened_data() if hasattr(rgba, "get_flattened_data") else rgba.getdata()
    for r, g, b, a in data:
        alpha_min = min(alpha_min, a)
        alpha_max = max(alpha_max, a)
        if a == 0:
            transparent += 1
        elif a < 255:
            partial += 1
            if g > max(r, b) + 8 and g > 24:
                fringe += 1
        else:
            if g > max(r, b) + 18 and g > 48 and max(r, b) < 96:
                fringe += 1
    return {
        "mode": rgba.mode,
        "pixels": total,
        "transparent_pixels": transparent,
        "partial_alpha_pixels": partial,
        "fringe_pixels": fringe,
        "alpha_min": alpha_min,
        "alpha_max": alpha_max,
    }


def process_one(path: Path, args: argparse.Namespace) -> dict[str, int | str]:
    image = Image.open(path)
    key = args.key if args.key is not None else estimate_key(image.convert("RGB"), args.border_width)
    out = cutout_image(
        image,
        key=key,
        transparent_floor=args.transparent_floor,
        despill_strength=args.despill_strength,
        edge_contract=args.edge_contract,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{path.stem}{args.suffix}.png"
    out.save(out_path)
    if args.preview_dir:
        args.preview_dir.mkdir(parents=True, exist_ok=True)
        checker_preview(out).save(args.preview_dir / f"{path.stem}{args.suffix}_preview.png")
    report = validate(out)
    report["input"] = str(path)
    report["output"] = str(out_path)
    report["key"] = f"{key[0]},{key[1]},{key[2]}"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="Input images or glob patterns")
    parser.add_argument("--out-dir", type=Path, default=Path("output/cutout"))
    parser.add_argument("--preview-dir", type=Path)
    parser.add_argument("--suffix", default="_cutout")
    parser.add_argument("--key", type=parse_key, help="Override key color as R,G,B")
    parser.add_argument("--border-width", type=int, default=8)
    parser.add_argument("--transparent-floor", type=float, default=0.62)
    parser.add_argument("--despill-strength", type=float, default=0.95)
    parser.add_argument("--edge-contract", type=int, default=0)
    args = parser.parse_args()

    inputs = expand_inputs(args.inputs)
    if not inputs:
        parser.error("no input files found")
    for path in inputs:
        report = process_one(path, args)
        parts = [f"{k}={v}" for k, v in report.items()]
        print(" | ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
