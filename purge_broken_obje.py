#!/usr/bin/env python3
"""
purge_broken_obje.py — Remove OBJE records whose FILE path does not exist on disk.

GEDCOM files commonly accumulate media references that point to files that have
been moved, renamed, or never transferred alongside the GEDCOM. This tool removes
those dead links rather than leaving broken OBJE blocks in the tree.

Three kinds of OBJE entries are handled:

  1. Top-level records    0 @O1@ OBJE / 1 FILE photos/smith.jpg
     The entire record is removed if its FILE is missing.

  2. Inline subrecords    1 OBJE (no xref, embedded in INDI/FAM)
     Just that subblock is removed if its FILE is missing.

  3. Pointer references   1 OBJE @O1@
     The pointer line is removed when the referenced top-level record is removed.

FILE paths are resolved relative to the directory that contains the GEDCOM file.
URL values (http://, https://, ftp://) are never removed — they cannot be checked
for local existence.

Usage:
  # Remove broken OBJE blocks in-place:
  python purge_broken_obje.py yourfile.ged

  # Write cleaned output to a new file:
  python purge_broken_obje.py yourfile.ged --output clean.ged

  # Preview what would be removed without writing:
  python purge_broken_obje.py yourfile.ged --dry-run
"""

import argparse
import os
import re
import sys

# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

_LEVEL_RE = re.compile(r'^(\d+)')
_TOP_OBJE_RE = re.compile(r'^0 (@[^@]+@) OBJE\s*$')   # top-level: 0 @X@ OBJE
_INLINE_OBJE_RE = re.compile(r'^(\d+) OBJE\s*$')       # inline:    N OBJE  (no value)
_PTR_OBJE_RE = re.compile(r'^(\d+) OBJE (@[^@]+@)\s*$')  # pointer: N OBJE @X@
_FILE_RE = re.compile(r'^\d+ FILE (.+)$')

_URL_SCHEMES = ('http://', 'https://', 'ftp://', 'ftps://')


def _is_url(path: str) -> bool:
    return any(path.lower().startswith(s) for s in _URL_SCHEMES)


def _file_exists(file_val: str, gedcom_dir: str) -> bool:
    """Return True if file_val resolves to an existing file (or is a URL)."""
    val = file_val.strip()
    if _is_url(val):
        return True  # URLs are never flagged as broken
    if os.path.isabs(val):
        return os.path.isfile(val)
    return os.path.isfile(os.path.join(gedcom_dir, val))


def _level(line: str) -> int | None:
    m = _LEVEL_RE.match(line)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Core helpers: find the FILE child of a block
# ---------------------------------------------------------------------------

def _find_file_in_block(lines: list[str], start: int, block_level: int) -> str | None:
    """
    Return the value of the first FILE tag that is a direct (or deeper) child
    of the block starting at lines[start], or None if there isn't one.
    """
    for i in range(start + 1, len(lines)):
        lv = _level(lines[i].rstrip('\n'))
        if lv is None:
            continue
        if lv <= block_level:
            break
        m = _FILE_RE.match(lines[i].rstrip('\n'))
        if m:
            return m.group(1).strip()
    return None


def _block_end(lines: list[str], start: int, block_level: int) -> int:
    """
    Return the index of the first line after the block that began at start
    (i.e., the first line whose level is <= block_level, or len(lines)).
    """
    for i in range(start + 1, len(lines)):
        lv = _level(lines[i].rstrip('\n'))
        if lv is not None and lv <= block_level:
            return i
    return len(lines)


# ---------------------------------------------------------------------------
# Main purge logic
# ---------------------------------------------------------------------------

def purge_broken_obje(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Remove OBJE blocks with missing FILE references from a GEDCOM file.

    Parameters
    ----------
    path_in  : source GEDCOM file
    path_out : destination path; None means overwrite path_in (unless dry_run)
    dry_run  : if True, compute and return stats but do not write anything

    Returns
    -------
    dict with keys:
      'lines_read'    : int
      'lines_removed' : int
      'obje_removed'  : int   — count of OBJE blocks/records removed
      'broken_files'  : list[str]  — the FILE values that triggered removal
    """
    gedcom_dir = os.path.dirname(os.path.abspath(path_in))

    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    # ------------------------------------------------------------------
    # Pass 1: identify top-level OBJE records whose FILE is broken.
    # Collect:  broken_xrefs  →  set of xref strings (e.g. '@O1@')
    #           broken_files  →  list of FILE values that triggered removal
    # ------------------------------------------------------------------
    broken_xrefs: set[str] = set()
    broken_files: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        m = _TOP_OBJE_RE.match(line)
        if m:
            xref = m.group(1)
            file_val = _find_file_in_block(lines, i, block_level=0)
            if file_val is not None and not _file_exists(file_val, gedcom_dir):
                broken_xrefs.add(xref)
                broken_files.append(file_val)
        i += 1

    # ------------------------------------------------------------------
    # Pass 2: build output, skipping broken blocks.
    # ------------------------------------------------------------------
    lines_out: list[str] = []
    obje_removed = 0
    i = 0

    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip('\n')

        # --- Top-level OBJE record ---
        m = _TOP_OBJE_RE.match(line)
        if m:
            xref = m.group(1)
            end = _block_end(lines, i, block_level=0)
            if xref in broken_xrefs:
                obje_removed += 1
                i = end
                continue
            else:
                lines_out.extend(lines[i:end])
                i = end
                continue

        # --- Pointer reference: N OBJE @X@ ---
        m = _PTR_OBJE_RE.match(line)
        if m:
            xref = m.group(2)
            if xref in broken_xrefs:
                i += 1
                continue  # drop the pointer line (single line, no children)

        # --- Inline OBJE subrecord: N OBJE (no value/xref) ---
        m = _INLINE_OBJE_RE.match(line)
        if m:
            block_level = int(m.group(1))
            file_val = _find_file_in_block(lines, i, block_level)
            end = _block_end(lines, i, block_level)
            if file_val is not None and not _file_exists(file_val, gedcom_dir):
                obje_removed += 1
                broken_files.append(file_val)
                i = end
                continue
            else:
                lines_out.extend(lines[i:end])
                i = end
                continue

        lines_out.append(raw)
        i += 1

    lines_removed = len(lines) - len(lines_out)
    result = {
        'lines_read': len(lines),
        'lines_removed': lines_removed,
        'obje_removed': obje_removed,
        'broken_files': broken_files,
    }

    if not dry_run and lines_removed > 0:
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
        description='Remove OBJE records with broken FILE paths from a GEDCOM file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to .ged file')
    parser.add_argument('--output', '-o', metavar='FILE',
                        help='Write cleaned output here instead of overwriting input')
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be removed without writing anything')
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    result = purge_broken_obje(args.gedfile, path_out=args.output, dry_run=args.dry_run)

    mode = 'DRY RUN' if args.dry_run else 'PURGE'
    dest = args.output or args.gedfile
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read    : {result["lines_read"]}')
    print(f'  Lines removed : {result["lines_removed"]}')
    print(f'  OBJE removed  : {result["obje_removed"]}')
    if result['broken_files']:
        print('  Broken files  :')
        for p in result['broken_files']:
            print(f'    {p}')
    else:
        print('  No broken OBJE links found.')
    if not args.dry_run and result['lines_removed'] > 0:
        print(f'  Written to    : {dest}')


if __name__ == '__main__':
    main()
