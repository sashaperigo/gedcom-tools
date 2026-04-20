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
from pathlib import Path

_INDI_RE = re.compile(r'^0 (@[^@]+@) INDI\b')
_FAM_RE  = re.compile(r'^0 (@[^@]+@) FAM\b')
_SOUR_RE = re.compile(r'^0 (@[^@]+@) SOUR\b')
_NOTE_RE = re.compile(r'^0 (@[^@]+@) NOTE\b(?: (.*))?$')
_TAG_RE  = re.compile(r'^(\d+) (\w+)(?: (.*))?$')
_YEAR_RE = re.compile(r'\b(\d{4})\b')

_EVENT_TAGS = frozenset({
    'BIRT', 'DEAT', 'BURI', 'RESI', 'OCCU', 'CHR', 'BAPM',
    'NATU', 'IMMI', 'EVEN', 'FACT', 'NATI', 'RELI', 'TITL',
    'ADOP', 'EDUC', 'RETI', 'DIV', 'CONF', 'PROB',
    'NCHI', 'DSCR',
})


# ---------------------------------------------------------------------------
# GEDCOM parsing
# ---------------------------------------------------------------------------

def _ged_val(raw: str) -> str:
    """Decode a raw GEDCOM line value for display.

    Applies two unescaping steps in order:
      1. GEDCOM pointer escape: '@@' → '@'  (literal at-sign in a value)
      2. HTML entity unescape: '&amp;' → '&' etc.  (carried over from some exports)
    """
    return html_mod.unescape(raw.replace('@@', '@'))


def _collect_shared_notes(lines: list[str]) -> dict[str, dict]:
    """Pass 1: collect all top-level '0 @xref@ NOTE' records into {xref: {text, citations}}."""
    shared: dict[str, dict] = {}
    current_xref: str | None = None
    for line in lines:
        m = _NOTE_RE.match(line)
        if m:
            current_xref = m.group(1)
            shared[current_xref] = {'text': _ged_val(m.group(2) or ''), 'citations': []}
            continue
        if line.startswith('0 '):
            current_xref = None
            continue
        if current_xref is not None:
            m2 = _TAG_RE.match(line)
            if not m2:
                continue
            lvl2, tag2 = int(m2.group(1)), m2.group(2)
            raw2 = m2.group(3) or ''
            val2 = raw2.strip()
            if tag2 in ('CONT', 'CONC'):
                sep = '\n' if tag2 == 'CONT' else ''
                # CONC: preserve leading space — it's the inter-word space placed at the
                # start of the continuation line per GEDCOM 5.5.5 spec recommendation.
                # CONT: strip is safe since '\n' already provides the word boundary.
                conc_raw = raw2 if tag2 == 'CONC' else val2
                shared[current_xref]['text'] += sep + _ged_val(conc_raw)
            elif lvl2 == 1 and tag2 == 'SOUR' and val2.startswith('@'):
                shared[current_xref]['citations'].append({'sour_xref': val2, 'page': None})
            elif lvl2 == 2 and tag2 == 'PAGE' and shared[current_xref]['citations']:
                shared[current_xref]['citations'][-1]['page'] = val2
    return shared


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

    shared_notes = _collect_shared_notes(lines)

    indis: dict  = {}
    fams: dict   = {}
    sources: dict = {}   # xref -> title
    ctx                = None   # ('indi', xref) or ('fam', xref) or ('sour', xref)
    current_evt        = None   # current event dict being built
    current_note       = None   # index into notes[] for CONT assembly
    current_sour_xref  = None   # xref of the 1 SOUR citation currently being parsed
    current_person_cite = None  # dict for the current person-level SOUR citation
    current_cite_field  = None  # 'text' or 'note' — which field CONT/CONC lines belong to
    current_asso       = None   # dict being built for an in-progress 1 ASSO block
    secondary_name_n   = 0      # counter for secondary NAME records within current INDI

    for line in lines:
        m = _INDI_RE.match(line)
        if m:
            xref = m.group(1)
            indis[xref] = {
                'name': None, 'birth_year': None, 'death_year': None,
                'famc': None, 'fams': [], 'sex': None, 'events': [], 'notes': [], 'source_xrefs': [], 'source_urls': {},
                'source_citations': [],
                'asso': [],
            }
            ctx                 = ('indi', xref)
            current_evt         = None
            current_note        = None
            current_person_cite = None
            current_cite_field  = None
            secondary_name_n    = 0
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
        raw_val = tm.group(3) or ''
        val = raw_val.strip()

        if ctx[0] == 'indi':
            xref = ctx[1]
            if lvl == 1 and tag != 'SOUR':
                current_sour_xref   = None
                current_person_cite = None
                current_cite_field  = None
            if lvl == 1 and tag != 'ASSO':
                current_asso = None
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
                _INLINE_TYPE_TAGS = frozenset({'OCCU', 'TITL', 'NATI', 'RELI', 'EDUC', 'NCHI', 'DSCR'})
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
                    current_evt['note'] = _ged_val(val)
                    current_note = 'event'   # sentinel: subsequent CONT/CONC at lvl 3 belong here
                elif tag == 'AGE':
                    current_evt['age'] = val
                elif tag == 'SOUR' and val.startswith('@'):
                    current_evt['citations'].append({'sour_xref': val, 'page': None})
            elif lvl == 3 and tag == 'PAGE' and current_evt is not None and current_evt.get('citations'):
                current_evt['citations'][-1]['page'] = val
            elif lvl == 3 and tag == 'WWW' and current_evt is not None and current_evt.get('citations'):
                if not current_evt['citations'][-1].get('url'):
                    current_evt['citations'][-1]['url'] = val
            elif lvl == 4 and tag == 'WWW' and current_evt is not None and current_evt.get('citations'):
                if not current_evt['citations'][-1].get('url'):
                    current_evt['citations'][-1]['url'] = val
            elif lvl == 3 and tag in ('CONT', 'CONC') and current_note == 'event':
                sep = '\n' if tag == 'CONT' else ''
                current_evt['note'] += sep + _ged_val(raw_val if tag == 'CONC' else val)
            elif lvl == 1 and tag == 'NOTE':
                raw = _ged_val(val) if val else ''
                note_idx = len(indis[xref]['notes'])
                if val and val.startswith('@'):
                    note_xref = val.rstrip()
                    entry = shared_notes.get(note_xref, {'text': raw, 'citations': []})
                    note_obj = {'text': entry['text'], 'shared': True, 'note_xref': note_xref,
                                'citations': list(entry['citations']), 'note_idx': note_idx}
                    current_note = None  # shared note: CONT/CONC belong to top-level record, not here
                else:
                    note_obj = {'text': raw, 'shared': False, 'note_xref': None,
                                'citations': [], 'note_idx': note_idx}
                    current_note = note_idx
                indis[xref]['notes'].append(note_obj)
                current_evt  = None
            elif lvl == 2 and tag in ('CONT', 'CONC') and isinstance(current_note, int):
                sep = '\n' if tag == 'CONT' else ''
                indis[xref]['notes'][current_note]['text'] += sep + _ged_val(raw_val if tag == 'CONC' else val)
            elif lvl == 2 and tag == 'SOUR' and isinstance(current_note, int) and val.startswith('@'):
                indis[xref]['notes'][current_note]['citations'].append({'sour_xref': val, 'page': None})
            elif lvl == 3 and tag == 'PAGE' and isinstance(current_note, int):
                cites = indis[xref]['notes'][current_note].get('citations')
                if cites:
                    cites[-1]['page'] = val
            elif lvl == 1 and tag == 'FAMC' and indis[xref]['famc'] is None:
                indis[xref]['famc'] = val
                current_evt = current_note = None
            elif lvl == 1 and tag == 'FAMS':
                indis[xref]['fams'].append(val)
                current_evt = current_note = None
            elif lvl == 1 and tag == 'SOUR' and val.startswith('@'):
                if val not in indis[xref]['source_xrefs']:
                    indis[xref]['source_xrefs'].append(val)
                cite_entry = {'sour_xref': val, 'page': None, 'text': None, 'note': None, 'url': None}
                indis[xref]['source_citations'].append(cite_entry)
                current_person_cite = cite_entry
                current_sour_xref   = val
                current_cite_field  = None
                current_evt = current_note = None
            elif lvl == 1 and tag == 'ASSO' and val.startswith('@'):
                current_asso = {'xref': val, 'rela': None}
                indis[xref]['asso'].append(current_asso)
                current_evt = current_note = None
            elif lvl == 2 and tag == 'RELA' and current_asso is not None:
                current_asso['rela'] = html_mod.unescape(val)
            elif lvl == 2 and tag == 'PAGE' and current_person_cite is not None:
                current_person_cite['page'] = val
            elif lvl == 2 and tag == 'NOTE' and current_person_cite is not None:
                current_person_cite['note'] = _ged_val(val)
                current_cite_field = 'note'
            elif lvl == 2 and tag == 'WWW' and current_person_cite is not None:
                if current_person_cite.get('url') is None:
                    current_person_cite['url'] = val
            elif lvl == 3 and tag == 'TEXT' and current_person_cite is not None:
                current_person_cite['text'] = _ged_val(val)
                current_cite_field = 'text'
            elif lvl == 4 and tag in ('CONT', 'CONC') and current_person_cite is not None and current_cite_field == 'text':
                sep = '\n' if tag == 'CONT' else ''
                current_person_cite['text'] = (current_person_cite['text'] or '') + sep + _ged_val(raw_val if tag == 'CONC' else val)
            elif lvl == 3 and tag in ('CONT', 'CONC') and current_person_cite is not None and current_cite_field == 'note':
                sep = '\n' if tag == 'CONT' else ''
                current_person_cite['note'] = (current_person_cite['note'] or '') + sep + _ged_val(raw_val if tag == 'CONC' else val)
            elif lvl == 3 and tag == 'WWW' and current_sour_xref is not None:
                if current_sour_xref not in indis[xref]['source_urls']:
                    indis[xref]['source_urls'][current_sour_xref] = val
                if current_person_cite is not None and current_person_cite.get('url') is None:
                    current_person_cite['url'] = val
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
                evt = {'tag': 'MARR', 'type': None, 'date': None, 'place': None, 'note': None, 'age': None, 'addr': None, 'citations': []}
                fams[xref].setdefault('marrs', []).append(evt)
                current_evt = evt
            elif lvl == 1 and tag == 'DIV':
                evt = {'tag': 'DIV', 'type': None, 'date': None, 'place': None, 'note': None, 'age': None, 'addr': None, 'citations': []}
                fams[xref].setdefault('divs', []).append(evt)
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
                elif tag == 'SOUR' and val.startswith('@'):
                    current_evt['citations'].append({'sour_xref': val, 'page': None})
            elif lvl == 3 and tag == 'PAGE' and current_evt is not None and current_evt.get('citations'):
                current_evt['citations'][-1]['page'] = val
            elif lvl == 3 and tag == 'WWW' and current_evt is not None and current_evt.get('citations'):
                if not current_evt['citations'][-1].get('url'):
                    current_evt['citations'][-1]['url'] = val
            elif lvl == 4 and tag == 'WWW' and current_evt is not None and current_evt.get('citations'):
                if not current_evt['citations'][-1].get('url'):
                    current_evt['citations'][-1]['url'] = val
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


_DEAT_AGE_KEYWORDS = frozenset({'STILLBORN', 'INFANT', 'CHILD'})


def _classify_death_age(age: str) -> str | None:
    """Return 'STILLBORN' / 'INFANT' / 'CHILD' for early-death ages, else None.
    Accepts keyword values and numeric forms: 'INFANT' for < 1 year, 'CHILD'
    for 1–12 years inclusive."""
    if not age:
        return None
    s = age.strip().upper().lstrip('<>').strip()
    if s in _DEAT_AGE_KEYWORDS:
        return s
    m = re.match(
        r'^(?:(\d+)Y)?\s*(?:(\d+)M)?\s*(?:(\d+)D)?$',
        s,
    )
    if not m or not any(m.groups()):
        return None
    years  = int(m.group(1) or 0)
    months = int(m.group(2) or 0)
    days   = int(m.group(3) or 0)
    if years == 0 and months == 0 and days == 0:
        return None
    if years < 1:
        return 'INFANT'
    if years <= 12:
        return 'CHILD'
    return None


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
        if sources:
            source_urls = info.get('source_urls', {})
            for i, cite in enumerate(info.get('source_citations', [])):
                sxref = cite.get('sour_xref') or ''
                sour  = sources.get(sxref) or {}
                title = (sour.get('titl') if isinstance(sour, dict) else sour) or ''
                url   = cite.get('url') or source_urls.get(sxref) or None
                src_list.append({
                    'title':       title or sxref,
                    'url':         url,
                    'sourceXref':  sxref,
                    'citationKey': f'SOUR:{i}',
                    'page':        cite.get('page') or '',
                    'text':        cite.get('text') or '',
                    'note':        cite.get('note') or '',
                })
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
            # Attach godparent ASSOs (stored at the INDI level) to BAPM/CHR
            # events so the panel can render them as pills.
            if t in ('BAPM', 'CHR'):
                e_out['asso'] = [
                    {'xref': a['xref'], 'rela': a.get('rela')}
                    for a in info.get('asso', []) or []
                ]
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
                    marr_cites = [
                        {'sourceXref': c['sour_xref'], **{k: v for k, v in c.items() if k != 'sour_xref'}}
                        for c in marr.get('citations', [])
                    ]
                    # MARR events live in FAM blocks; event_idx=None marks them as non-editable via INDI
                    events.append({**marr, 'citations': marr_cites,
                                   'event_idx': None, 'marr_idx': marr_idx,
                                   'spouse': spouse_name, 'spouse_xref': spouse_xref,
                                   'fam_xref': fam_xref})
                    appended = True
                if not appended and spouse_xref:
                    # FAM has no MARR record (or only bare duplicates) — emit a
                    # synthetic event so the spouse still appears in the panel.
                    events.append({'tag': 'MARR', 'type': None, 'date': None,
                                   'place': None, 'note': None, 'age': None, 'addr': None,
                                   'citations': [],
                                   'event_idx': None, 'marr_idx': 0,
                                   'spouse': spouse_name, 'spouse_xref': spouse_xref,
                                   'fam_xref': fam_xref})
                for div_idx, div in enumerate(fam.get('divs', [])):
                    if not any(div.get(f) for f in ('date', 'place', 'addr', 'note', 'type')):
                        continue
                    div_cites = [
                        {'sourceXref': c['sour_xref'], **{k: v for k, v in c.items() if k != 'sour_xref'}}
                        for c in div.get('citations', [])
                    ]
                    events.append({**div, 'citations': div_cites,
                                   'event_idx': None, 'div_idx': div_idx,
                                   'spouse': spouse_name, 'spouse_xref': spouse_xref,
                                   'fam_xref': fam_xref})
        age_at_death = next(
            (_classify_death_age(e['age']) for e in events
             if e['tag'] == 'DEAT' and e.get('age')
             and _classify_death_age(e['age'])),
            None
        )
        normalised_notes = []
        for n in info.get('notes', []):
            norm_cites = [
                {'sourceXref': c['sour_xref'], **{k: v for k, v in c.items() if k != 'sour_xref'}}
                for c in n.get('citations', [])
            ]
            normalised_notes.append({**n, 'citations': norm_cites})
        result[xref] = {
            'name':         info['name'] or '?',
            'birth_year':   info['birth_year'],
            'death_year':   info['death_year'],
            'sex':          info['sex'],
            'events':       sort_events(events),
            'notes':        normalised_notes,
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


def build_family_maps(indis: dict, fams: dict, tree: dict | None = None) -> dict:
    """Return {'parents', 'children', 'relatives'} — the three maps the client
    uses to render the Family panel section. Call after a structural edit so the
    client can replace its stale globals in-place."""
    parents: dict[str, list] = {}
    children: dict[str, list] = {}
    for xref, info in indis.items():
        famc = info.get('famc')
        if famc and famc in fams:
            fam = fams[famc]
            fa, mo = fam.get('husb'), fam.get('wife')
            parents[xref] = [fa, mo]
            for p in (fa, mo):
                if p:
                    children.setdefault(p, []).append(xref)
        else:
            parents[xref] = [None, None]
    relatives = build_relatives_json(tree or {}, indis, fams)
    return {'parents': parents, 'children': children, 'relatives': relatives}


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent
_HTML_TEMPLATE = (_TEMPLATE_DIR / "viz_ancestors.html").read_text(encoding="utf-8")
_CSS = (_TEMPLATE_DIR / "viz_ancestors.css").read_text(encoding="utf-8")


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


def _json_for_script(obj) -> str:
    """Serialize to JSON safe for embedding in an inline <script> block.
    Escapes `</` as `<\\/` so a user-supplied "</script" substring cannot
    terminate the enclosing <script> element."""
    return json.dumps(obj).replace('</', '<\\/')


def render_html(tree: dict, root_name: str, people: dict, relatives: dict, indis: dict,
                fams: dict | None = None, root_xref: str | None = None,
                sources: dict | None = None) -> str:
    """Return a complete self-contained HTML string."""
    safe_name      = html_mod.escape(root_name)
    tree_json      = _json_for_script(tree)
    people_json    = _json_for_script(people)
    relatives_json = _json_for_script(relatives)
    all_people     = sorted(
        [{"id": xref, "name": info["name"] or "",
          "birth_year": info.get("birth_year") or "",
          "death_year": info.get("death_year") or ""}
         for xref, info in indis.items()],
        key=lambda p: p["name"].lower()
    )
    all_people_json = _json_for_script(all_people)
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
    parents_json        = _json_for_script(parents)
    root_xref_json      = _json_for_script(root_xref or '')
    addr_by_place_json  = _json_for_script(build_addr_by_place(indis))
    all_places_json     = _json_for_script(build_all_places(indis, fams))
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
    sources_json = _json_for_script(sources_js)
    return (
        _HTML_TEMPLATE
        .replace('__STYLES__', _CSS)
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
