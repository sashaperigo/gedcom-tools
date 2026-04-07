#!/usr/bin/env python3
"""
extract_occupations.py — Extract "Occupation: X" from event NOTE fields and add OCCU events.

Many GEDCOM files from Ancestry export occupation data embedded in NOTE fields on
residence or other events, e.g.:

    1 RESI
    2 DATE 1921
    2 PLAC Lincoln, Lincolnshire, England
    2 NOTE Occupation: Police Constable; Marital Status: Married

This script scans for such notes and inserts a proper OCCU event immediately after
the parent event block, preserving the original NOTE unchanged:

    1 RESI
    2 DATE 1921
    2 PLAC Lincoln, Lincolnshire, England
    2 NOTE Occupation: Police Constable; Marital Status: Married
    1 OCCU Police Constable
    2 DATE 1921

Usage:
  python extract_occupations.py yourfile.ged
  python extract_occupations.py yourfile.ged --output clean.ged
  python extract_occupations.py yourfile.ged --dry-run
"""

import argparse
import os
import re
import sys

_LEVEL_TAG_RE = re.compile(r'^(\d+) ([A-Z_][A-Z0-9_]*)')
_OCCUPATION_RE = re.compile(r'Occupation:\s*([^;]+)')
_L0_RE = re.compile(r'^0 ')
_INDI_START_RE = re.compile(r'^0 @[^@]+@ INDI\b')

# Occupations that are not meaningful roles and should be ignored.
IGNORED_OCCUPATIONS: frozenset[str] = frozenset({
    'home duties',
    'unpaid domestic duties',
    'student',
    'school',
    'scholar',
    'private means',
    'none',
    '(no occupation)',
})

# Substrings that indicate an institution name rather than an occupation role.
_INSTITUTION_MARKERS: tuple[str, ...] = (
    'university',
    'college',
    'institute',
    'academy',
)


def extract_occupation_from_note(note_val: str) -> str | None:
    """
    Extract the occupation string from a semicolon-separated note value.

    Returns None if no "Occupation:" field is found, or if the value is in
    IGNORED_OCCUPATIONS (case-insensitive).

    Examples:
        "Occupation: Tailor"                              → "Tailor"
        "Occupation: Police Constable; Marital Status: Married" → "Police Constable"
        "Marital Status: Married; Occupation: Tailor"     → "Tailor"
        "Occupation: Student"                             → None  (ignored)
        "Marital Status: Married"                         → None
    """
    m = _OCCUPATION_RE.search(note_val)
    if not m:
        return None
    occ = m.group(1).strip()
    occ_lower = occ.lower()
    if occ_lower in IGNORED_OCCUPATIONS:
        return None
    if any(marker in occ_lower for marker in _INSTITUTION_MARKERS):
        return None
    return occ


def _level_tag(raw: str) -> tuple[int, str] | None:
    """Return (level, tag) for a GEDCOM line, or None if it doesn't match."""
    m = _LEVEL_TAG_RE.match(raw.rstrip('\n'))
    return (int(m.group(1)), m.group(2)) if m else None


def _line_value(raw: str) -> str:
    """Return the value portion of a GEDCOM line (after 'LEVEL TAG ')."""
    stripped = raw.rstrip('\n')
    parts = stripped.split(' ', 2)
    return parts[2] if len(parts) > 2 else ''


def extract_occupations(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Scan path_in for events whose NOTE fields contain "Occupation: X" and
    insert a matching OCCU event immediately after each such event block.

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, do not write anything — just return statistics

    Returns
    -------
    dict with keys:
      'lines_read'  : total lines in the input file
      'lines_delta' : lines added (positive = file grew)
      'occu_added'  : number of OCCU events inserted
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    lines_out: list[str] = []
    occu_added = 0

    in_indi = False           # are we inside an INDI record?
    current_event_date: str | None = None   # DATE seen under current level-1 event
    pending_occu: str | None = None         # occupation value waiting to be flushed

    def _flush_pending() -> None:
        nonlocal occu_added, pending_occu
        if pending_occu is not None:
            lines_out.append(f'1 OCCU {pending_occu}\n')
            if current_event_date is not None:
                lines_out.append(f'2 DATE {current_event_date}\n')
            occu_added += 1
            pending_occu = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        lt = _level_tag(raw)

        if _L0_RE.match(raw):
            # Start of a new record (including xref lines like "0 @I1@ INDI")
            _flush_pending()
            in_indi = bool(_INDI_START_RE.match(raw))
            current_event_date = None
            lines_out.append(raw)
            i += 1

        elif lt and lt[0] == 1 and in_indi:
            # New level-1 tag within an INDI — flush pending OCCU before this line
            _flush_pending()
            current_event_date = None
            lines_out.append(raw)
            i += 1

        elif lt and lt[0] == 2 and in_indi:
            if lt[1] == 'DATE':
                current_event_date = _line_value(raw)
            elif lt[1] == 'NOTE':
                occ = extract_occupation_from_note(_line_value(raw))
                if occ is not None:
                    pending_occu = occ
            lines_out.append(raw)
            i += 1

        else:
            lines_out.append(raw)
            i += 1

    # End of file — flush any remaining pending OCCU
    _flush_pending()

    lines_delta = len(lines_out) - len(lines)
    result = {
        'lines_read': len(lines),
        'lines_delta': lines_delta,
        'occu_added': occu_added,
    }

    if not dry_run and lines_delta != 0:
        dest = path_out if path_out else path_in
        tmp = dest + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, dest)
    elif not dry_run and path_out and path_out != path_in:
        with open(path_out, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)

    return result


def purge_blocked_occupations(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Remove any existing '1 OCCU <value>' events whose value is in IGNORED_OCCUPATIONS,
    along with their level-2+ children (e.g. DATE).

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, do not write anything — just return statistics

    Returns
    -------
    dict with keys:
      'lines_read'   : total lines in the input file
      'lines_delta'  : lines removed (negative = file shrank)
      'occu_removed' : number of OCCU events removed
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    lines_out: list[str] = []
    occu_removed = 0

    i = 0
    while i < len(lines):
        raw = lines[i]
        lt = _level_tag(raw)

        if lt and lt[0] == 1 and lt[1] == 'OCCU':
            occ_val = _line_value(raw).strip()
            if occ_val.lower() in IGNORED_OCCUPATIONS:
                # Skip this OCCU line and all its level-2+ children
                i += 1
                while i < len(lines):
                    child_raw = lines[i]
                    if _L0_RE.match(child_raw):
                        break
                    child_lt = _level_tag(child_raw)
                    if child_lt is not None and child_lt[0] <= 1:
                        break
                    i += 1
                occu_removed += 1
                continue

        lines_out.append(raw)
        i += 1

    lines_delta = len(lines_out) - len(lines)
    result = {
        'lines_read': len(lines),
        'lines_delta': lines_delta,
        'occu_removed': occu_removed,
    }

    if not dry_run and lines_delta != 0:
        dest = path_out if path_out else path_in
        tmp = dest + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, dest)
    elif not dry_run and path_out and path_out != path_in:
        with open(path_out, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Extract Occupation notes and add OCCU events to a GEDCOM file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to .ged file')
    parser.add_argument('--output', '-o', metavar='FILE',
                        help='Write output here instead of overwriting input')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview changes without writing')
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    result = extract_occupations(
        args.gedfile, path_out=args.output, dry_run=args.dry_run,
    )

    mode = 'DRY RUN' if args.dry_run else 'EXTRACT'
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read  : {result["lines_read"]}')
    print(f'  Lines delta : {result["lines_delta"]:+d}')
    print(f'  OCCU added  : {result["occu_added"]}')
    if not args.dry_run and result['lines_delta'] != 0:
        dest = args.output or args.gedfile
        print(f'  Written to  : {dest}')


if __name__ == '__main__':
    main()
