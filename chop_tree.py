#!/usr/bin/env python3
"""
chop_tree.py — Split a GEDCOM file in two at a given individual.

Given a person X, produces two clean files:

  File A (descendants): X + all descendants + their spouses.
    X's FAMC link is stripped — X becomes a root with no parents.

  File B (ancestors): X + all ancestors + X's siblings + X's direct spouse(s).
    X's FAMS family records are kept but with all CHIL lines removed.
    Siblings' own marriages and spouses' own families are stripped.

All FAMS/FAMC/HUSB/WIFE/CHIL pointer lines that would reference an absent
record are removed. SOUR, OBJE, NOTE and other auxiliary records are included
only if they are referenced by at least one included INDI or FAM record.
The original file is never modified.

Usage:
  python chop_tree.py @I42@ yourfile.ged --out-a descendants.ged --out-b ancestors.ged
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_LEVEL0_RE = re.compile(r'^0 (?:(@[^@]+@) )?(\S+)')
_L1_TAG_XREF_RE = re.compile(r'^1 ([A-Z]+) (@[^@]+@)\s*$')   # 1 TAG @xref@
_ANY_XREF_RE = re.compile(r'@([^@ \t]+)@')


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse(path: str) -> tuple[dict, list]:
    """
    Parse a GEDCOM file into a record index and an ordering list.

    Returns
    -------
    records : dict[key, {'tag': str, 'xref': str|None, 'lines': list[str]}]
              Key is the xref string (e.g. '@I1@') for xref records, or the
              keyword (e.g. 'HEAD', 'TRLR') for non-xref records.
    order   : list[str] of keys in file order
    """
    records: dict = {}
    order: list[str] = []
    current_key: str | None = None
    current_rec: dict | None = None

    for raw in Path(path).read_text(encoding='utf-8').splitlines(keepends=True):
        line = raw.rstrip('\r\n')
        m = _LEVEL0_RE.match(line)
        if m:
            if current_key is not None:
                records[current_key] = current_rec
                order.append(current_key)
            xref = m.group(1)
            tag = m.group(2)
            current_key = xref if xref else tag
            current_rec = {'tag': tag, 'xref': xref, 'lines': [raw]}
        elif current_rec is not None:
            current_rec['lines'].append(raw)

    if current_key is not None:
        records[current_key] = current_rec
        order.append(current_key)

    return records, order


# ---------------------------------------------------------------------------
# Graph extraction
# ---------------------------------------------------------------------------

def _build_graph(records: dict) -> tuple:
    """
    Extract INDI/FAM graph edges from the parsed record index.

    Returns
    -------
    indi_fams : dict[indi_xref, list[fam_xref]]  — FAMS references per individual
    indi_famc : dict[indi_xref, list[fam_xref]]  — FAMC references per individual
    fam_husb  : dict[fam_xref, str|None]          — HUSB per family
    fam_wife  : dict[fam_xref, str|None]          — WIFE per family
    fam_chil  : dict[fam_xref, list[indi_xref]]   — CHIL list per family
    """
    indi_fams: dict[str, list[str]] = defaultdict(list)
    indi_famc: dict[str, list[str]] = defaultdict(list)
    fam_husb: dict[str, str | None] = {}
    fam_wife: dict[str, str | None] = {}
    fam_chil: dict[str, list[str]] = defaultdict(list)

    for key, rec in records.items():
        if rec['tag'] == 'INDI':
            for raw in rec['lines'][1:]:
                m = _L1_TAG_XREF_RE.match(raw.rstrip('\r\n'))
                if not m:
                    continue
                tag, xref = m.group(1), m.group(2)
                if tag == 'FAMS':
                    indi_fams[key].append(xref)
                elif tag == 'FAMC':
                    indi_famc[key].append(xref)

        elif rec['tag'] == 'FAM':
            fam_husb[key] = None
            fam_wife[key] = None
            for raw in rec['lines'][1:]:
                m = _L1_TAG_XREF_RE.match(raw.rstrip('\r\n'))
                if not m:
                    continue
                tag, xref = m.group(1), m.group(2)
                if tag == 'HUSB':
                    fam_husb[key] = xref
                elif tag == 'WIFE':
                    fam_wife[key] = xref
                elif tag == 'CHIL':
                    fam_chil[key].append(xref)

    return indi_fams, indi_famc, fam_husb, fam_wife, fam_chil


# ---------------------------------------------------------------------------
# Set computation
# ---------------------------------------------------------------------------

def _descendants_sets(
    x_xref: str,
    indi_fams: dict,
    fam_husb: dict,
    fam_wife: dict,
    fam_chil: dict,
) -> tuple[set, set]:
    """
    Compute (indi_set, fam_set) for File A.

    Includes x, all descendants (recursive), and the spouse at each generation.
    Spouses are not recursed — only their own FAMS families that appear in the
    descendant chain are included.
    """
    indi_set: set[str] = {x_xref}
    fam_set: set[str] = set()
    queue = [x_xref]
    visited: set[str] = set()

    while queue:
        indi = queue.pop()
        if indi in visited:
            continue
        visited.add(indi)

        for fam_xref in indi_fams.get(indi, []):
            fam_set.add(fam_xref)
            husb = fam_husb.get(fam_xref)
            wife = fam_wife.get(fam_xref)

            # Include spouse (not recursed further)
            for person in (husb, wife):
                if person and person not in indi_set:
                    indi_set.add(person)

            # Include children and recurse
            for chil in fam_chil.get(fam_xref, []):
                if chil not in indi_set:
                    indi_set.add(chil)
                    queue.append(chil)

    return indi_set, fam_set


def _ancestors_sets(
    x_xref: str,
    indi_fams: dict,
    indi_famc: dict,
    fam_husb: dict,
    fam_wife: dict,
    fam_chil: dict,
) -> tuple[set, set]:
    """
    Compute (indi_set, fam_set) for File B.

    Includes x, all ancestors (recursive via FAMC), x's own siblings (other
    CHIL in x's birth families), and x's direct spouse(s). Sibling marriages
    and spouse birth families are excluded.

    X's marriage FAM records are included in fam_set, but when written, their
    CHIL lines will be stripped because children are not in indi_set.
    """
    indi_set: set[str] = {x_xref}
    fam_set: set[str] = set()

    # Include X's marriage family records (CHIL will be stripped at write time)
    for fam_xref in indi_fams.get(x_xref, []):
        fam_set.add(fam_xref)
        husb = fam_husb.get(fam_xref)
        wife = fam_wife.get(fam_xref)
        for person in (husb, wife):
            if person and person != x_xref:
                indi_set.add(person)  # spouse — not recursed

    # Walk the ancestor chain
    queue = [x_xref]
    visited: set[str] = set()

    while queue:
        indi = queue.pop()
        if indi in visited:
            continue
        visited.add(indi)

        for famc_xref in indi_famc.get(indi, []):
            fam_set.add(famc_xref)
            husb = fam_husb.get(famc_xref)
            wife = fam_wife.get(famc_xref)

            # Add parents and recurse
            for parent in (husb, wife):
                if parent and parent not in indi_set:
                    indi_set.add(parent)
                    queue.append(parent)

            # If this is X's own birth family, add siblings too
            if indi == x_xref:
                for sibling in fam_chil.get(famc_xref, []):
                    if sibling != x_xref:
                        indi_set.add(sibling)  # not recursed

    return indi_set, fam_set


# ---------------------------------------------------------------------------
# Auxiliary record collection
# ---------------------------------------------------------------------------

_STRUCTURAL_TAGS = frozenset({'INDI', 'FAM', 'HEAD', 'TRLR'})


def _collect_aux(records: dict, indi_set: set, fam_set: set) -> set:
    """
    Return the set of level-0 auxiliary record xrefs (SOUR, OBJE, NOTE, SUBM,
    etc.) that are referenced by any line in an included INDI, FAM, or HEAD record.
    """
    referenced: set[str] = set()
    scan_keys = list(indi_set) + list(fam_set) + ['HEAD']

    for key in scan_keys:
        rec = records.get(key)
        if rec is None:
            continue
        for raw in rec['lines']:
            for m in _ANY_XREF_RE.finditer(raw.rstrip('\r\n')):
                xref = f'@{m.group(1)}@'
                target = records.get(xref)
                if target and target['tag'] not in _STRUCTURAL_TAGS:
                    referenced.add(xref)

    return referenced


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _filter_indi_lines(lines: list[str], fam_set: set) -> list[str]:
    """Strip level-1 FAMS/FAMC lines that point to a FAM not in fam_set."""
    out = []
    for raw in lines:
        m = _L1_TAG_XREF_RE.match(raw.rstrip('\r\n'))
        if m and m.group(1) in ('FAMS', 'FAMC') and m.group(2) not in fam_set:
            continue
        out.append(raw)
    return out


def _filter_fam_lines(lines: list[str], indi_set: set) -> list[str]:
    """Strip level-1 HUSB/WIFE/CHIL lines that point to an INDI not in indi_set."""
    out = []
    for raw in lines:
        m = _L1_TAG_XREF_RE.match(raw.rstrip('\r\n'))
        if m and m.group(1) in ('HUSB', 'WIFE', 'CHIL') and m.group(2) not in indi_set:
            continue
        out.append(raw)
    return out


def _write_file(
    path: str,
    records: dict,
    order: list,
    indi_set: set,
    fam_set: set,
    aux_set: set,
) -> None:
    chunks: list[list[str]] = []

    for key in order:
        rec = records[key]
        tag = rec['tag']

        if tag == 'HEAD':
            chunks.append(rec['lines'])
        elif tag == 'TRLR':
            pass  # written last
        elif tag == 'INDI' and key in indi_set:
            chunks.append(_filter_indi_lines(rec['lines'], fam_set))
        elif tag == 'FAM' and key in fam_set:
            chunks.append(_filter_fam_lines(rec['lines'], indi_set))
        elif key in aux_set:
            chunks.append(rec['lines'])

    # TRLR always last
    if 'TRLR' in records:
        chunks.append(records['TRLR']['lines'])

    Path(path).write_text(''.join(''.join(chunk) for chunk in chunks), encoding='utf-8')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chop_tree(
    path_in: str,
    x_xref: str,
    path_out_a: str,
    path_out_b: str,
) -> None:
    """
    Chop a GEDCOM tree at individual x_xref, writing two output files.

    Parameters
    ----------
    path_in   : source GEDCOM file (never modified)
    x_xref    : xref of the individual to chop at (e.g. '@I42@')
    path_out_a: destination for the descendants file
    path_out_b: destination for the ancestors file
    """
    records, order = _parse(path_in)

    if x_xref not in records:
        raise ValueError(f'{x_xref!r} not found in {path_in!r}')
    if records[x_xref]['tag'] != 'INDI':
        raise ValueError(f'{x_xref!r} is not an INDI record')

    indi_fams, indi_famc, fam_husb, fam_wife, fam_chil = _build_graph(records)

    desc_indi, desc_fam = _descendants_sets(
        x_xref, indi_fams, fam_husb, fam_wife, fam_chil
    )
    anc_indi, anc_fam = _ancestors_sets(
        x_xref, indi_fams, indi_famc, fam_husb, fam_wife, fam_chil
    )

    desc_aux = _collect_aux(records, desc_indi, desc_fam)
    anc_aux = _collect_aux(records, anc_indi, anc_fam)

    _write_file(path_out_a, records, order, desc_indi, desc_fam, desc_aux)
    _write_file(path_out_b, records, order, anc_indi, anc_fam, anc_aux)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Split a GEDCOM file at a given individual.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('xref', help='Xref of the individual to chop at, e.g. @I42@')
    parser.add_argument('gedfile', help='Path to source .ged file')
    parser.add_argument('--out-a', required=True, metavar='FILE',
                        help='Output path for descendants file')
    parser.add_argument('--out-b', required=True, metavar='FILE',
                        help='Output path for ancestors file')
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    try:
        chop_tree(args.gedfile, args.xref, args.out_a, args.out_b)
    except ValueError as e:
        sys.exit(f'Error: {e}')

    print(f'Descendants → {args.out_a}')
    print(f'Ancestors   → {args.out_b}')


if __name__ == '__main__':
    main()
