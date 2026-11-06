#!/usr/bin/env python3
"""Vector tiles for one state (prototype for the ?map=gl renderer): dist/data/tiles/<slug>.pmtiles,
uploaded to R2 by ./sync-r2.sh and served tile by tile by the Worker (/tiles/<slug>/<z>/<x>/<y>.pbf)

Reads the state's zip from data/raw (every source vertex, as in the full-detail district
files) and writes one PMTiles archive with four layers, built by tippecanoe:

  villages   every village polygon at full detail, zoom 9+ (village labels 11+), with the app's properties
             (n name, d district, s taluk, l LGD, c category, a area) and ci, the district's
             palette index. The feature id is the village's index in <slug>.packed.json, so
             population, neighbours and search results line up with the existing files.
  districts  one dissolved outline per district for zooms 5-8 (fills only), so a zoomed-out
             view loads ~75 shapes instead of every village
  lines      district (k=d) and taluk (k=t) boundaries from <slug>.lines.json
  labels     one point per village (k=v) and per district (k=d) for map labels

District colours use the app's palette and the same rule (neighbouring districts differ,
picking the most different colour), so the tiles look like the current map.

  python3 build/make_tiles.py uttar-pradesh [path/to/data/raw] [--meta-only]

Also writes dist/data/tiles/<slug>.json: {"ci": {district: palette index}, "bbox": [w, s, e, n]},
which the app reads before the tiles so its district list matches the map's colours, and
dist/data/tiles/<slug>.attrs.json, the village list without shapes (see attrs()).
Needs tippecanoe (brew install tippecanoe) and dist/data/<slug>.lines.json, or fetches it.
"""
import os, re, sys, json, math, zipfile, tempfile, subprocess, urllib.request
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_geojson as mg
from build_all import pretty, slugify

ROOT = os.path.dirname(HERE)
PALETTE = ["#6ba368","#e0a13c","#d9663f","#3d94a6","#8a6fb0","#c0577f","#4d9670",
           "#c99a3c","#5b8def","#d17c4a","#57a99a","#b0563f","#7aa03f","#9a6ac0","#3f9fb0","#c77d9e"]
RGB = [tuple(int(h[i:i+2], 16) for i in (1, 3, 5)) for h in PALETTE]
LIVE = "https://indianvillage.4080studio.com"

def colour(names, nb):
    """DSATUR, as colourDistricts() in the app: most-constrained first, the palette colour
    most unlike its neighbours' (up to 'clearly different'), then the least used."""
    N, col, used = len(names), [-1] * len(names), [0] * len(PALETTE)
    dist = lambda a, b: sum((x - y) ** 2 for x, y in zip(RGB[a], RGB[b]))
    for _ in range(N):
        v = max((u for u in range(N) if col[u] < 0),
                key=lambda u: (len({col[w] for w in nb[u] if col[w] >= 0}), len(nb[u])))
        taken = [col[w] for w in nb[v] if col[w] >= 0]
        col[v] = max((c for c in range(len(PALETTE)) if c not in taken),
                     key=lambda c: min(min((dist(c, t) for t in taken), default=10**9), 15000) - used[c] * 600)
        used[col[v]] += 1
    return dict(zip(names, col))

def dissolve(rings):
    """Outline of a set of village rings: each edge shared by two villages appears once in each
    direction and cancels; the edges left chain into the outline, keeping the source's ring
    direction, so outer rings and holes can be told apart by their signed area. Edges are
    counted, not just marked, so duplicated edges in the source can't leave a ring open."""
    out = defaultdict(lambda: defaultdict(int))
    for r in rings:
        for a, b in zip(r, r[1:]):
            if a == b: continue
            back = out.get(b)
            if back and back.get(a):                       # the reverse edge cancels this one
                back[a] -= 1
                if not back[a]: del back[a]
            else: out[a][b] += 1
    nxt = defaultdict(list)
    for a, bs in out.items():
        for b, n in bs.items(): nxt[a].extend([b] * n)
    res = []
    while nxt:
        a = next(iter(nxt)); ring = [a]; cur = a
        while cur in nxt:                                  # every vertex has as many edges out as in,
            b = nxt[cur].pop()                             # so this walk always comes back to a
            if not nxt[cur]: del nxt[cur]
            ring.append(b); cur = b
            if b == a: break
        if len(ring) >= 4 and ring[0] == ring[-1]: res.append(ring)
    return res

def area(r):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(r, r[1:])) / 2

def inside(p, r):
    x, y, c = p[0], p[1], False
    for (x0, y0), (x1, y1) in zip(r, r[1:]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0): c = not c
    return c

def polygons(rings):
    """Rings from dissolve() as GeoJSON polygons: holes go in the outer ring that holds them."""
    if not rings: return None
    sign = 1 if area(max(rings, key=lambda r: abs(area(r)))) > 0 else -1   # the biggest ring is outer
    outer = [[r] for r in rings if area(r) * sign > 0]
    for h in (r for r in rings if area(r) * sign <= 0):
        home = next((o for o in sorted(outer, key=lambda o: abs(area(o[0]))) if inside(h[0], o[0])), None)
        if home: home.append(h)
    return {"type": "MultiPolygon", "coordinates": outer}

def ring_centroid(r):
    a = cx = cy = 0
    for (x0, y0), (x1, y1) in zip(r, r[1:]):
        k = x0 * y1 - x1 * y0; a += k; cx += (x0 + x1) * k; cy += (y0 + y1) * k
    return (cx / (3 * a), cy / (3 * a), abs(a) / 2) if a else (r[0][0], r[0][1], 0)

def attrs(slug, n_feats):
    """dist/data/tiles/<slug>.attrs.json: what the sheet needs from <slug>.packed.json without the
    shapes (names, codes, areas, and each village's middle and size for zooming to it), so the
    list and search are ready about as soon as the tiles. Columns, not objects, to stay small:
      D, S   district and taluk names; d, s index them (-1: not in the source)
      n, l, a, c   name, LGD code, area, category (c only where set, as {index: value});
             null where the source has no value
      l      whole-number codes as the difference from the previous whole-number code,
             anything else as the string itself
      x, y   bounding-box middle in 1/q degrees, as the difference from the previous village
      z      bounding-box size: round(4 * log2(size in 1/q degrees))"""
    pp = os.path.join(ROOT, "dist", "data", slug + ".packed.json")
    if os.path.exists(pp): P = json.load(open(pp))
    else:
        v = re.search(r'const DATA_V="(\d+)"', open(os.path.join(HERE, "app.html")).read()).group(1)
        P = json.load(urllib.request.urlopen(urllib.request.Request(
            f"{LIVE}/data/{slug}.packed.json?v={v}", headers={"User-Agent": "Mozilla/5.0 make_tiles"})))
    props = P["p"]
    if len(props) != n_feats: sys.exit(f"{slug}.packed.json has {len(props)} villages, the zip {n_feats}: ids would not line up")
    Q = 10000; f = P["q"] / Q
    D = sorted({p["d"] for p in props if p.get("d")}); S = sorted({p["s"] for p in props if p.get("s")})
    Di, Si = {n: i for i, n in enumerate(D)}, {n: i for i, n in enumerate(S)}
    out = {"meta": P["meta"], "q": Q, "D": D, "S": S, "n": [], "d": [], "s": [], "l": [], "a": [], "c": {}, "x": [], "y": [], "z": []}
    lp = px = py = 0
    for i, (p, g) in enumerate(zip(props, P["g"])):
        out["n"].append(p.get("n")); out["d"].append(Di.get(p.get("d"), -1)); out["s"].append(Si.get(p.get("s"), -1))
        l = p.get("l")
        if l and l.isdigit() and str(int(l)) == l: out["l"].append(int(l) - lp); lp = int(l)
        else: out["l"].append(l)
        out["a"].append(p.get("a"))
        if p.get("c"): out["c"][i] = p["c"]
        a = b = float("inf"); c = e = float("-inf")
        for poly in g:                               # outer rings: start point plus differences
            r, x, y = poly[0], 0, 0
            for j in range(0, len(r), 2):
                x += r[j]; y += r[j + 1]
                a, c, b, e = min(a, x), max(c, x), min(b, y), max(e, y)
        cx, cy = round((a + c) / 2 / f), round((b + e) / 2 / f)
        out["x"].append(cx - px); out["y"].append(cy - py); px, py = cx, cy
        out["z"].append(round(4 * math.log2(max(c - a, e - b, f) / f)))
    dst = os.path.join(ROOT, "dist", "data", "tiles", slug + ".attrs.json")
    json.dump(out, open(dst, "w"), separators=(",", ":"), ensure_ascii=False)
    print(f"-> {dst}  {os.path.getsize(dst) / 1048576:.1f} MB")

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    slug, meta_only = args[0], "--meta-only" in sys.argv
    raw = args[1] if len(args) > 1 else os.path.join(ROOT, "data", "raw")
    zf = next(f for f in os.listdir(raw) if f.lower().endswith(".zip") and slugify(pretty(f)) == slug)
    out = os.path.join(ROOT, "dist", "data", "tiles"); os.makedirs(out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="tiles-")
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(os.path.join(raw, zf)) as z: z.extractall(td)
        shp = next(os.path.join(dp, f) for dp, _, fs in os.walk(td) for f in fs if f.lower().endswith(".shp"))
        inv = mg.make_inverse(open(shp[:-4] + ".prj").read())
        shapes, recs = mg.read_shp(shp), mg.read_dbf(shp[:-4] + ".dbf")
        feats = []                                  # same order and skips as convert_split
        for rings_xy, rec in zip(shapes, recs):
            if not rings_xy: continue
            rings = []
            for ring in rings_xy:
                full = [(round(lo, 6), round(la, 6)) for lo, la in (inv(x, y) for x, y in ring)]
                if len(full) < 4: continue
                if full[0] != full[-1]: full.append(full[0])
                rings.append(full)
            if rings: feats.append((mg._props(rec), rings))
    print(f"{len(feats):,} villages read", flush=True)

    # district neighbours: a vertex shared by villages of two districts (sampled by a hash of
    # the coordinate, so both sides keep the same vertices)
    owner, nb = {}, defaultdict(set)
    for props, rings in feats:
        d = props["d"] or ""
        for r in rings:
            for p in r:
                if hash(p) % 6: continue
                o = owner.setdefault(p, d)
                if o != d: nb[o].add(d); nb[d].add(o)
    names = sorted({p["d"] or "" for p, _ in feats})
    ix = {n: i for i, n in enumerate(names)}
    ci = colour(names, [{ix[w] for w in nb[n]} for n in names])
    xs = [p[0] for _, rings in feats for r in rings for p in r[::25]]; ys = [p[1] for _, rings in feats for r in rings for p in r[::25]]
    json.dump({"ci": ci, "bbox": [min(xs), min(ys), max(xs), max(ys)]}, open(os.path.join(out, slug + ".json"), "w"), separators=(",", ":"))
    attrs(slug, len(feats))
    if meta_only: return

    vil, lab, dst_f = (open(os.path.join(work, n), "w") for n in ("villages.geojsonl", "labels.geojsonl", "districts.geojsonl"))
    dsum = defaultdict(lambda: [0, 0, 0])
    for i, (props, rings) in enumerate(feats):
        d = props["d"] or ""
        p = {k: v for k, v in props.items() if v not in (None, "")}
        p["ci"] = ci[d]
        g = mg._polys(rings)
        vil.write(json.dumps({"type": "Feature", "id": i, "tippecanoe": {"minzoom": 9}, "properties": p, "geometry": g}, separators=(",", ":")) + "\n")
        x, y, a = max((ring_centroid(r) for r in rings), key=lambda t: t[2])
        if props.get("n"):
            lab.write(json.dumps({"type": "Feature", "id": i, "tippecanoe": {"minzoom": 11}, "properties": {"k": "v", "n": props["n"], "a": props.get("a") or 0},
                                  "geometry": {"type": "Point", "coordinates": [round(x, 5), round(y, 5)]}}, separators=(",", ":")) + "\n")
        s = dsum[d]; s[0] += x * a; s[1] += y * a; s[2] += a
    for d, (sx, sy, a) in dsum.items():
        if d and a:
            lab.write(json.dumps({"type": "Feature", "properties": {"k": "d", "n": d.title()},
                                  "geometry": {"type": "Point", "coordinates": [round(sx / a, 5), round(sy / a, 5)]}}) + "\n")
    # one dissolved outline per district (each district on its own keeps memory down)
    byd = defaultdict(list)
    for props, rings in feats: byd[props["d"] or ""].append(rings)
    for d, vs in byd.items():
        g = polygons(dissolve([r for rings in vs for r in rings]))
        if g: dst_f.write(json.dumps({"type": "Feature", "tippecanoe": {"maxzoom": 8}, "properties": {"d": d, "ci": ci[d]}, "geometry": g}, separators=(",", ":")) + "\n")
    vil.close(); lab.close(); dst_f.close()

    # boundary lines, from the packed lines file (the same lines the app draws)
    lp = os.path.join(ROOT, "dist", "data", slug + ".lines.json")
    L = json.load(open(lp)) if os.path.exists(lp) else json.load(urllib.request.urlopen(
        urllib.request.Request(f"{LIVE}/data/{slug}.lines.json?v=6", headers={"User-Agent": "Mozilla/5.0 make_tiles"})))
    with open(os.path.join(work, "lines.geojsonl"), "w") as f:
        for k in ("d", "t"):
            for ln in L[k]:
                x, y, pts = ln[0], ln[1], [[ln[0] / L["q"], ln[1] / L["q"]]]
                for j in range(2, len(ln), 2):
                    x += ln[j]; y += ln[j + 1]; pts.append([x / L["q"], y / L["q"]])
                f.write(json.dumps({"type": "Feature", "properties": {"k": k}, "geometry": {"type": "LineString", "coordinates": pts}}) + "\n")

    dst = os.path.join(out, slug + ".pmtiles")
    cmd = ["tippecanoe", "-o", dst, "--force", "-n", pretty(zf), "-Z5", "-z14",
           "-L", json.dumps({"layer": "villages", "file": os.path.join(work, "villages.geojsonl")}),
           "-L", json.dumps({"layer": "districts", "file": os.path.join(work, "districts.geojsonl")}),
           "-L", json.dumps({"layer": "lines", "file": os.path.join(work, "lines.geojsonl")}),
           "-L", json.dumps({"layer": "labels", "file": os.path.join(work, "labels.geojsonl")}),
           # full detail at the top zoom; shared borders simplify the same way on both sides
           "--detect-shared-borders", "--no-tiny-polygon-reduction",
           # low zooms: merge each district's villages into one fill
           "--coalesce", "--reorder", "--hilbert",
           "-y", "n", "-y", "d", "-y", "s", "-y", "l", "-y", "c", "-y", "a", "-y", "ci", "-y", "k",
           # never drop a village to fit a tile: a dropped polygon is a hole in the map
           "--no-feature-limit", "--no-tile-size-limit",
           # keep every label point at every zoom (the style decides which show), and no progress spam
           "-r1", "--quiet"]
    subprocess.run(cmd, check=True)
    print(f"-> {dst}  {os.path.getsize(dst) / 1048576:.1f} MB")

if __name__ == "__main__":
    main()
