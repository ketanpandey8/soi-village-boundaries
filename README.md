# India Village Boundaries

Interactive explorer of the **Survey of India village boundary database**: all 27
published states and UTs, 586,164 villages. Search any village in India by name or LGD code,
find the village you're standing in, see a state's villages coloured by district, read each
village's taluk, district, area, category and LGD code, share a link to it, and download
it or a whole district as GeoJSON or KML with every surveyed point. Live at
**[indianvillage.4080studio.com](https://indianvillage.4080studio.com)**.

Data © Survey of India, used under the National Geospatial Policy 2022.

## Architecture

- **App**: one self-contained `dist/index.html` (no build step, no framework), copied from
  `build/app.html`. Renders an SVG map; villages are merged into one path per district for
  performance, and hover/tap use a spatial point-in-polygon index.
- **Data**: lives in a **Cloudflare R2 bucket**, proxied at `/data/*` by `src/worker.js`
  (which also caches it at the edge). Not committed to git.
- **Pages and previews**: the site routes by path (`/goa`, `/goa/626847`). For those paths
  the Worker serves the app with that state's or village's title, description and preview
  image (`dist/cards/`, drawn by `build/make_cards.py`), so shared links show what they point to.
- **Deploy**: a Cloudflare Worker (`wrangler.jsonc`) serving the static app and R2 data.

### Data layout and detail

Boundaries are never simplified away. Each state is built into two parts:

| File | Contents | Used when |
|---|---|---|
| `dist/data/<state>.packed.json` | every village with its attributes, simplified to a tolerance that scales with the state's width | zoomed out, where the removed points are under half a pixel |
| `dist/data/<state>/<district>.packed.json` | every source vertex (6 decimal places, about 0.1 m), no simplification | loaded per district once you zoom in far enough to see a difference, and always for the selected village |

Villages appear in the same order in both, and the app checks LGD codes before swapping
in full detail. The display file's `meta` records the tolerance (`dispTol`) and the
district file names (`detail`).

The build writes plain GeoJSON first, then `build/pack.py` packs each file: coordinates as
whole numbers at the precision they were rounded to, each ring stored as a start point plus
differences. It checks that every point decodes exactly, and cuts the data from 2.35 GB to
0.91 GB (Uttar Pradesh: 37 MB to 18 MB, or 7 MB to 5 MB compressed).

The home screen's village search reads `dist/data/search/` (`build/make_search.py`): the
index split by the first two or three letters of the name, and by the first two digits of
the LGD code, so each search fetches one small file.

### What the source leaves out

The app shows the source as released. Blank fields read "not in source", and each state
lists its gaps (unnamed villages, missing or duplicate LGD codes, missing taluks or
categories) with a button to highlight them. Field names vary between state files
(`Vill_Cat` / `Vill_cat`, `Sub_dist` / `Subdist`, `DISTRICT`, Madhya Pradesh's
`Villl_name`), so `build/make_geojson.py` matches them case-insensitively.

## Rebuild the data

Raw SoI zips (`data/raw/`, about 931 MB) and generated GeoJSON (`dist/data/`) are
gitignored. Regenerate from scratch:

```bash
python3 data/download.py        # download + verify all 27 state zips (resumable)
python3 build/build_all.py      # shapefiles -> display + full-detail GeoJSON (reads each .prj:
                                #   LCC, plus Gujarat=Mercator, Punjab=UTM)
python3 build/make_manifest.py  # state list with village counts
python3 build/make_india.py     # dissolve state outlines + per-state stats -> dist/data/india.geojson
python3 build/pack.py           # the smaller .packed.json files the app downloads
python3 build/make_search.py    # all-India village search index
python3 build/make_cards.py     # link preview images (needs Pillow), then commit dist/cards/
python3 data/check_release.py --write   # record which SoI release this was built from
```

Everything is pure Python stdlib, no GDAL or geopandas. After a rebuild, bump `DATA_V` in
`build/app.html` so browsers and the edge cache fetch the new files.

## Deploy

**One-time setup**

```bash
npx wrangler r2 bucket create soi-village-data   # create the data bucket
./sync-r2.sh                                     # upload dist/data/ (including district folders) to R2
npx wrangler deploy                              # deploy the Worker
```

Then connect the repo in the Cloudflare dashboard (Workers & Pages, this Worker,
Settings, Build, Connect to Git) so `main` auto-deploys.

**Day to day**

- Code/app change: open a pull request. `build/check.sh` runs on it (GitHub Actions), and
  Cloudflare builds a preview with its own link. Merging to `main` deploys.
- Rebuilt data: `./sync-r2.sh` (or `./sync-r2.sh search` for one prefix), then merge.

**New releases.** Every Monday a GitHub Action runs `data/check_release.py` against the
Survey of India download page and opens an issue if a state file is added or changed.

## No-data states

Only 27 states/UTs have village data (all that Survey of India has published). To show a
complete India, the unreleased ones (Jammu & Kashmir, Ladakh, Himachal Pradesh, Assam,
Arunachal Pradesh, Nagaland, Manipur, Mizoram, Meghalaya) are drawn as grey "no data"
outlines. They come from Survey of India's own
[Administrative Boundary Database](https://surveyofindia.gov.in/pages/administrative-boundary-data-base-abdb-)
(`State_District_Subdistrict_PAN INDIA.rar`, 202 MB), so every border on the map, including
the northern and north-eastern ones, is the official depiction.

```bash
curl -o data/raw/State_District_Subdistrict_PAN_INDIA.rar \
  "https://surveyofindia.gov.in/documents/State_District_Subdistrict_PAN%20INDIA.rar"
python3 build/make_nodata.py     # -> build/nodata-states.geojson (committed)
python3 build/make_india.py      # appends them to india.geojson
```
