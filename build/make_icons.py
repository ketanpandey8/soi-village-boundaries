#!/usr/bin/env python3
"""App icons for the web app manifest (dist/icons/): a few village parcels on the site's teal.
Drawn full-bleed so they also work as maskable icons (the safe zone is the middle 80%)."""
import os
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "icons")
TEAL, PARCELS, EDGE = "#0e7c86", ["#6ba368", "#e0a13c", "#d9663f", "#57a99a", "#c99a3c"], "#fffdf9"
# irregular parcels on a 100x100 grid, all inside the maskable safe zone (10..90)
SHAPES = [
    [(22, 26), (48, 20), (52, 44), (30, 50), (18, 40)],
    [(48, 20), (76, 24), (80, 46), (52, 44)],
    [(18, 40), (30, 50), (34, 76), (20, 72)],
    [(30, 50), (52, 44), (58, 70), (34, 76)],
    [(52, 44), (80, 46), (82, 74), (58, 70)],
]

def icon(size, path):
    S = 4                                            # draw large, then downsample
    im = Image.new("RGB", (size * S, size * S), TEAL)
    dr = ImageDraw.Draw(im)
    k = size * S / 100
    for pts, col in zip(SHAPES, PARCELS):
        dr.polygon([(x * k, y * k) for x, y in pts], fill=col, outline=EDGE, width=max(2, int(size * S / 90)))
    im.resize((size, size), Image.LANCZOS).save(path, optimize=True)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for n in (192, 512, 180):
        icon(n, os.path.join(OUT, f"icon-{n}.png"))
    print("icons ->", OUT)
