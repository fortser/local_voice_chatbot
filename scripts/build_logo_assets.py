"""Rebuild the Modern UI logo and window icon from the generated pixel-art source.

The source image is AI-generated "pixel art": 1254x1254 with ~15x15 px soft blocks
and thousands of near-identical colours. This script snaps it back to its native
grid (one colour per block), trims the palette and writes small crisp assets:

    assets/branding/shura_logo.png   native sprite (~83x84), scaled by the UI
    assets/branding/shura_icon.png   256x256 window icon (head in a rounded frame)
    assets/branding/shura_icon.ico   multi-size icon for Windows shortcuts

Usage:
    python scripts/build_logo_assets.py ["Pixel-Art Woman Eavesdropping.png"]

Requires Pillow and numpy. The UI itself only reads the generated PNG/ICO files.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Pixel-Art Woman Eavesdropping.png"
OUT_DIR = ROOT / "assets" / "branding"

# Block grid measured on the source by edge autocorrelation (period, phase in px).
GRID_X = (15.08, 4.25)
GRID_Y = (14.71, 6.75)
SAMPLE_RADIUS = 4          # px around each block centre; ignores soft block borders
PALETTE_SIZE = 40
ICON_CROP = (17, 1, 73, 57)  # sprite cells: face and the hand at the ear
SURFACE = (28, 35, 40, 255)  # theme "surface"
ACCENT = (168, 235, 206, 255)  # theme "accent"


def _centres(period: float, phase: float, length: int) -> np.ndarray:
    count = int(length / period) + 2
    centres = phase + 0.5 + period * (np.arange(-1, count) + 0.5)
    return centres[(centres >= 3) & (centres <= length - 4)]


def snap_to_grid(source: Image.Image) -> Image.Image:
    pixels = np.asarray(source.convert("RGBA")).astype(float)
    height, width = pixels.shape[:2]
    xs, ys = _centres(*GRID_X, width), _centres(*GRID_Y, height)
    sprite = np.zeros((len(ys), len(xs), 4), dtype=np.uint8)
    r = SAMPLE_RADIUS
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            y0, x0 = int(round(y)), int(round(x))
            patch = pixels[max(0, y0 - r):y0 + r + 1, max(0, x0 - r):x0 + r + 1].reshape(-1, 4)
            if np.median(patch[:, 3]) < 128:
                continue
            opaque = patch[patch[:, 3] >= 128]
            sprite[j, i, :3] = np.median(opaque[:, :3], axis=0)
            sprite[j, i, 3] = 255  # source alpha is 253: make the figure fully opaque
    image = Image.fromarray(sprite, "RGBA")
    alpha = image.getchannel("A")
    reduced = image.convert("RGB").quantize(
        colors=PALETTE_SIZE, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    ).convert("RGB")
    reduced.putalpha(alpha)
    top = alpha.getbbox()[1]
    return reduced.crop((0, max(0, top - 2), reduced.width, reduced.height))


def build_icon(sprite: Image.Image, size: int = 256) -> Image.Image:
    border = size // 32
    radius = size // 5
    crop = sprite.crop(ICON_CROP)
    inner = size - 2 * border
    face = crop.resize((inner, inner), Image.NEAREST)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius, fill=255)
    background = Image.new("RGBA", (size, size), SURFACE)
    background.alpha_composite(face, (border, border))
    canvas.paste(background, (0, 0), mask)
    ImageDraw.Draw(canvas).rounded_rectangle(
        (border // 2, border // 2, size - 1 - border // 2, size - 1 - border // 2),
        radius - border // 2, outline=ACCENT, width=border,
    )
    return canvas


def main(argv: list[str]) -> int:
    source = Path(argv[1]) if len(argv) > 1 else SOURCE
    if not source.is_file():
        print(f"Не найден исходник: {source}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sprite = snap_to_grid(Image.open(source))
    sprite.save(OUT_DIR / "shura_logo.png", optimize=True)
    icon = build_icon(sprite)
    icon.save(OUT_DIR / "shura_icon.png", optimize=True)
    icon.save(OUT_DIR / "shura_icon.ico",
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Логотип {sprite.size[0]}x{sprite.size[1]}, иконка 256x256 → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
