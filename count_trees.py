#!/usr/bin/env python3
"""
count_trees.py — Count connected family trees in a GEDCOM file.

Builds an undirected graph where every individual (INDI) is a node and every
family record (FAM) creates edges between all its members (HUSB, WIFE, CHIL).
Connected components of this graph are the distinct family trees.

Usage:
  python count_trees.py yourfile.ged
"""

import argparse
import os
import re
import sys

_INDI_RE = re.compile(r'^0 (@[^@]+@) INDI\b')
_FAM_RE  = re.compile(r'^0 (@[^@]+@) FAM\b')
_MBR_RE  = re.compile(r'^1 (?:HUSB|WIFE|CHIL) (@[^@]+@)$')


# ---------------------------------------------------------------------------
# Union-Find with path compression and union by rank
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, items: set[str]) -> None:
        self._parent: dict[str, str] = {x: x for x in items}
        self._rank:   dict[str, int] = {x: 0 for x in items}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path halving
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def components(self) -> list[list[str]]:
        """Return a list of connected components (each a list of xrefs)."""
        groups: dict[str, list[str]] = {}
        for x in self._parent:
            root = self.find(x)
            groups.setdefault(root, []).append(x)
        return list(groups.values())


# ---------------------------------------------------------------------------
# GEDCOM parsing
# ---------------------------------------------------------------------------

def _parse_graph(lines: list[str]) -> tuple[set[str], list[list[str]]]:
    """
    Return (indi_xrefs, fam_member_lists).
    fam_member_lists: one list per FAM, containing the xrefs of its members.
    """
    indi_xrefs: set[str] = set()
    fam_members: list[list[str]] = []
    current_fam: list[str] | None = None

    for raw in lines:
        line = raw.rstrip('\n')

        m = _INDI_RE.match(line)
        if m:
            indi_xrefs.add(m.group(1))
            current_fam = None
            continue

        m = _FAM_RE.match(line)
        if m:
            current_fam = []
            fam_members.append(current_fam)
            continue

        if line.startswith('0 '):
            current_fam = None
            continue

        if current_fam is not None:
            m = _MBR_RE.match(line)
            if m:
                current_fam.append(m.group(1))

    return indi_xrefs, fam_members


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def count_trees(path_in: str) -> dict:
    """
    Count connected family trees in a GEDCOM file.

    Returns dict with:
      'tree_count'        : number of distinct trees
      'trees'             : list of tree sizes (ints), sorted descending
      'total_individuals' : total number of INDI records
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    indi_xrefs, fam_members = _parse_graph(lines)

    if not indi_xrefs:
        return {'tree_count': 0, 'trees': [], 'total_individuals': 0}

    uf = _UnionFind(indi_xrefs)

    for members in fam_members:
        # Union all members of this FAM together
        for i in range(1, len(members)):
            # Only union if both xrefs are known INDIs (guard against bad data)
            if members[0] in indi_xrefs and members[i] in indi_xrefs:
                uf.union(members[0], members[i])

    components = uf.components()
    sizes = sorted((len(c) for c in components), reverse=True)

    return {
        'tree_count': len(sizes),
        'trees': sizes,
        'total_individuals': len(indi_xrefs),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Count connected family trees in a GEDCOM file.',
    )
    parser.add_argument('gedfile', help='Path to .ged file')
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    result = count_trees(args.gedfile)
    trees  = result['trees']
    total  = result['total_individuals']
    count  = result['tree_count']

    width = len(f'{total:,}')  # align numbers by the widest figure

    print(f'Trees : {count}')
    for i, size in enumerate(trees, 1):
        label = '  (main tree)' if i == 1 and count > 1 else ''
        print(f'  #{i:<3}: {size:{width},} individual{"s" if size != 1 else ""}{label}')
    print(f'Total : {total:,} individuals')


if __name__ == '__main__':
    main()
