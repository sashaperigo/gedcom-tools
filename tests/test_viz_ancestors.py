"""
Tests for viz_ancestors.py

Covers:
  - GEDCOM parsing: names, birth/death years, FAMC links
  - Parent lookup via FAM records
  - Ahnentafel ancestor tree building
  - HTML output generation
"""

from pathlib import Path

import pytest

from viz_ancestors import parse_gedcom, get_parents, build_ancestor_json, viz_ancestors

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
        assert len(indis) == 10  # @I1@ through @I10@

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
        assert len(fams) == 5  # @F1@ through @F4@, @F6@

    def test_fam_husb_wife(self, fams):
        assert fams['@F1@']['husb'] == '@I2@'
        assert fams['@F1@']['wife'] == '@I3@'

    def test_fam_missing_wife(self, fams):
        """@F6@ has no WIFE."""
        assert fams['@F6@']['husb'] == '@I10@'
        assert fams['@F6@']['wife'] is None


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
# TestAncestorTree
# ---------------------------------------------------------------------------

class TestAncestorTree:

    @pytest.fixture(scope='class')
    def tree(self, indis, fams):
        return build_ancestor_json('@I1@', indis, fams)

    def test_root_has_ahnentafel_1(self, tree):
        assert 1 in tree
        assert tree[1]['name'] == 'Rose Smith'

    def test_father_is_2(self, tree):
        assert 2 in tree
        assert tree[2]['name'] == 'James Smith'

    def test_mother_is_3(self, tree):
        assert 3 in tree
        assert tree[3]['name'] == 'Clara Jones'

    def test_paternal_grandfather_is_4(self, tree):
        assert 4 in tree
        assert tree[4]['name'] == 'Patrick Smith'

    def test_paternal_grandmother_is_5(self, tree):
        assert 5 in tree
        assert tree[5]['name'] == "Mary O'Brien"

    def test_maternal_grandfather_is_6(self, tree):
        assert 6 in tree
        assert tree[6]['name'] == 'John Jones'

    def test_maternal_grandmother_is_7(self, tree):
        assert 7 in tree
        assert tree[7]['name'] == 'Jane Brown'

    def test_missing_ancestor_absent(self, tree):
        """Patrick Smith (@I4@) has no FAMC → his parents (keys 8,9) absent."""
        assert 8 not in tree
        assert 9 not in tree

    def test_great_grandparents_via_maternal_grandmother(self, tree):
        """Jane Brown's parents → keys 14 (father) and 15 (mother)."""
        assert 14 in tree
        assert tree[14]['name'] == 'William Brown'
        assert 15 in tree
        assert tree[15]['name'] == 'Helen Taylor'

    def test_missing_half_branch(self, tree):
        """@F6@ has no WIFE → maternal grandfather's mother (key 13) absent."""
        assert 12 in tree   # Thomas Jones is paternal side of @I6@
        assert 13 not in tree

    def test_ancestor_count(self, tree):
        # Root(1) + parents(2) + grandparents(4) + great-gp partially:
        # William(14), Helen(15), Thomas(12) = 3 great-grandparents known
        # Total: 1+2+4+3 = 10
        assert len(tree) == 10

    def test_tree_node_has_required_keys(self, tree):
        node = tree[1]
        for key in ('name', 'birth_year', 'death_year'):
            assert key in node


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
