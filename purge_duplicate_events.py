#!/usr/bin/env python3
"""
purge_duplicate_events.py — Remove duplicate BIRT/DEAT event blocks from a GEDCOM file.

Two event blocks of the same type on the same individual are considered duplicates
when they have identical DATE and PLAC values (both fields compared, both may be absent).
Source citations are excluded from this comparison so that two events citing different
sources are still recognised as duplicates if their DATE and PLAC match.

When duplicates are found, the first block is kept and any source sub-blocks from
the duplicate that are not already present in the keeper are appended to it.
No source information is ever discarded.

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

_LEVEL_RE = re.compile(r'^(\d+) ')


def _level(line: str) -> int | None:
    m = _LEVEL_RE.match(line)
    return int(m.group(1)) if m else None


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
    return {
        'header': header,
        'body': body,
        'date': date,
        'plac': plac,
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

        # Reconstruct rec_lines with merges applied
        new_rec: list[str] = []
        block_idx = 0
        block_starts = {start: i for i, (start, _) in enumerate(block_spans)}
        block_end_map = {start: end for start, end in block_spans}
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

        rec_lines = new_rec

    return rec_lines, events_merged, sources_added


def purge_duplicate_events(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Merge duplicate BIRT/DEAT event blocks within each INDI record.

    Two blocks are duplicates when they share the same DATE and PLAC values.
    The first block is kept; source sub-blocks from the duplicate that are not
    already present in the keeper are appended to it.

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, compute statistics without writing anything

    Returns
    -------
    dict with keys:
      'lines_read'     : total lines in the input file
      'lines_removed'  : net lines removed (negative means lines were added
                         when sources migrated from a short duplicate to a
                         longer keeper; in practice always >= 0)
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
        if not re.match(r'^0 @.*@ INDI\b', line):
            lines_out.append(line)
            i += 1
            continue

        # Collect the full INDI record
        rec_start = i
        i += 1
        while i < len(all_lines) and not re.match(r'^0 ', all_lines[i]):
            i += 1
        rec_lines = all_lines[rec_start:i]

        new_rec, merged, added = _process_indi_record(rec_lines)
        lines_out.extend(new_rec)
        total_events_merged += merged
        total_sources_added += added

    lines_removed = len(all_lines) - len(lines_out)
    result = {
        'lines_read': len(all_lines),
        'lines_removed': lines_removed,
        'events_merged': total_events_merged,
        'sources_added': total_sources_added,
    }

    if not dry_run and (lines_removed != 0 or total_sources_added > 0):
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
        description='Merge duplicate BIRT/DEAT event blocks in a GEDCOM file.',
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
