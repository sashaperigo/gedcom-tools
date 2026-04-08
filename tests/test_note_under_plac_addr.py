"""
Tests for scan_note_under_plac(), fix_note_under_plac(),
scan_note_under_addr(), and fix_note_under_addr() in gedcom_linter.py.
"""
import os

import pytest

from gedcom_linter import (
    scan_note_under_plac, fix_note_under_plac,
    scan_note_under_addr, fix_note_under_addr,
)

GED_PATH = os.environ.get('GED_FILE', '')


def _write(tmp_path, content: str) -> str:
    p = tmp_path / 'test.ged'
    p.write_text(content, encoding='utf-8')
    return str(p)


def _read(tmp_path) -> str:
    return (tmp_path / 'test.ged').read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# scan_note_under_plac
# ---------------------------------------------------------------------------

class TestScanNoteUnderPlac:

    def test_valid_note_sibling_of_plac_not_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '2 NOTE St. Paul\'s Cathedral\n'
            '0 TRLR\n'
        )
        assert scan_note_under_plac(path) == []

    def test_note_child_of_plac_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '3 NOTE St. Paul\'s Cathedral\n'
            '0 TRLR\n'
        )
        violations = scan_note_under_plac(path)
        assert len(violations) == 1
        lineno, level = violations[0]
        assert lineno == 4
        assert level == 3

    def test_note_in_sour_block_not_flagged(self, tmp_path):
        """NOTE under PLAC inside a SOUR citation is not our issue."""
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 SOUR @S1@\n'
            '3 DATA\n'
            '4 TEXT some text\n'
            '0 TRLR\n'
        )
        assert scan_note_under_plac(path) == []

    def test_multiple_violations_all_reported(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC Smyrna, Turkey\n'
            '3 NOTE St. John\'s Cathedral\n'
            '1 DEAT\n'
            '2 PLAC London, England\n'
            '3 NOTE Cheltenham Cemetery\n'
            '0 TRLR\n'
        )
        violations = scan_note_under_plac(path)
        assert len(violations) == 2
        assert violations[0][0] == 4
        assert violations[1][0] == 7

    def test_note_not_immediately_after_plac_not_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '2 DATE 1 APR 1900\n'
            '3 NOTE not a plac child\n'
            '0 TRLR\n'
        )
        assert scan_note_under_plac(path) == []


# ---------------------------------------------------------------------------
# fix_note_under_plac
# ---------------------------------------------------------------------------

class TestFixNoteUnderPlac:

    def test_fix_converts_note_to_addr(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC Smyrna, Turkey\n'
            '3 NOTE St. John\'s Cathedral\n'
            '0 TRLR\n'
        )
        count = fix_note_under_plac(path)
        assert count == 1
        result = _read(tmp_path)
        assert "2 ADDR St. John's Cathedral\n" in result
        assert '3 NOTE' not in result

    def test_fix_does_not_touch_valid_note(self, tmp_path):
        original = (
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '2 NOTE A valid sibling note\n'
            '0 TRLR\n'
        )
        path = _write(tmp_path, original)
        count = fix_note_under_plac(path)
        assert count == 0
        assert _read(tmp_path) == original

    def test_fix_promotes_cont_lines(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC Smyrna, Turkey\n'
            '3 NOTE St. John\'s Cathedral\n'
            '4 CONT Additional detail\n'
            '0 TRLR\n'
        )
        fix_note_under_plac(path)
        result = _read(tmp_path)
        assert "2 ADDR St. John's Cathedral\n" in result
        assert '3 CONT Additional detail\n' in result
        assert '4 CONT' not in result

    def test_dry_run_makes_no_changes(self, tmp_path):
        original = (
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC Smyrna, Turkey\n'
            '3 NOTE St. John\'s Cathedral\n'
            '0 TRLR\n'
        )
        path = _write(tmp_path, original)
        count = fix_note_under_plac(path, dry_run=True)
        assert count == 1
        assert _read(tmp_path) == original

    def test_surrounding_structure_preserved(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC Smyrna, Turkey\n'
            '3 NOTE St. John\'s Cathedral\n'
            '2 SOUR @S1@\n'
            '3 PAGE Birth record\n'
            '0 TRLR\n'
        )
        fix_note_under_plac(path)
        result = _read(tmp_path)
        assert "2 ADDR St. John's Cathedral\n" in result
        assert '2 SOUR @S1@\n' in result
        assert '3 PAGE Birth record\n' in result

    def test_fix_not_applied_inside_sour(self, tmp_path):
        original = (
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 SOUR @S1@\n'
            '3 PAGE some page\n'
            '0 TRLR\n'
        )
        path = _write(tmp_path, original)
        count = fix_note_under_plac(path)
        assert count == 0
        assert _read(tmp_path) == original


# ---------------------------------------------------------------------------
# scan_note_under_addr
# ---------------------------------------------------------------------------

class TestScanNoteUnderAddr:

    def test_no_note_under_addr_is_fine(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 ADDR 10 Downing Street\n'
            '0 TRLR\n'
        )
        assert scan_note_under_addr(path) == []

    def test_note_child_of_addr_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 ADDR Shaftesbury Avenue\n'
            '3 NOTE French Hospital\n'
            '0 TRLR\n'
        )
        violations = scan_note_under_addr(path)
        assert len(violations) == 1
        assert violations[0] == (4, 3)

    def test_note_not_immediately_after_addr_not_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 ADDR 10 Downing Street\n'
            '2 DATE 1900\n'
            '3 NOTE not an addr child\n'
            '0 TRLR\n'
        )
        assert scan_note_under_addr(path) == []


# ---------------------------------------------------------------------------
# fix_note_under_addr
# ---------------------------------------------------------------------------

class TestFixNoteUnderAddr:

    def test_fix_puts_venue_first(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 DEAT\n'
            '2 PLAC Holborn, London, England\n'
            '2 ADDR Shaftesbury Avenue\n'
            '3 NOTE French Hospital\n'
            '0 TRLR\n'
        )
        count = fix_note_under_addr(path)
        assert count == 1
        result = _read(tmp_path)
        assert '2 ADDR French Hospital\n' in result
        assert '3 CONT Shaftesbury Avenue\n' in result
        assert '3 NOTE' not in result

    def test_fix_does_not_touch_addr_without_note_child(self, tmp_path):
        original = (
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 ADDR 10 Downing Street\n'
            '0 TRLR\n'
        )
        path = _write(tmp_path, original)
        count = fix_note_under_addr(path)
        assert count == 0
        assert _read(tmp_path) == original

    def test_dry_run_makes_no_changes(self, tmp_path):
        original = (
            '0 @I1@ INDI\n'
            '1 DEAT\n'
            '2 ADDR Shaftesbury Avenue\n'
            '3 NOTE French Hospital\n'
            '0 TRLR\n'
        )
        path = _write(tmp_path, original)
        count = fix_note_under_addr(path, dry_run=True)
        assert count == 1
        assert _read(tmp_path) == original

    def test_surrounding_lines_unchanged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 DEAT\n'
            '2 DATE 24 Jan 1941\n'
            '2 PLAC Holborn, London, England\n'
            '2 ADDR Shaftesbury Avenue\n'
            '3 NOTE French Hospital\n'
            '2 SOUR @S1@\n'
            '0 TRLR\n'
        )
        fix_note_under_addr(path)
        result = _read(tmp_path)
        assert '2 DATE 24 Jan 1941\n' in result
        assert '2 PLAC Holborn, London, England\n' in result
        assert '2 ADDR French Hospital\n' in result
        assert '3 CONT Shaftesbury Avenue\n' in result
        assert '2 SOUR @S1@\n' in result


# ---------------------------------------------------------------------------
# Integration tests against the real GEDCOM file
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GED_PATH, reason='GED_FILE not set')
def test_no_note_under_plac_in_real_file():
    violations = scan_note_under_plac(GED_PATH)
    assert violations == [], (
        f'{len(violations)} NOTE line(s) incorrectly nested under PLAC in {GED_PATH}:\n'
        + '\n'.join(f'  line {ln}: level-{lv}' for ln, lv in violations[:20])
    )


@pytest.mark.skipif(not GED_PATH, reason='GED_FILE not set')
def test_no_note_under_addr_in_real_file():
    violations = scan_note_under_addr(GED_PATH)
    assert violations == [], (
        f'{len(violations)} NOTE line(s) incorrectly nested under ADDR in {GED_PATH}:\n'
        + '\n'.join(f'  line {ln}: level-{lv}' for ln, lv in violations[:20])
    )
