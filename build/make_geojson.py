#!/usr/bin/env python3
"""Convert a Survey of India state shapefile (Lambert Conformal Conic / WGS84)
to WGS84 lat-long GeoJSON. Pure stdlib — no GDAL/pyshp needed.

Usage: python3 make_geojson.py <path-to.shp> <out.geojson> [dp_tolerance_deg]
The LCC parameters are hard-coded from the SoI .prj (same for every state).
"""
import struct, math, json, sys, re

# WGS84 ellipsoid
A    = 6378137.0
F    = 1/298.257223563
E2   = 2*F - F*F
E    = math.sqrt(E2)

# SoI states ship THREE different projections (read each .prj): most are Lambert
# Conformal Conic, but Gujarat is World Mercator and Punjab is UTM 43N (TM).
def make_inverse(prj_text):
    def p(name, default=None):
        m = re.search(r'PARAMETER\["%s"\D+(-?[\d.]+)' % name, prj_text)
        return float(m.group(1)) if m else default
    proj = re.search(r'PROJECTION\["([^"]+)"', prj_text)
    proj = proj.group(1) if proj else "Lambert_Conformal_Conic"
    FE, FN = p("False_Easting", 0.0), p("False_Northing", 0.0)
    cm = math.radians(p("Central_Meridian", 0.0))

    if proj == "Mercator":                                    # ellipsoidal World Mercator
        def inv(x, y):
            lon = cm + (x - FE)/A
            t = math.exp(-(y - FN)/A); phi = math.pi/2 - 2*math.atan(t)
            for _ in range(15):
                s = math.sin(phi)
                phi = math.pi/2 - 2*math.atan(t*(((1-E*s)/(1+E*s))**(E/2)))
            return math.degrees(lon), math.degrees(phi)
        return inv

    if proj == "Transverse_Mercator":                         # UTM
        k0 = p("Scale_Factor", 1.0)
        def inv(x, y):
            x -= FE; y -= FN
            M = y/k0
            mu = M/(A*(1 - E2/4 - 3*E2**2/64 - 5*E2**3/256))
            e1 = (1 - math.sqrt(1-E2))/(1 + math.sqrt(1-E2))
            phi1 = (mu + (3*e1/2 - 27*e1**3/32)*math.sin(2*mu)
                    + (21*e1**2/16 - 55*e1**4/32)*math.sin(4*mu)
                    + (151*e1**3/96)*math.sin(6*mu) + (1097*e1**4/512)*math.sin(8*mu))
            ep2 = E2/(1-E2)
            C1 = ep2*math.cos(phi1)**2; T1 = math.tan(phi1)**2
            N1 = A/math.sqrt(1 - E2*math.sin(phi1)**2)
            R1 = A*(1-E2)/(1 - E2*math.sin(phi1)**2)**1.5
            D = x/(N1*k0)
            lat = phi1 - (N1*math.tan(phi1)/R1)*(D**2/2
                  - (5+3*T1+10*C1-4*C1**2-9*ep2)*D**4/24
                  + (61+90*T1+298*C1+45*T1**2-252*ep2-3*C1**2)*D**6/720)
            lon = cm + (D - (1+2*T1+C1)*D**3/6
                  + (5-2*C1+28*T1-3*C1**2+8*ep2+24*T1**2)*D**5/120)/math.cos(phi1)
            return math.degrees(lon), math.degrees(lat)
        return inv

    # default: Lambert Conformal Conic (2SP)
    lat0 = math.radians(p("Latitude_Of_Origin", 24.0))
    lat1 = math.radians(p("Standard_Parallel_1", 12.472944))
    lat2 = math.radians(p("Standard_Parallel_2", 35.172806))
    _m = lambda ph: math.cos(ph)/math.sqrt(1 - E2*math.sin(ph)**2)
    def _t(ph):
        s = math.sin(ph)
        return math.tan(math.pi/4 - ph/2)/(((1-E*s)/(1+E*s))**(E/2))
    n = (math.log(_m(lat1)) - math.log(_m(lat2)))/(math.log(_t(lat1)) - math.log(_t(lat2)))
    bf = _m(lat1)/(n*_t(lat1)**n)
    rho0 = A*bf*_t(lat0)**n
    def inv(x, y):
        xp, yp = x - FE, y - FN
        rho = math.copysign(math.sqrt(xp*xp + (rho0-yp)**2), n)
        t = (rho/(A*bf))**(1/n)
        theta = math.atan2(xp, rho0 - yp)
        lon = theta/n + cm
        phi = math.pi/2 - 2*math.atan(t)
        for _ in range(15):
            s = math.sin(phi)
            phi = math.pi/2 - 2*math.atan(t*(((1-E*s)/(1+E*s))**(E/2)))
        return math.degrees(lon), math.degrees(phi)
    return inv

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

# --- Douglas-Peucker in lon/lat degrees (iterative: safe for huge rings) ---
def dp(points, tol):
    n = len(points)
    if n < 3: return points
    keep = [False]*n; keep[0] = keep[n-1] = True
    stack = [(0, n-1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]; bx, by = points[b]
        dx, dy = bx-ax, by-ay; L2 = dx*dx + dy*dy
        idx, dmax = -1, tol
        for i in range(a+1, b):
            px, py = points[i][0]-ax, points[i][1]-ay
            d = abs(px*dy - py*dx)/math.sqrt(L2) if L2 else math.hypot(px, py)
            if d > dmax: idx, dmax = i, d
        if idx != -1:
            keep[idx] = True; stack.append((a, idx)); stack.append((idx, b))
    return [points[i] for i in range(n) if keep[i]]

def signed_area(ring):
    s = 0.0
    for i in range(len(ring)-1):
        s += ring[i][0]*ring[i+1][1] - ring[i+1][0]*ring[i][1]
    return s/2

def convert(shp, out, tol=0.0002, prec=6):
    dbf = shp[:-4] + ".dbf"
    inverse = make_inverse(open(shp[:-4] + ".prj").read())   # per-state projection
    shapes = read_shp(shp)
    recs = read_dbf(dbf)
    feats = []
    for rings_xy, rec in zip(shapes, recs):
        if not rings_xy: continue
        # reproject + simplify each ring — never drop a village:
        # if simplification collapses a ring, fall back to its full (rounded) shape.
        proj_rings = []
        for ring in rings_xy:
            full = [(round(lo, prec), round(la, prec))
                    for lo, la in (inverse(x, y) for x, y in ring)]
            ll = dp(full, tol)
            if len(ll) < 4: ll = full          # collapsed -> keep the real shape (no bbox artifacts)
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
        # compact keys keep big-state files small: n=name d=district s=subdist l=lgd c=cat a=area
        props = {"n": rec.get("Vill_name", ""), "d": rec.get("District", ""),
                 "s": rec.get("Sub_dist", ""), "l": rec.get("Vill_LGD", "")}
        cat = rec.get("Vill_cat", "")
        if cat: props["c"] = cat               # omit when empty (26 of 27 states)
        try:
            a = round(float(rec.get("Shape_Area", 0))/1e6, 3)
            if a: props["a"] = a
        except: pass
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    fc = {"type": "FeatureCollection", "features": feats}
    json.dump(fc, open(out, "w"), separators=(",", ":"))
    return len(feats)

if __name__ == "__main__":
    shp, out = sys.argv[1], sys.argv[2]
    tol = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0002
    n = convert(shp, out, tol)
    print(f"{n} features -> {out}")
