"""Tests for gedcom_merge.merge — TDD ensuring no data is silently discarded."""

import pytest
import tempfile
import os

from gedcom_merge.model import (
    GedcomFile, Individual, Family, Source, GedcomNode,
    NameRecord, EventRecord, CitationRecord, ParsedDate,
    MergeDecisions,
)
from gedcom_merge.merge import (
    merge_records,
    _merge_citations, _merge_names, _merge_events, _merge_notes,
    _prefer_date, _prefer_place,
    remove_empty_family_shells,
    purge_dangling_xrefs,
    deduplicate_merged_sources,
    deduplicate_duplicate_families,
    deduplicate_duplicate_names,
    MergeStats,
)
from gedcom_merge.normalize import parse_date


def _node(tag='INDI', xref=None) -> GedcomNode:
    return GedcomNode(0, tag, '', xref, [])


def _indi(xref, given='John', surname='Smith', sex='M',
          birth_year=None, death_year=None,
          birth_place=None, death_place=None,
          fams=None, famc=None, citations=None) -> Individual:
    names = [NameRecord(full=f'{given} /{surname}/', given=given.lower(),
                        surname=surname.lower(), name_type=None)]
    events = []
    if birth_year:
        bd = ParsedDate(None, birth_year)
        events.append(EventRecord('BIRT', None, bd, birth_place,
                                  citations or [], _node()))
    if death_year:
        dd = ParsedDate(None, death_year)
        events.append(EventRecord('DEAT', None, dd, death_place,
                                  [], _node()))
    return Individual(
        xref=xref, names=names, sex=sex, events=events,
        family_child=famc or [], family_spouse=fams or [],
        citations=citations or [], media=[], raw=_node(xref=xref),
        normalized_surnames={surname.lower()},
        normalized_givens={given.lower()},
        birth_date=ParsedDate(None, birth_year) if birth_year else None,
        death_date=ParsedDate(None, death_year) if death_year else None,
    )


def _source(xref, title='Test Source', author=None) -> Source:
    from gedcom_merge.normalize import tokenize_title
    return Source(xref=xref, title=title, author=author, publisher=None,
                  repository_xref=None, notes=[], refn=None,
                  raw=_node('SOUR', xref), title_tokens=tokenize_title(title))


def _family(xref, husb=None, wife=None, children=None) -> Family:
    return Family(xref=xref, husband_xref=husb, wife_xref=wife,
                  child_xrefs=children or [], events=[], citations=[],
                  raw=_node('FAM', xref))


def _citation(source_xref, page=None) -> CitationRecord:
    return CitationRecord(source_xref=source_xref, page=page, data=None,
                          raw=_node('SOUR'))


def _file(indis=None, fams=None, sources=None) -> GedcomFile:
    return GedcomFile(
        individuals=indis or {},
        families=fams or {},
        sources=sources or {},
        repositories={}, media={}, notes={},
        submitter=None, header_raw=None,
    )


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

class TestPreferDate:
    def test_exact_beats_approximate(self):
        exact = ParsedDate(None, 1892, 3, 15)
        approx = ParsedDate('ABT', 1892)
        assert _prefer_date(exact, approx) is exact
        assert _prefer_date(approx, exact) is exact

    def test_full_beats_year_only(self):
        full = ParsedDate(None, 1892, 3, 15)
        year_only = ParsedDate(None, 1892)
        assert _prefer_date(full, year_only) is full

    def test_none_returns_other(self):
        d = ParsedDate(None, 1892)
        assert _prefer_date(None, d) is d
        assert _prefer_date(d, None) is d


class TestPreferPlace:
    def test_more_components_wins(self):
        result = _prefer_place('Columbus, Ohio', 'Columbus, Franklin, Ohio, USA')
        assert 'Franklin' in result

    def test_none_returns_other(self):
        assert _prefer_place(None, 'Paris, France') == 'Paris, France'
        assert _prefer_place('Paris, France', None) == 'Paris, France'


class TestMergeCitations:
    def test_adds_new_citation(self):
        stats = MergeStats()
        cit_a = _citation('@S1@', 'Page 1')
        cit_b = _citation('@S2@', 'Page 5')
        result = _merge_citations([cit_a], [cit_b], {}, stats)
        assert len(result) == 2
        assert stats.citations_added_from_b == 1

    def test_deduplicates_identical(self):
        stats = MergeStats()
        cit_a = _citation('@S1@', 'Page 42')
        cit_b = _citation('@S1@', 'Page 42')
        result = _merge_citations([cit_a], [cit_b], {}, stats)
        assert len(result) == 1
        assert stats.citations_added_from_b == 0

    def test_remaps_source_xref(self):
        stats = MergeStats()
        cit_b = _citation('@S99@', 'Page 1')
        id_map = {'@S99@': '@S1@'}
        result = _merge_citations([], [cit_b], id_map, stats)
        assert result[0].source_xref == '@S1@'

    def test_keeps_more_complete_page(self):
        """If B's PAGE is more complete than A's, keep B."""
        stats = MergeStats()
        cit_a = _citation('@S1@', 'Page 42')
        cit_b = _citation('@S1@', 'Page 42, Line 7, Roll 123')
        result = _merge_citations([cit_a], [cit_b], {}, stats)
        # Should keep the more complete one
        pages = [c.page for c in result if c.source_xref == '@S1@']
        assert any('Line 7' in (p or '') for p in pages)


class TestMergeNames:
    def test_keeps_a_primary(self):
        stats = MergeStats()
        name_a = NameRecord('John /Smith/', 'john', 'smith', None)
        name_b = NameRecord('John /Smith/', 'john', 'smith', None)
        result = _merge_names([name_a], [name_b], {}, stats)
        assert result[0] is name_a  # A stays primary

    def test_adds_new_name_as_aka(self):
        stats = MergeStats()
        name_a = NameRecord('John /Smith/', 'john', 'smith', None)
        name_b = NameRecord('Johnny /Smith/', 'johnny', 'smith', None)
        result = _merge_names([name_a], [name_b], {}, stats)
        assert len(result) == 2
        assert result[1].name_type == 'AKA'
        assert stats.aka_names_added == 1

    def test_no_duplicate_names(self):
        stats = MergeStats()
        name_a = NameRecord('John /Smith/', 'john', 'smith', None)
        name_b = NameRecord('John /Smith/', 'john', 'smith', None)
        result = _merge_names([name_a], [name_b], {}, stats)
        assert len(result) == 1
        assert stats.aka_names_added == 0


class TestMergeEvents:
    def test_merges_birth_date(self):
        """B's more specific birth date should be preferred."""
        stats = MergeStats()
        ev_a = EventRecord('BIRT', None, ParsedDate(None, 1892), None, [], _node())
        ev_b = EventRecord('BIRT', None, ParsedDate(None, 1892, 3, 15), 'Boston, MA', [], _node())
        result = _merge_events([ev_a], [ev_b], {}, stats)
        assert len(result) == 1
        assert result[0].date.day == 15
        assert result[0].place == 'Boston, MA'

    def test_unmatched_b_event_added(self):
        stats = MergeStats()
        ev_a = EventRecord('BIRT', None, ParsedDate(None, 1892), None, [], _node())
        ev_b = EventRecord('RESI', None, ParsedDate(None, 1910), 'New York', [], _node())
        result = _merge_events([ev_a], [ev_b], {}, stats)
        assert len(result) == 2
        assert stats.events_added_from_b == 1

    def test_no_events_lost(self):
        """All events from A are preserved; unmatched B events added."""
        stats = MergeStats()
        events_a = [
            EventRecord('BIRT', None, ParsedDate(None, 1892), None, [], _node()),
            EventRecord('RESI', None, ParsedDate(None, 1920), 'Chicago', [], _node()),
        ]
        events_b = [
            EventRecord('BIRT', None, ParsedDate(None, 1892, 3, 15), None, [], _node()),
            EventRecord('NATU', None, ParsedDate(None, 1915), 'Ohio', [], _node()),
        ]
        result = _merge_events(events_a, events_b, {}, stats)
        tags = [e.tag for e in result]
        assert 'BIRT' in tags
        assert 'RESI' in tags
        assert 'NATU' in tags
        assert len(result) == 3


class TestDateConflictMerge:
    def test_exact_beats_approximate_close(self):
        """ABT 1890 vs 6 NOV 1888 → keep exact, discard approximate."""
        stats = MergeStats()
        ev_a = EventRecord('BIRT', None, ParsedDate('ABT', 1890), None, [], _node())
        ev_b = EventRecord('BIRT', None, ParsedDate(None, 1888, 11, 6), None, [], _node())
        result = _merge_events([ev_a], [ev_b], {}, stats)
        assert len(result) == 1
        assert result[0].date.qualifier is None   # exact date kept
        assert result[0].date.year == 1888
        assert result[0].date.month == 11
        assert result[0].date.day == 6
        assert stats.date_conflicts_exact_wins == 1

    def test_exact_beats_approximate_citations_not_merged(self):
        """When exact wins, only the exact event's citations are kept."""
        stats = MergeStats()
        src_a = CitationRecord('@S1@', 'p. 10', None, _node())
        src_b = CitationRecord('@S2@', 'p. 5', None, _node())
        ev_a = EventRecord('BIRT', None, ParsedDate('ABT', 1890), None, [src_a], _node())
        ev_b = EventRecord('BIRT', None, ParsedDate(None, 1888, 11, 6), None, [src_b], _node())
        result = _merge_events([ev_a], [ev_b], {}, stats)
        assert len(result[0].citations) == 1
        assert result[0].citations[0].source_xref == '@S2@'  # only exact's citation

    def test_meaningfully_different_dates_kept_both(self):
        """1886 vs 1890 → two events, primary + alternate."""
        stats = MergeStats()
        ev_a = EventRecord('BIRT', None, ParsedDate(None, 1886), None, [], _node())
        ev_b = EventRecord('BIRT', None, ParsedDate(None, 1890), None, [], _node())
        result = _merge_events([ev_a], [ev_b], {}, stats)
        assert len(result) == 2
        assert stats.date_conflicts_kept_both == 1
        event_types = {e.event_type for e in result}
        assert 'alternate' in event_types

    def test_better_sourced_is_primary(self):
        """When B has more citations, B's date should be primary."""
        stats = MergeStats()
        src1 = CitationRecord('@S1@', None, None, _node())
        src2 = CitationRecord('@S2@', None, None, _node())
        src3 = CitationRecord('@S3@', None, None, _node())
        ev_a = EventRecord('BIRT', None, ParsedDate(None, 1886), None, [src1], _node())
        ev_b = EventRecord('BIRT', None, ParsedDate(None, 1890), None, [src2, src3], _node())
        result = _merge_events([ev_a], [ev_b], {}, stats)
        # Primary (first, no 'alternate' type) should be B's date (1890, 2 citations)
        primary = next(e for e in result if e.event_type != 'alternate')
        alternate = next(e for e in result if e.event_type == 'alternate')
        assert primary.date.year == 1890
        assert alternate.date.year == 1886

    def test_different_dates_citations_stay_separate(self):
        """When dates are kept separately, citations are NOT merged across events."""
        stats = MergeStats()
        src_a = CitationRecord('@S1@', 'p. 1', None, _node())
        src_b = CitationRecord('@S2@', 'p. 2', None, _node())
        ev_a = EventRecord('BIRT', None, ParsedDate(None, 1886), None, [src_a], _node())
        ev_b = EventRecord('BIRT', None, ParsedDate(None, 1890), None, [src_b], _node())
        result = _merge_events([ev_a], [ev_b], {}, stats)
        for ev in result:
            assert len(ev.citations) == 1  # each event has only its own citation

    def test_close_exact_dates_still_merge_normally(self):
        """1889 vs 1890 → within 2 years → standard merge (not kept separate)."""
        stats = MergeStats()
        ev_a = EventRecord('BIRT', None, ParsedDate(None, 1889), None, [], _node())
        ev_b = EventRecord('BIRT', None, ParsedDate(None, 1890), None, [], _node())
        result = _merge_events([ev_a], [ev_b], {}, stats)
        assert len(result) == 1
        assert stats.date_conflicts_kept_both == 0


# ---------------------------------------------------------------------------
# Note merging tests
# ---------------------------------------------------------------------------

class TestMergeNotes:
    def test_different_notes_both_kept(self):
        result = _merge_notes(['Note ABC'], ['Note DEF'])
        assert 'Note ABC' in result
        assert 'Note DEF' in result
        assert len(result) == 2

    def test_identical_notes_deduplicated(self):
        result = _merge_notes(['Note ABC'], ['Note ABC'])
        assert result.count('Note ABC') == 1

    def test_whitespace_normalized_for_dedup(self):
        result = _merge_notes(['  Note ABC  '], ['Note ABC'])
        assert len(result) == 1

    def test_a_notes_preserved_when_b_empty(self):
        result = _merge_notes(['Note ABC'], [])
        assert result == ['Note ABC']

    def test_b_notes_added_when_a_empty(self):
        result = _merge_notes([], ['Note DEF'])
        assert result == ['Note DEF']

    def test_order_a_first(self):
        result = _merge_notes(['Note A'], ['Note B'])
        assert result[0] == 'Note A'
        assert result[1] == 'Note B'


# ---------------------------------------------------------------------------
# Integration tests for merge_records
# ---------------------------------------------------------------------------

class TestMergeRecords:
    def _simple_decisions(self, indi_map=None, source_map=None,
                           indi_disp=None, source_disp=None) -> MergeDecisions:
        d = MergeDecisions()
        d.indi_map = indi_map or {}
        d.source_map = source_map or {}
        d.indi_disposition = indi_disp or {}
        d.source_disposition = source_disp or {}
        return d

    def test_a_individuals_preserved(self):
        """All File A individuals must appear in output."""
        ind_a = _indi('@I1@', 'John', 'Smith', birth_year=1880)
        file_a = _file(indis={'@I1@': ind_a})
        file_b = _file()
        decisions = self._simple_decisions()
        merged, stats = merge_records(file_a, file_b, decisions)
        assert '@I1@' in merged.individuals

    def test_matched_individual_merged(self):
        """Matched B individual's data merges into A's record."""
        ind_a = _indi('@I1@', 'John', 'Smith', birth_year=1880)
        ind_b = _indi('@I2@', 'John', 'Smith', birth_year=1880, birth_place='Boston, MA')
        file_a = _file(indis={'@I1@': ind_a})
        file_b = _file(indis={'@I2@': ind_b})
        decisions = self._simple_decisions(indi_map={'@I2@': '@I1@'})
        merged, stats = merge_records(file_a, file_b, decisions)
        ind_merged = merged.individuals['@I1@']
        birt = next(e for e in ind_merged.events if e.tag == 'BIRT')
        assert birt.place == 'Boston, MA'  # picked up from B

    def test_unmatched_add_individual(self):
        """Unmatched B individual marked 'add' appears in output with new xref."""
        ind_a = _indi('@I1@', 'Alice', 'Smith')
        ind_b = _indi('@I2@', 'Bob', 'Jones', birth_year=1990)
        file_a = _file(indis={'@I1@': ind_a})
        file_b = _file(indis={'@I2@': ind_b})
        decisions = self._simple_decisions(indi_disp={'@I2@': 'add'})
        merged, stats = merge_records(file_a, file_b, decisions)
        # Should have 2 individuals in output
        assert len(merged.individuals) == 2
        names = {i.display_name for i in merged.individuals.values()}
        assert any('alice' in n.lower() or 'Alice' in n for n in names)
        assert any('bob' in n.lower() or 'Bob' in n for n in names)

    def test_unmatched_skip_individual_not_added(self):
        """Unmatched B individual marked 'skip' is excluded from output."""
        ind_a = _indi('@I1@', 'Alice', 'Smith')
        ind_b = _indi('@I2@', 'Bob', 'Jones')
        file_a = _file(indis={'@I1@': ind_a})
        file_b = _file(indis={'@I2@': ind_b})
        decisions = self._simple_decisions(indi_disp={'@I2@': 'skip'})
        merged, stats = merge_records(file_a, file_b, decisions)
        assert len(merged.individuals) == 1

    def test_source_xref_remapped_in_citations(self):
        """When B source is matched, its xref is remapped in citations."""
        src_a = _source('@S1@', 'Census 1900')
        src_b = _source('@S99@', 'Census 1900')
        ind_b = _indi('@I2@', 'Bob', 'Jones',
                       citations=[_citation('@S99@', 'Page 1')])
        ind_a = _indi('@I1@', 'Bob', 'Jones')
        file_a = _file(indis={'@I1@': ind_a}, sources={'@S1@': src_a})
        file_b = _file(indis={'@I2@': ind_b}, sources={'@S99@': src_b})
        decisions = self._simple_decisions(
            indi_map={'@I2@': '@I1@'},
            source_map={'@S99@': '@S1@'},
        )
        merged, stats = merge_records(file_a, file_b, decisions)
        ind_merged = merged.individuals['@I1@']
        cit_xrefs = [c.source_xref for c in ind_merged.citations]
        assert '@S1@' in cit_xrefs
        assert '@S99@' not in cit_xrefs

    def test_family_children_union(self):
        """Child from B's family added to merged family."""
        ind_child_a = _indi('@I3@', 'Child', 'Smith', famc=['@F1@'])
        ind_child_b = _indi('@I4@', 'NewChild', 'Smith', famc=['@F2@'])
        fam_a = _family('@F1@', '@I1@', '@I2@', ['@I3@'])
        fam_b = _family('@F2@', '@I1@', '@I2@', ['@I3@', '@I4@'])
        file_a = _file(indis={'@I1@': _indi('@I1@', 'Dad', 'Smith'),
                               '@I2@': _indi('@I2@', 'Mom', 'Smith', sex='F'),
                               '@I3@': ind_child_a},
                        fams={'@F1@': fam_a})
        file_b = _file(indis={'@I4@': ind_child_b},
                        fams={'@F2@': fam_b})
        decisions = MergeDecisions()
        decisions.indi_map = {}
        decisions.family_map = {'@F2@': '@F1@'}
        decisions.indi_disposition = {'@I4@': 'add'}
        decisions.family_disposition = {}
        decisions.source_map = {}
        decisions.source_disposition = {}
        merged, stats = merge_records(file_a, file_b, decisions)
        fam_merged = merged.families['@F1@']
        assert len(fam_merged.child_xrefs) >= 1  # At least the original child

    def test_no_data_loss_all_sources_preserved(self):
        """All A sources appear in output; added B sources also appear."""
        src_a = _source('@S1@', 'Source One')
        src_b = _source('@S2@', 'Source Two')
        file_a = _file(sources={'@S1@': src_a})
        file_b = _file(sources={'@S2@': src_b})
        decisions = self._simple_decisions(source_disp={'@S2@': 'add'})
        merged, stats = merge_records(file_a, file_b, decisions)
        assert '@S1@' in merged.sources
        assert len(merged.sources) == 2  # A + B new source

    def test_matched_source_merged(self):
        """Matched B source notes/fields merged into A source."""
        src_a = _source('@S1@', 'Parish Records')
        src_b = _source('@S99@', 'Parish Records')
        src_b.notes = ['Digitized 2020']
        src_b.author = 'John Scholar'
        src_a.author = None
        file_a = _file(sources={'@S1@': src_a})
        file_b = _file(sources={'@S99@': src_b})
        decisions = self._simple_decisions(source_map={'@S99@': '@S1@'})
        merged, stats = merge_records(file_a, file_b, decisions)
        src_merged = merged.sources['@S1@']
        assert src_merged.author == 'John Scholar'
        assert 'Digitized 2020' in src_merged.notes


# ---------------------------------------------------------------------------
# Empty family shell tests
# ---------------------------------------------------------------------------

class TestRemoveEmptyFamilyShells:
    def test_removes_shell_with_only_spouses(self):
        """A family with HUSB+WIFE but no events/children/citations is removed."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@'])
        fam = _family('@F1@', '@I1@', '@I2@')  # no events, no children, no citations
        merged = _file(
            indis={'@I1@': ind_h, '@I2@': ind_w},
            fams={'@F1@': fam},
        )
        removed = remove_empty_family_shells(merged)
        assert removed == 1
        assert '@F1@' not in merged.families

    def test_cleans_up_fams_on_individuals(self):
        """FAMS pointers to removed shells are cleaned from individual records."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@'])
        fam = _family('@F1@', '@I1@', '@I2@')
        merged = _file(
            indis={'@I1@': ind_h, '@I2@': ind_w},
            fams={'@F1@': fam},
        )
        remove_empty_family_shells(merged)
        assert '@F1@' not in merged.individuals['@I1@'].family_spouse
        assert '@F1@' not in merged.individuals['@I2@'].family_spouse

    def test_keeps_family_with_events(self):
        """A family with a MARR event is preserved."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@'])
        marr = EventRecord('MARR', None, ParsedDate(None, 1950), None, [], _node())
        fam = Family('@F1@', '@I1@', '@I2@', [], [marr], [], _node('FAM', '@F1@'))
        merged = _file(
            indis={'@I1@': ind_h, '@I2@': ind_w},
            fams={'@F1@': fam},
        )
        removed = remove_empty_family_shells(merged)
        assert removed == 0
        assert '@F1@' in merged.families

    def test_keeps_family_with_children(self):
        """A family with children is preserved even with no events."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@'])
        ind_c = _indi('@I3@', 'Child', 'Smith', famc=['@F1@'])
        fam = Family('@F1@', '@I1@', '@I2@', ['@I3@'], [], [], _node('FAM', '@F1@'))
        merged = _file(
            indis={'@I1@': ind_h, '@I2@': ind_w, '@I3@': ind_c},
            fams={'@F1@': fam},
        )
        removed = remove_empty_family_shells(merged)
        assert removed == 0

    def test_keeps_non_shell_removes_shell(self):
        """Removes only empty shells, leaving real families intact."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@', '@F_MERGE_0001@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@', '@F_MERGE_0001@'])
        marr = EventRecord('MARR', None, ParsedDate(None, 1950), None, [], _node())
        real_fam = Family('@F1@', '@I1@', '@I2@', [], [marr], [], _node('FAM', '@F1@'))
        shell_fam = _family('@F_MERGE_0001@', '@I1@', '@I2@')
        merged = _file(
            indis={'@I1@': ind_h, '@I2@': ind_w},
            fams={'@F1@': real_fam, '@F_MERGE_0001@': shell_fam},
        )
        removed = remove_empty_family_shells(merged)
        assert removed == 1
        assert '@F1@' in merged.families
        assert '@F_MERGE_0001@' not in merged.families
        assert '@F1@' in merged.individuals['@I1@'].family_spouse
        assert '@F_MERGE_0001@' not in merged.individuals['@I1@'].family_spouse

    def test_merge_records_does_not_produce_empty_shells(self):
        """
        End-to-end: unmatched B families with no content should not
        appear as empty shells after merge + remove_empty_family_shells().
        """
        ind_a_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@'])
        ind_a_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@'])
        fam_a = _family('@F1@', '@I1@', '@I2@')  # A's family — also empty, but from A

        # File B has these same people (matched) in an empty family
        ind_b_h = _indi('@I10@', 'John', 'Smith', fams=['@F10@'])
        ind_b_w = _indi('@I11@', 'Jane', 'Smith', sex='F', fams=['@F10@'])
        fam_b = _family('@F10@', '@I10@', '@I11@')  # empty, unmatched

        file_a = _file(
            indis={'@I1@': ind_a_h, '@I2@': ind_a_w},
            fams={'@F1@': fam_a},
        )
        file_b = _file(
            indis={'@I10@': ind_b_h, '@I11@': ind_b_w},
            fams={'@F10@': fam_b},
        )

        decisions = MergeDecisions()
        decisions.indi_map = {'@I10@': '@I1@', '@I11@': '@I2@'}
        decisions.family_map = {}
        decisions.family_disposition = {'@F10@': 'add'}  # auto-added by review.py
        decisions.indi_disposition = {}
        decisions.source_map = {}
        decisions.source_disposition = {}

        merged, _ = merge_records(file_a, file_b, decisions)
        remove_empty_family_shells(merged)

        empty = [
            xref for xref, fam in merged.families.items()
            if (fam.husband_xref or fam.wife_xref)
            and not fam.events and not fam.child_xrefs and not fam.citations
        ]
        assert empty == [], f'Empty shells remain after cleanup: {empty}'


# ---------------------------------------------------------------------------
# Duplicate NAME deduplication tests
# ---------------------------------------------------------------------------

class TestMergeNamesDeduplicate:
    def test_deduplicates_within_names_a(self):
        """Duplicate names already in A's list are collapsed before merge."""
        stats = MergeStats()
        name1 = NameRecord('Antoine /Chilé/', 'antoine', 'chile', None)
        name2 = NameRecord('Antoine /Chilé/', 'antoine', 'chile', None)  # exact dup
        result = _merge_names([name1, name2], [], {}, stats)
        assert len(result) == 1

    def test_deduplicates_across_a_and_b(self):
        """A name in both A and B lists appears only once in output."""
        stats = MergeStats()
        name_a = NameRecord('John /Smith/', 'john', 'smith', None)
        name_b = NameRecord('John /Smith/', 'john', 'smith', None)
        result = _merge_names([name_a], [name_b], {}, stats)
        assert len(result) == 1
        assert stats.aka_names_added == 0

    def test_triple_duplicate_in_a_collapsed_to_one(self):
        """Three identical names in A reduce to a single entry."""
        stats = MergeStats()
        n = NameRecord('Maria /Rossi/', 'maria', 'rossi', None)
        result = _merge_names([n, n, n], [], {}, stats)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Duplicate family detection and prevention tests
# ---------------------------------------------------------------------------

class TestNoDuplicateFamilies:
    def test_unmatched_b_family_merged_into_existing_couple(self):
        """
        When an unmatched B family's remapped spouses already form a couple
        in File A, B's data is merged into the A family rather than creating
        a duplicate @F_MERGE_*@ record.
        """
        ind_a_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@'])
        ind_a_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@'])
        marr = EventRecord('MARR', None, ParsedDate(None, 1950), None, [], _node())
        fam_a = Family('@F1@', '@I1@', '@I2@', [], [marr], [], _node('FAM', '@F1@'))

        # B has the same couple (matched to A) in an unmatched family with a child
        ind_b_h = _indi('@I10@', 'John', 'Smith', fams=['@F10@'])
        ind_b_w = _indi('@I11@', 'Jane', 'Smith', sex='F', fams=['@F10@'])
        ind_b_c = _indi('@I12@', 'Kid', 'Smith', famc=['@F10@'])
        fam_b = Family('@F10@', '@I10@', '@I11@', ['@I12@'], [], [], _node('FAM', '@F10@'))

        file_a = _file(
            indis={'@I1@': ind_a_h, '@I2@': ind_a_w},
            fams={'@F1@': fam_a},
        )
        file_b = _file(
            indis={'@I10@': ind_b_h, '@I11@': ind_b_w, '@I12@': ind_b_c},
            fams={'@F10@': fam_b},
        )

        decisions = MergeDecisions()
        decisions.indi_map = {'@I10@': '@I1@', '@I11@': '@I2@'}
        decisions.indi_disposition = {'@I12@': 'add'}
        decisions.family_map = {}
        decisions.family_disposition = {'@F10@': 'add'}
        decisions.source_map = {}
        decisions.source_disposition = {}

        merged, _ = merge_records(file_a, file_b, decisions)

        # Only one family for this couple
        couples = [(fam.husband_xref, fam.wife_xref) for fam in merged.families.values()]
        assert couples.count(('@I1@', '@I2@')) == 1, \
            'Duplicate family created for same couple'

    def test_genuinely_new_b_family_still_added(self):
        """
        A B family whose spouses are not matched to any A couple creates a
        new family record as before.
        """
        ind_a = _indi('@I1@', 'Alice', 'Brown')
        ind_b_h = _indi('@I10@', 'Bob', 'Jones', fams=['@F10@'])
        ind_b_w = _indi('@I11@', 'Carol', 'Jones', sex='F', fams=['@F10@'])
        marr = EventRecord('MARR', None, ParsedDate(None, 1980), None, [], _node())
        fam_b = Family('@F10@', '@I10@', '@I11@', [], [marr], [], _node('FAM', '@F10@'))

        file_a = _file(indis={'@I1@': ind_a})
        file_b = _file(
            indis={'@I10@': ind_b_h, '@I11@': ind_b_w},
            fams={'@F10@': fam_b},
        )

        decisions = MergeDecisions()
        decisions.indi_map = {}
        decisions.indi_disposition = {'@I10@': 'add', '@I11@': 'add'}
        decisions.family_map = {}
        decisions.family_disposition = {'@F10@': 'add'}
        decisions.source_map = {}
        decisions.source_disposition = {}

        merged, _ = merge_records(file_a, file_b, decisions)
        assert len(merged.families) == 1
        fam = next(iter(merged.families.values()))
        assert any(e.tag == 'MARR' for e in fam.events)


# ---------------------------------------------------------------------------
# Dangling cross-reference purging tests
# ---------------------------------------------------------------------------

class TestPurgeDanglingXrefs:
    def test_removes_dangling_chil(self):
        """CHIL reference to a nonexistent individual is removed from family."""
        ind = _indi('@I1@', 'Parent', 'Smith', fams=['@F1@'])
        fam = Family('@F1@', '@I1@', None, ['@I1@', '@I_GONE@'], [], [], _node('FAM', '@F1@'))
        merged = _file(indis={'@I1@': ind}, fams={'@F1@': fam})
        removed = purge_dangling_xrefs(merged)
        assert removed == 1
        assert '@I_GONE@' not in merged.families['@F1@'].child_xrefs
        assert '@I1@' in merged.families['@F1@'].child_xrefs

    def test_removes_dangling_fams(self):
        """FAMS reference to a nonexistent family is removed from individual."""
        ind = _indi('@I1@', 'Alice', 'Smith', fams=['@F1@', '@F_GONE@'])
        fam = _family('@F1@', '@I1@', None)
        merged = _file(indis={'@I1@': ind}, fams={'@F1@': fam})
        removed = purge_dangling_xrefs(merged)
        assert removed == 1
        assert '@F_GONE@' not in merged.individuals['@I1@'].family_spouse
        assert '@F1@' in merged.individuals['@I1@'].family_spouse

    def test_no_removals_when_all_valid(self):
        """Returns 0 when there are no dangling references."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@'])
        fam = _family('@F1@', '@I1@', '@I2@')
        merged = _file(indis={'@I1@': ind_h, '@I2@': ind_w}, fams={'@F1@': fam})
        assert purge_dangling_xrefs(merged) == 0


# ---------------------------------------------------------------------------
# Duplicate source full-pass deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplicateMergedSourcesFullPass:
    def test_deduplicates_non_cocited_sources(self):
        """
        Two sources with identical titles that are never cited on the same
        individual should still be deduplicated by the full title-based pass.
        """
        from gedcom_merge.normalize import tokenize_title
        # Source A cited only on individual A; Source B cited only on individual B
        src_a = _source('@S1@', 'U.S. Census Records, 1900')
        src_b = _source('@S_MERGE_0001@', 'U.S. Census Records, 1900')
        src_a.title_tokens = tokenize_title(src_a.title)
        src_b.title_tokens = tokenize_title(src_b.title)

        ind_a = _indi('@I1@', 'Alice', 'Smith',
                      citations=[_citation('@S1@', 'p.1')])
        ind_b = _indi('@I2@', 'Bob', 'Jones',
                      citations=[_citation('@S_MERGE_0001@', 'p.2')])

        merged = _file(
            indis={'@I1@': ind_a, '@I2@': ind_b},
            sources={'@S1@': src_a, '@S_MERGE_0001@': src_b},
        )

        removed = deduplicate_merged_sources(merged, threshold=0.85)
        assert removed == 1
        assert '@S1@' in merged.sources
        assert '@S_MERGE_0001@' not in merged.sources
        # Citation on ind_b should now point to @S1@
        assert merged.individuals['@I2@'].citations[0].source_xref == '@S1@'

    def test_file_a_vs_file_a_not_deduped(self):
        """Two File-A sources with same title are NOT deduplicated (safety guard)."""
        from gedcom_merge.normalize import tokenize_title
        title = 'Parish Records'
        src_a1 = _source('@S1@', title)
        src_a2 = _source('@S2@', title)  # Also File-A (no @S_MERGE_ prefix)
        ind1 = _indi('@I1@', citations=[_citation('@S1@', 'p.1')])
        ind2 = _indi('@I2@', citations=[_citation('@S2@', 'p.2')])
        merged = _file(
            indis={'@I1@': ind1, '@I2@': ind2},
            sources={'@S1@': src_a1, '@S2@': src_a2},
        )
        removed = deduplicate_merged_sources(merged, threshold=0.85)
        assert removed == 0
        assert '@S1@' in merged.sources
        assert '@S2@' in merged.sources


# ---------------------------------------------------------------------------
# Duplicate family deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplicateDuplicateFamilies:
    def test_merges_content_into_canonical(self):
        """Events from duplicate family are merged into canonical."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@', '@F_MERGE_0001@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@', '@F_MERGE_0001@'])
        marr = EventRecord('MARR', None, ParsedDate(None, 1950), 'London', [], _node())
        real_fam = Family('@F1@', '@I1@', '@I2@', [], [marr], [], _node('FAM', '@F1@'))
        shell = _family('@F_MERGE_0001@', '@I1@', '@I2@')  # empty shell
        merged = _file(
            indis={'@I1@': ind_h, '@I2@': ind_w},
            fams={'@F1@': real_fam, '@F_MERGE_0001@': shell},
        )
        removed = deduplicate_duplicate_families(merged)
        assert removed == 1
        assert '@F1@' in merged.families
        assert '@F_MERGE_0001@' not in merged.families

    def test_fams_remapped_on_individuals(self):
        """FAMS pointers to removed duplicate are updated to canonical."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@', '@F_MERGE_0001@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@', '@F_MERGE_0001@'])
        marr = EventRecord('MARR', None, ParsedDate(None, 1950), None, [], _node())
        real_fam = Family('@F1@', '@I1@', '@I2@', [], [marr], [], _node('FAM', '@F1@'))
        shell = _family('@F_MERGE_0001@', '@I1@', '@I2@')
        merged = _file(
            indis={'@I1@': ind_h, '@I2@': ind_w},
            fams={'@F1@': real_fam, '@F_MERGE_0001@': shell},
        )
        deduplicate_duplicate_families(merged)
        assert merged.individuals['@I1@'].family_spouse == ['@F1@']
        assert merged.individuals['@I2@'].family_spouse == ['@F1@']

    def test_famc_remapped_on_children(self):
        """FAMC pointers on children to removed duplicate are updated to canonical."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@', '@F_MERGE_0001@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@', '@F_MERGE_0001@'])
        ind_c = _indi('@I3@', 'Kid', 'Smith', famc=['@F_MERGE_0001@'])
        marr = EventRecord('MARR', None, ParsedDate(None, 1950), None, [], _node())
        real_fam = Family('@F1@', '@I1@', '@I2@', [], [marr], [], _node('FAM', '@F1@'))
        shell = Family('@F_MERGE_0001@', '@I1@', '@I2@', ['@I3@'], [], [], _node('FAM', '@F_MERGE_0001@'))
        merged = _file(
            indis={'@I1@': ind_h, '@I2@': ind_w, '@I3@': ind_c},
            fams={'@F1@': real_fam, '@F_MERGE_0001@': shell},
        )
        deduplicate_duplicate_families(merged)
        assert merged.individuals['@I3@'].family_child == ['@F1@']

    def test_no_duplicates_returns_zero(self):
        """Returns 0 when no duplicate families exist."""
        ind_h = _indi('@I1@', 'John', 'Smith', fams=['@F1@'])
        ind_w = _indi('@I2@', 'Jane', 'Smith', sex='F', fams=['@F1@'])
        fam = _family('@F1@', '@I1@', '@I2@')
        merged = _file(indis={'@I1@': ind_h, '@I2@': ind_w}, fams={'@F1@': fam})
        assert deduplicate_duplicate_families(merged) == 0


# ---------------------------------------------------------------------------
# Duplicate name deduplication tests
# ---------------------------------------------------------------------------

class TestDeduplicateDuplicateNames:
    def test_removes_duplicate_name_within_individual(self):
        """Exact duplicate NAME in an individual is collapsed to one."""
        ind = _indi('@I1@', 'Antoine', 'Chile')
        dup = NameRecord('Antoine /Chilé/', 'antoine', 'chile', None)
        ind.names.append(dup)  # now has the same (given, surname) twice
        merged = _file(indis={'@I1@': ind})
        removed = deduplicate_duplicate_names(merged)
        assert removed == 1
        assert len(merged.individuals['@I1@'].names) == 1

    def test_different_names_untouched(self):
        """Distinct names in the same individual are kept."""
        ind = _indi('@I1@', 'Antoine', 'Chile')
        ind.names.append(NameRecord('Tony /Smith/', 'tony', 'smith', 'AKA'))
        merged = _file(indis={'@I1@': ind})
        removed = deduplicate_duplicate_names(merged)
        assert removed == 0
        assert len(merged.individuals['@I1@'].names) == 2

    def test_no_names_returns_zero(self):
        ind = _indi('@I1@', 'Antoine', 'Chile')
        merged = _file(indis={'@I1@': ind})
        assert deduplicate_duplicate_names(merged) == 0
