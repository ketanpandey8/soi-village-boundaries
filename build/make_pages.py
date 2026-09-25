#!/usr/bin/env python3
"""Bordering villages, village page data and sitemaps.

Neighbours come from the full-detail boundaries: two villages border each other when they
share at least two surveyed points (a stretch of boundary, not just a corner). Survey of
India's boundaries meet exactly, so no tolerance is needed.

  dist/data/<state>.nb.json     {"v": [[i, ...], ...]}  neighbours of each village, as
                                indices into the display file's order (the app loads this
                                when a village is selected)
  dist/data/pages/lgd-<ddd>.json {lgd: [[state, name, district, taluk, area, category,
                                [[lgd, name], ...], detail file, index in it], ...]}  for the Worker's village pages,
                                split by the first three digits of the LGD code, small
                                enough for the Worker to parse per request
  dist/data/sitemaps/           index.xml + sitemap-<n>.xml, every state and village page

Reads the .packed.json files, so run after pack.py.
"""
import os, json, html
from collections import defaultdict

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "data")
SITE = "https://indianvillage.4080studio.com"
PER_SITEMAP = 50000                     # the sitemap protocol's limit

def points(ring):
    x = y = 0
    for k in range(0, len(ring), 2):
        x += ring[k]; y += ring[k + 1]
        yield x, y

def neighbours(slug, disp):
    """Neighbour index lists, aligned with the display file."""
    files = disp["meta"]["detail"]
    at, seen = {}, defaultdict(int)                       # (district, j) -> display index
    for i, p in enumerate(disp["p"]):
        d = p.get("d") or ""; at[(d, seen[d])] = i; seen[d] += 1
    owners = defaultdict(set)
    for d, fn in files.items():
        pk = json.load(open(os.path.join(D, slug, fn + ".packed.json")))
        for j, g in enumerate(pk["g"]):
            i = at[(d, j)]
            for poly in g:
                for r in poly:
                    for pt in points(r): owners[pt].add(i)
    shared = defaultdict(lambda: defaultdict(int))
    for s in owners.values():
        if 1 < len(s) < 8:                                # skip degenerate pile-ups
            for a in s:
                for b in s:
                    if a != b: shared[a][b] += 1
    return [sorted(b for b, c in shared[i].items() if c >= 2) for i in range(len(disp["p"]))]

def main():
    slugs = sorted(f[:-len(".packed.json")] for f in os.listdir(D) if f.endswith(".packed.json"))
    states = {s["slug"]: s["name"] for s in json.load(open(os.path.join(D, "states.json")))}
    pages, urls = defaultdict(dict), [f"{SITE}/"]
    for slug in slugs:
        disp = json.load(open(os.path.join(D, slug + ".packed.json")))
        nb = neighbours(slug, disp)
        json.dump({"v": nb}, open(os.path.join(D, slug + ".nb.json"), "w"), separators=(",", ":"))
        P = disp["p"]; cat_default = (disp.get("meta") or {}).get("catDefault")
        urls.append(f"{SITE}/{slug}")
        files = (disp.get("meta") or {}).get("detail") or {}
        seen = defaultdict(int)                      # position of each village in its district file
        counts = defaultdict(int)
        for p in P:
            if p.get("l"): counts[p["l"]] += 1
        for i, p in enumerate(P):
            d = p.get("d") or ""; j_in_d = seen[d]; seen[d] += 1
            l = p.get("l")
            if not l: continue
            row = [slug, p.get("n") or "", p.get("d") or "", p.get("s") or "", p.get("a"),
                   p.get("c", cat_default) or "",
                   [[P[j].get("l") or "", P[j].get("n") or ""] for j in nb[i]],
                   files.get(d, ""), j_in_d]
            pages["lgd-" + l[:3]].setdefault(l, []).append(row)
            if counts[l] == 1: urls.append(f"{SITE}/{slug}/{l}")   # a shared code can't name one page
        alone = sum(1 for x in nb if not x)
        print(f"{states.get(slug, slug):32} {len(P):>7} villages, {alone:>5} with no bordering village", flush=True)

    out = os.path.join(D, "pages"); os.makedirs(out, exist_ok=True)
    for f in os.listdir(out): os.remove(os.path.join(out, f))
    for key, doc in pages.items():
        json.dump(doc, open(os.path.join(out, key + ".json"), "w"), ensure_ascii=False, separators=(",", ":"))

    sm = os.path.join(D, "sitemaps"); os.makedirs(sm, exist_ok=True)
    for f in os.listdir(sm): os.remove(os.path.join(sm, f))
    n = 0
    for n, k in enumerate(range(0, len(urls), PER_SITEMAP), 1):
        with open(os.path.join(sm, f"sitemap-{n}.xml"), "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
            for u in urls[k:k + PER_SITEMAP]: f.write(f"<url><loc>{html.escape(u)}</loc></url>\n")
            f.write("</urlset>\n")
    with open(os.path.join(sm, "index.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for i in range(1, n + 1): f.write(f"<sitemap><loc>{SITE}/sitemap-{i}.xml</loc></sitemap>\n")
        f.write("</sitemapindex>\n")
    print(f"\n{len(pages)} page files, {len(urls):,} URLs in {n} sitemaps")

if __name__ == "__main__":
    main()
