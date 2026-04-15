"""
match_families.py — Match family records between two GEDCOM files.

Family matching is derived from individual matches — no separate scoring needed.
A family in B matches a family in A if:
  - Both husband and wife match, OR
  - One spouse matches AND ≥1 child matches, OR
  - ≥2 children match AND no spouse contradicts
"""

from __future__ import annotations

from gedcom_merge.model import (
    GedcomFile, FamilyMatch, FamilyMatchResult,
)


def match_families(
    file_a: GedcomFile,
    file_b: GedcomFile,
    indi_map: dict[str, str],   # xref_b → xref_a (confirmed individual matches)
) -> FamilyMatchResult:
    """
    Derive family matches from confirmed individual matches.
    """
    matches: list[FamilyMatch] = []
    matched_b: set[str] = set()

    # Build reverse index for File A: (husb_a, wife_a) → family_a_xref
    # and husb_a → [fam_xrefs], wife_a → [fam_xrefs]
    by_couple: dict[tuple[str | None, str | None], str] = {}
    by_husb: dict[str, list[str]] = {}
    by_wife: dict[str, list[str]] = {}
    by_child: dict[str, list[str]] = {}

    for xref_a, fam_a in file_a.families.items():
        key = (fam_a.husband_xref, fam_a.wife_xref)
        by_couple[key] = xref_a
        if fam_a.husband_xref:
            by_husb.setdefault(fam_a.husband_xref, []).append(xref_a)
        if fam_a.wife_xref:
            by_wife.setdefault(fam_a.wife_xref, []).append(xref_a)
        for chil in fam_a.child_xrefs:
            by_child.setdefault(chil, []).append(xref_a)

    for xref_b, fam_b in file_b.families.items():
        # Translate B member xrefs to A xrefs
        husb_a = indi_map.get(fam_b.husband_xref) if fam_b.husband_xref else None
        wife_a = indi_map.get(fam_b.wife_xref) if fam_b.wife_xref else None
        children_a = [indi_map[c] for c in fam_b.child_xrefs if c in indi_map]

        matched_fam_a: str | None = None

        # --- Criterion 1: both spouses match ---
        if husb_a and wife_a:
            fam_a_xref = by_couple.get((husb_a, wife_a))
            if fam_a_xref:
                matched_fam_a = fam_a_xref

        # --- Criterion 2: one spouse + ≥1 child match ---
        if not matched_fam_a:
            candidate_fams: set[str] = set()
            if husb_a:
                candidate_fams.update(by_husb.get(husb_a, []))
            if wife_a:
                candidate_fams.update(by_wife.get(wife_a, []))
            for fam_a_xref in candidate_fams:
                fam_a = file_a.families[fam_a_xref]
                shared_children = [c for c in children_a if c in fam_a.child_xrefs]
                if shared_children:
                    matched_fam_a = fam_a_xref
                    break

        # --- Criterion 3: ≥2 children match, no spouse contradiction ---
        if not matched_fam_a and len(children_a) >= 2:
            # Find all families in A that contain these children
            fam_child_counts: dict[str, int] = {}
            for chil_a in children_a:
                for fam_a_xref in by_child.get(chil_a, []):
                    fam_child_counts[fam_a_xref] = fam_child_counts.get(fam_a_xref, 0) + 1

            for fam_a_xref, count in sorted(fam_child_counts.items(), key=lambda x: -x[1]):
                if count < 2:
                    break
                fam_a = file_a.families[fam_a_xref]
                # Check no spouse contradiction
                if husb_a and fam_a.husband_xref and fam_a.husband_xref != husb_a:
                    continue
                if wife_a and fam_a.wife_xref and fam_a.wife_xref != wife_a:
                    continue
                matched_fam_a = fam_a_xref
                break

        if matched_fam_a:
            matches.append(FamilyMatch(xref_a=matched_fam_a, xref_b=xref_b))
            matched_b.add(xref_b)

    unmatched_b = [xref for xref in file_b.families if xref not in matched_b]

    return FamilyMatchResult(matches=matches, unmatched_b=unmatched_b)
