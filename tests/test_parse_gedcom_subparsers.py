"""
Unit tests for the parse_gedcom sub-parsers extracted from the monolithic loop.

Each sub-parser handles one GEDCOM record context:
  _parse_indi_line  — lines inside an 0 @X@ INDI block
  _parse_fam_line   — lines inside an 0 @X@ FAM block
  _parse_sour_line  — lines inside an 0 @X@ SOUR block

Tests drive the API: sub-parsers receive (state, lvl, tag, val, raw_val, record)
and mutate record + state in place.
"""


from viz_ancestors import _parse_indi_line, _parse_fam_line, _parse_sour_line


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blank_indi():
    return {
        'name': None, 'birth_year': None, 'death_year': None,
        'famc': None, 'fams': [], 'sex': None, 'events': [], 'notes': [],
        'source_xrefs': [], 'source_urls': {}, 'source_citations': [], 'asso': [],
    }


def _blank_fam():
    return {'husb': None, 'wife': None, 'chil': []}


def _blank_sour():
    return {'titl': None, 'auth': None, 'publ': None, 'repo': None, 'note': None}


def _indi_state():
    return {
        'current_evt': None,
        'current_note': None,
        'current_sour_xref': None,
        'current_person_cite': None,
        'current_cite_field': None,
        'current_asso': None,
        'secondary_name_n': 0,
    }


def _fam_state():
    return {'current_evt': None}


# ---------------------------------------------------------------------------
# _parse_indi_line
# ---------------------------------------------------------------------------

class TestParseIndiLineName:
    def test_first_name_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'NAME', 'John /Smith/', 'John /Smith/', rec)
        assert rec['name'] == 'John Smith'

    def test_slashes_stripped_from_name(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'NAME', '/Smith/', '/Smith/', rec)
        assert rec['name'] == 'Smith'

    def test_second_name_becomes_aka_event(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'NAME', 'John /Smith/', 'John /Smith/', rec)
        _parse_indi_line(st, 1, 'NAME', 'Johnny /Smith/', 'Johnny /Smith/', rec)
        aka = [e for e in rec['events'] if e.get('type') == 'AKA']
        assert len(aka) == 1
        assert aka[0]['note'] == 'Johnny Smith'

    def test_primary_name_unchanged_after_second(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'NAME', 'John /Smith/', 'John /Smith/', rec)
        _parse_indi_line(st, 1, 'NAME', 'Johnny /Smith/', 'Johnny /Smith/', rec)
        assert rec['name'] == 'John Smith'


class TestParseIndiLineSex:
    def test_sex_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'SEX', 'F', 'F', rec)
        assert rec['sex'] == 'F'


class TestParseIndiLineEvents:
    def test_birt_event_created(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'BIRT', '', '', rec)
        assert len(rec['events']) == 1
        assert rec['events'][0]['tag'] == 'BIRT'

    def test_event_date_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'BIRT', '', '', rec)
        _parse_indi_line(st, 2, 'DATE', '12 MAR 1900', '12 MAR 1900', rec)
        assert rec['events'][0]['date'] == '12 MAR 1900'

    def test_birt_date_sets_birth_year(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'BIRT', '', '', rec)
        _parse_indi_line(st, 2, 'DATE', '12 MAR 1900', '12 MAR 1900', rec)
        assert rec['birth_year'] == '1900'

    def test_deat_date_sets_death_year(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'DEAT', '', '', rec)
        _parse_indi_line(st, 2, 'DATE', 'ABT 1975', 'ABT 1975', rec)
        assert rec['death_year'] == '1975'

    def test_event_place_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'BIRT', '', '', rec)
        _parse_indi_line(st, 2, 'PLAC', 'London, England', 'London, England', rec)
        assert rec['events'][0]['place'] == 'London, England'

    def test_event_type_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'EVEN', '', '', rec)
        _parse_indi_line(st, 2, 'TYPE', 'Baptism', 'Baptism', rec)
        assert rec['events'][0]['type'] == 'Baptism'

    def test_occu_inline_value_is_type(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'OCCU', 'Consul', 'Consul', rec)
        assert rec['events'][0]['type'] == 'Consul'

    def test_event_citation_added(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'BIRT', '', '', rec)
        _parse_indi_line(st, 2, 'SOUR', '@S1@', '@S1@', rec)
        assert rec['events'][0]['citations'] == [{'sour_xref': '@S1@', 'page': None, 'text': None, 'note': None}]

    def test_event_citation_page_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'BIRT', '', '', rec)
        _parse_indi_line(st, 2, 'SOUR', '@S1@', '@S1@', rec)
        _parse_indi_line(st, 3, 'PAGE', 'p. 42', 'p. 42', rec)
        assert rec['events'][0]['citations'][0]['page'] == 'p. 42'


class TestParseIndiLineFamLinks:
    def test_famc_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'FAMC', '@F1@', '@F1@', rec)
        assert rec['famc'] == '@F1@'

    def test_second_famc_ignored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'FAMC', '@F1@', '@F1@', rec)
        _parse_indi_line(st, 1, 'FAMC', '@F2@', '@F2@', rec)
        assert rec['famc'] == '@F1@'

    def test_fams_appended(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'FAMS', '@F1@', '@F1@', rec)
        _parse_indi_line(st, 1, 'FAMS', '@F2@', '@F2@', rec)
        assert rec['fams'] == ['@F1@', '@F2@']


class TestParseIndiLineNotes:
    def test_inline_note_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'NOTE', 'Hello world', 'Hello world', rec)
        assert rec['notes'][0]['text'] == 'Hello world'
        assert rec['notes'][0]['shared'] is False

    def test_note_cont_appended(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'NOTE', 'Line one', 'Line one', rec)
        _parse_indi_line(st, 2, 'CONT', 'Line two', 'Line two', rec)
        assert rec['notes'][0]['text'] == 'Line one\nLine two'


class TestParseIndiLineAsso:
    def test_asso_created(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'ASSO', '@I5@', '@I5@', rec)
        assert rec['asso'] == [{'xref': '@I5@', 'rela': None}]

    def test_asso_rela_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'ASSO', '@I5@', '@I5@', rec)
        _parse_indi_line(st, 2, 'RELA', 'Godparent', 'Godparent', rec)
        assert rec['asso'][0]['rela'] == 'Godparent'


class TestParseIndiLinePersonCitation:
    def test_person_sour_citation_added(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'SOUR', '@S1@', '@S1@', rec)
        assert rec['source_xrefs'] == ['@S1@']
        assert len(rec['source_citations']) == 1
        assert rec['source_citations'][0]['sour_xref'] == '@S1@'

    def test_person_sour_page_stored(self):
        rec = _blank_indi()
        st = _indi_state()
        _parse_indi_line(st, 1, 'SOUR', '@S1@', '@S1@', rec)
        _parse_indi_line(st, 2, 'PAGE', 'p. 7', 'p. 7', rec)
        assert rec['source_citations'][0]['page'] == 'p. 7'


# ---------------------------------------------------------------------------
# _parse_fam_line
# ---------------------------------------------------------------------------

class TestParseFamLine:
    def test_husb_stored(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'HUSB', '@I1@', '@I1@', rec)
        assert rec['husb'] == '@I1@'

    def test_wife_stored(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'WIFE', '@I2@', '@I2@', rec)
        assert rec['wife'] == '@I2@'

    def test_chil_appended(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'CHIL', '@I3@', '@I3@', rec)
        _parse_fam_line(st, 1, 'CHIL', '@I4@', '@I4@', rec)
        assert rec['chil'] == ['@I3@', '@I4@']

    def test_marr_event_created(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'MARR', '', '', rec)
        assert 'marrs' in rec
        assert len(rec['marrs']) == 1
        assert rec['marrs'][0]['tag'] == 'MARR'

    def test_marr_date_stored(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'MARR', '', '', rec)
        _parse_fam_line(st, 2, 'DATE', '15 JUN 1950', '15 JUN 1950', rec)
        assert rec['marrs'][0]['date'] == '15 JUN 1950'

    def test_marr_place_stored(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'MARR', '', '', rec)
        _parse_fam_line(st, 2, 'PLAC', 'Athens, Greece', 'Athens, Greece', rec)
        assert rec['marrs'][0]['place'] == 'Athens, Greece'

    def test_div_event_created(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'DIV', '', '', rec)
        assert 'divs' in rec
        assert rec['divs'][0]['tag'] == 'DIV'

    def test_marr_citation_added(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'MARR', '', '', rec)
        _parse_fam_line(st, 2, 'SOUR', '@S2@', '@S2@', rec)
        assert rec['marrs'][0]['citations'] == [{'sour_xref': '@S2@', 'page': None, 'text': None, 'note': None}]

    def test_marr_citation_page_stored(self):
        rec = _blank_fam()
        st = _fam_state()
        _parse_fam_line(st, 1, 'MARR', '', '', rec)
        _parse_fam_line(st, 2, 'SOUR', '@S2@', '@S2@', rec)
        _parse_fam_line(st, 3, 'PAGE', 'p. 12', 'p. 12', rec)
        assert rec['marrs'][0]['citations'][0]['page'] == 'p. 12'


# ---------------------------------------------------------------------------
# _parse_sour_line
# ---------------------------------------------------------------------------

class TestParseSourLine:
    def test_titl_stored(self):
        rec = _blank_sour()
        _parse_sour_line({}, 1, 'TITL', 'Census 1900', 'Census 1900', rec)
        assert rec['titl'] == 'Census 1900'

    def test_auth_stored(self):
        rec = _blank_sour()
        _parse_sour_line({}, 1, 'AUTH', 'National Archives', 'National Archives', rec)
        assert rec['auth'] == 'National Archives'

    def test_publ_stored(self):
        rec = _blank_sour()
        _parse_sour_line({}, 1, 'PUBL', 'Washington DC', 'Washington DC', rec)
        assert rec['publ'] == 'Washington DC'

    def test_note_stored(self):
        rec = _blank_sour()
        _parse_sour_line({}, 1, 'NOTE', 'See page 42', 'See page 42', rec)
        assert rec['note'] == 'See page 42'

    def test_repo_stored(self):
        rec = _blank_sour()
        _parse_sour_line({}, 1, 'REPO', '@R1@', '@R1@', rec)
        assert rec['repo'] == '@R1@'

    def test_unknown_tag_ignored(self):
        rec = _blank_sour()
        _parse_sour_line({}, 1, 'CHAN', '2024-01-01', '2024-01-01', rec)
        assert rec == _blank_sour()


class TestParseSourLineCont:
    def test_ged_val_decodes_double_at_in_titl(self):
        rec = _blank_sour()
        st = {}
        _parse_sour_line(st, 1, 'TITL', 'Family@@Records', 'Family@@Records', rec)
        assert rec['titl'] == 'Family@Records'

    def test_ged_val_decodes_html_entity_in_auth(self):
        rec = _blank_sour()
        st = {}
        _parse_sour_line(st, 1, 'AUTH', 'John &amp; Jane', 'John &amp; Jane', rec)
        assert rec['auth'] == 'John & Jane'

    def test_cont_appends_newline_to_note(self):
        rec = _blank_sour()
        st = {}
        _parse_sour_line(st, 1, 'NOTE', 'First line', 'First line', rec)
        _parse_sour_line(st, 2, 'CONT', 'Second line', 'Second line', rec)
        assert rec['note'] == 'First line\nSecond line'

    def test_conc_appends_without_newline(self):
        rec = _blank_sour()
        st = {}
        _parse_sour_line(st, 1, 'TITL', 'Part one', 'Part one', rec)
        _parse_sour_line(st, 2, 'CONC', ' part two', ' part two', rec)
        assert rec['titl'] == 'Part one part two'

    def test_conc_uses_raw_val_for_leading_space(self):
        rec = _blank_sour()
        st = {}
        _parse_sour_line(st, 1, 'TITL', 'Word', 'Word', rec)
        _parse_sour_line(st, 2, 'CONC', 'two', ' two', rec)  # raw has leading space
        assert rec['titl'] == 'Word two'

    def test_unknown_lvl1_tag_clears_current_field(self):
        rec = _blank_sour()
        st = {}
        _parse_sour_line(st, 1, 'NOTE', 'line one', 'line one', rec)
        _parse_sour_line(st, 1, 'CHAN', '2024', '2024', rec)
        _parse_sour_line(st, 2, 'CONT', 'ignored', 'ignored', rec)
        assert rec['note'] == 'line one'

    def test_cont_on_titl(self):
        rec = _blank_sour()
        st = {}
        _parse_sour_line(st, 1, 'TITL', 'First', 'First', rec)
        _parse_sour_line(st, 2, 'CONT', 'Second', 'Second', rec)
        assert rec['titl'] == 'First\nSecond'
