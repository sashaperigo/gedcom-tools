#!/usr/bin/env python3
"""
strip_ancestry_artifacts.py — Remove Ancestry.com-proprietary tags from a GEDCOM file.

Ancestry.com GEDCOM exports contain many non-standard underscore-prefixed tags
that have no meaning in GEDCOM 5.5.1 and clutter genealogy software imports.
This tool strips those tags (and all their child lines) from the file.

Usage:
  # Strip in-place:
  python strip_ancestry_artifacts.py yourfile.ged

  # Write cleaned output to a new file:
  python strip_ancestry_artifacts.py yourfile.ged --output clean.ged

  # Preview what would be removed without writing:
  python strip_ancestry_artifacts.py yourfile.ged --dry-run
"""

import argparse
import re
import sys
from collections import defaultdict

from gedcom_io import level_tag as _tag_of, write_lines

# ---------------------------------------------------------------------------
# Ancestry-proprietary tags to remove (with all child lines)
# ---------------------------------------------------------------------------

ANCESTRY_TAGS: frozenset[str] = frozenset({
    # Record & person identifiers
    '_APID',   # Ancestry Person / Record ID (links record to Ancestry DB)
    '_OID',    # Object ID (internal Ancestry object identifier)
    '_TID',    # Tree ID
    '_PID',    # Person ID
    '_LKID',   # Link ID
    '_MSER',   # Member serial / subscription identifier
    # Provenance / audit metadata
    '_CREA',   # Created-by (Ancestry user & timestamp)
    '_USER',   # Ancestry username
    '_ORIG',   # Origin indicator ("ANCESTRY" etc.)
    '_ENCR',   # Encryption indicator
    '_ATL',    # Ancestry tree link
    '_CLON',   # Clone / copy marker
    '_DATE',   # Ancestry internal date (distinct from standard DATE tag)
    # Photo / media metadata
    '_PRIM',   # Primary photo flag
    '_CROP',   # Crop coordinates block
    '_LEFT',   # Crop left edge
    '_TOP',    # Crop top edge
    '_WDTH',   # Crop width
    '_HGHT',   # Crop height
    '_TYPE',   # Ancestry media type
    '_WPID',   # Web photo ID
    '_HPID',   # Historical photo ID
    '_MTYPE',  # Media subtype (portrait, headstone, story, etc.)
    '_STYPE',  # Source/file type (jpeg, pdf, etc.)
    '_SIZE',   # File size in bytes
    '_DSCR',   # Media description / caption
    '_META',   # Ancestry metadataxml block
    # Tree / environment
    '_TREE',   # Tree identifier
    '_ENV',    # Environment ("ANCESTRY" etc.)
    # Media tag labels
    '_MTTAG',  # Ancestry media tag / label (reference and definition records)
})

_L0_XREF_RE = re.compile(r'^0 @[^@]+@ ([A-Z_][A-Z0-9_]*)')


def strip_ancestry_artifacts(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Remove Ancestry-proprietary tags (and their child lines) from a GEDCOM file.

    Parameters
    ----------
    path_in  : path to the source GEDCOM file
    path_out : destination path; if None, overwrites path_in (unless dry_run)
    dry_run  : if True, do not write anything — just return statistics

    Returns
    -------
    dict with keys:
      'lines_read'    : total lines in the input file
      'lines_removed' : number of lines dropped
      'tags_removed'  : dict mapping tag → count of top-level occurrences removed
    """
    with open(path_in, encoding='utf-8') as f:
        lines = f.readlines()

    lines_out: list[str] = []
    tags_removed: dict[str, int] = defaultdict(int)
    skip_until_level: int | None = None  # when set, skip lines at > this level

    for raw in lines:
        line = raw.rstrip('\n')
        parsed = _tag_of(line)

        if parsed is None:
            # Check for xref-prefixed level-0 records: `0 @T1@ _MTTAG`
            # These never match _LEVEL_RE so we handle the skip-block boundary here.
            xref_m = _L0_XREF_RE.match(line)
            if xref_m:
                # Any level-0 record ends an active skip block
                skip_until_level = None
                if xref_m.group(1) in ANCESTRY_TAGS:
                    tags_removed[xref_m.group(1)] += 1
                    skip_until_level = 0  # skip all child lines (level > 0)
                    continue
                # Not an ancestry tag — fall through to keep this line
            # Continuation or malformed line — keep unless we're inside a skip block
            if skip_until_level is not None:
                continue
            lines_out.append(raw)
            continue

        level, tag = parsed

        # If we're inside a skip block, check whether this line ends it
        if skip_until_level is not None:
            if level > skip_until_level:
                continue  # still inside the skip block
            else:
                skip_until_level = None  # block ended; fall through

        # Check whether this line starts a block we should remove
        if tag in ANCESTRY_TAGS:
            tags_removed[tag] += 1
            skip_until_level = level
            continue

        lines_out.append(raw)

    lines_removed = len(lines) - len(lines_out)
    result = {
        'lines_read': len(lines),
        'lines_removed': lines_removed,
        'tags_removed': dict(tags_removed),
    }

    write_lines(lines_out, path_in, path_out, dry_run, changed=lines_removed > 0)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Remove Ancestry.com-proprietary tags from a GEDCOM file.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to .ged file')
    parser.add_argument(
        '--output', '-o', metavar='FILE',
        help='Write cleaned output here instead of overwriting the input file',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print a summary of what would be removed without writing anything',
    )
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    result = strip_ancestry_artifacts(
        args.gedfile,
        path_out=args.output,
        dry_run=args.dry_run,
    )

    mode = 'DRY RUN' if args.dry_run else 'STRIP'
    dest = args.output or args.gedfile
    print(f'[{mode}] {args.gedfile}')
    print(f'  Lines read    : {result["lines_read"]}')
    print(f'  Lines removed : {result["lines_removed"]}')
    if result['tags_removed']:
        print('  Tags removed  :')
        for tag, count in sorted(result['tags_removed'].items()):
            print(f'    {tag}: {count}')
    else:
        print('  No Ancestry-proprietary tags found.')
    if not args.dry_run and result['lines_removed'] > 0:
        print(f'  Written to    : {dest}')


if __name__ == '__main__':
    main()
