#!/usr/bin/env python3
"""Convert all 27 Survey of India state zips into dist/data/:
  <slug>.geojson            simplified display file with all attributes
  <slug>/<district>.geojson full-detail boundaries (every source vertex), loaded on zoom
Also writes dist/data/states.json (the state picker manifest).
"""
import os, re, zipfile, tempfile, shutil, json, sys
sys.setrecursionlimit(100000)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_geojson as mg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW  = os.path.join(ROOT, "data", "raw")
OUT  = os.path.join(ROOT, "dist", "data")
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
            # Display tolerance scales with the state's width: a state fills ~1000 px at the
            # starting zoom, so this stays under ~0.6 px until about 4x zoom. The app swaps in
            # the full-detail district files before simplification could become visible.
            inv = mg.make_inverse(open(shp[:-4] + ".prj").read())
            tol = max(0.00005, mg.shp_lon_span(shp, inv) * 0.00015)
            ddir = os.path.join(OUT, slug)
            if os.path.isdir(ddir): shutil.rmtree(ddir)
            n = mg.convert_split(shp, outp, ddir, tol)
        sz = os.path.getsize(outp)
        full = sum(os.path.getsize(os.path.join(ddir, f)) for f in os.listdir(ddir))
        manifest.append({"slug": slug, "name": name, "count": n, "kb": round(sz/1024)})
        print(f"{name:34} {n:6d} villages  display {sz//1024:6d} KB  "
              f"full {full//1048576:4d} MB in {len(os.listdir(ddir))} districts  tol={tol:.5f}", flush=True)
    manifest.sort(key=lambda m: m["name"])
    json.dump(manifest, open(os.path.join(OUT, "states.json"), "w"))
    tot = sum(m["count"] for m in manifest)
    print(f"\n{len(manifest)} states, {tot:,} villages total -> dist/data/")

if __name__ == "__main__":
    main()
