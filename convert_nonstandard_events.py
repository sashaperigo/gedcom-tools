#!/usr/bin/env python3
"""
convert_nonstandard_events.py — Convert non-standard GEDCOM event tags to standard.

Handles three Ancestry/FamilySearch proprietary event tags:

  _MILT  (military service)  ->  EVEN + TYPE Military Service
  _SEPR  (separation)        ->  EVEN + TYPE Separation
  _DCAUSE (death cause)      ->  CAUS injected into the next DEAT event
                                 (or a new standalone DEAT if none follows)

Usage:
  python convert_nonstandard_events.py yourfile.ged
  python convert_nonstandard_events.py yourfile.ged --output clean.ged
  python convert_nonstandard_events.py yourfile.ged --dry-run
"""

import argparse
import os
import re
import sys

_LEVEL_TAG_RE = re.compile(r'^(\d+) ([A-Z_][A-Z0-9_]*)')


def _level_tag(raw: str) -> tuple[int, str] | None:
    """Return (level, tag) for a GEDCOM line, or None if it doesn't match."""
    m = _LEVEL_TAG_RE.match(raw.rstrip('\n'))
    return (int(m.group(1)), m.group(2)) if m else None


def _collect_children(lines: list[str], start: int, parent_level: int) -> tuple[list[str], int]:
    """
    Starting at index `start`, collect all lines with level > parent_level.
    Returns (child_lines, next_index).
    """
    children = []
    i = start
    while i < len(lines):
        lt = _level_tag(lines[i])
        if lt is None or lt[0] > parent_level:
            children.append(lines[i])
            i += 1
        else:
            break
    return children, i


def convert_nonstandard_events(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Convert _MILT, _SEPR, and _DCAUSE blocks to standard GEDCOM.

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, do not write anything — just return statistics

    Returns
    -------
    dict with keys:
      'lines_read'      : total lines in the input file
      'lines_delta'     : lines added minus lines removed (positive = file grew)
      'milt_converted'  : number of _MILT blocks converted
      'sepr_converted'  : number of _SEPR blocks converted
      'dcause_converted': number of _DCAUSE blocks converted
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    lines_out: list[str] = []
    milt_converted = 0
    sepr_converted = 0
    dcause_converted = 0

    # pending_caus: lines to inject into the next DEAT (from _DCAUSE processing)
    # Each entry: list of raw line strings ('2 CAUS ...\n', '3 CONT ...\n', ...)
    pending_caus: list[str] = []

    i = 0
    while i < len(lines):
        raw = lines[i]
        lt = _level_tag(raw)

        # ------------------------------------------------------------------ #
        # _MILT / _SEPR: replace tag, prepend TYPE child                      #
        # ------------------------------------------------------------------ #
        if lt and lt[1] in ('_MILT', '_SEPR'):
            event_type = 'Military Service' if lt[1] == '_MILT' else 'Separation'
            level = lt[0]
            children, i = _collect_children(lines, i + 1, level)
            lines_out.append(f'{level} EVEN\n')
            lines_out.append(f'{level + 1} TYPE {event_type}\n')
            lines_out.extend(children)
            if lt[1] == '_MILT':
                milt_converted += 1
            else:
                sepr_converted += 1

        # ------------------------------------------------------------------ #
        # _DCAUSE: extract CAUS text, queue for injection into next DEAT      #
        # ------------------------------------------------------------------ #
        elif lt and lt[1] == '_DCAUSE':
            level = lt[0]
            children, i = _collect_children(lines, i + 1, level)
            # Build CAUS lines from the NOTE child (and any CONT continuations)
            caus_lines: list[str] = []
            for child_raw in children:
                child_lt = _level_tag(child_raw)
                if child_lt and child_lt[1] == 'NOTE':
                    # Convert "N NOTE text" → "N CAUS text"
                    caus_lines.append(
                        child_raw.replace(f'{child_lt[0]} NOTE ', f'{child_lt[0]} CAUS ', 1)
                    )
                else:
                    caus_lines.append(child_raw)
            pending_caus.extend(caus_lines)
            dcause_converted += 1

        # ------------------------------------------------------------------ #
        # DEAT: if we have a pending CAUS, inject it as the first child       #
        # ------------------------------------------------------------------ #
        elif lt and lt[1] == 'DEAT' and pending_caus:
            level = lt[0]
            lines_out.append(raw)
            # Adjust CAUS/CONT level numbers to sit under this DEAT
            for caus_raw in pending_caus:
                caus_lt = _level_tag(caus_raw)
                if caus_lt:
                    # Rebase: pending lines were built at level (dcause_level+1);
                    # they should be at (deat_level+1) and deeper.
                    # Since _DCAUSE is always level 1 and DEAT is always level 1,
                    # the levels already match — just append as-is.
                    lines_out.append(caus_raw)
                else:
                    lines_out.append(caus_raw)
            pending_caus = []
            i += 1

        # ------------------------------------------------------------------ #
        # Level-0 boundary: flush any pending CAUS as a standalone DEAT       #
        # ------------------------------------------------------------------ #
        elif lt and lt[0] == 0 and pending_caus:
            lines_out.append('1 DEAT\n')
            lines_out.extend(pending_caus)
            pending_caus = []
            lines_out.append(raw)
            i += 1

        else:
            lines_out.append(raw)
            i += 1

    # End of file: flush any remaining pending CAUS
    if pending_caus:
        lines_out.append('1 DEAT\n')
        lines_out.extend(pending_caus)
        pending_caus = []

    lines_delta = len(lines_out) - len(lines)
    result = {
        'lines_read': len(lines),
        'lines_delta': lines_delta,
        'milt_converted': milt_converted,
        'sepr_converted': sepr_converted,
        'dcause_converted': dcause_converted,
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
        description='Convert _MILT, _SEPR, _DCAUSE to standard GEDCOM event tags.',
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

    result = convert_nonstandard_events(
        args.gedfile, path_out=args.output, dry_run=args.dry_run,
    )

    mode = 'DRY RUN' if args.dry_run else 'CONVERT'
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read      : {result["lines_read"]}')
    print(f'  Lines delta     : {result["lines_delta"]:+d}')
    print(f'  _MILT converted : {result["milt_converted"]}')
    print(f'  _SEPR converted : {result["sepr_converted"]}')
    print(f'  _DCAUSE converted: {result["dcause_converted"]}')
    if not args.dry_run and result['lines_delta'] != 0:
        dest = args.output or args.gedfile
        print(f'  Written to      : {dest}')


if __name__ == '__main__':
    main()
