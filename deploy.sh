#!/usr/bin/env bash
# Push code to GitHub and deploy the site to Cloudflare in one step.
# The map data (dist/data/, ~321 MB) is gitignored, so it can't ship via a
# Git-connected build — wrangler uploads it directly from this machine.
#
#   ./deploy.sh
#
set -euo pipefail

echo "→ Pushing to GitHub…"
git push

echo "→ Deploying to Cloudflare (indianvillage.4080studio.com)…"
npx wrangler deploy

echo "✓ Done — https://indianvillage.4080studio.com"
