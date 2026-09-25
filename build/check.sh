#!/usr/bin/env bash
# Checks that run on every pull request (.github/workflows/check.yml). Run locally the same way:
#   build/check.sh
# The map data isn't in git, so these check the code and the published page, not the data.
set -euo pipefail
cd "$(dirname "$0")/.."
fail=0; ok(){ echo "ok    $1"; }; bad(){ echo "FAIL  $1"; fail=1; }

# the deployed page must be the current app
cmp -s build/app.html dist/index.html && ok "dist/index.html matches build/app.html" \
  || bad "dist/index.html differs from build/app.html (cp build/app.html dist/index.html)"

# the app's script and the Worker parse
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
python3 - "$tmp/app.js" <<'PY'
import sys
s = open("build/app.html").read(); i = s.index("<script>") + 8
open(sys.argv[1], "w").write(s[i:s.index("</script>", i)])
PY
node --check "$tmp/app.js" && ok "app script parses" || bad "app script has a syntax error"
cp src/worker.js "$tmp/worker.mjs"
node --check "$tmp/worker.mjs" && ok "worker parses" || bad "worker has a syntax error"

# the search sound key is written twice (build/make_search.py, and skel() in the app) and
# the two must agree, or searches look in the wrong index file
names='["Rampur","Raampur","Ramapur","Chandpur","Phulwari","Fulwari","Bareilly","Rae Bareli","Bhagalpur","Sheikhpura","Aonla","Querim","Xavier Nagar","Zamania","Kottayam","H.Hossahalli","KRISHNAGAR","Bhubaneswar","Sheyhpur","Mau Aima"]'
py=$(python3 -c "import sys,json;sys.path.insert(0,'build');import make_search as m;print(json.dumps([m.key(n) for n in json.loads(sys.argv[1])], separators=(',', ':')))" "$names")
js=$(node -e "$(python3 - <<'PY2'
s = open("build/app.html").read(); i = s.index("  function skel("); j = s.index("\n", s.index('return s.replace(/(.)\\1+/g', i))
print(s[i:j])
PY2
)
console.log(JSON.stringify(JSON.parse(process.argv[1]).map(skel)))" "$names")
[ "$py" = "$js" ] && ok "search sound key matches in Python and the app" || bad "search sound key differs: $py vs $js"

# the service worker keeps map data per DATA_V, so it must match the app's
av=$(grep -o 'const DATA_V="[0-9]*"' build/app.html | grep -o '[0-9]*'); sv=$(grep -o 'const DATA_V = "[0-9]*"' dist/sw.js | grep -o '[0-9]*')
[ -n "$av" ] && [ "$av" = "$sv" ] && ok "DATA_V matches in the app and dist/sw.js ($av)" || bad "DATA_V is $av in the app but $sv in dist/sw.js"
node --check dist/sw.js && ok "service worker parses" || bad "dist/sw.js has a syntax error"

# every message the app passes to L() has a Hindi translation in its HI table
missing=$(python3 - <<'PY2'
import re, json
s = open("build/app.html").read()
m = re.search(r"const HI=(\{.*?\});\n", s); hi = json.loads(m.group(1))
s = s[:m.start()] + s[m.end():]                      # look for uses, not the table itself
used = set(re.findall(r'L\("((?:[^"\\]|\\.)+)"', s))
used |= {m for pair in re.findall(r'L\([^()]*?\?"([^"]+)":"([^"]+)"', s) for m in pair}
print("; ".join(sorted(k for k in used if k not in hi)))
PY2
)
[ -z "$missing" ] && ok "every L() message has Hindi" || bad "no Hindi for: $missing"

# build scripts compile
python3 -m py_compile build/*.py data/*.py && ok "python scripts compile" || bad "python scripts don't compile"

# house style: no em dashes anywhere a visitor can read
if grep -n $'\xe2\x80\x94' dist/index.html README.md; then bad "em dash found (above)"; else ok "no em dashes"; fi

# a preview image for India and every released state (the slugs in make_manifest.py)
missing=$(python3 - <<'PY'
import os, re
slugs = re.findall(r'"([a-z-]+)":"', open("build/make_manifest.py").read()) + ["india"]
print(" ".join(s for s in slugs if not os.path.exists(f"dist/cards/{s}.png")))
PY
)
[ -z "$missing" ] && ok "preview images present" || bad "missing preview images: $missing (python3 build/make_cards.py)"

exit $fail
