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
        assert birt['citations'] == [{'sour_xref': '@S1@', 'page': '47', 'text': None, 'note': None}]

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
        assert deat['citations'] == [{'sour_xref': '@S1@', 'page': None, 'text': None, 'note': None}]

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
        assert resi['citations'][0] == {'sour_xref': '@S1@', 'page': '12', 'text': None, 'note': None}
        assert resi['citations'][1] == {'sour_xref': '@S2@', 'page': '99', 'text': None, 'note': None}

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
        assert birt['citations'] == [{'sour_xref': '@S1@', 'page': '3', 'text': None, 'note': None}]

    def test_event_citation_quoted_text_parsed(self, tmp_path):
        """4 TEXT under 3 DATA under 2 SOUR on an event citation is parsed into the text field."""
        indis, _, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 BIRT
2 DATE 1 JAN 1900
2 SOUR @S1@
3 PAGE p. 42
3 DATA
4 TEXT Baptised at St. Mary's church
"""))
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['citations'][0]['text'] == "Baptised at St. Mary's church"

    def test_event_citation_note_parsed(self, tmp_path):
        """3 NOTE under 2 SOUR on an event citation is stored in the note field."""
        indis, _, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 BIRT
2 DATE 1 JAN 1900
2 SOUR @S1@
3 PAGE p. 42
3 NOTE Researcher note
"""))
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['citations'][0]['note'] == 'Researcher note'

    def test_event_citation_text_and_note_in_build_people_json(self, tmp_path):
        """text and note from event citations must survive build_people_json normalisation."""
        indis, _, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 BIRT
2 DATE 1 JAN 1900
2 SOUR @S1@
3 PAGE p. 42
3 DATA
4 TEXT Baptised at St. Mary's
3 NOTE Researcher note
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        birt = next(e for e in people['@I1@']['events'] if e['tag'] == 'BIRT')
        cite = birt['citations'][0]
        assert cite['text'] == "Baptised at St. Mary's"
        assert cite['note'] == 'Researcher note'

    def test_fam_event_citation_quoted_text_parsed(self, tmp_path):
        """4 TEXT under 3 DATA under 2 SOUR on a FAM event citation is parsed."""
        _, fams, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Marriage Register
0 @I1@ INDI
1 NAME Anna /Smith/
1 SEX F
1 FAMS @F1@
0 @I2@ INDI
1 NAME Bob /Jones/
1 SEX M
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 1900
2 SOUR @S1@
3 PAGE p. 12
3 DATA
4 TEXT They married at the local chapel
3 NOTE Parish records confirm
"""))
        marr = fams['@F1@']['marrs'][0]
        assert marr['citations'][0]['text'] == 'They married at the local chapel'
        assert marr['citations'][0]['note'] == 'Parish records confirm'

    def test_event_citation_url_from_direct_www(self, tmp_path):
        """3 WWW directly under 2 SOUR (not inside DATA) should populate url field."""
        indis, _, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Some Source
0 @I1@ INDI
1 NAME John /Smith/
1 BIRT
2 DATE 1 JAN 1900
2 SOUR @S1@
3 PAGE p. 12
3 WWW https://example.com/event-direct
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        person = people['@I1@']
        events = person['events']
        birt = next(e for e in events if e['tag'] == 'BIRT')
        assert len(birt['citations']) == 1
        cite = birt['citations'][0]
        assert cite.get('url') == 'https://example.com/event-direct'
        assert cite['page'] == 'p. 12'

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
        assert birt['citations'] == [{'sourceXref': '@S1@', 'page': '101', 'text': None, 'note': None}]

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


# ---------------------------------------------------------------------------
# TestFamEventCitations — MARR/DIV citations on FAM records
# ---------------------------------------------------------------------------

class TestFamEventCitations:

    def test_marr_event_has_citations_field(self, tmp_path):
        """Every MARR event dict must carry a citations list."""
        _, fams, _ = _parse(tmp_path, _ged("""\
0 @I1@ INDI
1 NAME Anna /Smith/
1 SEX F
1 FAMS @F1@
0 @I2@ INDI
1 NAME Bob /Jones/
1 SEX M
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 1900
2 PLAC London
"""))
        marr = fams['@F1@']['marrs'][0]
        assert 'citations' in marr
        assert marr['citations'] == []

    def test_marr_with_single_citation_and_page(self, tmp_path):
        """2 SOUR @S1@ + 3 PAGE under a MARR is captured on the event."""
        _, fams, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Marriage Register
0 @I1@ INDI
1 NAME Anna /Smith/
1 SEX F
1 FAMS @F1@
0 @I2@ INDI
1 NAME Bob /Jones/
1 SEX M
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 1900
2 SOUR @S1@
3 PAGE p.47
"""))
        marr = fams['@F1@']['marrs'][0]
        assert marr['citations'] == [{'sour_xref': '@S1@', 'page': 'p.47', 'text': None, 'note': None}]

    def test_marr_with_multiple_citations(self, tmp_path):
        """Multiple 2 SOUR sub-records under one MARR each become a separate citation."""
        _, fams, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Civil Registry
0 @S2@ SOUR
1 TITL Church Record
0 @I1@ INDI
1 NAME Anna /Smith/
1 SEX F
1 FAMS @F1@
0 @I2@ INDI
1 NAME Bob /Jones/
1 SEX M
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 1900
2 SOUR @S1@
3 PAGE 12
2 SOUR @S2@
3 PAGE 99
"""))
        marr = fams['@F1@']['marrs'][0]
        assert len(marr['citations']) == 2
        assert marr['citations'][0] == {'sour_xref': '@S1@', 'page': '12', 'text': None, 'note': None}
        assert marr['citations'][1] == {'sour_xref': '@S2@', 'page': '99', 'text': None, 'note': None}

    def test_div_event_has_citations(self, tmp_path):
        """1 DIV events under FAM get parsed with citations list."""
        _, fams, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Divorce Decree
0 @I1@ INDI
1 NAME Anna /Smith/
1 SEX F
1 FAMS @F1@
0 @I2@ INDI
1 NAME Bob /Jones/
1 SEX M
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 1900
1 DIV
2 DATE 1910
2 SOUR @S1@
3 PAGE 7
"""))
        fam = fams['@F1@']
        assert 'divs' in fam
        div = fam['divs'][0]
        assert div['tag'] == 'DIV'
        assert div['date'] == '1910'
        assert div['citations'] == [{'sour_xref': '@S1@', 'page': '7', 'text': None, 'note': None}]

    def test_marr_citation_isolated_from_div(self, tmp_path):
        """Citations under MARR do not bleed into a following DIV event, and vice versa."""
        _, fams, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Marriage Src
0 @S2@ SOUR
1 TITL Divorce Src
0 @I1@ INDI
1 NAME A /X/
1 SEX F
1 FAMS @F1@
0 @I2@ INDI
1 NAME B /Y/
1 SEX M
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 1900
2 SOUR @S1@
3 PAGE 1
1 DIV
2 DATE 1910
2 SOUR @S2@
3 PAGE 2
"""))
        fam = fams['@F1@']
        assert fam['marrs'][0]['citations'] == [{'sour_xref': '@S1@', 'page': '1', 'text': None, 'note': None}]
        assert fam['divs'][0]['citations'] == [{'sour_xref': '@S2@', 'page': '2', 'text': None, 'note': None}]

    def test_fam_event_citation_url_from_direct_www(self, tmp_path):
        """3 WWW directly under 2 SOUR in FAM event should populate url field."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Test Source
0 @I1@ INDI
1 NAME Husb /Test/
1 SEX M
1 FAMS @F1@
0 @I2@ INDI
1 NAME Wife /Test/
1 SEX F
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1920
2 SOUR @S1@
3 PAGE certificate 42
3 WWW https://example.com/fam-direct
"""))
        people = build_people_json({'@I1@'}, indis, fams=fams, sources=sources)
        person = people['@I1@']
        marr_events = [e for e in person['events'] if e['tag'] == 'MARR']
        assert len(marr_events) == 1
        cite = marr_events[0]['citations'][0]
        assert cite.get('url') == 'https://example.com/fam-direct'

    def test_build_people_json_carries_marr_citations(self, tmp_path):
        """build_people_json must include citations on the MARR events it merges into each spouse's event list."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Marriage Register
0 @I1@ INDI
1 NAME Anna /Smith/
1 SEX F
1 FAMS @F1@
0 @I2@ INDI
1 NAME Bob /Jones/
1 SEX M
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I1@
1 MARR
2 DATE 1900
2 SOUR @S1@
3 PAGE p.47
"""))
        people = build_people_json({'@I1@', '@I2@'}, indis, fams=fams, sources=sources)
        for xref in ('@I1@', '@I2@'):
            marr = next(e for e in people[xref]['events'] if e['tag'] == 'MARR')
            assert marr['citations'] == [{'sourceXref': '@S1@', 'page': 'p.47', 'text': None, 'note': None}]


# ---------------------------------------------------------------------------
# TestIndiSourceCitationParsing — person-level SOUR with full citation data
# ---------------------------------------------------------------------------

class TestIndiSourceCitationParsing:

    def test_person_level_sour_captured_in_source_citations(self, tmp_path):
        """1 SOUR @xref@ at person level is stored in source_citations list."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
"""))
        assert len(indis['@I1@']['source_citations']) == 1
        assert indis['@I1@']['source_citations'][0]['sour_xref'] == '@S1@'

    def test_person_level_sour_captures_page(self, tmp_path):
        """2 PAGE under 1 SOUR is stored on the citation entry."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
2 PAGE p.47
"""))
        assert indis['@I1@']['source_citations'][0]['page'] == 'p.47'

    def test_person_level_sour_captures_note(self, tmp_path):
        """2 NOTE under 1 SOUR is stored on the citation entry."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
2 NOTE cited online
"""))
        assert indis['@I1@']['source_citations'][0]['note'] == 'cited online'

    def test_person_level_sour_captures_text(self, tmp_path):
        """3 TEXT under 2 DATA under 1 SOUR is stored on the citation entry."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
2 DATA
3 TEXT Born in Athens
"""))
        assert indis['@I1@']['source_citations'][0]['text'] == 'Born in Athens'

    def test_person_level_sour_captures_url(self, tmp_path):
        """3 WWW under 1 SOUR is stored as url on the citation entry."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
3 WWW https://example.com/record
"""))
        assert indis['@I1@']['source_citations'][0]['url'] == 'https://example.com/record'

    def test_multiple_person_level_sour_entries_preserved(self, tmp_path):
        """Multiple 1 SOUR entries (even same xref) each get their own entry in source_citations."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Source One
0 @S2@ SOUR
1 TITL Source Two
0 @I1@ INDI
1 NAME Jane /Doe/
1 SOUR @S1@
2 PAGE p.1
1 SOUR @S2@
2 PAGE p.99
"""))
        cites = indis['@I1@']['source_citations']
        assert len(cites) == 2
        assert cites[0] == {'sour_xref': '@S1@', 'page': 'p.1', 'text': None, 'note': None, 'url': None}
        assert cites[1] == {'sour_xref': '@S2@', 'page': 'p.99', 'text': None, 'note': None, 'url': None}

    def test_person_sour_does_not_bleed_into_event(self, tmp_path):
        """A person-level SOUR after a BIRT event doesn't affect the event's citations."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Some Source
0 @I1@ INDI
1 NAME Bob /Brown/
1 BIRT
2 DATE 1900
1 SOUR @S1@
"""))
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['citations'] == []
        assert len(indis['@I1@']['source_citations']) == 1

    def test_event_sour_does_not_bleed_into_person_citations(self, tmp_path):
        """A 2 SOUR under a BIRT event doesn't appear in source_citations."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Some Source
0 @I1@ INDI
1 NAME Bob /Brown/
1 BIRT
2 DATE 1900
2 SOUR @S1@
3 PAGE 5
"""))
        assert indis['@I1@']['source_citations'] == []

    def test_person_level_sour_text_multiline_cont(self, tmp_path):
        """4 CONT lines after 3 TEXT are joined with newlines into cite['text']."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Death Record
0 @I1@ INDI
1 NAME Antonio /Malamo/
1 SOUR @S1@
2 DATA
3 TEXT Name    Antonio V Malamo
4 CONT Age     45
4 CONT Cause   Heart failure
"""))
        text = indis['@I1@']['source_citations'][0]['text']
        assert text == 'Name    Antonio V Malamo\nAge     45\nCause   Heart failure'

    def test_person_level_sour_text_conc_no_newline(self, tmp_path):
        """4 CONC lines are concatenated without a newline (long-line wrapping)."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Register
0 @I1@ INDI
1 NAME Jane /Doe/
1 SOUR @S1@
2 DATA
3 TEXT This is a very long line that was split
4 CONC  by CONC for line-length reasons
"""))
        text = indis['@I1@']['source_citations'][0]['text']
        assert text == 'This is a very long line that was split by CONC for line-length reasons'

    def test_person_level_sour_note_multiline_cont(self, tmp_path):
        """3 CONT lines after 2 NOTE are joined with newlines into cite['note']."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
2 NOTE First line of note
3 CONT Second line of note
3 CONT Third line of note
"""))
        note = indis['@I1@']['source_citations'][0]['note']
        assert note == 'First line of note\nSecond line of note\nThird line of note'

    def test_person_citation_url_from_direct_www(self, tmp_path):
        """2 WWW directly under 1 SOUR (not inside DATA) should populate url field."""
        indis, _, _ = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Some Source
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
2 PAGE p. 8
2 DATA
3 TEXT Some quoted text
2 QUAY 2
2 WWW https://example.com/direct
"""))
        assert len(indis['@I1@']['source_citations']) == 1
        cite = indis['@I1@']['source_citations'][0]
        assert cite['url'] == 'https://example.com/direct'
        assert cite['page'] == 'p. 8'
        assert cite['text'] == 'Some quoted text'


class TestBuildPeopleJsonIndiCitations:

    def test_sources_includes_citation_key(self, tmp_path):
        """build_people_json returns citationKey='SOUR:0' on first person source."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        src = people['@I1@']['sources'][0]
        assert src['citationKey'] == 'SOUR:0'

    def test_sources_includes_source_xref(self, tmp_path):
        """build_people_json returns sourceXref on each person source entry."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        assert people['@I1@']['sources'][0]['sourceXref'] == '@S1@'

    def test_sources_includes_page(self, tmp_path):
        """build_people_json includes page from the person-level citation."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Parish Register
0 @I1@ INDI
1 NAME John /Smith/
1 SOUR @S1@
2 PAGE p.47
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        assert people['@I1@']['sources'][0]['page'] == 'p.47'

    def test_sources_sequential_citation_keys(self, tmp_path):
        """Multiple person-level sources get SOUR:0, SOUR:1, etc. in file order."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @S1@ SOUR
1 TITL Source One
0 @S2@ SOUR
1 TITL Source Two
0 @I1@ INDI
1 NAME Jane /Doe/
1 SOUR @S1@
1 SOUR @S2@
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        srcs = people['@I1@']['sources']
        assert srcs[0]['citationKey'] == 'SOUR:0'
        assert srcs[1]['citationKey'] == 'SOUR:1'

    def test_sources_empty_when_no_person_level_sour(self, tmp_path):
        """Person with no 1 SOUR lines gets an empty sources list."""
        indis, fams, sources = _parse(tmp_path, _ged("""\
0 @I1@ INDI
1 NAME Nobody /Known/
1 BIRT
2 DATE 1900
"""))
        people = build_people_json({'@I1@'}, indis, sources=sources)
        assert people['@I1@']['sources'] == []
