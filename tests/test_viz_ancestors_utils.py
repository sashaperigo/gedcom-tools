"""
Tests for utility functions in viz_ancestors.py that were previously untested.

Covers:
  - build_addr_by_place  – {place: [sorted unique addr values]} for autocomplete
  - _find_person         – locate an INDI xref by exact xref or name substring
"""

from pathlib import Path

import pytest

from viz_ancestors import parse_gedcom, build_addr_by_place, build_all_places, _find_person

_FIXTURE_GED = str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_indis(tmp_path, gedcom_text: str) -> dict:
    """Write gedcom_text to a temp file, parse it, and return the indis dict."""
    ged = tmp_path / 'test.ged'
    ged.write_text(gedcom_text, encoding='utf-8')
    indis, _, _ = parse_gedcom(str(ged))
    return indis


# ---------------------------------------------------------------------------
# Shared GEDCOM text for build_addr_by_place tests
# ---------------------------------------------------------------------------

_ADDR_GEDCOM = """\
0 HEAD
1 GEDC
2 VERS 5.5
0 @I1@ INDI
1 NAME John /Smith/
1 BIRT
2 DATE 1900
2 PLAC London, England
2 ADDR 10 Downing Street
1 RESI
2 DATE 1920
2 PLAC London, England
2 ADDR 221B Baker Street
1 RESI
2 DATE 1930
2 PLAC Paris, France
2 ADDR 1 Rue de la Paix
0 @I2@ INDI
1 NAME Jane /Brown/
1 RESI
2 PLAC London, England
2 ADDR No. 1 Whitehall
0 @I3@ INDI
1 NAME Bob /Clark/
1 BIRT
2 DATE 1910
2 PLAC Rome, Italy
0 @I4@ INDI
1 NAME Ted /Hill/
1 BIRT
2 DATE 1915
2 ADDR Orphan Street
0 TRLR
"""


# ===========================================================================
# build_addr_by_place
# ===========================================================================

class TestBuildAddrByPlace:
    @pytest.fixture(scope='class')
    def indis(self, tmp_path_factory):
        tmp_path = tmp_path_factory.mktemp('addr')
        return _make_indis(tmp_path, _ADDR_GEDCOM)

    def test_empty_indis_returns_empty_dict(self):
        assert build_addr_by_place({}) == {}

    def test_event_with_place_and_addr_creates_key(self, indis):
        result = build_addr_by_place(indis)
        assert 'London, England' in result

    def test_addr_appears_in_values(self, indis):
        result = build_addr_by_place(indis)
        assert '10 Downing Street' in result['London, England']

    def test_multiple_addrs_for_same_place_all_present(self, indis):
        result = build_addr_by_place(indis)
        london = result['London, England']
        assert '221B Baker Street' in london
        assert 'No. 1 Whitehall' in london

    def test_multiple_addrs_for_same_place_sorted(self, indis):
        result = build_addr_by_place(indis)
        london = result['London, England']
        assert london == sorted(london)

    def test_multiple_addrs_deduplicated(self, tmp_path):
        # Two individuals, same place + same addr
        ged = """\
0 HEAD
0 @I1@ INDI
1 NAME A /A/
1 RESI
2 PLAC Rome
2 ADDR Via Roma
0 @I2@ INDI
1 NAME B /B/
1 RESI
2 PLAC Rome
2 ADDR Via Roma
0 TRLR
"""
        indis = _make_indis(tmp_path, ged)
        result = build_addr_by_place(indis)
        assert result['Rome'].count('Via Roma') == 1

    def test_event_with_no_addr_excluded(self, indis):
        # @I3@ has PLAC but no ADDR — Rome should not be a key
        result = build_addr_by_place(indis)
        assert 'Rome, Italy' not in result

    def test_event_with_no_place_excluded(self, indis):
        # @I4@ has ADDR but no PLAC — should not create any key
        result = build_addr_by_place(indis)
        assert not any('Orphan Street' in str(v) for v in result.values())

    def test_different_places_are_separate_keys(self, indis):
        result = build_addr_by_place(indis)
        assert 'Paris, France' in result
        assert result['Paris, France'] != result.get('London, England')

    def test_values_are_lists_not_sets(self, indis):
        result = build_addr_by_place(indis)
        for v in result.values():
            assert isinstance(v, list)


# ===========================================================================
# _find_person
# ===========================================================================

def _sample_indis():
    """Minimal in-memory indis dict without needing file I/O."""
    return {
        '@I1@': {'name': 'Rose Smith',   'events': [], 'notes': []},
        '@I2@': {'name': 'James Smith',  'events': [], 'notes': []},
        '@I3@': {'name': 'Clara Jones',  'events': [], 'notes': []},
        '@I4@': {'name': None,           'events': [], 'notes': []},  # no name
    }


class TestFindPerson:
    def test_exact_xref_match(self):
        assert _find_person('@I1@', _sample_indis()) == '@I1@'

    def test_exact_xref_not_in_indis_returns_none(self):
        assert _find_person('@I99@', _sample_indis()) is None

    def test_name_substring_match_case_insensitive(self):
        assert _find_person('rose', _sample_indis()) == '@I1@'

    def test_name_full_match(self):
        assert _find_person('Rose Smith', _sample_indis()) == '@I1@'

    def test_name_partial_surname(self):
        # 'Jones' matches Clara Jones
        assert _find_person('Jones', _sample_indis()) == '@I3@'

    def test_name_uppercase_query(self):
        assert _find_person('CLARA', _sample_indis()) == '@I3@'

    def test_individual_with_none_name_skipped(self):
        # @I4@ has name=None; querying a unique substring must not crash
        result = _find_person('rose', _sample_indis())
        assert result == '@I1@'  # still finds the right one

    def test_empty_indis_returns_none(self):
        assert _find_person('@I1@', {}) is None

    def test_no_match_returns_none(self):
        assert _find_person('Zephyr', _sample_indis()) is None


# ===========================================================================
# build_all_places
# ===========================================================================

def _indis_with_places():
    return {
        '@I1@': {'events': [
            {'tag': 'BIRT', 'place': 'London, England'},
            {'tag': 'RESI', 'place': 'Paris, France'},
            {'tag': 'DEAT', 'place': 'London, England'},   # duplicate of first
        ]},
        '@I2@': {'events': [
            {'tag': 'BIRT', 'place': 'Rome, Roma, Lazio, Italy'},
            {'tag': 'RESI', 'place': None},                 # no place
            {'tag': 'OCCU'},                                # no place key at all
        ]},
        '@I3@': {'events': []},                             # no events
    }


class TestBuildAllPlaces:
    def test_empty_indis_returns_empty_list(self):
        assert build_all_places({}) == []

    def test_empty_indis_with_none_fams_returns_empty_list(self):
        assert build_all_places({}, fams=None) == []

    def test_places_from_indi_events_included(self):
        result = build_all_places(_indis_with_places())
        assert 'London, England' in result
        assert 'Paris, France' in result
        assert 'Rome, Roma, Lazio, Italy' in result

    def test_duplicates_deduplicated(self):
        result = build_all_places(_indis_with_places())
        assert result.count('London, England') == 1

    def test_events_without_place_excluded(self):
        result = build_all_places(_indis_with_places())
        assert None not in result
        assert '' not in result

    def test_result_is_sorted(self):
        result = build_all_places(_indis_with_places())
        assert result == sorted(result)

    def test_result_is_list(self):
        assert isinstance(build_all_places(_indis_with_places()), list)

    def test_fam_marr_place_included(self):
        indis = {'@I1@': {'events': []}}
        fams = {
            '@F1@': {'marrs': [{'date': '1920', 'place': 'Athens, Greece'}]},
        }
        result = build_all_places(indis, fams=fams)
        assert 'Athens, Greece' in result

    def test_fam_marr_without_place_excluded(self):
        indis = {}
        fams = {'@F1@': {'marrs': [{'date': '1920'}]}}   # no 'place' key
        result = build_all_places(indis, fams=fams)
        assert result == []

    def test_fam_non_dict_event_skipped(self):
        # FAM records with no marrs list produce no places
        indis = {}
        fams = {'@F1@': {'marrs': []}, '@F2@': {}}
        result = build_all_places(indis, fams=fams)
        assert result == []

    def test_indi_and_fam_places_combined_and_deduplicated(self):
        indis = {'@I1@': {'events': [{'tag': 'BIRT', 'place': 'Athens, Greece'}]}}
        fams  = {'@F1@': {'marrs': [{'place': 'Athens, Greece'}]}}
        result = build_all_places(indis, fams=fams)
        assert result.count('Athens, Greece') == 1


# ---------------------------------------------------------------------------
# Note citation parsing
# ---------------------------------------------------------------------------

class TestNoteCitationParsing:

    def test_inline_note_with_sour_and_page(self, tmp_path):
        ged = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME John /Doe/
1 NOTE Some note text
2 SOUR @S1@
3 PAGE 42
0 @S1@ SOUR
1 TITL Birth Register
0 TRLR"""
        indis = _make_indis(tmp_path, ged)
        notes = indis['@I1@']['notes']
        assert len(notes) == 1
        assert notes[0]['citations'] == [{'sour_xref': '@S1@', 'page': '42'}]
        assert notes[0]['note_idx'] == 0

    def test_inline_note_sour_no_page(self, tmp_path):
        ged = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME John /Doe/
1 NOTE Some note text
2 SOUR @S1@
0 TRLR"""
        indis = _make_indis(tmp_path, ged)
        assert indis['@I1@']['notes'][0]['citations'] == [{'sour_xref': '@S1@', 'page': None}]

    def test_inline_note_multiple_citations(self, tmp_path):
        ged = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME John /Doe/
1 NOTE Some note text
2 SOUR @S1@
3 PAGE 10
2 SOUR @S2@
3 PAGE 20
0 TRLR"""
        indis = _make_indis(tmp_path, ged)
        cites = indis['@I1@']['notes'][0]['citations']
        assert len(cites) == 2
        assert cites[0] == {'sour_xref': '@S1@', 'page': '10'}
        assert cites[1] == {'sour_xref': '@S2@', 'page': '20'}

    def test_multiple_notes_get_correct_note_idx(self, tmp_path):
        ged = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME John /Doe/
1 NOTE First note
1 NOTE Second note
0 TRLR"""
        indis = _make_indis(tmp_path, ged)
        notes = indis['@I1@']['notes']
        assert notes[0]['note_idx'] == 0
        assert notes[1]['note_idx'] == 1

    def test_inline_note_no_citations_has_empty_list(self, tmp_path):
        ged = """\
0 HEAD
1 SOUR Test
0 @I1@ INDI
1 NAME John /Doe/
1 NOTE Just text, no sources
0 TRLR"""
        indis = _make_indis(tmp_path, ged)
        assert indis['@I1@']['notes'][0]['citations'] == []

    def test_shared_note_with_sour_and_page(self, tmp_path):
        ged = """\
0 HEAD
1 SOUR Test
0 @N1@ NOTE Shared note text
1 SOUR @S1@
2 PAGE 10
0 @I1@ INDI
1 NAME John /Doe/
1 NOTE @N1@
0 @S1@ SOUR
1 TITL Some Source
0 TRLR"""
        indis = _make_indis(tmp_path, ged)
        notes = indis['@I1@']['notes']
        assert len(notes) == 1
        assert notes[0]['shared'] is True
        assert notes[0]['note_xref'] == '@N1@'
        assert notes[0]['citations'] == [{'sour_xref': '@S1@', 'page': '10'}]

    def test_shared_note_no_citations(self, tmp_path):
        ged = """\
0 HEAD
1 SOUR Test
0 @N1@ NOTE Shared note text
0 @I1@ INDI
1 NAME John /Doe/
1 NOTE @N1@
0 TRLR"""
        indis = _make_indis(tmp_path, ged)
        assert indis['@I1@']['notes'][0]['citations'] == []

    def test_inline_and_shared_notes_mixed(self, tmp_path):
        ged = """\
0 HEAD
1 SOUR Test
0 @N1@ NOTE Shared
1 SOUR @S1@
0 @I1@ INDI
1 NAME John /Doe/
1 NOTE @N1@
1 NOTE Inline note
2 SOUR @S2@
0 TRLR"""
        indis = _make_indis(tmp_path, ged)
        notes = indis['@I1@']['notes']
        assert notes[0]['note_idx'] == 0
        assert notes[0]['shared'] is True
        assert len(notes[0]['citations']) == 1
        assert notes[1]['note_idx'] == 1
        assert notes[1]['shared'] is False
        assert len(notes[1]['citations']) == 1
