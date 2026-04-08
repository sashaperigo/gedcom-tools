"""
Tests for scan_addr_under_plac() and fix_addr_under_plac() in gedcom_linter.py.
"""
import os

import pytest

from gedcom_linter import scan_addr_under_plac, fix_addr_under_plac

GED_PATH = os.environ.get('GED_FILE', '')


def _write(tmp_path, content: str) -> str:
    p = tmp_path / 'test.ged'
    p.write_text(content, encoding='utf-8')
    return str(p)


def _read(tmp_path) -> str:
    return (tmp_path / 'test.ged').read_text(encoding='utf-8')


class TestScanAddrUnderPlac:

    def test_valid_addr_sibling_of_plac(self, tmp_path):
        """ADDR at same level as PLAC is fine."""
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 DATE 1 APR 1900\n'
            '2 PLAC London, England\n'
            '2 ADDR 10 Downing Street\n'
            '0 TRLR\n'
        )
        assert scan_addr_under_plac(path) == []

    def test_addr_child_of_plac_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '3 ADDR Shaftesbury Avenue\n'
            '0 TRLR\n'
        )
        violations = scan_addr_under_plac(path)
        assert len(violations) == 1
        lineno, level = violations[0]
        assert lineno == 4
        assert level == 3

    def test_addr_not_after_plac_not_flagged(self, tmp_path):
        """ADDR after a non-PLAC line at one level higher is fine."""
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 RESI\n'
            '2 DATE 1900\n'
            '2 ADDR 10 Downing Street\n'
            '0 TRLR\n'
        )
        assert scan_addr_under_plac(path) == []

    def test_multiple_violations_all_reported(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '3 ADDR Baker Street\n'
            '1 DEAT\n'
            '2 PLAC Paris, France\n'
            '3 ADDR Rue de Rivoli\n'
            '0 TRLR\n'
        )
        violations = scan_addr_under_plac(path)
        assert len(violations) == 2
        assert violations[0][0] == 4
        assert violations[1][0] == 7

    def test_addr_in_head_corp_not_flagged(self, tmp_path):
        """ADDR under CORP (not PLAC) in HEAD is valid."""
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 SOUR Ancestry\n'
            '2 CORP Ancestry.com\n'
            '3 ADDR 1300 West Traverse Parkway\n'
            '0 TRLR\n'
        )
        assert scan_addr_under_plac(path) == []


class TestFixAddrUnderPlac:

    def test_fix_promotes_addr_one_level(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '3 ADDR Baker Street\n'
            '0 TRLR\n'
        )
        count = fix_addr_under_plac(path)
        assert count == 1
        result = _read(tmp_path)
        assert '2 ADDR Baker Street\n' in result
        assert '3 ADDR' not in result

    def test_fix_does_not_change_valid_addr(self, tmp_path):
        original = (
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '2 ADDR 10 Downing Street\n'
            '0 TRLR\n'
        )
        path = _write(tmp_path, original)
        count = fix_addr_under_plac(path)
        assert count == 0
        assert _read(tmp_path) == original

    def test_fix_promotes_cont_lines_too(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '3 ADDR Baker Street\n'
            '4 CONT London W1\n'
            '0 TRLR\n'
        )
        fix_addr_under_plac(path)
        result = _read(tmp_path)
        assert '2 ADDR Baker Street\n' in result
        assert '3 CONT London W1\n' in result
        assert '4 CONT' not in result

    def test_fix_multiple_violations(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '3 ADDR Baker Street\n'
            '1 DEAT\n'
            '2 PLAC Paris, France\n'
            '3 ADDR Rue de Rivoli\n'
            '0 TRLR\n'
        )
        count = fix_addr_under_plac(path)
        assert count == 2
        result = _read(tmp_path)
        assert result.count('2 ADDR') == 2
        assert '3 ADDR' not in result

    def test_dry_run_makes_no_changes(self, tmp_path):
        original = (
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '3 ADDR Baker Street\n'
            '0 TRLR\n'
        )
        path = _write(tmp_path, original)
        count = fix_addr_under_plac(path, dry_run=True)
        assert count == 1
        assert _read(tmp_path) == original  # unchanged

    def test_structure_after_addr_preserved(self, tmp_path):
        """Lines after the ADDR block should be unaffected."""
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '3 ADDR Baker Street\n'
            '2 SOUR @S1@\n'
            '3 PAGE Birth record\n'
            '0 TRLR\n'
        )
        fix_addr_under_plac(path)
        result = _read(tmp_path)
        assert '2 ADDR Baker Street\n' in result
        assert '2 SOUR @S1@\n' in result
        assert '3 PAGE Birth record\n' in result


# ---------------------------------------------------------------------------
# Integration test against the real GEDCOM file
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GED_PATH, reason='GED_FILE not set')
def test_no_addr_under_plac_in_real_file():
    violations = scan_addr_under_plac(GED_PATH)
    assert violations == [], (
        f'{len(violations)} ADDR line(s) incorrectly nested under PLAC in {GED_PATH}:\n'
        + '\n'.join(
            f'  line {ln}: level-{lv} ADDR under level-{lv - 1} PLAC'
            for ln, lv in violations[:20]
        )
        + (f'\n  ... and {len(violations) - 20} more.' if len(violations) > 20 else '')
    )
