#!/usr/bin/env python3
"""Convert all 27 Survey of India state zips -> per-state GeoJSON in dist/data/.
Adaptive simplification keeps each file under a size cap so the site loads fast.
Also writes dist/data/states.json (the state picker manifest).
"""
import os, re, zipfile, tempfile, shutil, json, sys
sys.setrecursionlimit(100000)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_geojson as mg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW  = os.path.join(ROOT, "data", "raw")
OUT  = os.path.join(ROOT, "dist", "data")
CAP  = 40 * 1024 * 1024   # per-file cap — data is served from R2 (no 25 MiB asset limit),
                          # so we can keep real village shapes at good resolution
os.makedirs(OUT, exist_ok=True)

def pretty(fn):
    name = fn[:-4].replace("_", " ").replace("&", " & ")
    name = re.sub(r"\s+", " ", name).strip().title()
    fix = {"Andaman & Nicobar Islands":"Andaman & Nicobar Islands",
           "Nct Of Delhi":"Delhi", "Punducherry":"Puducherry",
           "Lakshyadweep":"Lakshadweep", "Tamilnadu":"Tamil Nadu",
           "Dadra Nagar Haveli & Daman Diu":"Dadra & Nagar Haveli & Daman & Diu"}
    return fix.get(name, name)

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

def main():
    zips = sorted(f for f in os.listdir(RAW) if f.lower().endswith(".zip"))
    manifest = []
    for zf in zips:
        name = pretty(zf); slug = slugify(name)
        outp = os.path.join(OUT, slug + ".geojson")
        with tempfile.TemporaryDirectory() as td:
            with zipfile.ZipFile(os.path.join(RAW, zf)) as z:
                z.extractall(td)
            shp = next((os.path.join(dp, f) for dp, _, fs in os.walk(td)
                        for f in fs if f.lower().endswith(".shp")), None)
            if not shp:
                print(f"!! no .shp in {zf}"); continue
            tol, prec = 0.0002, 5
            for _ in range(12):                    # tighten until under cap
                n = mg.convert(shp, outp, tol, prec)
                sz = os.path.getsize(outp)
                if sz <= CAP: break
                if tol > 0.01 and prec > 4: prec = 4   # last-resort precision drop
                tol *= 1.6
        manifest.append({"slug": slug, "name": name, "count": n,
                         "kb": round(sz/1024)})
        print(f"{name:32} {n:6d} villages  {sz//1024:6d} KB  tol={tol:.5f}", flush=True)
    manifest.sort(key=lambda m: m["name"])
    json.dump(manifest, open(os.path.join(OUT, "states.json"), "w"))
    tot = sum(m["count"] for m in manifest)
    print(f"\n{len(manifest)} states, {tot:,} villages total -> dist/data/")

if __name__ == "__main__":
    main()
