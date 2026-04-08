#!/usr/bin/env python3
"""
export_minimal.py — Export a compact version of a GEDCOM file.

Applies a two-step pipeline:

  Step 1 — normalize_ancestry (skipping add_aka):
      Run the standard normalization pipeline, minus the add_unaccented_names
      step, which would add AKA entries that step 2 would immediately remove.
      This removes proprietary Ancestry tags, broken OBJE records, etc.

  Step 2 — minimal export:
      • Remove AKA NAME blocks (1 NAME entries whose children include 2 TYPE AKA)
      • Reduce all person-level (1 SOUR) citations to bare pointers — always
      • Strip or trim fact-level (2 SOUR) citations — controlled by --keep-fact-sources
      • Drop event blocks that become empty after source stripping (no DATE,
        PLAC, NOTE, or other data children remaining)
      • Optionally reduce SOUR definition records to header + TITL only — controlled
        by --strip-sour-bodies

The output is saved as a .txt file (default: <input_stem>_minimal.txt).

Usage:
  python export_minimal.py yourfile.ged
  python export_minimal.py yourfile.ged --output compact.txt
  python export_minimal.py yourfile.ged --keep-fact-sources
  python export_minimal.py yourfile.ged --strip-sour-bodies
  python export_minimal.py yourfile.ged --dry-run
"""

import argparse
import os
import re
import sys
import tempfile

_LEVEL_RE = re.compile(r'^(\d+) ')


def _level(line: str) -> int | None:
    m = _LEVEL_RE.match(line)
    return int(m.group(1)) if m else None


def _collect_l1_block(lines: list[str], start: int) -> tuple[list[str], int]:
    """
    Collect the level-1 block beginning at lines[start] and all its level-2+
    descendants. Returns (block_lines, next_i) where next_i is the index of
    the next level-0 or level-1 line (i.e. the start of the following block).
    """
    block = [lines[start]]
    i = start + 1
    while i < len(lines):
        lv = _level(lines[i])
        if lv is None or lv <= 1:
            break
        block.append(lines[i])
        i += 1
    return block, i


def _has_aka(block_lines: list[str]) -> bool:
    """Return True if a NAME block contains a '2 TYPE AKA' child line."""
    return any(re.match(r'^2 TYPE AKA\b', l) for l in block_lines[1:])


def _has_inline_value(header_line: str) -> bool:
    """
    Return True if the level-1 tag line carries a value on the same line.
    e.g. '1 SEX M' → True, '1 BIRT' → False, '1 FAMS @F1@' → True.
    Tags with an inline value are always kept even when their children are
    stripped away; event containers without a value are dropped when empty.
    """
    return bool(re.match(r'^\d+ \w+ \S', header_line.rstrip()))


def _strip_fact_sources(block_lines: list[str]) -> tuple[list[str], int]:
    """
    Remove '2 SOUR' sub-blocks and their level-3+ children from a block entirely.
    Returns (cleaned_lines, sources_removed_count).
    """
    result = [block_lines[0]]
    sources_removed = 0
    i = 1
    while i < len(block_lines):
        line = block_lines[i]
        lv = _level(line)
        if lv == 2 and re.match(r'^2 SOUR\b', line):
            sources_removed += 1
            i += 1
            while i < len(block_lines) and (_level(block_lines[i]) or 0) >= 3:
                i += 1
        else:
            result.append(line)
            i += 1
    return result, sources_removed


def _trim_fact_source_children(block_lines: list[str]) -> list[str]:
    """
    Keep '2 SOUR' pointer lines but strip their level-3+ children.
    Used when keeping fact-level sources but reducing them to bare pointers.
    """
    result = [block_lines[0]]
    i = 1
    while i < len(block_lines):
        line = block_lines[i]
        lv = _level(line)
        if lv == 2 and re.match(r'^2 SOUR\b', line):
            result.append(line)  # keep the bare pointer
            i += 1
            while i < len(block_lines) and (_level(block_lines[i]) or 0) >= 3:
                i += 1  # skip PAGE, DATA, TEXT, QUAI, etc.
        else:
            result.append(line)
            i += 1
    return result


def _strip_sour_body(rec_lines: list[str]) -> list[str]:
    """
    Reduce a SOUR definition record to its level-0 header + 1 TITL line(s) only.
    Any CONC/CONT continuations of the TITL are preserved; all other children
    (AUTH, PUBL, NOTE, REFN, DATA, etc.) are dropped.
    """
    result = [rec_lines[0]]  # 0 @Sx@ SOUR
    in_titl = False
    for line in rec_lines[1:]:
        lv = _level(line)
        if lv == 1 and re.match(r'^1 TITL\b', line):
            result.append(line)
            in_titl = True
        elif in_titl and lv == 2 and re.match(r'^2 (CONT|CONC)\b', line):
            result.append(line)
        else:
            in_titl = False
    return result


def _process_record(
    rec_lines: list[str],
    strip_aka: bool,
    strip_fact_sources: bool,
    strip_notes: bool,
) -> tuple[list[str], int, int, int, int]:
    """
    Process one INDI or FAM record:
      - AKA NAME blocks removed (INDI only, when strip_aka=True)
      - Person-level 1 SOUR blocks reduced to bare pointer (always)
      - Fact-level 2 SOUR blocks: stripped entirely (strip_fact_sources=True)
        or trimmed to bare pointers (strip_fact_sources=False)
      - Event blocks with no remaining children dropped
      - Person-level 1 NOTE blocks removed (when strip_notes=True)

    Returns (new_lines, aka_removed, fact_sources_removed, empty_events_dropped, notes_stripped).
    """
    result = [rec_lines[0]]  # level-0 record header
    aka_removed = 0
    sources_removed = 0
    events_dropped = 0
    notes_stripped = 0

    i = 1
    while i < len(rec_lines):
        lv = _level(rec_lines[i])
        if lv != 1:
            result.append(rec_lines[i])
            i += 1
            continue

        block, next_i = _collect_l1_block(rec_lines, i)
        tag_m = re.match(r'^1 (\w+)', rec_lines[i])
        tag = tag_m.group(1) if tag_m else ''

        if strip_aka and tag == 'NAME' and _has_aka(block):
            aka_removed += 1
        elif strip_notes and tag == 'NOTE':
            notes_stripped += 1
        elif tag == 'SOUR':
            # Person-level source: always reduce to bare pointer only
            result.append(block[0])
        elif strip_fact_sources:
            cleaned, n_src = _strip_fact_sources(block)
            sources_removed += n_src
            if len(cleaned) > 1 or _has_inline_value(cleaned[0]):
                result.extend(cleaned)
            else:
                events_dropped += 1
        else:
            # keep_fact_sources: trim 2 SOUR children to bare pointers
            result.extend(_trim_fact_source_children(block))

        i = next_i

    return result, aka_removed, sources_removed, events_dropped, notes_stripped


def export_minimal(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
    skip_normalize: bool = False,
    keep_fact_sources: bool = False,
    strip_sour_bodies: bool = False,
    strip_notes: bool = False,
) -> dict:
    """
    Export a compact GEDCOM: strip AKAs, reduce source citations to bare pointers,
    and optionally strip fact-level sources, SOUR definition bodies, and person notes.

    Parameters
    ----------
    path_in           : source .ged file
    path_out          : destination path; None → <stem>_minimal.txt alongside input
    dry_run           : compute stats but don't write the output file
    skip_normalize    : skip step 1 (normalize_ancestry); used in tests
    keep_fact_sources : if True, keep fact-level 2 SOUR pointers (default: strip them)
    strip_sour_bodies : if True, reduce SOUR records to header + TITL only
    strip_notes       : if True, strip person-level (1 NOTE) blocks; event notes kept

    Returns
    -------
    dict with keys:
      lines_in              : lines fed into step 2 (post-normalize)
      lines_out             : lines in the output
      aka_blocks_removed    : AKA NAME blocks dropped
      fact_sources_removed  : fact-level SOUR blocks stripped (0 when keep_fact_sources)
      empty_events_dropped  : event blocks dropped for having no data children
      sour_records_trimmed  : SOUR definition records reduced to TITL only
      notes_stripped        : person-level NOTE blocks dropped
    """
    if path_out is None:
        base = os.path.splitext(path_in)[0]
        path_out = base + '_minimal.txt'

    if os.path.abspath(path_out) == os.path.abspath(path_in):
        raise ValueError(f'Output path must differ from input: {path_in}')

    # ------------------------------------------------------------------
    # Step 1 — normalize_ancestry (skip add_aka to avoid creating AKAs
    #           that step 2 would immediately remove)
    # ------------------------------------------------------------------
    tmp_norm = None
    if skip_normalize:
        work_path = path_in
    else:
        from normalize_ancestry import normalize_ancestry
        tmp_fd, tmp_norm = tempfile.mkstemp(suffix='.ged')
        os.close(tmp_fd)
        try:
            normalize_ancestry(path_in, path_out=tmp_norm, skip=['add_aka'])
            work_path = tmp_norm
        except Exception:
            os.unlink(tmp_norm)
            raise

    # ------------------------------------------------------------------
    # Step 2 — minimal export
    # ------------------------------------------------------------------
    try:
        with open(work_path, encoding='utf-8') as f:
            all_lines = f.readlines()

        lines_out: list[str] = []
        total_aka = 0
        total_sources = 0
        total_dropped = 0
        total_sour_trimmed = 0
        total_notes = 0

        i = 0
        while i < len(all_lines):
            line = all_lines[i]
            is_indi = re.match(r'^0 @[^@]+@ INDI\b', line)
            is_fam  = re.match(r'^0 @[^@]+@ FAM\b', line)
            is_sour = re.match(r'^0 @[^@]+@ SOUR\b', line)

            if is_indi or is_fam:
                # Collect full record (until next level-0 line)
                rec_start = i
                i += 1
                while i < len(all_lines) and not re.match(r'^0 ', all_lines[i]):
                    i += 1
                rec_lines = all_lines[rec_start:i]

                new_rec, aka, src, dropped, notes = _process_record(
                    rec_lines,
                    strip_aka=bool(is_indi),
                    strip_fact_sources=not keep_fact_sources,
                    strip_notes=strip_notes,
                )
                lines_out.extend(new_rec)
                total_aka     += aka
                total_sources += src
                total_dropped += dropped
                total_notes   += notes

            elif is_sour and strip_sour_bodies:
                # Collect full SOUR record, then trim to header + TITL
                rec_start = i
                i += 1
                while i < len(all_lines) and not re.match(r'^0 ', all_lines[i]):
                    i += 1
                rec_lines = all_lines[rec_start:i]
                lines_out.extend(_strip_sour_body(rec_lines))
                total_sour_trimmed += 1

            else:
                lines_out.append(line)
                i += 1

    finally:
        if tmp_norm and os.path.exists(tmp_norm):
            os.unlink(tmp_norm)

    result = {
        'lines_in':             len(all_lines),
        'lines_out':            len(lines_out),
        'aka_blocks_removed':   total_aka,
        'fact_sources_removed': total_sources,
        'empty_events_dropped': total_dropped,
        'sour_records_trimmed': total_sour_trimmed,
        'notes_stripped':       total_notes,
    }

    if not dry_run:
        tmp = path_out + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.writelines(lines_out)
        os.replace(tmp, path_out)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Export a compact GEDCOM with AKAs and source detail removed.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to the .ged file')
    parser.add_argument(
        '--output', '-o', metavar='FILE',
        help='Write output here (default: <input_stem>_minimal.txt)',
    )
    parser.add_argument(
        '--keep-fact-sources', action='store_true',
        help='Keep inline fact-level source pointers (default: strip them entirely)',
    )
    parser.add_argument(
        '--strip-sour-bodies', action='store_true',
        help='Reduce SOUR definition records to header + TITL only',
    )
    parser.add_argument(
        '--strip-notes', action='store_true',
        help='Strip person-level (1 NOTE) blocks; notes on events are kept',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print statistics without writing any output',
    )
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    if args.output and os.path.abspath(args.output) == os.path.abspath(args.gedfile):
        sys.exit('Error: --output must not be the same file as the input')

    mode = 'DRY RUN' if args.dry_run else 'EXPORT'
    print(f'[{mode}] {args.gedfile}')

    result = export_minimal(
        args.gedfile,
        path_out=args.output,
        dry_run=args.dry_run,
        keep_fact_sources=args.keep_fact_sources,
        strip_sour_bodies=args.strip_sour_bodies,
        strip_notes=args.strip_notes,
    )

    print(f'  Lines in (post-normalize)  : {result["lines_in"]:,}')
    print(f'  Lines out                  : {result["lines_out"]:,}')
    print(f'  Lines removed              : {result["lines_in"] - result["lines_out"]:,}')
    print(f'  AKA blocks removed         : {result["aka_blocks_removed"]:,}')
    print(f'  Fact sources stripped      : {result["fact_sources_removed"]:,}')
    print(f'  Empty events dropped       : {result["empty_events_dropped"]:,}')
    print(f'  SOUR records trimmed       : {result["sour_records_trimmed"]:,}')
    print(f'  Notes stripped             : {result["notes_stripped"]:,}')

    if not args.dry_run:
        out = args.output or (os.path.splitext(args.gedfile)[0] + '_minimal.txt')
        print(f'  Written to                 : {out}')


if __name__ == '__main__':
    main()
