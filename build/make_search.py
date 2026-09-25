#!/usr/bin/env python3
"""Write the all-India village search index into dist/data/find/.

The home screen searches every state at once, but loading 586,000 villages up front would
cost more than most states do. So the index is split into small files the app fetches as
you type:

  find/<cc>.json        villages whose name's sound key (see key()) starts with <cc> (a-z;
                        "_" for anything else, or a one-letter key)
  find/<ccc>.json       the same, by three letters, for busy prefixes (listed in index.json)
  find/lgd-<dd>.json    villages whose LGD code starts with the two digits <dd>

Each file: {"s": [state slugs], "d": [district names], "t": [taluk names],
            "v": [[name, state, district, taluk, lgd], ...]}   (state/district/taluk are
indices into the lists; unnamed villages appear only in the LGD files)

Reads the display files (dist/data/<state>.geojson), so run it after build_all.py.
"""
import os, re, json
D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "data")
OUT = os.path.join(D, "find")      # was search/ before the sound key; a new name so the
                                   # live site keeps its own index until this version deploys

SPLIT = 3000   # a two-letter file with more villages than this is split by the third letter

def key(name):
    """A rough sound key, so spellings that differ the way Indian names do in English letters
    still match: Rampur / Raampur / Ramapur, Chandpur / Candpur, Phulwari / Fulwari. The app
    turns queries in Indian scripts into English letters and then applies the same key, so
    this must stay identical to skel() in build/app.html."""
    s = re.sub(r"[^a-z ]", "", name.lower())
    s = s.replace("ph", "f").replace("w", "v").replace("z", "j").replace("q", "k").replace("x", "ks")
    s = re.sub(r"([bcdfgjklmnpstvy])h", r"\1", s)          # aspirates: kh, gh, ch, th, dh, bh, sh
    s = s.replace("ee", "i").replace("ii", "i").replace("oo", "u").replace("uu", "u")
    s = s.replace("ei", "e").replace("ey", "e")                        # Bareilly / Bareli
    s = re.sub(r"y\b", "i", s)                                        # final y: Bareilly / Bareli
    s = " ".join(w[:1] + w[1:].replace("a", "") for w in s.split())   # short a comes and goes
    return re.sub(r"(.)\1+", r"\1", s)                   # double letters

def shard_of(name, n=2):
    # first n characters of the name's key; anything outside a-z (or past the end) becomes "_"
    return "".join(c if "a" <= c <= "z" else "_" for c in key(name)[:n]).ljust(n, "_")

def main():
    shards = {}
    def add(key, row):
        shards.setdefault(key, []).append(row)
    slugs = sorted(f[:-8] for f in os.listdir(D)
                   if f.endswith(".geojson") and f != "india.geojson")
    total = 0
    for slug in slugs:
        fc = json.load(open(os.path.join(D, slug + ".geojson")))
        for f in fc["features"]:
            p = f["properties"]
            n, d, t, l = (p.get("n") or "").strip(), p.get("d") or "", p.get("s") or "", p.get("l") or ""
            row = (n, slug, d, t, l)
            if n: add(shard_of(n), row)
            if l: add("lgd-" + l[:2], row)
            total += 1
        print(f"{slug:32} {len(fc['features']):>7}")

    split = sorted(k for k, rows in shards.items() if not k.startswith("lgd-") and len(rows) > SPLIT)
    for k in split:
        for r in shards.pop(k): add(shard_of(r[0], 3), r)

    os.makedirs(OUT, exist_ok=True)
    for old in os.listdir(OUT):
        if old.endswith(".json"): os.remove(os.path.join(OUT, old))
    size = 0
    for key, rows in sorted(shards.items()):
        rows.sort(key=lambda r: (r[0].lower(), r[1], r[4]))
        idx = {"s": {}, "d": {}, "t": {}}
        def ix(kind, v):
            m = idx[kind]
            if v not in m: m[v] = len(m)
            return m[v]
        v = [[r[0], ix("s", r[1]), ix("d", r[2]), ix("t", r[3]), r[4]] for r in rows]
        doc = {k: list(m) for k, m in idx.items()}
        doc["v"] = v
        path = os.path.join(OUT, key + ".json")
        json.dump(doc, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
        size += os.path.getsize(path)
    json.dump({"split": split}, open(os.path.join(OUT, "index.json"), "w"), separators=(",", ":"))
    print(f"\n{total} villages -> {len(shards)} files in {OUT} ({size // 1048576} MB)")

if __name__ == "__main__":
    main()
