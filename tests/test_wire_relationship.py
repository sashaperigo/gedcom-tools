"""
Tests for _wire_relationship and _prune_empty_fam helpers.

Covers:
  - _wire_relationship with parent_of when other parent shares existing FAM
  - _prune_empty_fam for removing empty FAM blocks and backlinks
"""

import os
from pathlib import Path

import pytest

# serve_viz.py sys.exit()s at import if GED_FILE is not set; point at the
# existing fixture so the module loads cleanly.
_FIXTURE_GED = str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged')
os.environ.setdefault('GED_FILE', _FIXTURE_GED)

from serve_viz import (          # noqa: E402  (after env var is set)
    _wire_relationship,
)


# ---------------------------------------------------------------------------
# TestWireRelationshipParentOfSharedFam
# ---------------------------------------------------------------------------

class TestWireRelationshipParentOfSharedFam:
    """
    Scenario: Jr. is in F3429 with only Sr. (M) as HUSB. Rosa (F) and Sr.
    already share F1017. Adding Rosa as `parent_of` Jr. should redirect Jr.
    to F1017 instead of adding Rosa to F3429.
    """

    def _base_lines(self):
        """Return the base GEDCOM lines for the shared-FAM scenario."""
        return [
            "0 HEAD",
            "0 @ISR@ INDI",
            "1 NAME Marius /Sr/",
            "1 SEX M",
            "1 FAMS @F1017@",
            "1 FAMS @F3429@",
            "0 @IROSA@ INDI",
            "1 NAME Rosa /Morari/",
            "1 SEX F",
            "1 FAMS @F1017@",
            "0 @IJR@ INDI",
            "1 NAME Marius /Jr/",
            "1 SEX M",
            "1 FAMC @F3429@",
            "0 @F1017@ FAM",
            "1 HUSB @ISR@",
            "1 WIFE @IROSA@",
            "0 @F3429@ FAM",
            "1 HUSB @ISR@",
            "1 CHIL @IJR@",
            "0 TRLR",
        ]

    def test_adds_child_to_existing_shared_fam_not_new_fam(self):
        """After adding Rosa as parent_of Jr., Jr.'s FAMC should be F1017."""
        lines = self._base_lines()

        # Add Rosa as parent_of Jr.
        new_lines, error = _wire_relationship(
            lines,
            new_xref='@IROSA@',
            rel_type='parent_of',
            rel_xref='@IJR@',
            other_parent_xref=None,
            sex='F'
        )

        assert error is None, f"Expected no error, but got: {error}"

        # Find Jr.'s FAMC line
        jr_famc = None
        in_jr_block = False
        for line in new_lines:
            if line.startswith('0 @IJR@ INDI'):
                in_jr_block = True
            elif line.startswith('0 '):
                in_jr_block = False
            elif in_jr_block and line.startswith('1 FAMC'):
                jr_famc = line.split()[-1]
                break

        assert jr_famc == '@F1017@', f"Expected Jr.'s FAMC to be @F1017@, got {jr_famc}"

    def test_f1017_gains_chil(self):
        """F1017 should contain CHIL @IJR@ after the operation."""
        lines = self._base_lines()

        new_lines, error = _wire_relationship(
            lines,
            new_xref='@IROSA@',
            rel_type='parent_of',
            rel_xref='@IJR@',
            other_parent_xref=None,
            sex='F'
        )

        assert error is None, f"Expected no error, but got: {error}"

        # Find F1017 block and check for CHIL @IJR@
        f1017_block_found = False
        jr_child_found = False
        in_f1017 = False

        for line in new_lines:
            if line.startswith('0 @F1017@ FAM'):
                in_f1017 = True
                f1017_block_found = True
            elif line.startswith('0 '):
                in_f1017 = False
            elif in_f1017 and line.startswith('1 CHIL @IJR@'):
                jr_child_found = True

        assert f1017_block_found, "F1017 block not found"
        assert jr_child_found, "Jr. not added to F1017 as CHIL"

    def test_rosa_not_added_to_duplicate_fam(self):
        """Rosa should NOT gain FAMS @F3429@."""
        lines = self._base_lines()

        new_lines, error = _wire_relationship(
            lines,
            new_xref='@IROSA@',
            rel_type='parent_of',
            rel_xref='@IJR@',
            other_parent_xref=None,
            sex='F'
        )

        assert error is None, f"Expected no error, but got: {error}"

        # Find Rosa's INDI block and check FAMS lines
        rosa_fams = []
        in_rosa_block = False

        for line in new_lines:
            if line.startswith('0 @IROSA@ INDI'):
                in_rosa_block = True
            elif line.startswith('0 '):
                in_rosa_block = False
            elif in_rosa_block and line.startswith('1 FAMS'):
                fam_xref = line.split()[-1]
                rosa_fams.append(fam_xref)

        assert '@F3429@' not in rosa_fams, \
            f"Rosa should not have FAMS @F3429@, but her FAMs are: {rosa_fams}"

    def test_f3429_pruned_after_child_moved(self):
        """F3429 should be removed entirely (pruned because it's now childless)."""
        lines = self._base_lines()

        new_lines, error = _wire_relationship(
            lines,
            new_xref='@IROSA@',
            rel_type='parent_of',
            rel_xref='@IJR@',
            other_parent_xref=None,
            sex='F'
        )

        assert error is None, f"Expected no error, but got: {error}"

        # Check that F3429 block is completely gone
        f3429_found = False
        for line in new_lines:
            if line.startswith('0 @F3429@ FAM'):
                f3429_found = True
                break

        assert not f3429_found, "F3429 should be pruned but was found in output"


# ---------------------------------------------------------------------------
# TestPruneEmptyFam
# ---------------------------------------------------------------------------

class TestPruneEmptyFam:
    """Tests for _prune_empty_fam(lines, fam_xref) -> new_lines."""

    def test_removes_fam_block_with_no_chil(self):
        """_prune_empty_fam should remove a FAM block that has no CHIL entries."""
        lines = [
            "0 HEAD",
            "0 @ISR@ INDI",
            "1 NAME Marius /Sr/",
            "1 SEX M",
            "1 FAMS @F1017@",
            "1 FAMS @F3429@",
            "0 @IROSA@ INDI",
            "1 NAME Rosa /Morari/",
            "1 SEX F",
            "1 FAMS @F1017@",
            "0 @IJR@ INDI",
            "1 NAME Marius /Jr/",
            "1 SEX M",
            "1 FAMC @F1017@",
            "0 @F1017@ FAM",
            "1 HUSB @ISR@",
            "1 WIFE @IROSA@",
            "1 CHIL @IJR@",
            "0 @F3429@ FAM",
            "1 HUSB @ISR@",
            "0 TRLR",
        ]

        from serve_viz import _prune_empty_fam

        new_lines = _prune_empty_fam(lines, '@F3429@')

        # F3429 should be completely removed
        f3429_found = False
        for line in new_lines:
            if '@F3429@' in line:
                f3429_found = True
                break

        assert not f3429_found, "F3429 should be removed but was found in output"

    def test_removes_backlink_from_husb_wife(self):
        """_prune_empty_fam should remove FAMS backlinks from HUSB/WIFE individuals."""
        lines = [
            "0 HEAD",
            "0 @ISR@ INDI",
            "1 NAME Marius /Sr/",
            "1 SEX M",
            "1 FAMS @F1017@",
            "1 FAMS @F3429@",
            "0 @IROSA@ INDI",
            "1 NAME Rosa /Morari/",
            "1 SEX F",
            "1 FAMS @F1017@",
            "0 @IJR@ INDI",
            "1 NAME Marius /Jr/",
            "1 SEX M",
            "1 FAMC @F1017@",
            "0 @F1017@ FAM",
            "1 HUSB @ISR@",
            "1 WIFE @IROSA@",
            "1 CHIL @IJR@",
            "0 @F3429@ FAM",
            "1 HUSB @ISR@",
            "0 TRLR",
        ]

        from serve_viz import _prune_empty_fam

        new_lines = _prune_empty_fam(lines, '@F3429@')

        # Sr. should have only one FAMS: @F1017@
        sr_fams = []
        in_sr_block = False

        for line in new_lines:
            if line.startswith('0 @ISR@ INDI'):
                in_sr_block = True
            elif line.startswith('0 '):
                in_sr_block = False
            elif in_sr_block and line.startswith('1 FAMS'):
                fam_xref = line.split()[-1]
                sr_fams.append(fam_xref)

        assert sr_fams == ['@F1017@'], \
            f"Sr. should have only FAMS @F1017@, but has: {sr_fams}"

    def test_does_not_remove_fam_with_chil(self):
        """_prune_empty_fam should NOT remove a FAM that has CHIL entries."""
        lines = [
            "0 HEAD",
            "0 @ISR@ INDI",
            "1 NAME Marius /Sr/",
            "1 SEX M",
            "1 FAMS @F3429@",
            "0 @IJR@ INDI",
            "1 NAME Marius /Jr/",
            "1 SEX M",
            "1 FAMC @F3429@",
            "0 @F3429@ FAM",
            "1 HUSB @ISR@",
            "1 CHIL @IJR@",
            "0 TRLR",
        ]

        from serve_viz import _prune_empty_fam

        new_lines = _prune_empty_fam(lines, '@F3429@')

        # F3429 should still be there since it has a CHIL
        f3429_found = False
        for line in new_lines:
            if line.startswith('0 @F3429@ FAM'):
                f3429_found = True
                break

        assert f3429_found, "F3429 should not be pruned since it has CHIL"

    def test_prune_fam_with_both_husb_and_wife(self):
        """_prune_empty_fam should remove backlinks from both HUSB and WIFE."""
        lines = [
            "0 HEAD",
            "0 @ISR@ INDI",
            "1 NAME Marius /Sr/",
            "1 SEX M",
            "1 FAMS @F1017@",
            "1 FAMS @F3429@",
            "0 @IROSA@ INDI",
            "1 NAME Rosa /Morari/",
            "1 SEX F",
            "1 FAMS @F1017@",
            "1 FAMS @F3429@",
            "0 @IJR@ INDI",
            "1 NAME Marius /Jr/",
            "1 SEX M",
            "1 FAMC @F1017@",
            "0 @F1017@ FAM",
            "1 HUSB @ISR@",
            "1 WIFE @IROSA@",
            "1 CHIL @IJR@",
            "0 @F3429@ FAM",
            "1 HUSB @ISR@",
            "1 WIFE @IROSA@",
            "0 TRLR",
        ]

        from serve_viz import _prune_empty_fam

        new_lines = _prune_empty_fam(lines, '@F3429@')

        # Sr. should have only @F1017@
        sr_fams = []
        in_sr_block = False
        for line in new_lines:
            if line.startswith('0 @ISR@ INDI'):
                in_sr_block = True
            elif line.startswith('0 '):
                in_sr_block = False
            elif in_sr_block and line.startswith('1 FAMS'):
                sr_fams.append(line.split()[-1])

        # Rosa should have only @F1017@
        rosa_fams = []
        in_rosa_block = False
        for line in new_lines:
            if line.startswith('0 @IROSA@ INDI'):
                in_rosa_block = True
            elif line.startswith('0 '):
                in_rosa_block = False
            elif in_rosa_block and line.startswith('1 FAMS'):
                rosa_fams.append(line.split()[-1])

        assert sr_fams == ['@F1017@'], \
            f"Sr. should have only FAMS @F1017@, but has: {sr_fams}"
        assert rosa_fams == ['@F1017@'], \
            f"Rosa should have only FAMS @F1017@, but has: {rosa_fams}"

        # F3429 should be gone
        f3429_found = False
        for line in new_lines:
            if '@F3429@' in line:
                f3429_found = True
                break
        assert not f3429_found, "F3429 should be pruned but was found"
