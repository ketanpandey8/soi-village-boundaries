#!/usr/bin/env python3
"""Outlines for the states/UTs whose village data Survey of India hasn't released, so the
overview map shows all of India with those drawn as "no data".

Source: Survey of India's own State Boundary shapefile, part of the Administrative Boundary
Database (https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-,
file "State_District_Subdistrict_PAN INDIA.rar", free under the National Geospatial Policy
2022). Its borders are India's official ones, including Jammu & Kashmir, Ladakh and
Arunachal Pradesh.

    python3 build/make_nodata.py            # reads data/raw/State_District_Subdistrict_PAN_INDIA.rar
    python3 build/make_nodata.py path/to/State\\ Boundary.shp

Writes build/nodata-states.geojson; make_india.py appends it to india.geojson.
"""
import os, sys, json, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_geojson as mg

RAR = os.path.join(HERE, "..", "data", "raw", "State_District_Subdistrict_PAN_INDIA.rar")
INNER = "State_District_Subdistrict_PAN INDIA/State Boundary"
TMP = os.path.join(HERE, "tmp", "soi")
OUT = os.path.join(HERE, "nodata-states.geojson")

# SoI STATE value -> (slug, display name), for states with no village data yet
WANT = {
    "ARUNACHAL PRADESH": ("arunachal-pradesh", "Arunachal Pradesh"),
    "ASSAM":             ("assam", "Assam"),
    "HIMACHAL PRADESH":  ("himachal-pradesh", "Himachal Pradesh"),
    "JAMMU AND KASHMIR": ("jammu-kashmir", "Jammu & Kashmir"),
    "LADAKH":            ("ladakh", "Ladakh"),
    "MANIPUR":           ("manipur", "Manipur"),
    "MEGHALAYA":         ("meghalaya", "Meghalaya"),
    "MIZORAM":           ("mizoram", "Mizoram"),
    "NAGALAND":          ("nagaland", "Nagaland"),
}
# These are context outlines, drawn beside states whose villages are loaded. 0.001 deg
# (about 100 m) keeps them sharp at any zoom the app reaches for a neighbouring state.
TOL = 0.001

def source():
    if len(sys.argv) > 1: return sys.argv[1]
    shp = os.path.join(TMP, INNER, "State Boundary.shp")
    if not os.path.exists(shp):
        os.makedirs(TMP, exist_ok=True)
        subprocess.run(["bsdtar", "-xf", RAR, "-C", TMP, INNER], check=True)
    return shp

def main():
    shp = source()
    inverse = mg.make_inverse(open(shp[:-4] + ".prj").read())
    feats, seen = [], set()
    for rings_xy, rec in zip(mg.read_shp(shp), mg.read_dbf(shp[:-4] + ".dbf")):
        key = mg.field(rec, "state").upper()
        if key not in WANT or not rings_xy: continue
        slug, name = WANT[key]
        rings = []
        for ring in rings_xy:
            ll = mg.dp([(round(lo, 5), round(la, 5)) for lo, la in (inverse(x, y) for x, y in ring)], TOL)
            if len(ll) >= 4:
                if ll[0] != ll[-1]: ll.append(ll[0])
                rings.append(ll)
        geom = mg._polys(rings)
        feats.append({"type": "Feature",
                      "properties": {"slug": slug, "name": name,
                                     "villages": 0, "districts": 0, "taluks": 0, "nodata": True},
                      "geometry": geom})
        seen.add(key)
        print(f"{name:20} {len(json.dumps(geom)) // 1024:>5} KB")
    missing = set(WANT) - seen
    if missing: sys.exit(f"not found in {shp}: {', '.join(sorted(missing))}")
    feats.sort(key=lambda x: x["properties"]["name"])
    json.dump({"type": "FeatureCollection", "features": feats}, open(OUT, "w"), separators=(",", ":"))
    print(f"\n{len(feats)} no-data states -> {OUT} ({os.path.getsize(OUT) // 1024} KB)")

if __name__ == "__main__":
    main()
