#!/usr/bin/env python3
"""Build dist/data/india.geojson — one dissolved outline + stats per state.

Method: rasterize every village polygon into a fine grid, then trace the grid's
filled/empty boundary into closed rings. This is topology-independent (works even
when village polygons don't share exact edges, e.g. Gujarat / Rann of Kutch),
unlike edge-cancellation dissolve. Reads the already-simplified per-state GeoJSON
(dist/data/<slug>.geojson) so it's fast and needs no reprojection.

Optional arg = one slug (for testing).
"""
import os, sys, json
from collections import defaultdict
sys.setrecursionlimit(100000)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_geojson as mg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "dist", "data")
GRID = 850                      # target cells across the longer dimension

NAMES = {
 "andaman-nicobar-islands":"Andaman & Nicobar Islands","andhra-pradesh":"Andhra Pradesh",
 "bihar":"Bihar","chandigarh":"Chandigarh","chhattisgarh":"Chhattisgarh",
 "dadra-nagar-haveli-daman-diu":"Dadra & Nagar Haveli & Daman & Diu","delhi":"Delhi",
 "goa":"Goa","gujarat":"Gujarat","haryana":"Haryana","jharkhand":"Jharkhand",
 "karnataka":"Karnataka","kerala":"Kerala","lakshadweep":"Lakshadweep",
 "madhya-pradesh":"Madhya Pradesh","maharashtra":"Maharashtra","odisha":"Odisha",
 "puducherry":"Puducherry","punjab":"Punjab","rajasthan":"Rajasthan","sikkim":"Sikkim",
 "tamil-nadu":"Tamil Nadu","telangana":"Telangana","tripura":"Tripura",
 "uttar-pradesh":"Uttar Pradesh","uttarakhand":"Uttarakhand","west-bengal":"West Bengal",
}

def rings_of(geom):
    t = geom["type"]
    if t == "Polygon":      return list(geom["coordinates"])
    if t == "MultiPolygon": return [r for poly in geom["coordinates"] for r in poly]
    return []

def raster_outline(rings):
    xs = [x for r in rings for x, y in r]; ys = [y for r in rings for x, y in r]
    minx, maxx = max(66, min(xs)), min(99, max(xs))
    miny, maxy = max(6, min(ys)), min(38, max(ys))
    span = max(maxx-minx, maxy-miny) or 0.01
    cell = span/GRID
    W = int((maxx-minx)/cell)+4; H = int((maxy-miny)/cell)+4
    grid = bytearray(W*H)
    col = lambda x: int((x-minx)/cell)+1
    row = lambda y: int((y-miny)/cell)+1
    # scanline-fill each polygon ring
    for ring in rings:
        rys = [p[1] for p in ring]
        r0 = max(1, row(min(rys))); r1 = min(H-2, row(max(rys)))
        m = len(ring)
        for rr in range(r0, r1+1):
            yc = miny + (rr-1+0.5)*cell
            xin = []
            for i in range(m-1):
                x1, y1 = ring[i]; x2, y2 = ring[i+1]
                if (y1 <= yc < y2) or (y2 <= yc < y1):
                    xin.append(x1 + (yc-y1)/(y2-y1)*(x2-x1))
            xin.sort()
            base = rr*W
            for kk in range(0, len(xin)-1, 2):
                c0 = max(1, col(xin[kk])); c1 = min(W-2, col(xin[kk+1]))
                for cc in range(c0, c1+1): grid[base+cc] = 1
    # fill interior pinholes: flood the exterior from the border, then any empty
    # cell the flood never reached is an interior hole -> mark it filled (solid state)
    from collections import deque
    ext = bytearray(W*H); dq = deque()
    for c in range(W):
        for r in (0, H-1):
            i = r*W+c
            if not grid[i] and not ext[i]: ext[i] = 1; dq.append(i)
    for r in range(H):
        for c in (0, W-1):
            i = r*W+c
            if not grid[i] and not ext[i]: ext[i] = 1; dq.append(i)
    while dq:
        i = dq.popleft(); r, c = divmod(i, W)
        for j in ((i+1) if c < W-1 else -1, (i-1) if c > 0 else -1,
                  (i+W) if r < H-1 else -1, (i-W) if r > 0 else -1):
            if j >= 0 and not grid[j] and not ext[j]: ext[j] = 1; dq.append(j)
    for i in range(W*H):
        if not grid[i] and not ext[i]: grid[i] = 1
    # boundary edges between filled and empty cells (corner coords are integers)
    live = set(); adj = defaultdict(list)
    def edge(a, b):
        e = (a, b) if a <= b else (b, a)
        live.add(e); adj[a].append(b); adj[b].append(a)
    for rr in range(1, H-1):
        base = rr*W
        for cc in range(1, W-1):
            if not grid[base+cc]: continue
            if not grid[base+cc-1]:   edge((cc, rr),   (cc, rr+1))
            if not grid[base+cc+1]:   edge((cc+1, rr), (cc+1, rr+1))
            if not grid[base-W+cc]:   edge((cc, rr),   (cc+1, rr))
            if not grid[base+W+cc]:   edge((cc, rr+1), (cc+1, rr+1))
    # chain edges into closed rings (grid boundary is a clean manifold -> always closes)
    out = []
    while live:
        a, b = next(iter(live)); live.discard((a, b))
        ring = [a, b]; cur, start = b, a
        while cur != start:
            nxt = None
            for n in adj[cur]:
                e = (cur, n) if cur <= n else (n, cur)
                if e in live: nxt = n; e0 = e; break
            if nxt is None: break
            live.discard(e0); ring.append(nxt); cur = nxt
        if len(ring) >= 4:
            ll = [(round(minx+(c-1)*cell, 5), round(miny+(r-1)*cell, 5)) for c, r in ring]
            if ll[0] != ll[-1]: ll.append(ll[0])
            ll = mg.dp(ll, cell*1.4)               # smooth the blocky grid boundary
            if len(ll) >= 4: out.append(ll)
    return out, cell

def build_state(gj_path):
    fc = json.load(open(gj_path))
    feats = fc["features"]
    rings = [r for f in feats for r in rings_of(f["geometry"])]
    outs, cell = raster_outline(rings)
    # keep only rings with meaningful area (drops single-cell specks)
    outs = [r for r in outs if abs(mg.signed_area(r)) > (cell*cell)*4]
    polys, cur = [], None
    for r in sorted(outs, key=lambda r: -abs(mg.signed_area(r))):
        if mg.signed_area(r) < 0:
            if cur: polys.append(cur)
            cur = [r]
        else:
            if cur: cur.append(r)
            else: cur = [r]
    if cur: polys.append(cur)
    geom = ({"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1
            else {"type": "MultiPolygon", "coordinates": polys})
    dists = {f["properties"].get("d","") for f in feats if f["properties"].get("d")}
    taluks = {f["properties"].get("s","") for f in feats if f["properties"].get("s")}
    return geom, len(feats), len(dists), len(taluks)

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    files = sorted(f for f in os.listdir(OUT)
                   if f.endswith(".geojson") and f not in ("india.geojson", "states.json"))
    feats = []
    for fn in files:
        slug = fn[:-8]
        if only and slug != only: continue
        geom, nv, nd, nt = build_state(os.path.join(OUT, fn))
        feats.append({"type":"Feature",
                      "properties":{"slug":slug, "name":NAMES.get(slug, slug.replace("-"," ").title()),
                                    "villages":nv, "districts":nd, "taluks":nt},
                      "geometry":geom})
        print(f"{NAMES.get(slug,slug):32} {nv:6d} villages  {len(json.dumps(geom))//1024:4d} KB  {len(rings_of(geom))} rings", flush=True)
    out = os.path.join(OUT, "india.geojson")
    json.dump({"type":"FeatureCollection","features":feats}, open(out,"w"), separators=(",",":"))
    print(f"\n{len(feats)} states -> india.geojson ({os.path.getsize(out)//1024} KB)")

if __name__ == "__main__":
    main()
