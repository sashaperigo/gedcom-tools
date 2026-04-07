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

Notes:
  - Only level-2 DATE lines (event dates on INDI/FAM records) are touched by
    --fix-dates. Level-3/4 DATE lines inside DATA citation blocks are reported
    but never rewritten.
  - Lines that cannot be automatically normalized are reported as remaining
    violations after --fix-dates.
"""

import argparse
import os
import re
import sys

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

# ---------------------------------------------------------------------------
# Normalization rules (applied in order)
# ---------------------------------------------------------------------------

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
      - "1st / 2nd / 3rd / 4th" ordinals        → bare number
      - "Month D, YYYY"                         → D Month YYYY
      - "D Month, YYYY" (trailing comma)        → D Month YYYY
      - "YYYY Month D"                          → D Month YYYY
      - Non-English/full month names            → standard 3-letter abbrev
      - Collapse multiple spaces
    """
    v = val.strip()

    # Approximate qualifiers
    v = re.sub(r'^(about|abt\.?|circa|ca\.?|approx\.?|maybe)\s+', 'ABT ', v, flags=re.I)

    # Before / After
    v = re.sub(r'^(before|bef\.?)\s+', 'BEF ', v, flags=re.I)
    v = re.sub(r'^(after|aft\.?)\s+', 'AFT ', v, flags=re.I)

    # "full date - full date" range (e.g. "Abt. 1569 - 1583")
    m = re.match(r'^(.+\d{4})\s*-\s*(.+\d{4})$', v)
    if m:
        v = f'BET {m.group(1).strip()} AND {m.group(2).strip()}'

    # Plain "YYYY-YYYY"
    v = re.sub(r'^(\d{4})-(\d{4})$', r'BET \1 AND \2', v)

    # "bet. YYYY-YYYY" or "between YYYY-YYYY"
    v = re.sub(r'^bet\.?\s+(\d{3,4})-(\d{3,4})$', r'BET \1 AND \2', v, flags=re.I)
    v = re.sub(r'^between\s+(\d{3,4})-(\d{3,4})$', r'BET \1 AND \2', v, flags=re.I)

    # "bet[ween] X and Y"
    v = re.sub(r'^bet(?:ween)?\.?\s+(\S+)\s+and\s+(\S+)$', r'BET \1 AND \2', v, flags=re.I)

    # Ordinal day numbers: "1st", "2nd", "3rd", "4th" etc.
    v = re.sub(r'^(\d{1,2})(st|nd|rd|th)\s+', r'\1 ', v, flags=re.I)

    # "Month D, YYYY" → "D Month YYYY"
    v = re.sub(r'^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$', r'\2 \1 \3', v)

    # "D Month, YYYY" → "D Month YYYY"  (trailing comma)
    v = re.sub(r'^(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})$', r'\1 \2 \3', v)

    # "YYYY Month D" → "D Month YYYY"
    v = re.sub(r'^(\d{4})\s+([A-Za-z]+)\s+(\d{1,2})$', r'\3 \2 \1', v)

    # Normalize month names to 3-letter GEDCOM abbreviations
    v = MONTH_RE.sub(replace_month, v)

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


def scan_duplicate_sources(path: str):
    """
    Return list of (lineno, xref) for SOUR citation blocks that are exact
    duplicates of a previous citation of the same source under the same
    record/event (same xref AND identical child lines).
    """
    with open(path, encoding='utf-8') as f:
        lines = f.readlines()

    violations = []
    defn_re = re.compile(r'^0 ')
    current_rec = None
    current_event = None  # line index of current event start (unique per block)
    seen: dict = {}  # (rec, event_start_lineno, xref) -> set of children tuples

    for i, raw in enumerate(lines):
        line = raw.rstrip('\n')
        if defn_re.match(line):
            current_rec = line
            current_event = None
            seen = {}
            continue
        if line.startswith('1 '):
            current_event = i  # use line index so each event block is unique
            continue
        m = SOUR_CITE_LINE_RE.match(line)
        if m and current_rec:
            xref = m.group(2)
            key = (current_rec, current_event, xref)
            # collect children inline
            j = i + 1
            children = []
            while j < len(lines):
                child = lines[j].rstrip('\n')
                cm = _LEVEL_RE.match(child)
                if cm and int(cm.group(1)) <= int(m.group(1)):
                    break
                children.append(child)
                j += 1
            children_t = tuple(children)
            if key not in seen:
                seen[key] = set()
            if children_t in seen[key]:
                violations.append((i + 1, xref))
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

    defn_re = re.compile(r'^0 ')
    current_rec = None
    current_event = None  # line index of current event start (unique per block)
    seen: dict = {}
    remove_ranges = []  # list of (start_idx, end_idx) to drop

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
            current_event = i  # use line index so each event block is unique
            i += 1
            continue
        m = SOUR_CITE_LINE_RE.match(line)
        if m and current_rec:
            xref = m.group(2)
            level = int(m.group(1))
            j = i + 1
            while j < len(lines):
                child = lines[j].rstrip('\n')
                cm = _LEVEL_RE.match(child)
                if cm and int(cm.group(1)) <= level:
                    break
                j += 1
            children_t = tuple(lines[k].rstrip('\n') for k in range(i + 1, j))
            key = (current_rec, current_event, xref)
            if key not in seen:
                seen[key] = set()
            if children_t in seen[key]:
                if dry_run:
                    print(f'  line {i + 1}: duplicate {xref} under {current_event}')
                remove_ranges.append((i, j))
            else:
                seen[key].add(children_t)
            i = j
        else:
            i += 1

    if not dry_run and remove_ranges:
        # Build set of line indices to drop
        drop = set()
        for start, end in remove_ranges:
            drop.update(range(start, end))
        lines_out = [l for idx, l in enumerate(lines) if idx not in drop]
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

    m = re.match(r'^(\d+) ([A-Z]+) (.+)$', line)
    if not m:
        return [line]  # can't parse — leave alone

    level = int(m.group(1))
    tag = m.group(2)
    value = m.group(3)

    conc_prefix = f'{level + 1} CONC '
    first_prefix = f'{level} {tag} '

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

def scan_trailing_whitespace(path: str):
    """
    Return list of (lineno, repr(line)) for every line that has trailing
    whitespace (spaces or tabs before the newline).
    """
    violations = []
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            stripped = raw.rstrip('\n')
            if stripped != stripped.rstrip():
                violations.append((lineno, stripped))
    return violations


def fix_trailing_whitespace(path: str, dry_run: bool = False):
    """
    Strip trailing whitespace from every line in *path*.
    Returns the number of lines changed.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for lineno, raw in enumerate(lines_in, 1):
        clean = raw.rstrip('\n').rstrip() + '\n'
        if clean != raw:
            changed += 1
            if dry_run:
                print(f'  line {lineno}: {raw.rstrip(chr(10))!r}')
        lines_out.append(clean)

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
    r'\b(Avenue|Ave|Boulevard|Blvd|Road|Rd|Street|St|Lane|Ln|Drive|Dr'
    r'|Way|Court|Ct|Place|Pl|Terrace|Ter|Circle|Cir|Highway|Hwy'
    r'|Route|Rte|Alley|Aly|Parkway|Pkwy)\b', re.IGNORECASE)

_PLACE_KEYWORDS = re.compile(
    r'\b(Cemetery|Cemetary|Graveyard|Churchyard|Church|Chapel|Cathedral'
    r'|Hospital|Clinic|Sanitarium|Sanatorium|School|College|University'
    r'|Synagogue|Mosque|Temple|Crematorium|Crematory|Mortuary|Funeral'
    r'|Convent|Monastery|Asylum|Prison|Jail|Workhouse|Poorhouse'
    r'|Infirmary|Barracks|Fort|Camp|Plantation)\b', re.IGNORECASE)

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
        args.fix_places = True
        args.fix_address_parts = True
        args.fix_duplicate_sources = True
        args.fix_names = True
        args.fix_long_lines = True

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
    if not any([args.fix_dates, args.fix_whitespace, args.fix_places,
                args.fix_address_parts, args.fix_names, args.fix_long_lines,
                args.fix_duplicate_sources]):
        print(f'[CHECK] Scanning: {args.gedfile}')
        errors = False

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

        if errors:
            sys.exit(1)


if __name__ == '__main__':
    main()
