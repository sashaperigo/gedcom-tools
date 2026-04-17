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
            sources[xref] = {'titl': None, 'auth': None, 'publ': None, 'repo': None, 'note': None}
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
                       'age': None, 'citations': [], '_name_record': True, '_name_occurrence': secondary_name_n}
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
                evt = {'tag': tag, 'type': inline_type, 'date': None, 'place': None, 'cause': None, 'addr': None, 'note': initial_note, 'inline_val': val if val else None, 'age': None, 'citations': []}
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
                    current_note = 'event'   # sentinel: subsequent CONT/CONC at lvl 3 belong here
                elif tag == 'AGE':
                    current_evt['age'] = val
                elif tag == 'SOUR' and val.startswith('@'):
                    current_evt['citations'].append({'sour_xref': val, 'page': None})
            elif lvl == 3 and tag == 'PAGE' and current_evt is not None and current_evt.get('citations'):
                current_evt['citations'][-1]['page'] = val
            elif lvl == 3 and tag in ('CONT', 'CONC') and current_note == 'event':
                sep = '\n' if tag == 'CONT' else ''
                current_evt['note'] += sep + html_mod.unescape(val)
            elif lvl == 1 and tag == 'NOTE':
                indis[xref]['notes'].append(html_mod.unescape(val))
                current_note = len(indis[xref]['notes']) - 1
                current_evt  = None
            elif lvl == 2 and tag in ('CONT', 'CONC') and isinstance(current_note, int):
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
                # Always start a fresh event dict for each 1 MARR block so that
                # multiple ceremonies (e.g. civil + religious) are all captured.
                # Empty entries (bare duplicate "1 MARR" lines from a merge with no
                # sub-tags) are filtered out in build_people_json.
                evt = {'tag': 'MARR', 'type': None, 'date': None, 'place': None, 'note': None, 'age': None, 'addr': None}
                fams[xref].setdefault('marrs', []).append(evt)
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
            if lvl == 1 and tag in ('TITL', 'AUTH', 'PUBL', 'NOTE'):
                sources[xref][tag.lower()] = val
            elif lvl == 1 and tag == 'REPO':
                sources[xref]['repo'] = val

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
                sour = sources.get(sxref) or {}
                title = sour.get('titl') if isinstance(sour, dict) else sour
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
            # Normalise citation keys: sour_xref → sourceXref so JS can resolve
            # source titles via SOURCES[citation.sourceXref].titl.
            normalised_cites = [
                {
                    'sourceXref': c['sour_xref'],
                    **{k: v for k, v in c.items() if k != 'sour_xref'},
                }
                for c in e.get('citations', [])
            ]
            e_out = {**e, 'citations': normalised_cites}
            if e.get('_name_record'):
                tagged_events.append({**e_out, 'event_idx': None})
            else:
                occ = tag_counters.get(t, 0)
                tag_counters[t] = occ + 1
                tagged_events.append({**e_out, 'event_idx': occ})
        events = [
            e for e in tagged_events
            if not any(_matches_exclusion(e, ex) for ex in excl_list)
        ]
        if fams:
            for fam_xref in info.get('fams', []):
                fam = fams.get(fam_xref, {})
                marrs = fam.get('marrs', [])
                spouse_xref = fam.get('wife') if fam.get('husb') == xref else fam.get('husb')
                spouse_name = indis[spouse_xref]['name'] if spouse_xref and spouse_xref in indis else None
                appended = False
                for marr_idx, marr in enumerate(marrs):
                    # Skip bare duplicate MARR entries (no sub-tags) that can appear after a merge
                    if not any(marr.get(f) for f in ('date', 'place', 'addr', 'note', 'type')):
                        continue
                    # MARR events live in FAM blocks; event_idx=None marks them as non-editable via INDI
                    events.append({**marr, 'event_idx': None, 'marr_idx': marr_idx,
                                   'spouse': spouse_name, 'spouse_xref': spouse_xref,
                                   'fam_xref': fam_xref})
                    appended = True
                if not appended and spouse_xref:
                    # FAM has no MARR record (or only bare duplicates) — emit a
                    # synthetic event so the spouse still appears in the panel.
                    events.append({'tag': 'MARR', 'type': None, 'date': None,
                                   'place': None, 'note': None, 'age': None, 'addr': None,
                                   'event_idx': None, 'marr_idx': 0,
                                   'spouse': spouse_name, 'spouse_xref': spouse_xref,
                                   'fam_xref': fam_xref})
        _deat_age_keywords = frozenset({'STILLBORN', 'INFANT', 'CHILD'})
        age_at_death = next(
            (e['age'].upper() for e in events
             if e['tag'] == 'DEAT' and e.get('age') and e['age'].upper() in _deat_age_keywords),
            None
        )
        result[xref] = {
            'name':         info['name'] or '?',
            'birth_year':   info['birth_year'],
            'death_year':   info['death_year'],
            'sex':          info['sex'],
            'events':       sort_events(events),
            'notes':        info['notes'],
            'sources':      src_list,
            'age_at_death': age_at_death,
        }
    return result


def build_relatives_json(tree: dict, indis: dict, fams: dict) -> dict:
    """
    Return {xref: {siblings, spouses, sib_spouses, half_siblings}} for ALL individuals.

    half_siblings is a list of groups, each:
      {'shared_parent': xref, 'other_parent': xref|None, 'half_sibs': [xref,...]}
    A half-sibling shares exactly one parent (different FAMC record).
    """
    result = {}
    for xref in indis:
        p = indis.get(xref)
        if not p:
            continue

        # Full siblings: same FAMC record
        siblings = []
        famc = p.get('famc')
        if famc and famc in fams:
            for child_xref in fams[famc].get('chil', []):
                if child_xref != xref:
                    siblings.append(child_xref)
        full_sib_set = set(siblings)

        # Parents of current person
        parent_fam = fams.get(famc, {}) if famc else {}
        father = parent_fam.get('husb')
        mother = parent_fam.get('wife')

        # Half-siblings: for each parent, look at their other families
        half_siblings = []
        for shared_parent in (px for px in (father, mother) if px):
            parent_info = indis.get(shared_parent, {})
            # Collect half-sibs from every family of this parent except the current person's own family
            by_other: dict[str | None, list[str]] = {}
            for fam_xref in parent_info.get('fams', []):
                if fam_xref == famc:
                    continue  # skip the family the current person came from
                fam = fams.get(fam_xref, {})
                other_parent = fam.get('wife') if fam.get('husb') == shared_parent else fam.get('husb')
                for child_xref in fam.get('chil', []):
                    if child_xref == xref or child_xref in full_sib_set:
                        continue
                    key = other_parent  # None if unknown
                    by_other.setdefault(key, []).append(child_xref)
            for other_parent, half_sibs in by_other.items():
                half_siblings.append({
                    'shared_parent': shared_parent,
                    'other_parent': other_parent,
                    'half_sibs': half_sibs,
                })

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

        if siblings or spouses or half_siblings:
            entry: dict = {'siblings': siblings, 'spouses': spouses}
            if sib_spouses:
                entry['sib_spouses'] = sib_spouses
            if half_siblings:
                entry['half_siblings'] = half_siblings
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
#viewport { position: relative; overflow: hidden; cursor: grab; user-select: none; transition: margin-right 0.22s ease; height: calc(100vh - var(--header-h, 45px)); }
#viewport.dragging { cursor: grabbing; }
#tree { display: block; width: 100%; height: 100%; }
#gen-labels { position: absolute; left: 0; top: 0; bottom: 0; width: 90px;
  pointer-events: none; overflow: hidden; }
.gen-label { position: absolute; left: 8px; font-size: 11px; color: #64748b;
  font-family: system-ui, sans-serif; transform: translateY(-50%); white-space: nowrap; }
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
#panel-close-btn { background: none; border: none; color: #475569;
                   font-size: 20px; cursor: pointer; padding: 2px;
                   line-height: 1; }
#panel-close-btn:hover { color: #f1f5f9; }
/* ── Panel lifespan + nationalities ────────────────────────── */
#detail-lifespan { display: flex; align-items: center; gap: 6px; font-size: 13px;
                   color: #94a3b8; margin-bottom: 8px; }
.panel-birth-year, .panel-death-year { color: #94a3b8; }
.panel-lifespan-sep { color: #475569; }
.panel-age { font-size: 11px; color: #64748b; }
#detail-nationalities { display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
                        margin-bottom: 6px; }
.panel-nati-pill { background: #1e3a5f; border: 1px solid #3b82f6; color: #93c5fd;
                   font-size: 11px; border-radius: 12px; padding: 2px 10px; }
.add-event-btn { background: none; border: 1px solid #334155; color: #64748b;
                 border-radius: 4px; font-size: 11px; padding: 2px 8px; cursor: pointer; }
.add-event-btn:hover { border-color: #3b82f6; color: #3b82f6; }
/* ── Panel sections ─────────────────────────────────────────── */
.panel-section { margin-bottom: 20px; }
.panel-section-header { display: flex; align-items: center; justify-content: space-between;
                        margin-bottom: 8px; }
.panel-section-title { font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
                       text-transform: uppercase; color: #64748b; }
.panel-section-add { background: none; border: 1px solid #334155; color: #64748b;
                     border-radius: 4px; font-size: 13px; width: 22px; height: 22px;
                     cursor: pointer; display: flex; align-items: center; justify-content: center; }
.panel-section-add:hover { border-color: #3b82f6; color: #3b82f6; }
/* ── Fact rows ──────────────────────────────────────────────── */
.panel-fact-row { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px;
                  padding: 6px 0; border-bottom: 1px solid #1e293b; font-size: 13px; }
.panel-fact-label { font-weight: 600; color: #e2e8f0; min-width: 80px; }
.panel-fact-meta { color: #94a3b8; flex: 1; }
.panel-fact-cite-badge { background: #1e3a5f; color: #93c5fd; font-size: 10px;
                          border-radius: 10px; padding: 1px 7px; cursor: pointer;
                          white-space: nowrap; }
/* ── Godparent pills ────────────────────────────────────────── */
.panel-godparents { display: flex; flex-wrap: wrap; align-items: center;
                    gap: 6px; margin-top: 4px; width: 100%; }
.panel-godparents-label { font-size: 11px; color: #64748b; }
.panel-godparent-pill { background: #1e3a2f; border: 1px solid #4ade80; color: #86efac;
                        font-size: 11px; border-radius: 12px; padding: 2px 10px; cursor: pointer; }
.panel-godparent-pill:hover { background: #1a3d2b; }
.panel-add-godparent-btn { background: none; border: 1px solid #334155; color: #64748b;
                           border-radius: 4px; font-size: 11px; padding: 2px 8px; cursor: pointer; }
.panel-add-godparent-btn:hover { border-color: #4ade80; color: #4ade80; }
/* ── Citation rows ──────────────────────────────────────────── */
.panel-cite-row { display: flex; align-items: center; gap: 6px; padding: 5px 0;
                  border-bottom: 1px solid #1e293b; font-size: 12px; color: #94a3b8; }
.panel-cite-tag { background: #1e2d40; color: #7dd3fc; font-size: 10px;
                  border-radius: 3px; padding: 1px 6px; flex-shrink: 0; }
.panel-cite-edit, .panel-cite-del { background: none; border: none; color: #475569;
                                     cursor: pointer; font-size: 12px; padding: 1px 4px; }
.panel-cite-edit:hover { color: #94a3b8; }
.panel-cite-del:hover { color: #f87171; }
.panel-source-card { padding: 6px 0; border-bottom: 1px solid #1e293b; }
.panel-source-title { font-size: 12px; color: #94a3b8; display: flex;
                      align-items: center; gap: 6px; }
/* ── Note text ──────────────────────────────────────────────── */
.panel-note-text { font-size: 13px; color: #f1f5f9; line-height: 1.75;
                   white-space: pre-wrap; overflow-wrap: break-word;
                   padding: 10px 14px; background: rgba(254,249,195,0.1);
                   border-radius: 6px; border-left: 3px solid rgba(254,243,160,0.35);
                   margin-bottom: 10px; max-height: 260px; overflow-y: auto; }
/* ── Edit name button ───────────────────────────────────────── */
.panel-edit-name-btn { background: none; border: none; color: #475569;
                       cursor: pointer; font-size: 13px; padding: 0 4px; margin-left: 6px; }
.panel-edit-name-btn:hover { color: #94a3b8; }
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
.notes-header { display: flex; align-items: center; justify-content: space-between; }
.notes-toggle { display: flex; align-items: center; gap: 6px; background: none; border: none;
  cursor: pointer; color: #64748b; font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.08em; padding: 0 0 10px 0; }
.notes-toggle:hover { color: #94a3b8; }
.note-add-btn { background: none; border: 1px solid rgba(255,255,255,0.15); color: #64748b;
  border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 10px;
  text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 10px; }
.note-add-btn:hover { color: #94a3b8; border-color: rgba(255,255,255,0.3); }
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
             margin-bottom: 10px;
             max-height: 260px; overflow-y: auto; }
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
.add-fact-select { appearance: none; background: none; border: 1px dashed #334155;
  border-radius: 6px; color: #475569; font-size: 12px; padding: 5px 12px;
  cursor: pointer; margin-top: 12px; font-family: inherit; }
.add-fact-select:hover { border-color: #3b82f6; color: #3b82f6; }
.add-fact-select:focus { outline: none; border-color: #3b82f6; }
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
.marr-del-btn  { position: absolute; right: 30px; top: 8px; background: none; border: none;
  cursor: pointer; font-size: 12px; color: #64748b; padding: 2px 4px;
  border-radius: 4px; opacity: 0; transition: opacity .15s, color .15s; }
.marr-card:hover .marr-edit-btn,
.marr-card:hover .marr-del-btn  { opacity: 1; }
.marr-edit-btn:hover { color: #3b82f6 !important; }
.marr-del-btn:hover  { color: #ef4444 !important; }
.marr-card .marr-year { font-size: 12px; font-weight: 700; color: #94a3b8;
                        text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 3px; }
.marr-card .marr-prose { font-size: 15px; font-weight: 600; color: #f1f5f9; line-height: 1.4; }
.marr-card .marr-link { color: #93c5fd; text-decoration: underline; text-decoration-color: rgba(147,197,253,0.4); }
.marr-card:has(.marr-link):hover { background: rgba(219,234,254,0.08); }
.marr-card .marr-meta { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.marr-card .evt-note-inline { font-size: 12px; }
/* ── Spouse picker (marriage/divorce add modal) ───────────── */
#event-modal-spouse-results { max-height: 160px; overflow-y: auto; background: #0f172a;
  border: 1px solid #334155; border-radius: 6px; margin-top: 4px; }
.spouse-result-item { padding: 6px 10px; cursor: pointer; font-size: 12px; color: #cbd5e1; }
.spouse-result-item:hover { background: #1e3a5f; }
/* ── Alias modal ─────────────────────────────────────────── */
#alias-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 1000; align-items: center; justify-content: center; }
#alias-modal-overlay.open { display: flex; }
#alias-modal { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
  padding: 20px; width: 420px; max-width: 90vw; }
/* ── Add-godparent modal ─────────────────────────────────── */
#add-godparent-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 1000; align-items: center; justify-content: center; }
#add-godparent-modal-overlay.open { display: flex; }
#add-godparent-modal { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
  padding: 20px; width: 420px; max-width: 90vw; }
#add-godparent-modal-results { max-height: 160px; overflow-y: auto; background: #0f172a;
  border: 1px solid #334155; border-radius: 6px; margin-top: 4px; }
.godparent-result-item { padding: 6px 10px; cursor: pointer; font-size: 12px; color: #cbd5e1; }
.godparent-result-item:hover { background: #1e3a5f; }
/* ── Sources viewer modal ────────────────────────────────── */
#sources-modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.55);
  z-index: 1000; align-items: center; justify-content: center; }
#sources-modal-overlay.open { display: flex; }
#sources-modal { background: #1e293b; border: 1px solid #334155; border-radius: 10px;
  padding: 20px; width: 480px; max-width: 90vw; max-height: 80vh; overflow-y: auto; }
#sources-modal-header { display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 14px; }
#sources-modal-title { font-size: 13px; font-weight: 600; color: #94a3b8; margin: 0; line-height: 1.4; }
#sources-modal-close { background: none; border: none; color: #64748b; cursor: pointer;
  font-size: 18px; line-height: 1; padding: 0 0 0 8px; flex-shrink: 0; }
#sources-modal-close:hover { color: #94a3b8; }
#sources-modal-list { margin: 0; }
.src-modal-item { padding: 10px 0; border-bottom: 1px solid #1e3a52; }
.src-modal-item:last-child { border-bottom: none; padding-bottom: 0; }
.src-modal-title { font-size: 13px; color: #cbd5e1; line-height: 1.4; }
.src-modal-title a { color: #93c5fd; text-underline-offset: 2px;
  text-decoration-color: rgba(147,197,253,0.4); }
.src-modal-title a:hover { text-decoration-color: rgba(147,197,253,0.8); }
.src-modal-page { font-size: 11px; color: #64748b; margin-top: 3px; }
.src-modal-empty { font-size: 13px; color: #475569; }
/* ── Citation badge on fact rows ─────────────────────────── */
.evt-src-badge { font-size: 10px; color: #475569; background: rgba(71,85,105,0.15);
  border: 1px solid rgba(71,85,105,0.3); border-radius: 3px; padding: 1px 5px;
  cursor: pointer; white-space: nowrap; transition: color .15s, border-color .15s,
  background .15s; position: absolute; right: 46px; top: 3px; line-height: 1.4; }
.evt-src-badge:hover { color: #93c5fd; border-color: rgba(147,197,253,0.5);
  background: rgba(147,197,253,0.08); }
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
.facts-pills { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.facts-pills .add-event-btn { margin-top: 0; }
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
/* ── Family section ─────────────────────────────────────── */
#detail-family.has-content { margin-top: 16px; }
.family-sub { margin-bottom: 0; }
.family-sub-heading { display: block; font-size: 10px; font-weight: 700; color: #475569;
  text-transform: uppercase; letter-spacing: 0.1em;
  border-top: 1px solid #1e3a52; padding-top: 12px; margin: 18px 0 10px 0; }
.family-sub:first-child .family-sub-heading { margin-top: 0; }
.family-row { display: flex; align-items: baseline; gap: 6px; padding: 4px 0; font-size: 13px; }
.family-link { color: #93c5fd; text-decoration: none; cursor: pointer; }
.family-link:hover { color: #bfdbfe; text-decoration: underline; }
.family-years { color: #475569; font-size: 12px; }
.family-sex-m { color: #7db4e8; font-size: 9px; opacity: 0.8; }
.family-sex-f { color: #e8a0be; font-size: 9px; opacity: 0.8; }
.family-marr-meta { color: #64748b; font-size: 11px; font-style: italic; padding: 1px 0 3px 0; }
.family-children { padding-left: 14px; border-left: 2px solid #1e293b; margin: 2px 0 2px 2px; }
.family-halfsib-group { margin-top: 12px; }
.family-halfsib-group:first-child { margin-top: 0; }
.family-halfsib-label { font-size: 11px; color: #64748b; margin-bottom: 4px; line-height: 1.5; }
.family-unknown { color: #475569; font-style: italic; }
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
<div id="gen-labels"></div>
<svg id="tree" xmlns="http://www.w3.org/2000/svg">
  <g id="canvas"></g>
</svg>
</div>
<div id="note-modal-overlay" onclick="if(event.target===this)closeNoteModal()">
  <div id="note-modal">
    <h3 id="note-modal-title">Edit Note</h3>
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
        <option value="MARR">Marriage</option>
        <option value="DIV">Divorce</option>
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
        <option value="CONF">Confirmation</option>
        <option value="PROB">Probate</option>
      </select>
    </div>
    <div class="event-modal-field" id="event-modal-spouse-row" style="display:none">
      <label>Spouse / Other Party</label>
      <input type="text" id="event-modal-spouse-input" placeholder="Search by name\u2026"
             autocomplete="off" onkeydown="if(event.key==='Escape')closeEventModal()">
      <div id="event-modal-spouse-results"></div>
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
    <div class="event-modal-field" id="event-modal-place-row">
      <label>Place</label>
      <input type="text" id="event-modal-place" list="plac-suggestions"
             onkeydown="if(event.key==='Escape')closeEventModal()">
      <datalist id="plac-suggestions"></datalist>
    </div>
    <div class="event-modal-field" id="event-modal-addr-row">
      <label>Address</label>
      <input type="text" id="event-modal-addr" list="addr-suggestions"
             placeholder="e.g. Church name or building"
             onkeydown="if(event.key==='Escape')closeEventModal()">
      <datalist id="addr-suggestions"></datalist>
    </div>
    <div class="event-modal-field" id="event-modal-cause-row" style="display:none">
      <label>Cause of Death</label>
      <input type="text" id="event-modal-cause" onkeydown="if(event.key==='Escape')closeEventModal()">
    </div>
    <div class="event-modal-field">
      <label>Note</label>
      <textarea id="event-modal-note" rows="3"
                onkeydown="if(event.key==='Escape')closeEventModal()"></textarea>
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
      <label>Given Name(s)</label>
      <input type="text" id="alias-modal-given" placeholder="e.g. Paul"
             onkeydown="if(event.key==='Escape')closeAliasModal();if(event.key==='Enter')submitAliasModal()">
    </div>
    <div class="event-modal-field">
      <label>Surname</label>
      <input type="text" id="alias-modal-surname" placeholder="e.g. Kemerli"
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
<div id="add-godparent-modal-overlay" onclick="if(event.target===this)closeAddGodparentModal()">
  <div id="add-godparent-modal">
    <h3 id="add-godparent-modal-title">Add Godparent</h3>
    <div class="event-modal-field">
      <label>Search by name</label>
      <input type="text" id="add-godparent-modal-search" placeholder="Type a name\u2026"
             onkeydown="if(event.key==='Escape')closeAddGodparentModal()">
      <div id="add-godparent-modal-results"></div>
    </div>
    <div class="event-modal-actions">
      <button class="event-modal-cancel" onclick="closeAddGodparentModal()">Cancel</button>
      <button class="event-modal-save" onclick="submitAddGodparentModal()">Add</button>
    </div>
  </div>
</div>
<div id="sources-modal-overlay" onclick="if(event.target===this)closeSourcesModal()">
  <div id="sources-modal">
    <div id="sources-modal-header">
      <div id="sources-modal-title">Sources</div>
      <button id="sources-modal-close" onclick="closeSourcesModal()" title="Close">&times;</button>
    </div>
    <div id="sources-modal-list"></div>
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
      <div id="detail-nationalities"></div>
    </div>
    <div id="detail-header-btns">
      <button id="panel-close-btn" title="Close">&#x2715;</button>
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
    <div id="detail-family"></div>
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
const PEOPLE = __PEOPLE_JSON__;
const ALL_PEOPLE = __ALL_PEOPLE_JSON__;
const SOURCES = __SOURCES_JSON__;
const RELATIVES = __RELATIVES_JSON__;
const PARENTS = __PARENTS_JSON__;
const CHILDREN = {};
for (const [cx, [fa, mo]] of Object.entries(PARENTS)) {
  for (const p of [fa, mo]) { if (p) { (CHILDREN[p] = CHILDREN[p] || []).push(cx); } }
}
const ROOT_XREF = __ROOT_XREF_JSON__;
const ADDR_BY_PLACE = __ADDR_BY_PLACE_JSON__;
const ALL_PLACES = __ALL_PLACES_JSON__;
</script>
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script src="/js/viz_design.js"></script>
<script src="/js/viz_state.js"></script>
<script src="/js/viz_api.js"></script>
<script src="/js/viz_layout.js"></script>
<script src="/js/viz_render.js"></script>
<script src="/js/viz_panel.js"></script>
<script src="/js/viz_search.js"></script>
<script src="/js/viz_modals.js"></script>
<script>
document.addEventListener('DOMContentLoaded', function () {
  console.log('[boot] DOMContentLoaded fired');
  console.log('[boot] ROOT_XREF =', ROOT_XREF);
  console.log('[boot] typeof initState =', typeof initState);
  console.log('[boot] typeof initRenderer =', typeof initRenderer);
  console.log('[boot] typeof initPanel =', typeof initPanel);
  console.log('[boot] typeof computeLayout =', typeof computeLayout);
  console.log('[boot] typeof render =', typeof render);
  console.log('[boot] PEOPLE keys (first 3):', Object.keys(PEOPLE || {}).slice(0, 3));

  try {
    initState(ROOT_XREF);
    console.log('[boot] initState OK, state =', JSON.stringify(getState()));
  } catch(e) { console.error('[boot] initState FAILED:', e); }

  try {
    initPanel(document.getElementById('detail-panel'));
    console.log('[boot] initPanel OK');
  } catch(e) { console.error('[boot] initPanel FAILED:', e); }

  const svgEl = document.getElementById('tree');
  console.log('[boot] svgEl =', svgEl);
  try {
    if (svgEl) initRenderer(svgEl);
    console.log('[boot] initRenderer OK');
  } catch(e) { console.error('[boot] initRenderer FAILED:', e); }

  onStateChange(function (state) { render(); });

  const homeBtn = document.getElementById('home-btn');
  if (homeBtn) homeBtn.addEventListener('click', () => setState({ focusXref: ROOT_XREF }));

  try {
    render();
    console.log('[boot] initial render OK');
  } catch(e) { console.error('[boot] render FAILED:', e); }
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
            for marr in fam.get('marrs', []):
                if marr.get('place'):
                    places.add(marr['place'])
            div = fam.get('div')
            if isinstance(div, dict) and div.get('place'):
                places.add(div['place'])
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
                fams: dict | None = None, root_xref: str | None = None,
                sources: dict | None = None) -> str:
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
    # Build global SOURCES dict: {xref: {titl, auth, publ, repo, note, url}}
    source_urls_global: dict[str, str] = {}
    for indi_info in indis.values():
        for sxref, url in indi_info.get('source_urls', {}).items():
            if url and sxref not in source_urls_global:
                source_urls_global[sxref] = url
    sources_js = {
        xref: {
            'titl': sour.get('titl') or '',
            'auth': sour.get('auth') or '',
            'publ': sour.get('publ') or '',
            'repo': sour.get('repo') or '',
            'note': sour.get('note') or '',
            'url': source_urls_global.get(xref) or None,
        }
        for xref, sour in (sources or {}).items()
    }
    sources_json = json.dumps(sources_js)
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
        .replace('__SOURCES_JSON__', sources_json)
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
    html = render_html(tree, root_name, people, relatives, indis, fams=fams, root_xref=root_xref,
                       sources=sources)
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
