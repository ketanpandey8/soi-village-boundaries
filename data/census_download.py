"""Fetch Census 2011 village-level Primary Census Abstract files ("PCA TV", one .xlsx per
district) from the ORGI Census Digital Library into data/census/<state>/.

  python3 data/census_download.py uttar-pradesh "Uttar Pradesh" 6318 6396

The catalog ids for a state's districts are consecutive; scan a range wider than needed and
only the entries titled "PCA TV ... <State name> - District ..." are kept. The site's TLS
certificate chain is incomplete, so verification is skipped (public statistics, no secrets).
"""
import os, re, ssl, sys, urllib.request

BASE = 'https://censusindia.gov.in/nada/index.php/catalog/'
CTX = ssl._create_unverified_context()


def get(url, timeout=60):
    with urllib.request.urlopen(url, context=CTX, timeout=timeout) as r:
        return r.read()


def main(slug, state, lo, hi):
    out = os.path.join(os.path.dirname(__file__), 'census', slug)
    os.makedirs(out, exist_ok=True)
    n = 0
    for cid in range(int(lo), int(hi) + 1):
        dest = os.path.join(out, f'{cid}.xlsx')
        if os.path.exists(dest) and os.path.getsize(dest):
            n += 1
            continue
        page = get(BASE + str(cid)).decode('utf-8', 'replace')
        t = re.search(r'<title>([^<]*)', page)
        if not t or 'PCA TV' not in t.group(1) or f'{state} - District' not in t.group(1):
            continue
        m = re.search(rf'catalog/{cid}/download/\d+', get(BASE + f'{cid}/related-materials').decode('utf-8', 'replace'))
        if not m:
            print('no download link:', cid, t.group(1))
            continue
        data = get('https://censusindia.gov.in/nada/index.php/' + m.group(), timeout=180)
        if not data.startswith(b'PK'):
            print('not an xlsx:', cid)
            continue
        open(dest, 'wb').write(data)
        n += 1
        print(cid, t.group(1).split(' - District ')[-1])
    print(f'{n} district files in {out}')


if __name__ == '__main__':
    main(*sys.argv[1:5])
