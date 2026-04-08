"""
report.py — Generate a human-readable merge report.

Printed to console and saved to a file.
"""

from __future__ import annotations
import datetime

from gedcom_merge.model import GedcomFile
from gedcom_merge.merge import MergeStats


_DIVIDER = '=' * 50


def generate_report(
    file_a: GedcomFile,
    file_b: GedcomFile,
    merged: GedcomFile,
    stats: MergeStats,
    report_path: str,
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

    text = '\n'.join(lines) + '\n'

    print(text)

    if report_path:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(text)

    return text
