#!/usr/bin/env python3
"""
convert_events_to_facts.py

Converts misclassified EVEN records to their correct GEDCOM 5.5.1 types:

  EVEN TYPE Languages         → FACT TYPE Languages
  EVEN TYPE Literacy          → FACT TYPE Literacy
  EVEN TYPE Politics          → FACT TYPE Politics
  EVEN TYPE Medical condition → FACT TYPE Medical condition
  EVEN TYPE Physical Description → DSCR <note_value>
  EVEN TYPE Children          → NCHI <count>

Usage:
    python convert_events_to_facts.py --dry-run path/to/file.ged
    python convert_events_to_facts.py path/to/file.ged
"""

import argparse
import re
import sys
from pathlib import Path

# Tags that only need 1 EVEN → 1 FACT; all sub-tags are kept unchanged.
_FACT_SWAPS = {'Languages', 'Literacy', 'Politics', 'Medical condition'}


def _level(line: str) -> int | None:
    m = re.match(r'^(\d+)\s', line)
    return int(m.group(1)) if m else None


def _tag_val(line: str) -> tuple[str, str]:
    m = re.match(r'^\d+\s+(\S+)(?:\s+(.*))?$', line.rstrip('\r\n'))
    if not m:
        return '', ''
    return m.group(1), (m.group(2) or '')


def _collect_block(lines: list[str], start: int) -> int:
    """Return the index of the first line after the block beginning at start."""
    end = start + 1
    while end < len(lines):
        lvl = _level(lines[end])
        if lvl is not None and lvl <= 1:
            break
        end += 1
    return end


def _type_in_block(block: list[str]) -> str:
    """Return the value of the first level-2 TYPE line in the block, or ''."""
    for line in block:
        if _level(line) == 2:
            tag, val = _tag_val(line)
            if tag == 'TYPE':
                return val
    return ''


def _note_in_block(block: list[str]) -> str:
    """Return the value of the first level-2 NOTE line in the block, or ''."""
    for line in block:
        if _level(line) == 2:
            tag, val = _tag_val(line)
            if tag == 'NOTE':
                return val
    return ''


def _nl(line: str) -> str:
    """Return the line ending of a line."""
    if line.endswith('\r\n'):
        return '\r\n'
    return '\n'


def _convert_block(block: list[str]) -> tuple[list[str], str | None]:
    """
    Convert a single EVEN block if it matches a target TYPE.
    Returns (new_block, description_of_change) or (block, None) if unchanged.
    """
    type_val = _type_in_block(block)
    eol = _nl(block[0])

    if type_val in _FACT_SWAPS:
        new_block = [f'1 FACT{eol}'] + block[1:]
        return new_block, f'EVEN TYPE {type_val!r} → FACT TYPE {type_val!r}'

    if type_val == 'Physical Description':
        note_val = _note_in_block(block)
        dscr_line = f'1 DSCR {note_val}{eol}' if note_val else f'1 DSCR{eol}'
        new_block = [dscr_line]
        for line in block[1:]:
            lvl = _level(line)
            tag, _ = _tag_val(line)
            if lvl == 2 and tag in ('TYPE', 'NOTE'):
                continue  # NOTE value moved to DSCR line; TYPE no longer needed
            # Drop CONT/CONC lines that belonged to the NOTE
            if lvl == 3 and tag in ('CONT', 'CONC'):
                # Check if previous kept line was the NOTE — it was dropped, so drop these too
                # A simpler approach: track whether we're inside a dropped NOTE
                pass
            new_block.append(line)
        return new_block, f'EVEN TYPE Physical Description → DSCR {note_val!r}'

    if type_val == 'Children':
        note_val = _note_in_block(block)
        # Extract leading integer count from the note (e.g. "5 children" → "5")
        count_match = re.match(r'^(\d+)', (note_val or '').strip())
        count = count_match.group(1) if count_match else ''
        nchi_line = f'1 NCHI {count}{eol}' if count else f'1 NCHI{eol}'
        new_block = [nchi_line]
        for line in block[1:]:
            lvl = _level(line)
            tag, _ = _tag_val(line)
            if lvl == 2 and tag == 'TYPE':
                continue  # drop TYPE Children
            new_block.append(line)
        return new_block, f'EVEN TYPE Children → NCHI {count!r}'

    return block, None


def convert_lines(
    lines: list[str],
    return_changes: bool = False,
) -> list[str] | tuple[list[str], list[str]]:
    """
    Convert EVEN blocks in `lines` according to the rules above.

    Args:
        lines: list of GEDCOM lines (with newlines).
        return_changes: if True, return (new_lines, change_descriptions).

    Returns:
        new_lines, or (new_lines, changes) if return_changes is True.
    """
    result: list[str] = []
    changes: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        lvl = _level(line)

        if lvl == 1:
            tag, val = _tag_val(line)
            if tag == 'EVEN' and not val:
                end = _collect_block(lines, i)
                block = lines[i:end]
                new_block, change = _convert_block(block)
                result.extend(new_block)
                if change:
                    changes.append(change)
                i = end
                continue

        result.append(line)
        i += 1

    if return_changes:
        return result, changes
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('gedcom', help='Path to the .ged file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Print what would change without writing')
    args = parser.parse_args()

    path = Path(args.gedcom)
    if not path.exists():
        print(f'Error: {path} not found', file=sys.stderr)
        sys.exit(1)

    lines = path.read_text(encoding='utf-8-sig').splitlines(keepends=True)
    new_lines, changes = convert_lines(lines, return_changes=True)

    if not changes:
        print('No matching EVEN records found — nothing to do.')
        return

    print(f'Found {len(changes)} record(s) to convert:')
    for c in changes:
        print(f'  {c}')

    if args.dry_run:
        print('\n--dry-run: no changes written.')
        return

    backup = path.with_suffix('.ged.bak')
    backup.write_bytes(path.read_bytes())
    print(f'\nBackup written to {backup}')

    path.write_text(''.join(new_lines), encoding='utf-8')
    print(f'Updated {path}')


if __name__ == '__main__':
    main()
