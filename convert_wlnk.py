#!/usr/bin/env python3
"""
convert_wlnk.py — Convert Ancestry _WLNK blocks to standard GEDCOM.

Ancestry.com GEDCOM exports use `_WLNK` to attach titled web links to
individual records. Each block looks like:

    1 _WLNK
    2 TITL Some Title
    2 NOTE https://...url...

This script converts each block to standard GEDCOM:

  - Ancestry person URL + resolvable xref → ASSO + RELA
      1 ASSO @I382540076099@
      2 RELA Godmother

  - Ancestry person URL + unresolvable xref → NOTE fallback
      1 NOTE Godmother: Angela Dellatolla (person not in tree): https://...

  - Any other URL → NOTE
      1 NOTE Some Title: https://...url...

Usage:
  python convert_wlnk.py yourfile.ged
  python convert_wlnk.py yourfile.ged --output clean.ged
  python convert_wlnk.py yourfile.ged --dry-run
"""

import argparse
import os
import re
import sys

from gedcom_io import write_lines

ANCESTRY_PERSON_RE = re.compile(
    r'ancestry\.com/family-tree/person/tree/\d+/person/(\d+)'
)
_XREF_DEFN_RE = re.compile(r'^0 (@[^@]+@) ')
_L1_TAG_RE = re.compile(r'^1 ([A-Z_][A-Z0-9_]*)(?: (.*))?$')
_L2_TAG_RE = re.compile(r'^2 ([A-Z_][A-Z0-9_]*)(?: (.*))?$')


def _build_xref_set(lines: list[str]) -> set[str]:
    """Return the set of all xrefs defined in the file (e.g. {'@I123@', ...})."""
    xrefs = set()
    for line in lines:
        m = _XREF_DEFN_RE.match(line.rstrip('\n'))
        if m:
            xrefs.add(m.group(1))
    return xrefs


def _convert_wlnk_block(
    titl: str, note_url: str, xref_set: set[str]
) -> tuple[list[str], str]:
    """
    Return (replacement_lines, kind) for one _WLNK block.

    kind is one of: 'asso' | 'unresolved' | 'note'
    """
    m = ANCESTRY_PERSON_RE.search(note_url)
    if m:
        xref = f'@I{m.group(1)}@'
        rela = titl.split(':')[0].strip() if ':' in titl else titl.strip()
        if xref in xref_set:
            return [f'1 ASSO {xref}\n', f'2 RELA {rela}\n'], 'asso'
        else:
            return [f'1 NOTE {titl} (person not in tree): {note_url}\n'], 'unresolved'
    else:
        return [f'1 NOTE {titl}: {note_url}\n'], 'note'


def convert_wlnk(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Convert all _WLNK blocks in a GEDCOM file to ASSO or NOTE records.

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, do not write anything — just return statistics

    Returns
    -------
    dict with keys:
      'lines_read'    : total lines in the input file
      'lines_removed' : net lines removed (negative means lines were added)
      'asso_added'    : number of ASSO records created
      'notes_added'   : number of NOTE lines created (including unresolved fallbacks)
      'unresolved'    : number of Ancestry URLs that had no matching xref
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    xref_set = _build_xref_set(lines)

    lines_out: list[str] = []
    asso_added = 0
    notes_added = 0
    unresolved = 0

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip('\n')

        m1 = _L1_TAG_RE.match(line)
        if m1 and m1.group(1) == '_WLNK':
            # Collect child lines (level 2+) for this _WLNK block
            titl = ''
            note_url = ''
            i += 1
            while i < len(lines):
                child = lines[i].rstrip('\n')
                m2 = _L2_TAG_RE.match(child)
                if m2:
                    tag, val = m2.group(1), (m2.group(2) or '').strip()
                    if tag == 'TITL':
                        titl = val
                    elif tag == 'NOTE':
                        note_url = val
                    i += 1
                elif re.match(r'^[3-9] ', child):
                    # deeper continuation lines — skip
                    i += 1
                else:
                    break  # back to level 0 or 1

            replacement, kind = _convert_wlnk_block(titl, note_url, xref_set)
            lines_out.extend(replacement)
            if kind == 'asso':
                asso_added += 1
            elif kind == 'unresolved':
                unresolved += 1
                notes_added += 1
            else:
                notes_added += 1
        else:
            lines_out.append(raw)
            i += 1

    lines_removed = len(lines) - len(lines_out)
    result = {
        'lines_read': len(lines),
        'lines_removed': lines_removed,
        'asso_added': asso_added,
        'notes_added': notes_added,
        'unresolved': unresolved,
    }

    write_lines(lines_out, path_in, path_out, dry_run, changed=lines_removed != 0)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Convert Ancestry _WLNK blocks to standard GEDCOM ASSO/NOTE.',
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

    result = convert_wlnk(args.gedfile, path_out=args.output, dry_run=args.dry_run)

    mode = 'DRY RUN' if args.dry_run else 'CONVERT'
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read    : {result["lines_read"]}')
    print(f'  Lines removed : {result["lines_removed"]}')
    print(f'  ASSO added    : {result["asso_added"]}')
    print(f'  NOTEs added   : {result["notes_added"]}')
    print(f'  Unresolved    : {result["unresolved"]} (Ancestry URLs with no matching xref)')
    if not args.dry_run and result['lines_removed'] != 0:
        dest = args.output or args.gedfile
        print(f'  Written to    : {dest}')


if __name__ == '__main__':
    main()
