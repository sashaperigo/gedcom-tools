#!/usr/bin/env python3
"""
add_unaccented_names.py — Add unaccented AKA name entries for accented GEDCOM names.

For every individual whose NAME contains accented characters, a second NAME is
inserted immediately after the original name block, tagged as AKA:

    1 NAME Manon /Pérez/
    2 GIVN Manon
    2 SURN Pérez
    1 NAME Manon /Perez/
    2 TYPE AKA

Transliteration rules:
  - ä → ae,  Ä → Ae
  - ö → oe,  Ö → Oe
  - ü → ue,  Ü → Ue
  - All other combining diacritics → stripped via Unicode NFD normalization

A name is skipped if:
  - It contains no accented characters (unaccented == original).
  - The individual already has a NAME entry whose value matches the unaccented form.

Usage:
  python add_unaccented_names.py yourfile.ged
  python add_unaccented_names.py yourfile.ged --output clean.ged
  python add_unaccented_names.py yourfile.ged --dry-run
"""

import argparse
import os
import re
import sys
import unicodedata

from gedcom_io import level, write_lines

_L0_RE = re.compile(r'^0 ')
_INDI_RE = re.compile(r'^0 @[^@]+@ INDI\b')
_XREF_RE = re.compile(r'^0 (@[^@]+@)')
_NAME_RE = re.compile(r'^(1 NAME )(.+)$')

_UMLAUT_MAP = str.maketrans({
    'ä': 'ae', 'Ä': 'Ae',
    'ö': 'oe', 'Ö': 'Oe',
    'ü': 'ue', 'Ü': 'Ue',
})


def _remove_accents(val: str) -> str:
    """
    Return an unaccented version of val.

    German umlauts are expanded (ö→oe, ä→ae, ü→ue); all other combining
    diacritics are stripped via Unicode NFD normalization.
    """
    val = val.translate(_UMLAUT_MAP)
    nfd = unicodedata.normalize('NFD', val)
    return ''.join(c for c in nfd if not unicodedata.combining(c))


def _has_accent(val: str) -> bool:
    return _remove_accents(val) != val


def add_unaccented_names(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Add unaccented AKA NAME entries for every accented name in path_in.

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, do not write anything — just return statistics

    Returns
    -------
    dict with keys:
      'lines_read'  : total lines in the input file
      'lines_delta' : lines added (2 per AKA: NAME + TYPE)
      'names_added' : number of AKA entries inserted
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    # Pass 1: collect all existing NAME values per INDI xref (for dedup).
    indi_names: dict[str, set[str]] = {}
    current_xref: str | None = None
    for raw in lines:
        line = raw.rstrip('\n')
        if _INDI_RE.match(line):
            m = _XREF_RE.match(line)
            current_xref = m.group(1) if m else None
            indi_names.setdefault(current_xref, set())
        elif _L0_RE.match(line):
            current_xref = None
        elif current_xref is not None:
            m = _NAME_RE.match(line)
            if m:
                indi_names[current_xref].add(m.group(2))

    # Pass 2: build output, inserting AKA lines after each accented NAME block.
    lines_out: list[str] = []
    names_added = 0
    current_xref = None
    in_indi = False
    i = 0

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip('\n')

        if _L0_RE.match(line):
            in_indi = bool(_INDI_RE.match(line))
            m = _XREF_RE.match(line)
            current_xref = m.group(1) if (m and in_indi) else None
            lines_out.append(raw)
            i += 1
            continue

        if in_indi and current_xref is not None:
            m = _NAME_RE.match(line)
            if m:
                name_val = m.group(2)
                lines_out.append(raw)
                i += 1

                # Consume level-2+ children of this NAME block
                while i < len(lines):
                    child_line = lines[i].rstrip('\n')
                    lv = level(child_line)
                    if lv is not None and lv >= 2:
                        lines_out.append(lines[i])
                        i += 1
                    else:
                        break

                # Insert AKA if warranted
                if _has_accent(name_val):
                    unaccented = _remove_accents(name_val)
                    existing = indi_names.get(current_xref, set())
                    if unaccented not in existing:
                        if dry_run:
                            print(f'  {current_xref}: {name_val!r}  →  {unaccented!r}')
                        else:
                            lines_out.append(f'1 NAME {unaccented}\n')
                            lines_out.append('2 TYPE AKA\n')
                        # Update in-memory set to prevent duplicate AKAs within same run
                        indi_names.setdefault(current_xref, set()).add(unaccented)
                        names_added += 1
                continue

        lines_out.append(raw)
        i += 1

    lines_delta = len(lines_out) - len(lines)
    result = {
        'lines_read': len(lines),
        'lines_delta': lines_delta,
        'names_added': names_added,
    }

    write_lines(lines_out, path_in, path_out, dry_run, changed=bool(names_added))

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Add unaccented AKA name entries for accented GEDCOM names.',
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

    result = add_unaccented_names(
        args.gedfile, path_out=args.output, dry_run=args.dry_run,
    )

    mode = 'DRY RUN' if args.dry_run else 'ADD AKA'
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read  : {result["lines_read"]}')
    print(f'  Names added : {result["names_added"]}')
    print(f'  Lines delta : {result["lines_delta"]:+d}')
    if not args.dry_run and result['names_added']:
        dest = args.output or args.gedfile
        print(f'  Written to  : {dest}')


if __name__ == '__main__':
    main()
