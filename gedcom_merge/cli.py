"""
cli.py — Command-line interface and orchestration for gedcom-merge.

Usage:
    gedcom-merge [options] file_a file_b

Phases:
    1. Parse both files
    2. Match sources → individuals → families
    3. Interactive review (unless --batch)
    4. Merge records
    5. Write output
    6. Validate
    7. Generate report
"""

from __future__ import annotations
import argparse
import sys
import os


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog='gedcom-merge',
        description='Merge two GEDCOM 5.5.1 files into one.',
    )
    p.add_argument('file_a', help='Primary GEDCOM file (File A)')
    p.add_argument('file_b', help='Secondary GEDCOM file (File B)')
    p.add_argument('--primary', choices=['A', 'B'], default='A',
                   help="Which file's IDs to preserve (default: A / larger file)")
    p.add_argument('--output', '-o', default='merged.ged',
                   help='Output file path (default: merged.ged)')
    p.add_argument('--auto-threshold', type=float, default=0.75,
                   help='Score above which matches are auto-approved (default: 0.75)')
    p.add_argument('--review-threshold', type=float, default=0.50,
                   help='Score below which candidates are ignored (default: 0.50)')
    p.add_argument('--source-auto-threshold', type=float, default=0.90,
                   help='Auto-match threshold for sources (default: 0.90)')
    p.add_argument('--source-review-threshold', type=float, default=0.85,
                   help='Review threshold for sources (default: 0.85)')
    p.add_argument('--resume', metavar='SESSION_FILE',
                   help='Resume from a saved session file')
    p.add_argument('--session', metavar='SESSION_FILE', default='merge-session.json',
                   help='Session file path for save/resume (default: merge-session.json)')
    p.add_argument('--report', default='merge-report.txt',
                   help='Save merge report to file (default: merge-report.txt)')
    p.add_argument('--web', action='store_true',
                   help='Open review in browser (default: terminal)')
    p.add_argument('--port', type=int, default=8765,
                   help='Port for web review server (default: 8765)')
    p.add_argument('--batch', action='store_true',
                   help='Skip interactive review; auto-approve all above threshold')
    p.add_argument('--dry-run', action='store_true',
                   help='Run matching only, report results, do not write output')
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Validate inputs
    for path, label in [(args.file_a, 'File A'), (args.file_b, 'File B')]:
        if not os.path.isfile(path):
            print(f'Error: {label} not found: {path}', file=sys.stderr)
            return 1

    # Lazy imports (so CLI starts fast)
    from gedcom_merge.parser import parse_gedcom
    from gedcom_merge.match_sources import match_sources
    from gedcom_merge.match_individuals import match_individuals
    from gedcom_merge.match_families import match_families
    from gedcom_merge.merge import merge_records, MergeStats
    from gedcom_merge.writer import write_gedcom
    from gedcom_merge.validator import validate
    from gedcom_merge.report import generate_report
    from gedcom_merge.session import new_session, load_session, save_session
    from gedcom_merge.review import run_review
    from gedcom_merge.review_html import run_web_review
    from gedcom_merge.model import MergeDecisions

    # ---- Phase 1: Parse ----
    print(f'Parsing {args.file_a}...')
    file_a = parse_gedcom(args.file_a)
    file_a.path = os.path.basename(args.file_a)
    print(f'  {file_a.indi_count} individuals, {file_a.fam_count} families, {file_a.source_count} sources')

    print(f'Parsing {args.file_b}...')
    file_b = parse_gedcom(args.file_b)
    file_b.path = os.path.basename(args.file_b)
    print(f'  {file_b.indi_count} individuals, {file_b.fam_count} families, {file_b.source_count} sources')

    # If --primary B, swap (primary file's IDs are preserved)
    if args.primary == 'B' or (
        args.primary == 'A' and file_b.indi_count > file_a.indi_count
        and args.primary != 'A'
    ):
        file_a, file_b = file_b, file_a
        print('Note: File B is larger; using it as primary.')

    # ---- Phase 2: Match ----
    print('\nMatching sources...')
    source_result = match_sources(
        file_a, file_b,
        auto_threshold=args.source_auto_threshold,
        review_threshold=args.source_review_threshold,
    )
    print(f'  Auto-matched: {len(source_result.auto_matches)}, '
          f'Candidates: {len(source_result.candidates)}, '
          f'Unmatched: {len(source_result.unmatched_b)}')

    # Build preliminary source map for individual matching
    preliminary_source_map = {m.xref_b: m.xref_a for m in source_result.auto_matches}

    print('Matching individuals (with iterative propagation)...')
    indi_result = match_individuals(
        file_a, file_b,
        source_map=preliminary_source_map,
        auto_threshold=args.auto_threshold,
        review_threshold=args.review_threshold,
    )
    print(f'  Auto-matched: {len(indi_result.auto_matches)}, '
          f'Candidates: {len(indi_result.candidates)}, '
          f'Unmatched: {len(indi_result.unmatched_b)}')

    print('Matching families...')
    indi_map = {m.xref_b: m.xref_a for m in indi_result.auto_matches}
    fam_result = match_families(file_a, file_b, indi_map)
    print(f'  Matched: {len(fam_result.matches)}, '
          f'Unmatched: {len(fam_result.unmatched_b)}')

    if args.dry_run:
        print('\n--dry-run: skipping merge, write, and review.')
        return 0

    # ---- Phase 3: Review ----
    session = None
    session_path = args.session

    if args.resume:
        try:
            state = load_session(args.resume)
            session = state
            session_path = args.resume
            print(f'Resuming session from {args.resume}')
        except (ValueError, FileNotFoundError) as e:
            print(f'Error loading session: {e}', file=sys.stderr)
            return 1
    else:
        session = new_session(args.file_a, args.file_b, vars(args))

    if args.web:
        decisions = run_web_review(
            source_result, indi_result, fam_result,
            file_a, file_b,
            session=session,
            session_path=session_path,
            port=args.port,
        )
    else:
        decisions = run_review(
            source_result, indi_result, fam_result,
            file_a, file_b,
            session=session,
            session_path=session_path,
            batch=args.batch,
        )

    # ---- Phase 4: Merge ----
    print('\nMerging records...')
    merged, stats = merge_records(file_a, file_b, decisions)
    merged.path = os.path.basename(args.output)

    # Fill in match counts
    stats.source_matched_auto = len(source_result.auto_matches)
    stats.source_matched_manual = len(source_result.candidates)
    stats.indi_matched_auto = len(indi_result.auto_matches)
    stats.indi_matched_manual = len([
        m for m in indi_result.candidates if m.xref_b in decisions.indi_map
    ])
    stats.fam_matched_auto = len(fam_result.matches)

    # ---- Phase 5: Write ----
    print(f'Writing {args.output}...')
    write_gedcom(merged, args.output,
                 file_a_path=args.file_a, file_b_path=args.file_b)
    print(f'  Written: {merged.indi_count} individuals, '
          f'{merged.fam_count} families, {merged.source_count} sources')

    # ---- Phase 6: Validate ----
    print('Validating output...')
    errors = validate(args.output)
    if errors:
        print(f'\nValidation FAILED ({len(errors)} errors):')
        for err in errors:
            print(f'  ERROR: {err}')
        return 2
    else:
        print('  Validation passed.')

    # ---- Phase 7: Report ----
    generate_report(file_a, file_b, merged, stats, args.report)

    return 0


if __name__ == '__main__':
    sys.exit(main())
