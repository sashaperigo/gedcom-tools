"""Tests for scan_duplicate_events / fix_duplicate_events in gedcom_linter."""
import textwrap
from pathlib import Path

from gedcom_linter import (
    _dup_date_compatible,
    _dup_get_fields,
    _dup_get_sour_blocks,
    _dup_is_subset,
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
