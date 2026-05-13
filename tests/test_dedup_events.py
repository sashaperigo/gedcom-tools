"""Tests for scan_duplicate_events / fix_duplicate_events in gedcom_linter."""
import textwrap
from pathlib import Path

from gedcom_linter import (
    _dup_date_compatible,
    _dup_get_fields,
    _dup_get_sour_blocks,
    _dup_is_subset,
    scan_duplicate_events,
    fix_duplicate_events,
)


def write_ged(tmp_path, content: str) -> Path:
    p = tmp_path / 'test.ged'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


# ---------------------------------------------------------------------------
# _dup_date_compatible
# ---------------------------------------------------------------------------

class TestDupDateCompatible:
    def test_none_victim_always_compatible(self):
        assert _dup_date_compatible(None, '15 JAN 1920') is True
        assert _dup_date_compatible(None, None) is True

    def test_exact_match_compatible(self):
        assert _dup_date_compatible('15 JAN 1920', '15 JAN 1920') is True

    def test_year_only_subset_of_full_same_year(self):
        assert _dup_date_compatible('1920', '15 JAN 1920') is True

    def test_year_only_different_year_conflict(self):
        assert _dup_date_compatible('1919', '15 JAN 1920') is False

    def test_two_different_full_dates_conflict(self):
        assert _dup_date_compatible('1 JAN 1920', '2 JAN 1920') is False

    def test_victim_has_date_survivor_does_not_conflict(self):
        assert _dup_date_compatible('1920', None) is False

    def test_both_year_only_match(self):
        assert _dup_date_compatible('1920', '1920') is True

    def test_both_year_only_different_conflict(self):
        assert _dup_date_compatible('1920', '1921') is False


# ---------------------------------------------------------------------------
# _dup_get_fields / _dup_get_sour_blocks
# ---------------------------------------------------------------------------

class TestDupGetFields:
    def _block(self):
        return [
            '1 BIRT\n',
            '2 DATE 15 JAN 1920\n',
            '2 PLAC London, England\n',
            '2 SOUR @S1@\n',
            '3 PAGE p.5\n',
        ]

    def test_extracts_date_and_plac(self):
        lines = self._block()
        fields = _dup_get_fields(lines, 0, len(lines))
        assert fields == {'DATE': '15 JAN 1920', 'PLAC': 'London, England'}

    def test_excludes_sour(self):
        lines = self._block()
        fields = _dup_get_fields(lines, 0, len(lines))
        assert 'SOUR' not in fields

    def test_first_occurrence_wins(self):
        lines = [
            '1 BIRT\n',
            '2 DATE 1920\n',
            '2 DATE 1921\n',
        ]
        fields = _dup_get_fields(lines, 0, len(lines))
        assert fields['DATE'] == '1920'


class TestDupGetSourBlocks:
    def test_extracts_source_with_children(self):
        lines = [
            '1 BIRT\n',
            '2 DATE 1920\n',
            '2 SOUR @S1@\n',
            '3 PAGE p.1\n',
            '3 QUAY 3\n',
        ]
        blocks = _dup_get_sour_blocks(lines, 0, len(lines))
        assert len(blocks) == 1
        assert blocks[0][0] == '2 SOUR @S1@\n'
        assert len(blocks[0]) == 3  # SOUR + PAGE + QUAY

    def test_extracts_multiple_sources(self):
        lines = [
            '1 BIRT\n',
            '2 SOUR @S1@\n',
            '2 SOUR @S2@\n',
            '3 PAGE p.2\n',
        ]
        blocks = _dup_get_sour_blocks(lines, 0, len(lines))
        assert len(blocks) == 2

    def test_empty_when_no_sources(self):
        lines = ['1 BIRT\n', '2 DATE 1920\n']
        assert _dup_get_sour_blocks(lines, 0, len(lines)) == []


# ---------------------------------------------------------------------------
# scan_duplicate_events / fix_duplicate_events
# ---------------------------------------------------------------------------

class TestScanDuplicateEvents:
    def test_detects_identical_birt_blocks(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 1920
            0 TRLR
        """)
        issues = scan_duplicate_events(str(ged))
        assert len(issues) == 1
        assert issues[0][0] == '@I1@'
        assert issues[0][1] == 'BIRT'

    def test_no_false_positive_different_dates(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 1921
            0 TRLR
        """)
        assert scan_duplicate_events(str(ged)) == []

    def test_detects_deat_duplicates(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 DEAT
            2 DATE 1950
            1 DEAT
            2 DATE 1950
            0 TRLR
        """)
        issues = scan_duplicate_events(str(ged))
        assert any(i[1] == 'DEAT' for i in issues)

    def test_no_false_positive_single_block(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            0 TRLR
        """)
        assert scan_duplicate_events(str(ged)) == []


class TestFixDuplicateEvents:
    def test_removes_true_duplicate(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 1920
            0 TRLR
        """)
        count = fix_duplicate_events(str(ged))
        assert count == 1
        content = ged.read_text(encoding='utf-8')
        assert content.count('1 BIRT') == 1

    def test_merges_sources_from_victim_to_survivor(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            2 SOUR @S1@
            1 BIRT
            2 DATE 1920
            2 SOUR @S2@
            0 TRLR
        """)
        fix_duplicate_events(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '2 SOUR @S1@' in content
        assert '2 SOUR @S2@' in content
        assert content.count('1 BIRT') == 1

    def test_does_not_duplicate_shared_source(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            2 SOUR @S1@
            1 BIRT
            2 DATE 1920
            2 SOUR @S1@
            0 TRLR
        """)
        fix_duplicate_events(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert content.count('2 SOUR @S1@') == 1

    def test_removes_year_only_when_full_date_present_same_year(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 15 JAN 1920
            0 TRLR
        """)
        count = fix_duplicate_events(str(ged))
        assert count == 1
        content = ged.read_text(encoding='utf-8')
        assert content.count('1 BIRT') == 1
        assert '15 JAN 1920' in content

    def test_keeps_both_when_dates_conflict(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 1921
            0 TRLR
        """)
        count = fix_duplicate_events(str(ged))
        assert count == 0
        assert ged.read_text(encoding='utf-8').count('1 BIRT') == 2

    def test_keeps_both_when_plac_conflicts(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            2 PLAC London, England
            1 BIRT
            2 DATE 1920
            2 PLAC Paris, France
            0 TRLR
        """)
        count = fix_duplicate_events(str(ged))
        assert count == 0

    def test_dry_run_does_not_write(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 1920
            0 TRLR
        """)
        original = ged.read_text(encoding='utf-8')
        count = fix_duplicate_events(str(ged), dry_run=True)
        assert count == 1
        assert ged.read_text(encoding='utf-8') == original

    def test_three_blocks_pair_merged_unique_kept(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 1 MAR 1920
            0 TRLR
        """)
        count = fix_duplicate_events(str(ged))
        assert count == 1
        assert ged.read_text(encoding='utf-8').count('1 BIRT') == 2

    def test_handles_each_event_type(self, tmp_path):
        for tag in ('BIRT', 'DEAT', 'BAPM', 'BURI', 'NATU'):
            ged = write_ged(tmp_path, f"""\
                0 HEAD
                1 GEDC
                2 VERS 5.5.1
                0 @I1@ INDI
                1 {tag}
                2 DATE 1920
                1 {tag}
                2 DATE 1920
                0 TRLR
            """)
            count = fix_duplicate_events(str(ged))
            assert count == 1, f'Expected 1 removal for {tag}'
            assert ged.read_text(encoding='utf-8').count(f'1 {tag}') == 1

    def test_cross_individual_isolation(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 BIRT
            2 DATE 1920
            0 @I2@ INDI
            1 BIRT
            2 DATE 1950
            1 BIRT
            2 DATE 1950
            0 TRLR
        """)
        count = fix_duplicate_events(str(ged))
        assert count == 2
        content = ged.read_text(encoding='utf-8')
        assert content.count('1 BIRT') == 2

    def test_resi_not_touched(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 RESI
            2 DATE 1920
            1 RESI
            2 DATE 1920
            0 TRLR
        """)
        count = fix_duplicate_events(str(ged))
        assert count == 0
        assert ged.read_text(encoding='utf-8').count('1 RESI') == 2

    def test_no_duplicates_unchanged(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            0 TRLR
        """)
        original = ged.read_text(encoding='utf-8')
        count = fix_duplicate_events(str(ged))
        assert count == 0
        assert ged.read_text(encoding='utf-8') == original
