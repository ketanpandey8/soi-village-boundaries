#!/usr/bin/env python3
"""Taluk and district boundary lines, built from the village boundaries themselves.

An edge of a village's full-detail boundary is a taluk (or district) boundary when the
village on the other side of it is in a different taluk (or district). Using the villages'
own edges means the lines sit exactly on the village boundaries the map draws, and follow
the same taluk and district names the app shows. (Survey of India's separate district and
sub-district layers come from a different survey and don't line up with the village edges.)

  dist/data/<state>.lines.json  {"q": 100000, "d": [line, ...], "t": [line, ...]}
                                d = district boundaries, t = taluk boundaries that aren't
                                also district boundaries; line = [x0, y0, dx1, dy1, ...] as in
                                the packed files (pack.py), simplified to a quarter of the
                                display file's tolerance so they stay on the village edges

Edges where the name on either side is missing from the source are left out, rather than
drawing a boundary around "no taluk". Reads the .packed.json files; run after pack.py.
"""
import os, sys, json
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_geojson as mg

D = os.path.join(os.path.dirname(HERE), "dist", "data")

def rings_of(pk_geom):
    for poly in pk_geom:
        for r in poly:
            pts, x, y = [], 0, 0
            for k in range(0, len(r), 2):
                x += r[k]; y += r[k + 1]; pts.append((x, y))
            yield pts

def chain(edges):
    """Join undirected edges (point pairs) into polylines."""
    adj = defaultdict(list)
    for a, b in edges: adj[a].append(b); adj[b].append(a)
    used, lines = set(), []
    def walk(start, nxt):
        line = [start, nxt]; used.add(frozenset((start, nxt))); cur, prev = nxt, start
        while len(adj[cur]) == 2:                    # carry on through plain points; stop at junctions
            n = adj[cur][0] if adj[cur][1] == prev else adj[cur][1]
            e = frozenset((cur, n))
            if e in used: break
            used.add(e); line.append(n); prev, cur = cur, n
        return line
    for p in adj:                                    # start at ends and junctions first
        if len(adj[p]) != 2:
            for n in adj[p]:
                if frozenset((p, n)) not in used: lines.append(walk(p, n))
    for p in adj:                                    # what's left are closed loops
        for n in adj[p]:
            if frozenset((p, n)) not in used: lines.append(walk(p, n))
    return lines

def encode(line, q_in, q_out, tol):
    pts = [(x / q_in, y / q_in) for x, y in line]
    pts = mg.dp(pts, tol) if len(pts) > 2 else pts
    out, x0, y0 = [], 0, 0
    for lo, la in pts:
        x, y = round(lo * q_out), round(la * q_out)
        out += [x - x0, y - y0]; x0, y0 = x, y
    return out

def build(slug):
    disp = json.load(open(os.path.join(D, slug + ".packed.json")))
    meta = disp.get("meta") or {}
    files, tol = meta.get("detail") or {}, (meta.get("dispTol") or 0.0002) / 4
    P = disp["p"]
    at, seen = {}, defaultdict(int)
    for i, p in enumerate(P):
        d = p.get("d") or ""; at[(d, seen[d])] = i; seen[d] += 1
    rings, q = {}, None                              # village index -> list of point rings
    owners = defaultdict(set)
    for d, fn in files.items():
        pk = json.load(open(os.path.join(D, slug, fn + ".packed.json")))
        q = pk["q"]
        for j, g in enumerate(pk["g"]):
            i = at[(d, j)]
            rs = list(rings_of(g)); rings[i] = rs
            for r in rs:
                for pt in r: owners[pt].add(i)
    dist_e, tal_e = set(), set()
    for i, rs in rings.items():
        pi = P[i]
        for r in rs:
            for a, b in zip(r, r[1:]):
                # checked from both villages' sides (the sets drop repeats): the other village may
                # have an extra point along this edge, so only this side sees it whole
                for o in (owners[a] & owners[b]) - {i}:
                    po = P[o]
                    e = (a, b) if a < b else (b, a)
                    da, db = pi.get("d") or "", po.get("d") or ""
                    ta, tb = pi.get("s") or "", po.get("s") or ""
                    if da and db and da != db: dist_e.add(e)
                    elif ta and tb and ta != tb: tal_e.add(e)
    out = {"q": 100000,
           "d": [encode(l, q, 100000, tol) for l in chain(dist_e)],
           "t": [encode(l, q, 100000, tol) for l in chain(tal_e - dist_e)]}
    path = os.path.join(D, slug + ".lines.json")
    json.dump(out, open(path, "w"), separators=(",", ":"))
    return len(out["d"]), len(out["t"]), os.path.getsize(path)

def main():
    only = sys.argv[1:]
    slugs = only or sorted(f[:-len(".packed.json")] for f in os.listdir(D) if f.endswith(".packed.json"))
    for slug in slugs:
        nd, nt, size = build(slug)
        print(f"{slug:32} {nd:>5} district lines, {nt:>6} taluk lines, {size / 1024:>7.0f} KB", flush=True)

if __name__ == "__main__":
    main()
