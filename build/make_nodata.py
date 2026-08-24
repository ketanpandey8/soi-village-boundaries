#!/usr/bin/env python3
"""Extract simplified outlines for the states/UTs Survey of India hasn't released,
so the overview map can show a complete India silhouette (rendered as "no data").

Source: GADM India state boundaries (third-party). NOTE: the border depiction of
Jammu & Kashmir, Ladakh and Arunachal Pradesh is GADM's, which may not match
India's official Survey of India depiction. Replace SRC with an official-boundary
file and re-run before public deployment if that matters for your use.

Reads SRC (a GADM-style states GeoJSON with NAME_1) and writes
build/nodata-states.geojson. make_india.py appends these into india.geojson.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_geojson as mg

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    "/private/tmp/claude-501/-Users-ketanp-Documents-All-things-code-surveyofindia",
    "18bb0205-a72a-4a0c-9e32-ad14ad7841bb/scratchpad/india_states_src.geojson")
OUT = os.path.join(HERE, "nodata-states.geojson")

# GADM NAME_1 -> (slug, display name).  J&K here includes Ladakh (older admin split).
WANT = {
    "arunachal pradesh": ("arunachal-pradesh", "Arunachal Pradesh"),
    "assam":             ("assam", "Assam"),
    "himachal pradesh":  ("himachal-pradesh", "Himachal Pradesh"),
    "jammu and kashmir": ("jammu-kashmir", "Jammu & Kashmir / Ladakh"),
    "manipur":           ("manipur", "Manipur"),
    "meghalaya":         ("meghalaya", "Meghalaya"),
    "mizoram":           ("mizoram", "Mizoram"),
    "nagaland":          ("nagaland", "Nagaland"),
}
TOL = 0.008   # ~0.9 km: coarse outline, matches the overview scale

def simplify_geom(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    out = []
    for poly in polys:
        rings = []
        for ring in poly:
            ll = [(round(x, 4), round(y, 4)) for x, y in ring]
            ll = mg.dp(ll, TOL)
            if len(ll) >= 4:
                if ll[0] != ll[-1]: ll.append(ll[0])
                rings.append(ll)
        if rings and abs(mg.signed_area(rings[0])) > 0.0008:   # drop tiny specks
            out.append(rings)
    return {"type": "Polygon", "coordinates": out[0]} if len(out) == 1 \
        else {"type": "MultiPolygon", "coordinates": out}

def main():
    fc = json.load(open(SRC))
    feats = []
    for f in fc["features"]:
        key = f["properties"]["NAME_1"].lower()
        if key not in WANT: continue
        slug, name = WANT[key]
        geom = simplify_geom(f["geometry"])
        feats.append({"type": "Feature",
                      "properties": {"slug": slug, "name": name,
                                     "villages": 0, "districts": 0, "taluks": 0, "nodata": True},
                      "geometry": geom})
        print(f"{name:28} {len(json.dumps(geom))//1024} KB")
    feats.sort(key=lambda x: x["properties"]["name"])
    json.dump({"type": "FeatureCollection", "features": feats}, open(OUT, "w"), separators=(",", ":"))
    print(f"\n{len(feats)} no-data states -> {OUT} ({os.path.getsize(OUT)//1024} KB)")

if __name__ == "__main__":
    main()
