#!/usr/bin/env python3
"""
purge_duplicate_events.py — Remove duplicate event blocks from a GEDCOM file.

INDI records (BIRT / DEAT):
  Two blocks of the same type are duplicates when they have identical DATE and
  PLAC values. Source citations are excluded from the comparison so that two
  events citing different sources are still recognised as duplicates if their
  DATE and PLAC match.

FAM records (MARR):
  Two MARR blocks are duplicates when:
    • same PLAC (or one absent)
    • compatible DATE — one absent; or both share the same 4-digit year
      (so "5 SEP 1920", "ABT 1920", and "1920" all match); or one is a
      BEF/AFT bound and the other's year strictly falls inside it
      (e.g. "26 DEC 1897" matches "BEF 1903" because 1897 < 1903).
    • no conflicting ADDR — one absent, or both equal

  Two BEF/AFT bounds never match each other unless identical. Different
  venues (ADDR) are a clear signal of a genuine second ceremony and are
  preserved.

When duplicates are found, the richest block (most non-null sub-fields) is kept
and any source sub-blocks from the others that are not already present are
appended to it. No source information is ever discarded.

Usage:
  # Merge in-place:
  python purge_duplicate_events.py yourfile.ged

  # Write merged output to a new file:
  python purge_duplicate_events.py yourfile.ged --output clean.ged

  # Preview what would change without writing:
  python purge_duplicate_events.py yourfile.ged --dry-run
"""

import argparse
import os
import re
import sys

from gedcom_io import level as _level, write_lines

# ---------------------------------------------------------------------------
# MARR date-compatibility helpers
# ---------------------------------------------------------------------------

_YEAR_RE  = re.compile(r'\b(\d{4})\b')
_BOUND_RE = re.compile(r'^(BEF|AFT)\s+', re.IGNORECASE)


def _marr_dates_compatible(da: str | None, db: str | None) -> bool:
    """True if da and db could plausibly refer to the same marriage event.

    Null matches anything. Otherwise:
      • Identical strings always match.
      • If both have BEF/AFT prefixes, they must be identical (handled above).
      • If exactly one has a BEF/AFT prefix, the other is compatible when its
        year strictly falls inside the bound — e.g. "26 DEC 1897" is a more
        specific version of "BEF 1903" (1897 < 1903).  The same-year case is
        NOT compatible ("1920" is not strictly before "BEF 1920").
      • Otherwise two dates are compatible when they share the same 4-digit
        year, so "5 SEP 1920", "ABT 1920", and "1920" all match.
    """
    if not da or not db:
        return True
    if da == db:
        return True

    bound_a = _BOUND_RE.match(da)
    bound_b = _BOUND_RE.match(db)

    if bound_a and bound_b:
        # Both are directional bounds and not identical — not compatible.
        return False

    if bound_a or bound_b:
        # Exactly one side is a BEF/AFT bound.
        bound_str, other_str = (da, db) if bound_a else (db, da)
        prefix = _BOUND_RE.match(bound_str).group(1).upper()
        y_bound = _YEAR_RE.search(bound_str)
        y_other = _YEAR_RE.search(other_str)
        if not y_bound or not y_other:
            return False
        bound_year = int(y_bound.group(1))
        other_year = int(y_other.group(1))
        if prefix == 'BEF':
            return other_year < bound_year
        else:  # AFT
            return other_year > bound_year

    ya, yb = _YEAR_RE.search(da), _YEAR_RE.search(db)
    return bool(ya and yb and ya.group(1) == yb.group(1))


def _marr_blocks_are_duplicate(a: dict, b: dict) -> bool:
    """Return True if two parsed MARR event dicts represent the same ceremony."""
    # Different non-null places → distinct
    if a.get('plac') and b.get('plac') and a['plac'] != b['plac']:
        return False
    # Different non-null venues → distinct ceremonies
    if a.get('addr') and b.get('addr') and a['addr'] != b['addr']:
        return False
    return _marr_dates_compatible(a.get('date'), b.get('date'))


def _richness(p: dict) -> int:
    """Count non-null content fields (DATE, PLAC, ADDR, NOTE) in a parsed block."""
    return sum(1 for f in ('date', 'plac', 'addr', 'note') if p.get(f))


# ---------------------------------------------------------------------------
# Block reconstruction helper (shared by INDI and FAM processing)
# ---------------------------------------------------------------------------

def _apply_block_changes(
    rec_lines: list[str],
    block_spans: list[tuple[int, int]],
    to_remove: set[int],
    replacements: dict[int, list[str]],
) -> list[str]:
    """Reconstruct rec_lines, skipping removed blocks and splicing in replacements."""
    block_starts = {start: i for i, (start, _) in enumerate(block_spans)}
    block_end_map = {start: end for start, end in block_spans}
    new_rec: list[str] = []
    i = 0
    while i < len(rec_lines):
        if i in block_starts:
            bidx = block_starts[i]
            end = block_end_map[i]
            if bidx in to_remove:
                pass  # skip the duplicate block
            elif bidx in replacements:
                new_rec.extend(replacements[bidx])
            else:
                new_rec.extend(rec_lines[i:end])
            i = end
        else:
            new_rec.append(rec_lines[i])
            i += 1
    return new_rec


def _extract_source_blocks(event_body: list[str]) -> list[tuple[str, ...]]:
    """
    Extract source sub-blocks from the body lines of an event block
    (i.e. all lines after the '1 BIRT'/'1 DEAT' header, at level 2+).

    Returns a list of blocks, each represented as a tuple of strings
    (one per line). Using a tuple makes blocks hashable for deduplication.
    """
    blocks: list[tuple[str, ...]] = []
    current: list[str] = []
    for line in event_body:
        if re.match(r'^2 SOUR ', line):
            if current:
                blocks.append(tuple(current))
            current = [line]
        elif current and re.match(r'^[3-9] ', line):
            current.append(line)
        else:
            if current:
                blocks.append(tuple(current))
                current = []
    if current:
        blocks.append(tuple(current))
    return blocks


def _parse_event_block(block_lines: list[str]) -> dict:
    """
    Parse a single event block (all lines from the '1 BIRT'/'1 DEAT' header
    through its last sub-line) into its components.

    Returns a dict with:
      'header' : the level-1 line (str)
      'body'   : all subsequent lines (list[str])
      'date'   : value of the 2 DATE line, or None
      'plac'   : value of the 2 PLAC line, or None
      'sources': list[tuple[str,...]] — source sub-blocks (hashable)
    """
    header = block_lines[0]
    body = block_lines[1:]
    date = next(
        (re.match(r'^2 DATE (.+)', l).group(1).strip()
         for l in body if re.match(r'^2 DATE ', l)),
        None,
    )
    plac = next(
        (re.match(r'^2 PLAC (.+)', l).group(1).strip()
         for l in body if re.match(r'^2 PLAC ', l)),
        None,
    )
    addr = next(
        (re.match(r'^2 ADDR (.+)', l).group(1).strip()
         for l in body if re.match(r'^2 ADDR ', l)),
        None,
    )
    note = next(
        (re.match(r'^2 NOTE (.+)', l).group(1).strip()
         for l in body if re.match(r'^2 NOTE ', l)),
        None,
    )
    return {
        'header': header,
        'body': body,
        'date': date,
        'plac': plac,
        'addr': addr,
        'note': note,
        'sources': _extract_source_blocks(body),
    }


def _merge_into_keeper(keeper: dict, duplicate: dict) -> tuple[list[str], int]:
    """
    Merge a duplicate event block into its keeper, appending any source
    sub-blocks from the duplicate that are not already present in the keeper.

    Returns (merged_lines, sources_added).
    """
    existing_sources: set[tuple[str, ...]] = set(keeper['sources'])
    new_sources = [s for s in duplicate['sources'] if s not in existing_sources]

    merged = [keeper['header']] + keeper['body']
    for src_block in new_sources:
        merged.extend(src_block)

    return merged, len(new_sources)


def _collect_event_blocks(rec_lines: list[str], tag: str) -> list[tuple[int, int]]:
    """
    Find all blocks for `tag` (e.g. 'BIRT') within a record's lines.
    Returns list of (start, end) index pairs (end is exclusive).
    """
    blocks: list[tuple[int, int]] = []
    i = 0
    while i < len(rec_lines):
        if re.match(rf'^1 {re.escape(tag)}\b', rec_lines[i]):
            start = i
            i += 1
            while i < len(rec_lines) and re.match(r'^[2-9] ', rec_lines[i]):
                i += 1
            blocks.append((start, i))
        else:
            i += 1
    return blocks


def _process_indi_record(rec_lines: list[str]) -> tuple[list[str], int, int]:
    """
    Process a single INDI record, merging duplicate BIRT/DEAT blocks.

    Returns (new_lines, events_merged, sources_added).
    """
    events_merged = 0
    sources_added = 0

    for tag in ('BIRT', 'DEAT'):
        block_spans = _collect_event_blocks(rec_lines, tag)
        if len(block_spans) < 2:
            continue

        # Group block indices by (date, plac) key
        groups: dict[tuple, list[int]] = {}
        parsed: list[dict] = []
        for start, end in block_spans:
            p = _parse_event_block(rec_lines[start:end])
            parsed.append(p)
            key = (p['date'], p['plac'])
            groups.setdefault(key, []).append(len(parsed) - 1)

        # Build a set of block indices to remove and a map of replacements
        to_remove: set[int] = set()
        replacements: dict[int, list[str]] = {}  # block_idx -> new lines

        for key, idxs in groups.items():
            if len(idxs) < 2:
                continue
            keeper_idx = idxs[0]
            keeper = parsed[keeper_idx]
            for dup_idx in idxs[1:]:
                merged_lines, n_new = _merge_into_keeper(keeper, parsed[dup_idx])
                replacements[keeper_idx] = merged_lines
                # Re-parse keeper so subsequent duplicates see all its sources
                keeper = _parse_event_block(merged_lines)
                parsed[keeper_idx] = keeper
                to_remove.add(dup_idx)
                events_merged += 1
                sources_added += n_new

        if not (to_remove or replacements):
            continue

        rec_lines = _apply_block_changes(rec_lines, block_spans, to_remove, replacements)

    return rec_lines, events_merged, sources_added


def _process_fam_record(rec_lines: list[str]) -> tuple[list[str], int, int]:
    """
    Process a single FAM record, merging duplicate MARR blocks.

    Uses a looser date-compatibility heuristic than INDI events: two MARRs are
    duplicates when they share the same PLAC (or one is absent), have compatible
    dates (same year, ignoring ABT/EST; BEF/AFT never match), and have no
    conflicting ADDR (different venues = genuine second ceremony).

    The richest block (most non-null sub-fields) is kept as the keeper.

    Returns (new_lines, events_merged, sources_added).
    """
    events_merged = 0
    sources_added = 0

    for tag in ('MARR',):
        block_spans = _collect_event_blocks(rec_lines, tag)
        if len(block_spans) < 2:
            continue

        parsed: list[dict] = [
            _parse_event_block(rec_lines[s:e]) for s, e in block_spans
        ]

        # Group indices by duplicate heuristic (O(n²) — FAMs have very few MARRs)
        used = [False] * len(parsed)
        groups: list[list[int]] = []
        for i, a in enumerate(parsed):
            if used[i]:
                continue
            group = [i]
            for j in range(i + 1, len(parsed)):
                if not used[j] and _marr_blocks_are_duplicate(a, parsed[j]):
                    group.append(j)
                    used[j] = True
            used[i] = True
            groups.append(group)

        to_remove: set[int] = set()
        replacements: dict[int, list[str]] = {}

        for group in groups:
            if len(group) < 2:
                continue
            # Keep the richest block; merge sources from the rest into it
            keeper_i = max(group, key=lambda k: _richness(parsed[k]))
            keeper = parsed[keeper_i]
            for dup_i in group:
                if dup_i == keeper_i:
                    continue
                merged_lines, n_new = _merge_into_keeper(keeper, parsed[dup_i])
                replacements[keeper_i] = merged_lines
                keeper = _parse_event_block(merged_lines)
                parsed[keeper_i] = keeper
                to_remove.add(dup_i)
                events_merged += 1
                sources_added += n_new

        if not (to_remove or replacements):
            continue

        rec_lines = _apply_block_changes(rec_lines, block_spans, to_remove, replacements)

    return rec_lines, events_merged, sources_added


def purge_duplicate_events(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Merge duplicate event blocks within INDI and FAM records.

    INDI (BIRT/DEAT): duplicates share the same DATE and PLAC values exactly.
    FAM (MARR): duplicates share the same PLAC, compatible DATE (same year),
    and no conflicting ADDR. The richest block is kept in each case; source
    sub-blocks from the others are merged into it.

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, compute statistics without writing anything

    Returns
    -------
    dict with keys:
      'lines_read'     : total lines in the input file
      'lines_removed'  : net lines removed
      'events_merged'  : number of duplicate event blocks consumed
      'sources_added'  : source sub-blocks migrated from duplicates to keepers
    """
    with open(path_in, encoding='utf-8') as f:
        all_lines = f.readlines()

    lines_out: list[str] = []
    total_events_merged = 0
    total_sources_added = 0

    i = 0
    while i < len(all_lines):
        line = all_lines[i]

        if re.match(r'^0 @.*@ INDI\b', line):
            rec_start = i
            i += 1
            while i < len(all_lines) and not re.match(r'^0 ', all_lines[i]):
                i += 1
            rec_lines = all_lines[rec_start:i]
            new_rec, merged, added = _process_indi_record(rec_lines)
            lines_out.extend(new_rec)
            total_events_merged += merged
            total_sources_added += added

        elif re.match(r'^0 @.*@ FAM\b', line):
            rec_start = i
            i += 1
            while i < len(all_lines) and not re.match(r'^0 ', all_lines[i]):
                i += 1
            rec_lines = all_lines[rec_start:i]
            new_rec, merged, added = _process_fam_record(rec_lines)
            lines_out.extend(new_rec)
            total_events_merged += merged
            total_sources_added += added

        else:
            lines_out.append(line)
            i += 1

    lines_removed = len(all_lines) - len(lines_out)
    result = {
        'lines_read': len(all_lines),
        'lines_removed': lines_removed,
        'events_merged': total_events_merged,
        'sources_added': total_sources_added,
    }

    write_lines(lines_out, path_in, path_out, dry_run, changed=lines_removed != 0 or total_sources_added > 0)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Merge duplicate event blocks in a GEDCOM file (INDI: BIRT/DEAT; FAM: MARR).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to .ged file')
    parser.add_argument(
        '--output', '-o', metavar='FILE',
        help='Write output here instead of overwriting the input file',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print a summary without writing anything',
    )
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    result = purge_duplicate_events(
        args.gedfile,
        path_out=args.output,
        dry_run=args.dry_run,
    )

    mode = 'DRY RUN' if args.dry_run else 'PURGE'
    dest = args.output or args.gedfile
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read     : {result["lines_read"]}')
    print(f'  Lines removed  : {result["lines_removed"]}')
    print(f'  Events merged  : {result["events_merged"]}')
    print(f'  Sources added  : {result["sources_added"]}')
    if not args.dry_run and result['events_merged'] > 0:
        print(f'  Written to     : {dest}')


if __name__ == '__main__':
    main()
