"""
Tests for viz_ancestors.py

Covers:
  - GEDCOM parsing: names, birth/death years, sex, events, notes, FAMC links
  - Parent lookup via FAM records
  - Ahnentafel ancestor tree building
  - HTML output generation including detail panel
"""

from pathlib import Path

import pytest

from viz_ancestors import parse_gedcom, get_parents, build_tree_json, build_people_json, build_relatives_json, viz_ancestors, _date_sort_key, sort_events

FIXTURE = Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def parsed():
    return parse_gedcom(str(FIXTURE))


@pytest.fixture(scope='module')
def indis(parsed):
    return parsed[0]


@pytest.fixture(scope='module')
def fams(parsed):
    return parsed[1]


# ---------------------------------------------------------------------------
# TestParsing
# ---------------------------------------------------------------------------

class TestParsing:

    def test_fixture_exists(self):
        assert FIXTURE.exists()

    def test_all_indis_parsed(self, indis):
        assert len(indis) == 13  # @I1@ through @I13@

    def test_parse_indi_name(self, indis):
        """Slashes around surname must be stripped."""
        assert indis['@I1@']['name'] == 'Rose Smith'

    def test_parse_name_with_apostrophe(self, indis):
        assert indis['@I5@']['name'] == "Mary O'Brien"

    def test_parse_birth_year_exact(self, indis):
        """Exact year extracted from full DATE."""
        assert indis['@I2@']['birth_year'] == '1960'

    def test_parse_birth_year_with_day_month(self, indis):
        """Day+month+year: only year returned."""
        assert indis['@I1@']['birth_year'] == '1990'

    def test_parse_birth_year_approximate(self, indis):
        """'ABT 1963' → '1963'."""
        assert indis['@I3@']['birth_year'] == '1963'

    def test_parse_birth_year_none(self, indis):
        """Individual with no BIRT DATE has birth_year None."""
        assert indis['@I10@']['birth_year'] == '1905'  # @I10@ does have a birth year

    def test_parse_death_year(self, indis):
        assert indis['@I4@']['death_year'] == '2005'

    def test_parse_no_death(self, indis):
        """Individual with no DEAT has death_year None."""
        assert indis['@I3@']['death_year'] is None

    def test_parse_famc(self, indis):
        assert indis['@I1@']['famc'] == '@F1@'

    def test_parse_no_famc(self, indis):
        """Individual with no FAMC link has famc None."""
        assert indis['@I4@']['famc'] is None

    def test_all_fams_parsed(self, fams):
        assert len(fams) == 6  # @F1@ through @F6@

    def test_fam_husb_wife(self, fams):
        assert fams['@F1@']['husb'] == '@I2@'
        assert fams['@F1@']['wife'] == '@I3@'

    def test_fam_missing_wife(self, fams):
        """@F6@ has no WIFE."""
        assert fams['@F6@']['husb'] == '@I10@'
        assert fams['@F6@']['wife'] is None

    def test_parse_sex(self, indis):
        assert indis['@I1@']['sex'] == 'F'
        assert indis['@I2@']['sex'] == 'M'

    def test_parse_sex_none_when_absent(self, indis):
        """Any INDI without a SEX tag should have sex None."""
        # All fixture indis have SEX — confirm @I3@ has it too
        assert indis['@I3@']['sex'] == 'F'

    def test_parse_events_list(self, indis):
        assert isinstance(indis['@I1@']['events'], list)
        assert len(indis['@I1@']['events']) > 0

    def test_parse_birt_event_has_date_and_place(self, indis):
        birt = next(e for e in indis['@I1@']['events'] if e['tag'] == 'BIRT')
        assert birt['date'] == '14 MAR 1990'
        assert birt['place'] == 'Greenwich, Connecticut, USA'

    def test_parse_birt_event_date_only(self, indis):
        """@I2@ BIRT has date and place."""
        birt = next(e for e in indis['@I2@']['events'] if e['tag'] == 'BIRT')
        assert birt['date'] == '1960'
        assert birt['place'] == 'Ann Arbor, Michigan, USA'

    def test_parse_occu_event(self, indis):
        """@I2@ has an OCCU event with a TYPE."""
        occu = next((e for e in indis['@I2@']['events'] if e['tag'] == 'OCCU'), None)
        assert occu is not None
        assert occu['type'] == 'Engineer'

    def test_parse_notes_list(self, indis):
        assert isinstance(indis['@I1@']['notes'], list)
        assert len(indis['@I1@']['notes']) == 1

    def test_parse_note_text(self, indis):
        assert 'Rose was an avid gardener' in indis['@I1@']['notes'][0]

    def test_parse_note_cont_assembled(self, indis):
        """CONT line must be joined onto the note with a newline."""
        note = indis['@I1@']['notes'][0]
        assert '\n' in note
        assert 'prize-winning roses' in note

    def test_parse_no_notes(self, indis):
        """@I2@ has no NOTE tag."""
        assert indis['@I2@']['notes'] == []

    def test_parse_fact_aka_note(self, indis):
        """FACT with TYPE AKA and 2 NOTE child captures the alias in evt.note."""
        aka = next((e for e in indis['@I1@']['events'] if e['tag'] == 'FACT'), None)
        assert aka is not None
        assert aka['type'] == 'AKA'
        assert aka['note'] == 'Rosie Smith'

    def test_parse_fams_single(self, indis):
        """FAMS tag on INDI must be stored as a list."""
        assert indis['@I2@']['fams'] == ['@F1@']

    def test_parse_fams_absent(self, indis):
        """INDI with no FAMS gets an empty list."""
        assert indis['@I11@']['fams'] == []

    def test_parse_fams_root_has_fams(self, indis):
        """Root person @I1@ has FAMS @F5@."""
        assert '@F5@' in indis['@I1@']['fams']

    def test_parse_chil_single(self, fams):
        """@F3@ has exactly one CHIL."""
        assert fams['@F3@']['chil'] == ['@I3@']

    def test_parse_chil_multiple(self, fams):
        """@F1@ has two children: Rose and Alice."""
        assert set(fams['@F1@']['chil']) == {'@I1@', '@I11@'}

    def test_parse_chil_absent(self, fams):
        """@F5@ (Rose/Mark marriage) has no children."""
        assert fams['@F5@']['chil'] == []


# ---------------------------------------------------------------------------
# TestParentLookup
# ---------------------------------------------------------------------------

class TestParentLookup:

    def test_get_parents_both_known(self, indis, fams):
        father, mother = get_parents('@I1@', indis, fams)
        assert father == '@I2@'
        assert mother == '@I3@'

    def test_get_parents_one_missing(self, indis, fams):
        """@I6@ is FAMC @F6@, which has HUSB but no WIFE."""
        father, mother = get_parents('@I6@', indis, fams)
        assert father == '@I10@'
        assert mother is None

    def test_get_parents_no_famc(self, indis, fams):
        """@I4@ has no FAMC link."""
        father, mother = get_parents('@I4@', indis, fams)
        assert father is None
        assert mother is None


# ---------------------------------------------------------------------------
# TestTree  (Ahnentafel key → xref mapping)
# ---------------------------------------------------------------------------

class TestTree:

    @pytest.fixture(scope='class')
    def tree(self, indis, fams):
        return build_tree_json('@I1@', indis, fams)

    def test_root_has_ahnentafel_1(self, tree):
        assert 1 in tree
        assert tree[1] == '@I1@'

    def test_father_is_2(self, tree):
        assert tree[2] == '@I2@'

    def test_mother_is_3(self, tree):
        assert tree[3] == '@I3@'

    def test_paternal_grandfather_is_4(self, tree):
        assert tree[4] == '@I4@'

    def test_paternal_grandmother_is_5(self, tree):
        assert tree[5] == '@I5@'

    def test_maternal_grandfather_is_6(self, tree):
        assert tree[6] == '@I6@'

    def test_maternal_grandmother_is_7(self, tree):
        assert tree[7] == '@I7@'

    def test_missing_ancestor_absent(self, tree):
        """Patrick Smith (@I4@) has no FAMC → his parents (keys 8,9) absent."""
        assert 8 not in tree
        assert 9 not in tree

    def test_great_grandparents_via_maternal_grandmother(self, tree):
        """Jane Brown's parents → keys 14 (father) and 15 (mother)."""
        assert tree[14] == '@I8@'
        assert tree[15] == '@I9@'

    def test_missing_half_branch(self, tree):
        """@F6@ has no WIFE → maternal grandfather's mother (key 13) absent."""
        assert 12 in tree
        assert 13 not in tree

    def test_ancestor_count(self, tree):
        assert len(tree) == 10

    def test_values_are_xrefs(self, tree):
        """Every value must be a valid INDI xref string."""
        for xref in tree.values():
            assert isinstance(xref, str)
            assert xref.startswith('@I')


# ---------------------------------------------------------------------------
# TestPeople  (full person data lookup)
# ---------------------------------------------------------------------------

class TestPeople:

    @pytest.fixture(scope='class')
    def tree(self, indis, fams):
        return build_tree_json('@I1@', indis, fams)

    @pytest.fixture(scope='class')
    def people(self, tree, indis, parsed):
        _, _, sources = parsed
        return build_people_json(set(tree.values()), indis, sources)

    def test_root_in_people(self, people):
        assert '@I1@' in people

    def test_people_has_required_fields(self, people):
        p = people['@I1@']
        for field in ('name', 'birth_year', 'death_year', 'sex', 'events', 'notes', 'sources'):
            assert field in p

    def test_name(self, people):
        assert people['@I1@']['name'] == 'Rose Smith'
        assert people['@I2@']['name'] == 'James Smith'

    def test_sex(self, people):
        assert people['@I1@']['sex'] == 'F'
        assert people['@I2@']['sex'] == 'M'

    def test_birth_year(self, people):
        assert people['@I2@']['birth_year'] == '1960'

    def test_events_list(self, people):
        assert isinstance(people['@I1@']['events'], list)
        assert any(e['tag'] == 'BIRT' for e in people['@I1@']['events'])

    def test_notes(self, people):
        assert len(people['@I1@']['notes']) > 0
        assert 'Rose was an avid gardener' in people['@I1@']['notes'][0]

    def test_relative_xref_included(self, tree, indis, parsed):
        """build_people_json also works for relative xrefs (siblings/spouses)."""
        _, _, sources = parsed
        people = build_people_json({'@I11@', '@I12@'}, indis, sources)
        assert people['@I11@']['name'] == 'Alice Smith'
        assert people['@I12@']['name'] == 'Mark Davis'

    def test_unknown_xref_excluded(self, indis, parsed):
        """An xref not in indis is silently skipped."""
        _, _, sources = parsed
        people = build_people_json({'@NOBODY@'}, indis, sources)
        assert '@NOBODY@' not in people


# ---------------------------------------------------------------------------
# TestRelatives
# ---------------------------------------------------------------------------

class TestRelatives:

    @pytest.fixture(scope='class')
    def tree(self, indis, fams):
        return build_tree_json('@I1@', indis, fams)

    @pytest.fixture(scope='class')
    def relatives(self, tree, indis, fams):
        return build_relatives_json(tree, indis, fams)

    def test_root_has_siblings(self, relatives):
        """@I1@ (Rose) has Alice Smith (@I11@) as a sibling."""
        assert '@I1@' in relatives
        assert '@I11@' in relatives['@I1@']['siblings']

    def test_root_has_spouse(self, relatives):
        """@I1@ (Rose) has Mark Davis (@I12@) as a spouse."""
        assert '@I1@' in relatives
        assert '@I12@' in relatives['@I1@']['spouses']

    def test_siblings_are_xref_strings(self, relatives):
        """Siblings list must contain plain xref strings, not objects."""
        for xref in relatives['@I1@']['siblings']:
            assert isinstance(xref, str)
            assert xref.startswith('@I')

    def test_spouses_are_xref_strings(self, relatives):
        for xref in relatives['@I1@']['spouses']:
            assert isinstance(xref, str)
            assert xref.startswith('@I')

    def test_father_has_sibling_not_in_tree(self, relatives):
        """@I2@ (James) has Robert Smith (@I13@) as a sibling."""
        assert '@I2@' in relatives
        assert '@I13@' in relatives['@I2@']['siblings']

    def test_spouse_already_in_tree_still_returned(self, relatives):
        """@I2@ (James) spouse is Clara (@I3@) — still included; dedup is JS-side."""
        assert '@I3@' in relatives['@I2@']['spouses']

    def test_person_with_no_relatives_absent(self, relatives):
        """@I10@ (Thomas Jones) has no FAMC and no spouse → not in relatives dict."""
        assert '@I10@' not in relatives

    def test_no_self_in_siblings(self, relatives):
        """The anchor person must not appear in their own sibling list."""
        assert '@I1@' not in relatives['@I1@']['siblings']


# ---------------------------------------------------------------------------
# TestOutput
# ---------------------------------------------------------------------------

class TestOutput:

    def test_html_generated(self, tmp_path, indis, fams):
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        assert Path(out).exists()
        assert Path(out).stat().st_size > 0

    def test_html_contains_root_name(self, tmp_path):
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert 'Rose Smith' in content

    def test_html_contains_ancestor_names(self, tmp_path):
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert 'James Smith' in content
        assert 'Patrick Smith' in content
        assert 'William Brown' in content

    def test_html_contains_years(self, tmp_path):
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert '1960' in content
        assert '2005' in content

    def test_html_is_self_contained(self, tmp_path):
        """No external script/stylesheet src attributes."""
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert 'src="http' not in content
        assert "src='http" not in content

    def test_name_search(self, tmp_path):
        """--person accepts a name substring, not just an xref."""
        out = str(tmp_path / 'out.html')
        result = viz_ancestors(str(FIXTURE), 'Rose', out)
        assert result['root_name'] == 'Rose Smith'

    def test_return_dict_keys(self, tmp_path):
        out = str(tmp_path / 'out.html')
        result = viz_ancestors(str(FIXTURE), '@I1@', out)
        for key in ('root_name', 'ancestor_count', 'generations'):
        	assert key in result

    def test_return_ancestor_count(self, tmp_path):
        out = str(tmp_path / 'out.html')
        result = viz_ancestors(str(FIXTURE), '@I1@', out)
        assert result['ancestor_count'] == 10  # root + 9 ancestors

    def test_return_generations(self, tmp_path):
        out = str(tmp_path / 'out.html')
        result = viz_ancestors(str(FIXTURE), '@I1@', out)
        assert result['generations'] == 4  # gens 0-3

    def test_html_contains_detail_panel(self, tmp_path):
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert 'id="detail-panel"' in content

    def test_html_contains_event_labels(self, tmp_path):
        """EVENT_LABELS dict must be present in the JS for the panel to work."""
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert 'Birth' in content
        assert 'Death' in content
        assert 'Residence' in content

    def test_html_contains_sex_data(self, tmp_path):
        """Sex field must be embedded in PEOPLE JSON."""
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert '"sex": "F"' in content or '"sex":"F"' in content

    def test_html_contains_events_data(self, tmp_path):
        """Events list must be embedded in PEOPLE JSON."""
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert '"events"' in content
        assert 'Greenwich, Connecticut, USA' in content

    def test_html_contains_tree_and_people_json(self, tmp_path):
        """Both TREE and PEOPLE consts must be present in the output."""
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert 'const TREE' in content
        assert 'const PEOPLE' in content

    def test_html_contains_aka_note(self, tmp_path):
        """AKA alias stored as 2 NOTE must appear in the embedded JSON."""
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert 'Rosie Smith' in content

    def test_html_uses_midY_routing(self, tmp_path):
        """Connector routes through midY waypoint — no direct diagonal to child."""
        # JS is now in external viz_render.js file (not inlined in HTML output)
        render_js = Path(__file__).parent.parent / 'js' / 'viz_render.js'
        assert render_js.exists(), 'js/viz_render.js must exist'
        content = render_js.read_text(encoding='utf-8')
        assert 'cy - V_GAP / 2' in content   # midY L-shaped routing present

    def test_html_contains_relatives_json(self, tmp_path):
        """RELATIVES_JSON must be embedded and contain sibling/spouse data."""
        out = str(tmp_path / 'out.html')
        viz_ancestors(str(FIXTURE), '@I1@', out)
        content = Path(out).read_text(encoding='utf-8')
        assert 'const RELATIVES' in content
        assert 'Alice Smith' in content   # Rose's sibling
        assert 'Mark Davis' in content    # Rose's spouse
        assert 'Robert Smith' in content  # James's sibling


# ---------------------------------------------------------------------------
# TestSortEvents
# ---------------------------------------------------------------------------

class TestDateSortKey:
    """_date_sort_key returns (year, month, day, adjust).
    adjust: -1 for BEF (sorts before), +1 for AFT (sorts after), 0 otherwise."""

    def test_full_dmy(self):
        assert _date_sort_key('13 MAR 1942') == (1942, 3, 13, 0)

    def test_month_year(self):
        assert _date_sort_key('MAR 1942') == (1942, 3, 0, 0)

    def test_year_only(self):
        assert _date_sort_key('1942') == (1942, 0, 0, 0)

    def test_none(self):
        assert _date_sort_key(None) == (0, 0, 0, 0)

    def test_empty(self):
        assert _date_sort_key('') == (0, 0, 0, 0)

    def test_abt_qualifier(self):
        assert _date_sort_key('ABT 21 MAR 1942') == (1942, 3, 21, 0)

    def test_bef_qualifier(self):
        # BEF sorts just before the date
        assert _date_sort_key('BEF 1 JAN 1900') == (1900, 1, 1, -1)

    def test_aft_qualifier(self):
        # AFT sorts just after the date
        assert _date_sort_key('AFT DEC 1941') == (1941, 12, 0, 1)

    def test_bet_uses_first_date(self):
        assert _date_sort_key('BET 1 MAY 1942 AND 2 MAY 1942') == (1942, 5, 1, 0)

    def test_bef_sorts_before_same_year(self):
        # BEF 1850 should come before 1850 with no qualifier
        assert _date_sort_key('BEF 1850') < _date_sort_key('1850')

    def test_aft_sorts_after_same_year(self):
        # AFT 1850 should come after 1850 with no qualifier
        assert _date_sort_key('AFT 1850') > _date_sort_key('1850')

    def test_bef_aft_ordering(self):
        # BEF 1850 < 1850 < AFT 1850
        assert _date_sort_key('BEF 1850') < _date_sort_key('1850') < _date_sort_key('AFT 1850')

    def test_ordering(self):
        dates = ['12 MAY 1942', '9 MAY 1942', '1 MAY 1942', 'ABT 21 MAR 1942',
                 '17 MAR 1942', '13 MAR 1942']
        assert sorted(dates, key=_date_sort_key) == [
            '13 MAR 1942', '17 MAR 1942', 'ABT 21 MAR 1942',
            '1 MAY 1942', '9 MAY 1942', '12 MAY 1942',
        ]


class TestSortEvents:

    def _evt(self, tag, date=None, type_=None):
        return {'tag': tag, 'date': date, 'type': type_, 'place': None, 'note': None}

    def test_birt_pinned_first(self):
        events = [
            self._evt('RESI', '1 MAR 1942'),
            self._evt('BIRT', '1 JAN 1926'),
        ]
        result = sort_events(events)
        assert result[0]['tag'] == 'BIRT'

    def test_deat_pinned_last(self):
        events = [
            self._evt('DEAT', '1 JAN 2021'),
            self._evt('RESI', '1 MAR 1942'),
        ]
        result = sort_events(events)
        assert result[-1]['tag'] == 'DEAT'

    def test_buri_pinned_last(self):
        events = [
            self._evt('BURI', '5 JAN 2021'),
            self._evt('RESI', '1 MAR 1942'),
            self._evt('DEAT', '1 JAN 2021'),
        ]
        result = sort_events(events)
        assert result[-1]['tag'] in ('DEAT', 'BURI')
        assert result[-2]['tag'] in ('DEAT', 'BURI')

    def test_chronological_by_full_date(self):
        """Events within 1942 must sort by month and day, not just year."""
        events = [
            self._evt('EVEN', '12 MAY 1942', 'Arrival'),   # Bharatpur
            self._evt('EVEN', '9 MAY 1942',  'Arrival'),   # Bombay
            self._evt('EVEN', '1 MAY 1942',  'Departure'),
            self._evt('EVEN', 'ABT 21 MAR 1942', 'Arrival'),
            self._evt('EVEN', '17 MAR 1942', 'Arrival'),
            self._evt('EVEN', '13 MAR 1942', 'Departure'),
        ]
        result = sort_events(events)
        dates = [e['date'] for e in result]
        assert dates == [
            '13 MAR 1942', '17 MAR 1942', 'ABT 21 MAR 1942',
            '1 MAY 1942', '9 MAY 1942', '12 MAY 1942',
        ]

    def test_no_date_sorts_before_dated(self):
        events = [
            self._evt('RESI', '1 MAR 1942'),
            self._evt('OCCU', None),
        ]
        result = sort_events(events)
        assert result[0]['tag'] == 'OCCU'

    def test_preserves_all_events(self):
        events = [self._evt('EVEN', f'{i} JAN 1942') for i in range(1, 6)]
        assert len(sort_events(events)) == 5
