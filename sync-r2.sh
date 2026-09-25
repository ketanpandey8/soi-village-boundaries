#!/usr/bin/env bash
# Upload the built GeoJSON to the R2 bucket. Run once at setup, then again
# whenever you rebuild the data. Code changes don't need this, just git push.
#
#   ./sync-r2.sh            # everything, 8 uploads at a time
#   ./sync-r2.sh search     # only keys starting with "search" (any prefix works)
#   JOBS=4 ./sync-r2.sh     # fewer at once
#
# Uploads what the app reads, keeping the same paths as keys: the India outline and
# manifest, each state's packed display file and full-detail district files
# (build/pack.py), the village search index (build/make_search.py), and the bordering
# villages, village page data and sitemaps (build/make_pages.py).
set -euo pipefail

BUCKET="soi-village-data"
DIR="dist/data"
JOBS="${JOBS:-8}"

[ -d "$DIR" ] || { echo "No $DIR. Build it first (see README)"; exit 1; }

export BUCKET DIR
log=$(mktemp)
PREFIX="${1:-}"
find "$DIR" -type f \( -name '*.packed.json' -o -name 'india.geojson' -o -name 'states.json' \
                     -o -name '*.nb.json' -o -path "$DIR/search/*.json" -o -path "$DIR/pages/*.json" \
                     -o -path "$DIR/sitemaps/*.xml" \) | sort | grep -F "$DIR/$PREFIX" |
  xargs -P "$JOBS" -I{} sh -c '
    key="${1#"$DIR"/}"
    case "$1" in *.xml) type=application/xml ;; *) type=application/json ;; esac
    if npx wrangler r2 object put "$BUCKET/$key" --file "$1" \
         --content-type "$type" --remote >/dev/null 2>&1
    then echo "ok   $key"; else echo "FAIL $key"; fi' _ {} | tee "$log"

ok=$(grep -c '^ok' "$log" || true); fail=$(grep -c '^FAIL' "$log" || true); rm -f "$log"
echo "✓ Uploaded $ok files to r2://$BUCKET"
[ "$fail" -eq 0 ] || { echo "✘ $fail failed. Run again to retry (re-uploading is harmless)."; exit 1; }
