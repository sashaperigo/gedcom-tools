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

# Rules applied sequentially by normalize_date(). Each entry is
# (pattern, replacement, flags). The full date-range rule is handled
# separately because it requires .strip() on captured groups.
_DATE_RULES: list[tuple[str, str, int]] = [
    # Approximate qualifiers → ABT
    (r'^(about|abt\.?|circa|ca\.?|approx\.?|maybe)\s+', 'ABT ', re.I),
    # Before / After
    (r'^(before|bef\.?)\s+', 'BEF ', re.I),
    (r'^(after|aft\.?)\s+', 'AFT ', re.I),
    # Plain "YYYY-YYYY"
    (r'^(\d{4})-(\d{4})$', r'BET \1 AND \2', 0),
    # "bet. YYYY-YYYY" or "between YYYY-YYYY"
    (r'^bet\.?\s+(\d{3,4})-(\d{3,4})$', r'BET \1 AND \2', re.I),
    (r'^between\s+(\d{3,4})-(\d{3,4})$', r'BET \1 AND \2', re.I),
    # "bet[ween] X and Y"
    (r'^bet(?:ween)?\.?\s+(\S+)\s+and\s+(\S+)$', r'BET \1 AND \2', re.I),
    # Ordinal day numbers: "1st", "2nd", "3rd", "4th" etc.
    (r'^(\d{1,2})(st|nd|rd|th)\s+', r'\1 ', re.I),
    # "Month D, YYYY" → "D Month YYYY"
    (r'^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$', r'\2 \1 \3', 0),
    # "D Month, YYYY" → "D Month YYYY"  (trailing comma)
    (r'^(\d{1,2})\s+([A-Za-z]+),\s*(\d{4})$', r'\1 \2 \3', 0),
    # "YYYY Month D" → "D Month YYYY"
    (r'^(\d{4})\s+([A-Za-z]+)\s+(\d{1,2})$', r'\3 \2 \1', 0),
]


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

    # "full date - full date" range (e.g. "Abt. 1569 - 1583") — handled
    # separately because it requires .strip() on captured groups.
    m = re.match(r'^(.+\d{4})\s*-\s*(.+\d{4})$', v)
    if m:
        v = f'BET {m.group(1).strip()} AND {m.group(2).strip()}'

    for pattern, replacement, flags in _DATE_RULES:
        v = re.sub(pattern, replacement, v, flags=flags)

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
    seen: dict = {}

    for start_i, _end_i, key, children_t in _iter_sour_blocks_with_context(lines):
        seen.setdefault(key, set())
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

    seen: dict = {}
    remove_ranges = []  # list of (start_idx, end_idx) to drop

    for start_i, end_i, key, children_t in _iter_sour_blocks_with_context(lines):
        seen.setdefault(key, set())
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


def fix_name_case(path: str, dry_run: bool = False) -> int:
    """
    Convert all-caps NAME values to title case. Returns number of lines changed.

    Only NAME lines where every alphabetic character is uppercase are touched;
    names that already contain any lowercase letter are left untouched.
    """
    with open(path, encoding='utf-8') as f:
        lines_in = f.readlines()

    lines_out = []
    changed = 0
    for lineno, raw in enumerate(lines_in, 1):
        line = raw.rstrip('\n')
        m = NAME_LINE_RE.match(line)
        if m:
            val = m.group(3)
            letters = [c for c in val if c.isalpha()]
            if letters and all(c.isupper() for c in letters):
                fixed = _name_to_title_case(val)
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


def scan_addr_under_plac(path: str) -> list[tuple[int, int]]:
    """
    Return list of (lineno, level) for ADDR lines that are direct children of
    PLAC lines (i.e., ADDR at level N+1 immediately following PLAC at level N).

    GEDCOM 5.5.1 does not define ADDR as a subordinate of PLAC. ADDR belongs
    as a sibling of PLAC (both children of the parent event), not nested under it.
    """
    violations: list[tuple[int, int]] = []
    prev_level: int | None = None
    prev_tag: str | None = None
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = re.match(r'^(\d+) ([A-Z_]+)', line)
            if not m:
                continue
            curr_level = int(m.group(1))
            curr_tag = m.group(2)
            if curr_tag == 'ADDR' and prev_tag == 'PLAC' and curr_level == prev_level + 1:
                violations.append((lineno, curr_level))
            prev_level = curr_level
            prev_tag = curr_tag
    return violations


def scan_note_under_plac(path: str) -> list[tuple[int, int]]:
    """
    Return list of (lineno, level) for NOTE lines that are direct children of
    PLAC lines (i.e., NOTE at level N+1 immediately following PLAC at level N),
    outside of any SOUR block.

    Venue names (church, cemetery, etc.) stored as NOTE children of PLAC should
    instead be ADDR siblings of PLAC, per the project convention.
    """
    violations: list[tuple[int, int]] = []
    prev_level: int | None = None
    prev_tag: str | None = None
    in_sour_depth: int | None = None  # level at which SOUR opened, or None
    with open(path, encoding='utf-8') as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = re.match(r'^(\d+) ([A-Z_]+)', line)
            if not m:
                continue
            curr_level = int(m.group(1))
            curr_tag = m.group(2)
            # Track SOUR entry/exit
            if curr_tag == 'SOUR' and prev_level is not None and curr_level > 0:
                in_sour_depth = curr_level
            elif in_sour_depth is not None and curr_level <= in_sour_depth:
                in_sour_depth = None
            if (curr_tag == 'NOTE' and prev_tag == 'PLAC'
                    and curr_level == prev_level + 1
                    and in_sour_depth is None):
                violations.append((lineno, curr_level))
            prev_level = curr_level
            prev_tag = curr_tag
    return violations


def scan_note_under_addr(path: str) -> list[tuple[int, int]]:
    """
    Return list of (lineno, level) for NOTE lines that are direct children of
    ADDR lines (i.e., NOTE at level N+1 immediately following ADDR at level N),
    outside of any SOUR block.

    These should be restructured so the venue name appears on the ADDR line
    and the street address becomes a CONT continuation.
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
            if curr_tag == 'SOUR' and prev_level is not None and curr_level > 0:
                in_sour_depth = curr_level
            elif in_sour_depth is not None and curr_level <= in_sour_depth:
                in_sour_depth = None
            if (curr_tag == 'NOTE' and prev_tag == 'ADDR'
                    and curr_level == prev_level + 1
                    and in_sour_depth is None):
                violations.append((lineno, curr_level))
            prev_level = curr_level
            prev_tag = curr_tag
    return violations


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
    fixes_applied += fix_trailing_whitespace(path, dry_run=dry_run)
    fixes_applied += fix_duplicate_sources(path, dry_run=dry_run)
    fixes_applied += fix_name_double_spaces(path, dry_run=dry_run)
    fixes_applied += fix_name_case(path, dry_run=dry_run)
    fixes_applied += fix_long_lines(path, dry_run=dry_run)
    fixes_applied += fix_addr_under_plac(path, dry_run=dry_run)
    fixes_applied += fix_note_under_plac(path, dry_run=dry_run)
    fixes_applied += fix_note_under_addr(path, dry_run=dry_run)
    fixes_applied += fix_plac(path, dry_run=dry_run)
    fixes_applied += fix_plac_address_parts(path, dry_run=dry_run)
    dates_fixed, _ = fix_file(path, dry_run=dry_run)
    fixes_applied += dates_fixed
    fixes_applied += fix_broken_xrefs(path, dry_run=dry_run)
    fixes_applied += fix_duplicate_families(path, dry_run=dry_run)
    fixes_applied += fix_duplicate_names(path, dry_run=dry_run)

    with open(path, encoding='utf-8') as f:
        lines_after = sum(1 for _ in f)

    return {
        'lines_read': lines_before,
        'lines_delta': lines_after - lines_before,
        'fixes_applied': fixes_applied,
    }


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
        args.fix_addr_under_plac = True
        args.fix_note_under_plac = True
        args.fix_note_under_addr = True
        args.fix_broken_xrefs = True
        args.fix_duplicate_families = True
        args.fix_duplicate_names = True

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
                args.fix_duplicate_sources, args.fix_addr_under_plac,
                args.fix_note_under_plac, args.fix_note_under_addr,
                args.fix_broken_xrefs, args.fix_duplicate_families,
                args.fix_duplicate_names]):
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

        except ImportError:
            print('\nNOTE: structural checks skipped (gedcom_merge module not available).')

        if errors:
            sys.exit(1)


if __name__ == '__main__':
    main()
