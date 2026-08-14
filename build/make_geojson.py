#!/usr/bin/env python3
"""Convert a Survey of India state shapefile (Lambert Conformal Conic / WGS84)
to WGS84 lat-long GeoJSON. Pure stdlib — no GDAL/pyshp needed.

Usage: python3 make_geojson.py <path-to.shp> <out.geojson> [dp_tolerance_deg]
The LCC parameters are hard-coded from the SoI .prj (same for every state).
"""
import struct, math, json, sys

# --- SoI Lambert Conformal Conic params (from every state's .prj) ---
A   = 6378137.0            # WGS84 semi-major axis
INVF= 298.257223563
F   = 1/INVF
E2  = 2*F - F*F
E   = math.sqrt(E2)
LAT0= math.radians(24.0)
LON0= math.radians(80.0)
LAT1= math.radians(12.472944)
LAT2= math.radians(35.172806)
FE  = 4000000.0
FN  = 4000000.0

def _m(phi): return math.cos(phi)/math.sqrt(1 - E2*math.sin(phi)**2)
def _t(phi):
    s = math.sin(phi)
    return math.tan(math.pi/4 - phi/2) / (((1 - E*s)/(1 + E*s))**(E/2))

m1, m2 = _m(LAT1), _m(LAT2)
t0, t1, t2 = _t(LAT0), _t(LAT1), _t(LAT2)
N = (math.log(m1) - math.log(m2)) / (math.log(t1) - math.log(t2))
BF = m1 / (N * t1**N)
RHO0 = A * BF * t0**N

def inverse(x, y):
    """LCC easting/northing (m) -> (lon, lat) in degrees."""
    xp = x - FE
    yp = y - FN
    rho = math.copysign(math.sqrt(xp*xp + (RHO0 - yp)**2), N)
    t = (rho/(A*BF))**(1/N)
    theta = math.atan2(xp, RHO0 - yp)
    lon = theta/N + LON0
    # iterate for latitude
    phi = math.pi/2 - 2*math.atan(t)
    for _ in range(15):
        s = math.sin(phi)
        phi_new = math.pi/2 - 2*math.atan(t*(((1 - E*s)/(1 + E*s))**(E/2)))
        if abs(phi_new - phi) < 1e-12:
            phi = phi_new; break
        phi = phi_new
    return math.degrees(lon), math.degrees(phi)

# --- shapefile geometry reader (polygon type 5) ---
def read_shp(path):
    d = open(path, "rb").read()
    pos = 100
    shapes = []
    while pos < len(d):
        rnum, clen = struct.unpack(">ii", d[pos:pos+8]); pos += 8
        stype = struct.unpack("<i", d[pos:pos+4])[0]
        if stype == 0:                      # null shape
            shapes.append([]); pos += clen*2; continue
        nparts, npoints = struct.unpack("<ii", d[pos+36:pos+44])
        p = pos + 44
        parts = list(struct.unpack("<%di" % nparts, d[p:p+4*nparts])); p += 4*nparts
        pts = struct.unpack("<%dd" % (2*npoints), d[p:p+16*npoints])
        rings = []
        bounds = parts + [npoints]
        for i in range(nparts):
            ring = [(pts[2*j], pts[2*j+1]) for j in range(bounds[i], bounds[i+1])]
            rings.append(ring)
        shapes.append(rings)
        pos += clen*2
    return shapes

# --- dbf attribute reader ---
def read_dbf(path):
    d = open(path, "rb").read()
    num, hlen, rlen = struct.unpack("<I H H", d[4:12])
    fields = []; pos = 32
    while d[pos] != 0x0D:
        f = d[pos:pos+32]
        fields.append((f[0:11].split(b"\x00")[0].decode("latin1"), chr(f[11]), f[16]))
        pos += 32
    recs = []
    for i in range(num):
        p = hlen + i*rlen + 1; o = {}
        for name, typ, ln in fields:
            o[name] = d[p:p+ln].decode("latin1").strip(); p += ln
        recs.append(o)
    return recs

# --- Douglas-Peucker in lon/lat degrees ---
def dp(points, tol):
    if len(points) < 3: return points
    def _dp(pts):
        if len(pts) < 3: return pts
        a, b = pts[0], pts[-1]
        dx, dy = b[0]-a[0], b[1]-a[1]
        L2 = dx*dx + dy*dy
        idx, dmax = 0, 0.0
        for i in range(1, len(pts)-1):
            px, py = pts[i][0]-a[0], pts[i][1]-a[1]
            d = abs(px*dy - py*dx)/math.sqrt(L2) if L2 else math.hypot(px, py)
            if d > dmax: idx, dmax = i, d
        if dmax > tol:
            return _dp(pts[:idx+1])[:-1] + _dp(pts[idx:])
        return [a, b]
    return _dp(points)

def signed_area(ring):
    s = 0.0
    for i in range(len(ring)-1):
        s += ring[i][0]*ring[i+1][1] - ring[i+1][0]*ring[i][1]
    return s/2

def main():
    shp, out = sys.argv[1], sys.argv[2]
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0002  # ~20 m
    dbf = shp[:-4] + ".dbf"
    shapes = read_shp(shp)
    recs = read_dbf(dbf)
    feats = []
    for rings_xy, rec in zip(shapes, recs):
        if not rings_xy: continue
        # reproject + simplify each ring
        proj_rings = []
        for ring in rings_xy:
            ll = [inverse(x, y) for x, y in ring]
            ll = [(round(lo, 6), round(la, 6)) for lo, la in ll]
            ll = dp(ll, tol)
            if len(ll) >= 4:
                if ll[0] != ll[-1]: ll.append(ll[0])
                proj_rings.append(ll)
        if not proj_rings: continue
        # group holes (ESRI: clockwise=outer=negative area in lon/lat) into polygons
        polys, cur = [], None
        for r in proj_rings:
            if signed_area(r) < 0:            # outer
                if cur: polys.append(cur)
                cur = [r]
            else:                              # hole
                if cur: cur.append(r)
                else: cur = [r]
        if cur: polys.append(cur)
        if len(polys) == 1:
            geom = {"type": "Polygon", "coordinates": polys[0]}
        else:
            geom = {"type": "MultiPolygon", "coordinates": polys}
        props = {
            "name": rec.get("Vill_name", ""),
            "dist": rec.get("District", ""),
            "sub":  rec.get("Sub_dist", ""),
            "cat":  rec.get("Vill_cat", ""),
            "lgd":  rec.get("Vill_LGD", ""),
        }
        try: props["area_km2"] = round(float(rec.get("Shape_Area", 0))/1e6, 3)
        except: props["area_km2"] = None
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    fc = {"type": "FeatureCollection", "features": feats}
    json.dump(fc, open(out, "w"), separators=(",", ":"))
    print(f"{len(feats)} features -> {out}")

if __name__ == "__main__":
    main()
