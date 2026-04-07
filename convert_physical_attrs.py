#!/usr/bin/env python3
"""
convert_physical_attrs.py — Convert _HEIG/_WEIG to standard GEDCOM DSCR tags.

Ancestry and some other genealogy tools export physical measurements as
non-standard underscore-prefixed tags:

    1 _HEIG 5'8"
    2 DATE 1942
    1 _WEIG 151 lbs
    2 DATE 1942

These are converted to the standard GEDCOM 5.5.1 DSCR (physical description)
attribute, preserving any child lines (DATE, PLAC, SOUR, etc.):

    1 DSCR Height: 5'8"
    2 DATE 1942
    1 DSCR Weight: 151 lbs
    2 DATE 1942

Multiple DSCR tags on the same individual are valid in GEDCOM 5.5.1 and will
coexist with any pre-existing DSCR entries.

Usage:
  python convert_physical_attrs.py yourfile.ged
  python convert_physical_attrs.py yourfile.ged --output clean.ged
  python convert_physical_attrs.py yourfile.ged --dry-run
"""

import argparse
import os
import re
import sys

_LEVEL_TAG_RE = re.compile(r'^(\d+) ([A-Z_][A-Z0-9_]*)')


def _level_tag(raw: str) -> tuple[int, str] | None:
    m = _LEVEL_TAG_RE.match(raw.rstrip('\n'))
    return (int(m.group(1)), m.group(2)) if m else None


def _line_value(raw: str) -> str:
    parts = raw.rstrip('\n').split(' ', 2)
    return parts[2] if len(parts) > 2 else ''


def convert_physical_attrs(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Convert _HEIG and _WEIG tags to standard DSCR entries.

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, do not write anything — just return statistics

    Returns
    -------
    dict with keys:
      'lines_read'     : total lines in the input file
      'lines_delta'    : net line change (always 0 — tag rename only)
      'heig_converted' : number of _HEIG tags converted
      'weig_converted' : number of _WEIG tags converted
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    lines_out: list[str] = []
    heig_converted = 0
    weig_converted = 0

    for raw in lines:
        lt = _level_tag(raw)
        if lt and lt[1] == '_HEIG':
            val = _line_value(raw)
            lines_out.append(f'{lt[0]} DSCR Height: {val}\n')
            heig_converted += 1
        elif lt and lt[1] == '_WEIG':
            val = _line_value(raw)
            lines_out.append(f'{lt[0]} DSCR Weight: {val}\n')
            weig_converted += 1
        else:
            lines_out.append(raw)

    lines_delta = len(lines_out) - len(lines)
    result = {
        'lines_read': len(lines),
        'lines_delta': lines_delta,
        'heig_converted': heig_converted,
        'weig_converted': weig_converted,
    }

    if not dry_run and (heig_converted or weig_converted):
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
        description='Convert _HEIG/_WEIG physical attribute tags to standard GEDCOM DSCR.',
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

    result = convert_physical_attrs(
        args.gedfile, path_out=args.output, dry_run=args.dry_run,
    )

    mode = 'DRY RUN' if args.dry_run else 'CONVERT'
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read      : {result["lines_read"]}')
    print(f'  _HEIG converted : {result["heig_converted"]}')
    print(f'  _WEIG converted : {result["weig_converted"]}')
    if not args.dry_run and (result['heig_converted'] or result['weig_converted']):
        dest = args.output or args.gedfile
        print(f'  Written to      : {dest}')


if __name__ == '__main__':
    main()
