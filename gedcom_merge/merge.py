"""
merge.py — Merge matched GEDCOM records into a single unified GedcomFile.

The primary file's structure is preserved. Records from the secondary file are
integrated following the rules in the spec:
  - More specific dates/places win
  - Name variants union (B primary → AKA if different from A primary)
  - Citations union and deduplicate
  - No data is silently discarded

All changes are tracked in MergeStats for the report.
"""

from __future__ import annotations
import copy
from dataclasses import dataclass, field

from gedcom_merge.model import (
    GedcomFile, GedcomNode,
    Individual, Family, Source, Repository, MediaObject, Note,
    NameRecord, EventRecord, CitationRecord, ParsedDate,
    MergeDecisions,
)
from gedcom_merge.normalize import (
    normalize_name_str, parse_date, date_overlap_score, place_similarity,
    extract_parenthetical_surnames, strip_parentheticals,
)


# ---------------------------------------------------------------------------
# Merge statistics (fed to report.py)
# ---------------------------------------------------------------------------

@dataclass
class MergeStats:
    indi_matched_auto: int = 0
    indi_matched_manual: int = 0
    indi_added: int = 0
    indi_skipped: int = 0

    fam_matched_auto: int = 0
    fam_matched_manual: int = 0
    fam_added: int = 0

    source_matched_auto: int = 0
    source_matched_manual: int = 0
    source_added: int = 0
    source_skipped: int = 0

    birth_date_preferred_a: int = 0
    birth_place_preferred_b: int = 0
    aka_names_added: int = 0
    events_added_from_b: int = 0
    citations_added_from_b: int = 0
    date_conflicts_exact_wins: int = 0   # approximate discarded in favour of exact
    date_conflicts_kept_both: int = 0    # meaningfully different dates kept as separate events

    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ID remapping helpers
# ---------------------------------------------------------------------------

def _build_id_map(
    file_a: GedcomFile,
    file_b: GedcomFile,
    decisions: MergeDecisions,
    stats: MergeStats,
) -> dict[str, str]:
    """
    Build a complete xref_b → xref_a mapping for all B records.

    Matched records point to their A counterpart.
    Unmatched records that are 'add' get a new unique xref.
    """
    id_map: dict[str, str] = {}

    # Matched sources
    for xref_b, xref_a in decisions.source_map.items():
        id_map[xref_b] = xref_a

    # Matched individuals
    for xref_b, xref_a in decisions.indi_map.items():
        id_map[xref_b] = xref_a

    # Matched families
    for xref_b, xref_a in decisions.family_map.items():
        id_map[xref_b] = xref_a

    # Unmatched records to add → generate new IDs
    _counter = {'I': 0, 'F': 0, 'S': 0, 'R': 0, 'O': 0, 'N': 0}

    def _new_id(prefix: str) -> str:
        _counter[prefix] += 1
        return f'@{prefix}_MERGE_{_counter[prefix]:04d}@'

    for xref_b, disp in decisions.indi_disposition.items():
        if xref_b not in id_map:
            if disp == 'add':
                id_map[xref_b] = _new_id('I')
                stats.indi_added += 1
            else:
                stats.indi_skipped += 1

    for xref_b, disp in decisions.family_disposition.items():
        if xref_b not in id_map:
            if disp == 'add':
                id_map[xref_b] = _new_id('F')
                stats.fam_added += 1

    # Ensure all individuals referenced by added B families have IDs.
    # Without this, a family added from B can reference B individual xrefs that
    # were never reviewed (defaulting to 'skip'), leaving dangling HUSB/WIFE/CHIL.
    for xref_b, fam_b in file_b.families.items():
        disp = decisions.family_disposition.get(xref_b, 'skip')
        if xref_b not in decisions.family_map and disp == 'add' and xref_b in id_map:
            for member_xref in [fam_b.husband_xref, fam_b.wife_xref] + fam_b.child_xrefs:
                if member_xref and member_xref not in id_map:
                    id_map[member_xref] = _new_id('I')
                    stats.indi_added += 1

    for xref_b, disp in decisions.source_disposition.items():
        if xref_b not in id_map:
            if disp == 'add':
                id_map[xref_b] = _new_id('S')
                stats.source_added += 1
            else:
                stats.source_skipped += 1

    # Repositories and media from B: always add (they're referenced)
    for xref_b in file_b.repositories:
        if xref_b not in id_map:
            id_map[xref_b] = _new_id('R')

    for xref_b in file_b.media:
        if xref_b not in id_map:
            id_map[xref_b] = _new_id('O')

    for xref_b in file_b.notes:
        if xref_b not in id_map:
            id_map[xref_b] = _new_id('N')

    # Final pass: collect all source/repo/media xrefs referenced by B individuals
    # and B families that have been assigned IDs (either via review or auto-add).
    # Their citations must resolve — auto-add any sources not yet in id_map.
    def _collect_cit_sources(citations: list) -> list[str]:
        return [c.source_xref for c in citations if c.source_xref]

    for xref_b, ind_b in file_b.individuals.items():
        if xref_b not in id_map:
            continue  # not being added — skip
        all_source_xrefs = _collect_cit_sources(ind_b.citations)
        for ev in ind_b.events:
            all_source_xrefs.extend(_collect_cit_sources(ev.citations))
        for sx in all_source_xrefs:
            if sx not in id_map:
                id_map[sx] = _new_id('S')
                stats.source_added += 1
                # Also auto-add that source's repository if needed
                src_b = file_b.sources.get(sx)
                if src_b and src_b.repository_xref and src_b.repository_xref not in id_map:
                    id_map[src_b.repository_xref] = _new_id('R')

    for xref_b, fam_b in file_b.families.items():
        if xref_b not in id_map:
            continue
        all_source_xrefs = _collect_cit_sources(fam_b.citations)
        for ev in fam_b.events:
            all_source_xrefs.extend(_collect_cit_sources(ev.citations))
        for sx in all_source_xrefs:
            if sx not in id_map:
                id_map[sx] = _new_id('S')
                stats.source_added += 1
                src_b = file_b.sources.get(sx)
                if src_b and src_b.repository_xref and src_b.repository_xref not in id_map:
                    id_map[src_b.repository_xref] = _new_id('R')

    return id_map


def _remap(xref: str | None, id_map: dict[str, str]) -> str | None:
    if xref is None:
        return None
    return id_map.get(xref, xref)  # If not in map, assume it's already an A xref


def _remap_raw_node(node: GedcomNode, id_map: dict[str, str]) -> GedcomNode:
    """
    Return a deep copy of a GedcomNode tree with all xref-format values remapped.

    Any value that looks like @XREF@ and exists in id_map is replaced with its
    mapped value. This ensures raw nodes from File B that are written directly
    (for non-standard tags) have their source/individual/family xrefs remapped.
    """
    def _remap_value(val: str) -> str:
        if val and val.startswith('@') and val.endswith('@') and val in id_map:
            return id_map[val]
        return val

    def _clone(n: GedcomNode) -> GedcomNode:
        return GedcomNode(
            level=n.level,
            tag=n.tag,
            value=_remap_value(n.value),
            xref=n.xref,  # top-level xref is set by the caller, not remapped here
            children=[_clone(c) for c in n.children],
        )

    return _clone(node)


def _remap_citation(cit: CitationRecord, id_map: dict[str, str]) -> CitationRecord:
    return CitationRecord(
        source_xref=_remap(cit.source_xref, id_map) or cit.source_xref,
        page=cit.page,
        data=cit.data,
        raw=cit.raw,
    )


def _remap_citations(
    citations: list[CitationRecord], id_map: dict[str, str]
) -> list[CitationRecord]:
    return [_remap_citation(c, id_map) for c in citations]


# ---------------------------------------------------------------------------
# Citation deduplication
# ---------------------------------------------------------------------------

def _citation_key(cit: CitationRecord) -> tuple[str, str]:
    """Dedup key: (source_xref, page). Empty page treated as ''."""
    return (cit.source_xref, cit.page or '')


def _merge_citations(
    cits_a: list[CitationRecord],
    cits_b: list[CitationRecord],
    id_map: dict[str, str],
    stats: MergeStats,
) -> list[CitationRecord]:
    """
    Union citations from A and B. Deduplicate by (source_xref, page).
    When one PAGE is a substring of the other, keep the more complete one.
    """
    result: list[CitationRecord] = list(cits_a)
    seen: dict[str, CitationRecord] = {}
    for c in cits_a:
        seen[c.source_xref] = c  # track by source xref for substring check

    for cit_b in _remap_citations(cits_b, id_map):
        key = _citation_key(cit_b)
        # Check for exact duplicate
        if any(_citation_key(c) == key for c in result):
            continue
        # Check substring: if B's page is a substring of an existing citation, skip
        existing = seen.get(cit_b.source_xref)
        if existing and existing.page and cit_b.page:
            if cit_b.page in existing.page:
                continue  # existing is more complete
            if existing.page in cit_b.page:
                # B is more complete — keep B, remove existing
                result = [c for c in result if c is not existing]
        result.append(cit_b)
        seen[cit_b.source_xref] = cit_b
        stats.citations_added_from_b += 1

    return result


# ---------------------------------------------------------------------------
# Date / place preference
# ---------------------------------------------------------------------------

def _prefer_date(d_a: ParsedDate | None, d_b: ParsedDate | None) -> ParsedDate | None:
    """Return the more specific date."""
    if d_a is None:
        return d_b
    if d_b is None:
        return d_a
    return d_a if d_a.specificity() >= d_b.specificity() else d_b


def _prefer_place(p_a: str | None, p_b: str | None) -> str | None:
    """Return the more specific place (more hierarchical components)."""
    if not p_a:
        return p_b
    if not p_b:
        return p_a
    parts_a = [p.strip() for p in p_a.split(',') if p.strip()]
    parts_b = [p.strip() for p in p_b.split(',') if p.strip()]
    return p_b if len(parts_b) > len(parts_a) else p_a


# ---------------------------------------------------------------------------
# Event matching and merging
# ---------------------------------------------------------------------------

def _events_similar(ev_a: EventRecord, ev_b: EventRecord) -> bool:
    """True if two events represent the same life event."""
    if ev_a.tag != ev_b.tag:
        return False
    if ev_a.event_type != ev_b.event_type:
        return False
    # For unique events (birth, death) always merge if tag matches
    if ev_a.tag in ('BIRT', 'DEAT', 'BURI'):
        return True
    # For others, require approximate date match or both missing
    if ev_a.date is None and ev_b.date is None:
        return True
    score = date_overlap_score(ev_a.date, ev_b.date)
    return score >= 0.5


def _merge_event(
    ev_a: EventRecord,
    ev_b: EventRecord,
    id_map: dict[str, str],
    stats: MergeStats,
) -> EventRecord:
    """Merge ev_b into ev_a. Prefer more specific date/place."""
    merged_date = _prefer_date(ev_a.date, ev_b.date)
    merged_place = _prefer_place(ev_a.place, ev_b.place)
    merged_cits = _merge_citations(ev_a.citations, ev_b.citations, id_map, stats)

    # Rebuild raw node (keep A's raw, update value if needed)
    return EventRecord(
        tag=ev_a.tag,
        event_type=ev_a.event_type or ev_b.event_type,
        date=merged_date,
        place=merged_place,
        citations=merged_cits,
        raw=ev_a.raw,  # preserve A's raw node
    )


def _merge_events(
    events_a: list[EventRecord],
    events_b: list[EventRecord],
    id_map: dict[str, str],
    stats: MergeStats,
) -> list[EventRecord]:
    """
    Match events by (tag + event_type + approximate date), then merge matched
    pairs with nuanced date-conflict handling:

    Case 1 — one approximate, one exact, close (overlap score ≥ 0.4):
        Keep the exact date only. Citations stay with the exact event;
        the approximate's citations are dropped. Place merged (more specific wins).
        → stats.date_conflicts_exact_wins

    Case 2 — meaningfully different dates (year gap > 2):
        Keep both as separate events. Primary = better sourced (more citations;
        ties go to File A). Alternate gets event_type='alternate'. Citations
        are NOT merged — each event keeps only its own.
        → stats.date_conflicts_kept_both

    Case 3 — same or overlapping dates, similar specificity:
        Standard merge — prefer more specific date/place, union citations.

    Unmatched B events are always appended.
    """
    result: list[EventRecord] = []
    used_b: set[int] = set()

    for ev_a in events_a:
        # Find first matching B event
        best_b_idx = None
        for i, ev_b in enumerate(events_b):
            if i in used_b:
                continue
            if _events_similar(ev_a, ev_b):
                best_b_idx = i
                break

        if best_b_idx is None:
            result.append(ev_a)
            continue

        ev_b = events_b[best_b_idx]
        used_b.add(best_b_idx)

        # Both dates must be present with a year for conflict detection
        a_year = ev_a.date.year if ev_a.date else None
        b_year = ev_b.date.year if ev_b.date else None
        a_approx = ev_a.date is not None and ev_a.date.qualifier is not None
        b_approx = ev_b.date is not None and ev_b.date.qualifier is not None

        # Case 1: one approximate, one exact, close → keep the exact date
        if a_year and b_year and (a_approx != b_approx):
            from gedcom_merge.normalize import date_overlap_score as _dos
            overlap = _dos(ev_a.date, ev_b.date)
            if overlap >= 0.4:
                exact_ev = ev_b if a_approx else ev_a
                raw = exact_ev.raw if exact_ev is ev_a else _remap_raw_node(exact_ev.raw, id_map)
                result.append(EventRecord(
                    tag=exact_ev.tag,
                    event_type=exact_ev.event_type,
                    date=exact_ev.date,
                    place=_prefer_place(ev_a.place, ev_b.place),
                    citations=_remap_citations(exact_ev.citations, id_map),
                    raw=raw,
                ))
                stats.date_conflicts_exact_wins += 1
                continue

        # Case 2: meaningfully different years (gap > 2) → keep both
        if a_year and b_year and abs(a_year - b_year) > 2:
            cits_a = _remap_citations(ev_a.citations, id_map)
            cits_b = _remap_citations(ev_b.citations, id_map)
            # Primary = better sourced; ties → File A wins
            a_is_primary = len(ev_a.citations) >= len(ev_b.citations)
            primary_ev, alt_ev = (ev_a, ev_b) if a_is_primary else (ev_b, ev_a)
            primary_cits, alt_cits = (cits_a, cits_b) if a_is_primary else (cits_b, cits_a)

            primary_raw = primary_ev.raw if primary_ev is ev_a else _remap_raw_node(primary_ev.raw, id_map)
            alt_raw = alt_ev.raw if alt_ev is ev_a else _remap_raw_node(alt_ev.raw, id_map)
            result.append(EventRecord(
                tag=primary_ev.tag,
                event_type=primary_ev.event_type,
                date=primary_ev.date,
                place=primary_ev.place,
                citations=primary_cits,
                raw=primary_raw,
            ))
            result.append(EventRecord(
                tag=alt_ev.tag,
                event_type='alternate',
                date=alt_ev.date,
                place=alt_ev.place,
                citations=alt_cits,
                raw=alt_raw,
            ))
            stats.date_conflicts_kept_both += 1
            continue

        # Case 3: normal merge (dates close or same)
        result.append(_merge_event(ev_a, ev_b, id_map, stats))

    # Append unmatched B events
    for i, ev_b in enumerate(events_b):
        if i not in used_b:
            result.append(EventRecord(
                tag=ev_b.tag,
                event_type=ev_b.event_type,
                date=ev_b.date,
                place=ev_b.place,
                citations=_remap_citations(ev_b.citations, id_map),
                raw=_remap_raw_node(ev_b.raw, id_map),
            ))
            stats.events_added_from_b += 1

    return result


# ---------------------------------------------------------------------------
# Name merging
# ---------------------------------------------------------------------------

def _merge_notes(notes_a: list[str], notes_b: list[str]) -> list[str]:
    """
    Union inline notes from A and B. Deduplicate by stripped text.
    Notes with different content are both kept.
    """
    seen: set[str] = {n.strip() for n in notes_a}
    result: list[str] = list(notes_a)
    for note in notes_b:
        if note.strip() not in seen:
            result.append(note)
            seen.add(note.strip())
    return result


def _merge_names(
    names_a: list[NameRecord],
    names_b: list[NameRecord],
    id_map: dict[str, str],
    stats: MergeStats,
) -> list[NameRecord]:
    """
    Union name records. A's primary stays primary.
    If B's primary differs from A's primary, add as AKA.
    """
    # Deduplicate names_a first — the source file may already have duplicates
    seen_a: set[tuple[str, str]] = set()
    deduped_a: list[NameRecord] = []
    for n in names_a:
        key = (n.given, n.surname)
        if key not in seen_a:
            deduped_a.append(n)
            seen_a.add(key)
    result: list[NameRecord] = deduped_a

    known: set[tuple[str, str]] = set(seen_a)

    for name_b in names_b:
        key = (name_b.given, name_b.surname)
        if key in known:
            continue
        # Add as AKA if not already there; remap source citations from B
        new_name = NameRecord(
            full=name_b.full,
            given=name_b.given,
            surname=name_b.surname,
            name_type=name_b.name_type or 'AKA',
            citations=_remap_citations(name_b.citations, id_map),
        )
        result.append(new_name)
        known.add(key)
        stats.aka_names_added += 1

    return result


# ---------------------------------------------------------------------------
# Individual merging
# ---------------------------------------------------------------------------

def _merge_individual(
    ind_a: Individual,
    ind_b: Individual,
    id_map: dict[str, str],
    stats: MergeStats,
    field_choices: list | None = None,
) -> Individual:
    """Merge ind_b into ind_a, returning a new Individual."""
    # Names
    merged_names = _merge_names(ind_a.names, ind_b.names, id_map, stats)

    # Sex
    sex = ind_a.sex
    if not sex and ind_b.sex:
        sex = ind_b.sex

    # Events
    merged_events = _merge_events(ind_a.events, ind_b.events, id_map, stats)

    # Family links: remap B's links then union
    famc = list(ind_a.family_child)
    for xref in ind_b.family_child:
        remapped = _remap(xref, id_map)
        if remapped and remapped not in famc:
            famc.append(remapped)

    fams = list(ind_a.family_spouse)
    for xref in ind_b.family_spouse:
        remapped = _remap(xref, id_map)
        if remapped and remapped not in fams:
            fams.append(remapped)

    # Citations
    merged_cits = _merge_citations(ind_a.citations, ind_b.citations, id_map, stats)

    # Media
    media = list(ind_a.media)
    for xref in ind_b.media:
        remapped = _remap(xref, id_map)
        if remapped and remapped not in media:
            media.append(remapped)

    # Notes: union inline text (deduplicated) and linked note xrefs
    merged_notes = _merge_notes(ind_a.notes, ind_b.notes)
    note_xrefs = list(ind_a.note_xrefs)
    for xref in ind_b.note_xrefs:
        remapped = _remap(xref, id_map)
        if remapped and remapped not in note_xrefs:
            note_xrefs.append(remapped)

    # Re-derive normalized fields from merged names/events
    normalized_surnames: set[str] = set()
    normalized_givens: set[str] = set()
    for name in merged_names:
        if name.surname:
            clean_surname = strip_parentheticals(name.surname)
            if clean_surname:
                normalized_surnames.add(clean_surname)
        for alt in extract_parenthetical_surnames(name.full):
            if alt:
                normalized_surnames.add(alt)
        if name.given:
            clean_given = strip_parentheticals(name.given)
            for part in clean_given.split():
                normalized_givens.add(part)

    birth_date: ParsedDate | None = None
    death_date: ParsedDate | None = None
    for ev in merged_events:
        if ev.tag == 'BIRT' and birth_date is None:
            birth_date = ev.date
        elif ev.tag == 'DEAT' and death_date is None:
            death_date = ev.date

    return Individual(
        xref=ind_a.xref,
        names=merged_names,
        sex=sex,
        events=merged_events,
        family_child=famc,
        family_spouse=fams,
        citations=merged_cits,
        media=media,
        notes=merged_notes,
        note_xrefs=note_xrefs,
        raw=ind_a.raw,
        normalized_surnames=normalized_surnames,
        normalized_givens=normalized_givens,
        birth_date=birth_date,
        death_date=death_date,
    )


# ---------------------------------------------------------------------------
# Family merging
# ---------------------------------------------------------------------------

def _merge_family(
    fam_a: Family,
    fam_b: Family,
    id_map: dict[str, str],
    stats: MergeStats,
) -> Family:
    """Merge fam_b into fam_a."""
    # Children: A order preserved, B appended
    children = list(fam_a.child_xrefs)
    for xref in fam_b.child_xrefs:
        remapped = _remap(xref, id_map)
        if remapped and remapped not in children:
            children.append(remapped)

    merged_events = _merge_events(fam_a.events, fam_b.events, id_map, stats)
    merged_cits = _merge_citations(fam_a.citations, fam_b.citations, id_map, stats)

    return Family(
        xref=fam_a.xref,
        husband_xref=fam_a.husband_xref or _remap(fam_b.husband_xref, id_map),
        wife_xref=fam_a.wife_xref or _remap(fam_b.wife_xref, id_map),
        child_xrefs=children,
        events=merged_events,
        citations=merged_cits,
        raw=fam_a.raw,
    )


# ---------------------------------------------------------------------------
# Source merging
# ---------------------------------------------------------------------------

def _merge_source(
    src_a: Source,
    src_b: Source,
    id_map: dict[str, str],
    stats: MergeStats,
) -> Source:
    """Merge src_b into src_a."""
    # Title: keep A's unless B is clearly more complete
    title = src_a.title
    if not title:
        title = src_b.title

    author = src_a.author or src_b.author
    publisher = src_a.publisher or src_b.publisher
    repository_xref = src_a.repository_xref
    if not repository_xref and src_b.repository_xref:
        repository_xref = _remap(src_b.repository_xref, id_map)

    # Notes: concatenate unique notes
    existing_notes = set(src_a.notes)
    notes = list(src_a.notes)
    for note in src_b.notes:
        if note not in existing_notes:
            notes.append(note)

    # REFN: keep both if different
    refn = src_a.refn
    if src_b.refn and src_b.refn != src_a.refn:
        refn = f"{src_a.refn or ''};{src_b.refn}".strip(';')

    return Source(
        xref=src_a.xref,
        title=title,
        author=author,
        publisher=publisher,
        repository_xref=repository_xref,
        notes=notes,
        refn=refn,
        raw=src_a.raw,
        title_tokens=src_a.title_tokens,
    )


# ---------------------------------------------------------------------------
# Main merge function
# ---------------------------------------------------------------------------

def merge_records(
    file_a: GedcomFile,
    file_b: GedcomFile,
    decisions: MergeDecisions,
) -> tuple[GedcomFile, MergeStats]:
    """
    Merge file_b into file_a using the decisions from interactive review.

    Returns (merged_file, stats).
    Never silently discards data — all unmatched B records marked 'add' are
    included; only explicitly 'skip' records are excluded.
    """
    stats = MergeStats()

    # Track manual vs auto
    stats.indi_matched_auto = 0  # caller fills from IndividualMatchResult
    stats.source_matched_auto = 0

    id_map = _build_id_map(file_a, file_b, decisions, stats)

    # --------------- Sources ---------------
    merged_sources: dict[str, Source] = {}

    for xref_a, src_a in file_a.sources.items():
        xref_b = next((b for b, a in decisions.source_map.items() if a == xref_a), None)
        if xref_b:
            src_b = file_b.sources[xref_b]
            merged_sources[xref_a] = _merge_source(src_a, src_b, id_map, stats)
        else:
            merged_sources[xref_a] = src_a

    # Add unmatched B sources — includes both explicitly reviewed 'add' sources
    # and auto-added sources (referenced by added individuals/families but never reviewed).
    for xref_b, src_b in file_b.sources.items():
        if xref_b not in decisions.source_map and xref_b in id_map:
            new_xref = id_map.get(xref_b)
            if new_xref:
                src_copy = Source(
                    xref=new_xref,
                    title=src_b.title,
                    author=src_b.author,
                    publisher=src_b.publisher,
                    repository_xref=_remap(src_b.repository_xref, id_map),
                    notes=list(src_b.notes),
                    refn=src_b.refn,
                    raw=src_b.raw,
                    title_tokens=src_b.title_tokens,
                )
                merged_sources[new_xref] = src_copy

    # --------------- Repositories ---------------
    merged_repos: dict[str, Repository] = dict(file_a.repositories)
    for xref_b, repo_b in file_b.repositories.items():
        new_xref = id_map.get(xref_b, xref_b)
        if new_xref not in merged_repos:
            merged_repos[new_xref] = Repository(
                xref=new_xref, name=repo_b.name, raw=repo_b.raw
            )

    # --------------- Media ---------------
    merged_media: dict[str, MediaObject] = dict(file_a.media)
    for xref_b, obj_b in file_b.media.items():
        new_xref = id_map.get(xref_b, xref_b)
        if new_xref not in merged_media:
            merged_media[new_xref] = MediaObject(
                xref=new_xref, file=obj_b.file, form=obj_b.form,
                title=obj_b.title, raw=obj_b.raw
            )

    # --------------- Notes ---------------
    merged_notes: dict[str, Note] = dict(file_a.notes)
    for xref_b, note_b in file_b.notes.items():
        new_xref = id_map.get(xref_b, xref_b)
        if new_xref not in merged_notes:
            from gedcom_merge.model import Note as _Note
            merged_notes[new_xref] = _Note(xref=new_xref, text=note_b.text, raw=note_b.raw)

    # --------------- Individuals ---------------
    merged_indis: dict[str, Individual] = {}

    for xref_a, ind_a in file_a.individuals.items():
        xref_b = next((b for b, a in decisions.indi_map.items() if a == xref_a), None)
        if xref_b:
            ind_b = file_b.individuals[xref_b]
            field_choices = decisions.field_choices.get(xref_b)
            merged_indis[xref_a] = _merge_individual(ind_a, ind_b, id_map, stats, field_choices)
        else:
            merged_indis[xref_a] = ind_a

    # Add unmatched B individuals.
    # Include any B individual that has a new ID in id_map — either because
    # the user explicitly chose 'add', or because it was auto-added as a
    # member of a B family that is being added.
    for xref_b, ind_b in file_b.individuals.items():
        if xref_b not in decisions.indi_map and xref_b in id_map:
            new_xref = id_map.get(xref_b)
            if new_xref:
                # Remap all xrefs
                famc = [_remap(x, id_map) or x for x in ind_b.family_child]
                fams = [_remap(x, id_map) or x for x in ind_b.family_spouse]
                cits = _remap_citations(ind_b.citations, id_map)
                evs = [
                    EventRecord(
                        tag=e.tag, event_type=e.event_type, date=e.date,
                        place=e.place,
                        citations=_remap_citations(e.citations, id_map),
                        raw=e.raw,
                    )
                    for e in ind_b.events
                ]
                # Remap name citations too
                remapped_names = [
                    NameRecord(
                        full=n.full, given=n.given, surname=n.surname,
                        name_type=n.name_type,
                        citations=_remap_citations(n.citations, id_map),
                    )
                    for n in ind_b.names
                ]
                merged_indis[new_xref] = Individual(
                    xref=new_xref,
                    names=remapped_names,
                    sex=ind_b.sex,
                    events=evs,
                    family_child=famc,
                    family_spouse=fams,
                    citations=cits,
                    media=[_remap(x, id_map) or x for x in ind_b.media],
                    raw=_remap_raw_node(ind_b.raw, id_map),
                    normalized_surnames=set(ind_b.normalized_surnames),
                    normalized_givens=set(ind_b.normalized_givens),
                    birth_date=ind_b.birth_date,
                    death_date=ind_b.death_date,
                )

    # --------------- Families ---------------
    merged_fams: dict[str, Family] = {}

    for xref_a, fam_a in file_a.families.items():
        xref_b = next((b for b, a in decisions.family_map.items() if a == xref_a), None)
        if xref_b:
            fam_b = file_b.families[xref_b]
            merged_fams[xref_a] = _merge_family(fam_a, fam_b, id_map, stats)
        else:
            merged_fams[xref_a] = fam_a

    # Build couple index from already-merged families so we can detect
    # when an unmatched B family maps to a couple that already exists in A.
    couple_to_merged_xref: dict[tuple[str, str], str] = {
        (fam.husband_xref or '', fam.wife_xref or ''): xref
        for xref, fam in merged_fams.items()
        if fam.husband_xref or fam.wife_xref
    }

    # Add unmatched B families
    for xref_b, fam_b in file_b.families.items():
        disp = decisions.family_disposition.get(xref_b, 'skip')
        if xref_b not in decisions.family_map and disp == 'add':
            husb_a = _remap(fam_b.husband_xref, id_map)
            wife_a = _remap(fam_b.wife_xref, id_map)
            couple_key = (husb_a or '', wife_a or '')

            # If both spouses were matched and their A-side couple already
            # exists in merged_fams, merge B's content into that family
            # instead of creating a duplicate shell.
            if couple_key != ('', '') and couple_key in couple_to_merged_xref:
                existing_xref = couple_to_merged_xref[couple_key]
                merged_fams[existing_xref] = _merge_family(
                    merged_fams[existing_xref], fam_b, id_map, stats
                )
                continue

            new_xref = id_map.get(xref_b)
            if new_xref:
                children = [_remap(x, id_map) or x for x in fam_b.child_xrefs]
                evs = [
                    EventRecord(
                        tag=e.tag, event_type=e.event_type, date=e.date,
                        place=e.place,
                        citations=_remap_citations(e.citations, id_map),
                        raw=_remap_raw_node(e.raw, id_map),
                    )
                    for e in fam_b.events
                ]
                new_fam = Family(
                    xref=new_xref,
                    husband_xref=husb_a,
                    wife_xref=wife_a,
                    child_xrefs=children,
                    events=evs,
                    citations=_remap_citations(fam_b.citations, id_map),
                    raw=_remap_raw_node(fam_b.raw, id_map),
                )
                merged_fams[new_xref] = new_fam
                couple_to_merged_xref[couple_key] = new_xref

    merged = GedcomFile(
        individuals=merged_indis,
        families=merged_fams,
        sources=merged_sources,
        repositories=merged_repos,
        media=merged_media,
        notes=merged_notes,
        submitter=file_a.submitter,
        header_raw=file_a.header_raw,
        path='',
    )
    return merged, stats


# ---------------------------------------------------------------------------
# Post-merge empty family shell removal
# ---------------------------------------------------------------------------

def deduplicate_duplicate_families(merged: GedcomFile) -> int:
    """
    Post-merge pass: collapse family pairs that share the same husband+wife.

    When two FAM records in the merged file have identical (husband_xref,
    wife_xref) couples, one is canonical (preferred) and the other is a
    duplicate.  The canonical family keeps the richer record — events,
    children, and citations from both are unioned — and all FAMS pointers
    on individual records are updated to the canonical xref.

    Preference order for canonical: non-MERGE xref over @F_MERGE_*@ xref;
    when both are the same type, the one with more content wins.

    Returns the number of duplicate families removed.
    """
    from collections import defaultdict

    # Group families by (husband_xref or '', wife_xref or '')
    couple_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for xref, fam in merged.families.items():
        key = (fam.husband_xref or '', fam.wife_xref or '')
        if key != ('', ''):
            couple_groups[key].append(xref)

    removed = 0
    remap: dict[str, str] = {}  # duplicate_xref → canonical_xref

    def _is_merge_fam(xref: str) -> bool:
        return '_MERGE_' in xref

    def _content_score(fam: Family) -> int:
        return len(fam.events) + len(fam.child_xrefs) + len(fam.citations)

    for key, xrefs in couple_groups.items():
        if len(xrefs) < 2:
            continue

        # Pick canonical: prefer non-MERGE xref; break ties by content richness
        def _rank(x: str) -> tuple[int, int]:
            return (1 if _is_merge_fam(x) else 0, -_content_score(merged.families[x]))

        canonical_xref = min(xrefs, key=_rank)
        duplicates = [x for x in xrefs if x != canonical_xref]

        canonical_fam = merged.families[canonical_xref]

        # Union events, children, citations from duplicates into canonical
        existing_event_keys = {(e.tag, e.event_type, e.date and e.date.year) for e in canonical_fam.events}
        existing_children = set(canonical_fam.child_xrefs)
        existing_cit_keys = {(c.source_xref, c.page or '') for c in canonical_fam.citations}

        for dup_xref in duplicates:
            dup = merged.families[dup_xref]
            for ev in dup.events:
                key_ev = (ev.tag, ev.event_type, ev.date and ev.date.year)
                if key_ev not in existing_event_keys:
                    canonical_fam.events.append(ev)
                    existing_event_keys.add(key_ev)
            for child in dup.child_xrefs:
                if child not in existing_children:
                    canonical_fam.child_xrefs.append(child)
                    existing_children.add(child)
            for cit in dup.citations:
                cit_key = (cit.source_xref, cit.page or '')
                if cit_key not in existing_cit_keys:
                    canonical_fam.citations.append(cit)
                    existing_cit_keys.add(cit_key)

            remap[dup_xref] = canonical_xref
            del merged.families[dup_xref]
            removed += 1

    if not remap:
        return 0

    # Rewrite FAMS and FAMC on individuals
    for indi in merged.individuals.values():
        seen_fams: set[str] = set()
        new_fams: list[str] = []
        for f in indi.family_spouse:
            canonical = f
            while canonical in remap:
                canonical = remap[canonical]
            if canonical not in seen_fams:
                new_fams.append(canonical)
                seen_fams.add(canonical)
        indi.family_spouse = new_fams

        seen_famc: set[str] = set()
        new_famc: list[str] = []
        for f in indi.family_child:
            canonical = f
            while canonical in remap:
                canonical = remap[canonical]
            if canonical not in seen_famc:
                new_famc.append(canonical)
                seen_famc.add(canonical)
        indi.family_child = new_famc

    return removed


def deduplicate_duplicate_names(merged: GedcomFile) -> int:
    """
    Post-merge pass: remove duplicate NAME entries within individual records.

    Two names are considered duplicates when they share the same normalized
    (given, surname) pair — matching the deduplication key used by
    _merge_names() at merge time.

    Returns the total number of duplicate NAME entries removed.
    """
    removed = 0
    for indi in merged.individuals.values():
        seen: set[tuple[str, str]] = set()
        deduped: list = []
        for nm in indi.names:
            key = (nm.given, nm.surname)
            if key not in seen:
                deduped.append(nm)
                seen.add(key)
            else:
                removed += 1
        indi.names = deduped
    return removed


def purge_dangling_xrefs(merged: GedcomFile) -> int:
    """
    Post-merge pass: remove cross-references that point to records that no
    longer exist in the merged file.

    Handles:
    - FAM CHIL → nonexistent INDI
    - FAM HUSB / WIFE → nonexistent INDI
    - INDI FAMS / FAMC → nonexistent FAM
    - INDI / FAM citations SOUR → nonexistent SOUR
    - INDI OBJE → nonexistent OBJE

    Returns the total number of dangling pointers removed.
    """
    removed = 0
    indi_xrefs = set(merged.individuals)
    fam_xrefs = set(merged.families)
    sour_xrefs = set(merged.sources)
    obje_xrefs = set(merged.media)

    for fam in merged.families.values():
        if fam.husband_xref and fam.husband_xref not in indi_xrefs:
            fam.husband_xref = None
            removed += 1
        if fam.wife_xref and fam.wife_xref not in indi_xrefs:
            fam.wife_xref = None
            removed += 1
        before = len(fam.child_xrefs)
        fam.child_xrefs = [c for c in fam.child_xrefs if c in indi_xrefs]
        removed += before - len(fam.child_xrefs)

    for indi in merged.individuals.values():
        before_fams = len(indi.family_spouse)
        indi.family_spouse = [f for f in indi.family_spouse if f in fam_xrefs]
        removed += before_fams - len(indi.family_spouse)

        before_famc = len(indi.family_child)
        indi.family_child = [f for f in indi.family_child if f in fam_xrefs]
        removed += before_famc - len(indi.family_child)

        before_obje = len(indi.media)
        indi.media = [o for o in indi.media if o in obje_xrefs]
        removed += before_obje - len(indi.media)

    return removed


def remove_empty_family_shells(merged: GedcomFile) -> int:
    """
    Post-merge pass: remove FAM records that carry no genealogical content.

    An "empty shell" is a family that has a spouse link (HUSB or WIFE) but
    no events, no children, and no citations.  These are created when File B
    contains a family record that was never matched to a File A family and
    has no content of its own — the merge faithfully copies the empty record,
    but the result adds no information to the tree.

    For each removed family the corresponding FAMS pointer is removed from
    both spouses' individual records so the merged file remains referentially
    consistent.

    Returns the number of family records removed.
    """
    empty_xrefs: set[str] = {
        xref
        for xref, fam in merged.families.items()
        if (fam.husband_xref or fam.wife_xref)
        and not fam.events
        and not fam.child_xrefs
        and not fam.citations
    }
    if not empty_xrefs:
        return 0

    for xref in empty_xrefs:
        del merged.families[xref]

    for indi in merged.individuals.values():
        indi.family_spouse = [f for f in indi.family_spouse if f not in empty_xrefs]

    return len(empty_xrefs)


# ---------------------------------------------------------------------------
# Post-merge source deduplication
# ---------------------------------------------------------------------------

def deduplicate_merged_sources(
    merged: GedcomFile,
    threshold: float = 0.85,
) -> int:
    """
    Post-merge pass: collapse source records that are semantically identical
    but were assigned different xrefs (e.g. the same Ancestry database cited
    in both input trees with slightly different title strings).

    Algorithm:
    1. Collect *co-cited* pairs — source xrefs that appear together on the
       same individual or family record.  This bounds the comparison space to
       cases where a duplicate actually inflates citations.
    2. Score each co-cited pair with match_sources._score_pair.
    3. Build a remap: redundant_xref → canonical_xref.  File-A xrefs
       (those NOT starting with ``@S_MERGE_``) are preferred as canonical.
    4. Rewrite every citation in-place; deduplicate citations that now share
       a source_xref; remove dead source records.

    Returns the number of source records removed.
    """
    from gedcom_merge.match_sources import _score_pair as _score_src_pair
    from dataclasses import replace as _dc_replace

    # ------------------------------------------------------------------ #
    # Step 1 – collect co-cited pairs                                     #
    # ------------------------------------------------------------------ #

    def _cit_xrefs(cits: list[CitationRecord]) -> list[str]:
        return [c.source_xref for c in cits if c.source_xref]

    def _record_xrefs(ind: Individual | None = None, fam: Family | None = None) -> list[str]:
        obj = ind or fam
        if obj is None:
            return []
        xrefs: list[str] = _cit_xrefs(obj.citations)
        for ev in obj.events:
            xrefs.extend(_cit_xrefs(ev.citations))
        if ind is not None:
            for nm in ind.names:
                xrefs.extend(_cit_xrefs(nm.citations))
        return xrefs

    co_cited: set[tuple[str, str]] = set()
    for ind in merged.individuals.values():
        seen = list(dict.fromkeys(_record_xrefs(ind=ind)))
        for i in range(len(seen)):
            for j in range(i + 1, len(seen)):
                a, b = seen[i], seen[j]
                co_cited.add((min(a, b), max(a, b)))
    for fam in merged.families.values():
        seen = list(dict.fromkeys(_record_xrefs(fam=fam)))
        for i in range(len(seen)):
            for j in range(i + 1, len(seen)):
                a, b = seen[i], seen[j]
                co_cited.add((min(a, b), max(a, b)))

    # ------------------------------------------------------------------ #
    # Step 2 – score pairs and build remap                                #
    # ------------------------------------------------------------------ #

    # Union-find: remap[x] → canonical for x
    remap: dict[str, str] = {}

    def _canonical(x: str) -> str:
        while x in remap:
            x = remap[x]
        return x

    def _is_file_b(xref: str) -> bool:
        return xref.startswith('@S_MERGE_')

    for xa, xb in co_cited:
        src_a = merged.sources.get(xa)
        src_b = merged.sources.get(xb)
        if not src_a or not src_b:
            continue
        if _score_src_pair(src_a, src_b) < threshold:
            continue
        ca, cb = _canonical(xa), _canonical(xb)
        if ca == cb:
            continue
        # Prefer File-A xref as canonical; if both same type, keep ca
        if _is_file_b(ca) and not _is_file_b(cb):
            remap[ca] = cb
        else:
            remap[cb] = ca

    # ------------------------------------------------------------------ #
    # Step 3 – rewrite citations in-place                                 #
    # ------------------------------------------------------------------ #

    def _remap_cit_list(cits: list[CitationRecord]) -> list[CitationRecord]:
        seen_keys: set[tuple[str, str]] = set()
        result: list[CitationRecord] = []
        for c in cits:
            new_xref = _canonical(c.source_xref) if c.source_xref else c.source_xref
            key = (new_xref, c.page or '')
            if key in seen_keys:
                continue
            seen_keys.add(key)
            if new_xref != c.source_xref:
                c = _dc_replace(c, source_xref=new_xref)
            result.append(c)
        return result

    for ind in merged.individuals.values():
        ind.citations = _remap_cit_list(ind.citations)
        for ev in ind.events:
            ev.citations = _remap_cit_list(ev.citations)
        for nm in ind.names:
            nm.citations = _remap_cit_list(nm.citations)

    for fam in merged.families.values():
        fam.citations = _remap_cit_list(fam.citations)
        for ev in fam.events:
            ev.citations = _remap_cit_list(ev.citations)

    # ------------------------------------------------------------------ #
    # Step 4 – remove dead source records                                 #
    # ------------------------------------------------------------------ #

    dead = set(remap.keys())
    for xref in dead:
        merged.sources.pop(xref, None)

    # ------------------------------------------------------------------ #
    # Step 5 – full title-based pass for sources that were never co-cited  #
    # ------------------------------------------------------------------ #
    # The co-cited pass above only compares sources appearing together on a
    # single record.  Duplicate sources that are cited on different
    # individuals but never together escape that pass.  Run a full O(n²)
    # comparison limited to remaining (non-dead) sources to catch them.

    live_sources = [(xref, src) for xref, src in merged.sources.items()
                    if xref not in dead]
    extra_remap: dict[str, str] = {}

    for i, (xa, src_a) in enumerate(live_sources):
        for xb, src_b in live_sources[i + 1:]:
            ca = _canonical(xa)  # may already be remapped from Step 2
            cb = _canonical(xb)
            if ca == cb:
                continue
            # Only compare File-B against File-A — not A vs A or B vs B.
            # Deduplicating two File-A sources risks removing a source that
            # was present in the primary tree with distinct data.
            one_is_b = _is_file_b(ca) != _is_file_b(cb)
            if not one_is_b:
                continue
            if _score_src_pair(src_a, src_b) < threshold:
                continue
            # Prefer File-A xref as canonical
            if _is_file_b(ca) and not _is_file_b(cb):
                extra_remap[ca] = cb
                remap[ca] = cb
            else:
                extra_remap[cb] = ca
                remap[cb] = ca

    if extra_remap:
        # Rewrite citations for newly identified duplicates
        for ind in merged.individuals.values():
            ind.citations = _remap_cit_list(ind.citations)
            for ev in ind.events:
                ev.citations = _remap_cit_list(ev.citations)
            for nm in ind.names:
                nm.citations = _remap_cit_list(nm.citations)
        for fam in merged.families.values():
            fam.citations = _remap_cit_list(fam.citations)
            for ev in fam.events:
                ev.citations = _remap_cit_list(ev.citations)

        extra_dead = set(extra_remap.keys())
        for xref in extra_dead:
            merged.sources.pop(xref, None)
        dead |= extra_dead

    return len(dead)
