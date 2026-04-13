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
    ctx               = None   # ('indi', xref) or ('fam', xref) or ('sour', xref)
    current_evt       = None   # current event dict being built
    current_note      = None   # index into notes[] for CONT assembly
    current_sour_xref = None   # xref of the 1 SOUR citation currently being parsed
    secondary_name_n  = 0      # counter for secondary NAME records within current INDI

    for line in lines:
        m = _INDI_RE.match(line)
        if m:
            xref = m.group(1)
            indis[xref] = {
                'name': None, 'birth_year': None, 'death_year': None,
                'famc': None, 'fams': [], 'sex': None, 'events': [], 'notes': [], 'source_xrefs': [], 'source_urls': {},
            }
            ctx                = ('indi', xref)
            current_evt        = None
            current_note       = None
            secondary_name_n   = 0
            continue

        m = _FAM_RE.match(line)
        if m:
            xref = m.group(1)
            fams[xref] = {'husb': None, 'wife': None, 'chil': []}
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
            if lvl == 1 and tag != 'SOUR':
                current_sour_xref = None
            if lvl == 1 and tag == 'NAME' and indis[xref]['name'] is None:
                name = re.sub(r'/', '', html_mod.unescape(val))
                name = re.sub(r'\s+', ' ', name).strip()
                indis[xref]['name'] = name
                current_evt = current_note = None
            elif lvl == 1 and tag == 'NAME' and indis[xref]['name'] is not None:
                # Secondary NAME record — treat as an AKA alias (FACT/AKA)
                alias = re.sub(r'/', '', html_mod.unescape(val))
                alias = re.sub(r'\s+', ' ', alias).strip()
                evt = {'tag': 'FACT', 'type': 'AKA', 'date': None, 'place': None,
                       'cause': None, 'addr': None, 'note': alias, 'inline_val': None,
                       'age': None, '_name_record': True, '_name_occurrence': secondary_name_n}
                secondary_name_n += 1
                indis[xref]['events'].append(evt)
                current_evt  = evt
                current_note = None
            elif lvl == 1 and tag == 'SEX':
                indis[xref]['sex'] = val
                current_evt = current_note = None
            elif lvl == 1 and tag in _EVENT_TAGS:
                # For tags where the inline value IS the semantic type (e.g. "1 OCCU Consul",
                # "1 TITL Knight", "1 NATI French"), seed type from it.  A later 2 TYPE sub-tag
                # will override.  EVEN/FACT carry no inline value and use 2 TYPE exclusively.
                _INLINE_TYPE_TAGS = frozenset({'OCCU', 'TITL', 'NATI', 'RELI', 'EDUC'})
                inline_type = html_mod.unescape(val) if val and tag in _INLINE_TYPE_TAGS else None
                initial_note = None if tag in _INLINE_TYPE_TAGS else (html_mod.unescape(val) if val else None)
                evt = {'tag': tag, 'type': inline_type, 'date': None, 'place': None, 'cause': None, 'addr': None, 'note': initial_note, 'inline_val': val if val else None, 'age': None}
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
                    current_evt['place'] = html_mod.unescape(val)
                elif tag == 'TYPE':
                    current_evt['type'] = html_mod.unescape(val)
                elif tag == 'CAUS':
                    current_evt['cause'] = html_mod.unescape(val)
                elif tag == 'ADDR':
                    current_evt['addr'] = html_mod.unescape(val)
                elif tag == 'NOTE':
                    current_evt['note'] = html_mod.unescape(val)
                elif tag == 'AGE':
                    current_evt['age'] = val
            elif lvl == 1 and tag == 'NOTE':
                indis[xref]['notes'].append(html_mod.unescape(val))
                current_note = len(indis[xref]['notes']) - 1
                current_evt  = None
            elif lvl == 2 and tag in ('CONT', 'CONC') and current_note is not None:
                sep = '\n' if tag == 'CONT' else ''
                indis[xref]['notes'][current_note] += sep + html_mod.unescape(val)
            elif lvl == 1 and tag == 'FAMC' and indis[xref]['famc'] is None:
                indis[xref]['famc'] = val
                current_evt = current_note = None
            elif lvl == 1 and tag == 'FAMS':
                indis[xref]['fams'].append(val)
                current_evt = current_note = None
            elif lvl == 1 and tag == 'SOUR' and val.startswith('@'):
                if val not in indis[xref]['source_xrefs']:
                    indis[xref]['source_xrefs'].append(val)
                current_sour_xref = val
                current_evt = current_note = None
            elif lvl == 3 and tag == 'WWW' and current_sour_xref is not None:
                if current_sour_xref not in indis[xref]['source_urls']:
                    indis[xref]['source_urls'][current_sour_xref] = val
            elif lvl == 1:
                current_evt = current_note = None

        elif ctx[0] == 'fam':
            xref = ctx[1]
            if lvl == 1 and tag == 'HUSB':
                fams[xref]['husb'] = val
                current_evt = None
            elif lvl == 1 and tag == 'WIFE':
                fams[xref]['wife'] = val
                current_evt = None
            elif lvl == 1 and tag == 'CHIL':
                fams[xref]['chil'].append(val)
                current_evt = None
            elif lvl == 1 and tag == 'MARR':
                # If a MARR block was already parsed, keep it rather than overwriting with a
                # bare duplicate (duplicate 1 MARR lines can appear after a merge and would
                # otherwise silently lose sub-tags like ADDR from the original block).
                if fams[xref].get('marr') is None:
                    evt = {'tag': 'MARR', 'type': None, 'date': None, 'place': None, 'note': None, 'age': None, 'addr': None}
                    fams[xref]['marr'] = evt
                else:
                    evt = fams[xref]['marr']
                current_evt = evt
            elif lvl == 2 and current_evt is not None:
                if tag == 'DATE':
                    current_evt['date'] = val
                elif tag == 'PLAC':
                    current_evt['place'] = val
                elif tag == 'ADDR':
                    current_evt['addr'] = val
                elif tag == 'NOTE':
                    current_evt['note'] = val
            elif lvl == 1:
                current_evt = None

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


def build_tree_json(root_xref: str, indis: dict, fams: dict) -> dict:
    """
    Walk all ancestors recursively.
    Returns {ahnentafel_key (int): xref (str)}.
    Missing ancestors have no entry.
    """
    result: dict = {}
    stack = [(root_xref, 1)]
    while stack:
        xref, key = stack.pop()
        if not xref or xref not in indis:
            continue
        result[key] = xref
        father, mother = get_parents(xref, indis, fams)
        stack.append((father, 2 * key))
        stack.append((mother, 2 * key + 1))
    return result


_MONTH_NUM = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
    'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
    'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}

# GEDCOM AGE tag validation
# Format: [<|>] ( YYy [MMm [DDDd]] | MMm [DDDd] | DDDd | CHILD | INFANT | STILLBORN )
# Maximum 12 characters.
_AGE_RE = re.compile(
    r'^[<>]?(?:'
    r'\d+y(?:\s+\d+m(?:\s+\d+d)?|\s+\d+d)?'  # years (+ optional months/days)
    r'|\d+m(?:\s+\d+d)?'                        # months (+ optional days)
    r'|\d+d'                                     # days only
    r'|CHILD|INFANT|STILLBORN'
    r')$',
    re.IGNORECASE,
)


def is_valid_age(s: str) -> bool:
    """Return True if s is a valid GEDCOM AGE tag value.

    Valid examples: '55y', '6m', '14d', '4y 8m 10d', '>55y', '<1y',
                    'INFANT', 'STILLBORN', 'CHILD', '>CHILD'.
    Invalid: 'ABT 55', '55', '55 years', 'BET 50y AND 60y', '4y, 8m', '8m 4y'.
    Maximum field width is 12 characters.
    """
    if not s or len(s.strip()) > 12:
        return False
    return bool(_AGE_RE.match(s.strip()))


def _date_sort_key(date_str: str | None) -> tuple:
    """Return (year, month, day, adjust) tuple for chronological sorting.
    Unknown components default to 0.  BEF sorts just before the date (-1),
    AFT sorts just after (+1).  Handles GEDCOM qualifiers and BET ranges."""
    if not date_str:
        return (0, 0, 0, 0)
    s = date_str.strip().upper()
    adjust = 0
    for prefix in ('ABT ', 'CAL ', 'EST '):
        if s.startswith(prefix):
            s = s[4:]
            break
    else:
        if s.startswith('BEF '):
            s = s[4:]
            adjust = -1
        elif s.startswith('AFT '):
            s = s[4:]
            adjust = 1
    bet = re.match(r'^BET\s+(.+?)\s+AND\s+(.+)$', s)
    if bet:
        s = bet.group(1)
    dmy = re.match(r'^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$', s)
    if dmy:
        return (int(dmy.group(3)), _MONTH_NUM.get(dmy.group(2), 0), int(dmy.group(1)), adjust)
    my = re.match(r'^([A-Z]{3})\s+(\d{4})$', s)
    if my:
        return (int(my.group(2)), _MONTH_NUM.get(my.group(1), 0), 0, adjust)
    yr = re.match(r'^(\d{4})$', s)
    if yr:
        return (int(yr.group(1)), 0, 0, adjust)
    return (0, 0, 0, 0)


def sort_events(events: list) -> list:
    """Sort events chronologically, with fixed pins:
       BIRT first, then general events by date, then DEAT, Death Announcement, BURI, PROB."""
    def key(evt):
        tag = evt.get('tag', '')
        typ = (evt.get('type') or '').lower()
        if tag == 'BIRT':
            order = 0
        elif tag == 'DEAT':
            order = 2
        elif tag == 'EVEN' and ('death announcement' in typ or 'obituar' in typ or 'avis de décès' in typ):
            order = 3
        elif tag == 'BURI':
            order = 4
        elif tag == 'PROB':
            order = 5
        else:
            order = 1
        return (order,) + _date_sort_key(evt.get('date'))
    return sorted(events, key=key)


def _matches_exclusion(evt: dict, excl: dict) -> bool:
    """Return True if evt matches an exclusion entry (same xref checked by caller)."""
    if evt.get('tag') != excl.get('tag'):
        return False
    for field in ('date', 'place', 'type', 'inline_val'):
        excl_val = excl.get(field) or None
        if excl_val is not None and (evt.get(field) or None) != excl_val:
            return False
    return True


def build_people_json(xrefs: set, indis: dict, fams: dict | None = None,
                      sources: dict | None = None,
                      exclude: list | None = None) -> dict:
    """
    Build full person data for a set of xrefs.
    Returns {xref: {name, birth_year, death_year, sex, events, notes, sources}}.
    exclude: list of pending-deletion dicts {xref, tag, date, place, type, inline_val}.
    """
    # Group exclusions by xref for fast lookup
    excl_by_xref: dict[str, list] = {}
    for d in (exclude or []):
        excl_by_xref.setdefault(d['xref'], []).append(d)

    result = {}
    for xref in xrefs:
        info = indis.get(xref)
        if not info:
            continue
        src_list = []
        seen_src_titles: set[str] = set()
        if sources:
            source_urls = info.get('source_urls', {})
            for sxref in info.get('source_xrefs', []):
                title = sources.get(sxref)
                if title and title not in seen_src_titles:
                    seen_src_titles.add(title)
                    src_list.append({'title': title, 'url': source_urls.get(sxref) or None})
        excl_list = excl_by_xref.get(xref, [])
        # Assign per-tag occurrence index before exclusion filtering.
        # Secondary NAME records (_name_record=True) are stored as "1 NAME" in the
        # GEDCOM, not "1 FACT", so they must NOT increment the FACT counter —
        # otherwise genuine FACT tags receive inflated indices and can't be found
        # by _find_event_block(). Name records are edited via openAliasModal using
        # _name_occurrence, so event_idx=None is correct for them.
        tag_counters: dict[str, int] = {}
        tagged_events = []
        for e in info['events']:
            t = e['tag']
            if e.get('_name_record'):
                tagged_events.append({**e, 'event_idx': None})
            else:
                occ = tag_counters.get(t, 0)
                tag_counters[t] = occ + 1
                tagged_events.append({**e, 'event_idx': occ})
        events = [
            e for e in tagged_events
            if not any(_matches_exclusion(e, ex) for ex in excl_list)
        ]
        if fams:
            for fam_xref in info.get('fams', []):
                fam = fams.get(fam_xref, {})
                marr = fam.get('marr')
                if not marr:
                    continue
                spouse_xref = fam.get('wife') if fam.get('husb') == xref else fam.get('husb')
                spouse_name = indis[spouse_xref]['name'] if spouse_xref and spouse_xref in indis else None
                # MARR events live in FAM blocks; event_idx=None marks them as non-editable via INDI
                events.append({**marr, 'event_idx': None, 'spouse': spouse_name,
                               'spouse_xref': spouse_xref, 'fam_xref': fam_xref})
        result[xref] = {
            'name':       info['name'] or '?',
            'birth_year': info['birth_year'],
            'death_year': info['death_year'],
            'sex':        info['sex'],
            'events':     sort_events(events),
            'notes':      info['notes'],
            'sources':    src_list,
        }
    return result


def build_relatives_json(tree: dict, indis: dict, fams: dict) -> dict:
    """
    Return {xref: {siblings: [xref,...], spouses: [xref,...],
    sib_spouses: {sib_xref: [spouse_xref,...]}}} for ALL individuals,
    so lookups work for any person navigated to via search.
    """
    result = {}
    for xref in indis:
        p = indis.get(xref)
        if not p:
            continue
        siblings = []
        famc = p.get('famc')
        if famc and famc in fams:
            for child_xref in fams[famc].get('chil', []):
                if child_xref != xref:
                    siblings.append(child_xref)
        spouses = []
        for fam_xref in p.get('fams', []):
            fam = fams.get(fam_xref, {})
            spouse_xref = fam.get('wife') if fam.get('husb') == xref else fam.get('husb')
            if spouse_xref and spouse_xref in indis:
                spouses.append(spouse_xref)
        sib_spouses = {}
        for sib_xref in siblings:
            sib = indis.get(sib_xref)
            if not sib:
                continue
            sib_sp = []
            for fam_xref in sib.get('fams', []):
                fam = fams.get(fam_xref, {})
                sp_xref = fam.get('wife') if fam.get('husb') == sib_xref else fam.get('husb')
                if sp_xref and sp_xref in indis:
                    sib_sp.append(sp_xref)
            if sib_sp:
                sib_spouses[sib_xref] = sib_sp
        if siblings or spouses:
            entry = {'siblings': siblings, 'spouses': spouses}
            if sib_spouses:
                entry['sib_spouses'] = sib_spouses
            result[xref] = entry
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
#search-container { position: relative; }
#search-input {
  background: #0f172a; border: 1px solid #334155; border-radius: 20px;
  color: #f1f5f9; font-size: 13px; padding: 6px 14px; width: 220px;
  outline: none; transition: border-color 0.15s; }
#search-input:focus { border-color: #3b82f6; }
#search-input::placeholder { color: #475569; }
#search-results {
  position: absolute; top: calc(100% + 4px); right: 0;
  background: #1e293b; border: 1px solid #334155; border-radius: 8px;
  list-style: none; min-width: 280px; max-height: 320px; overflow-y: auto;
  z-index: 500; box-shadow: 0 8px 24px rgba(0,0,0,0.5); display: none; }
#search-results.open { display: block; }
#search-results li {
  padding: 8px 14px; font-size: 13px; color: #cbd5e1; cursor: pointer;
  border-bottom: 1px solid #1e293b; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
#search-results li:last-child { border-bottom: none; }
#search-results li:hover, #search-results li.active {
  background: #334155; color: #f1f5f9; }
#search-results li b { font-weight: 700; color: #f1f5f9; }
#search-results li .srch-dates { color: #64748b; font-size: 12px; margin-left: 4px; }
#viewport { overflow: hidden; cursor: grab; user-select: none; transition: margin-right 0.22s ease; }
#viewport.dragging { cursor: grabbing; }
#tree { display: block; width: 100%; height: 100%; }
/* ── Detail panel shell ─────────────────────────────────── */
#detail-panel {
  position: fixed; top: var(--header-h, 45px); right: 0;
  width: 480px; height: calc(100vh - var(--header-h, 45px));
  background: #1e293b; border-left: 1px solid #334155;
  overflow-y: auto;
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
#detail-header-btns { display: flex; flex-direction: column; align-items: center;
                      flex-shrink: 0; align-self: flex-start; padding: 10px 10px 10px 4px; gap: 6px; }
#detail-close { background: none; border: none; color: #475569;
                font-size: 20px; cursor: pointer; padding: 2px;
                line-height: 1; }
#detail-close:hover { color: #f1f5f9; }
#detail-set-root-btn { background: none; border: 1px solid #334155; border-radius: 5px;
                       color: #475569; font-size: 13px; cursor: pointer; padding: 3px 6px;
                       line-height: 1; white-space: nowrap; }
#detail-set-root-btn:hover { border-color: #3b82f6; color: #3b82f6; }
#home-btn { background: none; border: 1px solid #334155; border-radius: 50%;
            width: 34px; height: 34px; display: flex; align-items: center;
            justify-content: center; cursor: pointer; color: #94a3b8;
            font-size: 18px; flex-shrink: 0; margin-left: auto; }
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
.note-card-wrap { position: relative; }
.note-actions { position: absolute; top: 6px; right: 8px; display: none; gap: 4px; }
.note-card-wrap:hover .note-actions { display: flex; }
.note-action-btn { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
  color: #94a3b8; border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 11px; }
.note-action-btn:hover { background: rgba(255,255,255,0.15); color: #f1f5f9; }
.note-card { font-size: 13px; color: #f1f5f9; line-height: 1.75;
             white-space: pre-wrap; overflow-wrap: break-word; word-break: break-word;
             padding: 10px 14px;
             background: rgba(254, 249, 195, 0.1); border-radius: 6px;
             border-left: 3px solid rgba(254, 243, 160, 0.35);
             margin-bottom: 10px; }
.note-card a { color: #fde68a; text-underline-offset: 2px; }
#note-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 1000; align-items: center; justify-content: center; }
#note-modal-overlay.open { display: flex; }
#note-modal { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
  padding: 20px; width: 520px; max-width: 90vw; }
#note-modal h3 { margin: 0 0 12px; font-size: 14px; color: #94a3b8; font-weight: 600; }
#note-modal textarea { width: 100%; box-sizing: border-box; background: #0f172a;
  border: 1px solid #334155; color: #f1f5f9; border-radius: 6px; padding: 10px;
  font-size: 13px; font-family: inherit; line-height: 1.6; resize: vertical; min-height: 120px; }
.note-modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 12px; }
.note-modal-cancel { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
  color: #94a3b8; border-radius: 6px; padding: 6px 16px; cursor: pointer; }
.note-modal-save { background: #3b82f6; border: none; color: #fff;
  border-radius: 6px; padding: 6px 16px; cursor: pointer; font-weight: 600; }
/* ── Event edit/add modal ────────────────────────────────── */
#event-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 1000; align-items: center; justify-content: center; }
#event-modal-overlay.open { display: flex; }
#event-modal { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
  padding: 20px; width: 520px; max-width: 90vw; max-height: 85vh; overflow-y: auto; }
#event-modal h3 { margin: 0 0 14px; font-size: 14px; color: #94a3b8; font-weight: 600; }
#event-modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
#event-modal-header h3 { margin: 0; font-size: 14px; color: #94a3b8; font-weight: 600; }
#event-modal-close { background: none; border: none; color: #64748b; font-size: 18px; cursor: pointer;
  padding: 2px 6px; border-radius: 4px; line-height: 1; }
#event-modal-close:hover { color: #f1f5f9; background: rgba(255,255,255,0.08); }
.event-modal-field { margin-bottom: 12px; }
.event-modal-field label { display: block; font-size: 11px; color: #64748b;
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
.event-modal-field input, .event-modal-field select, .event-modal-field textarea {
  width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid #334155;
  color: #f1f5f9; border-radius: 6px; padding: 8px 10px;
  font-size: 13px; font-family: inherit; outline: none; }
.event-modal-field input:focus, .event-modal-field select:focus,
.event-modal-field textarea:focus { border-color: #3b82f6; }
.event-modal-field select option { background: #1e293b; }
.event-modal-field textarea { resize: vertical; min-height: 60px; }
.event-modal-note-footer { display: flex; justify-content: flex-end; margin-top: 3px; }
#event-modal-note-count { font-size: 10px; color: #64748b; }
#event-modal-note-count.at-limit { color: #ef4444; font-weight: 600; }
.event-modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.event-modal-cancel { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
  color: #94a3b8; border-radius: 6px; padding: 6px 16px; cursor: pointer; }
.event-modal-save { background: #3b82f6; border: none; color: #fff;
  border-radius: 6px; padding: 6px 16px; cursor: pointer; font-weight: 600; }
.evt-edit-btn { position: absolute; right: 22px; top: 2px; background: none; border: none;
  cursor: pointer; opacity: 0; font-size: 12px; color: #94a3b8; padding: 2px 4px;
  border-radius: 4px; transition: opacity .15s, color .15s; line-height: 1; }
.evt-entry:hover .evt-edit-btn { opacity: 1; }
.evt-edit-btn:hover { color: #3b82f6 !important; }
.add-event-btn { display: flex; align-items: center; gap: 5px; background: none;
  border: 1px dashed #334155; border-radius: 6px; color: #475569; font-size: 12px;
  padding: 5px 12px; cursor: pointer; margin-top: 12px; }
.add-event-btn:hover { border-color: #3b82f6; color: #3b82f6; }
/* ── Nationality pill actions ─────────────────────────────── */
.facts-pill-wrap { position: relative; display: inline-flex; align-items: center; }
.facts-pill-actions { display: none; position: absolute; right: -2px; top: 50%;
  transform: translateY(-50%); gap: 2px; background: #1e293b;
  border: 1px solid #334155; border-radius: 4px; padding: 1px 2px; }
.facts-pill-wrap:hover .facts-pill-actions { display: flex; }
.facts-pill-btn { background: none; border: none; cursor: pointer; font-size: 10px;
  color: #64748b; padding: 1px 3px; border-radius: 3px; line-height: 1; }
.facts-pill-btn:hover { color: #f1f5f9; background: rgba(255,255,255,0.08); }
.facts-pill-btn.del:hover { color: #ef4444; }
/* ── Name edit modal ─────────────────────────────────────── */
#name-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 1000; align-items: center; justify-content: center; }
#name-modal-overlay.open { display: flex; }
#name-modal { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
  padding: 20px; width: 420px; max-width: 90vw; }
#name-modal h3 { margin: 0 0 14px; font-size: 14px; color: #94a3b8; font-weight: 600; }
/* ── Name edit button in detail header ───────────────────── */
.name-edit-btn { background: none; border: none; cursor: pointer; font-size: 12px;
  color: #475569; padding: 2px 6px; border-radius: 4px; margin-left: 6px;
  vertical-align: middle; transition: color .15s; }
.name-edit-btn:hover { color: #3b82f6; }
/* ── AKA alias action buttons ────────────────────────────── */
.aka-entry { display: inline-flex; align-items: center; gap: 2px; }
.aka-btn { background: none; border: none; cursor: pointer; font-size: 10px;
  color: #475569; padding: 1px 3px; border-radius: 3px; line-height: 1;
  vertical-align: middle; }
.aka-btn:hover { color: #f1f5f9; background: rgba(255,255,255,0.08); }
.aka-btn.del:hover { color: #ef4444; }
.marr-card { position: relative; padding: 10px 14px; border-radius: 6px; margin-bottom: 14px;
             background: rgba(232, 121, 249, 0.08);
             border-left: 3px solid rgba(232, 121, 249, 0.5); }
.marr-edit-btn { position: absolute; right: 8px; top: 8px; background: none; border: none;
  cursor: pointer; font-size: 12px; color: #64748b; padding: 2px 4px;
  border-radius: 4px; opacity: 0; transition: opacity .15s, color .15s; }
.marr-card:hover .marr-edit-btn { opacity: 1; }
.marr-edit-btn:hover { color: #3b82f6 !important; }
.marr-card .marr-year { font-size: 12px; font-weight: 700; color: #94a3b8;
                        text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 3px; }
.marr-card .marr-prose { font-size: 15px; font-weight: 600; color: #f1f5f9; line-height: 1.4; }
.marr-card .marr-link { color: #93c5fd; text-decoration: underline; text-decoration-color: rgba(147,197,253,0.4); }
.marr-card:has(.marr-link):hover { background: rgba(219,234,254,0.08); }
.marr-card .marr-meta { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.marr-card .evt-note-inline { font-size: 12px; }
/* ── Alias modal ─────────────────────────────────────────── */
#alias-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 1000; align-items: center; justify-content: center; }
#alias-modal-overlay.open { display: flex; }
#alias-modal { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
  padding: 20px; width: 420px; max-width: 90vw; }
#alias-modal h3 { margin: 0 0 14px; font-size: 14px; color: #94a3b8; font-weight: 600; }
/* ── Timeline ───────────────────────────────────────────── */
#detail-timeline { position: relative; padding-left: 28px; }
.timeline-spine { position: absolute; left: 7px; top: 6px; bottom: 6px; width: 2px;
  background: linear-gradient(to bottom, #334155 0%, transparent 100%); }
.evt-entry { position: relative; margin-bottom: 14px; padding-left: 4px; padding-right: 48px; }
.fact-del { position: absolute; right: 0; top: 2px; background: none; border: none;
  cursor: pointer; opacity: 0; font-size: 13px; color: #94a3b8; padding: 2px 4px;
  border-radius: 4px; transition: opacity .15s, color .15s; line-height: 1; }
.evt-entry:hover .fact-del { opacity: 1; }
.fact-del:hover { color: #ef4444 !important; }
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
#detail-facts { margin-top: 16px; }
#detail-facts.has-content { border-top: 1px solid #334155; padding-top: 14px; }
.facts-heading { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
  color: #475569; margin-bottom: 10px; display: block; }
.facts-subheading { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em;
  color: #64748b; margin-bottom: 5px; margin-top: 10px; display: block; }
.facts-subheading:first-of-type { margin-top: 0; }
.facts-pills { display: flex; flex-wrap: wrap; gap: 6px; }
.facts-pill { font-size: 12px; background: #1c2a1e; border: 1px solid #2d4a31;
  border-radius: 12px; padding: 3px 10px; color: #6ee37a; }
.facts-pill .pill-date { color: #3d6642; font-size: 11px; margin-left: 5px; }
.facts-row-value { font-size: 13px; color: #cbd5e1; margin-bottom: 2px; }
#detail-sources { margin-top: 16px; border-top: 1px solid #334155; padding-top: 14px; }
.sources-heading { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
  color: #475569; margin-bottom: 8px; display: block; }
.source-item { font-size: 11px; color: #64748b; line-height: 1.5; padding: 2px 0; }
.source-list { margin: 4px 0 0 0; padding-left: 18px; }
.source-list .source-item { padding: 1px 0; }
.source-link { color: #64748b; text-underline-offset: 2px; text-decoration-color: rgba(100,116,139,0.4); }
.source-link:hover { color: #93c5fd; text-decoration-color: rgba(147,197,253,0.6); }
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
  <button id="home-btn" title="Return to root">&#x2302;</button>
  <div id="search-container">
    <input id="search-input" type="text" placeholder="Search people…" autocomplete="off" />
    <ul id="search-results"></ul>
  </div>
</header>
<div id="viewport">
<svg id="tree" xmlns="http://www.w3.org/2000/svg">
  <g id="canvas"></g>
</svg>
</div>
<div id="note-modal-overlay" onclick="if(event.target===this)closeNoteModal()">
  <div id="note-modal">
    <h3>Edit Note</h3>
    <textarea id="note-modal-textarea" rows="6" onkeydown="if(event.key==='Escape')closeNoteModal()"></textarea>
    <div class="note-modal-actions">
      <button class="note-modal-cancel" onclick="closeNoteModal()">Cancel</button>
      <button class="note-modal-save" onclick="submitNoteEdit()">Save</button>
    </div>
  </div>
</div>
<div id="event-modal-overlay">
  <div id="event-modal">
    <div id="event-modal-header">
      <h3 id="event-modal-title">Edit Event</h3>
      <button id="event-modal-close" onclick="closeEventModal()" title="Close">&times;</button>
    </div>
    <div class="event-modal-field" id="event-modal-tag-row">
      <label>Event Type</label>
      <select id="event-modal-tag" onkeydown="if(event.key==='Escape')closeEventModal()">
        <option value="BIRT">Birth</option>
        <option value="DEAT">Death</option>
        <option value="BURI">Burial</option>
        <option value="RESI">Residence</option>
        <option value="OCCU">Occupation</option>
        <option value="CHR">Christening</option>
        <option value="BAPM">Baptism</option>
        <option value="NATU">Naturalization</option>
        <option value="IMMI">Immigration</option>
        <option value="EMIG">Emigration</option>
        <option value="EVEN">Event</option>
        <option value="FACT">Fact</option>
        <option value="NATI">Nationality</option>
        <option value="RELI">Religion</option>
        <option value="TITL">Title</option>
        <option value="ADOP">Adoption</option>
        <option value="EDUC">Education</option>
        <option value="RETI">Retirement</option>
        <option value="DIV">Divorce</option>
        <option value="CONF">Confirmation</option>
        <option value="PROB">Probate</option>
      </select>
    </div>
    <div class="event-modal-field" id="event-modal-inline-row">
      <label id="event-modal-inline-label">Value</label>
      <input type="text" id="event-modal-inline" onkeydown="if(event.key==='Escape')closeEventModal()">
    </div>
    <div class="event-modal-field" id="event-modal-type-row">
      <label>Type / Description</label>
      <input type="text" id="event-modal-type" onkeydown="if(event.key==='Escape')closeEventModal()">
    </div>
    <div class="event-modal-field">
      <label>Date</label>
      <input type="text" id="event-modal-date" placeholder="e.g. 26 FEB 1785" onkeydown="if(event.key==='Escape')closeEventModal()">
    </div>
    <div class="event-modal-field">
      <label>Place</label>
      <input type="text" id="event-modal-place" list="plac-suggestions"
             onkeydown="if(event.key==='Escape')closeEventModal()">
      <datalist id="plac-suggestions"></datalist>
    </div>
    <div class="event-modal-field">
      <label>Address</label>
      <input type="text" id="event-modal-addr" list="addr-suggestions"
             placeholder="e.g. Church name or building"
             onkeydown="if(event.key==='Escape')closeEventModal()">
      <datalist id="addr-suggestions"></datalist>
    </div>
    <div class="event-modal-field">
      <label>Note</label>
      <textarea id="event-modal-note" rows="3"
                onkeydown="if(event.key==='Escape')closeEventModal()"
                oninput="_updateNoteCount()"></textarea>
      <div class="event-modal-note-footer">
        <span id="event-modal-note-count"></span>
      </div>
    </div>
    <div class="event-modal-actions">
      <button class="event-modal-cancel" onclick="closeEventModal()">Cancel</button>
      <button class="event-modal-save" id="event-modal-save-btn" onclick="submitEventModal()">Save</button>
    </div>
  </div>
</div>
<div id="alias-modal-overlay" onclick="if(event.target===this)closeAliasModal()">
  <div id="alias-modal">
    <h3 id="alias-modal-title">Add Secondary Name</h3>
    <div class="event-modal-field">
      <label>Name</label>
      <input type="text" id="alias-modal-name" placeholder="e.g. Paul Kemerli"
             onkeydown="if(event.key==='Escape')closeAliasModal();if(event.key==='Enter')submitAliasModal()">
    </div>
    <div class="event-modal-field">
      <label>Name Type</label>
      <select id="alias-modal-type" onkeydown="if(event.key==='Escape')closeAliasModal()">
        <option value="AKA">AKA (Also Known As)</option>
        <option value="Birth">Birth Name</option>
        <option value="Immigrant">Immigrant Name</option>
        <option value="Maiden">Maiden Name</option>
        <option value="Married">Married Name</option>
        <option value="Nickname">Nickname</option>
        <option value="Other">Other</option>
      </select>
    </div>
    <div class="event-modal-actions">
      <button class="event-modal-cancel" onclick="closeAliasModal()">Cancel</button>
      <button class="event-modal-save" id="alias-modal-save-btn" onclick="submitAliasModal()">Add</button>
    </div>
  </div>
</div>
<div id="name-modal-overlay" onclick="if(event.target===this)closeNameModal()">
  <div id="name-modal">
    <h3 id="name-modal-title">Edit Name</h3>
    <div class="event-modal-field">
      <label>Given Name(s)</label>
      <input type="text" id="name-modal-given"
             onkeydown="if(event.key==='Escape')closeNameModal();if(event.key==='Enter')submitNameModal()">
    </div>
    <div class="event-modal-field">
      <label>Surname</label>
      <input type="text" id="name-modal-surname"
             onkeydown="if(event.key==='Escape')closeNameModal();if(event.key==='Enter')submitNameModal()">
    </div>
    <div class="event-modal-actions">
      <button class="event-modal-cancel" onclick="closeNameModal()">Cancel</button>
      <button class="event-modal-save" onclick="submitNameModal()">Save</button>
    </div>
  </div>
</div>
<div id="detail-panel">
  <div id="detail-header">
    <div id="detail-accent-bar"></div>
    <div id="detail-header-inner">
      <h2 id="detail-name"></h2>
      <div id="detail-aka"></div>
      <div id="detail-lifespan-row"></div>
    </div>
    <div id="detail-header-btns">
      <button id="detail-close" title="Close">&#x2715;</button>
      <button id="detail-set-root-btn" title="Browse tree with this person as root">&#x2302;</button>
    </div>
  </div>
  <div id="detail-body">
    <div id="detail-notes"></div>
    <div id="detail-timeline">
      <div class="timeline-spine"></div>
      <div id="detail-events"></div>
    </div>
    <div id="detail-also-lived"></div>
    <div id="detail-facts"></div>
    <div id="detail-sources"></div>
  </div>
</div>
<script>
window.addEventListener('error', e => {
  console.error('[UNCAUGHT ERROR]', e.message, 'at', e.filename + ':' + e.lineno);
});
window.addEventListener('unhandledrejection', e => {
  console.error('[UNHANDLED REJECTION]', e.reason);
});
const TREE = __TREE_JSON__;
const PEOPLE = __PEOPLE_JSON__;
const ALL_PEOPLE = __ALL_PEOPLE_JSON__;
const RELATIVES = __RELATIVES_JSON__;
const PARENTS = __PARENTS_JSON__;
const ROOT_XREF = __ROOT_XREF_JSON__;
const ADDR_BY_PLACE = __ADDR_BY_PLACE_JSON__;
const ALL_PLACES = __ALL_PLACES_JSON__;
let currentTree = Object.assign({}, TREE);
const expandedRelatives = new Set([1]);
let _relPosCache = new Map();
// Maps "${anchorKey}:${sibIdx}" → current spouse index (0-based) for siblings with multiple spouses
let _sibSpouseIdx = new Map();

(function() {
  const input = document.getElementById('search-input');
  const list  = document.getElementById('search-results');
  let activeIdx = -1;

  // Accent-insensitive, lowercase normalization
  function stripAccents(s) { return s.normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }
  function normSearch(s)   { return stripAccents((s || '').toLowerCase()); }

  // Pre-parse each person's name into searchable fields (lazy, cached)
  const _parseCache = new Map();
  function getParsed(p) {
    if (_parseCache.has(p.id)) return _parseCache.get(p.id);
    const raw = p.name || '';
    // Collapse slashes, normalize spaces
    const flat = raw.replace(/\\//g, '').replace(/\\s+/g, ' ').trim();
    // Extract nicknames (text in double quotes)
    const nicks = [];
    const noNicks = flat.replace(/"([^"]+)"/g, (_, n) => { nicks.push(n.trim()); return ' '; })
                        .replace(/\\s+/g, ' ').trim();
    const tokens = noNicks.split(' ').filter(Boolean);
    // Display: title-case the flat form (keeps quotes visible)
    const disp = flat.replace(/\\b\\w/g, c => c.toUpperCase());
    const normDisp = normSearch(flat);  // same .length as flat (accent strip is length-preserving for NFC)
    const result = {
      disp,
      normDisp,
      normFirst: normSearch(tokens[0] || ''),
      normLast:  normSearch(tokens[tokens.length - 1] || ''),
      normNicks: nicks.map(normSearch),
    };
    _parseCache.set(p.id, result);
    return result;
  }

  function personMatches(parsed, qNorm) {
    if (!qNorm) return false;
    // 1. Plain substring anywhere in name (handles most queries)
    if (parsed.normDisp.includes(qNorm)) return true;
    const qToks = qNorm.split(' ').filter(Boolean);
    if (qToks.length === 1) {
      // 2. Single token: check nicknames
      return parsed.normNicks.some(n => n.includes(qToks[0]));
    }
    // 3. Multi-token: first+last match skipping middle names
    //    Query "A B" matches if A is first/nickname and B is last name
    //    Query "A B C" matches if A is first/nickname, C is last, B appears anywhere
    const qFirst = qToks[0];
    const qLast  = qToks[qToks.length - 1];
    const qMid   = qToks.slice(1, -1);
    if (!parsed.normLast.startsWith(qLast)) return false;
    if (!qMid.every(m => parsed.normDisp.includes(m))) return false;
    return parsed.normFirst.startsWith(qFirst) ||
           parsed.normNicks.some(n => n.startsWith(qFirst));
  }

  // Build innerHTML with query tokens bolded in displayStr.
  // normDispStr and displayStr must have equal .length (guaranteed by our parsing).
  function highlightName(displayStr, normDispStr, qNorm) {
    if (!qNorm) return escHtml(displayStr);
    const qToks = qNorm.split(' ').filter(Boolean);
    const regions = [];
    for (const tok of qToks) {
      let i = 0;
      while ((i = normDispStr.indexOf(tok, i)) !== -1) {
        regions.push([i, i + tok.length]);
        i++;
      }
    }
    regions.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const [s, e] of regions) {
      if (merged.length && s <= merged[merged.length - 1][1])
        merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], e);
      else merged.push([s, e]);
    }
    let html = '', last = 0;
    for (const [s, e] of merged) {
      html += escHtml(displayStr.slice(last, s));
      html += '<b>' + escHtml(displayStr.slice(s, e)) + '</b>';
      last = e;
    }
    html += escHtml(displayStr.slice(last));
    return html;
  }

  function renderResults(hits, qNorm) {
    list.innerHTML = '';
    activeIdx = -1;
    hits.forEach(p => {
      const parsed = getParsed(p);
      const li = document.createElement('li');
      const dates = [p.birth_year && `b.\u2009${p.birth_year}`,
                     p.death_year && `d.\u2009${p.death_year}`].filter(Boolean).join(' \u2013 ');
      const nameHtml = highlightName(parsed.disp, parsed.normDisp, qNorm);
      li.innerHTML = nameHtml + (dates ? `<span class="srch-dates">(${escHtml(dates)})</span>` : '');
      li.dataset.id = p.id;
      li.addEventListener('click', () => navigate(p.id));
      list.appendChild(li);
    });
    list.classList.toggle('open', hits.length > 0);
  }

  input.addEventListener('input', () => {
    const qNorm = normSearch(input.value.replace(/\\//g, '').replace(/\\s+/g, ' ').trim());
    if (!qNorm) { list.classList.remove('open'); list.innerHTML = ''; return; }
    const hits = ALL_PEOPLE.filter(p => personMatches(getParsed(p), qNorm)).slice(0, 20);
    renderResults(hits, qNorm);
  });

  input.addEventListener('keydown', e => {
    const items = list.querySelectorAll('li');
    if (!items.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); activeIdx = Math.min(activeIdx + 1, items.length - 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); activeIdx = Math.max(activeIdx - 1, 0); }
    else if (e.key === 'Enter') { if (activeIdx >= 0) navigate(items[activeIdx].dataset.id); return; }
    else if (e.key === 'Escape') { list.classList.remove('open'); list.innerHTML = ''; input.blur(); return; }
    items.forEach((li, i) => li.classList.toggle('active', i === activeIdx));
    if (activeIdx >= 0) items[activeIdx].scrollIntoView({ block: 'nearest' });
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('#search-container')) { list.classList.remove('open'); list.innerHTML = ''; }
  });

  function navigate(personId) {
    list.classList.remove('open');
    list.innerHTML = '';
    input.value = '';
    changeRoot(personId);
  }
})();

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

// ---------------------------------------------------------------------------
// Note edit / delete
// ---------------------------------------------------------------------------
let _noteEditXref = null, _noteEditIdx = null;

async function deleteNote(xref, noteIdx) {
  if (!confirm('Delete this note? The GEDCOM file will be updated immediately (a backup will be saved).')) return;
  try {
    const resp = await fetch('/api/delete_note', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({xref, note_idx: noteIdx, current_person: window._currentPerson || null}),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      _openDetailKey = null;
      showDetail(xref);
    } else {
      alert('Delete failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) { alert('Request failed: ' + e); }
}

function editNote(xref, noteIdx) {
  _noteEditXref = xref;
  _noteEditIdx  = noteIdx;
  document.getElementById('note-modal-textarea').value = (PEOPLE[xref] && PEOPLE[xref].notes[noteIdx]) || '';
  document.getElementById('note-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('note-modal-textarea').focus(), 50);
}

function closeNoteModal() {
  document.getElementById('note-modal-overlay').classList.remove('open');
  _noteEditXref = _noteEditIdx = null;
}

async function submitNoteEdit() {
  const newText  = document.getElementById('note-modal-textarea').value;
  const xref     = _noteEditXref;
  const noteIdx  = _noteEditIdx;
  closeNoteModal();
  try {
    const resp = await fetch('/api/edit_note', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({xref, note_idx: noteIdx, new_text: newText,
                            current_person: window._currentPerson || null}),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      _openDetailKey = null;
      showDetail(xref);
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) { alert('Request failed: ' + e); }
}

// ---------------------------------------------------------------------------
// Event edit / add
// ---------------------------------------------------------------------------
// Tags whose level-1 line carries an inline value (e.g. "1 OCCU Consul")
const _INLINE_TYPE_TAGS = new Set(['OCCU','TITL','NATI','RELI','EDUC']);
// Tags that use a 2 TYPE sub-field for description
const _TYPE_TAGS = new Set(['EVEN','FACT','OCCU','TITL','EDUC','NATI','RELI']);

let _eventModalXref = null, _eventModalIdx = null, _eventModalTag = null, _eventModalFamXref = null;

function _updateEventModalFields(tag) {
  const inlineRow = document.getElementById('event-modal-inline-row');
  const inlineLbl = document.getElementById('event-modal-inline-label');
  const typeRow   = document.getElementById('event-modal-type-row');
  if (_INLINE_TYPE_TAGS.has(tag)) {
    inlineRow.style.display = '';
    const labelMap = {OCCU:'Occupation',TITL:'Title',NATI:'Nationality',RELI:'Religion',EDUC:'Education'};
    inlineLbl.textContent = labelMap[tag] || 'Value';
  } else {
    inlineRow.style.display = 'none';
  }
  // For inline-type tags (EDUC, OCCU, etc.) the inline value IS the type —
  // showing a separate TYPE field would duplicate it and cause confusion.
  typeRow.style.display = (_TYPE_TAGS.has(tag) && !_INLINE_TYPE_TAGS.has(tag)) ? '' : 'none';
}

function _updateAddrSuggestions(place) {
  const dl = document.getElementById('addr-suggestions');
  if (!dl) return;
  dl.innerHTML = '';
  const suggestions = ADDR_BY_PLACE[place] || [];
  for (const s of suggestions) {
    const opt = document.createElement('option');
    opt.value = s;
    dl.appendChild(opt);
  }
}

(function() {
  const dl = document.getElementById('plac-suggestions');
  if (!dl) return;
  for (const p of ALL_PLACES) {
    const opt = document.createElement('option');
    opt.value = p;
    dl.appendChild(opt);
  }
})();

function _personName(xref) {
  return (PEOPLE[xref] && PEOPLE[xref].name) ||
    ((ALL_PEOPLE.find(p => p.id === xref) || {}).name) || xref;
}

function editEvent(xref, eventIdx, tag, famXref) {
  _eventModalXref    = xref;
  _eventModalIdx     = eventIdx;
  _eventModalTag     = tag;
  _eventModalFamXref = famXref || null;
  document.getElementById('event-modal-title').textContent = 'Edit Event \u2014 ' + _personName(xref);
  document.getElementById('event-modal-save-btn').textContent = 'Save';
  document.getElementById('event-modal-tag-row').style.display = 'none';
  const events = (PEOPLE[xref] && PEOPLE[xref].events) || [];
  // For FAM events (MARR), match by fam_xref; otherwise match by tag + event_idx
  const evt = famXref
    ? (events.find(e => e.fam_xref === famXref && e.tag === tag) || {})
    : (events.find(e => e.tag === tag && e.event_idx === eventIdx) || {});
  const placeVal = evt.place || '';
  document.getElementById('event-modal-inline').value = evt.inline_val || '';
  document.getElementById('event-modal-type').value   = evt.type || '';
  document.getElementById('event-modal-date').value   = evt.date || '';
  document.getElementById('event-modal-place').value  = placeVal;
  document.getElementById('event-modal-note').value   = evt.note || '';
  document.getElementById('event-modal-addr').value   = evt.addr || '';
  _updateAddrSuggestions(placeVal);
  _updateNoteCount();
  _updateEventModalFields(tag);
  document.getElementById('event-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('event-modal-date').focus(), 50);
}

function addEvent(xref, defaultTag = 'RESI', prefillType) {
  _eventModalXref    = xref;
  _eventModalIdx     = null;
  _eventModalTag     = null;
  _eventModalFamXref = null;
  document.getElementById('event-modal-title').textContent = 'Add Event \u2014 ' + _personName(xref);
  document.getElementById('event-modal-save-btn').textContent = 'Add';
  document.getElementById('event-modal-tag-row').style.display = '';
  document.getElementById('event-modal-tag').value    = defaultTag;
  document.getElementById('event-modal-inline').value = '';
  document.getElementById('event-modal-type').value   = prefillType || '';
  document.getElementById('event-modal-date').value   = '';
  document.getElementById('event-modal-place').value  = '';
  document.getElementById('event-modal-note').value   = '';
  document.getElementById('event-modal-addr').value   = '';
  _updateAddrSuggestions('');
  _updateNoteCount();
  _updateEventModalFields(defaultTag);
  document.getElementById('event-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('event-modal-date').focus(), 50);
}

function closeEventModal() {
  document.getElementById('event-modal-overlay').classList.remove('open');
  _eventModalXref = _eventModalIdx = _eventModalTag = _eventModalFamXref = null;
}

async function submitEventModal() {
  const xref     = _eventModalXref;
  const famXref  = _eventModalFamXref;
  const isAdd    = _eventModalIdx === null && !famXref;
  const tag      = isAdd ? document.getElementById('event-modal-tag').value : _eventModalTag;
  const typeRow = document.getElementById('event-modal-type-row');
  const fields = {
    inline_val: document.getElementById('event-modal-inline').value.trim(),
    DATE:        document.getElementById('event-modal-date').value.trim(),
    PLAC:        document.getElementById('event-modal-place').value.trim(),
    NOTE:        document.getElementById('event-modal-note').value.trim(),
    ADDR:        document.getElementById('event-modal-addr').value.trim(),
  };
  // Only include TYPE when the row is visible; omitting it preserves existing 2 TYPE sub-tags
  // for events (like MARR) where the type row is hidden.
  if (typeRow && typeRow.style.display !== 'none') {
    fields.TYPE = document.getElementById('event-modal-type').value.trim();
  }
  const endpoint = isAdd ? '/api/add_event' : '/api/edit_event';
  let body;
  if (isAdd) {
    body = { xref, tag, fields, current_person: window._currentPerson || null };
  } else if (famXref) {
    body = { xref, tag, fam_xref: famXref, updates: fields, current_person: window._currentPerson || null };
  } else {
    body = { xref, tag, event_idx: _eventModalIdx, updates: fields, current_person: window._currentPerson || null };
  }
  closeEventModal();
  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.ok) {
      // Update all returned people (may include both spouses for marriage edits)
      if (data.people) {
        for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      }
      _openDetailKey = null;
      showDetail(xref);
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}

const _NOTE_MAX_CHARS = 248;  // GEDCOM line limit (255) minus "2 NOTE " prefix (7)

function _updateNoteCount() {
  const textarea = document.getElementById('event-modal-note');
  const countEl  = document.getElementById('event-modal-note-count');
  if (!textarea || !countEl) return;
  const len = textarea.value.length;
  const remaining = _NOTE_MAX_CHARS - len;
  countEl.textContent = remaining + ' characters remaining';
  countEl.classList.toggle('at-limit', remaining <= 0);
  // Prevent input beyond the limit
  if (len > _NOTE_MAX_CHARS) {
    textarea.value = textarea.value.slice(0, _NOTE_MAX_CHARS);
  }
}

// Update field visibility when the tag selector changes (add mode only)
document.addEventListener('change', e => {
  if (e.target.id === 'event-modal-tag') _updateEventModalFields(e.target.value);
});
// Update ADDR suggestions as the place field changes
document.addEventListener('input', e => {
  if (e.target.id === 'event-modal-place') _updateAddrSuggestions(e.target.value.trim());
});

// ---------------------------------------------------------------------------
// Alias (secondary name) add / edit / delete
// ---------------------------------------------------------------------------

let _aliasModalXref = null, _aliasModalNameOccurrence = null, _aliasModalIsNameRecord = false;

function openAliasModal(xref, nameOccurrence, currentName, currentType, isNameRecord) {
  _aliasModalXref            = xref;
  _aliasModalNameOccurrence  = nameOccurrence;   // null = add mode
  _aliasModalIsNameRecord    = !!isNameRecord;
  const isAdd = nameOccurrence === null || nameOccurrence === undefined;
  document.getElementById('alias-modal-title').textContent =
    (isAdd ? 'Add Secondary Name \u2014 ' : 'Edit Name \u2014 ') + _personName(xref);
  document.getElementById('alias-modal-save-btn').textContent = isAdd ? 'Add' : 'Save';
  document.getElementById('alias-modal-name').value = currentName || '';
  // Set the dropdown; fall back to AKA if the value isn't in the list
  const sel = document.getElementById('alias-modal-type');
  const opt = [...sel.options].find(o => o.value === (currentType || 'AKA'));
  sel.value = opt ? opt.value : 'AKA';
  document.getElementById('alias-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('alias-modal-name').focus(), 50);
}

function closeAliasModal() {
  document.getElementById('alias-modal-overlay').classList.remove('open');
  _aliasModalXref = _aliasModalNameOccurrence = null;
}

async function deleteAlias(xref, evt) {
  const label = evt.note || evt.inline_val || '';
  if (!confirm('Delete this name? The GEDCOM file will be updated immediately.\\n\\n' + label)) return;
  let endpoint, body;
  if (evt._name_record) {
    endpoint = '/api/delete_secondary_name';
    body = { xref, name_occurrence: evt._name_occurrence, current_person: window._currentPerson || null };
  } else {
    // FACT-based AKA — use existing delete_fact
    endpoint = '/api/delete_fact';
    body = { xref, tag: evt.tag, date: evt.date || null, place: evt.place || null,
             type: evt.type || null, inline_val: evt.inline_val || null,
             current_person: xref };
  }
  try {
    const resp = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people) for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      _openDetailKey = null; showDetail(xref);
    } else { alert('Delete failed: ' + (data.error || 'unknown error')); }
  } catch (e) { alert('Request failed: ' + e); }
}

async function submitAliasModal() {
  const xref      = _aliasModalXref;
  const nameOcc   = _aliasModalNameOccurrence;
  const isAdd     = nameOcc === null || nameOcc === undefined;
  const name      = document.getElementById('alias-modal-name').value.trim();
  const nameType  = document.getElementById('alias-modal-type').value;
  if (!name) { alert('Please enter a name.'); return; }
  closeAliasModal();
  let endpoint, body;
  if (isAdd) {
    endpoint = '/api/add_secondary_name';
    body = { xref, name, name_type: nameType, current_person: window._currentPerson || null };
  } else {
    endpoint = '/api/edit_secondary_name';
    body = { xref, name_occurrence: nameOcc, name, name_type: nameType,
             current_person: window._currentPerson || null };
  }
  try {
    const resp = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people) for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      _openDetailKey = null; showDetail(xref);
    } else { alert('Save failed: ' + (data.error || 'unknown error')); }
  } catch (e) { alert('Request failed: ' + e); }
}

// ---------------------------------------------------------------------------
// Name editing
// ---------------------------------------------------------------------------

let _nameModalXref = null;

function editName(xref) {
  _nameModalXref = xref;
  const name = (_personName(xref) || '').trim();
  // Split "Given /Surname/" or just "Given Surname" into parts
  const surnameMatch = name.match(/^(.*?)\\s*\\/([^/]*)\\/\\s*(.*)$/);
  let given = '', surname = '';
  if (surnameMatch) {
    given   = (surnameMatch[1] + ' ' + (surnameMatch[3] || '')).trim();
    surname = surnameMatch[2].trim();
  } else {
    // Try to split on last word as surname heuristic
    const parts = name.split(' ');
    surname = parts.length > 1 ? parts.pop() : '';
    given   = parts.join(' ');
  }
  document.getElementById('name-modal-title').textContent = 'Edit Name \u2014 ' + name;
  document.getElementById('name-modal-given').value   = given;
  document.getElementById('name-modal-surname').value = surname;
  document.getElementById('name-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('name-modal-given').focus(), 50);
}

function closeNameModal() {
  document.getElementById('name-modal-overlay').classList.remove('open');
  _nameModalXref = null;
}

async function submitNameModal() {
  const xref      = _nameModalXref;
  const givenName = document.getElementById('name-modal-given').value.trim();
  const surname   = document.getElementById('name-modal-surname').value.trim();
  closeNameModal();
  try {
    const resp = await fetch('/api/edit_name', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ xref, given_name: givenName, surname,
                             current_person: window._currentPerson || null }),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      _openDetailKey = null;
      showDetail(xref);
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) { alert('Request failed: ' + e); }
}

async function deleteFact(xref, evt) {
  const label = (evt.date || '') + (evt.place ? ' · ' + evt.place : '') || evt.tag;
  if (!confirm('Delete this fact? The GEDCOM file will be updated immediately (a backup will be saved).\\n\\n' + evt.tag + (label ? ': ' + label : ''))) return;
  try {
    const resp = await fetch('/api/delete_fact', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        xref,
        tag: evt.tag,
        date: evt.date || null,
        place: evt.place || null,
        type: evt.type || null,
        inline_val: evt.inline_val || null,
        current_person: xref,
      }),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      _openDetailKey = null;
      showDetail(xref);
    } else {
      alert('Delete failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}
function linkify(s) {
  // Match URLs in the raw string before HTML-escaping, so & in query strings isn't truncated
  const URL_RE = /https?:\\/\\/\\S+/g;
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

// ── AGE formatting ────────────────────────────────────────────────────────────
function fmtAge(raw) {
  if (!raw) return '';
  const s = raw.trim();
  const uc = s.toUpperCase().replace(/^[<>]/, '');
  if (uc === 'INFANT')    return 'in infancy';
  if (uc === 'STILLBORN') return 'stillborn';
  if (uc === 'CHILD')     return 'in childhood';
  const prefix = s.startsWith('>') ? 'over ' : s.startsWith('<') ? 'under ' : '';
  let r = s.replace(/^[<>]/, '');
  r = r.replace(/(\\d+)y\\b/g, (_, n) => `${n} year${n === '1' ? '' : 's'}`);
  r = r.replace(/(\\d+)m\\b/g, (_, n) => `${n} month${n === '1' ? '' : 's'}`);
  r = r.replace(/(\\d+)d\\b/g, (_, n) => `${n} day${n === '1' ? '' : 's'}`);
  return (prefix + r.trim().replace(/\\s+/g, ' ')).trim();
}

// ── Per-event prose + meta ───────────────────────────────────────────────────
function buildProse(evt) {
  const date  = fmtDate(evt.date);
  const place = evt.place || '';
  const short = fmtPlace(place);
  const type  = evt.type || '';
  const addr  = evt.addr || '';
  const meta  = () => [addr, place, date].filter(Boolean).join(' \\u00b7 ');
  switch (evt.tag) {
    case 'BIRT': return { prose: short ? `Born in ${short}` : (date ? `Born ${date}` : 'Birth'),          meta: meta() };
    case 'DEAT': {
      const cause = evt.cause ? `of ${evt.cause}` : '';
      const age   = evt.age  || '';
      if (cause && short) return { prose: `Died ${cause} in ${short}`, meta: meta() };
      if (cause)          return { prose: `Died ${cause}`,             meta: meta() };
      if (short)          return { prose: `Died in ${short}`,          meta: meta() };
      if (!date && age) {
        const ageUC = age.toUpperCase().replace(/^[<>]/, '');
        if (ageUC === 'STILLBORN') return { prose: 'Stillborn',                   meta: meta() };
        return { prose: `Died at ${fmtAge(age)}`, meta: meta() };
      }
      return { prose: date ? `Died ${date}` : 'Death', meta: meta() };
    }
    case 'BURI': return { prose: short ? `Buried in ${short}` : (date ? `Buried ${date}` : 'Burial'),    meta: meta() };
    case 'RESI': return { prose: short ? `Lived in ${short}` : (date ? `Lived ${date}` : 'Residence'),   meta: meta() };
    case 'OCCU': {
      const jobTitle = evt.inline_val || '';
      return { prose: jobTitle ? `Worked as ${jobTitle}` : (short ? `Worked in ${short}` : 'Occupation'), meta: meta() };
    }
    case 'IMMI': return { prose: short ? `Immigrated to ${short}` : (date ? `Immigrated ${date}` : 'Immigration'), meta: meta() };
    case 'NATU': return { prose: short ? `Naturalized in ${short}` : (date ? `Naturalized ${date}` : 'Naturalization'), meta: meta() };
    case 'ADOP': return { prose: date ? `Adopted ${date}` : 'Adoption', meta: short };
    case 'EDUC': return { prose: type ? `Education: ${type}` : 'Education', meta: meta() };
    case 'RETI': return { prose: date ? `Retired ${date}` : 'Retirement', meta: short };
    case 'TITL': return { prose: type ? `Held title: ${type}` : 'Title', meta: date };
    case 'CHR':  return { prose: short ? `Christened in ${short}` : (date ? `Christened ${date}` : 'Christening'), meta: meta() };
    case 'BAPM': return { prose: short ? `Baptized in ${short}` : (date ? `Baptized ${date}` : 'Baptism'), meta: meta() };
    case 'CONF': return { prose: short ? `Confirmed in ${short}` : (date ? `Confirmed ${date}` : 'Confirmation'), meta: meta() };
    case 'NATI': return { prose: type ? `Nationality: ${type}` : (short ? `Nationality: ${short}` : 'Nationality'), meta: date };
    case 'RELI': return { prose: 'Religion', meta: type || date };
    case 'DIV':  return { prose: date ? `Divorced ${date}` : 'Divorce', meta: short };
    case 'FACT': {
      if (type && type.toUpperCase() === 'AKA')
        return { prose: `Also known as: ${evt.note || ''}`, meta: date };
      return { prose: type || short || 'Fact', meta: date };
    }
    case 'MARR': {
      const who = evt.spouse || '';
      const prose = who ? `Married ${who}` : 'Marriage';
      return { prose, meta: meta() };
    }
    case 'PROB': return { prose: short ? `Probate in ${short}` : (date ? `Probate ${date}` : 'Probate'), meta: meta() };
    case 'ARRV': return { prose: short ? `Arrived in ${short}` : (date ? `Arrived ${date}` : 'Arrival'),     meta: meta() };
    case 'DEPA': return { prose: short ? `Departed from ${short}` : (date ? `Departed ${date}` : 'Departure'), meta: meta() };
    default: {
      if (type === 'Arrival')
        return { prose: short ? `Arrived in ${short}` : (date ? `Arrived ${date}` : 'Arrival'), meta: meta() };
      if (type === 'Departure')
        return { prose: short ? `Departed from ${short}` : (date ? `Departed ${date}` : 'Departure'), meta: meta() };
      if (type === 'Church') {
        return { prose: evt.addr || short || 'Church', meta: meta() };
      }
      return {
        prose: type || (short ? short : (EVENT_LABELS[evt.tag] || evt.tag)),
        meta:  meta()
      };
    }
  }
}

function dotColor(evt) {
  if (evt.type === 'Name Change') return '#f97316';
  if (evt.tag === 'MARR') return '#e879f9';
  switch (evt.tag) {
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
function sortEvents(events) { return events; }  // pre-sorted by Python

function collapseResidences(events) {
  const result = [];
  let i = 0;
  while (i < events.length) {
    const evt = events[i];
    if (evt.tag !== 'RESI') { result.push(evt); i++; continue; }
    const short = fmtPlace(evt.place || '');
    // Collect consecutive RESI events with the same short place name
    const run = [evt];
    let j = i + 1;
    while (j < events.length && events[j].tag === 'RESI' &&
           fmtPlace(events[j].place || '') === short) {
      run.push(events[j]);
      j++;
    }
    if (run.length < 2) { result.push(evt); i = j; continue; }
    const years = run.map(e => (_YR_RE.exec(e.date || '') || [,null])[1]).filter(Boolean);
    const yearRange = years.length >= 2 ? `${years[0]}\u2013${years[years.length - 1]}` : (years[0] || '');
    const notes = run.flatMap(e => {
      if (!e.note) return [];
      const yr = (_YR_RE.exec(e.date || '') || [,null])[1];
      return [yr ? `${yr}: ${e.note}` : e.note];
    });
    result.push({ ...evt, _yearRange: yearRange, note: notes.length ? notes.join('\\n') : null });
    i = j;
  }
  return result;
}

// ── Detail panel ─────────────────────────────────────────────────────────────
let _openDetailKey = null;

function showDetail(xref) {
  if (_openDetailKey === xref) {
    return;  // already open for this person
  }
  const panelWasOpen = _openDetailKey !== null;
  const data = PEOPLE[xref] || (() => {
    const p = ALL_PEOPLE.find(x => x.id === xref);
    return p ? { name: p.name, birth_year: p.birth_year, death_year: p.death_year,
                 sex: null, events: [], notes: [], sources: [] } : null;
  })();
  if (!data) return;
  const panel = document.getElementById('detail-panel');

  try {
  // Accent color by sex
  const accent = {'M':'#3b82f6','F':'#a855f7'}[data.sex] || '#475569';
  document.getElementById('detail-accent-bar').style.background = accent;

  // Name + sex symbol + edit button
  const sexSym = {'M':'\\u2642','F':'\\u2640'}[data.sex] || '';
  const xrefQN  = JSON.stringify(xref).replace(/"/g, '&quot;');
  document.getElementById('detail-name').innerHTML =
    escHtml(data.name) +
    (sexSym ? `<span class="sex-sym">${sexSym}</span>` : '') +
    `<button class="name-edit-btn" title="Edit name" onclick="editName(${xrefQN})">\u270f</button>`;

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
  {
    const xrefQA = JSON.stringify(xref).replace(/"/g, '&quot;');
    const akaEvents = (data.events || []).map((e, i) => ({...e, _origIdx: i}))
      .filter(e => e.tag === 'FACT' && (e.type || '').toUpperCase() === 'AKA' && e.note);
    const addAkaBtn = `<button class="aka-btn" title="Add secondary name" style="font-size:11px;color:#475569;margin-left:4px" onclick="openAliasModal(${xrefQA},null,'','AKA',true)">&#43; alias</button>`;
    if (akaEvents.length) {
      const entries = akaEvents.map(e => {
        // NAME-based records have _name_occurrence; FACT-based have event_idx
        const isNameRec = e._name_record === true;
        const editBtn = isNameRec
          ? `<button class="aka-btn" title="Edit name" onclick="openAliasModal(${xrefQA},${e._name_occurrence},${JSON.stringify(e.note).replace(/"/g,'&quot;')},${JSON.stringify(e.type || 'AKA').replace(/"/g,'&quot;')},true)">\u270f</button>`
          : (e.event_idx !== null && e.event_idx !== undefined
            ? `<button class="aka-btn" title="Edit alias" onclick="editEvent(${xrefQA},${e.event_idx},'FACT')">\u270f</button>`
            : '');
        const delBtn = `<button class="aka-btn del" title="Delete name" onclick="deleteAlias(${xrefQA},PEOPLE[${xrefQA}].events[${e._origIdx}])">\u2715</button>`;
        return `<span class="aka-entry"><span style="font-style:italic">${escHtml(e.note)}</span>${editBtn}${delBtn}</span>`;
      }).join(' \xb7 ');
      akaDiv.innerHTML = entries + addAkaBtn;
    } else {
      akaDiv.innerHTML = addAkaBtn;
    }
  }

  // Notes — collapsible
  const notesDiv = document.getElementById('detail-notes');
  const notes = data.notes || [];
  if (notes.length) {
    const count = notes.length;
    const label = count === 1 ? '1 Note' : `${count} Notes`;
    const cards = notes.map((n, i) => {
      const xrefQ = JSON.stringify(xref).replace(/"/g, '&quot;');
      return `<div class="note-card-wrap">` +
        `<div class="note-card" style="border-left-color:${accent}">${linkify(n)}</div>` +
        `<div class="note-actions">` +
        `<button class="note-action-btn" title="Edit note" onclick="editNote(${xrefQ},${i})">\u270f</button>` +
        `<button class="note-action-btn" title="Delete note" onclick="deleteNote(${xrefQ},${i})">\u2715</button>` +
        `</div></div>`;
    }).join('');
    notesDiv.innerHTML =
      `<button class="notes-toggle open" onclick="this.classList.toggle('open');` +
      `this.nextElementSibling.style.display=this.classList.contains('open')?'block':'none'">` +
      `<span class="notes-toggle-arrow">&#9658;</span>${escHtml(label)}</button>` +
      `<div class="notes-body">${cards}</div>`;
  } else {
    notesDiv.innerHTML = '';
  }

  // Timeline events (AKA excluded — shown above; NATI shown in facts; undated RESI shown below)
  const evtDiv  = document.getElementById('detail-events');
  const alsoLivedDiv = document.getElementById('detail-also-lived');
  const factsDiv = document.getElementById('detail-facts');

  // Nationalities — always shown as pills in facts section, never in the timeline
  const natiEvents = (data.events || []).map((e, i) => ({...e, _origIdx: i}))
    .filter(e => e.tag === 'NATI');
  {
    const xrefQ = JSON.stringify(xref).replace(/"/g, '&quot;');
    const addNatiBtn = `<button class="add-event-btn" onclick="addEvent(${xrefQ},'NATI')">&#43; Add nationality</button>`;
    if (natiEvents.length) {
      const pills = natiEvents.map(e => {
        const _pillYr = e.date ? ((_YR_RE.exec(e.date) || [,null])[1]) : null;
        const dateStr = _pillYr ? `<span class="pill-date">${_pillYr}</span>` : '';
        const editBtn = e.event_idx !== null && e.event_idx !== undefined
          ? `<button class="facts-pill-btn" title="Edit" onclick="editEvent(${xrefQ},${e.event_idx},'NATI')">\u270f</button>`
          : '';
        const delBtn = `<button class="facts-pill-btn del" title="Delete" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${e._origIdx}])">\u2715</button>`;
        const actions = `<span class="facts-pill-actions">${editBtn}${delBtn}</span>`;
        return `<span class="facts-pill-wrap"><span class="facts-pill">${escHtml(e.inline_val || '')}${dateStr}</span>${actions}</span>`;
      }).join('');
      factsDiv.innerHTML = `<span class="facts-heading">Nationality</span><div class="facts-pills">${pills}${addNatiBtn}</div>`;
      factsDiv.className = 'has-content';
    } else {
      factsDiv.innerHTML = addNatiBtn;
      factsDiv.className = 'has-content';
    }
  }

  const allVisible = (data.events || []).map((e, i) => ({...e, _origIdx: i})).filter(e =>
    e.tag !== 'NATI' &&
    (e.tag === 'MARR' || e.date || e.place || e.note || e.type || e.cause || e.addr) &&
    !(e.tag === 'FACT' && (e.type || '').toUpperCase() === 'AKA')
  );
  const _keepInTimeline = e =>
    e.tag !== 'RELI' && (
    e.date ||
    e.tag === 'BIRT' || e.tag === 'DEAT' || e.tag === 'BURI' || e.tag === 'PROB' || e.tag === 'MARR' ||
    e.type === 'Arrival' || e.type === 'Departure');
  const undatedFactoids = allVisible.filter(e => !_keepInTimeline(e));
  const visible = allVisible.filter(_keepInTimeline);
  const sorted  = collapseResidences(sortEvents(visible));

  const _addEvtBtn = `<button class="add-event-btn" onclick="addEvent(${JSON.stringify(xref).replace(/"/g,'&quot;')})">&#43; Add event</button>`;
  if (!sorted.length) { evtDiv.innerHTML = _addEvtBtn; }
  else {
    let html = '', lastSection = '';
    for (const evt of sorted) {
      let section = 'Life';
      const evtYear = evt.date ? ((_YR_RE.exec(evt.date) || [,0])[1] | 0) : null;
      const _typ = (evt.type || '').toLowerCase();
      const _isDeathRelated = evt.tag === 'DEAT' || evt.tag === 'BURI' || evt.tag === 'PROB' ||
        (evt.tag === 'EVEN' && (_typ.includes('death') || _typ.includes('obituar') || _typ.includes('avis de d') || _typ.includes('probate')));
      if (evt.tag === 'BIRT' || (evtYear && by && evtYear <= by + 18)) section = 'Early Life';
      else if (_isDeathRelated) section = 'Later Life';

      if (section !== lastSection) {
        html += `<span class="timeline-section-label">${escHtml(section)}</span>`;
        lastSection = section;
      }

      const { prose, meta } = buildProse(evt);
      const color   = dotColor(evt);
      const noteInl = evt.note
        ? evt.note.split('\\n').map(l => `<div class="evt-note-inline">${escHtml(l)}</div>`).join('') : '';

      if (evt.tag === 'MARR') {
        const yearLabel = evtYear ? `<div class="marr-year">${evtYear}</div>` : '';
        const spXref = evt.spouse_xref;
        const spClickable = spXref && PARENTS[spXref];
        const spXrefAttr = spClickable ? escHtml(spXref) : '';
        const marrClick = spClickable
          ? ` style="cursor:pointer" data-spouse-xref="${spXrefAttr}" onclick="changeRoot(this.dataset.spouseXref)"` : '';
        const proseHtml = spClickable
          ? `<div class="marr-prose marr-link">${escHtml(prose)}</div>`
          : `<div class="marr-prose">${escHtml(prose)}</div>`;
        const xrefQ = JSON.stringify(xref).replace(/"/g, '&quot;');
        const marrEditBtn = evt.fam_xref
          ? `<button class="marr-edit-btn" title="Edit marriage" onclick="event.stopPropagation();editEvent(${xrefQ},null,'MARR',${JSON.stringify(evt.fam_xref).replace(/"/g,'&quot;')})">\u270f</button>`
          : '';
        html +=
          `<div class="marr-card"${marrClick}>` +
          marrEditBtn +
          yearLabel +
          proseHtml +
          (meta && meta !== String(evtYear) ? `<div class="marr-meta">${escHtml(meta)}</div>` : '') +
          noteInl +
          `</div>`;
        continue;
      }

      const isAnch  = evt.tag === 'BIRT' || evt.tag === 'DEAT';
      const dotCls  = isAnch ? 'evt-dot dot-anchor' : 'evt-dot';
      const yearStr = evt._yearRange
        ? `<span class="evt-year">${escHtml(evt._yearRange)}</span>`
        : (evtYear ? `<span class="evt-year">${evtYear}</span>` : '');
      const xrefQ   = JSON.stringify(xref).replace(/"/g, '&quot;');
      const delBtn  = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">\u2715</button>`;
      const editBtn = evt.event_idx !== null && evt.event_idx !== undefined
        ? `<button class="evt-edit-btn" title="Edit event" onclick="editEvent(${xrefQ},${evt.event_idx},${JSON.stringify(evt.tag).replace(/"/g,'&quot;')})">\u270f</button>`
        : '';
      html +=
        `<div class="evt-entry">` +
        `<div class="${dotCls}" style="background:${color}"></div>` +
        `<div class="evt-prose">${yearStr}${escHtml(prose)}</div>` +
        (meta && meta !== String(evtYear) ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
        noteInl +
        editBtn +
        delBtn +
        `</div>`;
    }
    html += _addEvtBtn;
    evtDiv.innerHTML = html;
  }

  // Undated bottom sections — rendered as timeline-style rows, no spine
  function undatedRows(evts) {
    return evts.map(evt => {
      const { prose, meta } = buildProse(evt);
      const color   = dotColor(evt);
      const noteInl = evt.note ? `<div class="evt-note-inline">${escHtml(evt.note)}</div>` : '';
      const xrefQ   = JSON.stringify(xref).replace(/"/g, '&quot;');
      const delBtn  = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">\u2715</button>`;
      const editBtn = evt.event_idx !== null && evt.event_idx !== undefined
        ? `<button class="evt-edit-btn" title="Edit event" onclick="editEvent(${xrefQ},${evt.event_idx},${JSON.stringify(evt.tag).replace(/"/g,'&quot;')})">\u270f</button>`
        : '';
      return `<div class="evt-entry">` +
        `<div class="evt-dot" style="background:${color}"></div>` +
        `<div class="evt-prose">${escHtml(prose)}</div>` +
        (meta ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
        noteInl +
        editBtn +
        delBtn +
        `</div>`;
    }).join('');
  }

  let bottomHtml = '';
  if (undatedFactoids.length) {
    const residences = undatedFactoids.filter(e => e.tag === 'RESI');
    const otherFacts = undatedFactoids.filter(e => e.tag !== 'RESI');
    // Sort so same-type facts appear together (e.g. all Education events adjacent)
    otherFacts.sort((a, b) => {
      const tagCmp = (a.tag || '').localeCompare(b.tag || '');
      if (tagCmp !== 0) return tagCmp;
      return (a.type || a.inline_val || '').localeCompare(b.type || b.inline_val || '');
    });
    if (residences.length) {
      bottomHtml += `<span class="also-lived-heading">Also lived in</span>` + undatedRows(residences);
    }
    if (otherFacts.length) {
      bottomHtml += `<span class="also-lived-heading">Facts</span>` + undatedRows(otherFacts);
    }
  }

  alsoLivedDiv.innerHTML = bottomHtml;
  alsoLivedDiv.className = bottomHtml ? 'has-content' : '';

  const sourcesDiv = document.getElementById('detail-sources');
  const srcs = (data.sources || []).slice().sort((a, b) => (a.title||'').localeCompare(b.title||''));
  const _srcHtml = s => s.url
    ? `<a href="${escHtml(s.url)}" target="_blank" rel="noopener" class="source-link">${escHtml(s.title)}</a>`
    : escHtml(s.title);
  sourcesDiv.innerHTML = srcs.length
    ? `<span class="sources-heading">Sources</span>` +
      (srcs.length === 1
        ? `<div class="source-item">${_srcHtml(srcs[0])}</div>`
        : `<ul class="source-list">${srcs.map(s => `<li class="source-item">${_srcHtml(s)}</li>`).join('')}</ul>`)
    : '';

  } catch (err) {
    console.error('[showDetail] error rendering', xref, err);
    return;
  }
  panel.classList.add('panel-open');
  _openDetailKey = xref;
  const vp = document.getElementById('viewport');
  vp.style.marginRight = '480px';
  document.getElementById('home-btn').style.right = (480 + 24) + 'px';
  if (!panelWasOpen) _animateFitAndCenter(220);
}

function closeDetail() {
  document.getElementById('detail-panel').classList.remove('panel-open');
  _openDetailKey = null;
  const vp = document.getElementById('viewport');
  vp.style.marginRight = '';
  document.getElementById('home-btn').style.right = '24px';
  _animateFitAndCenter(220);
}


function _animateFitAndCenter(duration) {
  const start = performance.now();
  function frame(now) {
    fitAndCenter();
    if (now - start < duration) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

document.getElementById('detail-close').addEventListener('click', closeDetail);
document.getElementById('detail-set-root-btn').addEventListener('click', () => {
  if (_openDetailKey) changeRoot(_openDetailKey);
});

// Build Ahnentafel map {key: xref} from PARENTS starting at rootXref
function buildAhnentafel(rootXref) {
  const result = {};
  const queue = [[rootXref, 1]];
  while (queue.length) {
    const [xref, k] = queue.shift();
    if (!xref || !PARENTS[xref]) continue;
    result[k] = xref;
    const [fatherXref, motherXref] = PARENTS[xref];
    if (fatherXref) queue.push([fatherXref, 2 * k]);
    if (motherXref) queue.push([motherXref, 2 * k + 1]);
  }
  return result;
}

function changeRoot(xref) {
  if (!xref || !PARENTS[xref] || !PARENTS[xref].some(p => p)) return;
  currentTree = buildAhnentafel(xref);
  visibleKeys.clear();
  _posCache.clear();
  _relPosCache.clear();
  expandedRelatives.clear();
  expandedRelatives.add(1);
  for (let g = 0; g <= 2; g++) {
    const start = Math.pow(2, g);
    const end   = Math.pow(2, g + 1);
    for (let k = start; k < end; k++) {
      if (k in currentTree) visibleKeys.add(k);
    }
  }
  render();
  fitAndCenter();
  showDetail(xref);
}

document.getElementById('home-btn').addEventListener('click', () => {
  changeRoot(ROOT_XREF);
});

const NODE_W = 175, NODE_H = 60, H_GAP = 10, V_GAP = 80;
// Extra gap between anchor node and its adjacent sibling, to clear the arrow button (16px + 4px margin).
const BTN_PAD = 24;
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

// True if key k represents a male: even keys (fathers) are male; key 1 uses GEDCOM sex field.
function isMaleKey(k) {
  if (k === 1) return PEOPLE[currentTree[1]]?.sex === 'M';
  return k % 2 === 0;
}

// Pre-computed new sibling slot counts per key (excludes already-visible ancestors).
// Built before layout so _subtreeWidth can use it.
const _sibSlots = new Map();
function _buildSibSlots() {
  _sibSlots.clear();
  const visXrefs = new Set([...visibleKeys].map(k => currentTree[k]).filter(Boolean));
  for (const k of expandedRelatives) {
    if (k === 1) continue;  // root handled separately; no layout slot needed
    const rels = RELATIVES[currentTree[k]];
    if (!rels) continue;
    const n = rels.siblings.filter(xref => !visXrefs.has(xref)).length;
    if (n > 0) _sibSlots.set(k, n);
  }
}

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
    // Add 1 gap slot when both sides have visible ancestors so the two parent
    // groups don't run into each other.
    const fHasAnc = hasFather && (visibleKeys.has(2*fk) || visibleKeys.has(2*fk+1));
    const mHasAnc = hasMother && (visibleKeys.has(2*mk) || visibleKeys.has(2*mk+1));
    // QUICK FIX: inject a fixed 1-slot gap when both sides have ancestors.
    // This prevents the two parent groups from touching but is too blunt —
    // it applies the same gap at every level regardless of actual subtree density,
    // and doesn't handle asymmetric cases (e.g. one side much wider than the other).
    // A proper fix would use a Reingold-Tilford-style contour algorithm to compute
    // the minimal separation that avoids overlap at each level.
    // See: https://github.com/sashaperigo/gedcom-tools/issues/5
    w = Math.max(1, fw + mw + (fHasAnc && mHasAnc ? 1 : 0));
  }
  // Reserve sibling slots (non-root only; root siblings are placed outside layout bounds)
  w += _sibSlots.get(k) || 0;
  cache.set(k, w);
  return w;
}

function computePositions() {
  _posCache = new Map();
  _buildSibSlots();
  const maxGen = maxVisibleGen();
  const slotW  = NODE_W + H_GAP;
  const wCache = new Map();
  _subtreeWidth(1, wCache);

  function layout(k, xStart) {
    const w      = wCache.get(k) || 1;
    const sibN   = _sibSlots.get(k) || 0;
    const male   = isMaleKey(k);
    // Male non-root with siblings: shift node right so siblings fit to its left.
    // Female non-root: siblings extend right; node stays at natural left edge of its ancestor slots.
    const leftShift  = (male && k !== 1) ? sibN : 0;
    const ancestorW  = w - sibN;          // slots used by actual ancestor subtree

    const fk = 2*k, mk = 2*k+1;
    const hasFather = visibleKeys.has(fk);
    const hasMother = visibleKeys.has(mk);
    const g  = genOf(k);
    const x  = xStart + leftShift * slotW + (ancestorW * slotW - NODE_W) / 2;
    const y  = MARGIN_TOP + BTN_ZONE + (maxGen - g) * (NODE_H + V_GAP);
    _posCache.set(k, {x, y});

    // Lay out children so parents center above the full sibling group (not just the ancestor subtree).
    // Shifting by sibN/2 slots places parents above the midpoint of the combined anchor+sibling row.
    const fHasAnc = hasFather && (visibleKeys.has(2*fk) || visibleKeys.has(2*fk+1));
    const mHasAnc = hasMother && (visibleKeys.has(2*mk) || visibleKeys.has(2*mk+1));
    const familyGap = (fHasAnc && mHasAnc) ? slotW : 0;
    let offset = xStart + (sibN / 2) * slotW;
    if (hasFather) { const fw = wCache.get(fk) || 1; layout(fk, offset); offset += fw * slotW; }
    offset += familyGap;
    if (hasMother) { layout(mk, offset); }
  }
  layout(1, MARGIN_X);

  // Couple compaction: move an isolated parent (no visible ancestors, no expanded siblings)
  // adjacent to their partner when the gap between them exceeds one slot.
  // This prevents e.g. a father with no ancestors from being placed far left of a mother
  // whose large subtree pushed her far right.
  for (const k of visibleKeys) {
    const fk = 2*k, mk = 2*k+1;
    if (!visibleKeys.has(fk) || !visibleKeys.has(mk)) continue;
    const fp = _posCache.get(fk), mp = _posCache.get(mk);
    if (!fp || !mp) continue;
    const fHasAncestors = visibleKeys.has(2*fk) || visibleKeys.has(2*fk+1);
    const mHasAncestors = visibleKeys.has(2*mk) || visibleKeys.has(2*mk+1);
    const fHasSiblings  = (_sibSlots.get(fk) || 0) > 0;
    const mHasSiblings  = (_sibSlots.get(mk) || 0) > 0;
    const gap = mp.x - (fp.x + NODE_W + H_GAP);
    if (!fHasAncestors && !fHasSiblings && gap > slotW) {
      _posCache.set(fk, {x: mp.x - NODE_W - H_GAP, y: fp.y});
    } else if (!mHasAncestors && !mHasSiblings && gap > slotW) {
      _posCache.set(mk, {x: fp.x + NODE_W + H_GAP, y: mp.y});
    }
  }
}

function nodePos(k) {
  return _posCache.get(k) || {x: 0, y: 0};
}

function computeRelativePositions() {
  _relPosCache.clear();
  const slotW = NODE_W + H_GAP;
  // Build xref → Ahnentafel key map for all visible ancestors
  const xrefToKey = new Map();
  for (const k of visibleKeys) {
    const xref = currentTree[k];
    if (xref) xrefToKey.set(xref, k);
  }

  for (const k of expandedRelatives) {
    if (!_posCache.has(k)) continue;
    const {x, y} = _posCache.get(k);
    const rels = RELATIVES[currentTree[k]];
    if (!rels) continue;
    const male = isMaleKey(k);

    // Spouses always go to the RIGHT of the anchor
    let newSpIdx = 0;
    rels.spouses.forEach((xref, j) => {
      const existingKey = xrefToKey.get(xref);
      if (existingKey !== undefined) {
        const pos = _posCache.get(existingKey);
        if (pos) _relPosCache.set(`sp:${k}:${j}`, {x: pos.x, y: pos.y, xref, existing: true});
      } else {
        _relPosCache.set(`sp:${k}:${j}`, {x: x + NODE_W + H_GAP + newSpIdx * slotW, y, xref, existing: false});
        newSpIdx++;
      }
    });

    // Siblings: males go LEFT, females go RIGHT (after any new spouses).
    // Each sibling group occupies 1 + (number of sibling's spouses) slots.
    let newSibOffset = 0;
    rels.siblings.forEach((xref, i) => {
      const sibSpouses = (rels.sib_spouses || {})[xref] || [];
      const existingKey = xrefToKey.get(xref);
      if (existingKey !== undefined) {
        const pos = _posCache.get(existingKey);
        if (pos) _relPosCache.set(`sib:${k}:${i}`, {x: pos.x, y: pos.y, xref, existing: true});
        // Sibling already in tree — no new slot consumed, skip its spouses here
      } else {
        const sibX = male
          ? x - (newSibOffset + 1) * slotW - BTN_PAD                          // left of anchor, with button clearance
          : x + NODE_W + H_GAP + BTN_PAD + (newSpIdx + newSibOffset) * slotW; // right, after spouses, with button clearance
        _relPosCache.set(`sib:${k}:${i}`, {x: sibX, y, xref, existing: false});

        // Show only the currently-selected spouse (one slot reserved if any spouses exist)
        if (sibSpouses.length > 0) {
          const spIdx = _sibSpouseIdx.get(`${k}:${i}`) || 0;
          const spXref = sibSpouses[spIdx];
          const existingSpKey = xrefToKey.get(spXref);
          if (existingSpKey !== undefined) {
            const pos = _posCache.get(existingSpKey);
            if (pos) _relPosCache.set(`sibsp:${k}:${i}`, {x: pos.x, y: pos.y, xref: spXref, existing: true, total: sibSpouses.length, spIdx});
          } else {
            const spX = male
              ? x - (newSibOffset + 2) * slotW - BTN_PAD
              : x + NODE_W + H_GAP + BTN_PAD + (newSpIdx + newSibOffset + 1) * slotW;
            _relPosCache.set(`sibsp:${k}:${i}`, {x: spX, y, xref: spXref, existing: false, total: sibSpouses.length, spIdx});
          }
        }

        newSibOffset += 1 + (sibSpouses.length > 0 ? 1 : 0);
      }
    });
  }
}

function hasHiddenParents(k) {
  return ((2 * k) in currentTree || (2 * k + 1) in currentTree) &&
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

function fitAndCenter(focusKey) {
  computePositions();
  computeRelativePositions();
  const vp = document.getElementById('viewport');
  let minX = Infinity, maxX = 0, maxY = 0;
  for (const {x, y} of _posCache.values()) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x + NODE_W);
    maxY = Math.max(maxY, y + NODE_H);
  }
  for (const {x, y} of _relPosCache.values()) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x + NODE_W);
    maxY = Math.max(maxY, y + NODE_H);
  }
  if (minX === Infinity) minX = 0;
  const treeW = maxX - minX + 2 * MARGIN_X;
  const treeH = maxY + 20;
  // QUICK FIX: fit to height only, ignoring width. This fills vertical space
  // but can leave wide trees clipped horizontally. A proper solution would
  // fit to height as the primary axis and then pan so the focal node is
  // centered — ensuring it's never out of view even when scaleX < scaleY.
  // See: https://github.com/sashaperigo/gedcom-tools/issues/6
  const scaleY = (vp.clientHeight * 0.92) / treeH;
  scale = Math.min(1, scaleY);

  if (focusKey) {
    // Center horizontally on the midpoint between the focus node's parents;
    // place parents at ~30% from the top so siblings are visible below.
    const fPos = _posCache.get(2 * focusKey);
    const mPos = _posCache.get(2 * focusKey + 1);
    const p = fPos || mPos;
    if (p) {
      const cx1 = fPos ? fPos.x + NODE_W / 2 : mPos.x + NODE_W / 2;
      const cx2 = mPos ? mPos.x + NODE_W / 2 : cx1;
      const centerX = (cx1 + cx2) / 2;
      tx = vp.clientWidth  / 2 - centerX * scale;
      ty = vp.clientHeight * 0.3 - p.y * scale;
      applyTransform();
      return;
    }
  }

  // Default: root at the bottom
  const { x: rootX, y: rootY } = nodePos(1);
  tx = vp.clientWidth  / 2 - (rootX + NODE_W / 2) * scale;
  ty = vp.clientHeight - (rootY + NODE_H) * scale - 30;
  applyTransform();
}

function expandNode(k) {
  if ((2 * k) in currentTree)     visibleKeys.add(2 * k);
  if ((2 * k + 1) in currentTree) visibleKeys.add(2 * k + 1);
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
  computeRelativePositions();
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

    const childCx = cx + NODE_W / 2;

    if (hasFather && hasMother) {
      // Horizontal line between the two parents at mid-node height.
      const { x: fx, y: fy } = nodePos(fk);
      const { x: mx }        = nodePos(mk);
      const coupleY = fy + NODE_H / 2;
      canvas.appendChild(svgEl('line', {
        x1: fx + NODE_W, y1: coupleY, x2: mx, y2: coupleY,
        stroke: '#475569', 'stroke-width': 1.5
      }));
      // Route through midY to avoid diagonal lines.
      // Always draw even when siblings are expanded (sibling connector may overdraw).
      const dropX = (fx + NODE_W + mx) / 2;  // midpoint of couple gap
      const midY  = cy - V_GAP / 2;
      canvas.appendChild(svgEl('line', {x1: dropX,   y1: coupleY, x2: dropX,   y2: midY,  stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: dropX,   y1: midY,   x2: childCx, y2: midY,   stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: childCx, y1: midY,   x2: childCx, y2: cy,     stroke: '#475569', 'stroke-width': 1.5}));
    } else if (hasFather) {
      const { x: fx, y: fy } = nodePos(fk);
      const px   = fx + NODE_W / 2;
      const midY = cy - V_GAP / 2;
      canvas.appendChild(svgEl('line', {x1: px,      y1: fy + NODE_H, x2: px,      y2: midY, stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: px,      y1: midY,        x2: childCx, y2: midY,  stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: childCx, y1: midY,        x2: childCx, y2: cy,    stroke: '#475569', 'stroke-width': 1.5}));
    } else {
      const { x: mx, y: my } = nodePos(mk);
      const px   = mx + NODE_W / 2;
      const midY = cy - V_GAP / 2;
      canvas.appendChild(svgEl('line', {x1: px,      y1: my + NODE_H, x2: px,      y2: midY, stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: px,      y1: midY,        x2: childCx, y2: midY,  stroke: '#475569', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1: childCx, y1: midY,        x2: childCx, y2: cy,    stroke: '#475569', 'stroke-width': 1.5}));
    }
  }

  // Relative connectors (drawn before nodes so buttons render on top)
  for (const k of expandedRelatives) {
    const rels = RELATIVES[currentTree[k]];
    if (!rels) continue;
    const ancEntry = _posCache.get(k);
    if (!ancEntry) continue;
    const {x: ax, y: ay} = ancEntry;
    const hasFather = visibleKeys.has(2*k);
    const hasMother = visibleKeys.has(2*k+1);

    // Sibling connectors — Ancestry-style: one horizontal bar + individual vertical drops
    const newSibs = rels.siblings.map((sib, i) => _relPosCache.get(`sib:${k}:${i}`))
                                  .filter(e => e && !e.existing);
    if (newSibs.length) {
      const ancCx = ax + NODE_W / 2;
      const male = isMaleKey(k);
      const outerCx = male
        ? Math.min(...newSibs.map(e => e.x + NODE_W / 2))
        : Math.max(...newSibs.map(e => e.x + NODE_W / 2));
      const [barX1, barX2] = male ? [outerCx, ancCx] : [ancCx, outerCx];
      if (hasFather || hasMother) {
        const midY = ay - V_GAP / 2;
        let extBarX1 = barX1, extBarX2 = barX2;
        if (hasFather && hasMother) {
          const fp = _posCache.get(2*k), mp = _posCache.get(2*k+1);
          const coupleY = fp.y + NODE_H / 2;
          const dropX   = (fp.x + NODE_W + mp.x) / 2;
          canvas.appendChild(svgEl('line', {x1: dropX, y1: coupleY, x2: dropX, y2: midY, stroke: '#475569', 'stroke-width': 1.5}));
          extBarX1 = Math.min(barX1, dropX);
          extBarX2 = Math.max(barX2, dropX);
        }
        canvas.appendChild(svgEl('line', {x1: extBarX1, y1: midY, x2: extBarX2, y2: midY, stroke: '#475569', 'stroke-width': 1.5}));
        canvas.appendChild(svgEl('line', {x1: ancCx, y1: midY, x2: ancCx, y2: ay, stroke: '#475569', 'stroke-width': 1.5}));
        newSibs.forEach(({x: sx, y: sy}) => {
          const sibCx = sx + NODE_W / 2;
          canvas.appendChild(svgEl('line', {x1: sibCx, y1: midY, x2: sibCx, y2: sy, stroke: '#475569', 'stroke-width': 1.5}));
        });
      } else {
        const barY = ay - 20;
        canvas.appendChild(svgEl('line', {x1: barX1, y1: barY, x2: barX2, y2: barY, stroke: '#475569', 'stroke-width': 1.5}));
        newSibs.forEach(({x: sx, y: sy}) => {
          const sibCx = sx + NODE_W / 2;
          canvas.appendChild(svgEl('line', {x1: sibCx, y1: barY, x2: sibCx, y2: sy, stroke: '#475569', 'stroke-width': 1.5}));
        });
        canvas.appendChild(svgEl('line', {x1: ancCx, y1: barY, x2: ancCx, y2: ay, stroke: '#475569', 'stroke-width': 1.5}));
      }
    }

    // Anchor spouse marriage connectors
    rels.spouses.forEach((sp, j) => {
      const spEntry = _relPosCache.get(`sp:${k}:${j}`);
      if (!spEntry || spEntry.existing) return;
      const {x: spx} = spEntry;
      const lineY = ay + NODE_H / 2;
      const [x1, x2] = spx < ax ? [spx + NODE_W, ax] : [ax + NODE_W, spx];
      canvas.appendChild(svgEl('line', {x1, y1: lineY - 3, x2, y2: lineY - 3, stroke: '#0f766e', 'stroke-width': 1.5}));
      canvas.appendChild(svgEl('line', {x1, y1: lineY + 3, x2, y2: lineY + 3, stroke: '#0f766e', 'stroke-width': 1.5}));
    });

    // Sibling-spouse marriage connectors + cycle toggle button
    rels.siblings.forEach((sibXref, i) => {
      const sibEntry = _relPosCache.get(`sib:${k}:${i}`);
      if (!sibEntry || sibEntry.existing) return;
      const {x: sx, y: sy} = sibEntry;
      const spEntry = _relPosCache.get(`sibsp:${k}:${i}`);
      if (!spEntry || spEntry.existing) return;
      const {x: spx, total, spIdx} = spEntry;
      const lineY = sy + NODE_H / 2;
      const [x1, x2] = spx < sx ? [spx + NODE_W, sx] : [sx + NODE_W, spx];
      const midX = (x1 + x2) / 2;
      // Draw marriage double lines, leaving a gap in the middle for the toggle button
      if (total > 1) {
        const gap = 12;
        canvas.appendChild(svgEl('line', {x1, y1: lineY - 3, x2: midX - gap, y2: lineY - 3, stroke: '#0f766e', 'stroke-width': 1.5}));
        canvas.appendChild(svgEl('line', {x1, y1: lineY + 3, x2: midX - gap, y2: lineY + 3, stroke: '#0f766e', 'stroke-width': 1.5}));
        canvas.appendChild(svgEl('line', {x1: midX + gap, y1: lineY - 3, x2, y2: lineY - 3, stroke: '#0f766e', 'stroke-width': 1.5}));
        canvas.appendChild(svgEl('line', {x1: midX + gap, y1: lineY + 3, x2, y2: lineY + 3, stroke: '#0f766e', 'stroke-width': 1.5}));
        // Cycle button
        const bw = 20, bh = 16;
        const btn = svgEl('rect', {x: midX - bw/2, y: lineY - bh/2, width: bw, height: bh, rx: 4, fill: '#0f766e', cursor: 'pointer'});
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const next = ((spIdx + 1) % total);
          _sibSpouseIdx.set(`${k}:${i}`, next);
          render();
        });
        canvas.appendChild(btn);
        // Right-pointing triangle
        canvas.appendChild(svgEl('polygon', {
          points: `${midX-4},${lineY-4} ${midX+5},${lineY} ${midX-4},${lineY+4}`,
          fill: 'white', 'pointer-events': 'none'
        }));
      } else {
        canvas.appendChild(svgEl('line', {x1, y1: lineY - 3, x2, y2: lineY - 3, stroke: '#0f766e', 'stroke-width': 1.5}));
        canvas.appendChild(svgEl('line', {x1, y1: lineY + 3, x2, y2: lineY + 3, stroke: '#0f766e', 'stroke-width': 1.5}));
      }
    });
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
    const data   = PEOPLE[currentTree[k]];
    const isRoot = (k === 1);
    const isMale = (k % 2 === 0 && k > 1);
    const fill   = isRoot ? '#2563eb' : (isMale ? '#1e40af' : '#6d28d9');

    const nodeG = svgEl('g', { cursor: 'pointer' });
    nodeG.addEventListener('click', (e) => {
      e.stopPropagation();
      const _xref = currentTree[k];
      console.log('[nodeG click] k=', k, 'xref=', _xref, 'didDrag=', didDrag);
      if (!didDrag) showDetail(_xref);
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

    // Expand / collapse buttons — 16×16 polygon triangles, same size as side arrows
    if (hasHiddenParents(k)) {
      const bx = x + NODE_W / 2 - 8;
      const by = y - BTN_ZONE + 4;
      const btn = svgEl('rect', {x: bx, y: by, width: 16, height: 16, rx: 4, fill: '#059669', cursor: 'pointer'});
      btn.addEventListener('click', (e) => { e.stopPropagation(); console.log('[expandBtn click] k=', k, 'xref=', currentTree[k]); expandNode(k); });
      canvas.appendChild(btn);
      canvas.appendChild(svgEl('polygon', {
        points: `${bx+4},${by+11} ${bx+8},${by+5} ${bx+12},${by+11}`,
        fill: 'white', 'pointer-events': 'none'
      }));
    } else if (hasVisibleParents(k)) {
      const bx = x + NODE_W / 2 - 8;
      const by = y - BTN_ZONE + 4;
      const btn = svgEl('rect', {x: bx, y: by, width: 16, height: 16, rx: 4, fill: '#475569', cursor: 'pointer'});
      btn.addEventListener('click', (e) => { e.stopPropagation(); collapseNode(k); });
      canvas.appendChild(btn);
      canvas.appendChild(svgEl('polygon', {
        points: `${bx+4},${by+5} ${bx+8},${by+11} ${bx+12},${by+5}`,
        fill: 'white', 'pointer-events': 'none'
      }));
    }

    // Relatives toggle button for non-root ancestors that have siblings or spouses.
    // Positioned outside the node on the side where siblings expand:
    // males expand left → button on left; females expand right → button on right.
    if (k !== 1 && RELATIVES[currentTree[k]]) {
      const isExpanded = expandedRelatives.has(k);
      const male = isMaleKey(k);
      const rbw = 16, rbh = 16;
      const rbx = male ? x - rbw - 4 : x + NODE_W + 4;
      const rby = y + (NODE_H - rbh) / 2;
      const rbtn = svgEl('rect', {
        x: rbx, y: rby, width: rbw, height: rbh,
        rx: 4, fill: isExpanded ? '#334155' : '#059669', cursor: 'pointer', opacity: 0.9
      });
      rbtn.addEventListener('click', (e) => {
        e.stopPropagation();
        console.log('[relToggle click] k=', k, 'xref=', currentTree[k]);
        if (expandedRelatives.has(k)) {
          expandedRelatives.delete(k);
          render();
        } else {
          expandedRelatives.add(k);
          // Auto-expand parents so siblings have a visible shared ancestor
          if ((2 * k) in currentTree) visibleKeys.add(2 * k);
          if ((2 * k + 1) in currentTree) visibleKeys.add(2 * k + 1);
          render();
        }
      });
      canvas.appendChild(rbtn);
      // Draw triangle as SVG polygon so left and right are perfect mirrors.
      // Collapsed: points toward where siblings will appear. Expanded: flips back.
      const pointLeft = (male !== isExpanded);
      const arrow = svgEl('polygon', {
        points: pointLeft
          ? `${rbx+11},${rby+4} ${rbx+5},${rby+8} ${rbx+11},${rby+12}`
          : `${rbx+5},${rby+4} ${rbx+11},${rby+8} ${rbx+5},${rby+12}`,
        fill: 'white', 'pointer-events': 'none'
      });
      canvas.appendChild(arrow);
    }
  }

  // ── Relative nodes and connectors ────────────────────────────────────────
  function drawRelNode(rx, ry, xref, fill) {
    const nodeData = PEOPLE[xref] || {};
    const rg = svgEl('g', { cursor: 'pointer' });
    rg.addEventListener('click', (e) => {
      e.stopPropagation();
      console.log('[relNode click] xref=', xref, 'didDrag=', didDrag);
      if (!didDrag) showDetail(xref);
    });
    rg.appendChild(svgEl('rect', { x: rx, y: ry, width: NODE_W, height: NODE_H, rx: 8, fill, opacity: 0.85 }));
    const dname = (nodeData.name || '?');
    const displayName = dname.length > 21 ? dname.slice(0, 19) + '\\u2026' : dname;
    const nt = svgEl('text', {
      x: rx + NODE_W / 2, y: ry + 22,
      'text-anchor': 'middle', fill: 'white', 'font-size': 13, 'font-weight': 600,
      'font-family': 'system-ui, sans-serif', 'pointer-events': 'none'
    });
    nt.textContent = displayName;
    rg.appendChild(nt);
    const yrs = [
      nodeData.birth_year && 'b.' + nodeData.birth_year,
      nodeData.death_year && 'd.' + nodeData.death_year
    ].filter(Boolean).join('  ');
    if (yrs) {
      const yt = svgEl('text', {
        x: rx + NODE_W / 2, y: ry + 42,
        'text-anchor': 'middle', fill: 'rgba(255,255,255,0.65)', 'font-size': 11,
        'font-family': 'system-ui, sans-serif', 'pointer-events': 'none'
      });
      yt.textContent = yrs;
      rg.appendChild(yt);
    }
    canvas.appendChild(rg);
  }

  for (const [key, entry] of _relPosCache.entries()) {
    if (entry.existing) continue;  // already rendered as an ancestor node
    const {x: rx, y: ry, xref} = entry;
    const isSibling = key.startsWith('sib:') && !key.startsWith('sibsp:');
    const fill = isSibling ? '#1e3a5f' : '#065f46';
    drawRelNode(rx, ry, xref, fill);
  }

  applyTransform();
}

function init() {
  // Show generations 0-2 initially
  for (let g = 0; g <= 2; g++) {
    const start = Math.pow(2, g);
    const end   = Math.pow(2, g + 1);
    for (let k = start; k < end; k++) {
      if (k in currentTree) visibleKeys.add(k);
    }
  }

  const vp   = document.getElementById('viewport');
  const hdr  = document.querySelector('header');
  const topH = hdr.offsetHeight;
  vp.style.height = (window.innerHeight - topH) + 'px';
  document.documentElement.style.setProperty('--header-h', topH + 'px');

  render();
  fitAndCenter();
  if (new URLSearchParams(window.location.search).get('open') === '1') showDetail(currentTree[1]);
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
  const vp   = document.getElementById('viewport');
  const hdr  = document.querySelector('header');
  vp.style.height = (window.innerHeight - hdr.offsetHeight) + 'px';
  if (_openDetailKey !== null) vp.style.marginRight = '480px';
});
</script>
</body>
</html>
"""


def build_all_places(indis: dict, fams: dict | None = None) -> list[str]:
    """Return sorted unique PLAC values from all events for PLAC auto-complete in the event modal."""
    places: set[str] = set()
    for info in indis.values():
        for evt in info.get('events', []):
            if evt.get('place'):
                places.add(evt['place'])
    if fams:
        for fam in fams.values():
            for key in ('marr', 'div'):
                evt = fam.get(key)
                if isinstance(evt, dict) and evt.get('place'):
                    places.add(evt['place'])
    return sorted(places)


def build_addr_by_place(indis: dict) -> dict:
    """Return {place: [sorted unique addr values]} for ADDR auto-complete in the event modal."""
    result: dict[str, set] = {}
    for info in indis.values():
        for evt in info['events']:
            place = evt.get('place') or ''
            addr  = evt.get('addr')  or ''
            if place and addr:
                result.setdefault(place, set()).add(addr)
    return {k: sorted(v) for k, v in result.items()}


def render_html(tree: dict, root_name: str, people: dict, relatives: dict, indis: dict,
                fams: dict | None = None, root_xref: str | None = None) -> str:
    """Return a complete self-contained HTML string."""
    safe_name      = html_mod.escape(root_name)
    tree_json      = json.dumps(tree)
    people_json    = json.dumps(people)
    relatives_json = json.dumps(relatives)
    all_people     = sorted(
        [{"id": xref, "name": info["name"] or "",
          "birth_year": info.get("birth_year") or "",
          "death_year": info.get("death_year") or ""}
         for xref, info in indis.items()],
        key=lambda p: p["name"].lower()
    )
    all_people_json = json.dumps(all_people)
    # Build parent map for JS tree rebuilding
    parents = {}
    if fams:
        for xref, info in indis.items():
            famc = info.get('famc')
            if famc and famc in fams:
                fam = fams[famc]
                parents[xref] = [fam.get('husb'), fam.get('wife')]
            else:
                parents[xref] = [None, None]
    parents_json        = json.dumps(parents)
    root_xref_json      = json.dumps(root_xref or '')
    addr_by_place_json  = json.dumps(build_addr_by_place(indis))
    all_places_json     = json.dumps(build_all_places(indis, fams))
    return (
        _HTML_TEMPLATE
        .replace('__ROOT_NAME__', safe_name)
        .replace('__TREE_JSON__', tree_json)
        .replace('__PEOPLE_JSON__', people_json)
        .replace('__ALL_PEOPLE_JSON__', all_people_json)
        .replace('__RELATIVES_JSON__', relatives_json)
        .replace('__PARENTS_JSON__', parents_json)
        .replace('__ROOT_XREF_JSON__', root_xref_json)
        .replace('__ADDR_BY_PLACE_JSON__', addr_by_place_json)
        .replace('__ALL_PLACES_JSON__', all_places_json)
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


def viz_ancestors(path_in: str, person: str, path_out: str,
                  exclude: list | None = None) -> dict:
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

    tree      = build_tree_json(root_xref, indis, fams)
    relatives = build_relatives_json(tree, indis, fams)

    # Build full detail data for everyone so the search panel always shows complete info
    people    = build_people_json(set(indis.keys()), indis, fams, sources, exclude=exclude)

    root_name = people.get(root_xref, {}).get('name', '?')
    html = render_html(tree, root_name, people, relatives, indis, fams=fams, root_xref=root_xref)
    with open(path_out, 'w', encoding='utf-8') as f:
        f.write(html)

    max_gen = max(math.floor(math.log2(k)) for k in tree) if tree else 0
    return {
        'root_name':      root_name,
        'ancestor_count': len(tree),
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
    parser.add_argument('--exclude', default=None,
                        help='JSON list of pending-deletion dicts to hide from view')
    args = parser.parse_args()

    exclude = None
    if args.exclude:
        try:
            exclude = json.loads(args.exclude)
        except Exception:
            sys.exit('Error: --exclude must be a valid JSON list')

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    try:
        result = viz_ancestors(args.gedfile, args.person, args.output, exclude=exclude)
    except ValueError as e:
        sys.exit(f'Error: {e}')

    print(f'Root     : {result["root_name"]}')
    print(f'Ancestors: {result["ancestor_count"]}')
    print(f'Depth    : {result["generations"]} generation{"s" if result["generations"] != 1 else ""}')
    print(f'Written  : {args.output}')


if __name__ == '__main__':
    main()
