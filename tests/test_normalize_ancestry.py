"""
Tests for normalize_ancestry.py

Focuses on invariants that must hold across the full pipeline:
the number of INDI and FAM records must never change.
"""

import re
import shutil
from pathlib import Path

import pytest

from normalize_ancestry import normalize_ancestry

FIXTURE = Path(__file__).parent / 'fixtures' / 'ancestry_export.ged'

_INDI_RE = re.compile(r'^0 @[^@]+@ INDI\b')
_FAM_RE  = re.compile(r'^0 @[^@]+@ FAM\b')


def _count_records(path: str) -> dict:
    """Return {'indi': int, 'fam': int} for a GEDCOM file."""
    indi = fam = 0
    with open(path, encoding='utf-8') as f:
        for line in f:
            if _INDI_RE.match(line):
                indi += 1
            elif _FAM_RE.match(line):
                fam += 1
    return {'indi': indi, 'fam': fam}


@pytest.fixture()
def tmp_copy(tmp_path):
    dest = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, dest)
    return str(dest)


# ---------------------------------------------------------------------------
# Record-count invariants
# ---------------------------------------------------------------------------

class TestRecordCountsPreserved:

    def test_indi_count_unchanged(self, tmp_copy, tmp_path):
        before = _count_records(tmp_copy)
        out = str(tmp_path / 'out.ged')
        normalize_ancestry(tmp_copy, path_out=out)
        after = _count_records(out)
        assert after['indi'] == before['indi'], (
            f"INDI count changed: {before['indi']} → {after['indi']}"
        )

    def test_fam_count_unchanged(self, tmp_copy, tmp_path):
        before = _count_records(tmp_copy)
        out = str(tmp_path / 'out.ged')
        normalize_ancestry(tmp_copy, path_out=out)
        after = _count_records(out)
        assert after['fam'] == before['fam'], (
            f"FAM count changed: {before['fam']} → {after['fam']}"
        )

    def test_dry_run_preserves_counts(self, tmp_copy):
        """dry_run must not touch the file — counts before == counts before."""
        before = _count_records(tmp_copy)
        normalize_ancestry(tmp_copy, dry_run=True)
        after = _count_records(tmp_copy)
        assert after == before

    def test_indi_count_unchanged_skipping_steps(self, tmp_copy, tmp_path):
        """Invariant holds even when some steps are skipped."""
        before = _count_records(tmp_copy)
        out = str(tmp_path / 'out.ged')
        normalize_ancestry(tmp_copy, path_out=out, skip=['purge_obje', 'linter'])
        after = _count_records(out)
        assert after['indi'] == before['indi']
        assert after['fam'] == before['fam']
