#!/usr/bin/env python3
"""UI consistency check for build/app.html (run by build/check.sh).

The app keeps one small design system in its stylesheet: a type scale (--fs-*), a corner
scale (--r-*), colour tokens per theme, and a handful of shared controls. This fails when
anything steps outside it, so a new button or label can't quietly bring its own look:

  - font sizes, corner radii and weights come from the scales
  - colours are defined only in the theme token blocks
  - every button is one of the shared controls (or a known one-off)
  - retired patterns (inline text links, inline expanders, old close buttons) stay gone
  - every class in the markup or script templates has a style or is a script hook
  - every id the script looks up exists, and every aria-controls points at an element
  - every overlay is a labelled dialog, and every button has a name

Prints one line per problem and exits 1 if there are any.
"""
import os, re, sys

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.html")
src = open(PATH, encoding="utf-8").read()
css = src[src.index("<style>"):src.index("</style>")]
page = src[src.index("</style>"):]                      # markup and script
tokens, rules = css[:css.index("  *{box-sizing")], css[css.index("  *{box-sizing"):]
problems = []
bad = problems.append

def decls(prop):
    """(selector, value) for every declaration of prop in the rules."""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", rules):
        sel, body = m.group(1).strip(), m.group(2)
        for v in re.findall(prop + r":([^;}]+)", body):
            yield sel, v.strip()

# scales
for sel, v in decls("font-size"):
    ok = re.fullmatch(r"var\(--fs-[a-z]+\)|inherit|[.\d]+em", v) or ("#labels" in sel and v.endswith("px"))
    if not ok: bad(f"font-size {v} in `{sel}`: use a --fs-* token")
for sel, v in decls("border-radius"):
    if not all(re.fullmatch(r"var\(--r-[a-z]+\)|50%|0", p) for p in v.split()):
        bad(f"border-radius {v} in `{sel}`: use a --r-* token")
for sel, v in decls("font-weight"):
    if v not in ("400", "600", "700") and not (v == "500" and "#labels" in sel):
        bad(f"font-weight {v} in `{sel}`: use 400, 600 or 700")

# colours live only in the theme blocks
for c in sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)", rules))):
    bad(f"literal colour {c} outside the theme tokens")

# every token used is defined
defined = set(re.findall(r"(--[\w-]+):", tokens)) | {"--vo", "--sh", "--inset", "--peek"}
for t in sorted(set(re.findall(r"var\((--[\w-]+)", css))):
    if t not in defined: bad(f"token {t} is used but never defined")

# buttons: shared controls, or one-offs with their own reviewed styles
SHARED = {"tbtn", "xbtn", "pbtn", "cbtn", "act", "res", "nrow", "mi", "gh"}
ONE_OFF_IDS = {"moreBtn", "statsBtn", "zin", "zout", "zreset", "locBtn"}
for m in re.finditer(r"<button\b([^>]*)>", page):
    attrs = m.group(1)
    cls = set(re.findall(r'class="([^"$]*)"', attrs)[0].split()) if 'class="' in attrs else set()
    bid = re.findall(r'id="([\w-]+)"', attrs)
    if not (cls & SHARED or set(bid) & ONE_OFF_IDS):
        bad(f"button without a shared control class: <button{attrs[:80]}>")

# retired patterns
for old in ("linkbtn", 'class="dx"', 'class="x"', 'class="hq"', "fmts", 'class="chip"', 'class="note"', 'class="go"'):
    if old in src: bad(f"retired pattern still present: {old}")

# classes used in markup / templates are styled, or are script hooks
HOOKS = {"ic", "sr-only", "close", "share", "sat", "dlt", "more", "od", "none", "nr", "ttl", "opts", "chev",
         "show", "searching", "vsearch", "in-state", "embed", "dragging", "nlist", "rn", "rm", "sw", "nm", "ct", "nodat",
         "grp", "zoom", "pop", "seg", "gl", "trow", "sheet-head", "side-sec", "side-head", "field", "list", "rsum", "rempty",
         "sub", "acts", "card-head", "vname", "nbrs", "empty", "gapline", "ok", "qt", "bar", "txt", "cred", "lbl", "pri", "on",
         "active", "selrow", "nodata", "row", "res", "act", "tbtn", "xbtn", "pbtn", "cbtn", "mi", "gh", "nrow"}
styled = set(re.findall(r"\.([a-zA-Z][\w-]*)", re.sub(r"[\d.]+(?:rem|em|px|s)\b|\.\d+", "", css)))
used = set()
for m in re.finditer(r'class="([^"]*)"', page):
    used |= {c for c in re.sub(r"\$\{[^}]*\}", " ", m.group(1)).split() if re.fullmatch(r"[a-zA-Z][\w-]*", c)}
for c in sorted(used - styled - HOOKS):
    bad(f"class .{c} is used but has no style (add one, or list it as a hook in build/ui_check.py)")

# ids and aria wiring
ids = set(re.findall(r'id="([\w-]+)"', page))
for r in sorted(set(re.findall(r'\$\("([\w-]+)"\)', page)) - ids):
    bad(f'$("{r}") has no element')
for r in sorted(set(re.findall(r'aria-controls="([\w-]+)"', page)) - ids):
    bad(f'aria-controls="{r}" has no element')
for m in re.finditer(r'<div id="(\w+)" class="pop"([^>]*)>', page):
    if 'role="dialog"' not in m.group(2) or "aria-label=" not in m.group(2):
        bad(f"overlay #{m.group(1)} needs role=dialog and an aria-label")

# every button has a name: text inside, or an aria-label
for m in re.finditer(r"<button\b([^>]*)>(.*?)</button>", page, re.S):
    text = re.sub(r"<svg.*?</svg>|<[^>]+>", "", m.group(2)).strip()
    if not text and "aria-label=" not in m.group(1):
        bad(f"button has no text or aria-label: <button{m.group(1)[:80]}>")

for p in problems: print("  " + p)
sys.exit(1 if problems else 0)
