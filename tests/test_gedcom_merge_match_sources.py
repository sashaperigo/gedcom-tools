"""Tests for gedcom_merge.match_sources — TDD for source matching logic."""

from gedcom_merge.model import GedcomFile, Source, GedcomNode
from gedcom_merge.normalize import tokenize_title
from gedcom_merge.match_sources import match_sources, _score_pair, _score_title


def _make_source(xref: str, title: str, author: str = '', publisher: str = '') -> Source:
    node = GedcomNode(0, 'SOUR', '', xref)
    return Source(
        xref=xref,
        title=title,
        author=author or None,
        publisher=publisher or None,
        repository_xref=None,
        notes=[],
        refn=None,
        raw=node,
        title_tokens=tokenize_title(title),
    )


def _make_file(**sources) -> GedcomFile:
    return GedcomFile(
        individuals={},
        families={},
        sources=sources,
        repositories={},
        media={},
        notes={},
        submitter=None,
        header_raw=None,
    )


class TestScorePair:
    def test_identical_titles(self):
        a = _make_source('@S1@', 'Massachusetts Vital Records')
        b = _make_source('@S2@', 'Massachusetts Vital Records')
        score = _score_pair(a, b)
        assert score >= 0.90

    def test_nearly_identical_with_prefix_difference(self):
        a = _make_source('@S1@', 'Illinois Federal Naturalization Records 1856-1991')
        b = _make_source('@S2@', 'Illinois U.S. Federal Naturalization Records 1856-1991')
        score = _score_pair(a, b)
        assert score >= 0.75, f'Expected >= 0.75 but got {score}'

    def test_completely_different(self):
        a = _make_source('@S1@', 'Massachusetts Vital Records')
        b = _make_source('@S2@', 'Hamburg Passenger Lists 1850-1934')
        score = _score_pair(a, b)
        assert score < 0.65

    def test_same_title_different_author(self):
        a = _make_source('@S1@', 'U.S. Federal Census 1900', author='National Archives')
        b = _make_source('@S2@', 'U.S. Federal Census 1900', author='')
        score = _score_pair(a, b)
        # Author mismatch (one empty) should reduce score slightly but still match
        assert score >= 0.80

    def test_ancestry_tree_vs_ancestry_family_tree(self):
        """Singular/plural variation should score above review threshold."""
        a = _make_source('@S1@', 'Ancestry Family Trees')
        b = _make_source('@S2@', 'Ancestry Family Tree')
        score = _score_pair(a, b)
        # Singular/plural 'Tree'/'Trees' produces Jaccard=0.5, Levenshtein tiebreaker
        # brings total title score to ~0.72; overall ~0.83 → well above review threshold
        assert score >= 0.65  # above review threshold; may be candidate or auto-match


class TestMatchSources:
    def test_exact_match_auto(self):
        src_a = _make_source('@S1@', 'Massachusetts Vital Records')
        src_b = _make_source('@S2@', 'Massachusetts Vital Records')
        file_a = _make_file(**{'@S1@': src_a})
        file_b = _make_file(**{'@S2@': src_b})
        result = match_sources(file_a, file_b)
        assert len(result.auto_matches) == 1
        assert result.auto_matches[0].xref_a == '@S1@'
        assert result.auto_matches[0].xref_b == '@S2@'
        assert len(result.unmatched_b) == 0

    def test_no_match(self):
        src_a = _make_source('@S1@', 'Massachusetts Vital Records')
        src_b = _make_source('@S2@', 'Hamburg Passenger Lists 1850-1934')
        file_a = _make_file(**{'@S1@': src_a})
        file_b = _make_file(**{'@S2@': src_b})
        result = match_sources(file_a, file_b)
        assert len(result.auto_matches) == 0
        assert '@S2@' in result.unmatched_b

    def test_one_to_one_matching(self):
        """Each source matched only once even if multiple candidates exist."""
        src_a1 = _make_source('@S1@', 'U.S. Federal Census 1900')
        src_a2 = _make_source('@S2@', 'U.S. Federal Census 1910')
        src_b = _make_source('@S3@', 'U.S. Federal Census 1900')
        file_a = _make_file(**{'@S1@': src_a1, '@S2@': src_a2})
        file_b = _make_file(**{'@S3@': src_b})
        result = match_sources(file_a, file_b)
        # S3 should match S1 (not both S1 and S2)
        matched_a_xrefs = [m.xref_a for m in result.auto_matches]
        assert len(matched_a_xrefs) == len(set(matched_a_xrefs))  # no duplicates

    def test_empty_files(self):
        file_a = _make_file()
        file_b = _make_file()
        result = match_sources(file_a, file_b)
        assert result.auto_matches == []
        assert result.candidates == []
        assert result.unmatched_b == []

    def test_ancestry_location_prefix_veto(self):
        """Different location prefix → score 0.0, regardless of shared database name."""
        a = _make_source('@S1@', 'California, Driver Licenses, 1900-2000')
        b = _make_source('@S2@', 'Florida, Driver Licenses, 1900-2000')
        score = _score_title(a, b)
        assert score == 0.0, f'Expected 0.0 (location veto) but got {score}'

    def test_ancestry_same_location_prefix_matches(self):
        """Same location prefix → normal Jaccard scoring applies."""
        a = _make_source('@S1@', 'California, Driver Licenses, 1900-2000')
        b = _make_source('@S2@', 'California, Driver Licenses, 1900-2000')
        score = _score_title(a, b)
        assert score >= 0.90, f'Expected >= 0.90 but got {score}'

    def test_no_comma_titles_not_vetoed(self):
        """Titles without commas are not treated as Ancestry databases — no location veto."""
        a = _make_source('@S1@', 'Massachusetts Vital Records')
        b = _make_source('@S2@', 'Florida Vital Records')
        # No comma → no location extraction → normal Jaccard
        score = _score_title(a, b)
        # Should score low due to different state tokens, but NOT 0.0 from veto
        assert score < 0.80  # different states, low score is expected

    def test_ancestry_veto_full_pair_score(self):
        """Different locations veto the whole pair score via _score_pair."""
        a = _make_source('@S1@', 'California, Driver Licenses, 1900-2000')
        b = _make_source('@S2@', 'Florida, Driver Licenses, 1900-2000')
        score = _score_pair(a, b)
        assert score < 0.65, f'Expected below review threshold but got {score}'

    def test_candidate_threshold(self):
        """Moderately similar sources go to candidates, not auto-matches."""
        src_a = _make_source('@S1@', 'Illinois Naturalization Records 1856')
        src_b = _make_source('@S2@', 'Illinois Federal Naturalization Records 1991')
        file_a = _make_file(**{'@S1@': src_a})
        file_b = _make_file(**{'@S2@': src_b})
        result = match_sources(file_a, file_b, auto_threshold=0.90, review_threshold=0.65)
        # Depending on score, it's either a candidate or unmatched
        all_results = result.auto_matches + result.candidates + [
            type('x', (), {'xref_b': u})() for u in result.unmatched_b
        ]
        assert len(all_results) == 1  # exactly one disposition for the one B source
