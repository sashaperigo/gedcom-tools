#!/usr/bin/env python3
"""
viz_ancestors.py — Generate an interactive ancestor pedigree chart from a GEDCOM file.

Renders a self-contained HTML file showing an Ahnentafel pedigree tree.
The starting person appears at the bottom; ancestors are arranged above by generation.
Click ▲ on any person to expand their ancestors further back in history.

Usage:
  python viz_ancestors.py yourfile.ged --person "Name or @Xref@"
  python viz_ancestors.py yourfile.ged --person "@I123@" --output chart.html
"""

import argparse
import html as html_mod
import json
import math
import os
import re
import sys

_INDI_RE = re.compile(r'^0 (@[^@]+@) INDI\b')
_FAM_RE  = re.compile(r'^0 (@[^@]+@) FAM\b')
_TAG_RE  = re.compile(r'^(\d+) (\w+)(?: (.*))?$')
_YEAR_RE = re.compile(r'\b(\d{4})\b')


# ---------------------------------------------------------------------------
# GEDCOM parsing
# ---------------------------------------------------------------------------

def parse_gedcom(path: str) -> tuple[dict, dict]:
    """
    Returns (indis, fams).
      indis: {xref: {'name': str|None, 'birth_year': str|None, 'death_year': str|None, 'famc': str|None}}
      fams:  {xref: {'husb': str|None, 'wife': str|None}}
    """
    with open(path, encoding='utf-8') as f:
        lines = [ln.rstrip('\n') for ln in f]

    indis: dict = {}
    fams: dict  = {}
    ctx   = None   # ('indi', xref) or ('fam', xref)
    event = None   # 'BIRT' or 'DEAT' when inside that event block

    for line in lines:
        m = _INDI_RE.match(line)
        if m:
            xref = m.group(1)
            indis[xref] = {'name': None, 'birth_year': None, 'death_year': None, 'famc': None}
            ctx   = ('indi', xref)
            event = None
            continue

        m = _FAM_RE.match(line)
        if m:
            xref = m.group(1)
            fams[xref] = {'husb': None, 'wife': None}
            ctx   = ('fam', xref)
            event = None
            continue

        if line.startswith('0 '):
            ctx   = None
            event = None
            continue

        if ctx is None:
            continue

        tm = _TAG_RE.match(line)
        if not tm:
            continue
        lvl = int(tm.group(1))
        tag = tm.group(2)
        val = (tm.group(3) or '').strip()

        if ctx[0] == 'indi':
            xref = ctx[1]
            if lvl == 1 and tag == 'NAME' and indis[xref]['name'] is None:
                name = re.sub(r'/', '', val)
                name = re.sub(r'\s+', ' ', name).strip()
                indis[xref]['name'] = name
            elif lvl == 1 and tag in ('BIRT', 'DEAT'):
                event = tag
            elif lvl == 2 and tag == 'DATE' and event in ('BIRT', 'DEAT'):
                ym = _YEAR_RE.search(val)
                if ym:
                    yr = ym.group(1)
                    if event == 'BIRT':
                        indis[xref]['birth_year'] = yr
                    else:
                        indis[xref]['death_year'] = yr
            elif lvl == 1 and tag == 'FAMC' and indis[xref]['famc'] is None:
                indis[xref]['famc'] = val
                event = None
            elif lvl == 1:
                event = None

        elif ctx[0] == 'fam':
            xref = ctx[1]
            if lvl == 1 and tag == 'HUSB':
                fams[xref]['husb'] = val
            elif lvl == 1 and tag == 'WIFE':
                fams[xref]['wife'] = val

    return indis, fams


# ---------------------------------------------------------------------------
# Ancestor graph
# ---------------------------------------------------------------------------

def get_parents(xref: str, indis: dict, fams: dict) -> tuple[str | None, str | None]:
    """Return (father_xref, mother_xref) or (None, None) if unknown."""
    famc = indis.get(xref, {}).get('famc')
    if not famc or famc not in fams:
        return None, None
    fam = fams[famc]
    return fam['husb'], fam['wife']


def build_ancestor_json(root_xref: str, indis: dict, fams: dict) -> dict:
    """
    Walk all ancestors recursively.
    Returns dict keyed by Ahnentafel number (int):
      {1: {name, birth_year, death_year}, 2: {...}, ...}
    Missing ancestors have no entry.
    """
    result: dict = {}
    stack = [(root_xref, 1)]
    while stack:
        xref, key = stack.pop()
        if not xref or xref not in indis:
            continue
        info = indis[xref]
        result[key] = {
            'name':       info['name'] or '?',
            'birth_year': info['birth_year'],
            'death_year': info['death_year'],
        }
        father, mother = get_parents(xref, indis, fams)
        stack.append((father, 2 * key))
        stack.append((mother, 2 * key + 1))
    return result


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ancestors of __ROOT_NAME__</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0f172a; color: white;
       font-family: system-ui, -apple-system, sans-serif;
       overflow: hidden; }
header { padding: 12px 20px; background: #1e293b;
         border-bottom: 1px solid #334155;
         display: flex; align-items: center; gap: 16px; }
header h1 { font-size: 16px; font-weight: 600; }
.hint { font-size: 12px; color: #94a3b8; }
#viewport { overflow: hidden; cursor: grab; user-select: none; }
#viewport.dragging { cursor: grabbing; }
#tree { display: block; width: 100%; height: 100%; }
</style>
</head>
<body>
<header>
  <h1>Ancestors of __ROOT_NAME__</h1>
  <span class="hint">Pinch to zoom · Two-finger drag to pan · Click ▲ to expand ancestors</span>
</header>
<div id="viewport">
<svg id="tree" xmlns="http://www.w3.org/2000/svg">
  <g id="canvas"></g>
</svg>
</div>
<script>
const ANCESTORS = __ANCESTORS_JSON__;

const NODE_W = 220, NODE_H = 60, H_GAP = 28, V_GAP = 80;
const MARGIN_X = 90, MARGIN_TOP = 50, BTN_ZONE = 28;

const visibleKeys = new Set();

// Pan / zoom state
let tx = 0, ty = 0, scale = 1;

function applyTransform() {
  document.getElementById('canvas').setAttribute(
    'transform', `translate(${tx}, ${ty}) scale(${scale})`
  );
}

function genOf(k) { return Math.floor(Math.log2(k)); }
function slotOf(k) { return k - Math.pow(2, genOf(k)); }

function maxVisibleGen() {
  let mx = 0;
  for (const k of visibleKeys) mx = Math.max(mx, genOf(k));
  return mx;
}

function nodePos(k, maxGen) {
  const g    = genOf(k);
  const slot = slotOf(k);
  const slotW = NODE_W + H_GAP;
  const slotsPerNode = Math.pow(2, maxGen - g);
  const x = MARGIN_X + slot * slotsPerNode * slotW + (slotsPerNode * slotW - NODE_W) / 2;
  const y = MARGIN_TOP + BTN_ZONE + (maxGen - g) * (NODE_H + V_GAP);
  return { x, y };
}

function hasHiddenParents(k) {
  return ((2 * k) in ANCESTORS || (2 * k + 1) in ANCESTORS) &&
         !visibleKeys.has(2 * k) && !visibleKeys.has(2 * k + 1);
}

function expandNode(k) {
  if ((2 * k) in ANCESTORS)     visibleKeys.add(2 * k);
  if ((2 * k + 1) in ANCESTORS) visibleKeys.add(2 * k + 1);
  render();
  // Pan up so the newly added generation is just visible at the top
  const maxGen = maxVisibleGen();
  const { y: newGenY } = nodePos(Math.pow(2, maxGen), maxGen);
  const screenY = ty + newGenY * scale;
  if (screenY < BTN_ZONE * scale + 20) {
    ty = BTN_ZONE * scale + 20 - newGenY * scale;
    applyTransform();
  }
}

function svgEl(tag, attrs) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

const GEN_LABELS = ['You', 'Parents', 'Grandparents', 'Great-grandparents'];
function genLabel(g) {
  if (g < GEN_LABELS.length) return GEN_LABELS[g];
  return (g - 1) + '× Great-grandparents';
}

function render() {
  const maxGen = maxVisibleGen();
  const canvas = document.getElementById('canvas');
  canvas.innerHTML = '';

  // Connector lines (drawn below nodes)
  for (const k of visibleKeys) {
    const { x: cx, y: cy } = nodePos(k, maxGen);
    const fk = 2 * k, mk = 2 * k + 1;
    const hasFather = visibleKeys.has(fk);
    const hasMother = visibleKeys.has(mk);
    if (!hasFather && !hasMother) continue;

    const midY    = cy - V_GAP / 2;
    const childCx = cx + NODE_W / 2;

    canvas.appendChild(svgEl('line', {
      x1: childCx, y1: cy, x2: childCx, y2: midY,
      stroke: '#475569', 'stroke-width': 1.5
    }));

    if (hasFather) {
      const { x: fx, y: fy } = nodePos(fk, maxGen);
      canvas.appendChild(svgEl('line', {
        x1: fx + NODE_W / 2, y1: fy + NODE_H,
        x2: fx + NODE_W / 2, y2: midY,
        stroke: '#475569', 'stroke-width': 1.5
      }));
    }
    if (hasMother) {
      const { x: mx, y: my } = nodePos(mk, maxGen);
      canvas.appendChild(svgEl('line', {
        x1: mx + NODE_W / 2, y1: my + NODE_H,
        x2: mx + NODE_W / 2, y2: midY,
        stroke: '#475569', 'stroke-width': 1.5
      }));
    }
    if (hasFather && hasMother) {
      const { x: fx } = nodePos(fk, maxGen);
      const { x: mx } = nodePos(mk, maxGen);
      canvas.appendChild(svgEl('line', {
        x1: fx + NODE_W / 2, y1: midY,
        x2: mx + NODE_W / 2, y2: midY,
        stroke: '#475569', 'stroke-width': 1.5
      }));
    }
  }

  // Generation labels (left side)
  const gensSeen = new Set([...visibleKeys].map(genOf));
  for (const g of gensSeen) {
    const { y } = nodePos(Math.pow(2, g), maxGen);
    const lbl = svgEl('text', {
      x: 4, y: y + NODE_H / 2,
      fill: '#64748b', 'font-size': 11,
      'font-family': 'system-ui, sans-serif',
      'dominant-baseline': 'middle'
    });
    lbl.textContent = genLabel(g);
    canvas.appendChild(lbl);
  }

  // Person nodes
  for (const k of visibleKeys) {
    const { x, y } = nodePos(k, maxGen);
    const data   = ANCESTORS[k];
    const isRoot = (k === 1);
    const isMale = (k % 2 === 0 && k > 1);
    const fill   = isRoot ? '#2563eb' : (isMale ? '#1e40af' : '#6d28d9');

    canvas.appendChild(svgEl('rect', {
      x, y, width: NODE_W, height: NODE_H,
      rx: 8, fill, opacity: 0.95
    }));

    const displayName = data.name.length > 27
      ? data.name.slice(0, 25) + '\\u2026'
      : data.name;
    const nameEl = svgEl('text', {
      x: x + NODE_W / 2, y: y + 22,
      'text-anchor': 'middle', fill: 'white',
      'font-size': 13, 'font-weight': 600,
      'font-family': 'system-ui, sans-serif'
    });
    nameEl.textContent = displayName;
    canvas.appendChild(nameEl);

    const years = [
      data.birth_year ? 'b.' + data.birth_year : '',
      data.death_year ? 'd.' + data.death_year : ''
    ].filter(Boolean).join('  ');
    if (years) {
      const yrEl = svgEl('text', {
        x: x + NODE_W / 2, y: y + 42,
        'text-anchor': 'middle', fill: 'rgba(255,255,255,0.65)',
        'font-size': 11,
        'font-family': 'system-ui, sans-serif'
      });
      yrEl.textContent = years;
      canvas.appendChild(yrEl);
    }

    // Expand button
    if (hasHiddenParents(k)) {
      const bx = x + NODE_W / 2 - 14;
      const by = y - BTN_ZONE + 2;
      const btn = svgEl('rect', {
        x: bx, y: by, width: 28, height: 22,
        rx: 5, fill: '#059669', cursor: 'pointer'
      });
      btn.addEventListener('click', (e) => { e.stopPropagation(); expandNode(k); });
      canvas.appendChild(btn);

      const btxt = svgEl('text', {
        x: x + NODE_W / 2, y: by + 14,
        'text-anchor': 'middle', fill: 'white',
        'font-size': 12,
        'font-family': 'system-ui, sans-serif',
        'pointer-events': 'none'
      });
      btxt.textContent = '\\u25b2';
      canvas.appendChild(btxt);
    }
  }

  applyTransform();
}

function init() {
  // Show generations 0-2 initially
  for (let g = 0; g <= 2; g++) {
    const start = Math.pow(2, g);
    const end   = Math.pow(2, g + 1);
    for (let k = start; k < end; k++) {
      if (k in ANCESTORS) visibleKeys.add(k);
    }
  }

  const vp  = document.getElementById('viewport');
  const hdr = document.querySelector('header');
  vp.style.height = (window.innerHeight - hdr.offsetHeight) + 'px';

  render();

  // Center root node horizontally; place it near the bottom of the viewport
  const maxGen = maxVisibleGen();
  const { x, y } = nodePos(1, maxGen);
  tx = vp.clientWidth  / 2 - (x + NODE_W / 2) * scale;
  ty = vp.clientHeight - (y + NODE_H)          * scale - 30;
  applyTransform();
}

// ---- Pinch-to-zoom + two-finger pan (trackpad wheel events) ----
document.getElementById('tree').addEventListener('wheel', (e) => {
  e.preventDefault();
  const svg  = document.getElementById('tree');
  const rect = svg.getBoundingClientRect();
  if (e.ctrlKey) {
    // Pinch gesture: zoom towards cursor
    const factor   = 1 - e.deltaY * 0.005;
    const newScale = Math.max(0.08, Math.min(6, scale * factor));
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    tx = mx - (mx - tx) * (newScale / scale);
    ty = my - (my - ty) * (newScale / scale);
    scale = newScale;
  } else {
    // Two-finger scroll: pan
    tx -= e.deltaX;
    ty -= e.deltaY;
  }
  applyTransform();
}, { passive: false });

// ---- Mouse drag pan ----
let dragging = false, dragX0 = 0, dragY0 = 0, tx0 = 0, ty0 = 0;

document.getElementById('tree').addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  dragging = true; dragX0 = e.clientX; dragY0 = e.clientY; tx0 = tx; ty0 = ty;
  document.getElementById('viewport').classList.add('dragging');
});
window.addEventListener('mousemove', (e) => {
  if (!dragging) return;
  tx = tx0 + e.clientX - dragX0;
  ty = ty0 + e.clientY - dragY0;
  applyTransform();
});
window.addEventListener('mouseup', () => {
  dragging = false;
  document.getElementById('viewport').classList.remove('dragging');
});

window.addEventListener('load', init);
window.addEventListener('resize', () => {
  const vp  = document.getElementById('viewport');
  const hdr = document.querySelector('header');
  vp.style.height = (window.innerHeight - hdr.offsetHeight) + 'px';
});
</script>
</body>
</html>
"""


def render_html(ancestor_data: dict, root_name: str) -> str:
    """Return a complete self-contained HTML string."""
    safe_name = html_mod.escape(root_name)
    json_str  = json.dumps(ancestor_data)
    return (
        _HTML_TEMPLATE
        .replace('__ROOT_NAME__', safe_name)
        .replace('__ANCESTORS_JSON__', json_str)
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _find_person(person: str, indis: dict) -> str | None:
    """Find INDI xref by exact xref or case-insensitive name substring."""
    if person in indis:
        return person
    p_lower = person.lower()
    for xref, info in indis.items():
        if info['name'] and p_lower in info['name'].lower():
            return xref
    return None


def viz_ancestors(path_in: str, person: str, path_out: str) -> dict:
    """
    Generate an ancestor pedigree HTML chart.

    Returns dict with:
      'root_name'      : display name of the starting person
      'ancestor_count' : total number of individuals in the chart
      'generations'    : depth of the deepest known ancestor (gen 0 = root)
    """
    indis, fams = parse_gedcom(path_in)
    root_xref   = _find_person(person, indis)
    if not root_xref:
        raise ValueError(f'Person not found: {person!r}')

    ancestor_data = build_ancestor_json(root_xref, indis, fams)
    root_name     = ancestor_data.get(1, {}).get('name', '?')

    html = render_html(ancestor_data, root_name)
    with open(path_out, 'w', encoding='utf-8') as f:
        f.write(html)

    max_gen = max(math.floor(math.log2(k)) for k in ancestor_data) if ancestor_data else 0
    return {
        'root_name':      root_name,
        'ancestor_count': len(ancestor_data),
        'generations':    max_gen + 1,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate an interactive ancestor pedigree chart from a GEDCOM file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to .ged file')
    parser.add_argument('--person', '-p', required=True,
                        help='Starting person: xref (@I123@) or name substring')
    parser.add_argument('--output', '-o', default='ancestors.html',
                        help='Output HTML file (default: ancestors.html)')
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    try:
        result = viz_ancestors(args.gedfile, args.person, args.output)
    except ValueError as e:
        sys.exit(f'Error: {e}')

    print(f'Root     : {result["root_name"]}')
    print(f'Ancestors: {result["ancestor_count"]}')
    print(f'Depth    : {result["generations"]} generation{"s" if result["generations"] != 1 else ""}')
    print(f'Written  : {args.output}')


if __name__ == '__main__':
    main()
