"""
review.py — Interactive terminal review UI using rich.

Three modes:
  1. Batch approval: show auto-matches, get [A]pprove all / [R]eview / [Q]uit
  2. Conflict review: side-by-side comparison for each candidate match
  3. Unmatched records: [A]dd / [S]kip / [L]ink for each unmatched B record
"""

from __future__ import annotations
import sys

from gedcom_merge.model import (
    GedcomFile, Individual, Source, Family,
    SourceMatchResult, IndividualMatchResult, FamilyMatchResult,
    MergeDecisions, FieldChoice,
    SourceMatch, IndividualMatch,
)
from gedcom_merge.session import SessionState, save_session

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich import box
    _RICH = True
except ImportError:
    _RICH = False


def _console() -> 'Console':
    if _RICH:
        from rich.console import Console
        return Console()
    return None  # type: ignore


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _indi_summary(ind: Individual, label: str = '') -> str:
    name = ind.display_name
    birth = f'b. {ind.birth_year}' if ind.birth_year else ''
    death = f'd. {ind.death_year}' if ind.death_year else ''
    parts = [name]
    if birth:
        parts.append(birth)
    if death:
        parts.append(death)
    summary = ', '.join(parts)
    return f'{label}{summary}' if not label else f'[{label}] {summary}'


def _source_summary(src: Source) -> str:
    title = src.title[:70] + '...' if len(src.title) > 70 else src.title
    return f'"{title}"'


# ---------------------------------------------------------------------------
# Mode 1: Batch approval
# ---------------------------------------------------------------------------

def _show_batch_approval(
    source_result: SourceMatchResult,
    indi_result: IndividualMatchResult,
    fam_result: FamilyMatchResult,
    file_a: GedcomFile,
    file_b: GedcomFile,
    console,
) -> bool:
    """Show auto-matches summary. Returns True if user approves all."""
    n_indi = len(indi_result.auto_matches)
    n_fam = len(fam_result.matches)
    n_src = len(source_result.auto_matches)

    if _RICH:
        table = Table(title='AUTO-MATCHED RECORDS', box=box.ROUNDED)
        table.add_column('File A', style='cyan')
        table.add_column('File B', style='green')
        table.add_column('Score', justify='right', style='yellow')

        # Show sources (up to 10)
        if source_result.auto_matches:
            table.add_row('[bold]SOURCES[/bold]', '', '')
            for m in source_result.auto_matches[:10]:
                src_a = file_a.sources.get(m.xref_a)
                src_b = file_b.sources.get(m.xref_b)
                a_title = (src_a.title[:40] + '...') if src_a and len(src_a.title) > 40 else (src_a.title if src_a else m.xref_a)
                b_title = (src_b.title[:40] + '...') if src_b and len(src_b.title) > 40 else (src_b.title if src_b else m.xref_b)
                table.add_row(a_title, b_title, f'{m.score:.2f}')
            if len(source_result.auto_matches) > 10:
                table.add_row(f'  ... {len(source_result.auto_matches) - 10} more', '', '')

        # Show individuals (up to 10)
        if indi_result.auto_matches:
            table.add_row('[bold]INDIVIDUALS[/bold]', '', '')
            for m in indi_result.auto_matches[:10]:
                ind_a = file_a.individuals.get(m.xref_a)
                ind_b = file_b.individuals.get(m.xref_b)
                a_str = _indi_summary(ind_a) if ind_a else m.xref_a
                b_str = _indi_summary(ind_b) if ind_b else m.xref_b
                table.add_row(a_str, b_str, f'{m.score:.2f}')
            if len(indi_result.auto_matches) > 10:
                table.add_row(f'  ... {len(indi_result.auto_matches) - 10} more', '', '')

        console.print(Panel(table, title=f'AUTO-MATCHED: {n_indi} individuals, {n_fam} families, {n_src} sources'))
        choice = Prompt.ask('\n[A] Approve all  [R] Review individually  [Q] Quit', choices=['a', 'r', 'q'], default='a')
    else:
        print(f'\nAUTO-MATCHED: {n_indi} individuals, {n_fam} families, {n_src} sources')
        choice = input('[A]pprove all / [R]eview / [Q]uit: ').strip().lower()

    if choice == 'q':
        print('Quitting.')
        sys.exit(0)
    return choice == 'a'


# ---------------------------------------------------------------------------
# Mode 2: Conflict review (candidate matches)
# ---------------------------------------------------------------------------

def _show_individual_conflict(
    match: IndividualMatch,
    file_a: GedcomFile,
    file_b: GedcomFile,
    console,
) -> str:
    """Show a side-by-side comparison. Returns 'm' (merge), 's' (skip), or 'd' (detail)."""
    ind_a = file_a.individuals.get(match.xref_a)
    ind_b = file_b.individuals.get(match.xref_b)

    if not ind_a or not ind_b:
        return 's'

    def _ev(ind: Individual, tag: str) -> str:
        ev = next((e for e in ind.events if e.tag == tag), None)
        if not ev:
            return '—'
        parts = []
        if ev.date:
            from gedcom_merge.writer import _format_date
            d = _format_date(ev.date)
            if d:
                parts.append(d)
        if ev.place:
            parts.append(ev.place[:35])
        return ', '.join(parts) or '—'

    def _parents(ind: Individual, file: GedcomFile) -> str:
        for famc in ind.family_child:
            fam = file.families.get(famc)
            if fam:
                parts = []
                if fam.husband_xref:
                    p = file.individuals.get(fam.husband_xref)
                    if p:
                        parts.append(p.display_name)
                if fam.wife_xref:
                    p = file.individuals.get(fam.wife_xref)
                    if p:
                        parts.append(p.display_name)
                if parts:
                    return ' & '.join(parts)
        return '—'

    if _RICH:
        table = Table(box=box.SIMPLE_HEAVY, show_header=True)
        table.add_column('Field', style='bold')
        table.add_column(f'File A  ({match.xref_a})', style='cyan')
        table.add_column(f'File B  ({match.xref_b})', style='green')

        def _add_name_row(ind: Individual) -> str:
            names = [n.full for n in ind.names]
            return '\n'.join(names) if names else '—'

        table.add_row('Name', _add_name_row(ind_a), _add_name_row(ind_b))
        table.add_row('Sex', ind_a.sex or '—', ind_b.sex or '—')
        table.add_row('Birth', _ev(ind_a, 'BIRT'), _ev(ind_b, 'BIRT'))
        table.add_row('Death', _ev(ind_a, 'DEAT'), _ev(ind_b, 'DEAT'))
        table.add_row('Parents', _parents(ind_a, file_a), _parents(ind_b, file_b))
        table.add_row('Sources', str(len(ind_a.citations) + sum(len(e.citations) for e in ind_a.events)),
                      str(len(ind_b.citations) + sum(len(e.citations) for e in ind_b.events)))

        console.print(Panel(
            table,
            title=f'CANDIDATE MATCH (score: {match.score:.2f})',
        ))
        choice = Prompt.ask('[M] Merge  [S] Skip  [D] Detail', choices=['m', 's', 'd'], default='s')
    else:
        print(f'\nCANDIDATE MATCH (score: {match.score:.2f})')
        print(f'  A: {_indi_summary(ind_a)}')
        print(f'  B: {_indi_summary(ind_b)}')
        choice = input('[M]erge / [S]kip / [D]etail: ').strip().lower()

    return choice or 's'


def _show_source_conflict(
    match: SourceMatch,
    file_a: GedcomFile,
    file_b: GedcomFile,
    console,
) -> str:
    src_a = file_a.sources.get(match.xref_a)
    src_b = file_b.sources.get(match.xref_b)

    if _RICH:
        table = Table(box=box.SIMPLE_HEAVY)
        table.add_column('Field', style='bold')
        table.add_column('File A', style='cyan')
        table.add_column('File B', style='green')
        table.add_row('Title', src_a.title if src_a else '—', src_b.title if src_b else '—')
        table.add_row('Author', (src_a.author or '—') if src_a else '—', (src_b.author or '—') if src_b else '—')
        console.print(Panel(table, title=f'SOURCE CANDIDATE MATCH (score: {match.score:.2f})'))
        choice = Prompt.ask('[M] Merge  [S] Skip', choices=['m', 's'], default='m')
    else:
        print(f'\nSOURCE CANDIDATE (score: {match.score:.2f})')
        print(f'  A: {_source_summary(src_a) if src_a else match.xref_a}')
        print(f'  B: {_source_summary(src_b) if src_b else match.xref_b}')
        choice = input('[M]erge / [S]kip: ').strip().lower()

    return choice or 'm'


# ---------------------------------------------------------------------------
# Mode 3: Unmatched records
# ---------------------------------------------------------------------------

def _review_unmatched_indi(
    xref_b: str,
    file_b: GedcomFile,
    console,
) -> str:
    """Returns 'add', 'skip', or 'link'."""
    ind = file_b.individuals.get(xref_b)
    summary = _indi_summary(ind) if ind else xref_b

    if _RICH:
        console.print(f'\n[yellow]UNMATCHED:[/yellow] {summary}')
        console.print('  → No match in File A.')
        choice = Prompt.ask('[A] Add  [S] Skip  [L] Link', choices=['a', 's', 'l'], default='a')
    else:
        print(f'\nUNMATCHED: {summary}')
        print('  → No match in File A.')
        choice = input('[A]dd / [S]kip / [L]ink: ').strip().lower()

    return {'a': 'add', 's': 'skip', 'l': 'link'}.get(choice, 'add')


def _review_unmatched_source(
    xref_b: str,
    file_b: GedcomFile,
    console,
) -> str:
    """Returns 'add', 'skip'."""
    src = file_b.sources.get(xref_b)
    summary = _source_summary(src) if src else xref_b

    if _RICH:
        console.print(f'\n[yellow]UNMATCHED SOURCE:[/yellow] {summary}')
        choice = Prompt.ask('[A] Add  [S] Skip', choices=['a', 's'], default='a')
    else:
        print(f'\nUNMATCHED SOURCE: {summary}')
        choice = input('[A]dd / [S]kip: ').strip().lower()

    return {'a': 'add', 's': 'skip'}.get(choice, 'add')


# ---------------------------------------------------------------------------
# Main review orchestration
# ---------------------------------------------------------------------------

def run_review(
    source_result: SourceMatchResult,
    indi_result: IndividualMatchResult,
    fam_result: FamilyMatchResult,
    file_a: GedcomFile,
    file_b: GedcomFile,
    session: SessionState | None = None,
    session_path: str | None = None,
    batch: bool = False,
) -> MergeDecisions:
    """
    Run the full interactive review process.

    If batch=True, auto-approves all auto-matches and adds all unmatched records
    without prompting.

    Returns a MergeDecisions with all confirmed matches and dispositions.
    """
    console = _console()
    decisions = MergeDecisions()

    # Restore from session if resuming
    if session:
        decisions.source_map = dict(session.source_map)
        decisions.indi_map = dict(session.indi_map)
        decisions.family_map = dict(session.family_map)
        decisions.source_disposition = dict(session.source_disposition)
        decisions.indi_disposition = dict(session.indi_disposition)
        decisions.family_disposition = dict(session.family_disposition)

    start_src_idx = session.source_candidate_idx if session else 0
    start_indi_idx = session.indi_candidate_idx if session else 0
    auto_approved = session.auto_approved if session else False

    # ---- Phase 1: Batch approval of auto-matches ----
    if not auto_approved:
        if batch:
            approve_all = True
        else:
            approve_all = _show_batch_approval(
                source_result, indi_result, fam_result, file_a, file_b, console
            )

        if approve_all:
            for m in source_result.auto_matches:
                decisions.source_map[m.xref_b] = m.xref_a
            for m in indi_result.auto_matches:
                decisions.indi_map[m.xref_b] = m.xref_a
            for m in fam_result.matches:
                decisions.family_map[m.xref_b] = m.xref_a
        else:
            # Review individually — treat auto-matches as candidates
            for m in source_result.auto_matches:
                choice = _show_source_conflict(m, file_a, file_b, console)
                if choice == 'm':
                    decisions.source_map[m.xref_b] = m.xref_a
            for m in indi_result.auto_matches:
                while True:
                    choice = _show_individual_conflict(m, file_a, file_b, console)
                    if choice == 'd':
                        # Show detail (same as 'm' for now, could expand)
                        continue
                    break
                if choice == 'm':
                    decisions.indi_map[m.xref_b] = m.xref_a
            for m in fam_result.matches:
                decisions.family_map[m.xref_b] = m.xref_a

        if session:
            session.auto_approved = True
            if session_path:
                _save_session_decisions(session, decisions)
                save_session(session_path, session)

    # ---- Phase 2: Review candidate (ambiguous) matches ----
    if not batch:
        for idx, m in enumerate(source_result.candidates):
            if idx < start_src_idx:
                continue
            if m.xref_b in decisions.source_map:
                continue
            choice = _show_source_conflict(m, file_a, file_b, console)
            if choice == 'm':
                decisions.source_map[m.xref_b] = m.xref_a
            if session:
                session.source_candidate_idx = idx + 1
                _save_session_decisions(session, decisions)
                if session_path:
                    save_session(session_path, session)

        for idx, m in enumerate(indi_result.candidates):
            if idx < start_indi_idx:
                continue
            if m.xref_b in decisions.indi_map:
                continue
            while True:
                choice = _show_individual_conflict(m, file_a, file_b, console)
                if choice != 'd':
                    break
            if choice == 'm':
                decisions.indi_map[m.xref_b] = m.xref_a
            if session:
                session.indi_candidate_idx = idx + 1
                _save_session_decisions(session, decisions)
                if session_path:
                    save_session(session_path, session)

    # ---- Phase 3: Unmatched records ----
    for xref_b in source_result.unmatched_b:
        if xref_b in decisions.source_map or xref_b in decisions.source_disposition:
            continue
        if batch:
            decisions.source_disposition[xref_b] = 'add'
        else:
            disp = _review_unmatched_source(xref_b, file_b, console)
            decisions.source_disposition[xref_b] = disp

    for xref_b in indi_result.unmatched_b:
        if xref_b in decisions.indi_map or xref_b in decisions.indi_disposition:
            continue
        if batch:
            decisions.indi_disposition[xref_b] = 'add'
        else:
            disp = _review_unmatched_indi(xref_b, file_b, console)
            if disp == 'link':
                # Simplified: treat 'link' as 'skip' (full link UI would need more work)
                disp = 'skip'
            decisions.indi_disposition[xref_b] = disp

    for xref_b in fam_result.unmatched_b:
        if xref_b in decisions.family_map or xref_b in decisions.family_disposition:
            continue
        decisions.family_disposition[xref_b] = 'add'

    return decisions


def _save_session_decisions(session: SessionState, decisions: MergeDecisions) -> None:
    session.source_map = dict(decisions.source_map)
    session.indi_map = dict(decisions.indi_map)
    session.family_map = dict(decisions.family_map)
    session.source_disposition = dict(decisions.source_disposition)
    session.indi_disposition = dict(decisions.indi_disposition)
    session.family_disposition = dict(decisions.family_disposition)
