#!/usr/bin/env python3
"""Download + verify all Survey of India village-boundary state zips.

Resumable (HTTP Range) so it survives the SoI server's frequent mid-transfer
connection drops on large files. Skips files already present and valid.

Usage:  python3 data/download.py
Source: https://surveyofindia.gov.in/pages/village-boundary-data-base-of-entire-india
Data is free to use under India's National Geospatial Policy 2022. Credit "Survey of India".
"""
import urllib.request, urllib.parse, os, time, zipfile

BASE = "https://surveyofindia.gov.in/documents/"
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CHUNK = 4 * 1024 * 1024  # 4 MB range chunks

def urls():
    with open(os.path.join(HERE, "urls.txt")) as f:
        return [l.strip().split("/")[-1] for l in f if l.strip()]

def is_valid(path):
    if not os.path.exists(path) or os.path.getsize(path) < 1000:
        return False
    try:
        with zipfile.ZipFile(path) as z:
            return z.testzip() is None and any(n.lower().endswith(".shp") for n in z.namelist())
    except Exception:
        return False

def total_size(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return int(r.headers["Content-Range"].split("/")[1])

def fetch(fname):
    url = BASE + urllib.parse.quote(fname)
    out = os.path.join(RAW, fname)
    if is_valid(out):
        print(f"have  {fname}"); return
    tot = total_size(url)
    have = os.path.getsize(out) if os.path.exists(out) else 0
    if have > tot:
        have = 0; os.remove(out)
    with open(out, "ab") as f:
        while have < tot:
            end = min(have + CHUNK - 1, tot - 1)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0",
                                                       "Range": f"bytes={have}-{end}"})
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = r.read()
                f.write(data); f.flush(); have += len(data)
            except Exception as e:
                print(f"  drop @ {have}/{tot}: {e} -- retrying"); time.sleep(2)
    print(f"  OK  {os.path.getsize(out)//1048576}MB {fname} valid={is_valid(out)}")

if __name__ == "__main__":
    os.makedirs(RAW, exist_ok=True)
    for name in urls():
        fetch(name)
    print("done")
