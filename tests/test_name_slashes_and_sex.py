"""
Tests for scan_name_slashes() and scan_sex_values() in gedcom_linter.py.
"""
import os

import pytest

from gedcom_linter import scan_name_slashes, scan_sex_values

GED_PATH = os.environ.get('GED_FILE', '')


def _write(tmp_path, content: str) -> str:
    p = tmp_path / 'test.ged'
    p.write_text(content, encoding='utf-8')
    return str(p)


# ---------------------------------------------------------------------------
# scan_name_slashes
# ---------------------------------------------------------------------------

class TestScanNameSlashes:

    def test_no_slashes_is_valid(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 NAME Alice Smith\n0 TRLR\n')
        assert scan_name_slashes(path) == []

    def test_one_pair_is_valid(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 NAME Alice /Smith/\n0 TRLR\n')
        assert scan_name_slashes(path) == []

    def test_one_pair_surname_only_is_valid(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 NAME /Smith/\n0 TRLR\n')
        assert scan_name_slashes(path) == []

    def test_two_pairs_flagged(self, tmp_path):
        # "/Given/ /Surname/" — two slash-delimited sections
        path = _write(tmp_path, '0 @I1@ INDI\n1 NAME /Alice/ /Smith/\n0 TRLR\n')
        violations = scan_name_slashes(path)
        assert len(violations) == 1
        lineno, val = violations[0]
        assert lineno == 2
        assert '/Alice/ /Smith/' in val

    def test_unmatched_single_slash_flagged(self, tmp_path):
        # Three slashes (unbalanced): "/Alice /Smith/"
        path = _write(tmp_path, '0 @I1@ INDI\n1 NAME /Alice /Smith/\n0 TRLR\n')
        violations = scan_name_slashes(path)
        # 3 slashes > 2 — flagged
        assert len(violations) == 1

    def test_multiple_names_only_bad_ones_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 NAME Alice /Smith/\n'        # valid
            '1 NAME /Alice/ /Smith/\n'      # invalid
            '0 TRLR\n'
        )
        violations = scan_name_slashes(path)
        assert len(violations) == 1
        assert violations[0][0] == 3

    def test_non_name_lines_ignored(self, tmp_path):
        # NOTE line with slashes should not be flagged
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 NOTE see /ref/ and /other/ for details\n'
            '0 TRLR\n'
        )
        assert scan_name_slashes(path) == []


# ---------------------------------------------------------------------------
# scan_sex_values
# ---------------------------------------------------------------------------

class TestScanSexValues:

    def test_sex_m_valid(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 SEX M\n0 TRLR\n')
        assert scan_sex_values(path) == []

    def test_sex_f_valid(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 SEX F\n0 TRLR\n')
        assert scan_sex_values(path) == []

    def test_sex_u_valid(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 SEX U\n0 TRLR\n')
        assert scan_sex_values(path) == []

    def test_sex_lowercase_m_flagged(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 SEX m\n0 TRLR\n')
        violations = scan_sex_values(path)
        assert len(violations) == 1
        assert violations[0] == (2, 'm')

    def test_sex_invalid_value_flagged(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 SEX X\n0 TRLR\n')
        violations = scan_sex_values(path)
        assert len(violations) == 1
        lineno, val = violations[0]
        assert lineno == 2
        assert val == 'X'

    def test_sex_unknown_word_flagged(self, tmp_path):
        path = _write(tmp_path, '0 @I1@ INDI\n1 SEX Male\n0 TRLR\n')
        violations = scan_sex_values(path)
        assert len(violations) == 1
        assert violations[0][1] == 'Male'

    def test_multiple_records_only_bad_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 SEX M\n'
            '0 @I2@ INDI\n'
            '1 SEX F\n'
            '0 @I3@ INDI\n'
            '1 SEX X\n'   # invalid
            '0 TRLR\n'
        )
        violations = scan_sex_values(path)
        assert len(violations) == 1
        assert violations[0][1] == 'X'

    def test_no_sex_tag_no_violations(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 NAME Alice /Smith/\n'
            '0 TRLR\n'
        )
        assert scan_sex_values(path) == []


# ---------------------------------------------------------------------------
# Integration tests against the real GEDCOM file
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GED_PATH, reason='GED_FILE not set')
def test_no_name_slash_violations_in_real_file():
    violations = scan_name_slashes(GED_PATH)
    assert violations == [], (
        f'{len(violations)} NAME value(s) with invalid slash structure in {GED_PATH}:\n'
        + '\n'.join(f'  line {ln}: {val!r}' for ln, val in violations[:20])
        + (f'\n  ... and {len(violations) - 20} more.' if len(violations) > 20 else '')
    )


@pytest.mark.skipif(not GED_PATH, reason='GED_FILE not set')
def test_no_invalid_sex_values_in_real_file():
    violations = scan_sex_values(GED_PATH)
    assert violations == [], (
        f'{len(violations)} invalid SEX value(s) in {GED_PATH}:\n'
        + '\n'.join(f'  line {ln}: {val!r}' for ln, val in violations[:20])
        + (f'\n  ... and {len(violations) - 20} more.' if len(violations) > 20 else '')
    )
