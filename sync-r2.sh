#!/usr/bin/env bash
# Upload the built GeoJSON to the R2 bucket. Run once at setup, then again
# whenever you rebuild the data. Code changes don't need this, just git push.
#
#   ./sync-r2.sh
#
# Uploads each state's display file plus its full-detail district files
# (dist/data/<state>/<district>.geojson), keeping the same paths as keys.
set -euo pipefail

BUCKET="soi-village-data"
DIR="dist/data"

[ -d "$DIR" ] || { echo "No $DIR. Build it first (see README)"; exit 1; }

count=0
while IFS= read -r f; do
  key="${f#"$DIR"/}"
  echo "→ $key"
  npx wrangler r2 object put "$BUCKET/$key" \
    --file "$f" --content-type application/json --remote
  count=$((count + 1))
done < <(find "$DIR" -type f \( -name '*.geojson' -o -name 'states.json' \) | sort)
echo "✓ Uploaded $count files to r2://$BUCKET"
