"""
analysis.py — Post-merge data quality analysis.

Checks the in-memory GedcomFile for common merge artifacts:
  1. Broken cross-references (dangling CHIL/HUSB/WIFE/FAMS/FAMC/SOUR/OBJE pointers)
  2. Duplicate families (same husband+wife pair with different xrefs)
  3. Duplicate sources (same normalized title with different xrefs)
  4. Orphaned individuals (no FAMS and no FAMC)
  5. Duplicate NAME entries within an individual
  6. Excessive or duplicate citations on events
  7. Empty family shells (HUSB/WIFE only, no events or children)
"""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field

from gedcom_merge.model import GedcomFile
from gedcom_merge.normalize import tokenize_title


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------

@dataclass
class AnalysisReport:
    broken_xrefs: list[str] = field(default_factory=list)
    # "FAM @F274@: CHIL @I242730475531@ not defined"

    duplicate_families: list[tuple[str, str]] = field(default_factory=list)
    # (xref_a, xref_b) — same husband+wife, different xrefs

    duplicate_sources: list[tuple[str, str]] = field(default_factory=list)
    # (xref_a, xref_b) — same normalized title, different xrefs

    orphaned_individuals: list[str] = field(default_factory=list)
    # xrefs with no FAMS and no FAMC

    duplicate_names: dict[str, list[str]] = field(default_factory=dict)
    # xref → list of NAME strings that appear more than once

    excessive_citations: list[tuple[str, str, int]] = field(default_factory=list)
    # (indi_xref, event_tag, count) — events with unusually many citations

    duplicate_citations: list[tuple[str, str, str, str]] = field(default_factory=list)
    # (indi_xref, event_tag, source_xref, page) — same citation appearing twice on one event

    empty_families: list[str] = field(default_factory=list)
    # xrefs of FAM records with only HUSB/WIFE — no events, no children

    def has_issues(self) -> bool:
        return self.issue_count() > 0

    def issue_count(self) -> int:
        return (
            len(self.broken_xrefs)
            + len(self.duplicate_families)
            + len(self.duplicate_sources)
            + len(self.orphaned_individuals)
            + sum(len(v) for v in self.duplicate_names.values())
            + len(self.excessive_citations)
            + len(self.duplicate_citations)
            + len(self.empty_families)
        )

    def print_summary(self) -> None:
        if self.broken_xrefs:
            print(f'  Broken cross-references ({len(self.broken_xrefs)}):')
            for msg in self.broken_xrefs[:10]:
                print(f'    {msg}')
            if len(self.broken_xrefs) > 10:
                print(f'    ... and {len(self.broken_xrefs) - 10} more')

        if self.duplicate_families:
            print(f'  Duplicate families ({len(self.duplicate_families)} pairs):')
            for a, b in self.duplicate_families[:5]:
                print(f'    {a} == {b}')
            if len(self.duplicate_families) > 5:
                print(f'    ... and {len(self.duplicate_families) - 5} more')

        if self.duplicate_sources:
            print(f'  Duplicate sources ({len(self.duplicate_sources)} pairs):')
            for a, b in self.duplicate_sources[:5]:
                print(f'    {a} == {b}')
            if len(self.duplicate_sources) > 5:
                print(f'    ... and {len(self.duplicate_sources) - 5} more')

        if self.orphaned_individuals:
            print(f'  Orphaned individuals (no family links): {len(self.orphaned_individuals)}')
            for xref in self.orphaned_individuals[:5]:
                print(f'    {xref}')
            if len(self.orphaned_individuals) > 5:
                print(f'    ... and {len(self.orphaned_individuals) - 5} more')

        if self.duplicate_names:
            total = sum(len(v) for v in self.duplicate_names.values())
            print(f'  Duplicate NAME entries ({total} across {len(self.duplicate_names)} individuals):')
            for xref, names in list(self.duplicate_names.items())[:3]:
                print(f'    {xref}: {names}')

        if self.excessive_citations:
            print(f'  Events with excessive citations (>{_EXCESSIVE_THRESHOLD}): {len(self.excessive_citations)}')
            for xref, tag, count in self.excessive_citations[:5]:
                print(f'    {xref} {tag}: {count} citations')
            if len(self.excessive_citations) > 5:
                print(f'    ... and {len(self.excessive_citations) - 5} more')

        if self.duplicate_citations:
            print(f'  Duplicate citations on events ({len(self.duplicate_citations)}):')
            for xref, tag, src, page in self.duplicate_citations[:5]:
                print(f'    {xref} {tag}: {src} "{page}"')
            if len(self.duplicate_citations) > 5:
                print(f'    ... and {len(self.duplicate_citations) - 5} more')

        if self.empty_families:
            print(f'  Empty family shells (no events/children): {len(self.empty_families)}')


# ---------------------------------------------------------------------------
# Threshold for "excessive" citations
# ---------------------------------------------------------------------------

_EXCESSIVE_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Sub-checks
# ---------------------------------------------------------------------------

def _check_broken_xrefs(merged: GedcomFile) -> list[str]:
    """
    Verify all cross-references point to existing records.
    Checks: FAM HUSB/WIFE/CHIL → INDI, INDI FAMS/FAMC → FAM,
            citations SOUR → SOUR, INDI OBJE → OBJE.
    """
    errors: list[str] = []
    indi_xrefs = set(merged.individuals)
    fam_xrefs = set(merged.families)
    sour_xrefs = set(merged.sources)
    obje_xrefs = set(merged.media)

    for fam_xref, fam in merged.families.items():
        if fam.husband_xref and fam.husband_xref not in indi_xrefs:
            errors.append(f'FAM {fam_xref}: HUSB {fam.husband_xref} not defined')
        if fam.wife_xref and fam.wife_xref not in indi_xrefs:
            errors.append(f'FAM {fam_xref}: WIFE {fam.wife_xref} not defined')
        for child in fam.child_xrefs:
            if child not in indi_xrefs:
                errors.append(f'FAM {fam_xref}: CHIL {child} not defined')
        for cit in fam.citations:
            if cit.source_xref not in sour_xrefs:
                errors.append(f'FAM {fam_xref}: SOUR {cit.source_xref} not defined')

    for indi_xref, indi in merged.individuals.items():
        for fams in indi.family_spouse:
            if fams not in fam_xrefs:
                errors.append(f'INDI {indi_xref}: FAMS {fams} not defined')
        for famc in indi.family_child:
            if famc not in fam_xrefs:
                errors.append(f'INDI {indi_xref}: FAMC {famc} not defined')
        for obje in indi.media:
            if obje not in obje_xrefs:
                errors.append(f'INDI {indi_xref}: OBJE {obje} not defined')
        for cit in indi.citations:
            if cit.source_xref not in sour_xrefs:
                errors.append(f'INDI {indi_xref}: SOUR {cit.source_xref} not defined')
        for ev in indi.events:
            for cit in ev.citations:
                if cit.source_xref not in sour_xrefs:
                    errors.append(f'INDI {indi_xref} {ev.tag}: SOUR {cit.source_xref} not defined')
        for nm in indi.names:
            for cit in nm.citations:
                if cit.source_xref not in sour_xrefs:
                    errors.append(f'INDI {indi_xref} NAME: SOUR {cit.source_xref} not defined')

    for sour_xref, sour in merged.sources.items():
        if sour.repository_xref and sour.repository_xref not in merged.repositories:
            errors.append(f'SOUR {sour_xref}: REPO {sour.repository_xref} not defined')

    return errors


def _find_duplicate_families(merged: GedcomFile) -> list[tuple[str, str]]:
    """
    Group FAM records by (husband_xref or '', wife_xref or '').
    Return pairs of xrefs that share the same couple key.
    """
    by_couple: dict[tuple[str, str], list[str]] = defaultdict(list)
    for xref, fam in merged.families.items():
        key = (fam.husband_xref or '', fam.wife_xref or '')
        if key != ('', ''):  # skip families with neither spouse
            by_couple[key].append(xref)

    pairs: list[tuple[str, str]] = []
    for xrefs in by_couple.values():
        if len(xrefs) > 1:
            # Emit all pairs
            for i in range(len(xrefs)):
                for j in range(i + 1, len(xrefs)):
                    pairs.append((xrefs[i], xrefs[j]))
    return pairs


def _find_duplicate_sources(merged: GedcomFile) -> list[tuple[str, str]]:
    """
    Group SOUR records by their normalized title token set.
    Return pairs of xrefs that share the same title fingerprint.
    Uses tokenize_title() from normalize.py (frozenset for hashability).
    """
    by_title: dict[frozenset[str], list[str]] = defaultdict(list)
    for xref, sour in merged.sources.items():
        if sour.title:
            key = frozenset(tokenize_title(sour.title))
            if key:
                by_title[key].append(xref)

    pairs: list[tuple[str, str]] = []
    for xrefs in by_title.values():
        if len(xrefs) > 1:
            for i in range(len(xrefs)):
                for j in range(i + 1, len(xrefs)):
                    pairs.append((xrefs[i], xrefs[j]))
    return pairs


def _find_orphaned_individuals(merged: GedcomFile) -> list[str]:
    """Return xrefs of individuals who are disconnected from the rest of the tree.

    An individual is considered connected if they have at least one of:
      - FAMS (spouse link to a family record)
      - FAMC (child link to a family record)
      - ASSOC (association to another individual, e.g. godparent, witness)

    ASSOC links are checked via the raw GedcomNode because they are not
    promoted into Individual fields — they express relationships (godparent,
    witness, etc.) that do not create a family record but do tie the person
    to someone else in the tree.
    """
    result = []
    for xref, indi in merged.individuals.items():
        if indi.family_spouse or indi.family_child:
            continue
        if indi.raw.all_children('ASSOC'):
            continue
        result.append(xref)
    return result


def _find_duplicate_names(merged: GedcomFile) -> dict[str, list[str]]:
    """
    For each individual, find NAME strings that appear more than once.
    Returns {xref: [duplicate_name_strings]} for individuals that have any duplicates.
    """
    result: dict[str, list[str]] = {}
    for xref, indi in merged.individuals.items():
        seen: dict[str, int] = defaultdict(int)
        for nm in indi.names:
            seen[nm.full] += 1
        dups = [name for name, count in seen.items() if count > 1]
        if dups:
            result[xref] = dups
    return result


def _find_citation_issues(
    merged: GedcomFile,
    excessive_threshold: int = _EXCESSIVE_THRESHOLD,
) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, str, str]]]:
    """
    For each individual's events:
    - Excessive: citation count > excessive_threshold
    - Duplicate: same (source_xref, page) appearing more than once on one event
    Returns (excessive_list, duplicate_list).
    """
    excessive: list[tuple[str, str, int]] = []
    duplicates: list[tuple[str, str, str, str]] = []

    for indi_xref, indi in merged.individuals.items():
        for ev in indi.events:
            count = len(ev.citations)
            if count > excessive_threshold:
                excessive.append((indi_xref, ev.tag, count))

            seen_keys: dict[tuple[str, str], int] = defaultdict(int)
            for cit in ev.citations:
                key = (cit.source_xref, cit.page or '')
                seen_keys[key] += 1
            for (src, page), n in seen_keys.items():
                if n > 1:
                    duplicates.append((indi_xref, ev.tag, src, page))

    return excessive, duplicates


def _find_empty_families(merged: GedcomFile) -> list[str]:
    """
    Return xrefs of FAM records that have a spouse link but no events and no children.
    These are merge-created shells with no genealogical content.
    """
    empty: list[str] = []
    for xref, fam in merged.families.items():
        has_spouse = fam.husband_xref or fam.wife_xref
        has_content = fam.events or fam.child_xrefs or fam.citations
        if has_spouse and not has_content:
            empty.append(xref)
    return empty


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze_merged(merged: GedcomFile) -> AnalysisReport:
    """
    Run all data quality checks on the merged GedcomFile.
    Returns an AnalysisReport summarizing all issues found.
    """
    excessive, dup_cits = _find_citation_issues(merged)

    return AnalysisReport(
        broken_xrefs=_check_broken_xrefs(merged),
        duplicate_families=_find_duplicate_families(merged),
        duplicate_sources=_find_duplicate_sources(merged),
        orphaned_individuals=_find_orphaned_individuals(merged),
        duplicate_names=_find_duplicate_names(merged),
        excessive_citations=excessive,
        duplicate_citations=dup_cits,
        empty_families=_find_empty_families(merged),
    )
