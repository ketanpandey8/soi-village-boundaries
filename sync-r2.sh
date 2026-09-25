#!/usr/bin/env bash
# Upload the built GeoJSON to the R2 bucket. Run once at setup, then again
# whenever you rebuild the data. Code changes don't need this, just git push.
#
#   ./sync-r2.sh            # 8 uploads at a time
#   JOBS=4 ./sync-r2.sh     # fewer at once
#
# Uploads each state's display file plus its full-detail district files
# (dist/data/<state>/<district>.geojson), keeping the same paths as keys.
set -euo pipefail

BUCKET="soi-village-data"
DIR="dist/data"
JOBS="${JOBS:-8}"

[ -d "$DIR" ] || { echo "No $DIR. Build it first (see README)"; exit 1; }

export BUCKET DIR
log=$(mktemp)
find "$DIR" -type f \( -name '*.geojson' -o -name 'states.json' \) | sort |
  xargs -P "$JOBS" -I{} sh -c '
    key="${1#"$DIR"/}"
    if npx wrangler r2 object put "$BUCKET/$key" --file "$1" \
         --content-type application/json --remote >/dev/null 2>&1
    then echo "ok   $key"; else echo "FAIL $key"; fi' _ {} | tee "$log"

ok=$(grep -c '^ok' "$log" || true); fail=$(grep -c '^FAIL' "$log" || true); rm -f "$log"
echo "✓ Uploaded $ok files to r2://$BUCKET"
[ "$fail" -eq 0 ] || { echo "✘ $fail failed. Run again to retry (re-uploading is harmless)."; exit 1; }
