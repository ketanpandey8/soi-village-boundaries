#!/usr/bin/env bash
# Upload the built GeoJSON to the R2 bucket. Run once at setup, then again
# whenever you rebuild the data. Code changes do NOT need this — just git push.
#
#   ./sync-r2.sh
#
set -euo pipefail

BUCKET="soi-village-data"
DIR="dist/data"

[ -d "$DIR" ] || { echo "No $DIR — build it first (see README)"; exit 1; }

count=0
for f in "$DIR"/*.geojson "$DIR"/states.json; do
  [ -e "$f" ] || continue
  echo "→ $(basename "$f")"
  npx wrangler r2 object put "$BUCKET/$(basename "$f")" \
    --file "$f" --content-type application/json
  count=$((count + 1))
done
echo "✓ Uploaded $count files to r2://$BUCKET"
