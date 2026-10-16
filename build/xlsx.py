"""Read the first sheet of an .xlsx file as dicts of column letter -> text (no openpyxl here)."""
import re, zipfile, xml.etree.ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def rows(path):
    z = zipfile.ZipFile(path)
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(NS + 'si'):
            ss.append(''.join(t.text or '' for t in si.iter(NS + 't')))
    sheet = sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet'))[0]
    for r in ET.fromstring(z.read(sheet)).iter(NS + 'row'):
        out = {}
        for c in r.iter(NS + 'c'):
            col = re.match(r'[A-Z]+', c.get('r')).group()
            v, t = c.find(NS + 'v'), c.get('t')
            if t == 'inlineStr':
                out[col] = ''.join(x.text or '' for x in c.iter(NS + 't'))
            elif v is None:
                out[col] = ''
            elif t == 's':
                out[col] = ss[int(v.text)]
            else:
                out[col] = v.text
        yield out
