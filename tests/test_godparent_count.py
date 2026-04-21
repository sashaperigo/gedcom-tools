"""
Unit tests for scan_godparent_count.

TDD: written before implementation.
Tests cover all specified violation cases from the task spec.
"""
import textwrap
from pathlib import Path


from gedcom_linter import scan_godparent_count


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def write_ged(tmp_path, content: str) -> Path:
    p = tmp_path / 'test.ged'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'godparents_sample.ged'


# ===========================================================================
# scan_godparent_count
# ===========================================================================

class TestScanGodparentCount:

    def test_no_godparents_no_violation(self, tmp_path):
        """0 godparents → no violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Test /Person/
            1 SEX M
            0 TRLR
        """)
        result = scan_godparent_count(str(p))
        assert result == []

    def test_one_male_one_female_no_violation(self, tmp_path):
        """1M + 1F godparents → valid, no violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Godfather /One/
            1 SEX M
            0 @I2@ INDI
            1 NAME Godmother /One/
            1 SEX F
            0 @I3@ INDI
            1 NAME Child /Test/
            1 SEX M
            1 ASSO @I1@
            2 RELA Godparent
            1 ASSO @I2@
            2 RELA Godparent
            0 TRLR
        """)
        result = scan_godparent_count(str(p))
        assert result == []

    def test_two_male_godparents_violation(self, tmp_path):
        """2M godparents → violation (>1 of same gender)."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Godfather /One/
            1 SEX M
            0 @I2@ INDI
            1 NAME Godfather /Two/
            1 SEX M
            0 @I3@ INDI
            1 NAME Child /Test/
            1 SEX F
            1 ASSO @I1@
            2 RELA Godparent
            1 ASSO @I2@
            2 RELA Godparent
            0 TRLR
        """)
        result = scan_godparent_count(str(p))
        assert len(result) == 1
        xref, total, m_count, f_count = result[0]
        assert xref == '@I3@'
        assert total == 2
        assert m_count == 2
        assert f_count == 0

    def test_three_total_violation(self, tmp_path):
        """3 total (1M + 1F + 1U) → violation (>2 total)."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Godfather /One/
            1 SEX M
            0 @I2@ INDI
            1 NAME Godmother /One/
            1 SEX F
            0 @I3@ INDI
            1 NAME Extra /Godparent/
            1 SEX U
            0 @I4@ INDI
            1 NAME Child /Test/
            1 SEX M
            1 ASSO @I1@
            2 RELA Godparent
            1 ASSO @I2@
            2 RELA Godparent
            1 ASSO @I3@
            2 RELA Godparent
            0 TRLR
        """)
        result = scan_godparent_count(str(p))
        assert len(result) == 1
        xref, total, m_count, f_count = result[0]
        assert xref == '@I4@'
        assert total == 3
        assert m_count == 1
        assert f_count == 1

    def test_two_female_godparents_violation(self, tmp_path):
        """2F godparents → violation (>1 of same gender)."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Godmother /One/
            1 SEX F
            0 @I2@ INDI
            1 NAME Godmother /Two/
            1 SEX F
            0 @I3@ INDI
            1 NAME Child /Test/
            1 SEX M
            1 ASSO @I1@
            2 RELA Godparent
            1 ASSO @I2@
            2 RELA Godparent
            0 TRLR
        """)
        result = scan_godparent_count(str(p))
        assert len(result) == 1
        xref, total, m_count, f_count = result[0]
        assert xref == '@I3@'
        assert total == 2
        assert m_count == 0
        assert f_count == 2

    def test_unknown_xref_treated_as_u(self, tmp_path):
        """Godparent xref not in sex_map → treated as U (counts toward total only)."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Child /Test/
            1 SEX M
            1 ASSO @I99@
            2 RELA Godparent
            0 TRLR
        """)
        # @I99@ not defined → sex is U → total=1, m=0, f=0 → no violation
        result = scan_godparent_count(str(p))
        assert result == []

    def test_unknown_xref_pushes_total_over_two(self, tmp_path):
        """Two known + one unknown xref = 3 total → violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Godfather /One/
            1 SEX M
            0 @I2@ INDI
            1 NAME Godmother /One/
            1 SEX F
            0 @I3@ INDI
            1 NAME Child /Test/
            1 SEX M
            1 ASSO @I1@
            2 RELA Godparent
            1 ASSO @I2@
            2 RELA Godparent
            1 ASSO @I99@
            2 RELA Godparent
            0 TRLR
        """)
        result = scan_godparent_count(str(p))
        assert len(result) == 1
        xref, total, m_count, f_count = result[0]
        assert xref == '@I3@'
        assert total == 3

    def test_rela_case_insensitive(self, tmp_path):
        """RELA value matching is case-insensitive."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Godfather /One/
            1 SEX M
            0 @I2@ INDI
            1 NAME Godfather /Two/
            1 SEX M
            0 @I3@ INDI
            1 NAME Child /Test/
            1 SEX F
            1 ASSO @I1@
            2 RELA godparent
            1 ASSO @I2@
            2 RELA GODPARENT
            0 TRLR
        """)
        result = scan_godparent_count(str(p))
        assert len(result) == 1

    def test_non_godparent_asso_ignored(self, tmp_path):
        """ASSO with RELA other than Godparent should not count."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Witness /One/
            1 SEX M
            0 @I2@ INDI
            1 NAME Witness /Two/
            1 SEX M
            0 @I3@ INDI
            1 NAME Child /Test/
            1 SEX M
            1 ASSO @I1@
            2 RELA Witness
            1 ASSO @I2@
            2 RELA Witness
            0 TRLR
        """)
        result = scan_godparent_count(str(p))
        assert result == []

    def test_fixture_file_violations(self):
        """Fixture file has known violations: @I8@, @I9@, @I10@."""
        result = scan_godparent_count(str(FIXTURE_PATH))
        violating_xrefs = {r[0] for r in result}
        # @I7@: 1M + 1F → valid
        assert '@I7@' not in violating_xrefs
        # @I8@: 2M → violation
        assert '@I8@' in violating_xrefs
        # @I9@: 3 total (1M + 1F + 1U) → violation
        assert '@I9@' in violating_xrefs
        # @I10@: 2F → violation
        assert '@I10@' in violating_xrefs
        # @I6@: 0 godparents → no violation
        assert '@I6@' not in violating_xrefs
        # @I11@: 1 unknown → no violation
        assert '@I11@' not in violating_xrefs
