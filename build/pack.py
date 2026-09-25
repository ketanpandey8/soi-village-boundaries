#!/usr/bin/env python3
"""Pack the village GeoJSON into the smaller files the app downloads.

For every dist/data/<state>.geojson and dist/data/<state>/<district>.geojson, writes a
.packed.json beside it. Coordinates become whole numbers (degrees x q, where q is 1e5 for
the display files and 1e6 for full detail, the precision they were rounded to), and each
ring stores its first point followed by the difference to each next point. Nothing is lost:
decoding gives back exactly the rounded source coordinates, which this script checks.

  {"q": 1000000, "meta": {...}, "p": [properties, ...],
   "g": [[polygon, ...], ...]}      polygon = [ring, ...], ring = [x0, y0, dx1, dy1, ...]

A feature with one polygon decodes to a Polygon, otherwise a MultiPolygon. UP's display
file goes from 37 MB to about 21 MB (8.1 to 6.4 MB compressed), and the app has less to parse.

Run after build_all.py. The app reads only the .packed.json files.
"""
import os, sys, json

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "data")

def polys_of(g):
    return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]

def precision(feats):
    """1e5 if every coordinate has at most 5 decimals, else 1e6 (the source rounding)."""
    for f in feats:
        for p in polys_of(f["geometry"]):
            for r in p:
                for lo, la in r:
                    if abs(round(lo, 5) - lo) > 1e-9 or abs(round(la, 5) - la) > 1e-9: return 1000000
    return 100000

def pack(path):
    fc = json.load(open(path))
    feats = fc["features"]
    q = precision(feats)
    g = []
    for f in feats:
        out = []
        for p in polys_of(f["geometry"]):
            rp = []
            for r in p:
                x0 = y0 = 0; a = []
                for lo, la in r:
                    x, y = round(lo * q), round(la * q)
                    a += [x - x0, y - y0]; x0, y0 = x, y
                rp.append(a)
            out.append(rp)
        g.append(out)
    doc = {"q": q, "p": [f["properties"] for f in feats], "g": g}
    if "meta" in fc: doc["meta"] = fc["meta"]
    out = path[:-len(".geojson")] + ".packed.json"
    json.dump(doc, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
    check(feats, doc)
    return os.path.getsize(path), os.path.getsize(out)

def check(feats, doc):
    q = doc["q"]
    for f, gp in zip(feats, doc["g"]):
        for p, pp in zip(polys_of(f["geometry"]), gp):
            for r, rr in zip(p, pp):
                x = y = 0
                for k, (lo, la) in enumerate(r):
                    x += rr[2 * k]; y += rr[2 * k + 1]
                    if abs(x / q - lo) > 0.5 / q or abs(y / q - la) > 0.5 / q:
                        sys.exit(f"lossy pack: {lo},{la} -> {x / q},{y / q}")

def main():
    files = []
    for f in sorted(os.listdir(D)):
        p = os.path.join(D, f)
        if f.endswith(".geojson") and f != "india.geojson": files.append(p)
        elif os.path.isdir(p) and f not in ("search", "find", "pages", "sitemaps"):
            files += [os.path.join(p, x) for x in sorted(os.listdir(p)) if x.endswith(".geojson")]
    a = b = 0
    for i, p in enumerate(files, 1):
        s0, s1 = pack(p); a += s0; b += s1
        if p.count(os.sep) == D.count(os.sep) + 1:
            print(f"{os.path.relpath(p, D):40} {s0 / 1e6:7.1f} MB -> {s1 / 1e6:6.1f} MB", flush=True)
    print(f"\n{len(files)} files: {a / 1e9:.2f} GB -> {b / 1e9:.2f} GB")

if __name__ == "__main__":
    main()
