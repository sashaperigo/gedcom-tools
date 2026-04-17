#!/usr/bin/env python3
"""
Dev server: watches viz_ancestors.py for changes, regenerates the HTML,
and serves it on http://localhost:8080/viz.html

Fact and note deletions are written to disk immediately (with an atomic backup).
Event edits and additions are also written immediately.
"""
import http.server
import importlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

from gedcom_linter import normalize_date, GEDCOM_DATE_RE

import viz_ancestors as _viz_mod
_viz_mtime: float | None = None


def _viz():
    """Return viz_ancestors module, reloading it if the file has changed on disk."""
    global _viz_mtime
    try:
        mtime = VIZ.stat().st_mtime
    except FileNotFoundError:
        return _viz_mod
    if _viz_mtime != mtime:
        importlib.reload(_viz_mod)
        _viz_mtime = mtime
    return _viz_mod

_DEFAULT_GED = Path(__file__).parent / "../smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged"
_ged_env = os.environ.get("GED_FILE", "")
if _ged_env:
    GED = Path(_ged_env)
elif _DEFAULT_GED.exists():
    GED = _DEFAULT_GED.resolve()
else:
    sys.exit("Error: set the GED_FILE environment variable to the path of your .ged file")
VIZ = Path(__file__).parent / "viz_ancestors.py"
OUT = Path(os.environ.get("VIZ_OUT", "/tmp/viz.html"))
PORT = 8080

_TAG_RE = re.compile(r'^(\d+) (\w+)(?: (.+))?$')

# ---------------------------------------------------------------------------
# HTML regeneration
# ---------------------------------------------------------------------------

def regenerate(person=None):
    if person is None:
        person = sys.argv[1] if len(sys.argv) > 1 else "@I380071267816@"
    args = ["python3", str(VIZ), str(GED), "--person", person, "-o", str(OUT)]
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"[rebuilt] {OUT} (person={person})")
    else:
        print(f"[error] {result.stderr.strip()}")


# ---------------------------------------------------------------------------
# File watcher
# ---------------------------------------------------------------------------

def watch():
    last_viz_mtime = None
    last_ged_mtime = None
    while True:
        try:
            viz_mtime = VIZ.stat().st_mtime
            if last_viz_mtime is None:
                last_viz_mtime = viz_mtime
            elif viz_mtime != last_viz_mtime:
                last_viz_mtime = viz_mtime
                regenerate()
        except FileNotFoundError:
            pass
        try:
            ged_mtime = GED.stat().st_mtime
            if last_ged_mtime is None:
                last_ged_mtime = ged_mtime
            elif ged_mtime != last_ged_mtime:
                last_ged_mtime = ged_mtime
                regenerate()
        except FileNotFoundError:
            pass
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Commit: apply pending deletions to disk with validation
# ---------------------------------------------------------------------------

def _find_indi_block(lines: list[str], xref: str) -> tuple[int | None, int | None, str | None]:
    """Return (indi_start, indi_end, err) for the individual's GEDCOM block."""
    indi_start = next(
        (i for i, l in enumerate(lines) if l.strip() == f'0 {xref} INDI'), None
    )
    if indi_start is None:
        return None, None, f'Individual {xref} not found'
    indi_end = next(
        (i for i in range(indi_start + 1, len(lines)) if lines[i].startswith('0 ')),
        len(lines),
    )
    return indi_start, indi_end, None


def _apply_deletion(lines: list[str], d: dict) -> tuple[list[str], str | None]:
    """Remove one fact from lines. Returns (new_lines, error_or_None)."""
    xref = d['xref']
    tag = d['tag']
    date = d.get('date') or None
    place = d.get('place') or None
    fact_type = d.get('type') or None
    inline_val = d.get('inline_val') or None

    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return lines, err

    event_start = event_end = None
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if not m:
            continue
        lvl, t, v = int(m.group(1)), m.group(2), (m.group(3) or '').strip()
        if lvl != 1 or t != tag:
            continue
        if inline_val is not None and v != inline_val:
            continue

        j = i + 1
        sub: dict[str, str] = {}
        while j < indi_end:
            sm = _TAG_RE.match(lines[j])
            if not sm or int(sm.group(1)) <= 1:
                break
            sl, st, sv = int(sm.group(1)), sm.group(2), (sm.group(3) or '').strip()
            if sl == 2 and st not in sub:
                sub[st] = sv
            j += 1

        def _eq(actual, expected):
            return expected is None or actual == expected

        if _eq(sub.get('DATE'), date) and _eq(sub.get('PLAC'), place) and _eq(sub.get('TYPE'), fact_type):
            event_start, event_end = i, j
            break

    if event_start is None:
        return lines, f'Fact {tag} not found in {xref} (may have already been deleted)'

    return lines[:event_start] + lines[event_end:], None


# Tags for which TYPE alternate is meaningful only when multiple events exist
_SOLE_EVENT_TYPE_TAGS = frozenset({'BIRT', 'DEAT'})


def _strip_sole_event_type_alternate(lines: list[str], xref: str, tag: str) -> list[str]:
    """
    After a deletion, if exactly one event of `tag` remains for `xref` and
    it carries a '2 TYPE alternate' sub-line, remove that sub-line.

    Only applies to BIRT and DEAT — the tags where TYPE alternate is only
    meaningful when multiple events of the same type exist.
    """
    if tag not in _SOLE_EVENT_TYPE_TAGS:
        return lines

    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return lines

    # Collect all event blocks of this tag
    events: list[tuple[int, int]] = []  # (start, end) — end is exclusive
    i = indi_start + 1
    while i < indi_end:
        m = _TAG_RE.match(lines[i])
        if m and int(m.group(1)) == 1 and m.group(2) == tag:
            start = i
            j = i + 1
            while j < indi_end:
                sm = _TAG_RE.match(lines[j])
                if sm and int(sm.group(1)) <= 1:
                    break
                j += 1
            events.append((start, j))
            i = j
        else:
            i += 1

    if len(events) != 1:
        return lines  # zero or multiple events — nothing to do

    ev_start, ev_end = events[0]
    # Find and remove any '2 TYPE alternate' within this event block
    type_lineno = next(
        (k for k in range(ev_start + 1, ev_end)
         if re.match(r'^2 TYPE\s+alternate\s*$', lines[k], re.IGNORECASE)),
        None,
    )
    if type_lineno is None:
        return lines

    return lines[:type_lineno] + lines[type_lineno + 1:]


def _find_note_block(lines: list[str], xref: str, note_idx: int) -> tuple[int | None, int | None, str | None]:
    """Return (start, end, err) — line range [start, end) for note at note_idx in xref."""
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return None, None, err
    count = 0
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if not m:
            continue
        lvl, tag = int(m.group(1)), m.group(2)
        if lvl == 1 and tag == 'NOTE':
            if count == note_idx:
                j = i + 1
                while j < indi_end:
                    sm = _TAG_RE.match(lines[j])
                    if sm and int(sm.group(1)) == 2 and sm.group(2) in ('CONT', 'CONC'):
                        j += 1
                    else:
                        break
                return i, j, None
            count += 1
    return None, None, f'Note index {note_idx} not found in {xref}'


_NOTE_LINE_MAX = 248  # 255-char GEDCOM line limit minus 7 chars for "2 NOTE " prefix


def _chunk_note_line(text: str, first_tag: str, conc_tag: str) -> list[str]:
    """Split one logical note line into physical GEDCOM lines using CONC for long lines.

    The spec warns that CONC splits must not occur at a trailing space (parsers
    often strip them), so we walk back from the limit to find a non-space cut.
    """
    out = []
    tag = first_tag
    while len(text) > _NOTE_LINE_MAX:
        cut = _NOTE_LINE_MAX
        while cut > 0 and text[cut - 1] == ' ':
            cut -= 1
        if cut == 0:
            cut = _NOTE_LINE_MAX  # no non-space found; split anyway
        out.append(f'{tag} {text[:cut]}')
        text = text[cut:]
        tag = conc_tag
    out.append(f'{tag} {text}')
    return out


def _encode_note_lines(text: str) -> list[str]:
    """Encode text into GEDCOM '1 NOTE / 2 CONT / 2 CONC' lines.

    Newlines in text become CONT lines (preserve line breaks).
    Lines longer than 248 chars are split with CONC (no line break).
    """
    out = []
    for i, line in enumerate(text.split('\n')):
        first_tag = '1 NOTE' if i == 0 else '2 CONT'
        out.extend(_chunk_note_line(line, first_tag, '2 CONC'))
    return out


def _encode_event_note_lines(text: str) -> list[str]:
    """Encode text into GEDCOM '2 NOTE / 3 CONT / 3 CONC' lines (event sub-notes).

    Newlines in text become CONT lines (preserve line breaks).
    Lines longer than 248 chars are split with CONC (no line break).
    """
    out = []
    for i, line in enumerate(text.split('\n')):
        first_tag = '2 NOTE' if i == 0 else '3 CONT'
        out.extend(_chunk_note_line(line, first_tag, '3 CONC'))
    return out


def _write_gedcom_atomic(lines: list[str]) -> None:
    """Backup original and write new lines to GED atomically."""
    backup = GED.with_suffix('.ged.bak')
    GED.rename(backup)
    GED.write_text('\n'.join(lines) + '\n', encoding='utf-8')


# ---------------------------------------------------------------------------
# Name editing helper
# ---------------------------------------------------------------------------

def _edit_name(lines: list[str], xref: str, given_name: str, surname: str) -> tuple[list[str], str | None]:
    """Rewrite the 1 NAME (and 2 GIVN/2 SURN sub-tags) for an individual."""
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return lines, err

    full_name = f'{given_name} /{surname}/'.strip()

    # Find existing 1 NAME line
    name_start = None
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if m and int(m.group(1)) == 1 and m.group(2) == 'NAME':
            name_start = i
            break

    if name_start is None:
        # Insert a fresh NAME block just after the INDI header line
        new_block = [f'1 NAME {full_name}']
        if given_name:
            new_block.append(f'2 GIVN {given_name}')
        if surname:
            new_block.append(f'2 SURN {surname}')
        return lines[:indi_start + 1] + new_block + lines[indi_start + 1:], None

    # Find end of existing NAME block (stops at next level ≤ 1)
    name_end = name_start + 1
    while name_end < indi_end:
        sm = _TAG_RE.match(lines[name_end])
        if sm and int(sm.group(1)) <= 1:
            break
        name_end += 1

    # Keep any sub-tags that are not GIVN/SURN (e.g. NICK, NPFX, etc.)
    kept = [
        l for l in lines[name_start + 1: name_end]
        if not (_TAG_RE.match(l) and _TAG_RE.match(l).group(2) in ('GIVN', 'SURN'))
    ]
    new_block = [f'1 NAME {full_name}'] + kept
    if given_name:
        new_block.append(f'2 GIVN {given_name}')
    if surname:
        new_block.append(f'2 SURN {surname}')
    return lines[:name_start] + new_block + lines[name_end:], None


# ---------------------------------------------------------------------------
# Secondary NAME record helpers (alias add / edit / delete)
# ---------------------------------------------------------------------------

def _find_secondary_name_block(
    lines: list[str], xref: str, n: int
) -> tuple[int | None, int | None, str | None]:
    """Return (start, end, err) for the nth (0-based) secondary NAME record in xref's INDI block."""
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return None, None, err
    primary_seen = False
    count = 0
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if not m or int(m.group(1)) != 1 or m.group(2) != 'NAME':
            continue
        if not primary_seen:
            primary_seen = True
            continue  # skip primary name
        if count == n:
            j = i + 1
            while j < indi_end:
                sm = _TAG_RE.match(lines[j])
                if sm and int(sm.group(1)) <= 1:
                    break
                j += 1
            return i, j, None
        count += 1
    return None, None, f'Secondary name [{n}] not found in {xref}'


def _add_secondary_name(
    lines: list[str], xref: str, name: str, name_type: str
) -> tuple[list[str], str | None]:
    """Append a new secondary NAME record just before indi_end."""
    _, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return lines, err
    full_name = name.strip()
    # Wrap surname in slashes if not already wrapped and looks like "Given Surname"
    if full_name and '/' not in full_name:
        parts = full_name.rsplit(' ', 1)
        if len(parts) == 2:
            full_name = f'{parts[0]} /{parts[1]}/'
    new_block = [f'1 NAME {full_name}']
    if name_type:
        new_block.append(f'2 TYPE {name_type.strip()}')
    return lines[:indi_end] + new_block + lines[indi_end:], None


def _edit_secondary_name(
    lines: list[str], xref: str, n: int, name: str, name_type: str
) -> tuple[list[str], str | None]:
    """Replace the nth secondary NAME block with an updated name and type."""
    start, end, err = _find_secondary_name_block(lines, xref, n)
    if err:
        return lines, err
    full_name = name.strip()
    if full_name and '/' not in full_name:
        parts = full_name.rsplit(' ', 1)
        if len(parts) == 2:
            full_name = f'{parts[0]} /{parts[1]}/'
    new_block = [f'1 NAME {full_name}']
    if name_type:
        new_block.append(f'2 TYPE {name_type.strip()}')
    return lines[:start] + new_block + lines[end:], None


# ---------------------------------------------------------------------------
# FAM block helpers (for marriage editing)
# ---------------------------------------------------------------------------

def _get_sex(lines: list[str], xref: str) -> str | None:
    """Return 'M', 'F', or None from the '1 SEX' tag in xref's INDI block."""
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return None
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if m and int(m.group(1)) == 1 and m.group(2) == 'SEX':
            return (m.group(3) or '').strip() or None
    return None


def _find_existing_fam(lines: list[str], xref1: str, xref2: str) -> str | None:
    """Return the FAM xref where HUSB/WIFE are xref1 & xref2 (either order), or None."""
    import re as _re
    _FAM_HDR_RE = _re.compile(r'^0 (@F\d+@) FAM$')
    fam_xref = None
    husb = wife = None
    in_fam = False
    for line in lines:
        m = _FAM_HDR_RE.match(line.strip())
        if m:
            # Check previous FAM before moving on
            if in_fam and husb and wife:
                pair = {husb, wife}
                if pair == {xref1, xref2}:
                    return fam_xref
            fam_xref = m.group(1)
            husb = wife = None
            in_fam = True
            continue
        if line.startswith('0 ') and not _FAM_HDR_RE.match(line.strip()):
            # End of any FAM block
            if in_fam and husb and wife:
                pair = {husb, wife}
                if pair == {xref1, xref2}:
                    return fam_xref
            in_fam = False
            fam_xref = husb = wife = None
            continue
        if in_fam:
            tm = _TAG_RE.match(line)
            if tm and int(tm.group(1)) == 1:
                tag = tm.group(2)
                val = (tm.group(3) or '').strip()
                if tag == 'HUSB':
                    husb = val
                elif tag == 'WIFE':
                    wife = val
    # Check last FAM in file
    if in_fam and husb and wife:
        if {husb, wife} == {xref1, xref2}:
            return fam_xref
    return None


def _next_fam_xref(lines: list[str]) -> str:
    """Scan all lines for @FXXX@ references and return @F(max+1)@."""
    import re as _re
    pattern = _re.compile(r'@F(\d+)@')
    max_n = 0
    for line in lines:
        for m in pattern.finditer(line):
            max_n = max(max_n, int(m.group(1)))
    return f'@F{max_n + 1}@'


def _add_fams_to_indi(lines: list[str], indi_xref: str, fam_xref: str) -> list[str]:
    """Insert '1 FAMS fam_xref' at the end of indi_xref's INDI block (idempotent)."""
    indi_start, indi_end, err = _find_indi_block(lines, indi_xref)
    if err:
        return lines
    target = f'1 FAMS {fam_xref}'
    for i in range(indi_start + 1, indi_end):
        if lines[i].strip() == target:
            return lines   # already present
    return lines[:indi_end] + [target] + lines[indi_end:]


def _insert_fam_event(lines: list[str], fam_xref: str, event_tag: str, fields: dict) -> list[str]:
    """Append a new MARR/DIV event block just before the end of the FAM record."""
    _, fam_end, err = _find_fam_block(lines, fam_xref)
    if err:
        return lines
    new_block = [f'1 {event_tag}']
    for subtag in ('DATE', 'PLAC', 'ADDR', 'NOTE'):
        val = (fields.get(subtag) or '').strip()
        if val:
            new_block.append(f'2 {subtag} {val}')
    return lines[:fam_end] + new_block + lines[fam_end:]


def _create_fam_with_event(
    lines: list[str], husb_xref: str, wife_xref: str,
    fam_xref: str, event_tag: str, fields: dict,
) -> list[str]:
    """Append a brand-new FAM record (with HUSB, WIFE, and one event) before TRLR."""
    trlr_idx = next(
        (i for i, l in enumerate(lines) if l.strip() == '0 TRLR'), len(lines)
    )
    # Find insertion point: after the last FAM block (before TRLR)
    insert_at = trlr_idx
    fam_block = [f'0 {fam_xref} FAM', f'1 HUSB {husb_xref}', f'1 WIFE {wife_xref}']
    fam_block.append(f'1 {event_tag}')
    for subtag in ('DATE', 'PLAC', 'ADDR', 'NOTE'):
        val = (fields.get(subtag) or '').strip()
        if val:
            fam_block.append(f'2 {subtag} {val}')
    return lines[:insert_at] + fam_block + lines[insert_at:]


def _find_fam_block(lines: list[str], fam_xref: str) -> tuple[int | None, int | None, str | None]:
    """Return (fam_start, fam_end, err) for a FAM record."""
    fam_start = next(
        (i for i, l in enumerate(lines) if l.strip() == f'0 {fam_xref} FAM'), None
    )
    if fam_start is None:
        return None, None, f'Family {fam_xref} not found'
    fam_end = next(
        (i for i in range(fam_start + 1, len(lines)) if lines[i].startswith('0 ')),
        len(lines),
    )
    return fam_start, fam_end, None


def _find_fam_event_block(
    lines: list[str], fam_xref: str, event_tag: str, occurrence: int = 0
) -> tuple[int | None, int | None, str | None]:
    """Return (start, end, err) for the Nth (0-based) occurrence of event_tag in the FAM block."""
    fam_start, fam_end, err = _find_fam_block(lines, fam_xref)
    if err:
        return None, None, err
    count = 0
    for i in range(fam_start + 1, fam_end):
        m = _TAG_RE.match(lines[i])
        if not m:
            continue
        if int(m.group(1)) == 1 and m.group(2) == event_tag:
            if count == occurrence:
                j = i + 1
                while j < fam_end:
                    sm = _TAG_RE.match(lines[j])
                    if sm and int(sm.group(1)) <= 1:
                        break
                    j += 1
                return i, j, None
            count += 1
    return None, None, f'Event {event_tag}[{occurrence}] not found in family {fam_xref}'


# ---------------------------------------------------------------------------
# Event editing / creation helpers
# ---------------------------------------------------------------------------

_MANAGED_SUBTAGS = frozenset({'DATE', 'PLAC', 'TYPE', 'NOTE', 'CAUS', 'ADDR'})
_INLINE_TYPE_TAGS = frozenset({'OCCU', 'TITL', 'NATI', 'RELI', 'EDUC', 'DSCR', 'NCHI'})


def _find_event_block(
    lines: list[str], xref: str, event_tag: str, occurrence_n: int
) -> tuple[int | None, int | None, str | None]:
    """Return (start, end, err) for the Nth (0-based) occurrence of event_tag in xref's INDI block."""
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return None, None, err
    count = 0
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if not m:
            continue
        if int(m.group(1)) == 1 and m.group(2) == event_tag:
            if count == occurrence_n:
                j = i + 1
                while j < indi_end:
                    sm = _TAG_RE.match(lines[j])
                    if sm and int(sm.group(1)) <= 1:
                        break
                    j += 1
                return i, j, None
            count += 1
    return None, None, f'Event {event_tag}[{occurrence_n}] not found in {xref}'


def _edit_event_fields(
    lines: list[str], block_start: int, block_end: int, updates: dict
) -> list[str]:
    """
    Apply field updates to an event block.
    updates keys: DATE, PLAC, TYPE, NOTE, CAUS, inline_val.
    Empty/None value = remove that sub-field.
    inline_val rewrites the level-1 header line.
    """
    header = lines[block_start]
    if 'inline_val' in updates:
        m = _TAG_RE.match(header)
        new_iv = (updates['inline_val'] or '').strip()
        header = f"{m.group(1)} {m.group(2)}" + (f" {new_iv}" if new_iv else "")

    new_block = [header]
    handled: set[str] = set()
    skip_cont = False  # True after replacing/removing a NOTE — drop its CONT/CONC lines
    for line in lines[block_start + 1: block_end]:
        m = _TAG_RE.match(line)
        if not m:
            new_block.append(line)
            skip_cont = False
            continue
        lvl, tag = int(m.group(1)), m.group(2)
        # Drop stale continuation lines that belonged to a NOTE we just replaced/deleted
        # (old event notes may have 3 CONT/CONC; individual notes have 2 CONT/CONC)
        if skip_cont and lvl in (2, 3) and tag in ('CONT', 'CONC'):
            continue
        skip_cont = False
        if lvl == 2 and tag in _MANAGED_SUBTAGS and tag in updates:
            handled.add(tag)
            new_val = (updates[tag] or '').strip()
            if tag == 'NOTE':
                if new_val:
                    new_block.extend(_encode_event_note_lines(new_val))
                # else: omit (delete the sub-field)
                skip_cont = True  # drop any following CONT/CONC for the old NOTE
            else:
                if new_val:
                    new_block.append(f'2 {tag} {new_val}')
        else:
            new_block.append(line)

    # Append new sub-tags not already in the block
    for tag in ('DATE', 'PLAC', 'ADDR', 'TYPE', 'NOTE', 'CAUS'):
        if tag in updates and tag not in handled:
            new_val = (updates[tag] or '').strip()
            if new_val:
                if tag == 'NOTE':
                    new_block.extend(_encode_event_note_lines(new_val))
                else:
                    new_block.append(f'2 {tag} {new_val}')

    return lines[:block_start] + new_block + lines[block_end:]


def _insert_new_event(
    lines: list[str], xref: str, event_tag: str, fields: dict
) -> tuple[list[str], str | None]:
    """Insert a new event block just before the end of xref's INDI record."""
    _, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return lines, err
    inline_val = (fields.get('inline_val') or '').strip()
    if event_tag in _INLINE_TYPE_TAGS and inline_val:
        header = f'1 {event_tag} {inline_val}'
    else:
        header = f'1 {event_tag}'
    new_block = [header]
    for subtag in ('DATE', 'PLAC', 'ADDR', 'TYPE', 'NOTE', 'CAUS'):
        val = (fields.get(subtag) or '').strip()
        if val:
            if subtag == 'NOTE':
                new_block.extend(_encode_event_note_lines(val))
            else:
                new_block.append(f'2 {subtag} {val}')
    return lines[:indi_end] + new_block + lines[indi_end:], None


# ---------------------------------------------------------------------------
# Source record helpers
# ---------------------------------------------------------------------------

def _next_sour_xref(lines: list[str]) -> str:
    """Scan all lines for @Sn@ references and return @S(max+1)@."""
    pattern = re.compile(r'@S(\d+)@')
    max_n = 0
    for line in lines:
        for m in pattern.finditer(line):
            max_n = max(max_n, int(m.group(1)))
    return f'@S{max_n + 1}@'


def _find_sour_block(lines: list[str], sour_xref: str) -> tuple[int | None, int | None, str | None]:
    """Return (sour_start, sour_end, err) for a SOUR record."""
    sour_start = next(
        (i for i, l in enumerate(lines) if l.strip() == f'0 {sour_xref} SOUR'), None
    )
    if sour_start is None:
        return None, None, f'Source {sour_xref} not found'
    sour_end = next(
        (i for i in range(sour_start + 1, len(lines)) if lines[i].startswith('0 ')),
        len(lines),
    )
    return sour_start, sour_end, None


_SOUR_OPTIONAL_TAGS = ('AUTH', 'PUBL', 'REPO', 'NOTE')


def _build_sour_block(xref: str, titl: str, auth: str, publ: str, repo: str, note: str) -> list[str]:
    """Build GEDCOM lines for a SOUR record."""
    block = [f'0 {xref} SOUR', f'1 TITL {titl}']
    for tag, val in (('AUTH', auth), ('PUBL', publ), ('REPO', repo), ('NOTE', note)):
        if val and val.strip():
            block.append(f'1 {tag} {val.strip()}')
    return block


# ---------------------------------------------------------------------------
# Citation helpers
# ---------------------------------------------------------------------------

def _next_indi_xref(lines: list[str]) -> str:
    """Scan all lines for @In@ references and return @I(max+1)@."""
    pattern = re.compile(r'@I(\d+)@')
    max_n = 0
    for line in lines:
        for m in pattern.finditer(line):
            max_n = max(max_n, int(m.group(1)))
    return f'@I{max_n + 1}@'


def _find_fact_for_citation(
    lines: list[str], xref: str, fact_key: str | None
) -> tuple[int | None, str | None]:
    """
    Given a fact_key like 'BIRT:0', return the line index of the end of that fact
    block — i.e., where to insert a citation.  Returns (insert_pos, err).
    If fact_key is None or 'SOUR:null'/empty, returns (indi_end, None) for
    a person-level citation (to be inserted as 1 SOUR).
    """
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return None, err

    if not fact_key or fact_key.startswith('SOUR:') or fact_key == 'null':
        return indi_end, None

    parts = fact_key.split(':')
    if len(parts) != 2:
        return None, f'Invalid fact_key format: {fact_key!r}'
    tag = parts[0]
    try:
        occurrence = int(parts[1])
    except ValueError:
        occurrence = 0

    start, end, err = _find_event_block(lines, xref, tag, occurrence)
    if err:
        return None, err
    return end, None


def _find_citation_block(
    lines: list[str], xref: str, citation_key: str
) -> tuple[int | None, int | None, int | None, str | None]:
    """
    Parse citation_key and locate the citation block.

    citation_key formats:
      'BIRT:0:0'  → fact tag BIRT, fact occurrence 0, citation occurrence 0 within that fact
                    → citation is at level 2 (2 SOUR ...)
      'SOUR:0'    → person-level citation 0
                    → citation is at level 1 (1 SOUR ...)

    Returns (block_start, block_end, citation_level, err).
    block_start: index of the '2 SOUR ...' or '1 SOUR ...' line
    block_end: exclusive end of that citation block
    citation_level: 1 or 2
    """
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return None, None, None, err

    parts = citation_key.split(':')

    # Person-level: 'SOUR:N'
    if parts[0] == 'SOUR' and len(parts) == 2:
        try:
            cite_n = int(parts[1])
        except ValueError:
            return None, None, None, f'Invalid citation_key: {citation_key!r}'
        count = 0
        for i in range(indi_start + 1, indi_end):
            m = _TAG_RE.match(lines[i])
            if not m:
                continue
            if int(m.group(1)) == 1 and m.group(2) == 'SOUR':
                if count == cite_n:
                    j = i + 1
                    while j < indi_end:
                        sm = _TAG_RE.match(lines[j])
                        if sm and int(sm.group(1)) <= 1:
                            break
                        j += 1
                    return i, j, 1, None
                count += 1
        return None, None, None, f'Person-level citation {cite_n} not found in {xref}'

    # Fact-level: 'TAG:fact_n:cite_n'
    if len(parts) != 3:
        return None, None, None, f'Invalid citation_key format: {citation_key!r}'
    fact_tag, fact_n_s, cite_n_s = parts
    try:
        fact_n = int(fact_n_s)
        cite_n = int(cite_n_s)
    except ValueError:
        return None, None, None, f'Invalid citation_key: {citation_key!r}'

    fact_start, fact_end, err = _find_event_block(lines, xref, fact_tag, fact_n)
    if err:
        return None, None, None, err

    count = 0
    for i in range(fact_start + 1, fact_end):
        m = _TAG_RE.match(lines[i])
        if not m:
            continue
        if int(m.group(1)) == 2 and m.group(2) == 'SOUR':
            if count == cite_n:
                j = i + 1
                while j < fact_end:
                    sm = _TAG_RE.match(lines[j])
                    if sm and int(sm.group(1)) <= 2:
                        break
                    j += 1
                return i, j, 2, None
            count += 1
    return None, None, None, f'Citation {cite_n} not found in {fact_tag}[{fact_n}] of {xref}'


def _build_citation_lines(sour_xref: str, page: str, text: str, note: str, base_level: int) -> list[str]:
    """
    Build the citation block lines at base_level.
    base_level=1 → person-level (1 SOUR, 2 PAGE, 2 DATA, 3 TEXT, 2 NOTE)
    base_level=2 → fact-level   (2 SOUR, 3 PAGE, 3 DATA, 4 TEXT, 3 NOTE)
    """
    b = base_level
    lines_out = [f'{b} SOUR {sour_xref}']
    if page and page.strip():
        lines_out.append(f'{b+1} PAGE {page.strip()}')
    if text and text.strip():
        lines_out.append(f'{b+1} DATA')
        lines_out.append(f'{b+2} TEXT {text.strip()}')
    if note and note.strip():
        lines_out.append(f'{b+1} NOTE {note.strip()}')
    return lines_out


def _update_citation_block(
    lines: list[str], block_start: int, block_end: int,
    citation_level: int, page: str, text: str, note: str
) -> list[str]:
    """
    Replace citation block (block_start..block_end) with updated PAGE/TEXT/NOTE values.
    Preserves the SOUR xref header line.
    """
    header = lines[block_start]  # '2 SOUR @S1@' or '1 SOUR @S1@'
    b = citation_level
    sour_xref_val = (header.split(' ', 2) + [''])[2].strip()
    new_block = _build_citation_lines(sour_xref_val, page, text, note, b)
    return lines[:block_start] + new_block + lines[block_end:]


# ---------------------------------------------------------------------------
# Person creation helpers
# ---------------------------------------------------------------------------

def _get_famc_for_indi(lines: list[str], xref: str) -> str | None:
    """Return the first FAMC xref for the given individual, or None."""
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return None
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if m and int(m.group(1)) == 1 and m.group(2) == 'FAMC':
            return (m.group(3) or '').strip() or None
    return None


def _get_fams_for_indi(lines: list[str], xref: str) -> list[str]:
    """Return all FAMS xrefs for the given individual."""
    indi_start, indi_end, err = _find_indi_block(lines, xref)
    if err:
        return []
    result = []
    for i in range(indi_start + 1, indi_end):
        m = _TAG_RE.match(lines[i])
        if m and int(m.group(1)) == 1 and m.group(2) == 'FAMS':
            val = (m.group(3) or '').strip()
            if val:
                result.append(val)
    return result


def _add_chil_to_fam(lines: list[str], fam_xref: str, chil_xref: str) -> list[str]:
    """Append '1 CHIL chil_xref' just before end of fam_xref's FAM block."""
    _, fam_end, err = _find_fam_block(lines, fam_xref)
    if err:
        return lines
    return lines[:fam_end] + [f'1 CHIL {chil_xref}'] + lines[fam_end:]


def _create_bare_fam(lines: list[str], fam_xref: str, husb_xref: str | None, wife_xref: str | None) -> list[str]:
    """Insert a new FAM record (no events) before TRLR."""
    trlr_idx = next(
        (i for i, l in enumerate(lines) if l.strip() == '0 TRLR'), len(lines)
    )
    fam_block = [f'0 {fam_xref} FAM']
    if husb_xref:
        fam_block.append(f'1 HUSB {husb_xref}')
    if wife_xref:
        fam_block.append(f'1 WIFE {wife_xref}')
    return lines[:trlr_idx] + fam_block + lines[trlr_idx:]


def _add_famc_to_indi(lines: list[str], indi_xref: str, fam_xref: str) -> list[str]:
    """Insert '1 FAMC fam_xref' at the end of indi_xref's INDI block (idempotent)."""
    indi_start, indi_end, err = _find_indi_block(lines, indi_xref)
    if err:
        return lines
    target = f'1 FAMC {fam_xref}'
    for i in range(indi_start + 1, indi_end):
        if lines[i].strip() == target:
            return lines
    return lines[:indi_end] + [target] + lines[indi_end:]


# ---------------------------------------------------------------------------
# Input validation / normalization
# ---------------------------------------------------------------------------

def _normalize_event_date(value: str) -> tuple[str, str | None]:
    """
    Normalize a user-supplied date string to GEDCOM 5.5.1 format.
    Returns (normalized_value, error_or_None).
    Empty/None input is returned as-is — deleting a date is valid.
    """
    if not value or not value.strip():
        return value, None
    normalized = normalize_date(value.strip())
    if not GEDCOM_DATE_RE.match(normalized):
        return value, (
            f'Invalid date: "{value}". Use GEDCOM format, e.g. '
            f'"5 JAN 1900", "ABT 1850", "BET 1900 AND 1910".'
        )
    return normalized, None


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/viz.html'):
            params = parse_qs(parsed.query)
            if 'person' in params:
                regenerate(unquote(params['person'][0]))
            else:
                regenerate()
            self.path = OUT.name
            self.directory = str(OUT.parent)
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        if parsed.path.startswith('/js/') and parsed.path.endswith('.js'):
            js_file = Path(__file__).parent / parsed.path.lstrip('/')
            if js_file.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'application/javascript')
                self.end_headers()
                self.wfile.write(js_file.read_bytes())
                return
            self.send_error(404)
            return
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if parsed.path == '/api/delete_fact':
            xref = body['xref']
            lines = GED.read_text(encoding='utf-8').splitlines()
            new_lines, err = _apply_deletion(lines, body)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                new_lines = _strip_sole_event_type_alternate(new_lines, xref, body['tag'])
                _write_gedcom_atomic(new_lines)
                print(f"[fact-delete] {xref} {body['tag']} deleted")
                regenerate(body.get('current_person'))
                viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/delete_note':
            xref     = body['xref']
            note_idx = int(body['note_idx'])
            lines    = GED.read_text(encoding='utf-8').splitlines()
            start, end, err = _find_note_block(lines, xref, note_idx)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                new_lines = lines[:start] + lines[end:]
                _write_gedcom_atomic(new_lines)
                print(f"[note-delete] {xref} note[{note_idx}] deleted")
                regenerate(body.get('current_person'))
                viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/add_note':
            xref     = body['xref']
            new_text = body.get('new_text', '').strip()
            if not new_text:
                resp = json.dumps({'ok': False, 'error': 'Note text is empty'}).encode()
            else:
                lines = GED.read_text(encoding='utf-8').splitlines()
                _, indi_end, err = _find_indi_block(lines, xref)
                if err:
                    resp = json.dumps({'ok': False, 'error': err}).encode()
                else:
                    new_lines = lines[:indi_end] + _encode_note_lines(new_text) + lines[indi_end:]
                    _write_gedcom_atomic(new_lines)
                    print(f"[note-add] {xref} note added")
                    regenerate(body.get('current_person'))
                    viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                    indis, fams, sources = parse_gedcom(str(GED))
                    updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                    resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/edit_note':
            xref     = body['xref']
            note_idx = int(body['note_idx'])
            new_text = body.get('new_text', '')
            lines    = GED.read_text(encoding='utf-8').splitlines()
            start, end, err = _find_note_block(lines, xref, note_idx)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                new_lines = lines[:start] + _encode_note_lines(new_text) + lines[end:]
                _write_gedcom_atomic(new_lines)
                print(f"[note-edit] {xref} note[{note_idx}] updated")
                regenerate(body.get('current_person'))
                viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/edit_event':
            xref      = body['xref']
            tag       = body['tag']
            fam_xref  = body.get('fam_xref') or None
            updates   = body.get('updates', {})
            if 'DATE' in updates:
                updates['DATE'], _date_err = _normalize_event_date(updates['DATE'])
            else:
                _date_err = None
            if _date_err:
                resp = json.dumps({'ok': False, 'error': _date_err}).encode()
            else:
                lines = GED.read_text(encoding='utf-8').splitlines()
                if fam_xref:
                    # Marriage events live in FAM records; marr_occurrence selects
                    # which 1 MARR block to edit when a FAM has multiple ceremonies.
                    marr_occ = int(body.get('marr_occurrence') or 0)
                    start, end, err = _find_fam_event_block(lines, fam_xref, tag, marr_occ)
                else:
                    event_idx = int(body['event_idx'])
                    start, end, err = _find_event_block(lines, xref, tag, event_idx)
                if err and fam_xref:
                    # FAM has no event tag yet (placeholder from viz) — insert it
                    new_lines = _insert_fam_event(lines, fam_xref, tag, updates)
                    err = None
                if err:
                    resp = json.dumps({'ok': False, 'error': err}).encode()
                else:
                    new_lines = _edit_event_fields(lines, start, end, updates) if start is not None else new_lines
                    _write_gedcom_atomic(new_lines)
                    print(f"[event-edit] {fam_xref or xref} {tag} updated")
                    regenerate(body.get('current_person'))
                    viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                    indis, fams, sources = parse_gedcom(str(GED))
                    # For FAM edits return data for both spouses so both panels refresh
                    if fam_xref and fam_xref in fams:
                        fam = fams[fam_xref]
                        xrefs_to_refresh = {x for x in (fam.get('husb'), fam.get('wife'), xref) if x}
                    else:
                        xrefs_to_refresh = {xref}
                    updated = build_people_json(xrefs_to_refresh, indis, fams=fams, sources=sources)
                    resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/add_secondary_name':
            xref      = body['xref']
            name      = (body.get('name') or '').strip()
            name_type = (body.get('name_type') or 'AKA').strip()
            lines     = GED.read_text(encoding='utf-8').splitlines()
            new_lines, err = _add_secondary_name(lines, xref, name, name_type)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                _write_gedcom_atomic(new_lines)
                print(f"[alias-add] {xref} NAME {name!r} TYPE {name_type}")
                regenerate(body.get('current_person'))
                viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/edit_secondary_name':
            xref             = body['xref']
            name_occurrence  = int(body['name_occurrence'])
            name             = (body.get('name') or '').strip()
            name_type        = (body.get('name_type') or 'AKA').strip()
            lines            = GED.read_text(encoding='utf-8').splitlines()
            new_lines, err = _edit_secondary_name(lines, xref, name_occurrence, name, name_type)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                _write_gedcom_atomic(new_lines)
                print(f"[alias-edit] {xref} NAME[{name_occurrence}] → {name!r}")
                regenerate(body.get('current_person'))
                viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/delete_secondary_name':
            xref            = body['xref']
            name_occurrence = int(body['name_occurrence'])
            lines           = GED.read_text(encoding='utf-8').splitlines()
            start, end, err = _find_secondary_name_block(lines, xref, name_occurrence)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                new_lines = lines[:start] + lines[end:]
                _write_gedcom_atomic(new_lines)
                print(f"[alias-delete] {xref} NAME[{name_occurrence}]")
                regenerate(body.get('current_person'))
                viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/edit_name':
            xref       = body['xref']
            given_name = (body.get('given_name') or '').strip()
            surname    = (body.get('surname') or '').strip()
            lines      = GED.read_text(encoding='utf-8').splitlines()
            new_lines, err = _edit_name(lines, xref, given_name, surname)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                _write_gedcom_atomic(new_lines)
                print(f"[name-edit] {xref} → {given_name} /{surname}/")
                regenerate(body.get('current_person'))
                viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/add_event':
            xref   = body['xref']
            tag    = body['tag']
            fields = body.get('fields', {})
            if 'DATE' in fields:
                fields['DATE'], _date_err = _normalize_event_date(fields['DATE'])
            else:
                _date_err = None
            if _date_err:
                resp = json.dumps({'ok': False, 'error': _date_err}).encode()
            else:
                lines  = GED.read_text(encoding='utf-8').splitlines()
                new_lines, err = _insert_new_event(lines, xref, tag, fields)
                if err:
                    resp = json.dumps({'ok': False, 'error': err}).encode()
                else:
                    _write_gedcom_atomic(new_lines)
                    print(f"[event-add] {xref} {tag} added")
                    regenerate(body.get('current_person'))
                    viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                    indis, fams, sources = parse_gedcom(str(GED))
                    updated = build_people_json({xref}, indis, fams=fams, sources=sources)
                    resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/delete_marriage':
            xref      = body.get('xref', '')
            fam_xref  = body.get('fam_xref', '')
            marr_occ  = int(body.get('marr_occurrence') or 0)
            event_tag = body.get('tag', 'MARR')
            lines     = GED.read_text(encoding='utf-8').splitlines()
            start, end, err = _find_fam_event_block(lines, fam_xref, event_tag, marr_occ)
            if err:
                resp = json.dumps({'ok': False, 'error': err}).encode()
            else:
                new_lines = lines[:start] + lines[end:]
                _write_gedcom_atomic(new_lines)
                print(f"[marriage-delete] {fam_xref} {event_tag}[{marr_occ}] deleted")
                regenerate(body.get('current_person'))
                viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                indis, fams, sources = parse_gedcom(str(GED))
                fam = fams.get(fam_xref, {})
                xrefs_to_refresh = {x for x in (fam.get('husb'), fam.get('wife'), xref) if x}
                updated = build_people_json(xrefs_to_refresh, indis, fams=fams, sources=sources)
                resp = json.dumps({'ok': True, 'people': updated}).encode()

        elif parsed.path == '/api/add_marriage':
            xref        = body.get('xref', '')
            spouse_xref = body.get('spouse_xref', '')
            tag         = body.get('tag', 'MARR')
            fields      = body.get('fields', {})
            if not spouse_xref:
                resp = json.dumps({'ok': False, 'error': 'spouse_xref is required'}).encode()
            else:
                if 'DATE' in fields and fields['DATE']:
                    fields['DATE'], _date_err = _normalize_event_date(fields['DATE'])
                else:
                    _date_err = None
                if _date_err:
                    resp = json.dumps({'ok': False, 'error': _date_err}).encode()
                else:
                    lines    = GED.read_text(encoding='utf-8').splitlines()
                    existing = _find_existing_fam(lines, xref, spouse_xref)
                    if existing:
                        new_lines = _insert_fam_event(lines, existing, tag, fields)
                    else:
                        sex1    = _get_sex(lines, xref)
                        sex2    = _get_sex(lines, spouse_xref)
                        if sex1 == 'F' and sex2 != 'F':
                            husb_xref, wife_xref = spouse_xref, xref
                        elif sex2 == 'F' and sex1 != 'F':
                            husb_xref, wife_xref = xref, spouse_xref
                        else:
                            husb_xref, wife_xref = xref, spouse_xref
                        new_fam = _next_fam_xref(lines)
                        new_lines = _create_fam_with_event(lines, husb_xref, wife_xref, new_fam, tag, fields)
                        new_lines = _add_fams_to_indi(new_lines, xref, new_fam)
                        new_lines = _add_fams_to_indi(new_lines, spouse_xref, new_fam)
                    _write_gedcom_atomic(new_lines)
                    print(f"[marriage-add] {xref} + {spouse_xref} {tag}")
                    regenerate(body.get('current_person'))
                    viz = _viz(); parse_gedcom = viz.parse_gedcom; build_people_json = viz.build_people_json
                    indis, fams, sources = parse_gedcom(str(GED))
                    updated = build_people_json({xref, spouse_xref}, indis, fams=fams, sources=sources)
                    resp = json.dumps({'ok': True, 'people': updated}).encode()

        # ------------------------------------------------------------------ #
        # Source endpoints                                                    #
        # ------------------------------------------------------------------ #

        elif parsed.path == '/api/add_source':
            titl = (body.get('titl') or '').strip()
            if not titl:
                self.send_error(400, 'titl is required')
                return
            auth = (body.get('auth') or '').strip()
            publ = (body.get('publ') or '').strip()
            repo = (body.get('repo') or '').strip()
            note = (body.get('note') or '').strip()
            lines = GED.read_text(encoding='utf-8').splitlines()
            new_xref = _next_sour_xref(lines)
            sour_block = _build_sour_block(new_xref, titl, auth, publ, repo, note)
            trlr_idx = next(
                (i for i, l in enumerate(lines) if l.strip() == '0 TRLR'), len(lines)
            )
            new_lines = lines[:trlr_idx] + sour_block + lines[trlr_idx:]
            _write_gedcom_atomic(new_lines)
            print(f"[source-add] {new_xref} {titl!r}")
            resp = json.dumps({'xref': new_xref}).encode()

        elif parsed.path == '/api/edit_source_record':
            xref = (body.get('xref') or '').strip()
            titl = (body.get('titl') or '').strip()
            if not xref:
                self.send_error(400, 'xref is required')
                return
            lines = GED.read_text(encoding='utf-8').splitlines()
            sour_start, sour_end, err = _find_sour_block(lines, xref)
            if err:
                self.send_error(400, err)
                return
            auth = (body.get('auth') or '').strip()
            publ = (body.get('publ') or '').strip()
            repo = (body.get('repo') or '').strip()
            note = (body.get('note') or '').strip()
            new_block = [f'0 {xref} SOUR']
            if titl:
                new_block.append(f'1 TITL {titl}')
            for tag, val in (('AUTH', auth), ('PUBL', publ), ('REPO', repo), ('NOTE', note)):
                if val:
                    new_block.append(f'1 {tag} {val}')
            # Keep any unmanaged level-1 sub-tags (e.g. custom extensions),
            # but skip managed tags AND all of their subordinate (level > 1)
            # continuation lines so we don't orphan CONT/CONC lines.
            managed = {'TITL', 'AUTH', 'PUBL', 'REPO', 'NOTE'}
            skip_children = False
            for line in lines[sour_start + 1: sour_end]:
                m = _TAG_RE.match(line)
                if m:
                    lvl = int(m.group(1))
                    if lvl == 1:
                        # New level-1 tag: decide whether to include it
                        skip_children = m.group(2) in managed
                        if skip_children:
                            continue
                    elif skip_children:
                        # Child of a managed tag — drop continuation lines too
                        continue
                new_block.append(line)
            new_lines = lines[:sour_start] + new_block + lines[sour_end:]
            _write_gedcom_atomic(new_lines)
            print(f"[source-edit] {xref}")
            resp = json.dumps({'ok': True}).encode()

        # ------------------------------------------------------------------ #
        # Citation endpoints                                                  #
        # ------------------------------------------------------------------ #

        elif parsed.path == '/api/add_citation':
            xref      = (body.get('xref') or '').strip()
            sour_xref = (body.get('sour_xref') or '').strip()
            if not xref:
                self.send_error(400, 'xref is required')
                return
            if not sour_xref:
                self.send_error(400, 'sour_xref is required')
                return
            fact_key  = body.get('fact_key') or None
            page      = (body.get('page') or '').strip()
            text      = (body.get('text') or '').strip()
            note      = (body.get('note') or '').strip()
            lines     = GED.read_text(encoding='utf-8').splitlines()

            # Determine insertion point and citation level
            if not fact_key or fact_key == 'null' or str(fact_key).startswith('SOUR:'):
                # Person-level citation at level 1
                _, indi_end, err = _find_indi_block(lines, xref)
                if err:
                    self.send_error(400, err)
                    return
                cite_lines = _build_citation_lines(sour_xref, page, text, note, base_level=1)
                new_lines  = lines[:indi_end] + cite_lines + lines[indi_end:]
            else:
                insert_pos, err = _find_fact_for_citation(lines, xref, fact_key)
                if err:
                    self.send_error(400, err)
                    return
                cite_lines = _build_citation_lines(sour_xref, page, text, note, base_level=2)
                new_lines  = lines[:insert_pos] + cite_lines + lines[insert_pos:]

            _write_gedcom_atomic(new_lines)
            print(f"[citation-add] {xref} {fact_key} → {sour_xref}")
            resp = json.dumps({'ok': True}).encode()

        elif parsed.path == '/api/edit_citation':
            xref         = (body.get('xref') or '').strip()
            citation_key = (body.get('citation_key') or '').strip()
            if not xref:
                self.send_error(400, 'xref is required')
                return
            if not citation_key:
                self.send_error(400, 'citation_key is required')
                return
            page = (body.get('page') or '').strip()
            text = (body.get('text') or '').strip()
            note = (body.get('note') or '').strip()
            lines = GED.read_text(encoding='utf-8').splitlines()
            block_start, block_end, cite_level, err = _find_citation_block(lines, xref, citation_key)
            if err:
                self.send_error(400, err)
                return
            new_lines = _update_citation_block(lines, block_start, block_end, cite_level, page, text, note)
            _write_gedcom_atomic(new_lines)
            print(f"[citation-edit] {xref} {citation_key}")
            resp = json.dumps({'ok': True}).encode()

        elif parsed.path == '/api/delete_citation':
            xref         = (body.get('xref') or '').strip()
            citation_key = (body.get('citation_key') or '').strip()
            if not xref:
                self.send_error(400, 'xref is required')
                return
            if not citation_key:
                self.send_error(400, 'citation_key is required')
                return
            lines = GED.read_text(encoding='utf-8').splitlines()
            block_start, block_end, _, err = _find_citation_block(lines, xref, citation_key)
            if err:
                self.send_error(400, err)
                return
            new_lines = lines[:block_start] + lines[block_end:]
            _write_gedcom_atomic(new_lines)
            print(f"[citation-delete] {xref} {citation_key}")
            resp = json.dumps({'ok': True}).encode()

        # ------------------------------------------------------------------ #
        # Person / relationship endpoints                                     #
        # ------------------------------------------------------------------ #

        elif parsed.path == '/api/add_person':
            given     = (body.get('given') or '').strip()
            surn      = (body.get('surn') or '').strip()
            sex       = (body.get('sex') or 'U').strip().upper()
            birth_yr  = (body.get('birth_year') or '').strip()
            rel_type  = (body.get('rel_type') or '').strip()
            rel_xref  = (body.get('rel_xref') or '').strip()

            if not given:
                self.send_error(400, 'given is required')
                return
            if not rel_xref:
                self.send_error(400, 'rel_xref is required')
                return
            if rel_type not in ('child_of', 'parent_of', 'spouse_of', 'sibling_of'):
                self.send_error(400, f'rel_type must be one of child_of, parent_of, spouse_of, sibling_of')
                return

            lines = GED.read_text(encoding='utf-8').splitlines()
            new_xref = _next_indi_xref(lines)

            # Build the new INDI block
            name_val = f'{given} /{surn}/' if surn else given
            new_indi = [f'0 {new_xref} INDI', f'1 NAME {name_val}']
            if surn:
                new_indi += [f'2 GIVN {given}', f'2 SURN {surn}']
            if sex in ('M', 'F'):
                new_indi.append(f'1 SEX {sex}')
            if birth_yr:
                new_indi += ['1 BIRT', f'2 DATE {birth_yr}']

            # Insert new INDI before TRLR
            trlr_idx = next(
                (i for i, l in enumerate(lines) if l.strip() == '0 TRLR'), len(lines)
            )
            lines = lines[:trlr_idx] + new_indi + lines[trlr_idx:]

            # Handle relationship
            if rel_type == 'child_of':
                # Find an existing FAMS for rel_xref and add CHIL to it,
                # or create a new FAM with rel_xref as parent.
                existing_fams = _get_fams_for_indi(lines, rel_xref)
                if existing_fams:
                    fam_xref = existing_fams[0]
                else:
                    fam_xref = _next_fam_xref(lines)
                    rel_sex = _get_sex(lines, rel_xref)
                    if rel_sex == 'F':
                        lines = _create_bare_fam(lines, fam_xref, None, rel_xref)
                        lines = _add_fams_to_indi(lines, rel_xref, fam_xref)
                    else:
                        lines = _create_bare_fam(lines, fam_xref, rel_xref, None)
                        lines = _add_fams_to_indi(lines, rel_xref, fam_xref)
                lines = _add_chil_to_fam(lines, fam_xref, new_xref)
                lines = _add_famc_to_indi(lines, new_xref, fam_xref)

            elif rel_type == 'parent_of':
                # New INDI is a parent of rel_xref. Find rel_xref's FAMC family.
                famc_xref = _get_famc_for_indi(lines, rel_xref)
                if famc_xref:
                    fam_xref = famc_xref
                    # Guard: check whether the HUSB/WIFE slot is already occupied
                    slot = 'WIFE' if sex == 'F' else 'HUSB'
                    fam_start, fam_end, ferr = _find_fam_block(lines, fam_xref)
                    if not ferr:
                        slot_occupied = any(
                            _TAG_RE.match(l) and _TAG_RE.match(l).group(2) == slot
                            for l in lines[fam_start:fam_end]
                        )
                        if slot_occupied:
                            self.send_error(400, f'Family {fam_xref} already has a {slot}')
                            return
                        lines = lines[:fam_end] + [f'1 {slot} {new_xref}'] + lines[fam_end:]
                else:
                    fam_xref = _next_fam_xref(lines)
                    if sex == 'F':
                        lines = _create_bare_fam(lines, fam_xref, None, new_xref)
                    else:
                        lines = _create_bare_fam(lines, fam_xref, new_xref, None)
                    lines = _add_chil_to_fam(lines, fam_xref, rel_xref)
                    lines = _add_famc_to_indi(lines, rel_xref, fam_xref)
                lines = _add_fams_to_indi(lines, new_xref, fam_xref)

            elif rel_type == 'spouse_of':
                rel_sex = _get_sex(lines, rel_xref)
                fam_xref = _next_fam_xref(lines)
                if sex == 'F' and rel_sex != 'F':
                    husb_xref, wife_xref = rel_xref, new_xref
                elif rel_sex == 'F' and sex != 'F':
                    husb_xref, wife_xref = new_xref, rel_xref
                else:
                    husb_xref, wife_xref = new_xref, rel_xref
                lines = _create_bare_fam(lines, fam_xref, husb_xref, wife_xref)
                lines = _add_fams_to_indi(lines, new_xref, fam_xref)
                lines = _add_fams_to_indi(lines, rel_xref, fam_xref)

            elif rel_type == 'sibling_of':
                # Add new INDI to the same FAMC family as rel_xref
                famc_xref = _get_famc_for_indi(lines, rel_xref)
                if famc_xref:
                    fam_xref = famc_xref
                else:
                    fam_xref = _next_fam_xref(lines)
                    lines = _create_bare_fam(lines, fam_xref, None, None)
                    lines = _add_chil_to_fam(lines, fam_xref, rel_xref)
                    lines = _add_famc_to_indi(lines, rel_xref, fam_xref)
                lines = _add_chil_to_fam(lines, fam_xref, new_xref)
                lines = _add_famc_to_indi(lines, new_xref, fam_xref)

            _write_gedcom_atomic(lines)
            print(f"[person-add] {new_xref} {name_val} ({rel_type} {rel_xref})")
            resp = json.dumps({'xref': new_xref}).encode()

        # ------------------------------------------------------------------ #
        # Godparent endpoints                                                 #
        # ------------------------------------------------------------------ #

        elif parsed.path == '/api/add_godparent':
            xref           = (body.get('xref') or '').strip()
            godparent_xref = (body.get('godparent_xref') or '').strip()
            if not xref:
                self.send_error(400, 'xref is required')
                return
            if not godparent_xref:
                self.send_error(400, 'godparent_xref is required')
                return
            lines = GED.read_text(encoding='utf-8').splitlines()
            _, indi_end, err = _find_indi_block(lines, xref)
            if err:
                self.send_error(400, err)
                return
            asso_block = [f'1 ASSO {godparent_xref}', '2 RELA Godparent']
            new_lines  = lines[:indi_end] + asso_block + lines[indi_end:]
            _write_gedcom_atomic(new_lines)
            print(f"[godparent-add] {xref} ← {godparent_xref}")
            resp = json.dumps({'ok': True}).encode()

        elif parsed.path == '/api/delete_godparent':
            xref           = (body.get('xref') or '').strip()
            godparent_xref = (body.get('godparent_xref') or '').strip()
            if not xref:
                self.send_error(400, 'xref is required')
                return
            if not godparent_xref:
                self.send_error(400, 'godparent_xref is required')
                return
            lines = GED.read_text(encoding='utf-8').splitlines()
            indi_start, indi_end, err = _find_indi_block(lines, xref)
            if err:
                self.send_error(400, err)
                return
            # Find the specific ASSO block for godparent_xref with RELA Godparent
            asso_start = asso_end = None
            for i in range(indi_start + 1, indi_end):
                m = _TAG_RE.match(lines[i])
                if not m or int(m.group(1)) != 1 or m.group(2) != 'ASSO':
                    continue
                val = (m.group(3) or '').strip()
                if val != godparent_xref:
                    continue
                # Check that the next subordinate line is RELA Godparent
                j = i + 1
                while j < indi_end:
                    sm = _TAG_RE.match(lines[j])
                    if sm and int(sm.group(1)) <= 1:
                        break
                    if sm and int(sm.group(1)) == 2 and sm.group(2) == 'RELA':
                        rela_val = (sm.group(3) or '').strip()
                        if rela_val == 'Godparent':
                            asso_start = i
                            # end of this ASSO block
                            k = i + 1
                            while k < indi_end:
                                skm = _TAG_RE.match(lines[k])
                                if skm and int(skm.group(1)) <= 1:
                                    break
                                k += 1
                            asso_end = k
                    j += 1
                if asso_start is not None:
                    break
            if asso_start is None:
                self.send_error(400, f'Godparent ASSO {godparent_xref} not found in {xref}')
                return
            new_lines = lines[:asso_start] + lines[asso_end:]
            _write_gedcom_atomic(new_lines)
            print(f"[godparent-delete] {xref} ← {godparent_xref}")
            resp = json.dumps({'ok': True}).encode()

        else:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(resp))
        self.end_headers()
        self.wfile.write(resp)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


# ---------------------------------------------------------------------------
# Graceful shutdown: commit on Ctrl-C
# ---------------------------------------------------------------------------

def _shutdown_handler(sig, frame):
    sys.exit(0)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, _shutdown_handler)
    regenerate()
    threading.Thread(target=watch, daemon=True).start()
    print(f"Serving on http://localhost:{PORT}/viz.html  (watching viz_ancestors.py and {GED.name} for changes)")
    with http.server.HTTPServer(('', PORT), Handler) as httpd:
        httpd.serve_forever()
