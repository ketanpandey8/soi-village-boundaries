"""Village population from Census 2011 -> dist/data/<state>.pop.json

Reads the Census 2011 village-level Primary Census Abstract ("PCA TV", one .xlsx per
district, fetched by data/census_download.py into data/census/<state>/) and writes one
number per village, in the same order as dist/data/<state>.packed.json, or null where the
village has no match. The join is on the LGD code: villages that existed in 2011 kept their
Census 2011 code as their LGD code. Towns are in the Survey of India data too, as polygons under
their Census 2011 town code, so their urban population joins the same way (in Uttar Pradesh
802 of 915 towns, 94% of town population; the rest, Noida the largest, have no polygon).

  python3 build/make_pop.py uttar-pradesh
"""
import glob, json, os, sys

sys.path.insert(0, os.path.dirname(__file__))
import xlsx

ROOT = os.path.join(os.path.dirname(__file__), '..')


def census(slug):
    pop = {}
    files = sorted(glob.glob(os.path.join(ROOT, 'data', 'census', slug, '*.xlsx')))
    if not files:
        sys.exit(f'no census files in data/census/{slug}/ (run data/census_download.py)')
    for f in files:
        for r in xlsx.rows(f):
            # columns: D = town/village code, G = level, I = total/rural/urban, K = total persons
            if (r.get('G'), r.get('I')) in (('VILLAGE', 'Rural'), ('TOWN', 'Urban')):
                pop[r['D'].zfill(6)] = int(r['K'])
    return pop


def main(slug):
    pop = census(slug)
    packed = json.load(open(os.path.join(ROOT, 'dist', 'data', slug + '.packed.json')))
    # a town split into several polygons shows the whole town's population on each
    out = [pop.get(str(p.get('l') or '').zfill(6)) for p in packed['p']]
    hit = sum(v is not None for v in out)
    path = os.path.join(ROOT, 'dist', 'data', slug + '.pop.json')
    with open(path, 'w') as fh:
        json.dump({'src': 'Census 2011', 'p': out}, fh, separators=(',', ':'))
    print(f'{slug}: {hit:,} of {len(out):,} villages matched ({hit / len(out):.1%}), '
          f'{os.path.getsize(path) / 1024:.0f} KB -> {path}')


if __name__ == '__main__':
    main(sys.argv[1])
