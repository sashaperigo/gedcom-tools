"""
Tests for convert_physical_attrs.py

Covers conversion of _HEIG and _WEIG to standard GEDCOM DSCR tags.
"""

import shutil
from pathlib import Path

import pytest

from convert_physical_attrs import convert_physical_attrs

FIXTURE = Path(__file__).parent / 'fixtures' / 'physical_attrs.ged'


@pytest.fixture()
def tmp_copy(tmp_path):
    dest = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, dest)
    return str(dest)


def content_of(path: str) -> str:
    return Path(path).read_text(encoding='utf-8')


def lines_of(path: str) -> list[str]:
    with open(path, encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


# ---------------------------------------------------------------------------
# Fixture sanity checks
# ---------------------------------------------------------------------------

class TestFixtureContents:

    def test_fixture_exists(self):
        assert FIXTURE.exists()

    def test_fixture_has_heig(self):
        assert '_HEIG' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_weig(self):
        assert '_WEIG' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_existing_dscr(self):
        assert '1 DSCR blue eyes' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_indi_with_no_physical_attrs(self):
        assert '@I5@ INDI' in FIXTURE.read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# Conversion tests
# ---------------------------------------------------------------------------

class TestConversion:

    def test_heig_converted_to_dscr(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        assert "1 DSCR Height: 5'8\"" in content_of(tmp_copy)

    def test_weig_converted_to_dscr(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        assert '1 DSCR Weight: 151 lbs' in content_of(tmp_copy)

    def test_no_heig_remain(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        assert '_HEIG' not in content_of(tmp_copy)

    def test_no_weig_remain(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        assert '_WEIG' not in content_of(tmp_copy)

    def test_date_child_preserved_under_dscr(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        lines = lines_of(tmp_copy)
        for i, line in enumerate(lines):
            if line == "1 DSCR Height: 5'8\"":
                assert lines[i + 1] == '2 DATE 1942'
                return
        pytest.fail("DSCR Height not found")

    def test_both_heig_and_weig_converted(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        c = content_of(tmp_copy)
        assert "1 DSCR Height: 5'3\"" in c
        assert '1 DSCR Weight: 140 lbs' in c

    def test_existing_dscr_preserved(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        assert '1 DSCR blue eyes; light complexion' in content_of(tmp_copy)

    def test_existing_dscr_and_heig_coexist(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        lines = lines_of(tmp_copy)
        dscr_lines = [l for l in lines if l.startswith('1 DSCR')]
        # @I4@ has original DSCR + converted _HEIG = 2 DSCR lines
        assert len(dscr_lines) >= 2

    def test_indi_without_attrs_unchanged(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        c = content_of(tmp_copy)
        assert '1 NAME Eve /White/' in c

    def test_trlr_preserved(self, tmp_copy):
        convert_physical_attrs(tmp_copy)
        assert lines_of(tmp_copy)[-1] == '0 TRLR'


# ---------------------------------------------------------------------------
# Return values
# ---------------------------------------------------------------------------

class TestReturnValues:

    def test_stats_keys_present(self, tmp_copy):
        result = convert_physical_attrs(tmp_copy)
        for key in ('lines_read', 'lines_delta', 'heig_converted', 'weig_converted'):
            assert key in result

    def test_heig_count(self, tmp_copy):
        result = convert_physical_attrs(tmp_copy)
        assert result['heig_converted'] == 3

    def test_weig_count(self, tmp_copy):
        result = convert_physical_attrs(tmp_copy)
        assert result['weig_converted'] == 2

    def test_lines_delta_zero(self, tmp_copy):
        # Tag rename only — line count unchanged
        result = convert_physical_attrs(tmp_copy)
        assert result['lines_delta'] == 0

    def test_lines_delta_matches_actual_diff(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            before = sum(1 for _ in f)
        result = convert_physical_attrs(tmp_copy)
        with open(tmp_copy, encoding='utf-8') as f:
            after = sum(1 for _ in f)
        assert result['lines_delta'] == after - before


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_clean_file_unchanged(self, tmp_path):
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /Smith/\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        original = clean.read_text(encoding='utf-8')
        result = convert_physical_attrs(str(clean))
        assert result['heig_converted'] == 0
        assert result['weig_converted'] == 0
        assert clean.read_text(encoding='utf-8') == original

    def test_dry_run_no_write(self, tmp_copy):
        original = Path(tmp_copy).read_text(encoding='utf-8')
        convert_physical_attrs(tmp_copy, dry_run=True)
        assert Path(tmp_copy).read_text(encoding='utf-8') == original

    def test_dry_run_stats_match_real(self, tmp_copy):
        import shutil
        import tempfile
        import os
        dry = convert_physical_attrs(tmp_copy, dry_run=True)
        with tempfile.NamedTemporaryFile(suffix='.ged', delete=False) as t:
            real_copy = t.name
        try:
            shutil.copy(tmp_copy, real_copy)
            real = convert_physical_attrs(real_copy)
        finally:
            os.unlink(real_copy)
        assert dry['heig_converted'] == real['heig_converted']
        assert dry['weig_converted'] == real['weig_converted']

    def test_output_file_option(self, tmp_path):
        out = str(tmp_path / 'out.ged')
        convert_physical_attrs(str(FIXTURE), path_out=out)
        c = Path(out).read_text(encoding='utf-8')
        assert '_HEIG' not in c
        assert '_WEIG' not in c
        assert 'DSCR Height' in c

    def test_input_unchanged_when_output_specified(self, tmp_path):
        out = str(tmp_path / 'out.ged')
        original = FIXTURE.read_text(encoding='utf-8')
        convert_physical_attrs(str(FIXTURE), path_out=out)
        assert FIXTURE.read_text(encoding='utf-8') == original
