#!/usr/bin/env bash
# Deploy the app CODE to Cloudflare. With R2, map data is separate:
#   - code:  git push  (auto-deploys once Git-connected) — or this script
#   - data:  ./sync-r2.sh  (only when you rebuild dist/data)
#
#   ./deploy.sh
#
set -euo pipefail

echo "→ Pushing to GitHub…"
git push

echo "→ Deploying Worker to Cloudflare (indianvillage.4080studio.com)…"
npx wrangler deploy

echo "✓ Done — https://indianvillage.4080studio.com"
echo "  (If you rebuilt the GeoJSON, also run ./sync-r2.sh)"
