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

_BET_RE       = re.compile(r'^BET\s+(.+?)\s+AND\s+(.+)$')
_DMY_RE       = re.compile(r'^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$')
_MY_RE        = re.compile(r'^([A-Z]{3})\s+(\d{4})$')
_YR_RE        = re.compile(r'^(\d{4})$')
_AGE_PARSE_RE = re.compile(r'^(?:(\d+)Y)?\s*(?:(\d+)M)?\s*(?:(\d+)D)?$')

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


def _parse_sour_line(state: dict, lvl: int, tag: str, val: str, raw_val: str, rec: dict) -> None:
    if lvl == 1 and tag in ('TITL', 'AUTH', 'PUBL', 'NOTE'):
        rec[tag.lower()] = _ged_val(val)
        state['current_field'] = tag.lower()
    elif lvl == 1 and tag == 'REPO':
        rec['repo'] = _ged_val(val)
        state['current_field'] = 'repo'
    elif lvl == 1:
        state['current_field'] = None
    elif tag in ('CONT', 'CONC') and state.get('current_field'):
        field = state['current_field']
        sep = '\n' if tag == 'CONT' else ''
        appended = _ged_val(raw_val if tag == 'CONC' else val)
        rec[field] = (rec[field] or '') + sep + appended


# ---------------------------------------------------------------------------
# FAM record parser
# ---------------------------------------------------------------------------

def _fam_handle_lvl1(state: dict, tag: str, val: str, rec: dict) -> None:
    if tag == 'HUSB':
        rec['husb'] = val
        state['current_evt'] = None
    elif tag == 'WIFE':
        rec['wife'] = val
        state['current_evt'] = None
    elif tag == 'CHIL':
        rec['chil'].append(val)
        state['current_evt'] = None
    elif tag in ('MARR', 'DIV'):
        evt = {'tag': tag, 'type': None, 'date': None, 'place': None,
               'note': None, 'age': None, 'addr': None, 'citations': []}
        rec.setdefault('marrs' if tag == 'MARR' else 'divs', []).append(evt)
        state['current_evt'] = evt
    else:
        state['current_evt'] = None
        state['current_evt_cite_field'] = None


def _fam_cont_conc(state: dict, lvl: int, tag: str, val: str, raw_val: str, evt: dict) -> None:
    field = state.get('current_evt_cite_field')
    citations = evt.get('citations')
    if not citations:
        return
    cite = citations[-1]
    sep = '\n' if tag == 'CONT' else ''
    appended = _ged_val(raw_val if tag == 'CONC' else val)
    if lvl == 4 and field == 'note':
        cite['note'] = (cite.get('note') or '') + sep + appended
    elif lvl == 5 and field == 'text':
        cite['text'] = (cite.get('text') or '') + sep + appended


def _parse_fam_line(state: dict, lvl: int, tag: str, val: str, raw_val: str, rec: dict) -> None:
    current_evt = state['current_evt']

    if lvl == 1:
        _fam_handle_lvl1(state, tag, val, rec)
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
            current_evt['citations'].append({'sour_xref': val, 'page': None, 'text': None, 'note': None})
            state['current_evt_cite_field'] = None
    elif tag == 'PAGE' and lvl == 3 and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['page'] = val
    elif tag == 'NOTE' and lvl == 3 and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['note'] = _ged_val(val)
        state['current_evt_cite_field'] = 'note'
    elif tag == 'QUAY' and lvl == 3 and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['quay'] = val.strip()
    elif tag == 'TEXT' and lvl == 4 and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['text'] = _ged_val(val)
        state['current_evt_cite_field'] = 'text'
    elif tag == 'DATE' and lvl == 4 and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['date'] = val.strip()
    elif tag in ('CONT', 'CONC') and current_evt is not None:
        _fam_cont_conc(state, lvl, tag, val, raw_val, current_evt)
    elif tag == 'WWW' and lvl in (3, 4) and current_evt is not None and current_evt.get('citations'):
        if not current_evt['citations'][-1].get('url'):
            current_evt['citations'][-1]['url'] = val


# ---------------------------------------------------------------------------
# INDI record parser
# ---------------------------------------------------------------------------

_INLINE_TYPE_TAGS = frozenset({'OCCU', 'TITL', 'NATI', 'RELI', 'EDUC', 'NCHI', 'DSCR'})


def _indi_handle_name(state: dict, val: str, rec: dict) -> None:
    name = re.sub(r'\s+', ' ', re.sub(r'/', '', html_mod.unescape(val))).strip()
    if rec['name'] is None:
        rec['name'] = name
        state['current_name_primary'] = True
        state['current_evt'] = state['current_note'] = None
    else:
        state['current_name_primary'] = False
        n = state['secondary_name_n']
        evt = {'tag': 'FACT', 'type': 'AKA', 'date': None, 'place': None,
               'cause': None, 'addr': None, 'note': name, 'inline_val': None,
               'age': None, 'citations': [], '_name_record': True, '_name_occurrence': n}
        state['secondary_name_n'] += 1
        rec['events'].append(evt)
        state['current_evt'] = evt
        state['current_note'] = None


def _indi_open_event(state: dict, tag: str, val: str, rec: dict) -> None:
    inline_type  = html_mod.unescape(val) if val and tag in _INLINE_TYPE_TAGS else None
    initial_note = None if tag in _INLINE_TYPE_TAGS else (html_mod.unescape(val) if val else None)
    evt = {'tag': tag, 'type': inline_type, 'date': None, 'place': None,
           'cause': None, 'addr': None, 'note': initial_note,
           'inline_val': val if val else None, 'age': None, 'citations': []}
    rec['events'].append(evt)
    state['current_evt'] = evt
    state['current_note'] = None
    state['current_evt_cite_field'] = None


def _indi_handle_note(state: dict, val: str, rec: dict) -> None:
    raw = _ged_val(val) if val else ''
    note_idx = len(rec['notes'])
    if val and val.startswith('@'):
        note_xref = val.rstrip()
        entry = state.get('shared_notes', {}).get(note_xref, {'text': raw, 'citations': []})
        note_obj = {'text': entry['text'], 'shared': True, 'note_xref': note_xref,
                    'citations': list(entry['citations']), 'note_idx': note_idx}
        state['current_note'] = None
    else:
        note_obj = {'text': raw, 'shared': False, 'note_xref': None,
                    'citations': [], 'note_idx': note_idx}
        state['current_note'] = note_idx
    rec['notes'].append(note_obj)
    state['current_evt'] = None


def _indi_handle_person_source(state: dict, val: str, rec: dict) -> None:
    if val not in rec['source_xrefs']:
        rec['source_xrefs'].append(val)
    cite_entry = {'sour_xref': val, 'page': None, 'text': None, 'note': None, 'url': None}
    rec['source_citations'].append(cite_entry)
    state['current_person_cite'] = cite_entry
    state['current_sour_xref']   = val
    state['current_cite_field']  = None
    state['current_evt'] = state['current_note'] = None


def _indi_handle_lvl1(state: dict, tag: str, val: str, raw_val: str, rec: dict) -> None:
    # Reset cross-tag cursors on each new level-1 tag
    if tag != 'SOUR':
        state['current_sour_xref']   = None
        state['current_person_cite'] = None
        state['current_cite_field']  = None
    if tag != 'ASSO':
        state['current_asso'] = None
    if tag != 'NAME':
        state['current_name_primary'] = False

    if tag == 'NAME':
        _indi_handle_name(state, val, rec)
    elif tag == 'SEX':
        rec['sex'] = val
        state['current_evt'] = state['current_note'] = None
    elif tag in _EVENT_TAGS:
        _indi_open_event(state, tag, val, rec)
    elif tag == 'NOTE':
        _indi_handle_note(state, val, rec)
    elif tag == 'FAMC' and rec['famc'] is None:
        rec['famc'] = val
        state['current_evt'] = state['current_note'] = None
    elif tag == 'FAMS':
        rec['fams'].append(val)
        state['current_evt'] = state['current_note'] = None
    elif tag == 'SOUR' and val.startswith('@'):
        _indi_handle_person_source(state, val, rec)
    elif tag == 'ASSO' and val.startswith('@'):
        state['current_asso'] = {'xref': val, 'rela': None}
        rec['asso'].append(state['current_asso'])
        state['current_evt'] = state['current_note'] = None
    else:
        state['current_evt'] = state['current_note'] = None


def _indi_evt_subfield(state: dict, tag: str, val: str, raw_val: str, rec: dict, evt: dict) -> None:
    if tag == 'DATE':
        evt['date'] = val
        ym = _YEAR_RE.search(val)
        if ym:
            yr = ym.group(1)
            if evt['tag'] == 'BIRT' and rec['birth_year'] is None:
                rec['birth_year'] = yr
            elif evt['tag'] == 'DEAT' and rec['death_year'] is None:
                rec['death_year'] = yr
    elif tag == 'PLAC':
        evt['place'] = html_mod.unescape(val)
    elif tag == 'TYPE':
        evt['type'] = html_mod.unescape(val)
    elif tag == 'CAUS':
        evt['cause'] = html_mod.unescape(val)
    elif tag == 'ADDR':
        evt['addr'] = html_mod.unescape(val)
    elif tag == 'NOTE':
        evt['note'] = _ged_val(val)
        state['current_note'] = 'event'
    elif tag == 'AGE':
        evt['age'] = val
    elif tag == 'SOUR' and val.startswith('@'):
        evt['citations'].append({'sour_xref': val, 'page': None, 'text': None, 'note': None})
        state['current_evt_cite_field'] = None


def _indi_handle_lvl2(state: dict, tag: str, val: str, raw_val: str, rec: dict) -> None:
    current_evt         = state['current_evt']
    current_note        = state['current_note']
    current_person_cite = state['current_person_cite']
    current_asso        = state['current_asso']

    if state.get('current_name_primary') and tag in ('GIVN', 'SURN', 'NSFX'):
        v = html_mod.unescape(val).strip() if val else None
        if tag == 'GIVN':
            rec['name_given'] = v
        elif tag == 'SURN':
            rec['name_surname'] = v
        elif tag == 'NSFX':
            rec['name_suffix'] = v
    elif current_evt is not None:
        _indi_evt_subfield(state, tag, val, raw_val, rec, current_evt)
    elif tag in ('CONT', 'CONC') and isinstance(current_note, int):
        sep = '\n' if tag == 'CONT' else ''
        rec['notes'][current_note]['text'] += sep + _ged_val(raw_val if tag == 'CONC' else val)
    elif tag == 'SOUR' and isinstance(current_note, int) and val.startswith('@'):
        rec['notes'][current_note]['citations'].append({'sour_xref': val, 'page': None})
    elif tag == 'RELA' and current_asso is not None:
        current_asso['rela'] = html_mod.unescape(val)
    elif tag == 'PAGE' and current_person_cite is not None:
        current_person_cite['page'] = val
    elif tag == 'NOTE' and current_person_cite is not None:
        current_person_cite['note'] = _ged_val(val)
        state['current_cite_field'] = 'note'
    elif tag == 'QUAY' and current_person_cite is not None:
        current_person_cite['quay'] = val.strip()
    elif tag == 'WWW' and current_person_cite is not None:
        if current_person_cite.get('url') is None:
            current_person_cite['url'] = val


def _indi_handle_lvl3(state: dict, tag: str, val: str, raw_val: str, rec: dict) -> None:
    current_evt         = state['current_evt']
    current_note        = state['current_note']
    current_person_cite = state['current_person_cite']

    if tag == 'PAGE' and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['page'] = val
    elif tag == 'NOTE' and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['note'] = _ged_val(val)
        state['current_evt_cite_field'] = 'note'
    elif tag == 'QUAY' and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['quay'] = val.strip()
    elif tag in ('CONT', 'CONC') and current_note == 'event':
        sep = '\n' if tag == 'CONT' else ''
        current_evt['note'] += sep + _ged_val(raw_val if tag == 'CONC' else val)
    elif tag == 'PAGE' and isinstance(current_note, int):
        cites = rec['notes'][current_note].get('citations')
        if cites:
            cites[-1]['page'] = val
    elif tag == 'TEXT' and current_person_cite is not None:
        current_person_cite['text'] = _ged_val(val)
        state['current_cite_field'] = 'text'
    elif tag == 'DATE' and current_person_cite is not None:
        current_person_cite['date'] = val.strip()
    elif tag in ('CONT', 'CONC') and current_person_cite is not None and state['current_cite_field'] == 'note':
        sep = '\n' if tag == 'CONT' else ''
        current_person_cite['note'] = (current_person_cite['note'] or '') + sep + _ged_val(raw_val if tag == 'CONC' else val)
    elif tag == 'WWW' and current_evt is not None and current_evt.get('citations'):
        if not current_evt['citations'][-1].get('url'):
            current_evt['citations'][-1]['url'] = val
    elif tag == 'WWW' and state['current_sour_xref'] is not None:
        sxref = state['current_sour_xref']
        if sxref not in rec['source_urls']:
            rec['source_urls'][sxref] = val
        if current_person_cite is not None and current_person_cite.get('url') is None:
            current_person_cite['url'] = val


def _indi_handle_lvl4(state: dict, tag: str, val: str, raw_val: str, rec: dict) -> None:
    current_evt         = state['current_evt']
    current_person_cite = state['current_person_cite']

    if tag == 'TEXT' and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['text'] = _ged_val(val)
        state['current_evt_cite_field'] = 'text'
    elif tag == 'DATE' and current_evt is not None and current_evt.get('citations'):
        current_evt['citations'][-1]['date'] = val.strip()
    elif tag in ('CONT', 'CONC') and current_evt is not None and current_evt.get('citations') and state.get('current_evt_cite_field') == 'note':
        sep = '\n' if tag == 'CONT' else ''
        current_evt['citations'][-1]['note'] = (current_evt['citations'][-1].get('note') or '') + sep + _ged_val(raw_val if tag == 'CONC' else val)
    elif tag in ('CONT', 'CONC') and current_person_cite is not None and state['current_cite_field'] == 'text':
        sep = '\n' if tag == 'CONT' else ''
        current_person_cite['text'] = (current_person_cite['text'] or '') + sep + _ged_val(raw_val if tag == 'CONC' else val)
    elif tag == 'WWW' and current_evt is not None and current_evt.get('citations'):
        if not current_evt['citations'][-1].get('url'):
            current_evt['citations'][-1]['url'] = val


def _indi_handle_lvl5(state: dict, tag: str, val: str, raw_val: str, rec: dict) -> None:
    current_evt = state['current_evt']
    if tag in ('CONT', 'CONC') and current_evt is not None and current_evt.get('citations') and state.get('current_evt_cite_field') == 'text':
        sep = '\n' if tag == 'CONT' else ''
        current_evt['citations'][-1]['text'] = (current_evt['citations'][-1].get('text') or '') + sep + _ged_val(raw_val if tag == 'CONC' else val)


def _parse_indi_line(state: dict, lvl: int, tag: str, val: str, raw_val: str, rec: dict) -> None:
    if lvl == 1:
        _indi_handle_lvl1(state, tag, val, raw_val, rec)
    elif lvl == 2:
        _indi_handle_lvl2(state, tag, val, raw_val, rec)
    elif lvl == 3:
        _indi_handle_lvl3(state, tag, val, raw_val, rec)
    elif lvl == 4:
        _indi_handle_lvl4(state, tag, val, raw_val, rec)
    elif lvl == 5:
        _indi_handle_lvl5(state, tag, val, raw_val, rec)


def parse_gedcom(path: str) -> tuple[dict, dict, dict]:
    """
    Returns (indis, fams, sources).
      indis: {xref: {name, birth_year, death_year, famc, sex, events, notes}}
        events: list of {tag, type, date, place}
        notes:  list of str (CONT lines joined with \n)
      fams:  {xref: {husb, wife, chil, marrs, divs}}
    """
    with open(path, encoding='utf-8') as f:
        lines = [ln.rstrip('\n') for ln in f]

    shared_notes = _collect_shared_notes(lines)

    indis: dict   = {}
    fams: dict    = {}
    sources: dict = {}
    ctx       = None   # ('indi', xref) or ('fam', xref) or ('sour', xref)
    indi_st   = {}     # state dict passed to _parse_indi_line
    fam_st    = {}     # state dict passed to _parse_fam_line

    for line in lines:
        m = _INDI_RE.match(line)
        if m:
            xref = m.group(1)
            indis[xref] = {
                'name': None, 'name_given': None, 'name_surname': None, 'name_suffix': None,
                'birth_year': None, 'death_year': None,
                'famc': None, 'fams': [], 'sex': None, 'events': [], 'notes': [],
                'source_xrefs': [], 'source_urls': {}, 'source_citations': [], 'asso': [],
            }
            ctx     = ('indi', xref)
            indi_st = {
                'current_evt': None, 'current_note': None,
                'current_sour_xref': None, 'current_person_cite': None,
                'current_cite_field': None, 'current_asso': None,
                'current_evt_cite_field': None,
                'current_name_primary': False,
                'secondary_name_n': 0, 'shared_notes': shared_notes,
            }
            continue

        m = _FAM_RE.match(line)
        if m:
            xref = m.group(1)
            fams[xref] = {'husb': None, 'wife': None, 'chil': []}
            ctx    = ('fam', xref)
            fam_st = {'current_evt': None, 'current_evt_cite_field': None}
            continue

        m = _SOUR_RE.match(line)
        if m:
            xref = m.group(1)
            sources[xref] = {'titl': None, 'auth': None, 'publ': None, 'repo': None, 'note': None}
            ctx = ('sour', xref)
            sour_st: dict = {'current_field': None}
            continue

        if line.startswith('0 '):
            ctx = None
            continue

        if ctx is None:
            continue

        tm = _TAG_RE.match(line)
        if not tm:
            continue
        lvl     = int(tm.group(1))
        tag     = tm.group(2)
        raw_val = tm.group(3) or ''
        val     = raw_val.strip()

        if ctx[0] == 'indi':
            _parse_indi_line(indi_st, lvl, tag, val, raw_val, indis[ctx[1]])
        elif ctx[0] == 'fam':
            _parse_fam_line(fam_st, lvl, tag, val, raw_val, fams[ctx[1]])
        elif ctx[0] == 'sour':
            _parse_sour_line(sour_st, lvl, tag, val, raw_val, sources[ctx[1]])

    return indis, fams, sources


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
    m = _AGE_PARSE_RE.match(s)
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
    bet = _BET_RE.match(s)
    if bet:
        s = bet.group(1)
    dmy = _DMY_RE.match(s)
    if dmy:
        return (int(dmy.group(3)), _MONTH_NUM.get(dmy.group(2), 0), int(dmy.group(1)), adjust)
    my = _MY_RE.match(s)
    if my:
        return (int(my.group(2)), _MONTH_NUM.get(my.group(1), 0), 0, adjust)
    yr = _YR_RE.match(s)
    if yr:
        return (int(yr.group(1)), 0, 0, adjust)
    return (0, 0, 0, 0)


_EVENT_ORDER = {'BIRT': 0, 'DEAT': 2, 'BURI': 4, 'PROB': 5}
_DEATH_RELATED_KEYWORDS = ('death announcement', 'obituar', 'avis de décès')


def _event_sort_order(evt: dict) -> int:
    tag = evt.get('tag', '')
    if tag in _EVENT_ORDER:
        return _EVENT_ORDER[tag]
    if tag == 'EVEN':
        typ = (evt.get('type') or '').lower()
        if any(kw in typ for kw in _DEATH_RELATED_KEYWORDS):
            return 3
    return 1


def sort_events(events: list) -> list:
    """Sort events chronologically, with fixed pins:
       BIRT first, then general events by date, then DEAT, Death Announcement, BURI, PROB."""
    return sorted(events, key=lambda e: (_event_sort_order(e),) + _date_sort_key(e.get('date')))


def _matches_exclusion(evt: dict, excl: dict) -> bool:
    """Return True if evt matches an exclusion entry (same xref checked by caller)."""
    if evt.get('tag') != excl.get('tag'):
        return False
    for field in ('date', 'place', 'type', 'inline_val'):
        excl_val = excl.get(field) or None
        if excl_val is not None and (evt.get(field) or None) != excl_val:
            return False
    return True


def _normalize_citation(c: dict) -> dict:
    return {'sourceXref': c['sour_xref'], **{k: v for k, v in c.items() if k != 'sour_xref'}}


def _spouse_of(fam: dict, xref: str) -> str | None:
    if fam.get('husb') == xref:
        return fam.get('wife')
    if fam.get('wife') == xref:
        return fam.get('husb')
    return None


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
                    'quay':        cite.get('quay') or '',
                    'date':        cite.get('date') or '',
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
            normalised_cites = [_normalize_citation(c) for c in e.get('citations', [])]
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
                spouse_xref = _spouse_of(fam, xref)
                spouse_name = indis[spouse_xref]['name'] if spouse_xref and spouse_xref in indis else None
                appended = False
                for marr_idx, marr in enumerate(marrs):
                    # Skip bare duplicate MARR entries (no sub-tags) that can appear after a merge
                    if not any(marr.get(f) for f in ('date', 'place', 'addr', 'note', 'type', 'citations')):
                        continue
                    marr_cites = [_normalize_citation(c) for c in marr.get('citations', [])]
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
                    div_cites = [_normalize_citation(c) for c in div.get('citations', [])]
                    events.append({**div, 'citations': div_cites,
                                   'event_idx': None, 'div_idx': div_idx,
                                   'spouse': spouse_name, 'spouse_xref': spouse_xref,
                                   'fam_xref': fam_xref})
        age_at_death = next(
            (cls for e in events
             if e['tag'] == 'DEAT' and e.get('age')
             and (cls := _classify_death_age(e['age']))),
            None
        )
        normalised_notes = []
        for n in info.get('notes', []):
            norm_cites = [_normalize_citation(c) for c in n.get('citations', [])]
            normalised_notes.append({**n, 'citations': norm_cites})
        result[xref] = {
            'name':         info['name'] or '?',
            'name_given':   info.get('name_given'),
            'name_surname': info.get('name_surname'),
            'name_suffix':  info.get('name_suffix'),
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
            spouse_xref = _spouse_of(fam, xref)
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
                sp_xref = _spouse_of(fam, sib_xref)
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
            for div in fam.get('divs', []):
                if div.get('place'):
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


def _build_parents_map(indis: dict, fams: dict) -> dict:
    parents = {}
    for xref, info in indis.items():
        famc = info.get('famc')
        if famc and famc in fams:
            fam = fams[famc]
            parents[xref] = [fam.get('husb'), fam.get('wife')]
        else:
            parents[xref] = [None, None]
    return parents


def _build_families_js(fams: dict) -> dict:
    families = {}
    for fam_xref, fam in fams.items():
        marr_year = None
        for marr in fam.get('marrs', []):
            date = marr.get('date')
            if date:
                ym = _YEAR_RE.search(date)
                if ym:
                    marr_year = int(ym.group(1))
                    break
        families[fam_xref] = {
            'husb': fam.get('husb'),
            'wife': fam.get('wife'),
            'chil': list(fam.get('chil', [])),
            'marr_year': marr_year,
        }
    return families


def _aggregate_source_urls(indis: dict) -> dict[str, str]:
    urls: dict[str, str] = {}
    for indi_info in indis.values():
        for sxref, url in indi_info.get('source_urls', {}).items():
            if url and sxref not in urls:
                urls[sxref] = url
    return urls


def _build_sources_js(sources: dict, source_urls: dict) -> dict:
    return {
        xref: {
            'titl': sour.get('titl') or '',
            'auth': sour.get('auth') or '',
            'publ': sour.get('publ') or '',
            'repo': sour.get('repo') or '',
            'note': sour.get('note') or '',
            'url':  source_urls.get(xref) or None,
        }
        for xref, sour in sources.items()
    }


def render_html(tree: dict, root_name: str, people: dict, relatives: dict, indis: dict,
                fams: dict | None = None, root_xref: str | None = None,
                sources: dict | None = None) -> str:
    """Return a complete self-contained HTML string."""
    all_people = sorted(
        [{"id": xref, "name": info["name"] or "",
          "birth_year": info.get("birth_year") or "",
          "death_year": info.get("death_year") or ""}
         for xref, info in indis.items()],
        key=lambda p: p["name"].lower()
    )
    parents     = _build_parents_map(indis, fams) if fams else {}
    families_js = _build_families_js(fams) if fams else {}
    source_urls = _aggregate_source_urls(indis)
    sources_js  = _build_sources_js(sources or {}, source_urls)

    return (
        _HTML_TEMPLATE
        .replace('__STYLES__',             _CSS)
        .replace('__ROOT_NAME__',          html_mod.escape(root_name))
        .replace('__TREE_JSON__',          _json_for_script(tree))
        .replace('__PEOPLE_JSON__',        _json_for_script(people))
        .replace('__ALL_PEOPLE_JSON__',    _json_for_script(all_people))
        .replace('__RELATIVES_JSON__',     _json_for_script(relatives))
        .replace('__PARENTS_JSON__',       _json_for_script(parents))
        .replace('__FAMILIES_JSON__',      _json_for_script(families_js))
        .replace('__ROOT_XREF_JSON__',     _json_for_script(root_xref or ''))
        .replace('__ADDR_BY_PLACE_JSON__', _json_for_script(build_addr_by_place(indis)))
        .replace('__ALL_PLACES_JSON__',    _json_for_script(build_all_places(indis, fams)))
        .replace('__SOURCES_JSON__',       _json_for_script(sources_js))
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
