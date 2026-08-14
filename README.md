# India Village Boundaries

Interactive explorer of **Survey of India's village-boundary database** — all 27
published states/UTs, ~586,000 villages. Pick a state, see its villages coloured by
district, isolate a district, search a village, and read its taluk / district / area /
LGD code. Live at **[indianvillage.4080studio.com](https://indianvillage.4080studio.com)**.

Data © Survey of India, used under the National Geospatial Policy 2022.

## Architecture

- **App** — one self-contained `dist/index.html` (no build step, no framework). Renders
  an SVG map; villages are merged into one path per district for performance and hover/tap
  use a spatial point-in-polygon index.
- **Data** — per-state GeoJSON lives in a **Cloudflare R2 bucket**, proxied at `/data/*`
  by `src/worker.js`. Not committed to git (~321 MB).
- **Deploy** — a Cloudflare Worker (`wrangler.jsonc`) serving the static app + R2 data.

## Rebuild the data

Raw SoI zips (`data/raw/`, ~931 MB) and generated GeoJSON (`dist/data/`, ~321 MB) are
gitignored. Regenerate from scratch:

```bash
python3 data/download.py        # download + verify all 27 state zips (resumable)
python3 build/build_all.py      # shapefile -> per-state GeoJSON (reads each .prj:
                                #   LCC, plus Gujarat=Mercator, Punjab=UTM)
python3 build/make_india.py     # dissolve state outlines -> dist/data/india.geojson
python3 build/make_manifest.py  # state picker manifest
```

Everything is pure Python stdlib — no GDAL/geopandas.

## Deploy

**One-time setup**

```bash
npx wrangler r2 bucket create soi-village-data   # create the data bucket
./sync-r2.sh                                     # upload dist/data/ to R2
npx wrangler deploy                              # deploy the Worker
```

Then connect the repo in the Cloudflare dashboard (Workers & Pages → this Worker →
Settings → Build → Connect to Git) so `main` auto-deploys.

**Day to day**

- Code/app change → `git push` (auto-deploys). Or `./deploy.sh`.
- Rebuilt data → `./sync-r2.sh`, then `git push`.

## Not included

Only the 27 states/UTs Survey of India has published. J&K, Ladakh, Himachal, Assam and
the other north-eastern states are not in the public release yet.
