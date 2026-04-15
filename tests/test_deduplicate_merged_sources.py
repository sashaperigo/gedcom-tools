"""Tests for deduplicate_merged_sources() in gedcom_merge.merge."""

from gedcom_merge.model import (
    GedcomFile, Individual, Family, Source,
    CitationRecord, NameRecord, EventRecord, GedcomNode,
)
from gedcom_merge.merge import deduplicate_merged_sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NULL_NODE = GedcomNode(level=0, tag='', value='', xref=None)


def _make_src(xref: str, title: str, author: str = 'Ancestry.com') -> Source:
    tokens = set(title.lower().replace(',', '').replace('.', '').split())
    return Source(
        xref=xref,
        title=title,
        author=author,
        publisher='Ancestry.com Operations Inc',
        repository_xref=None,
        notes=[],
        refn=None,
        raw=_NULL_NODE,
        title_tokens=tokens,
    )


def _make_cit(source_xref: str, page: str | None = None) -> CitationRecord:
    return CitationRecord(
        source_xref=source_xref,
        page=page,
        data=None,
        raw=_NULL_NODE,
    )


def _make_indi(xref: str, citations: list[CitationRecord]) -> Individual:
    return Individual(
        xref=xref,
        names=[NameRecord(full='Test /Person/', given='test', surname='person',
                          name_type=None)],
        sex='M',
        events=[],
        family_child=[],
        family_spouse=[],
        citations=citations,
        media=[],
        raw=_NULL_NODE,
    )


def _make_fam(xref: str, citations: list[CitationRecord]) -> Family:
    return Family(
        xref=xref,
        husband_xref=None,
        wife_xref=None,
        child_xrefs=[],
        events=[],
        citations=citations,
        raw=_NULL_NODE,
    )


def _make_file(
    individuals: dict | None = None,
    families: dict | None = None,
    sources: dict | None = None,
) -> GedcomFile:
    return GedcomFile(
        individuals=individuals or {},
        families=families or {},
        sources=sources or {},
        repositories={},
        media={},
        notes={},
        submitter=None,
        header_raw=None,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNoCocitedPairs:
    """No individuals cite more than one source — nothing to deduplicate."""

    def test_single_source_per_record(self):
        src = _make_src('@S1@', 'U.S. Census, 1900')
        ind = _make_indi('@I1@', [_make_cit('@S1@')])
        merged = _make_file(individuals={'@I1@': ind}, sources={'@S1@': src})
        removed = deduplicate_merged_sources(merged)
        assert removed == 0
        assert '@S1@' in merged.sources

    def test_empty_file(self):
        merged = _make_file()
        assert deduplicate_merged_sources(merged) == 0


class TestIdenticalSourcesMerged:
    """Two sources with the same title on the same record → merged to one."""

    def test_exact_title_match_removes_redundant(self):
        title = 'U.S. Census, 1880'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_001@', title)
        ind = _make_indi('@I1@', [_make_cit('@S1@'), _make_cit('@S_MERGE_001@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_001@': src_b},
        )
        removed = deduplicate_merged_sources(merged)
        assert removed == 1
        assert '@S_MERGE_001@' not in merged.sources
        assert '@S1@' in merged.sources

    def test_canonical_xref_kept_in_citations(self):
        title = 'U.S. Census, 1880'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_001@', title)
        ind = _make_indi('@I1@', [_make_cit('@S1@'), _make_cit('@S_MERGE_001@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_001@': src_b},
        )
        deduplicate_merged_sources(merged)
        xrefs = [c.source_xref for c in merged.individuals['@I1@'].citations]
        assert '@S1@' in xrefs
        assert '@S_MERGE_001@' not in xrefs

    def test_duplicate_citation_removed_after_remap(self):
        """After remapping, two citations to the same source on one record → deduped to one."""
        title = 'U.S. Census, 1880'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_001@', title)
        ind = _make_indi('@I1@', [_make_cit('@S1@'), _make_cit('@S_MERGE_001@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_001@': src_b},
        )
        deduplicate_merged_sources(merged)
        assert len(merged.individuals['@I1@'].citations) == 1


class TestFileBXrefPreference:
    """File-B xrefs (@S_MERGE_*) are remapped to File-A xrefs, not the reverse."""

    def test_file_b_xref_becomes_redundant(self):
        title = 'England, Select Births'
        src_a = _make_src('@S100@', title)
        src_b = _make_src('@S_MERGE_002@', title)
        ind = _make_indi('@I1@', [_make_cit('@S100@'), _make_cit('@S_MERGE_002@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S100@': src_a, '@S_MERGE_002@': src_b},
        )
        deduplicate_merged_sources(merged)
        assert '@S_MERGE_002@' not in merged.sources
        assert '@S100@' in merged.sources

    def test_two_file_b_xrefs_one_removed(self):
        """When both xrefs are File-B style, the lexicographically smaller one is kept."""
        title = 'England, Select Births'
        src_a = _make_src('@S_MERGE_001@', title)
        src_b = _make_src('@S_MERGE_002@', title)
        ind = _make_indi('@I1@', [_make_cit('@S_MERGE_001@'), _make_cit('@S_MERGE_002@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S_MERGE_001@': src_a, '@S_MERGE_002@': src_b},
        )
        removed = deduplicate_merged_sources(merged)
        assert removed == 1
        assert len(merged.sources) == 1


class TestSubsetTitleBonus:
    """Title-subset pairs (one title is subset of the other's tokens) score 0.97 → merged."""

    def test_date_range_suffix_variant_merged(self):
        src_a = _make_src('@S1@', 'California, U.S., Newspapers.com Stories and Events Index')
        src_b = _make_src('@S_MERGE_003@',
                          'California, U.S., Newspapers.com Stories and Events Index, 1800s-current')
        ind = _make_indi('@I1@', [_make_cit('@S1@'), _make_cit('@S_MERGE_003@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_003@': src_b},
        )
        removed = deduplicate_merged_sources(merged)
        assert removed == 1
        assert '@S_MERGE_003@' not in merged.sources

    def test_shorter_title_kept_as_canonical(self):
        """The File-A (shorter/canonical) xref survives; File-B is removed."""
        src_a = _make_src('@S1@', 'Ohio, Marriage Abstracts')
        src_b = _make_src('@S_MERGE_004@', 'Ohio, Marriage Abstracts, 1970-2007')
        ind = _make_indi('@I1@', [_make_cit('@S1@'), _make_cit('@S_MERGE_004@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_004@': src_b},
        )
        deduplicate_merged_sources(merged)
        assert '@S1@' in merged.sources
        assert '@S_MERGE_004@' not in merged.sources


class TestUnrelatedSourcesNotMerged:
    """Low-similarity source pairs stay separate."""

    def test_different_databases_not_merged(self):
        src_a = _make_src('@S1@', 'U.S., World War I Draft Registration Cards, 1917-1918')
        src_b = _make_src('@S_MERGE_005@', 'England and Wales, Civil Registration Birth Index')
        ind = _make_indi('@I1@', [_make_cit('@S1@'), _make_cit('@S_MERGE_005@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_005@': src_b},
        )
        removed = deduplicate_merged_sources(merged)
        assert removed == 0
        assert len(merged.sources) == 2

    def test_different_location_prefix_not_merged(self):
        src_a = _make_src('@S1@', 'California, U.S., Death Index, 1940-1997')
        src_b = _make_src('@S_MERGE_006@', 'New York, U.S., Death Index, 1940-1997')
        ind = _make_indi('@I1@', [_make_cit('@S1@'), _make_cit('@S_MERGE_006@')])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_006@': src_b},
        )
        removed = deduplicate_merged_sources(merged)
        assert removed == 0


class TestEventAndNameCitations:
    """Citations on events and name records are also remapped."""

    def test_event_citations_remapped(self):
        title = 'U.S. Census, 1900'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_007@', title)
        ev = EventRecord(tag='BIRT', event_type=None, date=None, place=None,
                         citations=[_make_cit('@S1@'), _make_cit('@S_MERGE_007@')])
        ind = Individual(
            xref='@I1@',
            names=[NameRecord(full='A /B/', given='a', surname='b', name_type=None)],
            sex='M', events=[ev], family_child=[], family_spouse=[],
            citations=[], media=[], raw=_NULL_NODE,
        )
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_007@': src_b},
        )
        deduplicate_merged_sources(merged)
        ev_xrefs = [c.source_xref for c in merged.individuals['@I1@'].events[0].citations]
        assert '@S_MERGE_007@' not in ev_xrefs
        assert len(ev_xrefs) == 1

    def test_name_citations_remapped(self):
        title = 'U.S. Census, 1900'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_008@', title)
        nm = NameRecord(full='A /B/', given='a', surname='b', name_type=None,
                        citations=[_make_cit('@S1@'), _make_cit('@S_MERGE_008@')])
        ind = Individual(
            xref='@I1@', names=[nm], sex='M', events=[], family_child=[],
            family_spouse=[], citations=[], media=[], raw=_NULL_NODE,
        )
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_008@': src_b},
        )
        deduplicate_merged_sources(merged)
        nm_xrefs = [c.source_xref for c in merged.individuals['@I1@'].names[0].citations]
        assert '@S_MERGE_008@' not in nm_xrefs
        assert len(nm_xrefs) == 1

    def test_family_citations_remapped(self):
        title = 'U.S. Census, 1900'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_009@', title)
        fam = _make_fam('@F1@', [_make_cit('@S1@'), _make_cit('@S_MERGE_009@')])
        merged = _make_file(
            families={'@F1@': fam},
            sources={'@S1@': src_a, '@S_MERGE_009@': src_b},
        )
        deduplicate_merged_sources(merged)
        fam_xrefs = [c.source_xref for c in merged.families['@F1@'].citations]
        assert '@S_MERGE_009@' not in fam_xrefs
        assert len(fam_xrefs) == 1


class TestNonCocitedSourcesFullPass:
    """Sources never cited together are caught by the full title-based pass (Step 5)."""

    def test_identical_title_sources_on_different_records_are_merged(self):
        """Two identical-title sources on different individuals are deduped by full pass."""
        title = 'U.S. Census, 1900'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_010@', title)
        ind1 = _make_indi('@I1@', [_make_cit('@S1@')])
        ind2 = _make_indi('@I2@', [_make_cit('@S_MERGE_010@')])
        merged = _make_file(
            individuals={'@I1@': ind1, '@I2@': ind2},
            sources={'@S1@': src_a, '@S_MERGE_010@': src_b},
        )
        removed = deduplicate_merged_sources(merged)
        assert removed == 1
        assert '@S1@' in merged.sources
        assert '@S_MERGE_010@' not in merged.sources
        # ind2's citation remapped to canonical @S1@
        assert merged.individuals['@I2@'].citations[0].source_xref == '@S1@'


class TestSameFilePairDedup:
    """File-A vs File-A sources with near-identical titles (score ≥ 0.99) are merged."""

    def test_punctuation_only_difference_merged(self):
        """'U.S. City Directories' and 'U.S., City Directories' deduplicate."""
        src_a = _make_src('@S1@', 'U.S. City Directories, 1822-1995')
        src_b = _make_src('@S2@', 'U.S., City Directories, 1822-1995')
        ind1 = _make_indi('@I1@', [_make_cit('@S1@')])
        ind2 = _make_indi('@I2@', [_make_cit('@S2@')])
        merged = _make_file(
            individuals={'@I1@': ind1, '@I2@': ind2},
            sources={'@S1@': src_a, '@S2@': src_b},
        )
        removed = deduplicate_merged_sources(merged)
        assert removed == 1
        assert len(merged.sources) == 1

    def test_different_file_a_sources_not_merged(self):
        """Two genuinely different File-A sources (score < 0.99) are left separate."""
        src_a = _make_src('@S1@', 'U.S. Census, 1900')
        src_b = _make_src('@S2@', 'U.S. Census, 1880')
        ind1 = _make_indi('@I1@', [_make_cit('@S1@')])
        ind2 = _make_indi('@I2@', [_make_cit('@S2@')])
        merged = _make_file(
            individuals={'@I1@': ind1, '@I2@': ind2},
            sources={'@S1@': src_a, '@S2@': src_b},
        )
        removed = deduplicate_merged_sources(merged)
        assert removed == 0
        assert len(merged.sources) == 2


class TestPagePreservation:
    """Different PAGE values on the same source xref are kept as separate citations."""

    def test_same_source_different_pages_both_kept(self):
        title = 'U.S. Census, 1900'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_011@', title)
        ind = _make_indi('@I1@', [
            _make_cit('@S1@', page='Roll 42, page 7'),
            _make_cit('@S_MERGE_011@', page='Roll 99, page 3'),
        ])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_011@': src_b},
        )
        deduplicate_merged_sources(merged)
        # Both citations survive because pages differ
        assert len(merged.individuals['@I1@'].citations) == 2

    def test_same_source_same_page_deduped(self):
        title = 'U.S. Census, 1900'
        src_a = _make_src('@S1@', title)
        src_b = _make_src('@S_MERGE_012@', title)
        page = 'Roll 42, page 7'
        ind = _make_indi('@I1@', [
            _make_cit('@S1@', page=page),
            _make_cit('@S_MERGE_012@', page=page),
        ])
        merged = _make_file(
            individuals={'@I1@': ind},
            sources={'@S1@': src_a, '@S_MERGE_012@': src_b},
        )
        deduplicate_merged_sources(merged)
        assert len(merged.individuals['@I1@'].citations) == 1
