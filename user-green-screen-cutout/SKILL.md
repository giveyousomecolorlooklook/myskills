---
name: user-green-screen-cutout
description: Remove flat green-screen/chroma-key backgrounds from PNG/JPEG/WebP images and produce clean alpha PNG cutouts. Use when Codex needs deterministic background removal for game UI sheets, sprites, icons, product-like assets, or screenshots on a solid green/chroma canvas, especially when edges must be despilled and validated for alpha and fringe-free results.
---

# Green Screen Cutout

## Quick Start

Use the bundled script for deterministic chroma-key removal:

```bash
python "$CODEX_HOME/skills/user-green-screen-cutout/scripts/chroma_cutout.py" source/*.png --out-dir output/cutout
```

On Windows when `CODEX_HOME` is unset, use:

```powershell
python "$HOME\.codex\skills\user-green-screen-cutout\scripts\chroma_cutout.py" source\*.png --out-dir output\cutout
```

## Workflow

1. Inspect the input image first when the content may contain green subject matter.
2. Run `scripts/chroma_cutout.py` on the target image or folder.
3. Check the report:
   - `mode=RGBA` or `alpha=yes`
   - transparent pixels are present
   - `fringe_pixels` is low or zero
4. If a green fringe remains, retry with more aggressive cleanup:

```bash
python "$CODEX_HOME/skills/user-green-screen-cutout/scripts/chroma_cutout.py" image.png --out-dir output/cutout --edge-contract 1 --despill-strength 1.0
```

5. If fine anti-aliased detail is being lost, retry less aggressively:

```bash
python "$CODEX_HOME/skills/user-green-screen-cutout/scripts/chroma_cutout.py" image.png --out-dir output/cutout --transparent-floor 0.78 --despill-strength 0.75
```

## Script Behavior

The script estimates the key color from the border, computes a green-dominance matte, removes fully keyed pixels, recovers semi-transparent edge color from the chroma-key composite, and despills remaining green contamination.

Useful options:

- `--key R,G,B`: override automatic border key estimation.
- `--transparent-floor N`: lower values remove more green; default is `0.62`.
- `--edge-contract N`: remove a thin alpha edge in pixels; use `1` for stubborn halos.
- `--despill-strength N`: `0` disables despill, `1` is full cleanup.
- `--preview-dir DIR`: optionally write checkerboard preview PNGs for debugging. Do not use this by default; only create previews when visual edge inspection is necessary.

Prefer this script over generation-based editing when the source already has a flat chroma background. Use image generation/editing only when the source is not actually keyed or needs semantic reconstruction.
