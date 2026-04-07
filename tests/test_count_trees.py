"""
Tests for count_trees.py

Covers connected-component counting on the family graph:
  - Multiple disconnected trees of varying sizes
  - Isolated individuals (no FAM membership)
  - FAM with a single member
  - Single fully-connected tree
  - All isolated (no FAMs)
  - Empty file
"""

from pathlib import Path

import pytest

from count_trees import count_trees

FIXTURE = Path(__file__).parent / 'fixtures' / 'trees_sample.ged'


# ---------------------------------------------------------------------------
# Fixture sanity checks
# ---------------------------------------------------------------------------

class TestFixtureContents:

    def test_fixture_exists(self):
        assert FIXTURE.exists()

    def test_fixture_has_multiple_indis(self):
        content = FIXTURE.read_text(encoding='utf-8')
        assert content.count('@ INDI') >= 4

    def test_fixture_has_multiple_fams(self):
        content = FIXTURE.read_text(encoding='utf-8')
        assert content.count('@ FAM') >= 2

    def test_fixture_has_isolated_individual(self):
        """At least one INDI must have no FAMS or FAMC."""
        lines = FIXTURE.read_text(encoding='utf-8').splitlines()
        import re
        in_indi = False
        has_fam_link = False
        isolated = False
        for line in lines:
            if re.match(r'^0 @.*@ INDI', line):
                if in_indi and not has_fam_link:
                    isolated = True
                in_indi = True
                has_fam_link = False
            elif re.match(r'^0 ', line):
                if in_indi and not has_fam_link:
                    isolated = True
                in_indi = False
            elif in_indi and re.match(r'^1 (FAMS|FAMC)', line):
                has_fam_link = True
        assert isolated, 'Fixture has no isolated INDI (one with no FAMS/FAMC)'

    def test_fixture_has_single_member_fam(self):
        """@F4@ has only a HUSB and no WIFE or CHIL."""
        content = FIXTURE.read_text(encoding='utf-8')
        assert '@F4@ FAM' in content


# ---------------------------------------------------------------------------
# Core counting — fixture
# ---------------------------------------------------------------------------

class TestCounting:

    def test_tree_count(self):
        # Tree A: @I1@-@I2@-@I3@-@I4@ (4 people via F1+F2)
        # Tree B: @I5@-@I6@ (2 people via F3)
        # Tree C: @I7@ (isolated)
        # Tree D: @I8@ (isolated)
        # Tree E: @I9@ (single-member FAM F4 — still just 1 person)
        result = count_trees(str(FIXTURE))
        assert result['tree_count'] == 5

    def test_sizes_sorted_descending(self):
        result = count_trees(str(FIXTURE))
        sizes = result['trees']
        assert sizes == sorted(sizes, reverse=True)

    def test_largest_tree_size(self):
        result = count_trees(str(FIXTURE))
        assert result['trees'][0] == 4

    def test_small_trees(self):
        result = count_trees(str(FIXTURE))
        assert result['trees'][1] == 2
        assert result['trees'][2] == 1
        assert result['trees'][3] == 1
        assert result['trees'][4] == 1

    def test_total_individuals(self):
        result = count_trees(str(FIXTURE))
        assert result['total_individuals'] == 9

    def test_sizes_sum_equals_total(self):
        result = count_trees(str(FIXTURE))
        assert sum(result['trees']) == result['total_individuals']

    def test_tree_count_equals_len_trees(self):
        result = count_trees(str(FIXTURE))
        assert result['tree_count'] == len(result['trees'])


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_single_tree(self, tmp_path):
        """All individuals connected → 1 tree."""
        ged = tmp_path / 'single.ged'
        ged.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /A/\n'
            '0 @I2@ INDI\n1 NAME Bob /B/\n'
            '0 @I3@ INDI\n1 NAME Carol /C/\n'
            '0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = count_trees(str(ged))
        assert result['tree_count'] == 1
        assert result['trees'] == [3]
        assert result['total_individuals'] == 3

    def test_all_isolated(self, tmp_path):
        """N individuals with no FAMs → N trees of size 1."""
        ged = tmp_path / 'isolated.ged'
        ged.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /A/\n'
            '0 @I2@ INDI\n1 NAME Bob /B/\n'
            '0 @I3@ INDI\n1 NAME Carol /C/\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = count_trees(str(ged))
        assert result['tree_count'] == 3
        assert result['trees'] == [1, 1, 1]
        assert result['total_individuals'] == 3

    def test_fam_with_one_member(self, tmp_path):
        """A FAM with only one member counts that person as their own tree."""
        ged = tmp_path / 'single_fam.ged'
        ged.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /A/\n'
            '0 @I2@ INDI\n1 NAME Bob /B/\n'
            '0 @F1@ FAM\n1 HUSB @I1@\n'  # only one member
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = count_trees(str(ged))
        assert result['tree_count'] == 2
        assert result['total_individuals'] == 2

    def test_empty_file(self, tmp_path):
        """File with no INDIs → 0 trees."""
        ged = tmp_path / 'empty.ged'
        ged.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n0 TRLR\n',
            encoding='utf-8',
        )
        result = count_trees(str(ged))
        assert result['tree_count'] == 0
        assert result['trees'] == []
        assert result['total_individuals'] == 0

    def test_two_fams_bridging_groups(self, tmp_path):
        """Two initially separate groups joined by a shared individual."""
        ged = tmp_path / 'bridge.ged'
        ged.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME A /A/\n'
            '0 @I2@ INDI\n1 NAME B /B/\n'
            '0 @I3@ INDI\n1 NAME C /C/\n'  # bridge: child of F1, parent in F2
            '0 @I4@ INDI\n1 NAME D /D/\n'
            '0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n1 CHIL @I3@\n'
            '0 @F2@ FAM\n1 HUSB @I3@\n1 WIFE @I4@\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = count_trees(str(ged))
        assert result['tree_count'] == 1
        assert result['trees'] == [4]


# ---------------------------------------------------------------------------
# Return value contract
# ---------------------------------------------------------------------------

class TestReturnValues:

    def test_keys_present(self):
        result = count_trees(str(FIXTURE))
        for key in ('tree_count', 'trees', 'total_individuals'):
            assert key in result

    def test_trees_is_list_of_ints(self):
        result = count_trees(str(FIXTURE))
        assert isinstance(result['trees'], list)
        assert all(isinstance(x, int) for x in result['trees'])

    def test_tree_count_is_int(self):
        result = count_trees(str(FIXTURE))
        assert isinstance(result['tree_count'], int)
