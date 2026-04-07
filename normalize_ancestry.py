#!/usr/bin/env python3
"""
normalize_ancestry.py — Comprehensive normalization pipeline for Ancestry GEDCOM exports.

Runs the following steps in order:

  1. strip_ancestry_artifacts   Remove proprietary Ancestry tags (_APID, _OID, etc.)
  2. convert_physical_attrs     Convert _HEIG/_WEIG to standard GEDCOM DSCR
  3. convert_nonstandard_events Convert _MILT, _SEPR, _DCAUSE to standard GEDCOM
  4. convert_wlnk               Convert _WLNK web links to ASSO/NOTE records
  5. clean_notexml              Strip <notexml> wrappers from NOTE fields
  6. extract_occupations        Pull "Occupation: X" from notes into OCCU events
  7. purge_blocked_occupations  Remove trivial OCCU entries (Student, Scholar, etc.)
  8. purge_duplicate_events     Merge duplicate BIRT/DEAT blocks
  9. purge_broken_obje          Remove OBJE references with missing files
 10. linter                     Fix dates, whitespace, PLAC, names, long lines, dupes

Usage:
  # Write result to yourfile_normalized.ged (default — original untouched):
  python normalize_ancestry.py yourfile.ged

  # Write result to a specific output file:
  python normalize_ancestry.py yourfile.ged --output clean.ged

  # Overwrite the original file in place:
  python normalize_ancestry.py yourfile.ged --in-place

  # Preview all changes without writing:
  python normalize_ancestry.py yourfile.ged --dry-run

  # Skip specific steps:
  python normalize_ancestry.py yourfile.ged --skip purge_obje linter
"""

import argparse
import os
import shutil
import sys
import tempfile

from strip_ancestry_artifacts import strip_ancestry_artifacts
from convert_physical_attrs import convert_physical_attrs
from convert_nonstandard_events import convert_nonstandard_events
from convert_wlnk import convert_wlnk
from clean_notexml import clean_notexml
from extract_occupations import extract_occupations, purge_blocked_occupations
from purge_duplicate_events import purge_duplicate_events
from purge_broken_obje import purge_broken_obje
from gedcom_linter import lint_and_fix


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

def _fmt_delta(n: int) -> str:
    return f'{n:+,d} lines' if n != 0 else '  0 lines'


def _run_strip(path: str) -> tuple[str, str]:
    r = strip_ancestry_artifacts(path)
    tags_total = sum(r['tags_removed'].values())
    detail = f'{tags_total} tags removed'
    return _fmt_delta(-r['lines_removed']), detail


def _run_convert_physical_attrs(path: str) -> tuple[str, str]:
    r = convert_physical_attrs(path)
    detail = (f'{r["heig_converted"]} _HEIG, '
              f'{r["weig_converted"]} _WEIG converted')
    return _fmt_delta(r['lines_delta']), detail


def _run_convert_events(path: str) -> tuple[str, str]:
    r = convert_nonstandard_events(path)
    detail = (f'{r["milt_converted"]} _MILT, '
              f'{r["sepr_converted"]} _SEPR, '
              f'{r["dcause_converted"]} _DCAUSE converted')
    return _fmt_delta(r['lines_delta']), detail


def _run_convert_wlnk(path: str) -> tuple[str, str]:
    r = convert_wlnk(path)
    detail = (f'{r["asso_added"]} ASSO added, '
              f'{r["notes_added"]} notes added')
    return _fmt_delta(-r['lines_removed']), detail


def _run_clean_notexml(path: str) -> tuple[str, str]:
    r = clean_notexml(path)
    detail = f'{r["notes_cleaned"]} notes cleaned'
    return _fmt_delta(r['lines_delta']), detail


def _run_extract_occupations(path: str) -> tuple[str, str]:
    r = extract_occupations(path)
    detail = f'{r["occu_added"]} OCCU events added'
    return _fmt_delta(r['lines_delta']), detail


def _run_purge_blocked_occupations(path: str) -> tuple[str, str]:
    r = purge_blocked_occupations(path)
    detail = f'{r["occu_removed"]} blocked OCCU removed'
    return _fmt_delta(r['lines_delta']), detail


def _run_purge_duplicate_events(path: str) -> tuple[str, str]:
    r = purge_duplicate_events(path)
    detail = (f'{r["events_merged"]} events merged, '
              f'{r["sources_added"]} sources migrated')
    return _fmt_delta(-r['lines_removed']), detail


def _run_purge_broken_obje(path: str) -> tuple[str, str]:
    r = purge_broken_obje(path)
    detail = f'{r["obje_removed"]} OBJE removed'
    return _fmt_delta(-r['lines_removed']), detail


def _run_linter(path: str) -> tuple[str, str]:
    r = lint_and_fix(path)
    detail = f'{r["fixes_applied"]} fixes applied'
    return _fmt_delta(r['lines_delta']), detail


STEPS: list[tuple[str, str, callable]] = [
    ('strip',            'strip_ancestry_artifacts  ', _run_strip),
    ('convert_physical', 'convert_physical_attrs    ', _run_convert_physical_attrs),
    ('convert_events',   'convert_nonstandard_events', _run_convert_events),
    ('convert_wlnk',     'convert_wlnk              ', _run_convert_wlnk),
    ('clean_notes',      'clean_notexml             ', _run_clean_notexml),
    ('extract_occu',     'extract_occupations       ', _run_extract_occupations),
    ('purge_occu',       'purge_blocked_occupations ', _run_purge_blocked_occupations),
    ('purge_dupes',      'purge_duplicate_events    ', _run_purge_duplicate_events),
    ('purge_obje',       'purge_broken_obje         ', _run_purge_broken_obje),
    ('linter',           'gedcom_linter             ', _run_linter),
]

STEP_NAMES = [name for name, _, _ in STEPS]


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def normalize_ancestry(
    path_in: str,
    path_out: str | None = None,
    dry_run: bool = False,
    skip: list[str] | None = None,
) -> list[dict]:
    """
    Run the full normalization pipeline on path_in.

    All steps operate on a temporary copy of the file; the original is never
    touched until the final atomic replace. In dry_run mode the temp copy is
    discarded without touching the original.

    Returns a list of result dicts, one per executed step:
      {'step': str, 'label': str, 'delta': str, 'detail': str}
    """
    skip_set = set(skip or [])

    # Work on a temp copy so the original is never partially modified
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.ged')
    os.close(tmp_fd)
    shutil.copy2(path_in, tmp_path)

    results = []
    try:
        for step_name, label, runner in STEPS:
            if step_name in skip_set:
                continue
            delta_str, detail = runner(tmp_path)
            results.append({
                'step': step_name,
                'label': label,
                'delta': delta_str,
                'detail': detail,
            })

        if not dry_run:
            dest = path_out if path_out else path_in
            os.replace(tmp_path, dest)
            tmp_path = None  # prevent cleanup below

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Normalize an Ancestry GEDCOM export through all cleanup steps.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('gedfile', help='Path to the .ged file')
    parser.add_argument('--output', '-o', metavar='FILE',
                        help='Write result to this file (default: <input>_normalized.ged)')
    parser.add_argument('--in-place', action='store_true',
                        help='Overwrite the input file instead of writing a new file')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run all steps on a temp copy; print results without writing')
    parser.add_argument('--skip', metavar='STEP', nargs='+',
                        choices=STEP_NAMES,
                        help=f'Steps to skip. Choices: {", ".join(STEP_NAMES)}')
    args = parser.parse_args()

    if not os.path.isfile(args.gedfile):
        sys.exit(f'Error: file not found: {args.gedfile}')

    if args.output and args.in_place:
        sys.exit('Error: --output and --in-place are mutually exclusive')

    if args.in_place:
        path_out = args.gedfile
    elif args.output:
        path_out = args.output
    else:
        base, ext = os.path.splitext(args.gedfile)
        path_out = base + '_normalized' + (ext or '.ged')

    mode = 'DRY RUN' if args.dry_run else 'NORMALIZE'
    print(f'[{mode}] {args.gedfile}')
    if args.skip:
        print(f'  Skipping: {", ".join(args.skip)}')

    results = normalize_ancestry(
        args.gedfile,
        path_out=path_out,
        dry_run=args.dry_run,
        skip=args.skip,
    )

    print()
    total_delta = 0
    for i, r in enumerate(results, 1):
        print(f'  {i:2}. {r["label"]}: {r["delta"]:>14}  ({r["detail"]})')
        # Parse delta from the formatted string for totalling
        raw = r['delta'].replace(',', '').replace(' lines', '').strip()
        try:
            total_delta += int(raw)
        except ValueError:
            pass

    print(f'  {"─" * 62}')
    print(f'  {"Total":30}  {_fmt_delta(total_delta):>14}')

    if not args.dry_run:
        print(f'\n  Written to: {path_out}')


if __name__ == '__main__':
    main()
