#!/usr/bin/env python3
"""
gedcom_linter.py — GEDCOM 5.5.1 linter and fixer.

Usage:
  # Check only (report violations, make no changes):
  python gedcom_linter.py yourfile.ged

  # Fix specific issues in-place:
  python gedcom_linter.py --fix-dates yourfile.ged
  python gedcom_linter.py --fix-places yourfile.ged
  python gedcom_linter.py --fix-whitespace yourfile.ged
  python gedcom_linter.py --fix-names yourfile.ged
  python gedcom_linter.py --fix-long-lines yourfile.ged
  python gedcom_linter.py --fix-duplicate-sources yourfile.ged

  # Run all fixes at once:
  python gedcom_linter.py --fix-all yourfile.ged

  # Preview changes without writing (dry run):
  python gedcom_linter.py --fix-dates --dry-run yourfile.ged

Checks performed:
  1. DATE format — every event DATE conforms to GEDCOM 5.5.1 grammar.
     --fix-dates normalizes common variants (e.g. "about 1835" → "ABT 1835",
     "January 5, 1900" → "5 JAN 1900", "1900-1905" → "BET 1900 AND 1905").
  2. DATE has year — every DATE value contains an extractable 3-or-4-digit year.
     (No auto-fix; these require manual review.)
  3. Trailing whitespace — no line ends with spaces or tabs.
  4. PLAC formatting — place values use consistent comma spacing.
  5. NAME double spaces — name values have no collapsed double spaces.
  6. Long lines — no line exceeds 255 characters.
  7. Duplicate SOUR citations — no exact-duplicate source blocks per event.
  8. Level jumps — no line's level exceeds the previous line's level by more
     than 1 (e.g., a level-3 line appearing directly after a level-1 line is
     invalid GEDCOM 5.5.1). No auto-fix; these require manual correction.
  9. NAME slash balance — each NAME value must contain zero or exactly one
     slash-delimited surname section (e.g. "John /Smith/" is valid; two pairs
     of slashes like "/John/ /Smith/" is invalid per GEDCOM 5.5.1 §2.7.2).
     No auto-fix; these require manual review.
 10. SEX values — SEX tag values must be M, F, or U per GEDCOM 5.5.1 §2.7.
     No auto-fix; these require manual review.
 11. ADDR under PLAC — ADDR is not a valid subordinate of PLAC in GEDCOM
     5.5.1. ADDR should be a sibling of PLAC (child of the parent event).
     --fix-addr-under-plac promotes such ADDR lines up one level.
 12. PLAC FORM header — GEDCOM 5.5.1 §2.7.3 recommends a "1 PLAC / 2 FORM"
     declaration in the HEAD block so importing software knows how to interpret
     the comma-separated fields in PLAC values. Warns if absent. No auto-fix.

Notes:
  - Only level-2 DATE lines (event dates on INDI/FAM records) are touched by
    --fix-dates. Level-3/4 DATE lines inside DATA citation blocks are reported
    but never rewritten.
  - Lines that cannot be automatically normalized are reported as remaining
    violations after --fix-dates.
"""

import argparse
import html
import os
import re
import sys
import unicodedata
from collections import defaultdict

# ---------------------------------------------------------------------------
# Month-name lookup (English, German, French, Spanish/Portuguese abbrevs)
# ---------------------------------------------------------------------------

MONTH_MAP = {
    # English
    'january': 'JAN', 'february': 'FEB', 'march': 'MAR', 'april': 'APR',
    'may': 'MAY', 'june': 'JUN', 'july': 'JUL', 'august': 'AUG',
    'september': 'SEP', 'october': 'OCT', 'november': 'NOV', 'december': 'DEC',
    'sept': 'SEP',
    # German
    'januar': 'JAN', 'februar': 'FEB', 'märz': 'MAR', 'mär': 'MAR',
    'mai': 'MAY', 'juni': 'JUN', 'juli': 'JUL',
    'oktober': 'OCT', 'dezember': 'DEC',
    # French
    'janvier': 'JAN', 'février': 'FEB', 'fevrier': 'FEB', 'févr': 'FEB',
    'avril': 'APR', 'juin': 'JUN', 'juillet': 'JUL',
    'août': 'AUG', 'aout': 'AUG', 'septembre': 'SEP', 'octobre': 'OCT',
    'novembre': 'NOV', 'décembre': 'DEC', 'déc': 'DEC',
    # Spanish / Portuguese abbrevs
    'ago': 'AUG',
}

# Build a regex that matches any month name (longest first to avoid partial matches)
_month_keys_sorted = sorted(MONTH_MAP.keys(), key=len, reverse=True)
MONTH_RE = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in _month_keys_sorted) + r')\b',
    re.IGNORECASE,
)


def replace_month(m: re.Match) -> str:
    return MONTH_MAP[m.group(1).lower()]


# ---------------------------------------------------------------------------
# GEDCOM 5.5.1 date grammar (what we accept as valid)
# ---------------------------------------------------------------------------

_MONTHS_PAT = (
    r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
)
GEDCOM_DATE_RE = re.compile(
    r"^(BET .+ AND .+"
    r"|FROM .+"
    r"|(ABT|CAL|EST|BEF|AFT|INT)? ?\d{0,2} ?" + _MONTHS_PAT + r" \d{1,4}"
    r"|(ABT|CAL|EST|BEF|AFT|INT)? ?\d{1,4}"
    r")$",
    re.IGNORECASE,
)

YEAR_RE = re.compile(r"\b\d{3,4}\b")

# Matches 3-letter GEDCOM month abbreviations (case-insensitive).
# Used by scan_date_month_caps / fix_date_caps and normalize_date.
_ABBREV_MONTH_RE = re.compile(
    r'\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b',
    re.IGNORECASE,
)

# AGE tag value grammar per GEDCOM 5.5.1
_AGE_RE = re.compile(
    r'^[<>]?'
    r'(?:'
    r'\d+y(?:\s+\d+m)?(?:\s+\d+d)?'
    r'|\d+m(?:\s+\d+d)?'
    r'|\d+d'
    r'|CHILD|INFANT|STILLBORN'
    r')$',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Normalization rules (applied in order)
# ---------------------------------------------------------------------------

# Rules applied sequentially by normalize_date(). Each entry is
# (pattern, replacement, flags). The full date-range rule is handled
# separately because it requires .strip() on captured groups.
_DATE_RULES: list[tuple[str, str, int]] = [
    # Approximate qualifiers → ABT
    (r'^(about|around|abt\.?|circa|ca\.?|approx\.?|maybe)\s+', 'ABT ', re.I),
    # Before / After
    (r'^(before|bef\.?)\s+', 'BEF ', re.I),
    (r'^(after|aft\.?)\s+', 'AFT ', re.I),
    # Plain "YYYY-YYYY"
    (r'^(\d{4})-(\d{4})$', r'BET \1 AND \2', 0),
    # "bet. YYYY-YYYY" or "between YYYY-YYYY"
    (r'^bet\.?\s+(\d{3,4})-(\d{3,4})$', r'BET \1 AND \2', re.I),
    (r'^between\s+(\d{3,4})-(\d{3,4})$', r'BET \1 AND \2', re.I),
    # "bet[ween] X and Y" — .+? allows multi-word date parts (e.g. "April 1962")
    (r'^bet(?:ween)?\.?\s+(.+?)\s+and\s+(.+)$', r'BET \1 AND \2', re.I),
    # "Jan." → "Jan"  (abbreviated months with trailing period)
    (r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.', r'\1', re.I),
    # "the Nth of Month" → "Nth Month"
    (r'\bthe\s+(\d{1,2}(?:st|nd|rd|th)?)\s+of\s+', r'\1 ', re.I),
    # Ordinal day numbers anywhere in the string: "1st", "2nd", "3rd", "4th" etc.
    (r'(\d{1,2})(st|nd|rd|th)(\s+)', r'\1\3', re.I),
    # "Month D, YYYY" → "D Month YYYY"
    (r'^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$', r'\2 \1 \3', 0),
    # "D Month, YYYY" → "D Month YYYY"  (trailing comma)
    (r'^(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})$', r'\1 \2 \3', 0),
    # "YYYY Month D" → "D Month YYYY"
    (r'^(\d{4})\s+([A-Za-z]+)\s+(\d{1,2})$', r'\3 \2 \1', 0),
    # "Month D YYYY" → "D Month YYYY"  (no comma, no qualifier)
    (r'^([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})$', r'\2 \1 \3', 0),
    # "QUAL Month D, YYYY" → "QUAL D Month YYYY"  (qualifier already applied)
    (r'^(BEF|AFT|ABT|CAL|EST|INT)\s+([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$',
     r'\1 \3 \2 \4', re.I),
    # "QUAL Month D YYYY" → "QUAL D Month YYYY"  (no comma)
    (r'^(BEF|AFT|ABT|CAL|EST|INT)\s+([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})$',
     r'\1 \3 \2 \4', re.I),
    # "QUAL D Month, YYYY" → "QUAL D Month YYYY"  (trailing comma only)
    (r'^(BEF|AFT|ABT|CAL|EST|INT)\s+(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})$',
     r'\1 \2 \3 \4', re.I),
]

_MONTH_ABBREVS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN',
                  'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']


def normalize_date(val: str) -> str:
    """
    Attempt to convert a non-standard GEDCOM date string to a valid
    GEDCOM 5.5.1 date. Returns the (possibly unchanged) value.

    Transformations applied:
      - "about / abt. / circa / ca. / approx." → ABT
      - "before / bef."                         → BEF
      - "after / aft."                          → AFT
      - "YYYY-YYYY" or full "date-date" range   → BET … AND …
      - "bet. YYYY-YYYY" / "between YYYY-YYYY"  → BET … AND …
      - "bet[ween] X and Y"                     → BET X AND Y
      - "Jan." abbreviated months with period   → "Jan"
      - "the Nth of Month"                      → "Nth Month"
      - "1st / 2nd / 3rd / 4th" ordinals        → bare number
      - "Month D, YYYY"                         → D Month YYYY
      - "D Month, YYYY" (trailing comma)        → D Month YYYY
      - "YYYY Month D"                          → D Month YYYY
      - "Month D YYYY" (no comma)               → D Month YYYY
      - Qualifier-prefixed reorder rules        → QUAL D Month YYYY
      - ISO "YYYY-MM-DD"                        → D Month YYYY
      - US "MM/DD/YYYY"                         → D Month YYYY
      - Non-English/full month names            → standard 3-letter abbrev
      - Collapse multiple spaces
    """
    v = val.strip()

    # ISO date: "1985-01-15" → "15 JAN 1985"
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})$', v)
    if m:
        mo = int(m.group(2))
        if 1 <= mo <= 12:
            v = f'{int(m.group(3))} {_MONTH_ABBREVS[mo - 1]} {m.group(1)}'

    # US slash date: "01/15/1985" → "15 JAN 1985"
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', v)
    if m:
        mo = int(m.group(1))
        if 1 <= mo <= 12:
            v = f'{int(m.group(2))} {_MONTH_ABBREVS[mo - 1]} {m.group(3)}'

    # "full date - full date" range (e.g. "Abt. 1569 - 1583") — handled
    # separately because it requires .strip() on captured groups.
    m = re.match(r'^(.+\d{4})\s*-\s*(.+\d{4})$', v)
    if m:
        v = f'BET {m.group(1).strip()} AND {m.group(2).strip()}'

    for pattern, replacement, flags in _DATE_RULES:
        v = re.sub(pattern, replacement, v, flags=flags)

    # Normalize month names to 3-letter GEDCOM abbreviations
    v = MONTH_RE.sub(replace_month, v)

    # Uppercase any remaining 3-letter month abbreviations (e.g. 'Feb' → 'FEB')
    v = _ABBREV_MONTH_RE.sub(lambda x: x.group(0).upper(), v)

    # Collapse extra whitespace
    v = re.sub(r'\s{2,}', ' ', v).strip()

    return v


# ---------------------------------------------------------------------------
# Redundant SOUR citation removal
# ---------------------------------------------------------------------------

SOUR_CITE_LINE_RE = re.compile(r'^(\d+) SOUR (@[^@]+@)$')
_LEVEL_RE = re.compile(r'^(\d+)')


def _sour_blocks(lines: list[str]):
    """
    Iterate over lines yielding (start_idx, end_idx, level, xref, children_tuple)
    for each SOUR citation block. end_idx is exclusive.
    """
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        m = SOUR_CITE_LINE_RE.match(line)
        if m:
            level = int(m.group(1))
            xref = m.group(2)
            j = i + 1
            while j < len(lines):
                child = lines[j].rstrip('\n')
                cm = _LEVEL_RE.match(child)
                if cm and int(cm.group(1)) <= level:
                    break
                j += 1
            children = tuple(lines[k].rstrip('\n') for k in range(i + 1, j))
            yield (i, j, level, xref, children)
            i = j
        else:
            i += 1


def _iter_sour_blocks_with_context(lines: list[str]):
    """
    Iterate over lines, yielding (start_i, end_i, key, children_t) for each
    SOUR citation block.

    - start_i / end_i  : half-open range [start_i, end_i) of lines in the block
    - key              : (current_rec_line, event_start_lineno, xref) — unique
                         per source citation within a record/event
    - children_t       : tuple of stripped child lines (used for dedup comparison)
    """
    defn_re = re.compile(r'^0 ')
    current_rec = None
    current_event = None
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        if defn_re.match(line):
            current_rec = line
            current_event = None
            i += 1
            continue
        if line.startswith('1 '):
            current_event = i
            i += 1
            continue
        m = SOUR_CITE_LINE_RE.match(line)
        if m and current_rec:
            xref = m.group(2)
            level = int(m.group(1))
            j = i + 1
            while j < len(lines):
                cm = _LEVEL_RE.match(lines[j].rstrip('\n'))
                if cm and int(cm.group(1)) <= level:
                    break
                j += 1
            children_t = tuple(lines[k].rstrip('\n') for k in range(i + 1, j))
            yield (i, j, (current_rec, current_event, xref), children_t)
            i = j
        else:
            i += 1


def scan_duplicate_sources(path: str):
    """
    Return list of (lineno, xref) for SOUR citation blocks that are exact
    duplicates of a previous citation of the same source under the same
    record/event (same xref AND identical child lines).
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    violations = []
    seen: defaultdict = defaultdict(set)

    for start_i, _end_i, key, children_t in _iter_sour_blocks_with_context(lines):
        if children_t in seen[key]:
            violations.append((start_i + 1, key[2]))
        else:
            seen[key].add(children_t)

    return violations


def fix_duplicate_sources(path: str, dry_run: bool = False):
    """
    Remove exact-duplicate SOUR citation blocks (same xref, same child lines,
    same parent record/event). Returns number of blocks removed.
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    seen: defaultdict = defaultdict(set)
    remove_ranges = []  # list of (start_idx, end_idx) to drop

    for start_i, end_i, key, children_t in _iter_sour_blocks_with_context(lines):
        if children_t in seen[key]:
            if dry_run:
                print(f'  line {start_i + 1}: duplicate {key[2]} under {key[1]}')
            remove_ranges.append((start_i, end_i))
        else:
            seen[key].add(children_t)

    if not dry_run and remove_ranges:
        drop = set()
        for start, end in remove_ranges:
            drop.update(range(start, end))
        lines_out = [line for idx, line in enumerate(lines) if idx not in drop]
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return len(remove_ranges)


# ---------------------------------------------------------------------------
# NAME double-space normalization
# ---------------------------------------------------------------------------

NAME_LINE_RE = re.compile(r'^((\d+) NAME )(.+)$')


def scan_name_double_spaces(path: str):
    """Return list of (lineno, original, fixed) for NAME lines with double spaces."""
    violations = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = NAME_LINE_RE.match(line)
            if not m:
                continue
            val = m.group(3)
            fixed = re.sub(r'  +', ' ', val).strip()
            if fixed != val:
                violations.append((lineno, val, fixed))
    return violations


def fix_name_double_spaces(path: str, dry_run: bool = False):
    """Collapse consecutive spaces in NAME values. Returns number of lines changed."""
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')
        m = NAME_LINE_RE.match(line)
        if m:
            val = m.group(3)
            fixed = re.sub(r'  +', ' ', val).strip()
            if fixed != val:
                changed += 1
                if dry_run:
                    print(f'  line {lineno}: {val!r}  →  {fixed!r}')
                line = m.group(1) + fixed
        lines_out.append(line + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Name casing (ALL CAPS → Title Case)
# ---------------------------------------------------------------------------

# Particles that stay lowercase unless they open a slash-delimited surname block.
_NAME_PARTICLES = frozenset({
    'af', 'aus',
    'bin', 'binte',
    'da', 'dal', 'dalla', 'das', 'de', 'degli', 'dei', 'del', 'della',
    'delle', 'dello', 'den', 'der', 'des', 'di', 'do', 'dos', 'du',
    'la', 'las', 'le', 'les', 'lo', 'los',
    'van', 'von',
    'y',
    'z', 'ze', 'zu', 'zur',
})


def _name_to_title_case(val: str) -> str:
    """
    Convert an all-caps GEDCOM NAME value to proper title case.

    Rules:
    - Each word is title-cased (handles hyphens and apostrophes via str.title()).
    - A word whose lowercase form is in _NAME_PARTICLES is kept lowercase,
      unless it is the very first word or it opens a slash-delimited surname
      block (i.e. it starts with '/').
    - Slash delimiters are preserved exactly.
    """
    titled = val.title()  # handles O'BRIEN→O'Brien, SMITH-JONES→Smith-Jones
    words = titled.split(' ')
    out = []
    for i, word in enumerate(words):
        lslash = word.startswith('/')
        rslash = word.endswith('/')
        core = word.strip('/')
        # Keep particle lowercase unless it's the first word or starts a
        # slash-delimited surname block.
        if core.lower() in _NAME_PARTICLES and i > 0:
            core = core.lower()
        out.append(('/' if lslash else '') + core + ('/' if rslash else ''))
    return ' '.join(out)


_NAME_PIECE_CASE_TAGS = frozenset({'GIVN', 'SURN', 'NPFX', 'NSFX'})
_NAME_PIECE_CASE_RE = re.compile(r'^((\d+) (GIVN|SURN|NPFX|NSFX) )(.+)$')


def fix_name_case(path: str, dry_run: bool = False) -> int:
    """
    Convert all-caps NAME values (and their GIVN/SURN/NPFX/NSFX sub-tags) to
    title case. Returns number of lines changed.

    Only lines where every alphabetic character is uppercase are touched;
    lines that already contain any lowercase letter are left untouched.
    GIVN/SURN sub-tags under a NAME block are fixed in the same pass so that
    the name value and its pieces always stay in sync.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    in_name_block = False
    name_level = 0

    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')

        # Detect level from the line prefix to track NAME block boundaries
        level_m = re.match(r'^(\d+)', line)
        cur_level = int(level_m.group(1)) if level_m else -1

        # If we drop back to or below the NAME level, we've left the NAME block
        if in_name_block and cur_level <= name_level:
            in_name_block = False

        m = NAME_LINE_RE.match(line)
        if m:
            name_level = int(m.group(2))
            in_name_block = True
            val = m.group(3)
            letters = [c for c in val if c.isalpha()]
            if letters and all(c.isupper() for c in letters):
                fixed = _name_to_title_case(val)
                if fixed != val:
                    changed += 1
                    if dry_run:
                        print(f'  line {lineno}: {val!r}  →  {fixed!r}')
                    line = m.group(1) + fixed
        elif in_name_block:
            mp = _NAME_PIECE_CASE_RE.match(line)
            if mp:
                val = mp.group(4)
                letters = [c for c in val if c.isalpha()]
                if letters and all(c.isupper() for c in letters):
                    fixed = _name_to_title_case(val)
                    if fixed != val:
                        changed += 1
                        if dry_run:
                            print(f'  line {lineno} ({mp.group(3)}): {val!r}  →  {fixed!r}')
                        line = mp.group(1) + fixed

        lines_out.append(line + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Long-line wrapping (NOTE lines > 255 chars → CONC continuations)
# ---------------------------------------------------------------------------

GEDCOM_MAX_LINE = 255


def _wrap_line(line: str, max_len: int = GEDCOM_MAX_LINE) -> list[str]:
    """
    Split a single GEDCOM line that exceeds max_len into a list of lines,
    using CONC continuation lines. The level of the CONC is one greater
    than the original line's level.

    Only wraps if the line exceeds max_len characters.
    """
    if len(line) <= max_len:
        return [line]

    # Match both plain lines (LEVEL TAG VALUE) and xref lines (LEVEL XREF TAG VALUE)
    m = re.match(r'^(\d+) (@[^@]+@) ([A-Z_][A-Z0-9_]*) (.+)$', line)
    if m:
        level = int(m.group(1))
        xref = m.group(2)
        tag = m.group(3)
        value = m.group(4)
        first_prefix = f'{level} {xref} {tag} '
    else:
        m = re.match(r'^(\d+) ([A-Z_][A-Z0-9_]*) (.+)$', line)
        if not m:
            return [line]  # can't parse — leave alone
        level = int(m.group(1))
        tag = m.group(2)
        value = m.group(3)
        first_prefix = f'{level} {tag} '

    conc_prefix = f'{level + 1} CONC '

    result = []
    # how many value chars fit on the first line
    first_avail = max_len - len(first_prefix)
    result.append((first_prefix + value[:first_avail]).rstrip())
    value = value[first_avail:]

    conc_avail = max_len - len(conc_prefix)
    while value:
        result.append((conc_prefix + value[:conc_avail]).rstrip())
        value = value[conc_avail:]

    return result


def scan_long_lines(path: str, max_len: int = GEDCOM_MAX_LINE):
    """Return list of (lineno, length) for lines exceeding max_len."""
    violations = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            if len(line) > max_len:
                violations.append((lineno, len(line)))
    return violations


def _scan_tag_under_parent(
    path: str, child_tag: str, parent_tag: str, track_sour: bool = False
) -> list[tuple[int, int]]:
    """
    Return (lineno, level) for every line where ``child_tag`` at level N+1
    immediately follows ``parent_tag`` at level N.  When ``track_sour`` is
    True, matches inside a SOUR citation block are excluded.
    """
    violations: list[tuple[int, int]] = []
    prev_level: int | None = None
    prev_tag: str | None = None
    in_sour_depth: int | None = None
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = re.match(r'^(\d+) ([A-Z_]+)', line)
            if not m:
                continue
            curr_level = int(m.group(1))
            curr_tag = m.group(2)
            if track_sour:
                if curr_tag == 'SOUR' and prev_level is not None and curr_level > 0:
                    in_sour_depth = curr_level
                elif in_sour_depth is not None and curr_level <= in_sour_depth:
                    in_sour_depth = None
            if (curr_tag == child_tag and prev_tag == parent_tag
                    and curr_level == prev_level + 1
                    and (not track_sour or in_sour_depth is None)):
                violations.append((lineno, curr_level))
            prev_level = curr_level
            prev_tag = curr_tag
    return violations


def scan_addr_under_plac(path: str) -> list[tuple[int, int]]:
    """
    Return list of (lineno, level) for ADDR lines that are direct children of
    PLAC lines (i.e., ADDR at level N+1 immediately following PLAC at level N).

    GEDCOM 5.5.1 does not define ADDR as a subordinate of PLAC. ADDR belongs
    as a sibling of PLAC (both children of the parent event), not nested under it.
    """
    return _scan_tag_under_parent(path, 'ADDR', 'PLAC')


def scan_note_under_plac(path: str) -> list[tuple[int, int]]:
    """
    Return list of (lineno, level) for NOTE lines that are direct children of
    PLAC lines (i.e., NOTE at level N+1 immediately following PLAC at level N),
    outside of any SOUR block.

    Venue names (church, cemetery, etc.) stored as NOTE children of PLAC should
    instead be ADDR siblings of PLAC, per the project convention.
    """
    return _scan_tag_under_parent(path, 'NOTE', 'PLAC', track_sour=True)


def scan_note_under_addr(path: str) -> list[tuple[int, int]]:
    """
    Return list of (lineno, level) for NOTE lines that are direct children of
    ADDR lines (i.e., NOTE at level N+1 immediately following ADDR at level N),
    outside of any SOUR block.

    These should be restructured so the venue name appears on the ADDR line
    and the street address becomes a CONT continuation.
    """
    return _scan_tag_under_parent(path, 'NOTE', 'ADDR', track_sour=True)


def _fix_misplaced_tag(
    path: str,
    child_tag: str,
    new_tag: str,
    parent_tag: str,
    track_sour: bool,
    dry_run: bool,
) -> int:
    """
    Promote lines where ``child_tag`` appears as an invalid child of ``parent_tag``
    up one level, renaming them to ``new_tag``. Any CONT/CONC continuation lines
    immediately following are also promoted by one level.

    When ``track_sour`` is True, lines inside a SOUR citation block are skipped.

    Returns the number of lines fixed.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    in_sour_depth: int | None = None
    i = 0
    while i < len(lines_in):
        line = lines_in[i].rstrip('\n')
        m = re.match(r'^(\d+) ([A-Z_]+)(.*)', line)
        if m:
            curr_level = int(m.group(1))
            curr_tag = m.group(2)
            rest = m.group(3)  # everything after the tag (including leading space+value)
            if track_sour:
                if curr_tag == 'SOUR' and curr_level > 0:
                    in_sour_depth = curr_level
                elif in_sour_depth is not None and curr_level <= in_sour_depth:
                    in_sour_depth = None
            if curr_tag == child_tag and (not track_sour or in_sour_depth is None):
                prev_gedcom = None
                for prev_raw in reversed(lines_out):
                    pm = re.match(r'^(\d+) ([A-Z_]+)', prev_raw.rstrip('\n'))
                    if pm:
                        prev_gedcom = (int(pm.group(1)), pm.group(2))
                        break
                if prev_gedcom and prev_gedcom[1] == parent_tag and prev_gedcom[0] == curr_level - 1:
                    new_level = curr_level - 1
                    fixed_line = f'{new_level} {new_tag}{rest}'
                    if dry_run:
                        print(f'  line {i + 1}: {line!r}')
                        print(f'           → {fixed_line!r}')
                    lines_out.append(fixed_line + '\n')
                    changed += 1
                    i += 1
                    # Promote any CONT/CONC continuation lines
                    while i < len(lines_in):
                        cont_line = lines_in[i].rstrip('\n')
                        cm = re.match(r'^(\d+) (CONT|CONC)', cont_line)
                        if cm and int(cm.group(1)) == curr_level + 1:
                            fixed_cont = f'{curr_level} {cm.group(2)}' + cont_line[len(f'{curr_level + 1} {cm.group(2)}'):]
                            if dry_run:
                                print(f'  line {i + 1}: {cont_line!r}')
                                print(f'           → {fixed_cont!r}')
                            lines_out.append(fixed_cont + '\n')
                            i += 1
                        else:
                            break
                    continue
        lines_out.append(line + '\n')
        i += 1

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


def fix_note_under_plac(path: str, dry_run: bool = False) -> int:
    """
    Convert NOTE lines that are invalid children of PLAC into ADDR siblings.

    Each ``(N+1) NOTE <venue>`` immediately following ``N PLAC ...`` (outside
    a SOUR block) is rewritten to ``N ADDR <venue>``. Any CONT/CONC lines
    that follow are promoted by one level to stay subordinate to the new ADDR.

    Returns the number of NOTE lines converted.
    """
    return _fix_misplaced_tag(path, child_tag='NOTE', new_tag='ADDR', parent_tag='PLAC',
                               track_sour=True, dry_run=dry_run)


def fix_note_under_addr(path: str, dry_run: bool = False) -> int:
    """
    Restructure NOTE children of ADDR so the venue name leads the ADDR line.

    When ``N ADDR <street>`` is immediately followed by ``(N+1) NOTE <venue>``
    (outside a SOUR block), rewrite to:

        N ADDR <venue>
        (N+1) CONT <street>

    This puts the venue name first (as is conventional) and demotes the street
    address to a CONT continuation.

    Returns the number of blocks restructured.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    in_sour_depth: int | None = None
    i = 0
    while i < len(lines_in):
        line = lines_in[i].rstrip('\n')
        m = re.match(r'^(\d+) ([A-Z_]+)(.*)', line)
        if m:
            curr_level = int(m.group(1))
            curr_tag = m.group(2)
            if curr_tag == 'SOUR' and curr_level > 0:
                in_sour_depth = curr_level
            elif in_sour_depth is not None and curr_level <= in_sour_depth:
                in_sour_depth = None
            if curr_tag == 'ADDR' and in_sour_depth is None and i + 1 < len(lines_in):
                next_line = lines_in[i + 1].rstrip('\n')
                nm = re.match(r'^(\d+) NOTE(.*)', next_line)
                if nm and int(nm.group(1)) == curr_level + 1:
                    street_val = m.group(3)   # e.g. " Shaftesbury Avenue"
                    venue_val = nm.group(2)    # e.g. " French Hospital"
                    new_addr = f'{curr_level} ADDR{venue_val}'
                    new_cont = f'{curr_level + 1} CONT{street_val}'
                    if dry_run:
                        print(f'  line {i + 1}: {line!r}')
                        print(f'  line {i + 2}: {next_line!r}')
                        print(f'           → {new_addr!r}')
                        print(f'           → {new_cont!r}')
                    lines_out.append(new_addr + '\n')
                    lines_out.append(new_cont + '\n')
                    changed += 1
                    i += 2
                    continue
        lines_out.append(line + '\n')
        i += 1

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


def fix_addr_under_plac(path: str, dry_run: bool = False) -> int:
    """
    Promote ADDR lines that are invalid children of PLAC up one level, making
    them siblings of PLAC (children of the parent event).

    Also promotes any CONT/CONC continuation lines directly following such an
    ADDR by one level to keep them correctly subordinate to ADDR.

    Returns the number of ADDR lines fixed.
    """
    return _fix_misplaced_tag(path, child_tag='ADDR', new_tag='ADDR', parent_tag='PLAC',
                               track_sour=False, dry_run=dry_run)


def scan_level_jumps(path: str) -> list[tuple[int, int, int]]:
    """
    Return list of (lineno, prev_level, curr_level) where the level increases
    by more than 1 from one line to the next.

    A jump greater than 1 (e.g., level 3 immediately after level 1) is invalid
    in GEDCOM 5.5.1 and likely indicates a malformed or truncated record.
    """
    violations: list[tuple[int, int, int]] = []
    prev_level: int | None = None
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            m = _LEVEL_RE.match(raw)
            if not m:
                continue
            curr_level = int(m.group(1))
            if prev_level is not None and curr_level > prev_level + 1:
                violations.append((lineno, prev_level, curr_level))
            prev_level = curr_level
    return violations


def scan_name_slashes(path: str) -> list[tuple[int, str]]:
    """
    Return list of (lineno, value) for NAME lines whose value contains more
    than one slash-delimited surname section.

    GEDCOM 5.5.1 §2.7.2 allows exactly zero or one pair of slashes in a NAME
    personal value: "Given /Surname/ Suffix".  Two or more pairs (e.g.
    "/Given/ /Surname/") are invalid.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = NAME_LINE_RE.match(line)
            if not m:
                continue
            val = m.group(3)
            # Count slash-delimited sections: each pair is open+close slash
            slash_count = val.count('/')
            if slash_count > 2:
                violations.append((lineno, val))
    return violations


_SEX_LINE_RE = re.compile(r'^1 SEX (.+)$')
_VALID_SEX = frozenset({'M', 'F', 'U'})


def scan_sex_values(path: str) -> list[tuple[int, str]]:
    """
    Return list of (lineno, value) for SEX lines whose value is not M, F, or U.

    GEDCOM 5.5.1 defines SEX_VALUE as M | F | U (male, female, undetermined).
    Any other value is a spec violation.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            m = _SEX_LINE_RE.match(raw.rstrip('\n'))
            if not m:
                continue
            val = m.group(1).strip()
            if val not in _VALID_SEX:
                violations.append((lineno, val))
    return violations


def fix_long_lines(path: str, dry_run: bool = False, max_len: int = GEDCOM_MAX_LINE):
    """Wrap lines > max_len using CONC continuation. Returns number of lines wrapped."""
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')
        if len(line) > max_len:
            wrapped = _wrap_line(line, max_len)
            if len(wrapped) > 1:
                changed += 1
                if dry_run:
                    print(f'  line {lineno} ({len(line)} chars) → {len(wrapped)} lines')
                for w in wrapped:
                    lines_out.append(w + '\n')
                continue
        lines_out.append(line + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# File scanning and fixing
# ---------------------------------------------------------------------------

DATE_LINE_RE = re.compile(r'^(2 DATE )(.+)$')


# ---------------------------------------------------------------------------
# Trailing-whitespace check and fix
# ---------------------------------------------------------------------------

_CONC_RE = re.compile(r'^\d+ CONC')


def scan_trailing_whitespace(path: str):
    """
    Return list of (lineno, repr(line)) for every line that has trailing
    whitespace (spaces or tabs before the newline).

    Lines whose immediate successor is a CONC tag are excluded: in GEDCOM
    5.5.1, CONC concatenates with no separator, so a trailing space on the
    preceding line is the only way to preserve a word boundary in the joined
    text and must not be treated as an error.
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    violations = []
    for i, raw in enumerate(lines):
        stripped = raw.rstrip('\n')
        if stripped == stripped.rstrip():
            continue  # no trailing whitespace
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
        if _CONC_RE.match(next_line):
            continue  # trailing space is semantically required before CONC
        violations.append((i + 1, stripped))
    return violations


def fix_trailing_whitespace(path: str, dry_run: bool = False):
    """
    Strip trailing whitespace from every line in *path*.
    Returns the number of lines changed.

    Lines whose immediate successor is a CONC tag are left untouched: the
    trailing space is semantically meaningful (see scan_trailing_whitespace).
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for i, raw in enumerate(lines_in):
        next_raw = lines_in[i + 1] if i + 1 < len(lines_in) else ''
        if _CONC_RE.match(next_raw.strip()):
            lines_out.append(raw)  # preserve trailing space before CONC
            continue
        clean = raw.rstrip('\n').rstrip() + '\n'
        if clean != raw:
            changed += 1
            if dry_run:
                print(f'  line {i + 1}: {raw.rstrip(chr(10))!r}')
        lines_out.append(clean)

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# HTML entity / tag detection and removal
# ---------------------------------------------------------------------------

# Matches any HTML entity: &lt; &gt; &amp; &apos; &quot; &nbsp; &#NNN; &#xHH;
_HTML_ENTITY_RE = re.compile(r'&(?:[a-zA-Z]+|#\d+|#x[0-9a-fA-F]+);')
# Block-level tags whose removal should leave a space so adjacent words are not run together.
_HTML_BLOCK_TAG_RE = re.compile(r'<(?:p|br|li|/p|/li)[^>]*>', re.IGNORECASE)
# Anchor tags: capture href and link text so we can emit "text (url)" instead of losing the URL.
_HTML_ANCHOR_RE   = re.compile(r'<a\s[^>]*\bhref="([^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
# Any remaining HTML tag.
_HTML_ANY_TAG_RE  = re.compile(r'<[^>]+>')
# A GEDCOM "level tag value" line — capture prefix (level + optional xref + tag) and value.
_GEDCOM_LINE_RE   = re.compile(r'^(\d+ (?:@[^@]+@ )?\S+ )(.*)', re.DOTALL)
# Runs of two or more spaces (used to collapse the gaps left after tag removal).
_MULTI_SPACE_RE   = re.compile(r'  +')


def _replace_anchor(m: re.Match) -> str:
    """
    Convert ``<a href="URL">text</a>`` to ``text (URL)``.

    Exceptions:
    - If URL is a template placeholder (``##SearchUrlPrefix##``), just keep text.
    - If the link text already is the URL (or empty), avoid duplication.
    """
    url  = m.group(1).strip()
    text = m.group(2).strip()
    if not url or '##' in url:
        return text
    if not text or text == url:
        return url
    return f'{text} ({url})'


def _decode_html_value(value: str) -> str:
    """
    Decode HTML entities and strip HTML tags from a GEDCOM field value.

    Processing order:
    1. Two passes of html.unescape() — handles single- and double-encoded
       entities (e.g. ``&amp;amp;`` → ``&amp;`` → ``&``).
    2. Replace Unicode non-breaking space (U+00A0) with a regular space.
    3. Convert ``<a href="URL">text</a>`` to ``text (URL)`` so hyperlink
       URLs are preserved rather than silently dropped.
    4. Replace block-level tags (``<p>``, ``<br>``, ``<li>``) with a space
       so adjacent words are not merged.
    5. Strip all remaining HTML tags.
    6. Collapse runs of spaces introduced by the above steps.
    """
    decoded = html.unescape(html.unescape(value))
    decoded = decoded.replace('\u00a0', ' ')
    decoded = _HTML_ANCHOR_RE.sub(_replace_anchor, decoded)
    decoded = _HTML_BLOCK_TAG_RE.sub(' ', decoded)
    decoded = _HTML_ANY_TAG_RE.sub('', decoded)
    decoded = _MULTI_SPACE_RE.sub(' ', decoded).strip()
    return decoded


def _line_has_html(line: str) -> bool:
    """Return True if the line contains an HTML entity or tag."""
    return bool(_HTML_ENTITY_RE.search(line) or _HTML_ANY_TAG_RE.search(line))


def scan_html_entities(path: str) -> list[tuple[int, str]]:
    """
    Return a list of ``(lineno, raw_value)`` for every line that contains
    HTML entities (e.g. ``&lt;``, ``&amp;``) or HTML tags (e.g. ``<i>``).
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            if _line_has_html(line):
                violations.append((lineno, line))
    return violations


def fix_html_entities(path: str, dry_run: bool = False) -> int:
    """
    Decode HTML entities and strip HTML tags from every GEDCOM line that
    contains them.  Returns the number of lines changed.

    The fix is applied to the *value* portion of each line (everything after
    the ``level [xref] tag`` prefix) so that structural GEDCOM tokens are
    never touched.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for i, raw in enumerate(lines_in):
        body = raw.rstrip('\n')
        if not _line_has_html(body):
            lines_out.append(raw)
            continue

        m = _GEDCOM_LINE_RE.match(body)
        if m:
            prefix, value = m.group(1), m.group(2)
            new_value = _decode_html_value(value)
            new_body = (prefix + new_value).rstrip()
        else:
            new_body = body.rstrip()

        if new_body != body:
            changed += 1
            if dry_run:
                print(f'  line {i + 1}: {body!r}')
                print(f'         → {new_body!r}')

        lines_out.append(new_body + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# PLAC normalization
# ---------------------------------------------------------------------------

PLAC_RE = re.compile(r'^(\d+ PLAC )(.+)$')

_STREET_SUFFIXES = re.compile(
    # "St" intentionally omitted — it matches saint-name prefixes in parish
    # and church names (e.g. "St Marks, Kensington") causing false positives.
    # Addresses using "St" as a Street abbreviation almost always have a
    # leading house number, which the digit heuristic already catches.
    r'\b(Avenue|Ave|Boulevard|Blvd|Road|Rd|Street|Lane|Ln|Drive|Dr'
    r'|Way|Court|Ct|Place|Pl|Terrace|Ter|Circle|Cir|Highway|Hwy'
    r'|Route|Rte|Alley|Aly|Parkway|Pkwy)\b', re.IGNORECASE)

_PLACE_KEYWORDS = re.compile(
    # "Fort" and "College" intentionally omitted — they appear frequently in
    # legitimate city names (Fort Worth, Fort Lauderdale, College Park) and
    # generate more false positives than true detections.
    r'\b(Cemetery|Cemetary|Graveyard|Churchyard|Church|Chapel|Cathedral'
    r'|Hospital|Clinic|Sanitarium|Sanatorium|School|University'
    r'|Synagogue|Mosque|Temple|Crematorium|Crematory|Mortuary|Funeral'
    r'|Convent|Monastery|Asylum|Prison|Jail|Workhouse|Poorhouse'
    r'|Infirmary|Barracks|Camp|Plantation)\b', re.IGNORECASE)

# Title abbreviations that prefix named places (e.g. "St. Mary's Church",
# "Mt. Auburn Cemetery") — stripped before street-suffix detection so the
# abbreviation "St" doesn't misclassify them as street addresses.
_TITLE_PREFIX_RE = re.compile(r'^[A-Za-z]{1,3}\.\s+')


def normalize_plac(val: str) -> str:
    """
    Normalize a PLAC value:
      - strip leading/trailing whitespace
      - strip leading/trailing commas
      - normalize spacing around commas: exactly one space after each comma,
        no space before
    """
    v = val.strip().strip(',').strip()
    v = re.sub(r'\s*,\s*', ', ', v)
    v = re.sub(r'\s{2,}', ' ', v)
    return v


def scan_plac_form(path: str) -> str | None:
    """
    Return the PLAC FORM value declared in the file header, or None if absent.

    GEDCOM 5.5.1 §2.7.3 recommends declaring the expected place hierarchy in
    the HEAD block:

        1 PLAC
        2 FORM City, County, State, Country

    Without this declaration, software importing the file cannot reliably
    interpret the comma-separated fields in PLAC values.
    """
    in_head = False
    in_plac = False
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            if line.startswith('0 HEAD'):
                in_head = True
                continue
            if in_head and line.startswith('0 '):
                break  # left the HEAD block
            if not in_head:
                continue
            if line == '1 PLAC':
                in_plac = True
                continue
            if in_plac:
                m = re.match(r'^2 FORM (.+)$', line)
                if m:
                    return m.group(1).strip()
                if re.match(r'^[12] ', line):
                    in_plac = False  # left the PLAC sub-block without finding FORM
    return None


def scan_plac(path: str):
    """Return list of (lineno, original_val, normalized_val) for bad PLAC lines."""
    violations = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = PLAC_RE.match(line)
            if not m:
                continue
            val = m.group(2)
            fixed = normalize_plac(val)
            if fixed != val:
                violations.append((lineno, val, fixed))
    return violations


def fix_plac(path: str, dry_run: bool = False):
    """Normalize all PLAC values in *path*. Returns number of lines changed."""
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')
        m = PLAC_RE.match(line)
        if m:
            val = m.group(2)
            fixed = normalize_plac(val)
            if fixed != val:
                changed += 1
                if dry_run:
                    print(f'  line {lineno}: {val!r}  →  {fixed!r}')
                line = m.group(1) + fixed
        lines_out.append(line + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


def classify_plac_part(part: str) -> str | None:
    """
    Classify a candidate misplaced first part of a PLAC value.

    Returns:
      'addr'      — looks like a street address → move to ADDR tag
      'note'      — looks like a named-place descriptor → move to NOTE tag
      'ambiguous' — neither pattern matches; flag for review, no auto-fix
      None        — part is empty (caller should skip)

    Classification priority:
      1. Leading digit OR street-suffix keyword → 'addr'
      2. Named-place keyword → 'note'
      3. Everything else → 'ambiguous'
    """
    p = part.strip()
    if not p:
        return None
    # Strip a leading title abbreviation (e.g. "St.", "Mt.", "Dr.") before
    # checking street suffixes so that "St. Mary's Church" is not misclassified
    # as a street address due to the abbreviation "St".
    stripped = _TITLE_PREFIX_RE.sub('', p)
    if p[0].isdigit() or _STREET_SUFFIXES.search(stripped):
        return 'addr'
    if _PLACE_KEYWORDS.search(p):
        return 'note'
    return 'ambiguous'


def scan_plac_address_parts(path: str) -> list:
    """
    Return list of (lineno, plac_val, first_part, category) for every PLAC
    line whose first comma-separated part is clearly misplaced.

    category is 'addr' (→ ADDR tag) or 'note' (→ NOTE tag).
    Ambiguous first parts (plain names that match neither pattern) are
    intentionally excluded — they are indistinguishable from valid city names.
    Only lines with at least two comma-separated parts are considered.
    """
    results = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = PLAC_RE.match(line)
            if not m:
                continue
            val = m.group(2).strip()
            parts = [p.strip() for p in val.split(',')]
            if len(parts) < 2:
                continue
            first = parts[0]
            category = classify_plac_part(first)
            if category not in ('addr', 'note'):
                continue
            results.append((lineno, val, first, category))
    return results


def fix_plac_address_parts(path: str, dry_run: bool = False) -> int:
    """
    Move misplaced first parts out of PLAC values.

    - Street addresses ('addr') → inserted as a subordinate ADDR tag
    - Named descriptors ('note') → inserted as a subordinate NOTE tag
    - Ambiguous parts → skipped (not auto-fixed)

    If the subordinate tag already exists on the very next line, the
    misplaced part is prepended: "<part>; <existing value>".

    Returns the number of PLAC lines changed.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    # Work on a list we can splice into
    lines_out = list(lines_in)
    changed = 0
    i = 0
    while i < len(lines_out):
        line = lines_out[i].rstrip('\n')
        m = PLAC_RE.match(line)
        if not m:
            i += 1
            continue

        val = m.group(2).strip()
        parts = [p.strip() for p in val.split(',')]
        if len(parts) < 2:
            i += 1
            continue

        first = parts[0]
        category = classify_plac_part(first)
        if category not in ('addr', 'note'):
            i += 1
            continue

        tag = 'ADDR' if category == 'addr' else 'NOTE'
        plac_level = int(m.group(1).split()[0])
        child_level = plac_level + 1
        child_prefix = f'{child_level} {tag} '
        stripped_val = ', '.join(parts[1:])
        new_plac_line = m.group(1).rstrip() + ' ' + stripped_val

        if dry_run:
            print(f'  line {i + 1}: PLAC {val!r}')
            print(f'    → PLAC {stripped_val!r}')
            print(f'    → insert: {child_prefix}{first!r}')

        # Check if the immediately following line is already the same child tag
        next_i = i + 1
        if next_i < len(lines_out):
            next_line = lines_out[next_i].rstrip('\n')
            if next_line.startswith(child_prefix):
                existing_val = next_line[len(child_prefix):]
                merged = f'{first}; {existing_val}'
                if dry_run:
                    print(f'    → merge existing {tag}: {merged!r}')
                if not dry_run:
                    lines_out[next_i] = child_prefix + merged + '\n'
                    lines_out[i] = new_plac_line + '\n'
                changed += 1
                i += 2
                continue

        if not dry_run:
            lines_out[i] = new_plac_line + '\n'
            lines_out.insert(i + 1, child_prefix + first + '\n')
        changed += 1
        i += 2  # skip past the newly inserted line

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Structural checks (require gedcom_merge parser — lazy imports for speed)
# ---------------------------------------------------------------------------

def scan_broken_xrefs(path: str) -> list[str]:
    """
    Return a list of broken cross-reference error strings.
    Checks FAM HUSB/WIFE/CHIL, INDI FAMS/FAMC/OBJE, and all SOUR citations.
    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.analysis import _check_broken_xrefs
    return _check_broken_xrefs(parse_gedcom(path))


# ---------------------------------------------------------------------------
# Record-order check and fix
# ---------------------------------------------------------------------------

# Canonical position of each top-level record type (lower = earlier in file).
# Unknown tags (e.g. _LOC) get rank 8, slotted between NOTE and TRLR.
_RECORD_RANK: dict[str, int] = {
    'HEAD': 0,
    'SUBM': 1,
    'INDI': 2,
    'FAM':  3,
    'SOUR': 4,
    'REPO': 5,
    'OBJE': 6,
    'NOTE': 7,
    'TRLR': 9,
}
_RANK_UNKNOWN = 8


def _rec_rank(tag: str) -> int:
    return _RECORD_RANK.get(tag, _RANK_UNKNOWN)


def scan_record_order(path: str) -> list[str]:
    """
    Return human-readable strings for top-level records that appear out of
    canonical GEDCOM order: HEAD, SUBM, INDI, FAM, SOUR, REPO, OBJE, NOTE,
    <other>, TRLR.
    """
    violations: list[str] = []
    max_rank = -1
    max_tag = ''
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = re.match(r'^0 (?:(@[^@]+@) )?(\S+)', line)
            if not m:
                continue
            xref = m.group(1) or ''
            tag = m.group(2)
            if tag == 'TRLR':
                break
            rank = _rec_rank(tag)
            if rank < max_rank:
                label = f'{xref} {tag}'.strip() if xref else tag
                violations.append(
                    f'line {lineno}: {label} appears after {max_tag} '
                    f'({tag!r} should precede {max_tag!r})'
                )
            else:
                max_rank = rank
                max_tag = tag
    return violations


def fix_record_order(path: str, dry_run: bool = False) -> int:
    """
    Reorder top-level records into canonical GEDCOM sequence:
    HEAD, SUBM, INDI, FAM, SOUR, REPO, OBJE, NOTE, <other>, TRLR.
    Preserves original order within each record-type group.
    Returns the number of top-level records that were moved.
    """
    with open(path, encoding='utf-8') as f:
        raw_lines = f.readlines()

    # Split into blocks: each block owns a level-0 line plus all following
    # higher-level lines up to (but not including) the next level-0 line.
    blocks: list[tuple[str, list[str]]] = []   # (tag, lines)
    current_lines: list[str] = []
    current_tag = ''

    for raw in raw_lines:
        m = re.match(r'^0 (?:@[^@]+@ )?(\S+)', raw.rstrip('\n'))
        if m:
            if current_lines:
                blocks.append((current_tag, current_lines))
            current_tag = m.group(1)
            current_lines = [raw]
        else:
            current_lines.append(raw)
    if current_lines:
        blocks.append((current_tag, current_lines))

    head   = [(t, ls) for t, ls in blocks if t == 'HEAD']
    trlr   = [(t, ls) for t, ls in blocks if t == 'TRLR']
    middle = [(t, ls) for t, ls in blocks if t not in ('HEAD', 'TRLR')]

    sorted_middle = sorted(middle, key=lambda b: _rec_rank(b[0]))

    # Count blocks that are out of canonical position (appear after a type with
    # a higher rank).  This is the number that will actually move, not a
    # positional-diff count (which over-counts due to downstream shifting).
    moved = 0
    max_r = -1
    for tag, _ in middle:
        r = _rec_rank(tag)
        if r < max_r:
            moved += 1
        else:
            max_r = r

    if moved and not dry_run:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8', newline='\n') as f:
            for _, ls in head + sorted_middle + trlr:
                for line in ls:
                    f.write(line if line.endswith('\n') else line + '\n')
        os.replace(tmp, path)

    return moved


def scan_dangling_note_xrefs(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, xref) for NOTE pointer lines that reference a shared-note
    xref which has no matching top-level '0 @xref@ NOTE' record.
    """
    defined: set[str] = set()
    references: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m0 = re.match(r'^0 (@[^@]+@) NOTE', line)
            if m0:
                defined.add(m0.group(1))
                continue
            mn = re.match(r'^\d+ NOTE (@[^@]+@)\s*$', line)
            if mn:
                references.append((lineno, mn.group(1)))
    return [(ln, xref) for ln, xref in references if xref not in defined]


def scan_duplicate_families(path: str) -> list[tuple[str, str]]:
    """
    Return (xref_a, xref_b) pairs of FAM records sharing the same husband+wife.
    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.analysis import _find_duplicate_families
    return _find_duplicate_families(parse_gedcom(path))


def scan_duplicate_sources_structural(path: str) -> list[tuple[str, str]]:
    """
    Return (xref_a, xref_b) pairs of SOUR records with matching normalized titles.
    Unlike scan_duplicate_sources() (which checks exact citation blocks), this
    uses full title similarity across the entire source list.
    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.analysis import _find_duplicate_sources
    return _find_duplicate_sources(parse_gedcom(path))


def scan_orphaned_individuals(path: str) -> list[str]:
    """
    Return xrefs of individuals with no FAMS or FAMC links.
    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.analysis import _find_orphaned_individuals
    return _find_orphaned_individuals(parse_gedcom(path))


def scan_duplicate_names(path: str) -> dict[str, list[str]]:
    """
    Return {xref: [duplicate_name_strings]} for individuals that have the same
    normalized (given, surname) pair appearing more than once in their NAME list.
    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.analysis import _find_duplicate_names
    return _find_duplicate_names(parse_gedcom(path))


def fix_broken_xrefs(path: str, dry_run: bool = False) -> int:
    """
    Remove dangling cross-references (CHIL/HUSB/WIFE/FAMS/FAMC/OBJE/SOUR
    pointers to nonexistent records) from the file.
    Returns the number of references removed.
    Requires the gedcom_merge parser/writer.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.merge import purge_dangling_xrefs
    from gedcom_merge.writer import write_gedcom
    merged = parse_gedcom(path)
    removed = purge_dangling_xrefs(merged)
    if removed and not dry_run:
        write_gedcom(merged, path)
    return removed


def fix_duplicate_families(path: str, dry_run: bool = False) -> int:
    """
    Collapse FAM records that share the same husband+wife into a single record,
    unioning their events/children/citations. Also removes empty shells created
    by the collapse.
    Returns the number of duplicate family records removed.
    Requires the gedcom_merge parser/writer.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.merge import deduplicate_duplicate_families, remove_empty_family_shells
    from gedcom_merge.writer import write_gedcom
    merged = parse_gedcom(path)
    removed = deduplicate_duplicate_families(merged)
    remove_empty_family_shells(merged)
    if removed and not dry_run:
        write_gedcom(merged, path)
    return removed


def fix_duplicate_names(path: str, dry_run: bool = False) -> int:
    """
    Remove duplicate NAME entries within individual records (same normalized
    given+surname appearing more than once).
    Returns the number of duplicate NAME entries removed.
    Requires the gedcom_merge parser/writer.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.merge import deduplicate_duplicate_names
    from gedcom_merge.writer import write_gedcom
    merged = parse_gedcom(path)
    removed = deduplicate_duplicate_names(merged)
    if removed and not dry_run:
        write_gedcom(merged, path)
    return removed


def fix_merge_sources(path: str, keep_xref: str, remove_xref: str,
                      dry_run: bool = False) -> int:
    """
    Remap all citations from remove_xref to keep_xref, then delete remove_xref.
    Use this to manually merge source records that the auto-dedup didn't catch.
    Returns the number of citation records updated (remapped or collapsed).
    Requires the gedcom_merge parser/writer.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.writer import write_gedcom
    from gedcom_merge.merge import _apply_citation_remap

    gf = parse_gedcom(path)
    if keep_xref not in gf.sources:
        raise ValueError(f'keep xref not found in file: {keep_xref}')
    if remove_xref not in gf.sources:
        raise ValueError(f'remove xref not found in file: {remove_xref}')

    updated = _apply_citation_remap(gf, {remove_xref: keep_xref})
    del gf.sources[remove_xref]

    if not dry_run:
        write_gedcom(gf, path)
    return updated


_EVENT_SORT_FIRST_TAGS = frozenset({'BIRT', 'CHR', 'BAPM', 'ADOP'})
_EVENT_SORT_LAST_TAGS  = frozenset({'DEAT', 'BURI', 'PROB', 'WILL'})


def _event_sort_key(ev) -> tuple:
    """Sort key for a GEDCOM EventRecord.

    Birth-type events (BIRT, CHR, BAPM, ADOP) are always placed first;
    death-type events (DEAT, BURI, PROB, WILL) are always placed last.
    All other events are sorted chronologically by date within the middle group.
    Events with no date sort to the end of their group (year 9999).
    """
    group = 0 if ev.tag in _EVENT_SORT_FIRST_TAGS else (2 if ev.tag in _EVENT_SORT_LAST_TAGS else 1)
    year  = (ev.date.year  or 9999) if ev.date else 9999
    month = (ev.date.month or 0)    if ev.date else 0
    day   = (ev.date.day   or 0)    if ev.date else 0
    return (group, year, month, day)


def scan_unsorted_events(path: str) -> list[str]:
    """
    Return a list of human-readable strings for individuals and families
    whose events are not in chronological order.
    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    gf = parse_gedcom(path)
    issues: list[str] = []
    for xref, ind in gf.individuals.items():
        keys = [_event_sort_key(e) for e in ind.events]
        if keys != sorted(keys):
            issues.append(f'{xref}: {len(ind.events)} events are out of chronological order')
    for xref, fam in gf.families.items():
        keys = [_event_sort_key(e) for e in fam.events]
        if keys != sorted(keys):
            issues.append(f'{xref}: {len(fam.events)} family events are out of chronological order')
    return issues


def fix_sort_events(path: str, dry_run: bool = False) -> int:
    """
    Sort events within each individual and family record into chronological
    order. Birth-type events are pinned first; death-type events are pinned
    last. Returns the count of records whose event order changed.
    Requires the gedcom_merge parser/writer.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.writer import write_gedcom
    gf = parse_gedcom(path)
    changed = 0
    for ind in gf.individuals.values():
        original = [_event_sort_key(e) for e in ind.events]
        ind.events = sorted(ind.events, key=_event_sort_key)
        if [_event_sort_key(e) for e in ind.events] != original:
            changed += 1
    for fam in gf.families.values():
        original = [_event_sort_key(e) for e in fam.events]
        fam.events = sorted(fam.events, key=_event_sort_key)
        if [_event_sort_key(e) for e in fam.events] != original:
            changed += 1
    if not dry_run and changed:
        write_gedcom(gf, path)
    return changed


def _is_level2_date(line: str) -> bool:
    """Return True if this is a level-2 DATE line (event date, not citation)."""
    return line.startswith('2 DATE ')


def scan(path: str):
    """
    Scan a GEDCOM file and return two lists:
      no_year     — (lineno, value) for DATE lines with no extractable year
      bad_format  — (lineno, value) for DATE lines that fail GEDCOM_DATE_RE
                    (only level-2 DATE lines are included)
    """
    no_year = []
    bad_format = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = re.match(r'^\d+ DATE (.+)$', line)
            if not m:
                continue
            val = m.group(1).strip()
            if not YEAR_RE.search(val):
                no_year.append((lineno, val))
            elif not GEDCOM_DATE_RE.match(val):
                if _is_level2_date(line):
                    bad_format.append((lineno, val))
    return no_year, bad_format


def fix_file(path: str, dry_run: bool = False):
    """
    Rewrite all level-2 DATE lines in *path* using normalize_date().
    Returns (changed, remaining_violations) counts.

    If dry_run is True, print a preview of changes but do not write.
    """
    lines_in = []
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    remaining = []

    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')
        m = DATE_LINE_RE.match(line)
        if m and _is_level2_date(line):
            prefix, val = m.group(1), m.group(2).strip()
            new_val = normalize_date(val)
            if new_val != val:
                changed += 1
                if dry_run:
                    print(f'  line {lineno}: {val!r}  →  {new_val!r}')
                line = prefix + new_val
            if not GEDCOM_DATE_RE.match(new_val) and YEAR_RE.search(new_val):
                remaining.append((lineno, new_val))
        lines_out.append(line + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed, remaining


# ---------------------------------------------------------------------------
# Severity-level constants
# ---------------------------------------------------------------------------

_ERR  = '[ERROR]'
_WARN = '[WARNING]'
_INFO = '[INFO]'


# ---------------------------------------------------------------------------
# Date month-capitalization check and fix  (spec 2.1)
# ---------------------------------------------------------------------------

def scan_date_month_caps(path: str) -> list[tuple[int, str]]:
    """
    Return list of (lineno, value) for DATE lines where a month abbreviation
    is not fully uppercase (e.g. 'Feb', 'apr', 'jan').
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = re.match(r'^\d+ DATE (.+)$', line)
            if not m:
                continue
            val = m.group(1).strip()
            for match in _ABBREV_MONTH_RE.finditer(val):
                if match.group(0) != match.group(0).upper():
                    violations.append((lineno, val))
                    break
    return violations


def fix_date_caps(path: str, dry_run: bool = False) -> int:
    """
    Normalize month abbreviations in DATE lines to uppercase.
    Returns number of lines changed.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')
        m = re.match(r'^(\d+ DATE )(.+)$', line)
        if m:
            val = m.group(2).strip()
            fixed = _ABBREV_MONTH_RE.sub(lambda x: x.group(0).upper(), val)
            if fixed != val:
                changed += 1
                if dry_run:
                    print(f'  line {lineno}: {val!r}  →  {fixed!r}')
                line = m.group(1) + fixed
        lines_out.append(line + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Header required-field validation  (spec 1.1)
# ---------------------------------------------------------------------------

def scan_header_required_fields(path: str) -> list[str]:
    """
    Return a list of description strings for required HEAD structures that are absent.

    Checks:
      1 SOUR   — approved system ID (required)
      1 SUBM   — submitter reference (required)
      1 GEDC   — with subordinate 2 VERS and 2 FORM LINEAGE-LINKED (required)
      1 CHAR   — character set (required)
    """
    in_head = False
    has_sour = False
    has_subm = False
    has_gedc = False
    has_gedc_vers = False
    has_gedc_form = False
    has_char = False
    in_gedc = False

    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            if line.startswith('0 HEAD'):
                in_head = True
                continue
            if in_head and line.startswith('0 '):
                break
            if not in_head:
                continue
            if re.match(r'^1 SOUR\b', line):
                has_sour = True
            if re.match(r'^1 SUBM ', line):
                has_subm = True
            if line == '1 GEDC':
                has_gedc = True
                in_gedc = True
            elif in_gedc and line.startswith('1 '):
                in_gedc = False
            if re.match(r'^1 CHAR\b', line):
                has_char = True
            if in_gedc:
                if re.match(r'^2 VERS ', line):
                    has_gedc_vers = True
                if re.match(r'^2 FORM LINEAGE-LINKED', line, re.IGNORECASE):
                    has_gedc_form = True

    missing = []
    if not has_sour:
        missing.append('1 SOUR (approved system ID) is absent from HEAD')
    if not has_subm:
        missing.append('1 SUBM (submitter reference) is absent from HEAD')
    if not has_gedc:
        missing.append('1 GEDC block is absent from HEAD')
    else:
        if not has_gedc_vers:
            missing.append('2 VERS is absent from the HEAD GEDC block')
        if not has_gedc_form:
            missing.append('2 FORM LINEAGE-LINKED is absent from the HEAD GEDC block')
    if not has_char:
        missing.append('1 CHAR (character set) is absent from HEAD')
    return missing


# ---------------------------------------------------------------------------
# Bare DEAT/BIRT without assertion  (spec 1.2)
# ---------------------------------------------------------------------------

_BARE_EVENT_TAGS = frozenset({'BIRT', 'CHR', 'DEAT'})


def scan_bare_event_tags(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, tag) for level-1 BIRT/CHR/DEAT lines that have no value
    and no level-2 or deeper children.

    A bare tag like '1 DEAT' (no 'Y' and no subordinate DATE/PLAC/etc.)
    violates GEDCOM 5.5.1 which requires '1 DEAT Y' to assert a known death
    with no details.  Tags with subordinate children are valid (the data implies
    the event happened).
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        m = re.match(r'^1 ([A-Z]+)(.*)', line)
        if m and m.group(1) in _BARE_EVENT_TAGS:
            tag = m.group(1)
            val = m.group(2).strip()
            # Skip if value is present (including 'Y')
            if val:
                i += 1
                continue
            # Check for children (any level-2+ line before next level-0/1)
            j = i + 1
            has_children = False
            while j < len(lines):
                cl = lines[j].rstrip('\n')
                cm = re.match(r'^(\d+)', cl)
                if cm:
                    lvl = int(cm.group(1))
                    if lvl >= 2:
                        has_children = True
                        break
                    else:
                        break
                j += 1
            if not has_children:
                violations.append((i + 1, tag))
        i += 1
    return violations


# ---------------------------------------------------------------------------
# EVEN / FACT / IDNO without TYPE  (spec 1.3)
# ---------------------------------------------------------------------------

_TYPED_EVENT_TAGS = frozenset({'EVEN', 'FACT', 'IDNO'})


def scan_untyped_events(path: str) -> list[tuple[int, str, str]]:
    """
    Return (lineno, tag, xref) for level-1 EVEN/FACT/IDNO lines that have no
    subordinate 2 TYPE child.
    """
    violations: list[tuple[int, str, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    current_xref = ''
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        m0 = re.match(r'^0 (@[^@]+@) ', line)
        if m0:
            current_xref = m0.group(1)
            i += 1
            continue
        m = re.match(r'^1 ([A-Z]+)', line)
        if m and m.group(1) in _TYPED_EVENT_TAGS:
            tag = m.group(1)
            lineno = i + 1
            j = i + 1
            has_type = False
            while j < len(lines):
                cl = lines[j].rstrip('\n')
                cm = re.match(r'^(\d+) ([A-Z]+)', cl)
                if cm:
                    lvl = int(cm.group(1))
                    if lvl == 2 and cm.group(2) == 'TYPE':
                        has_type = True
                        break
                    elif lvl <= 1:
                        break
                j += 1
            if not has_type:
                violations.append((lineno, tag, current_xref))
        i += 1
    return violations


# ---------------------------------------------------------------------------
# Missing SEX tag  (spec 1.10)
# ---------------------------------------------------------------------------

def scan_missing_sex(path: str) -> list[str]:
    """
    Return xrefs of INDI records that have no 1 SEX tag at all.
    (The existing scan_sex_values checks for *invalid* values; this checks
    for *absence*.)
    """
    violations: list[str] = []
    current_xref: str | None = None
    in_indi = False
    has_sex = False

    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            m = re.match(r'^0 (@[^@]+@) INDI', line)
            if m:
                if in_indi and current_xref and not has_sex:
                    violations.append(current_xref)
                current_xref = m.group(1)
                in_indi = True
                has_sex = False
                continue
            if in_indi and line.startswith('0 '):
                if current_xref and not has_sex:
                    violations.append(current_xref)
                in_indi = False
                current_xref = None
                continue
            if in_indi and re.match(r'^1 SEX\b', line):
                has_sex = True

    if in_indi and current_xref and not has_sex:
        violations.append(current_xref)
    return violations


# ---------------------------------------------------------------------------
# AGE value validation  (spec 1.4)
# ---------------------------------------------------------------------------

def scan_age_values(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, value) for AGE tag lines whose value does not conform to the
    GEDCOM 5.5.1 grammar: optional '<'/'>' prefix, followed by one of
    YYy [MMm [DDd]], MMm [DDd], DDd, or the keywords CHILD / INFANT / STILLBORN.
    Maximum 12 characters.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            m = re.match(r'^\d+ AGE (.+)$', raw.rstrip('\n'))
            if m:
                val = m.group(1).strip()
                if len(val) > 12 or not _AGE_RE.match(val):
                    violations.append((lineno, val))
    return violations


# ---------------------------------------------------------------------------
# RESN value validation  (spec 1.7)
# ---------------------------------------------------------------------------

_VALID_RESN = frozenset({'confidential', 'locked', 'privacy'})


def scan_resn_values(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, value) for RESN lines whose value is not in
    {confidential, locked, privacy}.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            m = re.match(r'^\d+ RESN (.+)$', raw.rstrip('\n'))
            if m:
                val = m.group(1).strip()
                if val.lower() not in _VALID_RESN:
                    violations.append((lineno, val))
    return violations


# ---------------------------------------------------------------------------
# PEDI value validation  (spec 1.8)
# ---------------------------------------------------------------------------

_VALID_PEDI = frozenset({'adopted', 'birth', 'foster', 'sealing'})


def scan_pedi_values(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, value) for PEDI lines whose value is not in
    {adopted, birth, foster, sealing}.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            m = re.match(r'^\d+ PEDI (.+)$', raw.rstrip('\n'))
            if m:
                val = m.group(1).strip()
                if val.lower() not in _VALID_PEDI:
                    violations.append((lineno, val))
    return violations


# ---------------------------------------------------------------------------
# Non-standard tag inventory  (spec 1.9)
# ---------------------------------------------------------------------------

_NONSTANDARD_TAG_SUGGESTIONS: dict[str, str] = {
    '_FREL': 'PEDI (under FAMC, father relationship)',
    '_MREL': 'PEDI (under FAMC, mother relationship)',
    '_SREL': 'NOTE on FAM record, or 1 EVEN with 2 TYPE Partnership',
    '_FSID': 'No standard equivalent — FamilySearch-specific identifier',
    '_UID':  'No standard equivalent — application-specific unique ID',
}


def scan_nonstandard_tags(path: str) -> dict[str, int]:
    """
    Return {tag: count} for all underscore-prefixed tags found in the file.
    These are vendor extensions not defined in GEDCOM 5.5.1.
    """
    counts: dict[str, int] = {}
    with open(path, encoding='utf-8') as f:
        for raw in f:
            m = re.match(r'^\d+ (_[A-Z0-9_]+)', raw.rstrip('\n'))
            if m:
                tag = m.group(1)
                counts[tag] = counts.get(tag, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# OCCU length warning  (spec 3.3)
# ---------------------------------------------------------------------------

def scan_occu_length(path: str, threshold: int = 120) -> list[tuple[int, int]]:
    """
    Return (lineno, length) for OCCU values exceeding *threshold* characters.
    Long OCCU values likely contain narrative text that should be split into a
    short value with a subordinate NOTE.
    """
    violations: list[tuple[int, int]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            m = re.match(r'^\d+ OCCU (.+)$', raw.rstrip('\n'))
            if m:
                val = m.group(1)
                if len(val) > threshold:
                    violations.append((lineno, len(val)))
    return violations


# ---------------------------------------------------------------------------
# Source quality report  (spec 1.11)
# ---------------------------------------------------------------------------

def scan_source_quality(path: str) -> dict:
    """
    Return a dict with three keys:
      'no_title'     : list of xrefs for SOUR records with no TITL
      'no_authority' : list of (xref, title) for SOUR records with TITL but no AUTH/PUBL/REPO
      'no_page'      : list of (lineno, sour_xref) for source citations with no PAGE child
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    no_title: list[str] = []
    no_authority: list[tuple[str, str]] = []
    no_page: list[tuple[int, str]] = []

    # ── Scan SOUR definition records ─────────────────────────────────────────
    i = 0
    current_xref: str | None = None
    in_sour_rec = False
    has_titl = False
    has_authority = False
    sour_title = ''

    while i < len(lines):
        line = lines[i].rstrip('\n')
        m0 = re.match(r'^0 (@S[^@]+@) SOUR', line)
        if m0:
            if in_sour_rec and current_xref:
                if not has_titl:
                    no_title.append(current_xref)
                elif not has_authority:
                    no_authority.append((current_xref, sour_title))
            current_xref = m0.group(1)
            in_sour_rec = True
            has_titl = False
            has_authority = False
            sour_title = ''
            i += 1
            continue
        if in_sour_rec and line.startswith('0 '):
            if current_xref:
                if not has_titl:
                    no_title.append(current_xref)
                elif not has_authority:
                    no_authority.append((current_xref, sour_title))
            in_sour_rec = False
            current_xref = None
        if in_sour_rec:
            mt = re.match(r'^1 TITL (.+)', line)
            if mt:
                has_titl = True
                sour_title = mt.group(1).strip()
            elif re.match(r'^1 (AUTH|PUBL|REPO)\b', line):
                has_authority = True
        i += 1

    if in_sour_rec and current_xref:
        if not has_titl:
            no_title.append(current_xref)
        elif not has_authority:
            no_authority.append((current_xref, sour_title))

    # ── Scan source citations for PAGE ───────────────────────────────────────
    cite_re = re.compile(r'^(\d+) SOUR (@[^@]+@)$')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        m = cite_re.match(line)
        if m:
            cite_level = int(m.group(1))
            cite_xref = m.group(2)
            j = i + 1
            has_page = False
            while j < len(lines):
                cl = lines[j].rstrip('\n')
                cm = re.match(r'^(\d+) ([A-Z]+)', cl)
                if cm:
                    if int(cm.group(1)) > cite_level:
                        if cm.group(2) == 'PAGE':
                            has_page = True
                            break
                    else:
                        break
                j += 1
            if not has_page:
                no_page.append((i + 1, cite_xref))
        i += 1

    return {'no_title': no_title, 'no_authority': no_authority, 'no_page': no_page}


# ---------------------------------------------------------------------------
# CONC / CONT validation  (spec 1.5)
# ---------------------------------------------------------------------------

def scan_conc_cont(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, description) for CONC/CONT anomalies:
      - Level is not exactly one greater than the most recent non-CONC/CONT line

    Note: CONC values starting with a leading space are intentional and spec-compliant.
    Per GEDCOM 5.5.5 (pp. 41, 43-44): splitting just before a space so the space
    becomes the first character of the CONC value is the recommended technique to
    preserve word boundaries. Readers must not strip leading white space from line values.
    """
    violations: list[tuple[int, str]] = []
    last_parent_level: int | None = None

    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = re.match(r'^(\d+) (CONC|CONT)(.*)', line)
            if m:
                level = int(m.group(1))
                tag = m.group(2)
                if last_parent_level is not None and level != last_parent_level + 1:
                    violations.append((
                        lineno,
                        f'{tag} at level {level} but parent is at level '
                        f'{last_parent_level} (expected level {last_parent_level + 1})',
                    ))
                # CONC/CONT lines don't update last_parent_level
            else:
                m2 = re.match(r'^(\d+)', line)
                if m2:
                    last_parent_level = int(m2.group(1))

    return violations


def fix_conc_cont_levels(path: str, dry_run: bool = False) -> int:
    """
    Rewrite CONC/CONT lines whose level != last_non_conc_level + 1.

    In GEDCOM 5.5.1, all CONT/CONC for a record must be at record_level + 1.
    A '3 CONC' following '2 CONT' should be '2 CONC' (both belong to the
    level-1 record).  Returns the count of lines corrected.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    last_parent_level: int | None = None

    for raw in lines_in:
        line = raw.rstrip('\n')
        m = re.match(r'^(\d+) (CONC|CONT)(.*)', line)
        if m:
            level = int(m.group(1))
            tag = m.group(2)
            rest = m.group(3)
            if last_parent_level is not None:
                expected = last_parent_level + 1
                if level != expected:
                    changed += 1
                    line = f'{expected} {tag}{rest}'
            lines_out.append(line + '\n')
        else:
            m2 = re.match(r'^(\d+)', line)
            if m2:
                last_parent_level = int(m2.group(1))
            lines_out.append(line + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


def scan_short_conc(path: str, min_len: int = 5) -> list[tuple[int, str, str]]:
    """
    Return (lineno, xref_context, value) for CONC lines whose value is shorter
    than min_len characters.  Very short CONC values (e.g. 1–4 chars) indicate
    that a note was split at the wrong point, usually from a prior editing bug.
    CONT lines are excluded — blank CONT lines (empty paragraphs) are valid.
    """
    results: list[tuple[int, str, str]] = []
    current_xref = ''
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m0 = re.match(r'^0 (@[^@]+@) ', line)
            if m0:
                current_xref = m0.group(1)
            m = re.match(r'^\d+ CONC(?: (.*))?$', line)
            if m:
                val = m.group(1) or ''
                if len(val) < min_len:
                    results.append((lineno, current_xref, val))
    return results


def scan_mid_word_conc(path: str) -> list[tuple[int, str, str]]:
    """
    Return (lineno, xref_context, boundary) for CONC lines in shared NOTE
    records where the join creates a mid-word transition: the preceding value
    ends with an alphabetic character and the CONC value starts with a
    lowercase letter (no leading space).

    This detects splits like ``bapti`` + ``zed`` or ``cah`` + ``ier`` that
    occur when a note was encoded with hard line-length cuts rather than
    word-boundary cuts.  Digit-to-letter transitions (e.g. ``18`` + ``th``)
    and CONC values that start with a space are excluded.
    """
    results: list[tuple[int, str, str]] = []
    current_xref = ''
    prev_tail = ''
    in_shared_note = False
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m0 = re.match(r'^0 (@[^@]+@) NOTE(?: (.*))?$', line)
            if m0:
                current_xref = m0.group(1)
                note_val = m0.group(2) or ''
                prev_tail = note_val[-1:] if note_val else ''
                in_shared_note = True
                continue
            if line.startswith('0 '):
                in_shared_note = False
                prev_tail = ''
                continue
            if not in_shared_note:
                continue
            mc = re.match(r'^\d+ CONC(?: (.*))?$', line)
            if mc:
                val = mc.group(1) or ''
                if prev_tail.isalpha() and val and val[0].islower():
                    results.append((lineno, current_xref, prev_tail + '|' + val[:10]))
                prev_tail = val[-1:] if val else prev_tail
                continue
            mt = re.match(r'^\d+ CONT(?: (.*))?$', line)
            if mt:
                val = mt.group(1) or ''
                prev_tail = val[-1:] if val else ''
    return results


def fix_note_reflow(path: str, dry_run: bool = False, min_len: int = 5) -> int:
    """
    Re-encode shared NOTE records (``0 @xref@ NOTE``) that have bad CONC
    wrapping: a CONC value shorter than *min_len* characters, or a mid-word
    CONC join (preceding value ends with alpha, CONC value starts with a
    lowercase letter without a leading space).

    Notes with CONT lines are handled: empty CONTs are preserved as paragraph
    breaks; non-empty CONTs begin a new paragraph whose text is the CONT value
    followed by any subsequent CONC continuations.

    Returns the number of NOTE records reflowed.
    """
    GEDCOM_MAX = 255

    def _is_mid_word(prev_tail: str, conc_val: str) -> bool:
        return bool(prev_tail and prev_tail.isalpha() and conc_val and conc_val[0].islower())

    def _chunk_paragraph(para: str, first_prefix: str) -> list[str]:
        """Split one paragraph into GEDCOM lines at word boundaries."""
        out: list[str] = []
        prefix = first_prefix
        remaining = para
        while remaining:
            max_val = GEDCOM_MAX - len(prefix) - 1
            if len(remaining) <= max_val:
                out.append(f'{prefix} {remaining}')
                break
            chunk = remaining[:max_val]
            split_pos = chunk.rfind(' ')
            if split_pos <= 0:
                out.append(f'{prefix} {remaining[:max_val]}')
                remaining = remaining[max_val:]
            else:
                out.append(f'{prefix} {remaining[:split_pos]}')
                remaining = remaining[split_pos:]  # leading space goes to next CONC
            prefix = '1 CONC'
        return out

    def _emit_note(xref: str, segments: list[tuple[str, str]]) -> list[str]:
        """Reconstruct logical text and re-emit with proper word-boundary wrapping."""
        # CONC → append to current paragraph; CONT → start a new paragraph
        paragraphs: list[str] = ['']
        for kind, val in segments:
            if kind == 'CONC':
                paragraphs[-1] += val
            else:  # CONT
                paragraphs.append(val)

        out: list[str] = []
        for p_idx, para in enumerate(paragraphs):
            first_prefix = f'0 {xref} NOTE' if p_idx == 0 else '1 CONT'
            if para:
                out.extend(_chunk_paragraph(para, first_prefix))
            else:
                out.append(first_prefix)
        return out

    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    note_re = re.compile(r'^0 (@[^@]+@) NOTE(?: (.*))?$')
    tag_re  = re.compile(r'^(\d+) (CONC|CONT)(?: (.*))?$')

    blocks: list[tuple[int, int, str, list[tuple[str, str]]]] = []
    i = 0
    while i < len(lines_in):
        line = lines_in[i].rstrip('\n')
        m = note_re.match(line)
        if m:
            xref = m.group(1)
            note_val = m.group(2) or ''
            segments: list[tuple[str, str]] = []
            needs_reflow = False
            prev_tail = note_val[-1:] if note_val else ''
            j = i + 1
            while j < len(lines_in):
                nline = lines_in[j].rstrip('\n')
                if nline.startswith('0 '):
                    break
                tm = tag_re.match(nline)
                if tm:
                    tag2, val2 = tm.group(2), (tm.group(3) or '')
                    segments.append((tag2, val2))
                    if tag2 == 'CONC':
                        if len(val2) < min_len or _is_mid_word(prev_tail, val2):
                            needs_reflow = True
                        prev_tail = val2[-1:] if val2 else prev_tail
                    elif tag2 == 'CONT':
                        prev_tail = val2[-1:] if val2 else ''
                j += 1
            if needs_reflow:
                blocks.append((i, j, xref, [('CONC', note_val)] + segments))
        i += 1

    if not blocks:
        return 0

    lines_out = list(lines_in)
    for start, end, xref, segs in reversed(blocks):
        new_block = _emit_note(xref, segs)
        lines_out[start:end] = [l + '\n' for l in new_block]

    if not dry_run:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return len(blocks)


# ---------------------------------------------------------------------------
# Bare @ sign detection  (spec 1.4 — pointer escape rule)
# ---------------------------------------------------------------------------

# A value that is entirely a pointer, e.g. '@I1@' or '@N_SOME_NOTE@'.
_POINTER_VALUE_RE = re.compile(r'^@[^@]+@$')
# Any @…@ sequence embedded in a value (pointer reference or calendar escape
# such as @#DJULIAN@).  These are not bare at-signs.
_AT_SEQ_RE = re.compile(r'@[^@\s]+@')


def scan_bare_at_signs(path: str) -> list[tuple[int, str]]:
    """Return (lineno, description) for line values that contain a bare '@'.

    Per the GEDCOM spec, a literal '@' inside a line value must be written
    as '@@'.  A single '@' that is not part of '@@', not the entire pointer
    value '@XREF@', and not part of an embedded @…@ sequence (e.g. a
    calendar escape like '@#DJULIAN@') is a spec violation that causes
    most parsers to misread the value.

    Common culprit: e-mail addresses written as 'user@example.com' instead
    of 'user@@example.com'.
    """
    violations: list[tuple[int, str]] = []

    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\r\n')
            m = re.match(r'^\d+ (?:@[^@]+@ )?\S+(.*)', line)
            if not m:
                continue
            rest = m.group(1)
            if not rest.startswith(' '):
                continue          # no value on this line
            value = rest[1:]      # strip the single delimiter space

            # Entire value is a pointer reference → fine
            if _POINTER_VALUE_RE.match(value):
                continue

            # Strip escaped at-signs ('@@') and any embedded @…@ sequences
            # (pointer refs embedded in text, calendar escapes, etc.), then
            # check whether any bare '@' remains.
            cleaned = _AT_SEQ_RE.sub('', value.replace('@@', ''))
            if '@' in cleaned:
                violations.append((
                    lineno,
                    f'bare \'@\' in value (should be \'@@\'): {value!r}',
                ))

    return violations


# ---------------------------------------------------------------------------
# Malformed xref detection  (spec 1.3)
# ---------------------------------------------------------------------------

# Level-0 record definition:  0 @XREF@ TAG [value]
_XREF_DEFN_LINE_RE  = re.compile(r'^0 (@[^@]+@) \S+')
# Pointer value (entire value is a pointer):  N TAG @XREF@
_XREF_PTR_LINE_RE   = re.compile(r'^\d+ \S+ (@[^@]+@)\s*$')
# Valid xref content: alphanumeric + underscore only (GEDCOM 5.5.5 is
# alphanumeric-only; we allow underscore for the very common _-prefixed
# convention used throughout the lineage-linked community).
_XREF_INNER_VALID_RE = re.compile(r'^[A-Za-z0-9_]+$')
_XREF_MAX_LEN = 22   # spec maximum including both '@' delimiters


def scan_malformed_xrefs(path: str) -> list[tuple[int, str]]:
    """Return (lineno, description) for xref identifiers that violate spec rules.

    Checks applied to every xref definition (level-0 lines) and every
    pointer value (lines whose entire value is @XREF@):

      1. Length ≤ 22 characters including the '@' delimiters.
      2. No spaces inside the xref.
      3. First character after the opening '@' is alphanumeric or underscore.
         (GEDCOM 5.5.5 restricts to alphanumeric; we also permit '_' for
         the underscore-prefixed naming convention that is ubiquitous in
         real-world files.)

    Multiple violations on the same xref are reported separately so that
    each rule failure is visible.
    """
    violations: list[tuple[int, str]] = []

    def _check(lineno: int, xref: str) -> None:
        inner = xref[1:-1]   # strip opening and closing '@'
        if len(xref) > _XREF_MAX_LEN:
            violations.append((
                lineno,
                f'xref too long ({len(xref)} chars, max {_XREF_MAX_LEN}): {xref!r}',
            ))
        if ' ' in inner:
            violations.append((lineno, f'xref contains a space: {xref!r}'))
        if inner and not re.match(r'^[A-Za-z0-9_]', inner):
            violations.append((
                lineno,
                f'xref starts with invalid character {inner[0]!r}: {xref!r}',
            ))

    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\r\n')
            m = _XREF_DEFN_LINE_RE.match(line)
            if m:
                _check(lineno, m.group(1))
                continue
            m = _XREF_PTR_LINE_RE.match(line)
            if m:
                _check(lineno, m.group(1))

    return violations


# ---------------------------------------------------------------------------
# Nickname extraction  (spec 2.2)
# ---------------------------------------------------------------------------

_NICKNAME_RE = re.compile(r'"([^"]+)"')


def scan_name_nicknames(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, value) for NAME lines that contain a quoted nickname in the
    given-name portion (e.g. 'Adelaide "Edla" /Dellatolla/').
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = NAME_LINE_RE.match(line)
            if not m:
                continue
            val = m.group(3)
            given_part = val[:val.index('/')] if '/' in val else val
            if _NICKNAME_RE.search(given_part):
                violations.append((lineno, val))
    return violations


def fix_nicknames(path: str, dry_run: bool = False) -> int:
    """
    Extract quoted nicknames from NAME values and insert as subordinate NICK tags.

    For each NAME line like '1 NAME Adelaide "Edla" /Dellatolla/':
      1. Remove the quoted nickname (and quotes) from the NAME value.
      2. Insert a '2 NICK Edla' line immediately after the NAME line.
         If a 2 NICK already exists, append the nickname if not already present.

    Returns the number of NAME lines changed.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = list(lines_in)
    changed = 0
    i = 0
    while i < len(lines_out):
        line = lines_out[i].rstrip('\n')
        m = NAME_LINE_RE.match(line)
        if m:
            name_level = int(m.group(2))
            val = m.group(3)
            given_part = val[:val.index('/')] if '/' in val else val
            rest = val[val.index('/'):] if '/' in val else ''
            nick_match = _NICKNAME_RE.search(given_part)
            if nick_match:
                nickname = nick_match.group(1)
                new_given = _NICKNAME_RE.sub('', given_part)
                new_given = re.sub(r'\s{2,}', ' ', new_given).strip()
                new_val = (new_given + (' ' if new_given and rest else '') + rest).strip()
                new_name_line = m.group(1) + new_val

                nick_level = name_level + 1
                nick_prefix = f'{nick_level} NICK'

                # Locate existing NICK child if any
                existing_nick_idx: int | None = None
                j = i + 1
                while j < len(lines_out):
                    cl = lines_out[j].rstrip('\n')
                    cm = re.match(r'^(\d+)', cl)
                    if cm:
                        if int(cm.group(1)) <= name_level:
                            break
                        if cl.startswith(nick_prefix):
                            existing_nick_idx = j
                            break
                    j += 1

                if dry_run:
                    print(f'  line {i + 1}: {val!r}  →  {new_val!r}')
                    if existing_nick_idx is not None:
                        print(f'    append to existing NICK: {nickname!r}')
                    else:
                        print(f'    insert: {nick_prefix} {nickname!r}')
                else:
                    lines_out[i] = new_name_line + '\n'
                    if existing_nick_idx is not None:
                        existing_nick = lines_out[existing_nick_idx].rstrip('\n')
                        existing_val = existing_nick[len(nick_prefix):].strip()
                        if nickname not in existing_val:
                            lines_out[existing_nick_idx] = (
                                f'{nick_prefix} {existing_val}; {nickname}\n'
                            )
                    else:
                        lines_out.insert(i + 1, f'{nick_prefix} {nickname}\n')
                        i += 1
                changed += 1
        i += 1

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# GIVN / SURN name-piece generation  (spec 2.5)
# ---------------------------------------------------------------------------

def scan_name_pieces(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, value) for NAME lines that have no subordinate GIVN or SURN
    tag, but do contain at least one slash (i.e. have a parseable surname block).
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        m = NAME_LINE_RE.match(line)
        if m:
            name_level = int(m.group(2))
            val = m.group(3)
            if '/' not in val:
                i += 1
                continue
            has_givn = False
            has_surn = False
            j = i + 1
            while j < len(lines):
                cl = lines[j].rstrip('\n')
                cm = re.match(r'^(\d+) ([A-Z]+)', cl)
                if cm:
                    if int(cm.group(1)) <= name_level:
                        break
                    if cm.group(2) == 'GIVN':
                        has_givn = True
                    elif cm.group(2) == 'SURN':
                        has_surn = True
                j += 1
            if not has_givn or not has_surn:
                violations.append((i + 1, val))
        i += 1
    return violations


def _parse_name_pieces(val: str) -> tuple[str, str, str]:
    """Parse a GEDCOM NAME value into (given, surname, suffix) using slash convention."""
    if '/' not in val:
        return val.strip(), '', ''
    parts = val.split('/')
    given = parts[0].strip()
    surname = parts[1].strip() if len(parts) >= 2 else ''
    suffix = parts[2].strip() if len(parts) >= 3 else ''
    return given, surname, suffix


def fix_name_pieces(path: str, dry_run: bool = False) -> int:
    """
    Insert missing GIVN/SURN/NSFX subordinate tags for NAME lines that lack them.
    Only processes NAME lines containing at least one slash.
    Does not overwrite existing name pieces.
    Returns the number of NAME lines changed.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = list(lines_in)
    changed = 0
    i = 0
    while i < len(lines_out):
        line = lines_out[i].rstrip('\n')
        m = NAME_LINE_RE.match(line)
        if m:
            name_level = int(m.group(2))
            val = m.group(3)
            if '/' not in val:
                i += 1
                continue

            given, surname, suffix = _parse_name_pieces(val)

            has_givn = False
            has_surn = False
            has_nsfx = False
            insert_after = i
            j = i + 1
            while j < len(lines_out):
                cl = lines_out[j].rstrip('\n')
                cm = re.match(r'^(\d+) ([A-Z]+)', cl)
                if cm:
                    if int(cm.group(1)) <= name_level:
                        break
                    tag = cm.group(2)
                    if tag == 'GIVN':
                        has_givn = True
                    elif tag == 'SURN':
                        has_surn = True
                    elif tag == 'NSFX':
                        has_nsfx = True
                    insert_after = j
                j += 1

            child_level = name_level + 1
            to_insert = []
            if not has_givn and given:
                to_insert.append(f'{child_level} GIVN {given}')
            if not has_surn and surname:
                to_insert.append(f'{child_level} SURN {surname}')
            if not has_nsfx and suffix:
                to_insert.append(f'{child_level} NSFX {suffix}')

            if to_insert:
                changed += 1
                if dry_run:
                    print(f'  line {i + 1}: NAME {val!r}')
                    for piece in to_insert:
                        print(f'    insert: {piece!r}')
                else:
                    for offset, piece in enumerate(to_insert):
                        lines_out.insert(insert_after + 1 + offset, piece + '\n')
                    i += len(to_insert)
        i += 1

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Day-month-only dates → date phrases  (spec 2.6)
# ---------------------------------------------------------------------------

_DATELESS_DATE_RE = re.compile(
    r'^(\d{1,2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$',
    re.IGNORECASE,
)


def scan_dateless_dates(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, value) for DATE lines that have a day+month but no year
    (e.g. '31 Jan' or '13 OCT').
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = re.match(r'^\d+ DATE (.+)$', line)
            if m and _DATELESS_DATE_RE.match(m.group(1).strip()):
                violations.append((lineno, m.group(1).strip()))
    return violations


def fix_dateless_dates(path: str, dry_run: bool = False) -> int:
    """
    Wrap day+month-only DATE values as parenthesised date phrases per the spec.
    '31 Jan' → '(31 JAN, year unknown)'
    Returns the number of lines changed.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')
        m = re.match(r'^(\d+ DATE )(.+)$', line)
        if m:
            val = m.group(2).strip()
            dm = _DATELESS_DATE_RE.match(val)
            if dm:
                fixed = f'({dm.group(1)} {dm.group(2).upper()}, year unknown)'
                changed += 1
                if dry_run:
                    print(f'  line {lineno}: {val!r}  →  {fixed!r}')
                line = m.group(1) + fixed
        lines_out.append(line + '\n')

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Date logical consistency  (spec 1.6)
# ---------------------------------------------------------------------------

def scan_date_consistency(path: str) -> list[str]:
    """
    Return list of human-readable strings for logical date inconsistencies.

    Checks within individuals:
      - Birth year should precede death year
      - Christening/baptism year should be on or after birth year
      - Burial year should be on or after death year

    Checks within families:
      - Marriage year should be after both spouses' birth years (if known)
      - Children's birth years should be after parents' birth years

    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    gf = parse_gedcom(path)
    issues: list[str] = []

    def _year(date_obj) -> int | None:
        return date_obj.year if date_obj and getattr(date_obj, 'year', None) else None

    for xref, ind in gf.individuals.items():
        birth_year = death_year = chr_year = buri_year = None
        for ev in ind.events:
            y = _year(ev.date)
            if not y:
                continue
            if ev.tag == 'BIRT':
                birth_year = y
            elif ev.tag == 'DEAT':
                death_year = y
            elif ev.tag in ('CHR', 'BAPM'):
                chr_year = y
            elif ev.tag == 'BURI':
                buri_year = y

        if birth_year and death_year and birth_year > death_year:
            issues.append(f'{xref}: birth year {birth_year} is after death year {death_year}')
        if birth_year and chr_year and chr_year < birth_year:
            issues.append(f'{xref}: christening/baptism year {chr_year} is before birth year {birth_year}')
        if death_year and buri_year and buri_year < death_year:
            issues.append(f'{xref}: burial year {buri_year} is before death year {death_year}')

    for fam_xref, fam in gf.families.items():
        marr_year = None
        for ev in fam.events:
            y = _year(ev.date)
            if ev.tag == 'MARR' and y:
                marr_year = y
                break

        husb = gf.individuals.get(fam.husband_xref) if fam.husband_xref else None
        wife = gf.individuals.get(fam.wife_xref) if fam.wife_xref else None

        for spouse, label in [(husb, 'husband'), (wife, 'wife')]:
            if not spouse:
                continue
            spouse_birth = None
            for ev in spouse.events:
                y = _year(ev.date)
                if ev.tag == 'BIRT' and y:
                    spouse_birth = y
                    break
            if marr_year and spouse_birth and marr_year < spouse_birth:
                issues.append(
                    f'{fam_xref}: marriage year {marr_year} is before '
                    f'{label} ({spouse.xref}) birth year {spouse_birth}'
                )

        for child_xref in fam.child_xrefs:
            child = gf.individuals.get(child_xref)
            if not child:
                continue
            child_birth = None
            for ev in child.events:
                y = _year(ev.date)
                if ev.tag == 'BIRT' and y:
                    child_birth = y
                    break
            if not child_birth:
                continue
            for parent, label in [(husb, 'father'), (wife, 'mother')]:
                if not parent:
                    continue
                parent_birth = parent_death = None
                for ev in parent.events:
                    y = _year(ev.date)
                    if ev.tag == 'BIRT' and y:
                        parent_birth = y
                    elif ev.tag == 'DEAT' and y:
                        parent_death = y
                if parent_birth and child_birth <= parent_birth:
                    issues.append(
                        f'{child_xref}: birth year {child_birth} is not after '
                        f'{label} ({parent.xref}) birth year {parent_birth}'
                    )
                if parent_death and child_birth > parent_death + 1:
                    issues.append(
                        f'{child_xref}: birth year {child_birth} is after '
                        f'{label} ({parent.xref}) death year {parent_death}'
                    )

    return issues


# ---------------------------------------------------------------------------
# Estimated birth date from baptism/christening  (data quality enrichment)
# ---------------------------------------------------------------------------

def scan_bapm_without_birth(path: str) -> list[tuple[str, int, int]]:
    """
    Find INDI records that have a BAPM or CHR event with a DATE but lack any
    BIRT event with a DATE.

    Returns a list of (xref, bapm_lineno, year) tuples where:
      xref        : individual cross-reference (e.g. '@I42@')
      bapm_lineno : 1-based line number of the BAPM/CHR DATE line
      year        : four-digit year extracted from the baptism date
    """
    results: list[tuple[str, int, int]] = []

    current_xref: str | None = None
    birt_has_date = False
    bapm_year: int | None = None
    bapm_lineno: int | None = None
    current_event: str | None = None

    def _flush():
        if current_xref and bapm_year and not birt_has_date:
            results.append((current_xref, bapm_lineno, bapm_year))

    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')

            # Level-0 records
            m0 = re.match(r'^0 (@\S+@) INDI\s*$', line)
            if m0:
                _flush()
                current_xref = m0.group(1)
                birt_has_date = False
                bapm_year = None
                bapm_lineno = None
                current_event = None
                continue

            if re.match(r'^0 ', line):
                _flush()
                current_xref = None
                birt_has_date = False
                bapm_year = None
                bapm_lineno = None
                current_event = None
                continue

            if current_xref is None:
                continue

            # Level-1 events
            m1 = re.match(r'^1 ([A-Z]+)', line)
            if m1:
                tag = m1.group(1)
                if tag == 'BIRT':
                    current_event = 'BIRT'
                elif tag in ('BAPM', 'CHR'):
                    current_event = 'BAPM'
                else:
                    current_event = None
                continue

            # Level-2 DATE under current event
            m2 = re.match(r'^2 DATE (.+)$', line)
            if m2 and current_event:
                val = m2.group(1).strip()
                if current_event == 'BIRT' and val:
                    birt_has_date = True
                elif current_event == 'BAPM' and bapm_year is None:
                    ym = re.search(r'\b(\d{4})\b', val)
                    if ym:
                        bapm_year = int(ym.group(1))
                        bapm_lineno = lineno

    _flush()
    return results


def fix_bapm_without_birth(path: str, dry_run: bool = False) -> int:
    """
    For each INDI that has a BAPM/CHR DATE but no BIRT DATE, insert an
    estimated birth event immediately after the INDI header line::

        1 BIRT
        2 DATE EST <year>

    If the individual already has a bare ``1 BIRT`` (no DATE child), the
    ``2 DATE EST <year>`` line is inserted after that existing ``1 BIRT``
    instead of creating a duplicate event block.

    Returns the number of individuals updated.
    """
    candidates = scan_bapm_without_birth(path)
    if not candidates:
        return 0

    # Build a set of xrefs that need fixing for quick lookup
    fix_map: dict[str, int] = {xref: year for xref, _ln, year in candidates}

    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    # Each entry: (insert_after_index, new_lines, description)
    # insert_after_index is 0-based; new lines are inserted *after* that index.
    changes: list[tuple[int, list[str], str]] = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        m0 = re.match(r'^0 (@\S+@) INDI\s*$', line)
        if m0:
            xref = m0.group(1)
            if xref in fix_map:
                year = fix_map[xref]
                indi_start = i
                # Scan the INDI block to find the end and any existing BIRT
                birt_idx: int | None = None
                j = i + 1
                while j < len(lines):
                    cl = lines[j].rstrip('\n')
                    if re.match(r'^0 ', cl):
                        break
                    if re.match(r'^1 BIRT\b', cl):
                        birt_idx = j
                    j += 1

                if birt_idx is not None:
                    # Existing BIRT with no DATE: add DATE after the 1 BIRT line
                    desc = f'{xref}: insert 2 DATE EST {year} into existing BIRT'
                    changes.append((birt_idx, [f'2 DATE EST {year}\n'], desc))
                else:
                    # No BIRT at all: insert full block after the INDI header
                    desc = f'{xref}: insert 1 BIRT / 2 DATE EST {year}'
                    changes.append((indi_start, ['1 BIRT\n', f'2 DATE EST {year}\n'], desc))
        i += 1

    if not changes:
        return 0

    if dry_run:
        for _idx, new_lines, desc in sorted(changes, key=lambda c: c[0]):
            print(f'  {desc}')
            for nl in new_lines:
                print(f'    + {nl.rstrip()}')
        return len(changes)

    # Apply in reverse order so earlier indices stay valid
    for insert_after, new_lines, _desc in sorted(changes, key=lambda c: c[0], reverse=True):
        lines[insert_after + 1:insert_after + 1] = new_lines

    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    os.replace(tmp, path)

    return len(changes)


# ---------------------------------------------------------------------------
# Bidirectional pointer consistency  (spec 1.13)
# ---------------------------------------------------------------------------

def scan_bidirectional_pointers(path: str) -> list[str]:
    """
    Return error strings for family–individual pointer reciprocity issues.

    Unlike scan_broken_xrefs (which checks that referenced records exist),
    this checks that every pointer is mirrored in the other direction:
      - FAM HUSB/WIFE → INDI must have FAMS back to that FAM
      - FAM CHIL → INDI must have FAMC back to that FAM
      - INDI FAMS → FAM must list that INDI as HUSB or WIFE
      - INDI FAMC → FAM must list that INDI as CHIL

    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    gf = parse_gedcom(path)
    issues: list[str] = []

    for fam_xref, fam in gf.families.items():
        for spouse_xref in filter(None, [fam.husband_xref, fam.wife_xref]):
            ind = gf.individuals.get(spouse_xref)
            if ind and fam_xref not in ind.family_spouse:
                issues.append(
                    f'FAM {fam_xref} lists {spouse_xref} as spouse, '
                    f'but INDI {spouse_xref} has no FAMS @{fam_xref}@'
                )
        for child_xref in fam.child_xrefs:
            ind = gf.individuals.get(child_xref)
            if ind and fam_xref not in ind.family_child:
                issues.append(
                    f'FAM {fam_xref} lists {child_xref} as child, '
                    f'but INDI {child_xref} has no FAMC @{fam_xref}@'
                )

    for ind_xref, ind in gf.individuals.items():
        for fam_xref in ind.family_spouse:
            fam = gf.families.get(fam_xref)
            if fam and ind_xref not in filter(None, [fam.husband_xref, fam.wife_xref]):
                issues.append(
                    f'INDI {ind_xref} has FAMS @{fam_xref}@, '
                    f'but FAM {fam_xref} does not list them as HUSB or WIFE'
                )
        for fam_xref in ind.family_child:
            fam = gf.families.get(fam_xref)
            if fam and ind_xref not in fam.child_xrefs:
                issues.append(
                    f'INDI {ind_xref} has FAMC @{fam_xref}@, '
                    f'but FAM {fam_xref} does not list them as CHIL'
                )

    return issues


# ---------------------------------------------------------------------------
# Duplicate RESI consolidation  (spec 2.4)
# ---------------------------------------------------------------------------

def scan_duplicate_resi(path: str) -> list[tuple[str, str, str]]:
    """
    Return (xref, date_str, place_str) for individuals with more than one RESI
    event sharing the same date and place.
    Requires the gedcom_merge parser.
    """
    from gedcom_merge.parser import parse_gedcom
    gf = parse_gedcom(path)
    issues: list[tuple[str, str, str]] = []

    for xref, ind in gf.individuals.items():
        resi_events = [ev for ev in ind.events if ev.tag == 'RESI']
        seen: set[tuple[str, str]] = set()
        for ev in resi_events:
            date_str = str(ev.date) if ev.date else ''
            place_str = ev.place or ''
            key = (date_str, place_str)
            if key in seen:
                issues.append((xref, date_str, place_str))
            else:
                seen.add(key)

    return issues


def fix_bare_events(path: str, dry_run: bool = False) -> int:
    """
    Append 'Y' to bare level-1 BIRT/CHR/DEAT lines that have no value and no
    children, converting e.g. '1 BIRT' → '1 BIRT Y'.

    GEDCOM 5.5.1 requires 'Y' on a bare event tag to assert the event occurred
    with no further details available.
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    out = []
    count = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip('\n')
        m = re.match(r'^1 ([A-Z]+)$', stripped)
        if m and m.group(1) in _BARE_EVENT_TAGS:
            # Check for children
            j = i + 1
            has_children = False
            while j < len(lines):
                cl = lines[j].rstrip('\n')
                cm = re.match(r'^(\d+)', cl)
                if cm:
                    if int(cm.group(1)) >= 2:
                        has_children = True
                    break
                j += 1
            if not has_children:
                eol = '\n' if line.endswith('\n') else ''
                out.append(f'1 {m.group(1)} Y{eol}')
                count += 1
                i += 1
                continue
        out.append(line)
        i += 1

    if count and not dry_run:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(out)
    return count


def fix_duplicate_resi(path: str, dry_run: bool = False) -> int:
    """
    Remove duplicate RESI events (same date and place) from individual records,
    merging their unique source citations into the surviving event.
    Returns the number of duplicate RESI events removed.
    Requires the gedcom_merge parser/writer.
    """
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.writer import write_gedcom
    gf = parse_gedcom(path)

    removed = 0
    for ind in gf.individuals.values():
        resi_keep: dict[tuple[str, str], object] = {}
        keep_events = []

        for ev in ind.events:
            if ev.tag != 'RESI':
                keep_events.append(ev)
                continue
            date_str = str(ev.date) if ev.date else ''
            place_str = ev.place or ''
            key = (date_str, place_str)
            if key not in resi_keep:
                resi_keep[key] = ev
                keep_events.append(ev)
            else:
                primary = resi_keep[key]
                existing_keys = {
                    (c.source_xref, c.page) for c in primary.citations
                }
                for cit in ev.citations:
                    ck = (cit.source_xref, cit.page)
                    if ck not in existing_keys:
                        primary.citations.append(cit)
                        existing_keys.add(ck)
                removed += 1
                if dry_run:
                    print(
                        f'  {ind.xref}: duplicate RESI '
                        f'date={date_str!r} place={place_str!r}'
                    )

        if removed:
            ind.events = keep_events

    if removed and not dry_run:
        write_gedcom(gf, path)

    return removed


# ---------------------------------------------------------------------------
# FACT AKA → proper NAME tag  (spec 2.3)
# ---------------------------------------------------------------------------

def scan_fact_aka(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, note_value) for FACT blocks that have both a TYPE AKA
    and a NOTE child — these should be converted to proper NAME records.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        if re.match(r'^1 FACT\b', line):
            has_aka = False
            note_val: str | None = None
            j = i + 1
            while j < len(lines):
                cl = lines[j].rstrip('\n')
                cm = re.match(r'^(\d+) ([A-Z]+)(.*)', cl)
                if cm:
                    if int(cm.group(1)) <= 1:
                        break
                    if cm.group(2) == 'TYPE' and cm.group(3).strip().upper() == 'AKA':
                        has_aka = True
                    elif cm.group(2) == 'NOTE':
                        note_val = cm.group(3).strip()
                j += 1
            if has_aka and note_val:
                violations.append((i + 1, note_val))
        i += 1
    return violations


def fix_aka_facts(path: str, dry_run: bool = False) -> int:
    """
    Convert FACT / TYPE AKA / NOTE <name> blocks to proper NAME records.

    Heuristic: the last whitespace-separated word in the NOTE value is treated
    as the surname (wrapped in slashes). Single-word values are wrapped as a
    pure surname. The resulting record is:

        1 NAME <given> /<surname>/
        2 TYPE aka

    Returns the number of blocks converted.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = list(lines_in)
    changed = 0
    i = 0
    while i < len(lines_out):
        line = lines_out[i].rstrip('\n')
        if re.match(r'^1 FACT\b', line):
            has_aka = False
            note_val: str | None = None
            block_end = i + 1
            j = i + 1
            while j < len(lines_out):
                cl = lines_out[j].rstrip('\n')
                cm = re.match(r'^(\d+) ([A-Z]+)(.*)', cl)
                if cm:
                    if int(cm.group(1)) <= 1:
                        break
                    if cm.group(2) == 'TYPE' and cm.group(3).strip().upper() == 'AKA':
                        has_aka = True
                    elif cm.group(2) == 'NOTE':
                        note_val = cm.group(3).strip()
                    block_end = j + 1
                j += 1

            if has_aka and note_val:
                words = note_val.split()
                if len(words) == 1:
                    name_val = f'/{words[0]}/'
                else:
                    surname = words[-1]
                    given = ' '.join(words[:-1])
                    name_val = f'{given} /{surname}/'

                new_name_line = f'1 NAME {name_val}'
                new_type_line = '2 TYPE aka'

                if dry_run:
                    print(f'  line {i + 1}: FACT/AKA/NOTE {note_val!r}')
                    print(f'    → {new_name_line!r}')
                    print(f'    → {new_type_line!r}')
                else:
                    del lines_out[i:block_end]
                    lines_out.insert(i, new_type_line + '\n')
                    lines_out.insert(i, new_name_line + '\n')

                changed += 1
                if not dry_run:
                    i += 2
                    continue
        i += 1

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Place consistency report  (spec 1.12)
# ---------------------------------------------------------------------------

def _normalize_place_str(val: str) -> str:
    """Lowercase, strip diacritics, collapse whitespace."""
    nfkd = unicodedata.normalize('NFKD', val.lower())
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', stripped).strip()


def _levenshtein(a: str, b: str) -> int:
    """Compute the Levenshtein edit distance between two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


_COUNTRY_ALIASES: dict[str, str] = {
    'usa': 'united states',
    'u.s.a.': 'united states',
    'united states of america': 'united states',
    'england': 'united kingdom',
    'great britain': 'united kingdom',
    'scotland': 'united kingdom',
    'wales': 'united kingdom',
}


def scan_place_consistency(path: str) -> dict:
    """
    Return a summary of potential place-name inconsistencies:

      'similar_places'          : list of (plac_a, plac_b) pairs that likely
                                  refer to the same location but are spelled
                                  differently (city-level Levenshtein ≤ 2 within
                                  the same region/country group)
      'country_inconsistencies' : list of (raw_a, raw_b) country-name pairs
                                  that normalise to the same canonical country
                                  but are spelled/abbreviated differently
                                  (e.g. 'USA' vs 'United States')
      'bare_countries'          : list of PLAC values with no comma (likely
                                  just a country name with no subdivision)
    """
    plac_values: list[str] = []
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            m = PLAC_RE.match(line)
            if m:
                plac_values.append(m.group(2).strip())

    bare_countries = [v for v in plac_values if ',' not in v]

    # Group by normalised (country, region) key
    by_region: dict[tuple[str, str], list[str]] = defaultdict(list)
    for val in plac_values:
        parts = [p.strip() for p in val.split(',')]
        if len(parts) >= 2:
            country_key = _normalize_place_str(parts[-1])
            region_key = _normalize_place_str(parts[-2]) if len(parts) >= 2 else ''
            by_region[(country_key, region_key)].append(val)

    similar_places: list[tuple[str, str]] = []
    for _region, vals in by_region.items():
        unique_vals = list(dict.fromkeys(vals))
        for j in range(len(unique_vals)):
            for k in range(j + 1, len(unique_vals)):
                a, b = unique_vals[j], unique_vals[k]
                city_a = _normalize_place_str(a.split(',')[0])
                city_b = _normalize_place_str(b.split(',')[0])
                if city_a == city_b:
                    continue
                if (city_a in city_b or city_b in city_a or
                        _levenshtein(city_a, city_b) <= 2):
                    similar_places.append((a, b))

    # Detect country-name inconsistencies
    country_groups: dict[str, set[str]] = defaultdict(set)
    for val in plac_values:
        parts = [p.strip() for p in val.split(',')]
        if parts:
            raw_country = parts[-1].strip()
            norm = _normalize_place_str(raw_country)
            canonical = _COUNTRY_ALIASES.get(norm, norm)
            country_groups[canonical].add(raw_country)

    country_inconsistencies: list[tuple[str, str]] = []
    for _canonical, raw_set in country_groups.items():
        raw_list = sorted(raw_set)
        if len(raw_list) > 1:
            for j in range(len(raw_list)):
                for k in range(j + 1, len(raw_list)):
                    country_inconsistencies.append((raw_list[j], raw_list[k]))

    return {
        'similar_places': similar_places,
        'country_inconsistencies': country_inconsistencies,
        'bare_countries': bare_countries,
    }


# ---------------------------------------------------------------------------
# Same-source multiple-citation check  (spec 3.2 — "potential duplicates")
# ---------------------------------------------------------------------------

def scan_same_sour_multiple_cites(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, xref) for source citations that reference the same @SOUR@
    more than once on the same individual/event, even when their child lines
    differ (e.g. one has a PAGE, one doesn't).

    These are 'potential duplicates' and are reported separately from the
    exact-duplicate blocks detected by scan_duplicate_sources().
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    violations: list[tuple[int, str]] = []
    current_rec: str | None = None
    current_event: int | None = None
    seen: dict[tuple[str | None, int | None], dict[str, int]] = {}

    defn_re = re.compile(r'^0 ')
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        if defn_re.match(line):
            current_rec = line
            current_event = None
            seen = {}
            i += 1
            continue
        if line.startswith('1 '):
            current_event = i
            i += 1
            continue
        m = SOUR_CITE_LINE_RE.match(line)
        if m and current_rec is not None:
            xref = m.group(2)
            key = (current_rec, current_event)
            if key not in seen:
                seen[key] = {}
            if xref in seen[key]:
                violations.append((i + 1, xref))
            else:
                seen[key][xref] = i
        i += 1

    return violations


# ---------------------------------------------------------------------------
# NAME sub-tag ordering  (GIVN/SURN/NSFX before TYPE before everything else)
# ---------------------------------------------------------------------------

# Tags that are "name pieces" and must appear before TYPE in a NAME block.
_NAME_PIECE_TAGS = {'GIVN', 'SURN', 'NSFX', 'NPFX'}


def _name_child_chunks(lines: list[str], start: int, name_level: int):
    """
    Yield (tag, chunk_lines) for each immediate child block of the NAME line
    at index *start*.  Each chunk includes the child line plus any deeper
    descendants that belong to it.
    """
    child_level = name_level + 1
    i = start + 1
    while i < len(lines):
        m = re.match(r'^(\d+)\s+(\S+)', lines[i])
        if not m:
            i += 1
            continue
        level = int(m.group(1))
        if level < child_level:
            break
        if level == child_level:
            tag = m.group(2)
            chunk = [lines[i]]
            j = i + 1
            while j < len(lines):
                dm = re.match(r'^(\d+)', lines[j])
                if dm and int(dm.group(1)) <= child_level:
                    break
                chunk.append(lines[j])
                j += 1
            yield tag, chunk, i          # tag, lines, start-index in `lines`
            i = j
        else:
            i += 1


def _name_piece_sort_key(tag: str) -> int:
    """0 = name piece (GIVN/SURN/NSFX/NPFX), 1 = TYPE, 2 = everything else."""
    if tag in _NAME_PIECE_TAGS:
        return 0
    if tag == 'TYPE':
        return 1
    return 2


def scan_citation_data_children(path: str) -> list[tuple[int, str, str]]:
    """
    Return (lineno, invalid_tag, sour_xref) for tags that appear as direct
    children of the DATA block inside an inline SOURCE_CITATION but are not
    permitted by GEDCOM 5.5.1.

    The only valid direct children of SOUR.DATA in a citation are:
      DATE, TEXT, CONC, CONT

    Any other tag (e.g. WWW, NOTE, SOUR, PLAC) at that level is flagged.
    Level-0 SOUR records with their own DATA blocks are excluded.
    """
    _VALID = frozenset({'DATE', 'TEXT', 'CONC', 'CONT'})
    violations: list[tuple[int, str, str]] = []

    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        # Inline SOUR citation: level >= 1 with an @XREF@ pointer
        m = re.match(r'^(\d+) SOUR (@[^@]+@)', lines[i].rstrip('\n'))
        if not m or int(m.group(1)) < 1:
            i += 1
            continue

        sour_level = int(m.group(1))
        sour_xref = m.group(2)

        # Scan children of the SOUR citation for a DATA block
        j = i + 1
        while j < len(lines):
            lm = re.match(r'^(\d+)', lines[j])
            if not lm:
                j += 1
                continue
            child_level = int(lm.group(1))
            if child_level <= sour_level:
                break  # end of citation

            if child_level == sour_level + 1:
                dm = re.match(r'^\d+ DATA\s*$', lines[j].rstrip('\n'))
                if dm:
                    # Now check DATA's direct children
                    data_level = sour_level + 1
                    k = j + 1
                    while k < len(lines):
                        klm = re.match(r'^(\d+) (\w+)', lines[k])
                        if not klm:
                            k += 1
                            continue
                        if int(klm.group(1)) <= data_level:
                            break  # end of DATA block
                        if int(klm.group(1)) == data_level + 1:
                            tag = klm.group(2)
                            if tag not in _VALID:
                                violations.append((k + 1, tag, sour_xref))
                        k += 1
                    j = k
                    continue
            j += 1

        i += 1

    return violations


def scan_name_piece_order(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, name_value) for NAME records where TYPE appears before
    any of GIVN, SURN, NSFX, or NPFX in the subordinate tags.

    Desired order: GIVN/SURN/NSFX/NPFX → TYPE → everything else.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        m = NAME_LINE_RE.match(lines[i].rstrip('\n'))
        if m:
            name_level = int(m.group(2))
            name_val = m.group(3)
            name_lineno = i + 1
            seen_type = False
            flagged = False
            for tag, _chunk, _idx in _name_child_chunks(lines, i, name_level):
                if tag == 'TYPE':
                    seen_type = True
                elif tag in _NAME_PIECE_TAGS and seen_type:
                    flagged = True
                    break
            if flagged:
                violations.append((name_lineno, name_val))
        i += 1

    return violations


def fix_name_piece_order(path: str, dry_run: bool = False) -> int:
    """
    Reorder sub-tags within each NAME block so GIVN/SURN/NSFX/NPFX come
    first, then TYPE, then everything else (preserving relative order within
    each group).  Returns the count of NAME blocks that were reordered.
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    out = list(lines)
    changed = 0
    i = 0

    while i < len(out):
        m = NAME_LINE_RE.match(out[i].rstrip('\n'))
        if not m:
            i += 1
            continue

        name_level = int(m.group(2))
        chunks = list(_name_child_chunks(out, i, name_level))

        if not chunks:
            i += 1
            continue

        # Stable sort: group 0 (name pieces) → 1 (TYPE) → 2 (other)
        sorted_chunks = sorted(chunks, key=lambda c: _name_piece_sort_key(c[0]))

        original_tags = [c[0] for c in chunks]
        sorted_tags   = [c[0] for c in sorted_chunks]

        if original_tags != sorted_tags:
            changed += 1
            if not dry_run:
                # Splice the reordered lines back in place
                start = chunks[0][2]                          # line index of first child
                end   = chunks[-1][2] + len(chunks[-1][1])   # line index after last child
                new_block = [line for _, chunk_lines, _ in sorted_chunks
                             for line in chunk_lines]
                out[start:end] = new_block
                # Adjust i: the NAME line index hasn't changed
        i += 1

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Event source/note ordering
# ---------------------------------------------------------------------------

_ALL_GEDCOM_EVENT_TAGS = frozenset({
    # Individual events
    'BIRT', 'CHR', 'DEAT', 'BURI', 'CREM', 'ADOP', 'BAPM', 'BARM', 'BASM',
    'BLES', 'CHRA', 'CONF', 'FCOM', 'ORDN', 'NATU', 'EMIG', 'IMMI', 'CENS',
    'PROB', 'WILL', 'GRAD', 'RETI', 'EVEN',
    # Individual attributes
    'CAST', 'DSCR', 'EDUC', 'IDNO', 'NATI', 'NCHI', 'NMR', 'OCCU', 'PROP',
    'RELI', 'RESI', 'SSN', 'TITL', 'FACT',
    # Family events/attributes
    'ANUL', 'DIV', 'DIVF', 'ENGA', 'MARB', 'MARC', 'MARL', 'MARR', 'MARS',
})


def _event_child_sort_key(tag: str) -> int:
    """0 = other details (DATE/PLAC/ADDR/etc.), 1 = SOUR, 2 = NOTE."""
    if tag == 'NOTE':
        return 2
    if tag == 'SOUR':
        return 1
    return 0


def scan_event_source_order(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, tag) for event blocks where SOUR or NOTE appears before
    other sub-tags (DATE, PLAC, ADDR, etc.), or NOTE appears before SOUR.

    Desired order within any event: other details → SOUR → NOTE.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        m = re.match(r'^(\d+)\s+(\S+)', lines[i].rstrip('\n'))
        if m and int(m.group(1)) == 1 and m.group(2) in _ALL_GEDCOM_EVENT_TAGS:
            tag = m.group(2)
            chunks = list(_name_child_chunks(lines, i, 1))
            if chunks:
                original_tags = [c[0] for c in chunks]
                sorted_tags   = [c[0] for c in
                                  sorted(chunks, key=lambda c: _event_child_sort_key(c[0]))]
                if original_tags != sorted_tags:
                    violations.append((i + 1, tag))
        i += 1

    return violations


def fix_event_source_order(path: str, dry_run: bool = False) -> int:
    """
    Stable-sort sub-tags within each event block: other details first, then
    SOUR (with all PAGE/DATA children), then NOTE last.
    Returns the count of event blocks that were reordered.
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    out = list(lines)
    changed = 0
    i = 0

    while i < len(out):
        m = re.match(r'^(\d+)\s+(\S+)', out[i].rstrip('\n'))
        if m and int(m.group(1)) == 1 and m.group(2) in _ALL_GEDCOM_EVENT_TAGS:
            chunks = list(_name_child_chunks(out, i, 1))
            if chunks:
                sorted_chunks = sorted(chunks, key=lambda c: _event_child_sort_key(c[0]))
                original_tags = [c[0] for c in chunks]
                sorted_tags   = [c[0] for c in sorted_chunks]
                if original_tags != sorted_tags:
                    changed += 1
                    if not dry_run:
                        start = chunks[0][2]
                        end   = chunks[-1][2] + len(chunks[-1][1])
                        new_block = [line for _, chunk_lines, _ in sorted_chunks
                                     for line in chunk_lines]
                        out[start:end] = new_block
        i += 1

    if not dry_run and changed:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(out)
        os.replace(tmp, path)

    return changed


# ---------------------------------------------------------------------------
# Citation quality: redundant PAGE and repeated TEXT
# ---------------------------------------------------------------------------

def _build_source_titles(lines: list[str]) -> dict[str, str]:
    """Return {xref: normalized_titl} parsed from level-0 SOUR records."""
    sources: dict[str, str] = {}
    current: str | None = None
    for line in lines:
        stripped = line.rstrip('\n')
        m0 = re.match(r'^0\s+(@[^@]+@)\s+SOUR', stripped)
        if m0:
            current = m0.group(1)
            continue
        if stripped.startswith('0 '):
            current = None
            continue
        if current:
            m1 = re.match(r'^1\s+TITL\s+(.*)', stripped)
            if m1:
                sources[current] = m1.group(1).strip().lower()
    return sources


def _collect_sour_text_blocks(lines: list[str], source_titles: dict[str, str]):
    """
    Yield (xref, text_key, text_start_idx, text_end_idx_exclusive, sour_level)
    for each inline SOUR citation that contains a TEXT block nested inside its
    DATA sub-block.

    text_key is a tuple of ('TEXT'/'CONT'/'CONC', value) tuples representing
    the full text content for deduplication.
    """
    i = 0
    while i < len(lines):
        m = re.match(r'^(\d+)\s+SOUR\s+(@[^@]+@)', lines[i].rstrip('\n'))
        if m and int(m.group(1)) >= 1 and m.group(2) in source_titles:
            sour_level = int(m.group(1))
            xref = m.group(2)
            text_level = sour_level + 2   # TEXT is inside DATA (sour+1), so sour+2
            cont_level = sour_level + 3

            j = i + 1
            while j < len(lines):
                child = lines[j].rstrip('\n')
                cm = re.match(r'^(\d+)', child)
                if not cm:
                    j += 1
                    continue
                cl = int(cm.group(1))
                if cl <= sour_level:
                    break                 # Left the SOUR block

                tm = re.match(r'^(\d+)\s+TEXT\s*(.*)', child)
                if tm and int(tm.group(1)) == text_level:
                    text_start = j
                    parts: list[tuple[str, str]] = [('TEXT', tm.group(2))]

                    k = j + 1
                    while k < len(lines):
                        cont = lines[k].rstrip('\n')
                        ccm = re.match(r'^(\d+)\s+(CONT|CONC)\s*(.*)', cont)
                        if ccm and int(ccm.group(1)) == cont_level:
                            parts.append((ccm.group(2), ccm.group(3)))
                            k += 1
                        else:
                            dm = re.match(r'^(\d+)', cont)
                            if dm and int(dm.group(1)) > cont_level:
                                k += 1
                                continue
                            break

                    yield (xref, tuple(parts), text_start, k, sour_level)
                    j = k
                    continue
                j += 1
            i = j
            continue
        i += 1


def _norm_page_titl(s: str) -> str:
    """Lowercase, strip whitespace, and remove a trailing 's' for plural normalisation."""
    s = s.lower().strip()
    if s.endswith('s'):
        s = s[:-1]
    return s


def scan_redundant_citation_page(path: str) -> list[tuple[int, str, str]]:
    """
    Return (lineno, source_xref, page_value) for inline SOUR citations where the
    PAGE value matches the cited source's TITL (case-insensitive, singular/plural
    normalised).

    These PAGE lines add no information and should be removed.
    """
    violations: list[tuple[int, str, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    source_titles = _build_source_titles(lines)

    i = 0
    while i < len(lines):
        m = re.match(r'^(\d+)\s+SOUR\s+(@[^@]+@)', lines[i].rstrip('\n'))
        if m and int(m.group(1)) >= 1 and m.group(2) in source_titles:
            sour_level = int(m.group(1))
            xref = m.group(2)
            norm_titl = _norm_page_titl(source_titles[xref])

            # Scan immediate children of SOUR for PAGE
            for tag, chunk, idx in _name_child_chunks(lines, i, sour_level):
                if tag == 'PAGE':
                    pm = re.match(r'^\d+\s+PAGE\s+(.*)', chunk[0].rstrip('\n'))
                    if pm:
                        page_val = pm.group(1).strip()
                        if _norm_page_titl(page_val) == norm_titl:
                            violations.append((idx + 1, xref, page_val))
        i += 1

    return violations


def fix_redundant_citation_page(path: str, dry_run: bool = False) -> int:
    """
    Remove PAGE lines from inline SOUR citations where the PAGE value equals
    the source's own TITL (i.e., adds no information).
    Returns the number of PAGE lines removed.
    """
    violations = scan_redundant_citation_page(path)
    if not violations:
        return 0

    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    # Collect line indices to remove (0-based).  PAGE children (CONT/CONC) are
    # collected too, though in practice citation PAGE values are single-line.
    remove_indices: set[int] = set()
    for lineno, xref, page_val in violations:
        idx = lineno - 1
        remove_indices.add(idx)
        # Remove any continuation lines that belong to this PAGE
        m = re.match(r'^(\d+)', lines[idx])
        if m:
            page_level = int(m.group(1))
            j = idx + 1
            while j < len(lines):
                dm = re.match(r'^(\d+)', lines[j])
                if dm:
                    if int(dm.group(1)) <= page_level:
                        break
                    remove_indices.add(j)
                j += 1

    if not dry_run:
        out = [line for i, line in enumerate(lines) if i not in remove_indices]
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(out)
        os.replace(tmp, path)

    return len(violations)


def fix_repeated_citation_text(path: str, dry_run: bool = False) -> int:
    # Retired: identical TEXT across citations doesn't mean it belongs at
    # the source level — it's usually citation-specific context (person,
    # voyage, document excerpt) that happens to be repeated for related
    # events on the same individual.
    return 0


# ---------------------------------------------------------------------------
# Curly-quote normalisation
# ---------------------------------------------------------------------------

# Typographic/curly quote characters to replace with their straight equivalents.
_CURLY_QUOTE_MAP = {
    '\u2018': "'",  # LEFT SINGLE QUOTATION MARK  '
    '\u2019': "'",  # RIGHT SINGLE QUOTATION MARK '
    '\u201a': "'",  # SINGLE LOW-9 QUOTATION MARK ‚
    '\u201b': "'",  # SINGLE HIGH-REVERSED-9      ‛
    '\u201c': '"',  # LEFT DOUBLE QUOTATION MARK  "
    '\u201d': '"',  # RIGHT DOUBLE QUOTATION MARK "
    '\u201e': '"',  # DOUBLE LOW-9 QUOTATION MARK „
    '\u201f': '"',  # DOUBLE HIGH-REVERSED-9      ‟
    '\u2039': "'",  # SINGLE LEFT-POINTING ANGLE  ‹
    '\u203a': "'",  # SINGLE RIGHT-POINTING ANGLE ›
    '\u00ab': '"',  # LEFT-POINTING DOUBLE ANGLE  «
    '\u00bb': '"',  # RIGHT-POINTING DOUBLE ANGLE »
}
_CURLY_QUOTE_RE = re.compile('[' + ''.join(_CURLY_QUOTE_MAP) + ']')


def scan_curly_quotes(path: str) -> list[tuple[int, str]]:
    """
    Return a list of ``(lineno, line)`` for every line in *path* that contains
    a curly/typographic quote character.  Line numbers are 1-based.

    GEDCOM files should use plain ASCII straight quotes throughout so that
    nickname extraction (``"Nick"``) and other text processing is reliable.
    """
    violations = []
    with open(path, encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            if _CURLY_QUOTE_RE.search(line):
                violations.append((i, line.rstrip('\n')))
    return violations


def fix_curly_quotes(path: str, dry_run: bool = False) -> int:
    """
    Replace every curly/typographic quote in *path* with its straight ASCII
    equivalent (see ``_CURLY_QUOTE_MAP``).

    Returns the number of lines changed.  Writes the result in-place unless
    *dry_run* is ``True``.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for line in lines_in:
        fixed = _CURLY_QUOTE_RE.sub(lambda m: _CURLY_QUOTE_MAP[m.group()], line)
        if fixed != line:
            changed += 1
        lines_out.append(fixed)

    if not dry_run and changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)

    return changed


# ---------------------------------------------------------------------------
# Unknown surname placeholder stripping  (/UNKNOWN/ → //)
# ---------------------------------------------------------------------------

_UNKNOWN_NAME_RE = re.compile(r'^(\d+ NAME .*/)(UNKNOWN)(/.*)$', re.IGNORECASE)
_UNKNOWN_SURN_RE = re.compile(r'^(\d+) SURN UNKNOWN\s*$', re.IGNORECASE)


def scan_unknown_surname(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, line) for every NAME line whose surname slot contains the
    placeholder value 'UNKNOWN' (case-insensitive), e.g. 'John /UNKNOWN/'.

    These should be converted to '//'. Corresponding '2 SURN UNKNOWN' sub-tags
    are also flagged.
    """
    violations: list[tuple[int, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()
    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip('\n')
        if _UNKNOWN_NAME_RE.match(line) or _UNKNOWN_SURN_RE.match(line):
            violations.append((lineno, line))
    return violations


def fix_unknown_surname(path: str, dry_run: bool = False) -> int:
    """
    Replace '/UNKNOWN/' with '//' in NAME lines and remove any '2 SURN UNKNOWN'
    sub-tags.  Returns the number of lines changed or removed.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for raw in lines_in:
        line = raw.rstrip('\n')
        eol = '\n' if raw.endswith('\n') else ''
        m_name = _UNKNOWN_NAME_RE.match(line)
        if m_name:
            line = m_name.group(1) + m_name.group(3)  # replace UNKNOWN with empty
            changed += 1
            lines_out.append(line + eol)
        elif _UNKNOWN_SURN_RE.match(line):
            changed += 1  # drop the line entirely
        else:
            lines_out.append(raw)

    if not dry_run and changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)

    return changed


# ---------------------------------------------------------------------------
# Name piece case consistency (GIVN/SURN all-caps under title-cased NAME)
# ---------------------------------------------------------------------------

def scan_name_piece_case(path: str) -> list[tuple[int, str, str]]:
    """
    Return (lineno, tag, value) for every GIVN/SURN/NPFX/NSFX sub-tag that is
    all-caps while its parent NAME line already contains at least one lowercase
    letter (i.e. the NAME was title-cased but the sub-tags were not).

    This detects the inconsistency where fix_name_case has been run on a file
    (or the NAME was added with correct case) but the subordinate name pieces
    still contain all-caps values.
    """
    violations: list[tuple[int, str, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    in_name_block = False
    name_level = 0
    name_is_allcaps = True  # if True, pieces are expected to be all-caps too

    for lineno, raw in enumerate(lines, 1):
        line = raw.rstrip('\n')
        level_m = re.match(r'^(\d+)', line)
        cur_level = int(level_m.group(1)) if level_m else -1

        if in_name_block and cur_level <= name_level:
            in_name_block = False

        m = NAME_LINE_RE.match(line)
        if m:
            name_level = int(m.group(2))
            in_name_block = True
            val = m.group(3)
            letters = [c for c in val if c.isalpha()]
            # Track whether the NAME itself is all-caps
            name_is_allcaps = bool(letters) and all(c.isupper() for c in letters)
            continue

        if in_name_block and not name_is_allcaps:
            mp = _NAME_PIECE_CASE_RE.match(line)
            if mp:
                val = mp.group(4)
                letters = [c for c in val if c.isalpha()]
                if letters and all(c.isupper() for c in letters):
                    violations.append((lineno, mp.group(3), val))

    return violations


def fix_name_piece_case(path: str, dry_run: bool = False) -> int:
    """
    Title-case any all-caps GIVN/SURN/NPFX/NSFX sub-tags whose parent NAME
    line is not all-caps (i.e. the pieces are out of sync with the NAME).

    Returns the number of lines changed.
    """
    hits = scan_name_piece_case(path)
    if not hits:
        return 0

    lines_to_fix: set[int] = {lineno for lineno, _tag, _val in hits}

    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')
        if lineno in lines_to_fix:
            mp = _NAME_PIECE_CASE_RE.match(line)
            if mp:
                fixed = _name_to_title_case(mp.group(4))
                line = mp.group(1) + fixed
                changed += 1
        lines_out.append(line + '\n')

    if not dry_run and changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)

    return changed


# ---------------------------------------------------------------------------
# Sole-event TYPE alternate
# ---------------------------------------------------------------------------

def scan_sole_event_type_alternate(path: str) -> list[tuple[int, str, str]]:
    """
    Return (lineno, tag, xref) for every '2 TYPE alternate' sub-line that
    belongs to a BIRT or DEAT event when that event is the *only* BIRT/DEAT
    for the individual.

    If an individual has two BIRT events and one is marked TYPE alternate,
    that is intentional (it's the alternate birth record) and is NOT flagged.
    Only when the event is the sole occurrence of its type is the TYPE
    alternate label meaningless.
    """
    violations: list[tuple[int, str, str]] = []
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    _TAGS = ('BIRT', 'DEAT')
    current_xref: str | None = None
    # For each tag, list of (event_start_lineno_0indexed, type_alternate_lineno_0indexed)
    # We collect per-individual, then decide after the record ends.
    event_info: dict[str, list[tuple[int, int | None]]] = {}  # tag → [(event_start, type_lineno)]

    def _flush(xref: str | None) -> None:
        if xref is None:
            return
        for tag, events in event_info.items():
            if len(events) == 1:
                _, type_lineno = events[0]
                if type_lineno is not None:
                    violations.append((type_lineno + 1, tag, xref))

    i = 0
    in_indi = False
    current_event_tag: str | None = None
    current_event_start: int | None = None
    current_type_lineno: int | None = None  # 0-based index of '2 TYPE alternate' in current event

    while i < len(lines):
        raw = lines[i].rstrip('\n')

        if re.match(r'^0 ', raw):
            # End of previous record — flush
            if current_event_tag and in_indi:
                event_info.setdefault(current_event_tag, []).append(
                    (current_event_start, current_type_lineno)
                )
            _flush(current_xref)

            in_indi = bool(re.match(r'^0 @[^@]+@ INDI\b', raw))
            m = re.match(r'^0 (@[^@]+@)', raw)
            current_xref = m.group(1) if (m and in_indi) else None
            event_info = {}
            current_event_tag = None
            current_event_start = None
            current_type_lineno = None
            i += 1
            continue

        if not in_indi:
            i += 1
            continue

        m1 = re.match(r'^1 ([A-Z]+)', raw)
        if m1:
            # Close previous event block
            if current_event_tag is not None:
                event_info.setdefault(current_event_tag, []).append(
                    (current_event_start, current_type_lineno)
                )
            tag1 = m1.group(1)
            if tag1 in _TAGS:
                current_event_tag = tag1
                current_event_start = i
                current_type_lineno = None
            else:
                current_event_tag = None
                current_event_start = None
                current_type_lineno = None
            i += 1
            continue

        if current_event_tag and re.match(r'^2 TYPE\s+alternate\s*$', raw, re.IGNORECASE):
            current_type_lineno = i

        i += 1

    # End of file — flush last record
    if current_event_tag and in_indi:
        event_info.setdefault(current_event_tag, []).append(
            (current_event_start, current_type_lineno)
        )
    _flush(current_xref)

    return violations


def fix_sole_event_type_alternate(path: str, dry_run: bool = False) -> int:
    """
    Remove '2 TYPE alternate' lines from BIRT/DEAT events when the individual
    has only one event of that type.

    Returns the number of lines removed.
    """
    hits = scan_sole_event_type_alternate(path)
    if not hits:
        return 0

    # Convert to a set of 1-based line numbers to drop
    lines_to_remove: set[int] = {lineno for lineno, _tag, _xref in hits}

    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    out = [line for i, line in enumerate(lines, 1) if i not in lines_to_remove]

    if not dry_run:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(out)

    return len(lines_to_remove)


# ---------------------------------------------------------------------------
# Godparent count validation  (spec 1.11)
# ---------------------------------------------------------------------------

def scan_godparent_count(path: str) -> list[tuple[str, int, int, int]]:
    """
    Return (xref, total, male_count, female_count) tuples for any INDI that
    violates the godparent rules:
      - More than 2 godparents total, OR
      - More than 1 godparent of the same gender (M or F)

    Algorithm:
    1. First pass: build sex_map = { xref: 'M'|'F'|'U' } from all INDI 1 SEX tags.
    2. Second pass: for each INDI, collect all 1 ASSO blocks where 2 RELA == 'Godparent'
       (case-insensitive). Look up each godparent's sex in sex_map (default 'U').
    3. Emit violation if total > 2 OR male_count > 1 OR female_count > 1.
    """
    # --- First pass: build sex_map ---
    sex_map: dict[str, str] = {}
    current_xref: str | None = None
    in_indi = False

    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            m = re.match(r'^0 (@[^@]+@) INDI', line)
            if m:
                current_xref = m.group(1)
                in_indi = True
                continue
            if in_indi and line.startswith('0 '):
                in_indi = False
                current_xref = None
                continue
            if in_indi and current_xref:
                sm = re.match(r'^1 SEX ([MFU])', line)
                if sm:
                    sex_map[current_xref] = sm.group(1)

    # --- Second pass: collect godparent ASSOciations per INDI ---
    violations: list[tuple[str, int, int, int]] = []
    current_xref = None
    in_indi = False
    godparents: list[str] = []  # list of godparent xrefs for current INDI

    def _check_and_emit(indi_xref: str, gps: list[str]) -> None:
        if not gps:
            return
        male_count = sum(1 for gp in gps if sex_map.get(gp, 'U') == 'M')
        female_count = sum(1 for gp in gps if sex_map.get(gp, 'U') == 'F')
        total = len(gps)
        if total > 2 or male_count > 1 or female_count > 1:
            violations.append((indi_xref, total, male_count, female_count))

    with open(path, encoding='utf-8') as f:
        lines_iter = enumerate(f, 1)
        pending_asso_xref: str | None = None  # ASSO xref awaiting RELA confirmation

        for _lineno, raw in lines_iter:
            line = raw.rstrip('\n')
            m0 = re.match(r'^0 (@[^@]+@) INDI', line)
            if m0:
                # Close previous INDI
                if in_indi and current_xref:
                    _check_and_emit(current_xref, godparents)
                current_xref = m0.group(1)
                in_indi = True
                godparents = []
                pending_asso_xref = None
                continue

            if in_indi and line.startswith('0 '):
                # Close current INDI
                _check_and_emit(current_xref, godparents)
                in_indi = False
                current_xref = None
                godparents = []
                pending_asso_xref = None
                continue

            if not in_indi:
                continue

            # Level-1 ASSO tag.  Overwriting any existing pending_asso_xref is
            # intentional: if the previous ASSO never received a "2 RELA
            # Godparent" line it was not a godparent association and can be
            # discarded.
            m1 = re.match(r'^1 ASSO (@[^@]+@)', line)
            if m1:
                pending_asso_xref = m1.group(1)
                continue

            # Level-1 tag (not ASSO) — pending ASSO loses its chance for RELA
            if re.match(r'^1 ', line):
                pending_asso_xref = None
                continue

            # Level-2 RELA tag under a pending ASSO
            if pending_asso_xref is not None:
                m2 = re.match(r'^2 RELA (.+)', line)
                if m2:
                    rela = m2.group(1).strip()
                    if rela.lower() == 'godparent':
                        godparents.append(pending_asso_xref)
                    pending_asso_xref = None

    # Final INDI at end of file
    if in_indi and current_xref:
        _check_and_emit(current_xref, godparents)

    return violations


# ---------------------------------------------------------------------------
# ASSO without RELA  (spec 1.12)
# ---------------------------------------------------------------------------

def scan_asso_without_rela(path: str) -> list[tuple[int, str]]:
    """
    Return (lineno, indi_xref) for every 1 ASSO tag on an INDI record that has
    no 2 RELA subordinate before the next level-0 or level-1 tag.

    RELA is required per GEDCOM 5.5.1 ASSOCIATION_STRUCTURE.
    """
    violations: list[tuple[int, str]] = []
    current_xref: str | None = None
    in_indi = False
    pending_asso_lineno: int | None = None   # lineno of the 1 ASSO under scrutiny

    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')

            m0 = re.match(r'^0 (@[^@]+@) INDI', line)
            if m0:
                # Close previous INDI; if we had a pending ASSO it has no RELA
                if in_indi and pending_asso_lineno is not None:
                    violations.append((pending_asso_lineno, current_xref))
                current_xref = m0.group(1)
                in_indi = True
                pending_asso_lineno = None
                continue

            if in_indi and line.startswith('0 '):
                # Close current INDI
                if pending_asso_lineno is not None:
                    violations.append((pending_asso_lineno, current_xref))
                in_indi = False
                current_xref = None
                pending_asso_lineno = None
                continue

            if not in_indi:
                continue

            # Level-1 ASSO tag
            if re.match(r'^1 ASSO\b', line):
                # Previous ASSO (if any) had no RELA
                if pending_asso_lineno is not None:
                    violations.append((pending_asso_lineno, current_xref))
                pending_asso_lineno = lineno
                continue

            # Another level-1 tag (not ASSO) closes any pending ASSO without RELA
            if re.match(r'^1 ', line):
                if pending_asso_lineno is not None:
                    violations.append((pending_asso_lineno, current_xref))
                    pending_asso_lineno = None
                continue

            # Level-2 RELA tag resolves the pending ASSO
            if pending_asso_lineno is not None and re.match(r'^2 RELA\b', line):
                pending_asso_lineno = None

    # End of file: any pending ASSO has no RELA
    if in_indi and pending_asso_lineno is not None:
        violations.append((pending_asso_lineno, current_xref))

    return violations


# ---------------------------------------------------------------------------
# SOUR without TITL  (spec 1.13)
# ---------------------------------------------------------------------------

def scan_sour_without_titl(path: str) -> list[str]:
    """
    Return xrefs of 0 @Sn@ SOUR records that have no 1 TITL subordinate.
    """
    violations: list[str] = []
    current_xref: str | None = None
    in_sour = False
    has_titl = False

    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')

            m = re.match(r'^0 (@[^@]+@) SOUR', line)
            if m:
                if in_sour and current_xref and not has_titl:
                    violations.append(current_xref)
                current_xref = m.group(1)
                in_sour = True
                has_titl = False
                continue

            if in_sour and line.startswith('0 '):
                if current_xref and not has_titl:
                    violations.append(current_xref)
                in_sour = False
                current_xref = None
                continue

            if in_sour and re.match(r'^1 TITL\b', line):
                has_titl = True

    if in_sour and current_xref and not has_titl:
        violations.append(current_xref)

    return violations


# ---------------------------------------------------------------------------
# Programmatic all-fixes API
# ---------------------------------------------------------------------------

def lint_and_fix(path: str, dry_run: bool = False) -> dict:
    """
    Run all fix operations (equivalent to --fix-all) on *path*.

    Parameters
    ----------
    path    : path to the GEDCOM file (modified in-place unless dry_run)
    dry_run : if True, compute what would change but do not write

    Returns
    -------
    dict with keys:
      'lines_read'     : total lines in the file before any fixes
      'lines_delta'    : net line change (negative = file shrank)
      'fixes_applied'  : total number of individual fixes made across all passes
    """
    with open(path, encoding='utf-8') as f:
        lines_before = sum(1 for _ in f)

    fixes_applied = 0
    fixes_applied += fix_curly_quotes(path, dry_run=dry_run)
    fixes_applied += fix_trailing_whitespace(path, dry_run=dry_run)
    fixes_applied += fix_duplicate_sources(path, dry_run=dry_run)
    fixes_applied += fix_name_double_spaces(path, dry_run=dry_run)
    fixes_applied += fix_name_case(path, dry_run=dry_run)
    fixes_applied += fix_name_piece_case(path, dry_run=dry_run)
    fixes_applied += fix_long_lines(path, dry_run=dry_run)
    fixes_applied += fix_addr_under_plac(path, dry_run=dry_run)
    fixes_applied += fix_note_under_plac(path, dry_run=dry_run)
    fixes_applied += fix_note_under_addr(path, dry_run=dry_run)
    fixes_applied += fix_plac(path, dry_run=dry_run)
    fixes_applied += fix_plac_address_parts(path, dry_run=dry_run)
    dates_fixed, _ = fix_file(path, dry_run=dry_run)
    fixes_applied += dates_fixed
    fixes_applied += fix_date_caps(path, dry_run=dry_run)
    fixes_applied += fix_nicknames(path, dry_run=dry_run)
    fixes_applied += fix_name_pieces(path, dry_run=dry_run)
    fixes_applied += fix_name_piece_order(path, dry_run=dry_run)
    fixes_applied += fix_event_source_order(path, dry_run=dry_run)
    fixes_applied += fix_redundant_citation_page(path, dry_run=dry_run)
    fixes_applied += fix_dateless_dates(path, dry_run=dry_run)
    fixes_applied += fix_aka_facts(path, dry_run=dry_run)
    fixes_applied += fix_broken_xrefs(path, dry_run=dry_run)
    fixes_applied += fix_duplicate_families(path, dry_run=dry_run)
    fixes_applied += fix_unknown_surname(path, dry_run=dry_run)
    fixes_applied += fix_duplicate_names(path, dry_run=dry_run)
    fixes_applied += fix_duplicate_resi(path, dry_run=dry_run)
    fixes_applied += fix_bapm_without_birth(path, dry_run=dry_run)
    fixes_applied += fix_bare_events(path, dry_run=dry_run)
    fixes_applied += fix_sole_event_type_alternate(path, dry_run=dry_run)
    fixes_applied += fix_record_order(path, dry_run=dry_run)
    fixes_applied += fix_sort_events(path, dry_run=dry_run)
    # fix_sort_events round-trips through parse/write, which can reformat NOTE
    # records into long lines with trailing spaces before CONC. Re-run both
    # long-line wrapping and whitespace stripping after it.
    fixes_applied += fix_long_lines(path, dry_run=dry_run)
    # Run whitespace strip again — some fixers (e.g. fix_name_pieces) can
    # introduce trailing whitespace on blank CONT lines.
    fixes_applied += fix_trailing_whitespace(path, dry_run=dry_run)

    with open(path, encoding='utf-8') as f:
        lines_after = sum(1 for _ in f)

    return {
        'lines_read': lines_before,
        'lines_delta': lines_after - lines_before,
        'fixes_applied': fixes_applied,
    }


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _build_name_map(path: str) -> dict[str, str]:
    """Return {xref: display_name} for all INDI records in *path*."""
    name_map: dict[str, str] = {}
    cur_xref: str | None = None
    with open(path, encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')
            m0 = re.match(r'^0 (@[^@]+@) INDI', line)
            if m0:
                cur_xref = m0.group(1)
                continue
            if cur_xref and line.startswith('0 '):
                cur_xref = None
                continue
            if cur_xref:
                mn = re.match(r'^1 NAME (.+)', line)
                if mn and cur_xref not in name_map:
                    name_map[cur_xref] = mn.group(1).strip().replace('/', '').strip()
    return name_map


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Lint (and optionally fix) GEDCOM 5.5.1 date fields.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to .ged file')
    parser.add_argument(
        '--fix-dates', action='store_true',
        help='Normalize non-standard DATE values in-place',
    )
    parser.add_argument(
        '--fix-whitespace', action='store_true',
        help='Strip trailing whitespace from every line in-place',
    )
    parser.add_argument(
        '--fix-html-entities', action='store_true',
        help='Decode HTML entities (&lt; &amp; &nbsp; etc.) and strip HTML tags '
             'from NOTE, TITL, PUBL, PAGE and other field values in-place',
    )
    parser.add_argument(
        '--fix-places', action='store_true',
        help='Normalize PLAC comma-spacing in-place',
    )
    parser.add_argument(
        '--fix-address-parts', action='store_true',
        help='Move misplaced address/descriptor parts out of PLAC values in-place',
    )
    parser.add_argument(
        '--fix-duplicate-sources', action='store_true',
        help='Remove exact-duplicate SOUR citation blocks in-place',
    )
    parser.add_argument(
        '--fix-names', action='store_true',
        help='Collapse double spaces in NAME values in-place',
    )
    parser.add_argument(
        '--fix-long-lines', action='store_true',
        help='Wrap lines > 255 chars using CONC continuations in-place',
    )
    parser.add_argument(
        '--fix-addr-under-plac', action='store_true',
        help='Promote ADDR lines that are invalid children of PLAC up one level in-place',
    )
    parser.add_argument(
        '--fix-note-under-plac', action='store_true',
        help='Convert NOTE children of PLAC to ADDR siblings (venue names) in-place',
    )
    parser.add_argument(
        '--fix-note-under-addr', action='store_true',
        help='Restructure NOTE children of ADDR: venue name leads ADDR, street becomes CONT',
    )
    parser.add_argument(
        '--fix-broken-xrefs', action='store_true',
        help='Remove dangling CHIL/HUSB/WIFE/FAMS/FAMC/OBJE/SOUR pointers in-place',
    )
    parser.add_argument(
        '--fix-duplicate-families', action='store_true',
        help='Collapse FAM records with the same husband+wife into one in-place',
    )
    parser.add_argument(
        '--fix-duplicate-names', action='store_true',
        help='Remove duplicate NAME entries within individuals in-place',
    )
    parser.add_argument(
        '--fix-record-order', action='store_true',
        help='Reorder top-level records into canonical GEDCOM sequence '
             '(HEAD, SUBM, INDI, FAM, SOUR, REPO, OBJE, NOTE, TRLR) in-place',
    )
    parser.add_argument(
        '--fix-sort-events', action='store_true',
        help='Sort events in each record into chronological order in-place',
    )
    parser.add_argument(
        '--fix-conc-cont-levels', action='store_true',
        help='Rewrite CONC/CONT lines at wrong level (must be parent_level+1) in-place',
    )
    parser.add_argument(
        '--fix-note-reflow', action='store_true',
        help='Re-encode shared NOTE records that contain abnormally short CONC values (<5 chars) in-place',
    )
    parser.add_argument(
        '--fix-date-caps', action='store_true',
        help='Normalize month abbreviations in DATE lines to uppercase in-place',
    )
    parser.add_argument(
        '--fix-nicknames', action='store_true',
        help='Extract quoted nicknames from NAME values and insert 2 NICK subordinates',
    )
    parser.add_argument(
        '--fix-name-pieces', action='store_true',
        help='Insert missing GIVN/SURN/NSFX subordinates for NAME lines in-place',
    )
    parser.add_argument(
        '--fix-name-piece-order', action='store_true',
        help='Reorder NAME sub-tags so GIVN/SURN/NSFX come before TYPE in-place',
    )
    parser.add_argument(
        '--fix-event-source-order', action='store_true',
        help='Reorder event sub-tags so SOUR comes before NOTE and after other details',
    )
    parser.add_argument(
        '--fix-redundant-citation-page', action='store_true',
        help='Remove citation PAGE lines that just repeat the source TITL verbatim',
    )
    parser.add_argument(
        '--fix-dateless-dates', action='store_true',
        help='Wrap day+month-only DATE values as date phrases in-place',
    )
    parser.add_argument(
        '--fix-aka-facts', action='store_true',
        help='Convert FACT/TYPE AKA/NOTE blocks to proper NAME records in-place',
    )
    parser.add_argument(
        '--fix-duplicate-resi', action='store_true',
        help='Merge duplicate RESI events (same date+place) within individual records',
    )
    parser.add_argument(
        '--fix-bare-events', action='store_true',
        help='Append Y to bare BIRT/CHR/DEAT tags with no value and no children',
    )
    parser.add_argument(
        '--fix-birth-from-bapm', action='store_true',
        help='Insert estimated birth date (EST YEAR) for individuals with a '
             'baptism/christening date but no birth date',
    )
    parser.add_argument(
        '--merge-sources', nargs=2, metavar=('KEEP', 'REMOVE'),
        help='Remap all citations from REMOVE xref to KEEP xref and delete REMOVE. '
             'Example: --merge-sources @S100@ @S200@',
    )
    parser.add_argument(
        '--fix-all', action='store_true',
        help='Run all fix operations in sequence',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='With any --fix-* flag: print changes but do not write the file',
    )
    args = parser.parse_args()

    if args.fix_all:
        args.fix_dates = True
        args.fix_whitespace = True
        args.fix_html_entities = True
        args.fix_places = True
        args.fix_address_parts = True
        args.fix_duplicate_sources = True
        args.fix_names = True
        args.fix_long_lines = True
        args.fix_addr_under_plac = True
        args.fix_note_under_plac = True
        args.fix_note_under_addr = True
        args.fix_date_caps = True
        args.fix_nicknames = True
        args.fix_name_pieces = True
        args.fix_name_piece_order = True
        args.fix_event_source_order = True
        args.fix_redundant_citation_page = True
        args.fix_dateless_dates = True
        args.fix_aka_facts = True
        args.fix_broken_xrefs = True
        args.fix_duplicate_families = True
        args.fix_duplicate_names = True
        args.fix_duplicate_resi = True
        args.fix_bare_events = True
        args.fix_birth_from_bapm = True
        args.fix_record_order = True
        args.fix_sort_events = True
        args.fix_conc_cont_levels = True
        args.fix_note_reflow = True

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    if args.fix_whitespace:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Stripping trailing whitespace in: {args.gedfile}')
        changed = fix_trailing_whitespace(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} line(s) would be changed.')
        else:
            print(f'{changed} line(s) fixed.')

    if args.fix_html_entities:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Decoding HTML entities and stripping HTML tags in: {args.gedfile}')
        changed = fix_html_entities(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} line(s) would be changed.')
        else:
            print(f'{changed} line(s) fixed.')

    if args.fix_duplicate_sources:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Removing duplicate SOUR citations in: {args.gedfile}')
        changed = fix_duplicate_sources(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} duplicate block(s) would be removed.')
        else:
            print(f'{changed} duplicate SOUR block(s) removed.')

    if args.fix_names:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Collapsing double spaces in NAME values: {args.gedfile}')
        changed = fix_name_double_spaces(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} line(s) would be changed.')
        else:
            print(f'{changed} NAME line(s) fixed.')

    if args.fix_long_lines:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Wrapping long lines in: {args.gedfile}')
        changed = fix_long_lines(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} line(s) would be wrapped.')
        else:
            print(f'{changed} line(s) wrapped.')

    if args.fix_addr_under_plac:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Promoting ADDR-under-PLAC to sibling level in: {args.gedfile}')
        changed = fix_addr_under_plac(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} ADDR line(s) would be promoted.')
        else:
            print(f'{changed} ADDR line(s) promoted.')

    if args.fix_note_under_plac:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Converting NOTE-under-PLAC to ADDR siblings in: {args.gedfile}')
        changed = fix_note_under_plac(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} NOTE line(s) would be converted to ADDR.')
        else:
            print(f'{changed} NOTE line(s) converted to ADDR.')

    if args.fix_note_under_addr:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Restructuring NOTE-under-ADDR (venue first) in: {args.gedfile}')
        changed = fix_note_under_addr(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} ADDR block(s) would be restructured.')
        else:
            print(f'{changed} ADDR block(s) restructured.')

    if args.fix_places:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Normalizing PLAC values in: {args.gedfile}')
        changed = fix_plac(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} line(s) would be changed.')
        else:
            print(f'{changed} PLAC line(s) normalized.')

    if args.fix_address_parts:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Moving misplaced PLAC address parts in: {args.gedfile}')
        changed = fix_plac_address_parts(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} PLAC line(s) would be changed.')
        else:
            print(f'{changed} PLAC line(s) fixed.')

    if args.fix_broken_xrefs:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Removing dangling cross-references in: {args.gedfile}')
        removed = fix_broken_xrefs(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {removed} dangling reference(s) would be removed.')
        else:
            print(f'  {removed} dangling reference(s) removed.')

    if args.fix_duplicate_families:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Collapsing duplicate families in: {args.gedfile}')
        removed = fix_duplicate_families(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {removed} duplicate family record(s) would be removed.')
        else:
            print(f'  {removed} duplicate family record(s) removed.')

    if args.fix_duplicate_names:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Removing duplicate NAME entries in: {args.gedfile}')
        removed = fix_duplicate_names(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {removed} duplicate NAME entry/entries would be removed.')
        else:
            print(f'  {removed} duplicate NAME entry/entries removed.')

    if args.fix_record_order:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Reordering top-level records into canonical sequence in: {args.gedfile}')
        moved = fix_record_order(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {moved} record(s) would be moved.')
        else:
            print(f'  {moved} record(s) moved.')

    if args.fix_sort_events:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Sorting events chronologically in: {args.gedfile}')
        changed = fix_sort_events(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {changed} record(s) would have events reordered.')
        else:
            print(f'  {changed} record(s) had events reordered.')
        if changed and not args.dry_run:
            # fix_sort_events round-trips through write_gedcom which can reflow
            # NOTE records into lines that exceed 255 chars. Re-wrap immediately.
            fix_long_lines(args.gedfile)
            fix_trailing_whitespace(args.gedfile)

    if args.fix_conc_cont_levels:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Correcting CONC/CONT line levels in: {args.gedfile}')
        changed = fix_conc_cont_levels(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {changed} CONC/CONT line(s) would be corrected.')
        else:
            print(f'  {changed} CONC/CONT line(s) corrected.')

    if args.fix_note_reflow:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Reflowing shared NOTE records with short CONC values in: {args.gedfile}')
        changed = fix_note_reflow(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {changed} NOTE record(s) would be reflowed.')
        else:
            print(f'  {changed} NOTE record(s) reflowed.')

    if args.fix_date_caps:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Normalizing DATE month-abbreviation capitalization in: {args.gedfile}')
        changed = fix_date_caps(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} line(s) would be changed.')
        else:
            print(f'{changed} DATE line(s) fixed.')

    if args.fix_nicknames:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Extracting quoted nicknames from NAME values in: {args.gedfile}')
        changed = fix_nicknames(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} NAME line(s) would be changed.')
        else:
            print(f'{changed} NAME line(s) changed; NICK tags inserted.')

    if args.fix_name_pieces:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Inserting missing GIVN/SURN subordinates in: {args.gedfile}')
        changed = fix_name_pieces(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} NAME line(s) would gain new subordinates.')
        else:
            print(f'{changed} NAME line(s) updated with GIVN/SURN/NSFX.')

    if args.fix_name_piece_order:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Reordering NAME sub-tags (GIVN/SURN before TYPE) in: {args.gedfile}')
        changed = fix_name_piece_order(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} NAME block(s) would be reordered.')
        else:
            print(f'{changed} NAME block(s) reordered.')

    if args.fix_event_source_order:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Reordering event sub-tags (SOUR/NOTE last) in: {args.gedfile}')
        changed = fix_event_source_order(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} event block(s) would be reordered.')
        else:
            print(f'{changed} event block(s) reordered.')

    if args.fix_redundant_citation_page:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Removing redundant citation PAGE values in: {args.gedfile}')
        changed = fix_redundant_citation_page(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} redundant PAGE line(s) would be removed.')
        else:
            print(f'{changed} redundant PAGE line(s) removed.')

    if args.fix_dateless_dates:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Wrapping day+month-only DATE values in: {args.gedfile}')
        changed = fix_dateless_dates(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} DATE line(s) would be wrapped.')
        else:
            print(f'{changed} DATE line(s) wrapped as date phrases.')

    if args.fix_aka_facts:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Converting FACT/AKA/NOTE blocks to NAME records in: {args.gedfile}')
        changed = fix_aka_facts(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} FACT/AKA block(s) would be converted.')
        else:
            print(f'{changed} FACT/AKA block(s) converted to NAME records.')

    if args.fix_duplicate_resi:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Merging duplicate RESI events in: {args.gedfile}')
        removed = fix_duplicate_resi(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {removed} duplicate RESI event(s) would be removed.')
        else:
            print(f'  {removed} duplicate RESI event(s) removed.')

    if args.fix_bare_events:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Appending Y to bare event tags in: {args.gedfile}')
        fixed = fix_bare_events(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {fixed} bare event tag(s) would be updated.')
        else:
            print(f'  {fixed} bare event tag(s) updated.')

    if args.fix_birth_from_bapm:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Adding estimated birth dates from baptism dates: {args.gedfile}')
        fixed = fix_bapm_without_birth(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'  {fixed} individual(s) would have EST birth date added.')
        else:
            print(f'  {fixed} individual(s) given estimated birth date from baptism.')

    if args.merge_sources:
        keep, remove = args.merge_sources
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Merging {remove} → {keep} in: {args.gedfile}')
        try:
            n = fix_merge_sources(args.gedfile, keep, remove, dry_run=args.dry_run)
            if args.dry_run:
                print(f'  {n} citation(s) would be updated; {remove} would be removed.')
            else:
                print(f'  {n} citation(s) updated; {remove} removed.')
        except ValueError as e:
            print(f'  Error: {e}', file=sys.stderr)
            sys.exit(1)

    if args.fix_dates:
        mode = 'DRY RUN' if args.dry_run else 'FIX'
        print(f'[{mode}] Normalizing DATE values in: {args.gedfile}')
        changed, remaining = fix_file(args.gedfile, dry_run=args.dry_run)
        if args.dry_run:
            print(f'\n{changed} line(s) would be changed.')
        else:
            print(f'{changed} DATE line(s) normalized.')
        if remaining:
            print(f'\n{len(remaining)} DATE value(s) could not be auto-fixed '
                  '(require manual review):')
            for ln, val in remaining:
                print(f'  line {ln}: {val!r}')
        else:
            print('No remaining violations.')
    # Final whitespace pass: some fixers (e.g. fix_name_pieces) can introduce
    # trailing whitespace on blank CONT lines; strip it after all other fixes.
    if args.fix_all:
        fix_trailing_whitespace(args.gedfile, dry_run=args.dry_run)

    if not any([args.fix_dates, args.fix_whitespace, args.fix_html_entities,
                args.fix_places, args.fix_address_parts, args.fix_names, args.fix_long_lines,
                args.fix_duplicate_sources, args.fix_addr_under_plac,
                args.fix_note_under_plac, args.fix_note_under_addr,
                args.fix_date_caps, args.fix_nicknames, args.fix_name_pieces,
                args.fix_name_piece_order, args.fix_event_source_order,
                args.fix_redundant_citation_page,
                args.fix_dateless_dates, args.fix_aka_facts,
                args.fix_broken_xrefs, args.fix_duplicate_families,
                args.fix_duplicate_names, args.fix_duplicate_resi,
                args.fix_bare_events, args.fix_birth_from_bapm,
                args.fix_record_order, args.fix_sort_events,
                args.fix_conc_cont_levels, args.fix_note_reflow,
                args.merge_sources]):
        print(f'[CHECK] Scanning: {args.gedfile}')
        errors = False
        # counters for summary statistics
        _err_count: dict[str, int] = {}
        _warn_count: dict[str, int] = {}
        _info_count: dict[str, int] = {}

        trailing = scan_trailing_whitespace(args.gedfile)
        if trailing:
            errors = True
            print(f'\n{len(trailing)} line(s) with trailing whitespace '
                  '(run --fix-whitespace to strip):')
            for ln, val in trailing[:20]:
                print(f'  line {ln}: {val!r}')
            if len(trailing) > 20:
                print(f'  ... and {len(trailing) - 20} more.')
        else:
            print('OK: no trailing whitespace.')

        html_issues = scan_html_entities(args.gedfile)
        if html_issues:
            errors = True
            print(f'\n{len(html_issues)} line(s) with HTML entities or tags '
                  '(run --fix-html-entities to decode):')
            for ln, val in html_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(html_issues) > 20:
                print(f'  ... and {len(html_issues) - 20} more.')
        else:
            print('OK: no HTML entities or tags.')

        dupe_sources = scan_duplicate_sources(args.gedfile)
        if dupe_sources:
            errors = True
            print(f'\n{len(dupe_sources)} exact-duplicate SOUR citation(s) '
                  '(run --fix-duplicate-sources to remove):')
            for ln, xref in dupe_sources[:20]:
                print(f'  line {ln}: {xref}')
            if len(dupe_sources) > 20:
                print(f'  ... and {len(dupe_sources) - 20} more.')
        else:
            print('OK: no duplicate SOUR citations.')

        name_issues = scan_name_double_spaces(args.gedfile)
        if name_issues:
            errors = True
            print(f'\n{len(name_issues)} NAME value(s) with double spaces '
                  '(run --fix-names to normalize):')
            for ln, orig, fixed in name_issues:
                print(f'  line {ln}: {orig!r}  →  {fixed!r}')
        else:
            print('OK: no double spaces in NAME values.')

        long_lines = scan_long_lines(args.gedfile)
        if long_lines:
            errors = True
            print(f'\n{len(long_lines)} line(s) exceed 255 characters '
                  '(run --fix-long-lines to wrap with CONC):')
            for ln, length in long_lines:
                print(f'  line {ln}: {length} chars')
        else:
            print('OK: no lines exceed 255 characters.')

        level_jumps = scan_level_jumps(args.gedfile)
        if level_jumps:
            errors = True
            print(f'\n{len(level_jumps)} invalid level jump(s) '
                  '(level increases by more than 1 — requires manual correction):')
            for ln, prev, curr in level_jumps:
                print(f'  line {ln}: level {prev} → level {curr}')
        else:
            print('OK: no invalid level jumps.')

        addr_plac_issues = scan_addr_under_plac(args.gedfile)
        if addr_plac_issues:
            errors = True
            print(f'\n{len(addr_plac_issues)} ADDR line(s) incorrectly nested under PLAC '
                  '(run --fix-addr-under-plac to promote to sibling level):')
            for ln, level in addr_plac_issues[:20]:
                print(f'  line {ln}: level-{level} ADDR under level-{level - 1} PLAC')
            if len(addr_plac_issues) > 20:
                print(f'  ... and {len(addr_plac_issues) - 20} more.')
        else:
            print('OK: no ADDR lines incorrectly nested under PLAC.')

        note_plac_issues = scan_note_under_plac(args.gedfile)
        if note_plac_issues:
            errors = True
            print(f'\n{len(note_plac_issues)} NOTE line(s) incorrectly nested under PLAC '
                  '(run --fix-note-under-plac to convert to ADDR siblings):')
            for ln, level in note_plac_issues[:20]:
                print(f'  line {ln}: level-{level} NOTE under level-{level - 1} PLAC')
            if len(note_plac_issues) > 20:
                print(f'  ... and {len(note_plac_issues) - 20} more.')
        else:
            print('OK: no NOTE lines incorrectly nested under PLAC.')

        note_addr_issues = scan_note_under_addr(args.gedfile)
        if note_addr_issues:
            errors = True
            print(f'\n{len(note_addr_issues)} NOTE line(s) incorrectly nested under ADDR '
                  '(run --fix-note-under-addr to restructure with venue name first):')
            for ln, level in note_addr_issues[:20]:
                print(f'  line {ln}: level-{level} NOTE under level-{level - 1} ADDR')
            if len(note_addr_issues) > 20:
                print(f'  ... and {len(note_addr_issues) - 20} more.')
        else:
            print('OK: no NOTE lines incorrectly nested under ADDR.')

        name_slash_issues = scan_name_slashes(args.gedfile)
        if name_slash_issues:
            errors = True
            print(f'\n{len(name_slash_issues)} NAME value(s) with multiple slash-delimited '
                  'sections (invalid per GEDCOM 5.5.1 §2.7.2 — requires manual correction):')
            for ln, val in name_slash_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(name_slash_issues) > 20:
                print(f'  ... and {len(name_slash_issues) - 20} more.')
        else:
            print('OK: all NAME values have valid slash structure.')

        sex_issues = scan_sex_values(args.gedfile)
        if sex_issues:
            errors = True
            print(f'\n{len(sex_issues)} SEX value(s) not in {{M, F, U}} '
                  '(invalid per GEDCOM 5.5.1 — requires manual correction):')
            for ln, val in sex_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(sex_issues) > 20:
                print(f'  ... and {len(sex_issues) - 20} more.')
        else:
            print('OK: all SEX values are valid (M, F, or U).')

        plac_form = scan_plac_form(args.gedfile)
        if plac_form is None:
            errors = True
            print('\nWARNING: no PLAC FORM declaration in header.')
            print('  GEDCOM 5.5.1 §2.7.3 recommends declaring the place hierarchy so')
            print('  importing software knows how to interpret comma-separated PLAC values.')
            print('  Add to the HEAD block:')
            print('    1 PLAC')
            print('    2 FORM City, County, State, Country')
        else:
            print(f'OK: PLAC FORM declared in header: {plac_form!r}')

        plac_issues = scan_plac(args.gedfile)
        if plac_issues:
            errors = True
            print(f'\n{len(plac_issues)} PLAC value(s) with spacing/comma issues '
                  '(run --fix-places to normalize):')
            for ln, orig, fixed in plac_issues:
                print(f'  line {ln}: {orig!r}  →  {fixed!r}')
        else:
            print('OK: all PLAC values are well-formed.')

        addr_parts = scan_plac_address_parts(args.gedfile)
        if addr_parts:
            errors = True
            print(f'\n{len(addr_parts)} PLAC value(s) with misplaced address/descriptor parts '
                  '(run --fix-address-parts to move):')
            for ln, val, part, cat in addr_parts:
                tag = 'ADDR' if cat == 'addr' else 'NOTE'
                print(f'  line {ln}: {val!r}  →  move {part!r} to {tag}')
        else:
            print('OK: no misplaced address parts in PLAC values.')

        no_year, bad_format = scan(args.gedfile)

        if no_year:
            errors = True
            print(f'\n{len(no_year)} DATE line(s) with no extractable year '
                  '(require manual correction):')
            for ln, val in no_year:
                print(f'  line {ln}: {val!r}')
        else:
            print('OK: all DATE values contain an extractable year.')

        if bad_format:
            errors = True
            print(f'\n{len(bad_format)} level-2 DATE value(s) not in GEDCOM 5.5.1 format '
                  '(run --fix-dates to auto-normalize):')
            for ln, val in bad_format[:40]:
                print(f'  line {ln}: {val!r}')
            if len(bad_format) > 40:
                print(f'  ... and {len(bad_format) - 40} more.')
        else:
            print('OK: all level-2 DATE values conform to GEDCOM 5.5.1.')

        # ── New line-level checks ────────────────────────────────────────────

        header_issues = scan_header_required_fields(args.gedfile)
        if header_issues:
            errors = True
            print(f'\n{_ERR} {len(header_issues)} required HEAD field(s) missing:')
            for msg in header_issues:
                print(f'  {msg}')
        else:
            print('OK: HEAD block contains all required fields.')

        date_caps_issues = scan_date_month_caps(args.gedfile)
        if date_caps_issues:
            errors = True
            print(f'\n{_ERR} {len(date_caps_issues)} DATE value(s) with non-uppercase month '
                  'abbreviations (run --fix-date-caps to normalize):')
            for ln, val in date_caps_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(date_caps_issues) > 20:
                print(f'  ... and {len(date_caps_issues) - 20} more.')
        else:
            print('OK: all DATE month abbreviations are uppercase.')

        bare_events = scan_bare_event_tags(args.gedfile)
        if bare_events:
            print(f'\n{_WARN} {len(bare_events)} bare event tag(s) with no value and no '
                  "children (add 'Y' to assert or add subordinate data):")
            for ln, tag in bare_events[:20]:
                print(f'  line {ln}: 1 {tag}')
            if len(bare_events) > 20:
                print(f'  ... and {len(bare_events) - 20} more.')
        else:
            print('OK: no bare BIRT/CHR/DEAT tags without assertion.')

        untyped_events = scan_untyped_events(args.gedfile)
        if untyped_events:
            print(f'\n{_WARN} {len(untyped_events)} EVEN/FACT/IDNO tag(s) without a TYPE '
                  'child (required per GEDCOM 5.5.1):')
            for ln, tag, xref in untyped_events[:20]:
                print(f'  line {ln}: {xref} — 1 {tag} has no 2 TYPE')
            if len(untyped_events) > 20:
                print(f'  ... and {len(untyped_events) - 20} more.')
        else:
            print('OK: all EVEN/FACT/IDNO tags have a TYPE subordinate.')

        missing_sex = scan_missing_sex(args.gedfile)
        if missing_sex:
            print(f'\n{_INFO} {len(missing_sex)} individual(s) with no SEX tag:')
            for xref in missing_sex[:20]:
                print(f'  {xref}')
            if len(missing_sex) > 20:
                print(f'  ... and {len(missing_sex) - 20} more.')
        else:
            print('OK: all individuals have a SEX tag.')

        age_issues = scan_age_values(args.gedfile)
        if age_issues:
            errors = True
            print(f'\n{_ERR} {len(age_issues)} AGE value(s) not conforming to GEDCOM 5.5.1:')
            for ln, val in age_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(age_issues) > 20:
                print(f'  ... and {len(age_issues) - 20} more.')
        else:
            print('OK: all AGE values conform to GEDCOM 5.5.1.')

        resn_issues = scan_resn_values(args.gedfile)
        if resn_issues:
            errors = True
            print(f'\n{_ERR} {len(resn_issues)} RESN value(s) not in '
                  '{confidential, locked, privacy}:')
            for ln, val in resn_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(resn_issues) > 20:
                print(f'  ... and {len(resn_issues) - 20} more.')
        else:
            print('OK: all RESN values are valid.')

        pedi_issues = scan_pedi_values(args.gedfile)
        if pedi_issues:
            errors = True
            print(f'\n{_ERR} {len(pedi_issues)} PEDI value(s) not in '
                  '{adopted, birth, foster, sealing}:')
            for ln, val in pedi_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(pedi_issues) > 20:
                print(f'  ... and {len(pedi_issues) - 20} more.')
        else:
            print('OK: all PEDI values are valid.')

        conc_issues = scan_conc_cont(args.gedfile)
        if conc_issues:
            print(f'\n{_WARN} {len(conc_issues)} CONC/CONT anomaly/anomalies:')
            for ln, desc in conc_issues[:20]:
                print(f'  line {ln}: {desc}')
            if len(conc_issues) > 20:
                print(f'  ... and {len(conc_issues) - 20} more.')
        else:
            print('OK: no CONC/CONT structure anomalies.')

        xref_issues = scan_malformed_xrefs(args.gedfile)
        if xref_issues:
            print(f'\n{_WARN} {len(xref_issues)} malformed xref identifier(s):')
            for ln, desc in xref_issues[:20]:
                print(f'  line {ln}: {desc}')
            if len(xref_issues) > 20:
                print(f'  ... and {len(xref_issues) - 20} more.')
        else:
            print('OK: all xref identifiers are well-formed.')

        bare_at_issues = scan_bare_at_signs(args.gedfile)
        if bare_at_issues:
            print(f'\n{_WARN} {len(bare_at_issues)} bare \'@\' sign(s) in values '
                  '(should be \'@@\' per spec):')
            for ln, desc in bare_at_issues[:20]:
                print(f'  line {ln}: {desc}')
            if len(bare_at_issues) > 20:
                print(f'  ... and {len(bare_at_issues) - 20} more.')
        else:
            print("OK: no bare '@' signs found in values.")

        nickname_issues = scan_name_nicknames(args.gedfile)
        if nickname_issues:
            print(f'\n{_INFO} {len(nickname_issues)} NAME value(s) with quoted nicknames '
                  '(run --fix-nicknames to extract to NICK tags):')
            for ln, val in nickname_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(nickname_issues) > 20:
                print(f'  ... and {len(nickname_issues) - 20} more.')
        else:
            print('OK: no quoted nicknames found in NAME values.')

        name_piece_issues = scan_name_pieces(args.gedfile)
        if name_piece_issues:
            print(f'\n{_INFO} {len(name_piece_issues)} NAME value(s) missing GIVN or SURN '
                  'subordinates (run --fix-name-pieces to generate):')
            for ln, val in name_piece_issues[:10]:
                print(f'  line {ln}: {val!r}')
            if len(name_piece_issues) > 10:
                print(f'  ... and {len(name_piece_issues) - 10} more.')
        else:
            print('OK: all NAME values with slashes have GIVN/SURN subordinates.')

        dateless_issues = scan_dateless_dates(args.gedfile)
        if dateless_issues:
            errors = True
            print(f'\n{_ERR} {len(dateless_issues)} DATE value(s) with day+month but no year '
                  '(run --fix-dateless-dates to wrap as date phrases):')
            for ln, val in dateless_issues[:20]:
                print(f'  line {ln}: {val!r}')
            if len(dateless_issues) > 20:
                print(f'  ... and {len(dateless_issues) - 20} more.')
        else:
            print('OK: no day+month-only DATE values found.')

        occu_issues = scan_occu_length(args.gedfile)
        if occu_issues:
            print(f'\n{_INFO} {len(occu_issues)} OCCU value(s) exceeding 120 characters '
                  '(likely narrative — consider splitting to OCCU + NOTE):')
            for ln, length in occu_issues[:10]:
                print(f'  line {ln}: {length} characters')
            if len(occu_issues) > 10:
                print(f'  ... and {len(occu_issues) - 10} more.')
        else:
            print('OK: no overly long OCCU values.')

        nonstd_tags = scan_nonstandard_tags(args.gedfile)
        if nonstd_tags:
            total_nonstd = sum(nonstd_tags.values())
            print(f'\n{_INFO} {total_nonstd} non-standard (underscore-prefixed) tag(s) '
                  f'across {len(nonstd_tags)} distinct tag(s):')
            for tag, count in sorted(nonstd_tags.items(), key=lambda x: -x[1]):
                suggestion = _NONSTANDARD_TAG_SUGGESTIONS.get(tag, 'no known standard equivalent')
                print(f'  {tag}: {count} occurrence(s)  →  {suggestion}')
        else:
            print('OK: no non-standard underscore-prefixed tags found.')

        aka_issues = scan_fact_aka(args.gedfile)
        if aka_issues:
            print(f'\n{_WARN} {len(aka_issues)} FACT/AKA/NOTE block(s) that should be proper '
                  'NAME records (run --fix-aka-facts to convert):')
            for ln, note_val in aka_issues[:20]:
                print(f'  line {ln}: NOTE {note_val!r}')
            if len(aka_issues) > 20:
                print(f'  ... and {len(aka_issues) - 20} more.')
        else:
            print('OK: no FACT/AKA blocks needing conversion.')

        src_quality = scan_source_quality(args.gedfile)
        if src_quality['no_title']:
            print(f'\n{_INFO} {len(src_quality["no_title"])} source record(s) with no TITL:')
            for xref in src_quality['no_title'][:10]:
                print(f'  {xref}')
            if len(src_quality['no_title']) > 10:
                print(f'  ... and {len(src_quality["no_title"]) - 10} more.')
        if src_quality['no_authority']:
            print(f'\n{_INFO} {len(src_quality["no_authority"])} source record(s) with TITL '
                  'but no AUTH/PUBL/REPO:')
            for xref, title in src_quality['no_authority'][:10]:
                print(f'  {xref}: {title!r}')
            if len(src_quality['no_authority']) > 10:
                print(f'  ... and {len(src_quality["no_authority"]) - 10} more.')
        if src_quality['no_page']:
            print(f'\n{_INFO} {len(src_quality["no_page"])} source citation(s) with no PAGE '
                  'subordinate:')
            for ln, xref in src_quality['no_page'][:5]:
                print(f'  line {ln}: {xref}')
            if len(src_quality['no_page']) > 5:
                print(f'  ... and {len(src_quality["no_page"]) - 5} more.')
        if not any(src_quality.values()):
            print('OK: all source records have TITL and citations have PAGE.')

        citation_data_issues = scan_citation_data_children(args.gedfile)
        if citation_data_issues:
            errors = True
            print(f'\n{_WARN} {len(citation_data_issues)} invalid tag(s) under DATA '
                  'in source citation(s) (only DATE and TEXT are valid children):')
            for ln, tag, xref in citation_data_issues[:20]:
                print(f'  line {ln}: {tag} inside DATA of {xref}')
            if len(citation_data_issues) > 20:
                print(f'  ... and {len(citation_data_issues) - 20} more.')
        else:
            print('OK: no invalid children under citation DATA blocks.')

        same_sour_dupes = scan_same_sour_multiple_cites(args.gedfile)
        if same_sour_dupes:
            print(f'\n{_WARN} {len(same_sour_dupes)} potential-duplicate source citation(s) '
                  '(same SOUR xref cited twice on same event, child lines differ):')
            for ln, xref in same_sour_dupes[:20]:
                print(f'  line {ln}: {xref}')
            if len(same_sour_dupes) > 20:
                print(f'  ... and {len(same_sour_dupes) - 20} more.')
        else:
            print('OK: no same-source double-citations detected.')

        place_report = scan_place_consistency(args.gedfile)
        if place_report['similar_places']:
            print(f'\n{_INFO} {len(place_report["similar_places"])} likely-duplicate place '
                  'name pair(s) (similar spelling, same region/country):')
            for a, b in place_report['similar_places'][:10]:
                print(f'  {a!r}  ~  {b!r}')
            if len(place_report['similar_places']) > 10:
                print(f'  ... and {len(place_report["similar_places"]) - 10} more.')
        if place_report['country_inconsistencies']:
            print(f'\n{_INFO} {len(place_report["country_inconsistencies"])} country-name '
                  'inconsistency pair(s):')
            for a, b in place_report['country_inconsistencies'][:10]:
                print(f'  {a!r}  vs  {b!r}')
        if place_report['bare_countries']:
            bc = place_report['bare_countries']
            print(f'\n{_INFO} {len(bc)} bare country-name PLAC value(s) (no subdivision):')
            for val in sorted(set(bc))[:10]:
                print(f'  {val!r}')
        if not any(place_report.values()):
            print('OK: no place-name inconsistencies detected.')

        # -- Structural checks (require gedcom_merge parser) --
        try:
            broken = scan_broken_xrefs(args.gedfile)
            if broken:
                errors = True
                print(f'\n{len(broken)} broken cross-reference(s) '
                      '(run --fix-broken-xrefs to remove):')
                for msg in broken[:20]:
                    print(f'  {msg}')
                if len(broken) > 20:
                    print(f'  ... and {len(broken) - 20} more.')
            else:
                print('OK: no broken cross-references.')

            dup_fams = scan_duplicate_families(args.gedfile)
            if dup_fams:
                errors = True
                print(f'\n{len(dup_fams)} duplicate family pair(s) (same husband+wife) '
                      '(run --fix-duplicate-families to collapse):')
                for xa, xb in dup_fams[:20]:
                    print(f'  {xa} == {xb}')
                if len(dup_fams) > 20:
                    print(f'  ... and {len(dup_fams) - 20} more.')
            else:
                print('OK: no duplicate family records.')

            dup_srcs = scan_duplicate_sources_structural(args.gedfile)
            if dup_srcs:
                errors = True
                print(f'\n{len(dup_srcs)} duplicate source pair(s) (same normalized title):')
                for xa, xb in dup_srcs[:20]:
                    print(f'  {xa} == {xb}')
                if len(dup_srcs) > 20:
                    print(f'  ... and {len(dup_srcs) - 20} more.')
            else:
                print('OK: no duplicate source records.')

            orphans = scan_orphaned_individuals(args.gedfile)
            if orphans:
                print(f'\n{len(orphans)} orphaned individual(s) (no FAMS or FAMC links):')
                for xref in orphans[:20]:
                    print(f'  {xref}')
                if len(orphans) > 20:
                    print(f'  ... and {len(orphans) - 20} more.')
            else:
                print('OK: no orphaned individuals.')

            dup_names = scan_duplicate_names(args.gedfile)
            if dup_names:
                errors = True
                total = sum(len(v) for v in dup_names.values())
                print(f'\n{total} duplicate NAME entry/entries across '
                      f'{len(dup_names)} individual(s) '
                      '(run --fix-duplicate-names to remove):')
                for xref, names in list(dup_names.items())[:10]:
                    print(f'  {xref}: {names}')
                if len(dup_names) > 10:
                    print(f'  ... and {len(dup_names) - 10} more individual(s).')
            else:
                print('OK: no duplicate NAME entries.')

            unsorted_evs = scan_unsorted_events(args.gedfile)
            if unsorted_evs:
                errors = True
                print(f'\n{len(unsorted_evs)} record(s) with out-of-order events '
                      '(run --fix-sort-events to sort):')
                for msg in unsorted_evs[:20]:
                    print(f'  {msg}')
                if len(unsorted_evs) > 20:
                    print(f'  ... and {len(unsorted_evs) - 20} more.')
            else:
                print('OK: all events are in chronological order.')

            short_concs = scan_short_conc(args.gedfile)
            if short_concs:
                print(f'\n{_WARN} {len(short_concs)} CONC line(s) with very short values '
                      f'(<5 chars) — likely a note-encoding artifact '
                      f'(run --fix-note-reflow to re-encode):')
                by_xref: dict[str, list[tuple[int, str]]] = {}
                for ln, xref, val in short_concs:
                    by_xref.setdefault(xref, []).append((ln, val))
                for xref, entries in list(by_xref.items())[:10]:
                    sample = ', '.join(f'line {ln}: {val!r}' for ln, val in entries[:3])
                    print(f'  {xref}: {sample}')
                if len(by_xref) > 10:
                    print(f'  ... and {len(by_xref) - 10} more record(s).')
            else:
                print('OK: no abnormally short CONC lines.')

            mid_word_concs = scan_mid_word_conc(args.gedfile)
            if mid_word_concs:
                print(f'\n{_WARN} {len(mid_word_concs)} CONC line(s) with mid-word joins '
                      f'(letter+lowercase boundary) — bad wrapping '
                      f'(run --fix-note-reflow to re-encode):')
                mw_by_xref: dict[str, list[tuple[int, str]]] = {}
                for ln, xref, boundary in mid_word_concs:
                    mw_by_xref.setdefault(xref, []).append((ln, boundary))
                for xref, entries in list(mw_by_xref.items())[:10]:
                    sample = ', '.join(f'line {ln}: {b!r}' for ln, b in entries[:3])
                    print(f'  {xref}: {sample}')
                if len(mw_by_xref) > 10:
                    print(f'  ... and {len(mw_by_xref) - 10} more record(s).')
            else:
                print('OK: no mid-word CONC joins.')

            # ── New structural checks ────────────────────────────────────────

            dup_resi = scan_duplicate_resi(args.gedfile)
            if dup_resi:
                print(f'\n{_WARN} {len(dup_resi)} duplicate RESI event(s) '
                      '(same date+place on same individual — run --fix-duplicate-resi):')
                for xref, date_str, place_str in dup_resi[:20]:
                    print(f'  {xref}: date={date_str!r} place={place_str!r}')
                if len(dup_resi) > 20:
                    print(f'  ... and {len(dup_resi) - 20} more.')
            else:
                print('OK: no duplicate RESI events.')

            bidir_issues = scan_bidirectional_pointers(args.gedfile)
            if bidir_issues:
                print(f'\n{_WARN} {len(bidir_issues)} bidirectional pointer inconsistency/ies:')
                for msg in bidir_issues[:20]:
                    print(f'  {msg}')
                if len(bidir_issues) > 20:
                    print(f'  ... and {len(bidir_issues) - 20} more.')
            else:
                print('OK: all family–individual pointers are consistent in both directions.')

            date_logic = scan_date_consistency(args.gedfile)
            if date_logic:
                print(f'\n{_WARN} {len(date_logic)} date logical inconsistency/ies:')
                for msg in date_logic[:20]:
                    print(f'  {msg}')
                if len(date_logic) > 20:
                    print(f'  ... and {len(date_logic) - 20} more.')
            else:
                print('OK: no date logical inconsistencies detected.')

            # ── New content-quality checks ───────────────────────────────────

            name_map = _build_name_map(args.gedfile)

            godparent_issues = scan_godparent_count(args.gedfile)
            if godparent_issues:
                print(f'\n{_WARN} {len(godparent_issues)} individual(s) with unusual godparent count:')
                for xref, total, m_count, f_count in godparent_issues[:20]:
                    name = name_map.get(xref, xref)
                    reasons = []
                    if total > 2:
                        reasons.append(f'expected at most 2 total')
                    if m_count > 1:
                        reasons.append(f'expected at most 1 male godparent')
                    if f_count > 1:
                        reasons.append(f'expected at most 1 female godparent')
                    reason_str = ', '.join(reasons)
                    print(f'  {xref} {name}: {total} godparents ({m_count}M, {f_count}F) — {reason_str}')
                if len(godparent_issues) > 20:
                    print(f'  ... and {len(godparent_issues) - 20} more.')
            else:
                print('OK: no unusual godparent counts.')

            asso_no_rela = scan_asso_without_rela(args.gedfile)
            if asso_no_rela:
                errors = True
                print(f'\n{_ERR} {len(asso_no_rela)} ASSO record(s) missing required RELA tag:')
                for lineno, xref in asso_no_rela[:20]:
                    print(f'  line {lineno} ({xref})')
                if len(asso_no_rela) > 20:
                    print(f'  ... and {len(asso_no_rela) - 20} more.')
            else:
                print('OK: all ASSO records have a RELA tag.')

            sour_no_titl = scan_sour_without_titl(args.gedfile)
            if sour_no_titl:
                xref_list = ', '.join(sour_no_titl[:20])
                if len(sour_no_titl) > 20:
                    xref_list += f', ... and {len(sour_no_titl) - 20} more'
                print(f'\n{_WARN} {len(sour_no_titl)} SOUR record(s) have no TITL: {xref_list}')
            else:
                print('OK: all SOUR records have a TITL.')

            dangling_notes = scan_dangling_note_xrefs(args.gedfile)
            if dangling_notes:
                errors = True
                bad_xrefs = sorted({xref for _, xref in dangling_notes})
                print(f'\n{_ERR} {len(dangling_notes)} NOTE pointer(s) reference '
                      f'{len(bad_xrefs)} undefined shared-note xref(s):')
                for xref in bad_xrefs:
                    lns = [str(ln) for ln, x in dangling_notes if x == xref]
                    print(f'  {xref} — line(s): {", ".join(lns[:5])}'
                          + (f' (+{len(lns)-5} more)' if len(lns) > 5 else ''))
            else:
                print('OK: all NOTE pointers resolve to defined shared notes.')

            rec_order = scan_record_order(args.gedfile)
            if rec_order:
                errors = True
                print(f'\n{_ERR} {len(rec_order)} top-level record(s) out of canonical order '
                      '(run --fix-record-order to reorder):')
                for msg in rec_order[:20]:
                    print(f'  {msg}')
                if len(rec_order) > 20:
                    print(f'  ... and {len(rec_order) - 20} more.')
            else:
                print('OK: top-level records are in canonical order '
                      '(HEAD, SUBM, INDI, FAM, SOUR, REPO, OBJE, NOTE, TRLR).')

            # ── Summary statistics ───────────────────────────────────────────
            try:
                from gedcom_merge.parser import parse_gedcom
                gf = parse_gedcom(args.gedfile)
                n_indi = len(gf.individuals)
                n_fam  = len(gf.families)
                n_sour = len(gf.sources)
            except Exception:
                n_indi = n_fam = n_sour = 0

            # Gather top issues for the summary
            _issue_rows = []
            if src_quality['no_page']:
                _issue_rows.append((len(src_quality['no_page']),
                                    'source citations without PAGE', _INFO))
            if dupe_sources:
                _issue_rows.append((len(dupe_sources),
                                    'exact-duplicate source citations', _WARN))
            if same_sour_dupes:
                _issue_rows.append((len(same_sour_dupes),
                                    'same-source double citations (potential)', _WARN))
            if citation_data_issues:
                _issue_rows.append((len(citation_data_issues),
                                    'invalid tags under citation DATA', _WARN))
            if name_piece_issues:
                _issue_rows.append((len(name_piece_issues),
                                    'NAME values missing GIVN/SURN', _INFO))
            if nickname_issues:
                _issue_rows.append((len(nickname_issues),
                                    'NAME values with quoted nicknames', _INFO))
            if place_report['bare_countries']:
                _issue_rows.append((len(place_report['bare_countries']),
                                    'bare country-name PLAC values', _INFO))
            if aka_issues:
                _issue_rows.append((len(aka_issues),
                                    'FACT/AKA blocks to convert', _WARN))
            if addr_plac_issues:
                _issue_rows.append((len(addr_plac_issues),
                                    'ADDR nested under PLAC', _ERR))
            if long_lines:
                _issue_rows.append((len(long_lines),
                                    'lines over 255 characters', _ERR))
            if no_year:
                _issue_rows.append((len(no_year),
                                    'DATE values with no year', _ERR))
            if bad_format:
                _issue_rows.append((len(bad_format),
                                    'DATE values with invalid format', _ERR))
            if godparent_issues:
                _issue_rows.append((len(godparent_issues),
                                    'individuals with unusual godparent count', _WARN))
            if asso_no_rela:
                _issue_rows.append((len(asso_no_rela),
                                    'ASSO records missing RELA tag', _ERR))
            if sour_no_titl:
                _issue_rows.append((len(sour_no_titl),
                                    'SOUR records without TITL', _WARN))
            _issue_rows.sort(key=lambda r: -r[0])

            _total_errors   = sum(1 for _, _, sev in _issue_rows if sev == _ERR)
            _total_warnings = sum(1 for _, _, sev in _issue_rows if sev == _WARN)
            _total_infos    = sum(1 for _, _, sev in _issue_rows if sev == _INFO)

            print('\n=== SUMMARY ===')
            if n_indi or n_fam or n_sour:
                print(f'Records: {n_indi:,} individuals, '
                      f'{n_fam:,} families, {n_sour:,} sources')
            print(f'Errors:   {sum(r[0] for r in _issue_rows if r[2] == _ERR)}')
            print(f'Warnings: {sum(r[0] for r in _issue_rows if r[2] == _WARN)}')
            print(f'Info:     {sum(r[0] for r in _issue_rows if r[2] == _INFO)}')
            if _issue_rows:
                print('\nTop issues:')
                for count, label, sev in _issue_rows[:10]:
                    print(f'  {count:>6,}  {label} ({sev})')

        except ImportError:
            print('\nNOTE: structural checks skipped (gedcom_merge module not available).')

        if errors:
            sys.exit(1)


if __name__ == '__main__':
    main()
