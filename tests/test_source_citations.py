"""
Tests for event-level SOUR citation parsing in viz_ancestors.py.

Covers:
  - parse_gedcom:  2 SOUR @xref@ and 3 PAGE sub-records captured on event dicts
  - build_people_json: citations passed through to the output event objects
  - render_html:   window.SOURCES dict injected into the generated HTML
"""

import os
from pathlib import Path


os.environ.setdefault('GED_FILE', str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'))

from viz_ancestors import parse_gedcom, build_people_json, render_html


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse(tmp_path, gedcom_text: str):
    """Write gedcom_text to a temp file and return (indis, fams, sources)."""
    ged = tmp_path / 'test.ged'
    ged.write_text(gedcom_text, encoding='utf-8')
    return parse_gedcom(str(ged))


_BASE_HEADER = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
"""

_BASE_TRAILER = "0 TRLR\n"


def _ged(body: str) -> str:
    return _BASE_HEADER + body + _BASE_TRAILER


# ---------------------------------------------------------------------------
# TestEventCitationParsing
# ---------------------------------------------------------------------------

class TestEventCitationParsing:

    def test_event_with_single_citation_and_page(self, tmp_path):
        """2 SOUR @S1@ + 3 PAGE captured on the event's citations list."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Ellis Island Records
0 @I1@ INDI
1 NAME John /Smith/
1 BIRT
2 DATE 1900
2 PLAC London, England
2 SOUR @S1@
3 PAGE 47
"""))
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['citations'] == [{'sour_xref': '@S1@', 'page': '47'}]

    def test_event_with_citation_no_page(self, tmp_path):
        """2 SOUR @S1@ without a 3 PAGE line stores page as None."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Some Source
0 @I1@ INDI
1 NAME Jane /Doe/
1 DEAT
2 DATE 1950
2 SOUR @S1@
"""))
        deat = next(e for e in indis['@I1@']['events'] if e['tag'] == 'DEAT')
        assert deat['citations'] == [{'sour_xref': '@S1@', 'page': None}]

    def test_event_with_no_citations(self, tmp_path):
        """Events without any SOUR sub-records get an empty citations list."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @I1@ INDI
1 NAME Bob /Brown/
1 BIRT
2 DATE 1920
"""))
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['citations'] == []

    def test_event_with_multiple_citations(self, tmp_path):
        """Multiple 2 SOUR sub-records each become a separate citation entry."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Source One
0 @S2@ SOUR
1 TITL Source Two
0 @I1@ INDI
1 NAME Alice /Clark/
1 RESI
2 DATE 1930
2 SOUR @S1@
3 PAGE 12
2 SOUR @S2@
3 PAGE 99
"""))
        resi = next(e for e in indis['@I1@']['events'] if e['tag'] == 'RESI')
        assert len(resi['citations']) == 2
        assert resi['citations'][0] == {'sour_xref': '@S1@', 'page': '12'}
        assert resi['citations'][1] == {'sour_xref': '@S2@', 'page': '99'}

    def test_person_level_source_not_captured_as_event_citation(self, tmp_path):
        """1 SOUR @xref@ at person level must not appear in any event's citations."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Person Source
0 @I1@ INDI
1 NAME Tom /Jones/
1 BIRT
2 DATE 1880
1 SOUR @S1@
"""))
        # Person-level source present in source_xrefs
        assert '@S1@' in indis['@I1@']['source_xrefs']
        # But NOT in the BIRT event's citations
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['citations'] == []

    def test_citations_isolated_to_their_event(self, tmp_path):
        """A citation under one event does not bleed into the next event."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Some Source
0 @I1@ INDI
1 NAME Mary /White/
1 BIRT
2 DATE 1900
2 SOUR @S1@
3 PAGE 5
1 DEAT
2 DATE 1970
"""))
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        deat = next(e for e in indis['@I1@']['events'] if e['tag'] == 'DEAT')
        assert len(birt['citations']) == 1
        assert deat['citations'] == []

    def test_event_note_still_parsed_alongside_citation(self, tmp_path):
        """A 2 NOTE under the same event as a 2 SOUR must still be captured."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Some Source
0 @I1@ INDI
1 NAME Ed /Gray/
1 BIRT
2 DATE 1910
2 NOTE Born at home
2 SOUR @S1@
3 PAGE 3
"""))
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['note'] == 'Born at home'
        assert birt['citations'] == [{'sour_xref': '@S1@', 'page': '3'}]

    def test_all_event_types_get_citations_field(self, tmp_path):
        """Every event tag in _EVENT_TAGS must have a citations list after parsing."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @I1@ INDI
1 NAME Test /Person/
1 BIRT
2 DATE 1900
1 DEAT
2 DATE 1990
1 OCCU
2 TYPE Farmer
1 NATI
2 TYPE Greek
"""))
        for evt in indis['@I1@']['events']:
            assert 'citations' in evt, f"Event {evt['tag']} missing 'citations' key"
            assert isinstance(evt['citations'], list)


# ---------------------------------------------------------------------------
# TestBuildPeopleJsonCitations
# ---------------------------------------------------------------------------

class TestBuildPeopleJsonCitations:

    def test_citations_in_event_output(self, tmp_path):
        """build_people_json must pass event citations through to the output dict."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Birth Register
0 @I1@ INDI
1 NAME Lucy /Hill/
1 BIRT
2 DATE 1905
2 SOUR @S1@
3 PAGE 101
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        birt = next(e for e in people['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['citations'] == [{'sourceXref': '@S1@', 'page': '101'}]

    def test_empty_citations_in_event_output(self, tmp_path):
        """Events with no citations export an empty list, not None."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @I1@ INDI
1 NAME Sam /Green/
1 BIRT
2 DATE 1920
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        birt = next(e for e in people['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['citations'] == []


# ---------------------------------------------------------------------------
# TestSourcesJsInjection
# ---------------------------------------------------------------------------

class TestSourcesJsInjection:

    def test_sources_global_in_html(self, tmp_path):
        """render_html must embed a SOURCES constant with all source xrefs."""
        from viz_ancestors import build_tree_json, build_relatives_json

        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Ellis Island Records
0 @S2@ SOUR
1 TITL Greek Orthodox Ledger
0 @I1@ INDI
1 NAME Root /Person/
1 SEX M
1 BIRT
2 DATE 1900
1 SOUR @S1@
"""))
        tree = build_tree_json('@I1@', indis, fams)
        people = build_people_json(set(tree.values()), indis, fams=fams, sources=sources)
        relatives = build_relatives_json(tree, indis, fams)
        html = render_html(tree, 'Root Person', people, relatives, indis, fams,
                           root_xref='@I1@', sources=sources)

        assert 'const SOURCES' in html
        assert 'Ellis Island Records' in html
        assert 'Greek Orthodox Ledger' in html

    def test_sources_global_keyed_by_xref(self, tmp_path):
        """SOURCES dict in HTML must use the source xref as key."""
        from viz_ancestors import build_tree_json, build_relatives_json

        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S42@ SOUR
1 TITL Vital Records
0 @I1@ INDI
1 NAME Test /Root/
1 SEX F
1 BIRT
2 DATE 1910
1 SOUR @S42@
"""))
        tree = build_tree_json('@I1@', indis, fams)
        people = build_people_json(set(tree.values()), indis, fams=fams, sources=sources)
        relatives = build_relatives_json(tree, indis, fams)
        html = render_html(tree, 'Test Root', people, relatives, indis, fams,
                           root_xref='@I1@', sources=sources)

        # The xref must appear as a JSON key inside the SOURCES const
        assert '@S42@' in html
