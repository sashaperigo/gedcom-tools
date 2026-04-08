"""
Tests for scan_level_jumps() in gedcom_linter.py, plus an integration test
that the real GEDCOM file (GED_FILE env var) has no invalid level jumps.
"""
import os
from pathlib import Path

import pytest

from gedcom_linter import scan_level_jumps

GED_PATH = os.environ.get('GED_FILE', '')


# ---------------------------------------------------------------------------
# Unit tests (inline GEDCOM content via tmp_path)
# ---------------------------------------------------------------------------

def _write(tmp_path, content: str) -> str:
    p = tmp_path / 'test.ged'
    p.write_text(content, encoding='utf-8')
    return str(p)


class TestScanLevelJumps:

    def test_valid_file_no_violations(self, tmp_path):
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 NAME Alice /Smith/\n'
            '1 BIRT\n'
            '2 DATE 1 APR 1900\n'
            '2 PLAC London, England\n'
            '0 TRLR\n'
        )
        assert scan_level_jumps(path) == []

    def test_level_jump_1_to_3_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '3 DATE 1 APR 1900\n'   # jumps from 1 to 3 — invalid
            '0 TRLR\n'
        )
        violations = scan_level_jumps(path)
        assert len(violations) == 1
        lineno, prev, curr = violations[0]
        assert lineno == 3
        assert prev == 1
        assert curr == 3

    def test_level_jump_0_to_2_flagged(self, tmp_path):
        path = _write(tmp_path,
            '0 HEAD\n'
            '2 VERS 5.5.1\n'   # jumps from 0 to 2 — invalid
            '0 TRLR\n'
        )
        violations = scan_level_jumps(path)
        assert len(violations) == 1
        assert violations[0] == (2, 0, 2)

    def test_multiple_jumps_all_reported(self, tmp_path):
        path = _write(tmp_path,
            '0 HEAD\n'
            '2 VERS 5.5.1\n'   # jump: 0 → 2
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '3 DATE 1 APR 1900\n'  # jump: 1 → 3
            '0 TRLR\n'
        )
        assert len(scan_level_jumps(path)) == 2

    def test_level_decrease_is_fine(self, tmp_path):
        """Levels can decrease by any amount — only increases > 1 are invalid."""
        path = _write(tmp_path,
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 DATE 1 APR 1900\n'
            '2 PLAC London\n'
            '1 DEAT\n'           # back to 1 — fine
            '2 DATE 5 JUN 1980\n'
            '0 TRLR\n'
        )
        assert scan_level_jumps(path) == []

    def test_exact_increase_of_1_is_fine(self, tmp_path):
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '3 FORM LINEAGE-LINKED\n'  # 2 → 3: jump of 1 — fine
            '0 TRLR\n'
        )
        assert scan_level_jumps(path) == []

    def test_returns_correct_line_number(self, tmp_path):
        path = _write(tmp_path,
            '0 HEAD\n'           # line 1
            '1 GEDC\n'           # line 2
            '0 @I1@ INDI\n'     # line 3
            '1 NAME Alice /S/\n' # line 4
            '3 NOTE bad\n'       # line 5 — jump 1 → 3
            '0 TRLR\n'           # line 6
        )
        violations = scan_level_jumps(path)
        assert violations[0][0] == 5


# ---------------------------------------------------------------------------
# Integration test against the real GEDCOM file
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GED_PATH, reason='GED_FILE not set')
def test_no_level_jumps_in_real_file():
    violations = scan_level_jumps(GED_PATH)
    assert violations == [], (
        f'{len(violations)} invalid level jump(s) in {GED_PATH}:\n'
        + '\n'.join(
            f'  line {ln}: level {prev} → level {curr}'
            for ln, prev, curr in violations[:20]
        )
        + (f'\n  ... and {len(violations) - 20} more.' if len(violations) > 20 else '')
    )
