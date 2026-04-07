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
_SOUR_RE = re.compile(r'^0 (@[^@]+@) SOUR\b')
_TAG_RE  = re.compile(r'^(\d+) (\w+)(?: (.*))?$')
_YEAR_RE = re.compile(r'\b(\d{4})\b')

_EVENT_TAGS = frozenset({
    'BIRT', 'DEAT', 'BURI', 'RESI', 'OCCU', 'CHR', 'BAPM',
    'NATU', 'IMMI', 'EVEN', 'FACT', 'NATI', 'RELI', 'TITL',
    'ADOP', 'EDUC', 'RETI', 'DIV', 'CONF', 'PROB',
})


# ---------------------------------------------------------------------------
# GEDCOM parsing
# ---------------------------------------------------------------------------

def parse_gedcom(path: str) -> tuple[dict, dict, dict]:
    """
    Returns (indis, fams).
      indis: {xref: {name, birth_year, death_year, famc, sex, events, notes}}
        events: list of {tag, type, date, place}
        notes:  list of str (CONT lines joined with \\n)
      fams:  {xref: {'husb': str|None, 'wife': str|None}}
    """
    with open(path, encoding='utf-8') as f:
        lines = [ln.rstrip('\n') for ln in f]

    indis: dict  = {}
    fams: dict   = {}
    sources: dict = {}   # xref -> title
    ctx           = None   # ('indi', xref) or ('fam', xref) or ('sour', xref)
    current_evt   = None   # current event dict being built
    current_note  = None   # index into notes[] for CONT assembly

    for line in lines:
        m = _INDI_RE.match(line)
        if m:
            xref = m.group(1)
            indis[xref] = {
                'name': None, 'birth_year': None, 'death_year': None,
                'famc': None, 'sex': None, 'events': [], 'notes': [], 'source_xrefs': [],
            }
            ctx          = ('indi', xref)
            current_evt  = None
            current_note = None
            continue

        m = _FAM_RE.match(line)
        if m:
            xref = m.group(1)
            fams[xref] = {'husb': None, 'wife': None}
            ctx          = ('fam', xref)
            current_evt  = None
            current_note = None
            continue

        m = _SOUR_RE.match(line)
        if m:
            xref = m.group(1)
            sources[xref] = None
            ctx          = ('sour', xref)
            current_evt  = None
            current_note = None
            continue

        if line.startswith('0 '):
            ctx          = None
            current_evt  = None
            current_note = None
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
                current_evt = current_note = None
            elif lvl == 1 and tag == 'SEX':
                indis[xref]['sex'] = val
                current_evt = current_note = None
            elif lvl == 1 and tag in _EVENT_TAGS:
                evt = {'tag': tag, 'type': None, 'date': None, 'place': None, 'note': val if val else None}
                indis[xref]['events'].append(evt)
                current_evt  = evt
                current_note = None
            elif lvl == 2 and current_evt is not None:
                if tag == 'DATE':
                    current_evt['date'] = val
                    ym = _YEAR_RE.search(val)
                    if ym:
                        yr = ym.group(1)
                        if current_evt['tag'] == 'BIRT' and indis[xref]['birth_year'] is None:
                            indis[xref]['birth_year'] = yr
                        elif current_evt['tag'] == 'DEAT' and indis[xref]['death_year'] is None:
                            indis[xref]['death_year'] = yr
                elif tag == 'PLAC':
                    current_evt['place'] = val
                elif tag == 'TYPE':
                    current_evt['type'] = val
                elif tag == 'NOTE':
                    current_evt['note'] = val
            elif lvl == 1 and tag == 'NOTE':
                indis[xref]['notes'].append(val)
                current_note = len(indis[xref]['notes']) - 1
                current_evt  = None
            elif lvl == 2 and tag in ('CONT', 'CONC') and current_note is not None:
                sep = '\n' if tag == 'CONT' else ''
                indis[xref]['notes'][current_note] += sep + val
            elif lvl == 1 and tag == 'FAMC' and indis[xref]['famc'] is None:
                indis[xref]['famc'] = val
                current_evt = current_note = None
            elif lvl == 1 and tag == 'SOUR' and val.startswith('@'):
                if val not in indis[xref]['source_xrefs']:
                    indis[xref]['source_xrefs'].append(val)
                current_evt = current_note = None
            elif lvl == 1:
                current_evt = current_note = None

        elif ctx[0] == 'fam':
            xref = ctx[1]
            if lvl == 1 and tag == 'HUSB':
                fams[xref]['husb'] = val
            elif lvl == 1 and tag == 'WIFE':
                fams[xref]['wife'] = val

        elif ctx[0] == 'sour':
            xref = ctx[1]
            if lvl == 1 and tag == 'TITL':
                sources[xref] = val

    return indis, fams, sources


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


def build_ancestor_json(root_xref: str, indis: dict, fams: dict, sources: dict | None = None) -> dict:
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
        src_titles = []
        if sources:
            for sxref in info.get('source_xrefs', []):
                title = sources.get(sxref)
                if title and title not in src_titles:
                    src_titles.append(title)
        result[key] = {
            'name':       info['name'] or '?',
            'birth_year': info['birth_year'],
            'death_year': info['death_year'],
            'sex':        info['sex'],
            'events':     info['events'],
            'notes':      info['notes'],
            'sources':    src_titles,
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
/* ── Detail panel shell ─────────────────────────────────── */
#detail-panel {
  position: fixed; top: var(--header-h, 45px); right: 0;
  width: 480px; height: calc(100vh - var(--header-h, 45px));
  background: #1e293b; border-left: 1px solid #334155;
  overflow-y: auto; z-index: 100;
  transform: translateX(480px); transition: transform 0.22s ease;
  display: flex; flex-direction: column; }
#detail-panel.panel-open { transform: translateX(0); }
/* ── Header ─────────────────────────────────────────────── */
#detail-header {
  padding: 0; border-bottom: 1px solid #334155;
  position: sticky; top: 0; background: #1e293b; z-index: 1;
  display: flex; align-items: flex-start; }
#detail-accent-bar { width: 4px; flex-shrink: 0; align-self: stretch; background: #475569; }
#detail-header-inner { flex: 1; padding: 14px 8px 14px 14px; min-width: 0; }
#detail-name { font-size: 17px; font-weight: 700; color: #f1f5f9;
               line-height: 1.3; margin-bottom: 10px; }
.sex-sym { font-size: 13px; color: #64748b; margin-left: 5px; }
#detail-aka { font-size: 12px; color: #64748b; font-style: italic;
              margin-bottom: 10px; line-height: 1.5; }
#detail-close { background: none; border: none; color: #475569;
                font-size: 20px; cursor: pointer; padding: 14px 14px 14px 4px;
                line-height: 1; flex-shrink: 0; align-self: flex-start; }
#detail-close:hover { color: #f1f5f9; }
#home-btn { position: fixed; bottom: 24px; right: 24px; z-index: 200;
            background: #1e293b; border: 1px solid #334155; border-radius: 50%;
            width: 44px; height: 44px; display: flex; align-items: center;
            justify-content: center; cursor: pointer; color: #94a3b8;
            font-size: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.4); }
#home-btn:hover { background: #334155; color: #f1f5f9; }
/* ── Lifespan bar ───────────────────────────────────────── */
#detail-lifespan-row { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.lifespan-year { color: #94a3b8; white-space: nowrap; flex-shrink: 0; }
.lifespan-bar-track { flex: 1; height: 4px; background: #334155;
                      border-radius: 2px; overflow: hidden; }
.lifespan-bar-fill { height: 100%; border-radius: 2px; }
.lifespan-age { font-size: 11px; color: #64748b; white-space: nowrap; flex-shrink: 0; }
/* ── Body ───────────────────────────────────────────────── */
#detail-body { padding: 18px 20px 28px 20px; flex: 1; }
/* ── Notes (shown first) ────────────────────────────────── */
#detail-notes { margin-bottom: 20px; }
.notes-toggle { display: flex; align-items: center; gap: 6px; background: none; border: none;
  cursor: pointer; color: #64748b; font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.08em; padding: 0 0 10px 0; }
.notes-toggle:hover { color: #94a3b8; }
.notes-toggle-arrow { font-size: 8px; transition: transform 0.2s; }
.notes-toggle.open .notes-toggle-arrow { transform: rotate(90deg); }
.note-card { font-size: 13px; color: #f1f5f9; line-height: 1.75;
             white-space: pre-wrap; overflow-wrap: break-word; word-break: break-word;
             padding: 10px 14px;
             background: rgba(254, 249, 195, 0.1); border-radius: 6px;
             border-left: 3px solid rgba(254, 243, 160, 0.35);
             margin-bottom: 10px; }
.note-card a { color: #fde68a; text-underline-offset: 2px; }
/* ── Timeline ───────────────────────────────────────────── */
#detail-timeline { position: relative; padding-left: 28px; }
.timeline-spine { position: absolute; left: 7px; top: 6px; bottom: 6px; width: 2px;
  background: linear-gradient(to bottom, #334155 0%, transparent 100%); }
.evt-entry { position: relative; margin-bottom: 14px; padding-left: 4px; }
.evt-dot { position: absolute; left: -24px; top: 5px;
           width: 10px; height: 10px; border-radius: 50%; border: 2px solid #1e293b; }
.evt-dot.dot-anchor { width: 12px; height: 12px; left: -25px; top: 4px; }
.evt-year  { font-size: 12px; font-weight: 700; color: #94a3b8;
             margin-right: 7px; font-variant-numeric: tabular-nums; }
.evt-prose { font-size: 13px; color: #e2e8f0; line-height: 1.5; font-weight: 500; }
.evt-meta  { font-size: 11px; color: #64748b; margin-top: 2px; line-height: 1.4; padding-left: 0; }
.evt-note-inline { font-size: 11px; color: #94a3b8; margin-top: 3px; font-style: italic; }
/* ── Also lived in ──────────────────────────────────────── */
#detail-also-lived { position: relative; padding-left: 28px; }
#detail-also-lived.has-content { margin-top: 16px; border-top: 1px solid #334155; padding-top: 16px; }
#detail-sources { margin-top: 16px; border-top: 1px solid #334155; padding-top: 14px; }
.sources-heading { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
  color: #475569; margin-bottom: 8px; display: block; }
.source-item { font-size: 11px; color: #64748b; line-height: 1.5; padding: 2px 0; }
.source-list { margin: 4px 0 0 0; padding-left: 18px; }
.source-list .source-item { padding: 1px 0; }
.also-lived-heading { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
  color: #475569; margin-bottom: 10px; margin-top: 16px; display: block; }
.also-lived-heading:first-child { margin-top: 0; }
/* ── Section divider ────────────────────────────────────── */
.timeline-section-label {
  font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
  color: #475569; margin: 18px 0 10px -28px; padding-left: 28px;
  display: block; border-top: 1px solid #1e3a52; padding-top: 12px; }
.timeline-section-label:first-child { margin-top: 0; border-top: none; padding-top: 0; }
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
<button id="home-btn" title="Return to root">&#x2302;</button>
<div id="detail-panel">
  <div id="detail-header">
    <div id="detail-accent-bar"></div>
    <div id="detail-header-inner">
      <h2 id="detail-name"></h2>
      <div id="detail-aka"></div>
      <div id="detail-lifespan-row"></div>
    </div>
    <button id="detail-close" title="Close">&#x2715;</button>
  </div>
  <div id="detail-body">
    <div id="detail-notes"></div>
    <div id="detail-timeline">
      <div class="timeline-spine"></div>
      <div id="detail-events"></div>
    </div>
    <div id="detail-also-lived"></div>
    <div id="detail-sources"></div>
  </div>
</div>
<script>
const ANCESTORS = __ANCESTORS_JSON__;

const EVENT_LABELS = {
  BIRT:'Birth', DEAT:'Death', BURI:'Burial', RESI:'Residence',
  OCCU:'Occupation', CHR:'Christening', BAPM:'Baptism',
  NATU:'Naturalization', IMMI:'Immigration', NATI:'Nationality',
  RELI:'Religion', TITL:'Title', ADOP:'Adoption', EDUC:'Education',
  RETI:'Retirement', DIV:'Divorce', CONF:'Confirmation', PROB:'Probate',
  EVEN:'Event', FACT:'Fact',
};

function escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function linkify(s) {
  // Match URLs in the raw string before HTML-escaping, so & in query strings isn't truncated
  const URL_RE = /https?:\/\/\S+/g;
  let result = '', last = 0, m;
  while ((m = URL_RE.exec(s)) !== null) {
    result += escHtml(s.slice(last, m.index));
    const rawUrl = m[0].replace(/[.,;:!?)]+$/, ''); // strip trailing punctuation
    const href   = rawUrl.replace(/&amp;/g, '&');   // decode any HTML entities in URL
    result += `<a href="${escHtml(href)}" target="_blank" rel="noopener">${escHtml(rawUrl)}</a>`;
    last = m.index + rawUrl.length;
  }
  result += escHtml(s.slice(last));
  return result;
}

// ── Date / place formatting ──────────────────────────────────────────────────
const _MONTH_ABBR = {
  JAN:'January', FEB:'February', MAR:'March',    APR:'April',
  MAY:'May',     JUN:'June',     JUL:'July',     AUG:'August',
  SEP:'September',OCT:'October', NOV:'November', DEC:'December'
};

function fmtDate(raw) {
  if (!raw) return '';
  const s = raw.trim().toUpperCase();
  let prefix = '', rest = s;
  if      (s.startsWith('ABT ')) { prefix = 'around ';  rest = s.slice(4); }
  else if (s.startsWith('BEF ')) { prefix = 'before ';  rest = s.slice(4); }
  else if (s.startsWith('AFT ')) { prefix = 'after ';   rest = s.slice(4); }
  else if (s.startsWith('CAL ') || s.startsWith('EST ')) { prefix = 'around '; rest = s.slice(4); }
  const bet = rest.match(/^BET\\s+(.+?)\\s+AND\\s+(.+)$/);
  if (bet) return fmtDate(bet[1]) + ' – ' + fmtDate(bet[2]);
  const dmy = rest.match(/^(\\d{1,2})\\s+([A-Z]{3})\\s+(\\d{4})$/);
  if (dmy) return prefix + (_MONTH_ABBR[dmy[2]] || dmy[2]) + ' ' + dmy[1] + ', ' + dmy[3];
  const my = rest.match(/^([A-Z]{3})\\s+(\\d{4})$/);
  if (my) return prefix + (_MONTH_ABBR[my[1]] || my[1]) + ' ' + my[2];
  const y = rest.match(/^(\\d{4})$/);
  if (y) return prefix + y[1];
  return prefix + raw;
}

function fmtPlace(raw) {
  if (!raw) return '';
  const parts = raw.split(',').map(s => s.trim()).filter(Boolean);
  if (parts.length <= 1) return parts[0] || '';
  const last = parts[parts.length - 1];
  const isUSA = /^(USA|United States|United States of America)$/i.test(last);
  if (isUSA) {
    // City, [County], State, USA → City, State
    const city  = parts[0];
    const state = parts.length >= 3 ? parts[parts.length - 2] : '';
    if (!state) return city;
    const stateOut = /^District of Columbia$/i.test(state) ? 'D.C.' : state;
    return city + ', ' + stateOut;
  }
  // Non-US: City, Country (first + last, skipping intermediate parts)
  return parts.length === 2 ? parts.join(', ') : parts[0] + ', ' + last;
}

// ── Per-event prose + meta ───────────────────────────────────────────────────
function buildProse(evt) {
  const date  = fmtDate(evt.date);
  const place = evt.place || '';
  const short = fmtPlace(place);
  const type  = evt.type || '';
  const full  = place !== short ? place : '';
  const meta  = () => [full, date].filter(Boolean).join(' \\u00b7 ');
  switch (evt.tag) {
    case 'BIRT': return { prose: short ? `Born in ${short}` : (date ? `Born ${date}` : 'Birth'),          meta: meta() };
    case 'DEAT': return { prose: short ? `Died in ${short}` : (date ? `Died ${date}` : 'Death'),          meta: meta() };
    case 'BURI': return { prose: short ? `Buried in ${short}` : (date ? `Buried ${date}` : 'Burial'),    meta: meta() };
    case 'RESI': return { prose: short ? `Lived in ${short}` : (date ? `Lived ${date}` : 'Residence'),   meta: meta() };
    case 'OCCU': {
      return { prose: type ? `Worked as ${type}` : 'Occupation', meta: meta() };
    }
    case 'IMMI': return { prose: short ? `Immigrated to ${short}` : (date ? `Immigrated ${date}` : 'Immigration'), meta: meta() };
    case 'NATU': return { prose: short ? `Naturalized in ${short}` : (date ? `Naturalized ${date}` : 'Naturalization'), meta: meta() };
    case 'ADOP': return { prose: date ? `Adopted ${date}` : 'Adoption', meta: short };
    case 'EDUC': return { prose: type ? `Education: ${type}` : (short ? `Studied at ${short}` : 'Education'), meta: meta() };
    case 'RETI': return { prose: date ? `Retired ${date}` : 'Retirement', meta: short };
    case 'TITL': return { prose: type ? `Held title: ${type}` : 'Title', meta: date };
    case 'CHR':  return { prose: short ? `Christened in ${short}` : (date ? `Christened ${date}` : 'Christening'), meta: meta() };
    case 'BAPM': return { prose: short ? `Baptized in ${short}` : (date ? `Baptized ${date}` : 'Baptism'), meta: meta() };
    case 'CONF': return { prose: short ? `Confirmed in ${short}` : (date ? `Confirmed ${date}` : 'Confirmation'), meta: meta() };
    case 'NATI': return { prose: type ? `Nationality: ${type}` : (short ? `Nationality: ${short}` : 'Nationality'), meta: date };
    case 'RELI': return { prose: type ? `Religion: ${type}` : 'Religion', meta: date };
    case 'DIV':  return { prose: date ? `Divorced ${date}` : 'Divorce', meta: short };
    case 'FACT': {
      if (type && type.toUpperCase() === 'AKA')
        return { prose: `Also known as: ${evt.note || ''}`, meta: date };
      return { prose: type || short || 'Fact', meta: date };
    }
    case 'PROB': return { prose: short ? `Probate in ${short}` : (date ? `Probate ${date}` : 'Probate'), meta: meta() };
    default: {
      return {
        prose: type || (short ? short : (EVENT_LABELS[evt.tag] || evt.tag)),
        meta:  [full, date].filter(Boolean).join(' \\u00b7 ')
      };
    }
  }
}

function dotColor(tag) {
  switch (tag) {
    case 'BIRT': case 'DEAT':              return '#f1f5f9';
    case 'BURI':                           return '#94a3b8';
    case 'RESI':                           return '#38bdf8';
    case 'OCCU': case 'RETI':             return '#fbbf24';
    case 'IMMI': case 'NATU':             return '#34d399';
    case 'CHR':  case 'BAPM': case 'CONF': case 'RELI': return '#2dd4bf';
    case 'EDUC':                           return '#a78bfa';
    default:                               return '#64748b';
  }
}

const _YR_RE = /\\b(\\d{4})\\b/;
function sortEvents(events) {
  return [...events].sort((a, b) => {
    if (a.tag === 'BIRT') return -1;
    if (b.tag === 'BIRT') return 1;
    const isEnd = t => t === 'DEAT' || t === 'BURI';
    if (isEnd(a.tag) && !isEnd(b.tag)) return 1;
    if (!isEnd(a.tag) && isEnd(b.tag)) return -1;
    const ya = a.date ? ((_YR_RE.exec(a.date) || [, 0])[1] | 0) : 0;
    const yb = b.date ? ((_YR_RE.exec(b.date) || [, 0])[1] | 0) : 0;
    return ya - yb;
  });
}

// ── Detail panel ─────────────────────────────────────────────────────────────
let _openDetailKey = null;

function showDetail(k) {
  if (_openDetailKey === k) { closeDetail(); return; }
  const data  = ANCESTORS[k];
  const panel = document.getElementById('detail-panel');

  // Accent color by sex
  const accent = {'M':'#3b82f6','F':'#a855f7'}[data.sex] || '#475569';
  document.getElementById('detail-accent-bar').style.background = accent;

  // Name + sex symbol
  const sexSym = {'M':'\\u2642','F':'\\u2640'}[data.sex] || '';
  document.getElementById('detail-name').innerHTML =
    escHtml(data.name) + (sexSym ? `<span class="sex-sym">${sexSym}</span>` : '');

  // Lifespan bar
  const by = data.birth_year ? parseInt(data.birth_year) : null;
  const dy = data.death_year ? parseInt(data.death_year) : null;
  const lifespanRow = document.getElementById('detail-lifespan-row');
  if (by) {
    const span = (dy && dy > by) ? dy - by : null;
    const fillStyle = dy
      ? `background: linear-gradient(90deg, ${accent}, #6366f1); width: 100%;`
      : `background: linear-gradient(90deg, ${accent}, transparent); width: 100%;`;
    lifespanRow.innerHTML =
      `<span class="lifespan-year">${by}</span>` +
      `<div class="lifespan-bar-track"><div class="lifespan-bar-fill" style="${fillStyle}"></div></div>` +
      `<span class="lifespan-year">${dy || '\\u2014'}</span>` +
      (span ? `<span class="lifespan-age">~${span} years</span>` : '');
  } else {
    lifespanRow.innerHTML = '';
  }

  // AKA aliases — shown under the name, not in the timeline
  const akaDiv = document.getElementById('detail-aka');
  const akaNames = (data.events || [])
    .filter(e => e.tag === 'FACT' && (e.type || '').toUpperCase() === 'AKA' && e.note)
    .map(e => escHtml(e.note));
  akaDiv.innerHTML = akaNames.length ? akaNames.join(' \xb7 ') : '';

  // Notes — collapsible
  const notesDiv = document.getElementById('detail-notes');
  const notes = data.notes || [];
  if (notes.length) {
    const count = notes.length;
    const label = count === 1 ? '1 Note' : `${count} Notes`;
    const cards = notes.map(n =>
      `<div class="note-card" style="border-left-color:${accent}">${linkify(n)}</div>`
    ).join('');
    notesDiv.innerHTML =
      `<button class="notes-toggle open" onclick="this.classList.toggle('open');` +
      `this.nextElementSibling.style.display=this.classList.contains('open')?'block':'none'">` +
      `<span class="notes-toggle-arrow">&#9658;</span>${escHtml(label)}</button>` +
      `<div class="notes-body">${cards}</div>`;
  } else {
    notesDiv.innerHTML = '';
  }

  // Timeline events (AKA excluded — shown above; undated RESI shown below)
  const evtDiv  = document.getElementById('detail-events');
  const alsoLivedDiv = document.getElementById('detail-also-lived');
  const allVisible = (data.events || []).filter(e =>
    (e.date || e.place || e.note || e.type) &&
    !(e.tag === 'FACT' && (e.type || '').toUpperCase() === 'AKA')
  );
  const undatedResi = allVisible.filter(e => e.tag === 'RESI' && !e.date);
  const undatedOccu = allVisible.filter(e => e.tag === 'OCCU' && !e.date);
  const undatedNati = allVisible.filter(e => e.tag === 'NATI' && !e.date);
  const visible = allVisible.filter(e =>
    !(e.tag === 'RESI' && !e.date) &&
    !(e.tag === 'OCCU' && !e.date) &&
    !(e.tag === 'NATI' && !e.date)
  );
  const sorted  = sortEvents(visible);

  if (!sorted.length) { evtDiv.innerHTML = ''; }
  else {
    let html = '', lastSection = '';
    for (const evt of sorted) {
      let section = 'Life';
      const evtYear = evt.date ? ((_YR_RE.exec(evt.date) || [,0])[1] | 0) : null;
      if (evt.tag === 'BIRT' || (evtYear && by && evtYear <= by + 18)) section = 'Early Life';
      else if (evt.tag === 'DEAT' || evt.tag === 'BURI') section = 'Later Life';

      if (section !== lastSection) {
        html += `<span class="timeline-section-label">${escHtml(section)}</span>`;
        lastSection = section;
      }

      const { prose, meta } = buildProse(evt);
      const color   = dotColor(evt.tag);
      const isAnch  = evt.tag === 'BIRT' || evt.tag === 'DEAT';
      const dotCls  = isAnch ? 'evt-dot dot-anchor' : 'evt-dot';
      const noteInl = evt.note
        ? `<div class="evt-note-inline">${escHtml(evt.note)}</div>` : '';
      const yearStr = evtYear ? `<span class="evt-year">${evtYear}</span>` : '';
      html +=
        `<div class="evt-entry">` +
        `<div class="${dotCls}" style="background:${color}"></div>` +
        `<div class="evt-prose">${yearStr}${escHtml(prose)}</div>` +
        (meta && meta !== String(evtYear) ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
        noteInl +
        `</div>`;
    }
    evtDiv.innerHTML = html;
  }

  // Undated bottom sections — rendered as timeline-style rows, no spine
  function undatedRows(evts) {
    return evts.map(evt => {
      const { prose, meta } = buildProse(evt);
      const color   = dotColor(evt.tag);
      const noteInl = evt.note ? `<div class="evt-note-inline">${escHtml(evt.note)}</div>` : '';
      return `<div class="evt-entry">` +
        `<div class="evt-dot" style="background:${color}"></div>` +
        `<div class="evt-prose">${escHtml(prose)}</div>` +
        (meta ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
        noteInl +
        `</div>`;
    }).join('');
  }

  let bottomHtml = '';
  if (undatedResi.length) bottomHtml += `<span class="also-lived-heading">Also lived in</span>` + undatedRows(undatedResi);
  if (undatedOccu.length) bottomHtml += `<span class="also-lived-heading">Occupation</span>`    + undatedRows(undatedOccu);
  if (undatedNati.length) bottomHtml += `<span class="also-lived-heading">Nationality</span>`   + undatedRows(undatedNati);

  alsoLivedDiv.innerHTML = bottomHtml;
  alsoLivedDiv.className = bottomHtml ? 'has-content' : '';

  const sourcesDiv = document.getElementById('detail-sources');
  const srcs = data.sources || [];
  sourcesDiv.innerHTML = srcs.length
    ? `<span class="sources-heading">Sources</span>` +
      (srcs.length === 1
        ? `<div class="source-item">${escHtml(srcs[0])}</div>`
        : `<ul class="source-list">${srcs.map(s => `<li class="source-item">${escHtml(s)}</li>`).join('')}</ul>`)
    : '';

  panel.classList.add('panel-open');
  _openDetailKey = k;
}

function closeDetail() {
  document.getElementById('detail-panel').classList.remove('panel-open');
  _openDetailKey = null;
}

document.getElementById('detail-close').addEventListener('click', closeDetail);
document.getElementById('home-btn').addEventListener('click', () => {
  closeDetail();
  visibleKeys.clear();
  for (let g = 0; g <= 4; g++) {
    const start = Math.pow(2, g), end = Math.pow(2, g + 1);
    for (let k = start; k < end; k++) { if (k in ANCESTORS) visibleKeys.add(k); }
  }
  scale = 1;
  render();
  fitAndCenter();
});

const NODE_W = 175, NODE_H = 60, H_GAP = 10, V_GAP = 80;
const MARGIN_X = 90, MARGIN_TOP = 50, BTN_ZONE = 28;

const visibleKeys = new Set();

// Pan / zoom state
let tx = 0, ty = 0, scale = 1;
let didDrag = false;

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

// Compact layout: each node gets only as much horizontal space as its visible subtree needs.
let _posCache = new Map();

function _subtreeWidth(k, cache) {
  if (cache.has(k)) return cache.get(k);
  const fk = 2*k, mk = 2*k+1;
  const hasFather = visibleKeys.has(fk);
  const hasMother = visibleKeys.has(mk);
  let w;
  if (!hasFather && !hasMother) {
    w = 1;
  } else {
    const fw = hasFather ? _subtreeWidth(fk, cache) : 0;
    const mw = hasMother ? _subtreeWidth(mk, cache) : 0;
    w = Math.max(1, fw + mw);
  }
  cache.set(k, w);
  return w;
}

function computePositions() {
  _posCache = new Map();
  const maxGen = maxVisibleGen();
  const slotW  = NODE_W + H_GAP;
  const wCache = new Map();
  _subtreeWidth(1, wCache);

  function layout(k, xStart) {
    const w  = wCache.get(k) || 1;
    const fk = 2*k, mk = 2*k+1;
    const hasFather = visibleKeys.has(fk);
    const hasMother = visibleKeys.has(mk);
    const g  = genOf(k);
    const x  = xStart + (w * slotW - NODE_W) / 2;
    const y  = MARGIN_TOP + BTN_ZONE + (maxGen - g) * (NODE_H + V_GAP);
    _posCache.set(k, {x, y});
    let offset = xStart;
    if (hasFather) { const fw = wCache.get(fk) || 1; layout(fk, offset); offset += fw * slotW; }
    if (hasMother) { layout(mk, offset); }
  }
  layout(1, MARGIN_X);
}

function nodePos(k) {
  return _posCache.get(k) || {x: 0, y: 0};
}

function hasHiddenParents(k) {
  return ((2 * k) in ANCESTORS || (2 * k + 1) in ANCESTORS) &&
         !visibleKeys.has(2 * k) && !visibleKeys.has(2 * k + 1);
}

function hasVisibleParents(k) {
  return visibleKeys.has(2 * k) || visibleKeys.has(2 * k + 1);
}

function collapseNode(k) {
  function removeSubtree(n) {
    visibleKeys.delete(n);
    if (visibleKeys.has(2 * n)) removeSubtree(2 * n);
    if (visibleKeys.has(2 * n + 1)) removeSubtree(2 * n + 1);
  }
  if (visibleKeys.has(2 * k))     removeSubtree(2 * k);
  if (visibleKeys.has(2 * k + 1)) removeSubtree(2 * k + 1);
  render();
  fitAndCenter();
}

function fitAndCenter() {
  computePositions();
  const vp = document.getElementById('viewport');
  let maxX = 0, maxY = 0;
  for (const {x, y} of _posCache.values()) {
    maxX = Math.max(maxX, x + NODE_W);
    maxY = Math.max(maxY, y + NODE_H);
  }
  const treeW = maxX + MARGIN_X;
  const treeH = maxY + 20;
  const scaleX = (vp.clientWidth  * 0.96) / treeW;
  const scaleY = (vp.clientHeight * 0.92) / treeH;
  scale = Math.min(1, scaleX, scaleY);
  const { x: rootX, y: rootY } = nodePos(1);
  tx = vp.clientWidth  / 2 - (rootX + NODE_W / 2) * scale;
  ty = vp.clientHeight - (rootY + NODE_H) * scale - 30;
  applyTransform();
}

function expandNode(k) {
  if ((2 * k) in ANCESTORS)     visibleKeys.add(2 * k);
  if ((2 * k + 1) in ANCESTORS) visibleKeys.add(2 * k + 1);
  render();
  fitAndCenter();
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
  computePositions();
  const maxGen = maxVisibleGen();
  const canvas = document.getElementById('canvas');
  canvas.innerHTML = '';

  // Connector lines (drawn below nodes)
  for (const k of visibleKeys) {
    const { x: cx, y: cy } = nodePos(k);
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
      const { x: fx, y: fy } = nodePos(fk);
      canvas.appendChild(svgEl('line', {
        x1: fx + NODE_W / 2, y1: fy + NODE_H,
        x2: fx + NODE_W / 2, y2: midY,
        stroke: '#475569', 'stroke-width': 1.5
      }));
    }
    if (hasMother) {
      const { x: mx, y: my } = nodePos(mk);
      canvas.appendChild(svgEl('line', {
        x1: mx + NODE_W / 2, y1: my + NODE_H,
        x2: mx + NODE_W / 2, y2: midY,
        stroke: '#475569', 'stroke-width': 1.5
      }));
    }
    if (hasFather && hasMother) {
      const { x: fx } = nodePos(fk);
      const { x: mx } = nodePos(mk);
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
    const firstK = [...visibleKeys].find(k => genOf(k) === g);
    const { y } = nodePos(firstK);
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
    const { x, y } = nodePos(k);
    const data   = ANCESTORS[k];
    const isRoot = (k === 1);
    const isMale = (k % 2 === 0 && k > 1);
    const fill   = isRoot ? '#2563eb' : (isMale ? '#1e40af' : '#6d28d9');

    const nodeG = svgEl('g', { cursor: 'pointer' });
    nodeG.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!didDrag) showDetail(k);
    });

    const nodeRect = svgEl('rect', {
      x, y, width: NODE_W, height: NODE_H,
      rx: 8, fill, opacity: 0.95
    });
    nodeG.appendChild(nodeRect);

    const displayName = data.name.length > 21
      ? data.name.slice(0, 19) + '\\u2026'
      : data.name;
    const nameEl = svgEl('text', {
      x: x + NODE_W / 2, y: y + 22,
      'text-anchor': 'middle', fill: 'white',
      'font-size': 13, 'font-weight': 600,
      'font-family': 'system-ui, sans-serif',
      'pointer-events': 'none'
    });
    nameEl.textContent = displayName;
    nodeG.appendChild(nameEl);

    const years = [
      data.birth_year ? 'b.' + data.birth_year : '',
      data.death_year ? 'd.' + data.death_year : ''
    ].filter(Boolean).join('  ');
    if (years) {
      const yrEl = svgEl('text', {
        x: x + NODE_W / 2, y: y + 42,
        'text-anchor': 'middle', fill: 'rgba(255,255,255,0.65)',
        'font-size': 11,
        'font-family': 'system-ui, sans-serif',
        'pointer-events': 'none'
      });
      yrEl.textContent = years;
      nodeG.appendChild(yrEl);
    }
    canvas.appendChild(nodeG);

    // Expand / collapse buttons
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
        'text-anchor': 'middle', fill: 'white', 'font-size': 12,
        'font-family': 'system-ui, sans-serif', 'pointer-events': 'none'
      });
      btxt.textContent = '\\u25b2';
      canvas.appendChild(btxt);
    } else if (hasVisibleParents(k)) {
      const bx = x + NODE_W / 2 - 14;
      const by = y - BTN_ZONE + 2;
      const btn = svgEl('rect', {
        x: bx, y: by, width: 28, height: 22,
        rx: 5, fill: '#475569', cursor: 'pointer'
      });
      btn.addEventListener('click', (e) => { e.stopPropagation(); collapseNode(k); });
      canvas.appendChild(btn);
      const btxt = svgEl('text', {
        x: x + NODE_W / 2, y: by + 14,
        'text-anchor': 'middle', fill: 'white', 'font-size': 12,
        'font-family': 'system-ui, sans-serif', 'pointer-events': 'none'
      });
      btxt.textContent = '\\u25bc';
      canvas.appendChild(btxt);
    }
  }

  applyTransform();
}

function init() {
  // Show generations 0-2 initially
  for (let g = 0; g <= 4; g++) {
    const start = Math.pow(2, g);
    const end   = Math.pow(2, g + 1);
    for (let k = start; k < end; k++) {
      if (k in ANCESTORS) visibleKeys.add(k);
    }
  }

  const vp  = document.getElementById('viewport');
  const hdr = document.querySelector('header');
  const hdrH = hdr.offsetHeight;
  vp.style.height = (window.innerHeight - hdrH) + 'px';
  document.documentElement.style.setProperty('--header-h', hdrH + 'px');

  render();
  fitAndCenter();
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
  dragging = true; didDrag = false;
  dragX0 = e.clientX; dragY0 = e.clientY; tx0 = tx; ty0 = ty;
  document.getElementById('viewport').classList.add('dragging');
});
window.addEventListener('mousemove', (e) => {
  if (!dragging) return;
  if (Math.hypot(e.clientX - dragX0, e.clientY - dragY0) > 4) didDrag = true;
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
    indis, fams, sources = parse_gedcom(path_in)
    root_xref   = _find_person(person, indis)
    if not root_xref:
        raise ValueError(f'Person not found: {person!r}')

    ancestor_data = build_ancestor_json(root_xref, indis, fams, sources)
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
