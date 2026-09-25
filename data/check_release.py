#!/usr/bin/env python3
"""Check Survey of India's village boundary page for new or changed state files.

Compares the zips linked from the page (name, size, last-modified) against
data/release.tsv, the release this site was built from. Prints what changed and exits 1
if anything did (2 if the check itself failed), so the weekly GitHub Action
(.github/workflows/soi-release.yml) can open an issue. Nothing is downloaded beyond the page itself and a HEAD request per file.

    python3 data/check_release.py            # compare
    python3 data/check_release.py --write    # record the current release as the baseline
"""
import os, re, sys, html, urllib.request, urllib.parse

PAGE = "https://surveyofindia.gov.in/pages/village-boundary-data-base-of-entire-india"
SITE = "https://surveyofindia.gov.in"
BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "release.tsv")
UA = {"User-Agent": "Mozilla/5.0 (india-village-boundaries release check)"}

def get(url, method="GET"):
    req = urllib.request.Request(url, headers=UA, method=method)
    return urllib.request.urlopen(req, timeout=60)

def current():
    page = get(PAGE).read().decode("utf-8", "replace")
    links = sorted(set(html.unescape(m) for m in re.findall(r'href="([^"]+\.zip)"', page, re.I)))
    if not links:
        print("No zip links found: the page layout may have changed.", file=sys.stderr); sys.exit(2)
    rows = {}
    for href in links:
        name = urllib.parse.unquote(href.rsplit("/", 1)[-1])
        url = urllib.parse.urljoin(SITE, urllib.parse.quote(href, safe="/:&"))
        try:
            with get(url, "HEAD") as r:
                rows[name] = (r.headers.get("Content-Length", ""), r.headers.get("Last-Modified", ""))
        except Exception as e:
            rows[name] = ("?", f"error: {e}")
    return rows

def baseline():
    if not os.path.exists(BASE): return {}
    out = {}
    for line in open(BASE):
        if line.startswith("#") or not line.strip(): continue
        name, size, mod = line.rstrip("\n").split("\t")
        out[name] = (size, mod)
    return out

def main():
    try: now = current()
    except Exception as e:                           # site down, timeout...: not a release change
        print(f"Couldn't read {PAGE}: {e}", file=sys.stderr); sys.exit(2)
    if "--write" in sys.argv:
        with open(BASE, "w") as f:
            f.write("# file\tbytes\tlast-modified  (written by check_release.py --write)\n")
            for name, (size, mod) in sorted(now.items()): f.write(f"{name}\t{size}\t{mod}\n")
        print(f"recorded {len(now)} files -> {BASE}"); return
    old = baseline()
    new = sorted(set(now) - set(old))
    gone = sorted(set(old) - set(now))
    changed = sorted(n for n in set(now) & set(old) if now[n][0] != old[n][0] and "?" not in now[n][0])
    if not (new or gone or changed):
        print(f"No change: {len(now)} state files, same as the baseline."); return
    print(f"Survey of India's village boundary release has changed ({PAGE}).\n")
    for n in new: print(f"- New: {n} ({int(now[n][0] or 0) / 1e6:.0f} MB, {now[n][1]})")
    for n in changed: print(f"- Updated: {n} ({int(old[n][0]) / 1e6:.0f} -> {int(now[n][0]) / 1e6:.0f} MB, {now[n][1]})")
    for n in gone: print(f"- No longer listed: {n}")
    print("\nTo rebuild: add new files to data/urls.txt, then follow \"Rebuild the data\" in the README"
          " and run python3 data/check_release.py --write.")
    sys.exit(1)

if __name__ == "__main__":
    main()
