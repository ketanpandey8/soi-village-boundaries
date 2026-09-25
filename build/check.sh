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
