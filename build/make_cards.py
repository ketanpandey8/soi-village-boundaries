#!/usr/bin/env python3
"""Draw the link-preview images (1200x630 PNG) shown when a page is shared:

  dist/cards/india.png    every state, released ones coloured, the rest grey
  dist/cards/<slug>.png   one state with all its villages, coloured by district

The Worker points og:image at these (src/worker.js). Needs Pillow and macOS's Helvetica
Neue; run after build_all.py and make_india.py.
"""
import os, json, math
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "dist", "data")
OUT = os.path.join(ROOT, "dist", "cards")
W, H, SS = 1200, 630, 2                     # drawn at 2x, then downsampled for smooth edges
MAP_W = 640                                 # left panel holds the map, right the text
BG, PANEL, INK, MUTED, ACCENT = "#f6f3ee", "#fffdf9", "#1a1e22", "#6b6862", "#0e7c86"
MAP_BG, NODATA, EDGE = "#eef0ec", "#d9d3c7", "#fffdf9"
PALETTE = ["#6ba368", "#e0a13c", "#d9663f", "#3d94a6", "#8a6fb0", "#c0577f", "#4d9670",
           "#c99a3c", "#5b8def", "#d17c4a", "#57a99a", "#b0563f", "#7aa03f", "#9a6ac0", "#3f9fb0", "#c77d9e"]
FONT = "/System/Library/Fonts/HelveticaNeue.ttc"   # index 0 regular, 1 bold, 10 medium

def font(size, idx=0):
    return ImageFont.truetype(FONT, size * SS, index=idx)

def merc(lo, la):
    return lo, math.degrees(math.log(math.tan(math.pi / 4 + math.radians(la) / 2)))

def rings(g):
    if g["type"] == "Polygon": yield from g["coordinates"]
    elif g["type"] == "MultiPolygon":
        for p in g["coordinates"]: yield from p

def projector(geoms, box):
    xs, ys = [], []
    for g in geoms:
        for r in rings(g):
            for lo, la in r:
                x, y = merc(lo, la); xs.append(x); ys.append(y)
    a, b, c, d = min(xs), min(ys), max(xs), max(ys)
    bx, by, bw, bh = box
    s = min(bw / (c - a), bh / (d - b))
    ox, oy = bx + (bw - (c - a) * s) / 2, by + (bh - (d - b) * s) / 2
    def P(lo, la):
        x, y = merc(lo, la)
        return (ox + (x - a) * s) * SS, (oy + (d - y) * s) * SS
    return P

def outer(g):
    return [g["coordinates"][0]] if g["type"] == "Polygon" else [p[0] for p in g["coordinates"]]

def fill(dr, g, P, colour, outline=None, width=1):
    # exteriors only: whatever sits in a hole is its own feature, drawn later (see by_size)
    for r in outer(g):
        pts = [P(lo, la) for lo, la in r]
        if len(pts) >= 3: dr.polygon(pts, fill=colour, outline=outline, width=width)

def by_size(feats):
    """Largest first, so villages inside another's hole are drawn on top of it."""
    def span(f):
        xs = [x for r in outer(f["geometry"]) for x, _ in r]; ys = [y for r in outer(f["geometry"]) for _, y in r]
        return (max(xs) - min(xs)) * (max(ys) - min(ys))
    return sorted(feats, key=span, reverse=True)

def colour_regions(keys_of, P):
    """Neighbours never share a colour. Rasterise regions into ids (as the app does), link ids
    that touch or sit one pixel apart, then colour most-constrained first with the least-used
    free colour so the whole palette gets used."""
    keys = list(keys_of)
    R = 3                                              # raster at 1/3 of the drawn size
    ras = Image.new("I", (MAP_W * SS // R, H * SS // R), 0)
    rd = ImageDraw.Draw(ras)
    for n, k in enumerate(keys, 1):
        for g in keys_of[k]:
            for r in outer(g):
                pts = [(x / R, y / R) for x, y in (P(lo, la) for lo, la in r)]
                if len(pts) >= 3: rd.polygon(pts, fill=n)
    w, h = ras.size
    px = ras.load()
    nb = {k: set() for k in keys}
    for y in range(h - 2):
        for x in range(w - 2):
            a = px[x, y]
            if not a: continue
            for b in (px[x + 1, y] or px[x + 2, y], px[x, y + 1] or px[x, y + 2]):
                if b and b != a: nb[keys[a - 1]].add(keys[b - 1]); nb[keys[b - 1]].add(keys[a - 1])
    col, used = {}, [0] * len(PALETTE)
    while len(col) < len(keys):
        k = max((k for k in keys if k not in col),
                key=lambda k: (len({col[n] for n in nb[k] if n in col}), len(nb[k])))
        taken = {col[n] for n in nb[k] if n in col}
        c = min((c for c in range(len(PALETTE)) if c not in taken), key=lambda c: used[c], default=0)
        col[k] = c; used[c] += 1
    return {k: PALETTE[c] for k, c in col.items()}

def text_panel(dr, title, lines):
    x = (MAP_W + 56) * SS
    y = 150 * SS
    dr.text((x, y), "INDIA VILLAGES", font=font(22, 1), fill=ACCENT)
    y += 50 * SS
    size = 64 if len(title) <= 16 else 52 if len(title) <= 22 else 42
    for part in wrap(title, font(size, 1), (W - MAP_W - 100) * SS):
        dr.text((x, y), part, font=font(size, 1), fill=INK)
        y += int(size * 1.12) * SS
    y += 18 * SS
    for ln in lines:
        dr.text((x, y), ln, font=font(28), fill=MUTED)
        y += 42 * SS
    dr.text((x, (H - 70) * SS), "indianvillage.4080studio.com", font=font(24, 10), fill=INK)
    dr.text((x, (H - 40) * SS), "Data: Survey of India", font=font(20), fill=MUTED)

def wrap(text, f, maxw):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if f.getlength(t) <= maxw or not cur: cur = t
        else: out.append(cur); cur = w
    return out + [cur]

def canvas():
    im = Image.new("RGB", (W * SS, H * SS), BG)
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, MAP_W * SS, H * SS], fill=MAP_BG)
    return im, dr

def save(im, name):
    # 256 colours is plenty for flat fills and keeps each card small
    im = im.resize((W, H), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=256)
    im.save(os.path.join(OUT, name), optimize=True)

def main():
    os.makedirs(OUT, exist_ok=True)
    india = json.load(open(os.path.join(D, "india.geojson")))["features"]
    box = (30, 30, MAP_W - 60, H - 60)

    # India
    im, dr = canvas()
    P = projector([f["geometry"] for f in india], box)
    cols = colour_regions({f["properties"]["slug"]: [f["geometry"]] for f in india}, P)
    for f in india:
        p = f["properties"]
        fill(dr, f["geometry"], P, cols[p["slug"]] if p.get("villages") else NODATA, EDGE, SS)
    vill = sum(f["properties"].get("villages", 0) for f in india)
    have = sum(1 for f in india if f["properties"].get("villages"))
    text_panel(dr, "Every village boundary in India", [f"{vill:,} villages", f"{have} states and UTs"])
    save(im, "india.png"); print("india.png")

    # one per released state
    for f in india:
        p = f["properties"]
        if not p.get("villages"): continue
        fc = json.load(open(os.path.join(D, p["slug"] + ".geojson")))["features"]
        by_d = {}
        for v in fc: by_d.setdefault(v["properties"].get("d") or "", []).append(v["geometry"])
        im, dr = canvas()
        P = projector([v["geometry"] for v in fc], box)
        cols = colour_regions(by_d, P)
        edge = SS if len(fc) < 25000 else 0         # outlines only while villages stay visible
        for v in by_size(fc):
            fill(dr, v["geometry"], P, cols[v["properties"].get("d") or ""], EDGE if edge else None, edge or 1)
        text_panel(dr, p["name"], [f"{p['villages']:,} villages", f"{p['districts']} districts, {p['taluks']} taluks"])
        save(im, p["slug"] + ".png"); print(p["slug"] + ".png")
    size = sum(os.path.getsize(os.path.join(OUT, x)) for x in os.listdir(OUT))
    print(f"\n{len(os.listdir(OUT))} cards -> {OUT} ({size // 1024} KB)")

if __name__ == "__main__":
    main()
