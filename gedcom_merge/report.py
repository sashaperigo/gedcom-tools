"""
report.py — Generate a human-readable merge report.

Printed to console and saved to a file.
"""

from __future__ import annotations
import datetime

from gedcom_merge.model import GedcomFile
from gedcom_merge.merge import MergeStats
from gedcom_merge.analysis import AnalysisReport


_DIVIDER = '=' * 50


def generate_report(
    file_a: GedcomFile,
    file_b: GedcomFile,
    merged: GedcomFile,
    stats: MergeStats,
    report_path: str,
    analysis: AnalysisReport | None = None,
) -> str:
    """
    Build the merge report text, print it, and save to report_path.
    Returns the report text.
    """
    lines = [
        'GEDCOM Merge Report',
        '===================',
        f'Date: {datetime.date.today().isoformat()}',
        f'File A (primary): {file_a.path} '
        f'({file_a.indi_count} individuals, {file_a.fam_count} families, '
        f'{file_a.source_count} sources)',
        f'File B: {file_b.path} '
        f'({file_b.indi_count} individuals, {file_b.fam_count} families, '
        f'{file_b.source_count} sources)',
        '',
        'Matched:',
        f'  Individuals: {stats.indi_matched_auto + stats.indi_matched_manual} '
        f'(auto: {stats.indi_matched_auto}, manual: {stats.indi_matched_manual})',
        f'  Families:    {stats.fam_matched_auto + stats.fam_matched_manual} '
        f'(auto: {stats.fam_matched_auto}, manual: {stats.fam_matched_manual})',
        f'  Sources:     {stats.source_matched_auto + stats.source_matched_manual} '
        f'(auto: {stats.source_matched_auto}, manual: {stats.source_matched_manual})',
        '',
        'Added from File B:',
        f'  Individuals: {stats.indi_added}',
        f'  Families:    {stats.fam_added}',
        f'  Sources:     {stats.source_added}',
        '',
        'Skipped:',
        f'  Individuals: {stats.indi_skipped}',
        f'  Sources:     {stats.source_skipped}',
        '',
        'Conflicts resolved:',
        f'  AKA names added:          {stats.aka_names_added}',
        f'  Events added from B:      {stats.events_added_from_b}',
        f'  Citations added from B:   {stats.citations_added_from_b}',
        '',
        f'Output: {merged.path} '
        f'({merged.indi_count} individuals, {merged.fam_count} families, '
        f'{merged.source_count} sources)',
    ]

    if stats.warnings:
        lines.append('')
        lines.append('Warnings:')
        for w in stats.warnings:
            lines.append(f'  - {w}')

    if analysis is not None:
        lines.append('')
        lines.append('Data Quality Analysis:')
        if not analysis.has_issues():
            lines.append('  No issues found.')
        else:
            lines.append(f'  Total issues: {analysis.issue_count()}')
            if analysis.broken_xrefs:
                lines.append(f'  Broken cross-references ({len(analysis.broken_xrefs)}):')
                for msg in analysis.broken_xrefs:
                    lines.append(f'    {msg}')
            if analysis.duplicate_families:
                lines.append(f'  Duplicate families ({len(analysis.duplicate_families)} pairs):')
                for a, b in analysis.duplicate_families:
                    lines.append(f'    {a} == {b}')
            if analysis.duplicate_sources:
                lines.append(f'  Duplicate sources ({len(analysis.duplicate_sources)} pairs):')
                for a, b in analysis.duplicate_sources:
                    lines.append(f'    {a} == {b}')
            if analysis.orphaned_individuals:
                lines.append(f'  Orphaned individuals ({len(analysis.orphaned_individuals)}):')
                for xref in analysis.orphaned_individuals:
                    lines.append(f'    {xref}')
            if analysis.duplicate_names:
                total = sum(len(v) for v in analysis.duplicate_names.values())
                lines.append(f'  Duplicate NAME entries ({total} across {len(analysis.duplicate_names)} individuals):')
                for xref, names in analysis.duplicate_names.items():
                    lines.append(f'    {xref}: {", ".join(names)}')
            if analysis.excessive_citations:
                lines.append(f'  Events with excessive citations (>{10}): {len(analysis.excessive_citations)}')
                for xref, tag, count in analysis.excessive_citations:
                    lines.append(f'    {xref} {tag}: {count} citations')
            if analysis.duplicate_citations:
                lines.append(f'  Duplicate citations ({len(analysis.duplicate_citations)}):')
                for xref, tag, src, page in analysis.duplicate_citations:
                    lines.append(f'    {xref} {tag}: {src} page="{page}"')
            if analysis.empty_families:
                lines.append(f'  Empty family shells ({len(analysis.empty_families)}):')
                for xref in analysis.empty_families:
                    lines.append(f'    {xref}')

    text = '\n'.join(lines) + '\n'

    print(text)

    if report_path:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(text)

    return text
