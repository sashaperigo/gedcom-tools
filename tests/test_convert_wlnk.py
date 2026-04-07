"""
Tests for convert_wlnk.py

Covers conversion of Ancestry _WLNK blocks to standard GEDCOM:
  - Ancestry person URLs that resolve → ASSO + RELA
  - Ancestry person URLs that don't resolve → NOTE fallback
  - External URLs → NOTE
  - Multiple _WLNK on one INDI
  - Standard tags preserved
  - Return value statistics
  - Dry-run and output-file options
"""

import os
import re
import shutil
from pathlib import Path

import pytest

from convert_wlnk import convert_wlnk

FIXTURE = Path(__file__).parent / 'fixtures' / 'wlnk_sample.ged'


@pytest.fixture()
def tmp_copy(tmp_path):
    dest = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, dest)
    return str(dest)


def lines_of(path: str) -> list[str]:
    with open(path, encoding='utf-8') as f:
        return [l.rstrip('\n') for l in f]


# ---------------------------------------------------------------------------
# Fixture sanity checks
# ---------------------------------------------------------------------------

class TestFixtureContents:

    def test_fixture_exists(self):
        assert FIXTURE.exists()

    def test_fixture_has_wlnk(self):
        content = FIXTURE.read_text(encoding='utf-8')
        assert '_WLNK' in content

    def test_fixture_has_ancestry_url(self):
        content = FIXTURE.read_text(encoding='utf-8')
        assert 'ancestry.com/family-tree/person' in content

    def test_fixture_has_external_url(self):
        content = FIXTURE.read_text(encoding='utf-8')
        assert 'themonth.com' in content

    def test_fixture_has_resolvable_indi(self):
        """@I382540076099@ must exist as an INDI for the resolved-URL test."""
        content = FIXTURE.read_text(encoding='utf-8')
        assert '@I382540076099@ INDI' in content

    def test_fixture_has_unresolvable_url(self):
        """person/999999999 must NOT be an INDI in the fixture."""
        content = FIXTURE.read_text(encoding='utf-8')
        assert '999999999' in content
        assert '@I999999999@ INDI' not in content


# ---------------------------------------------------------------------------
# Core conversion behaviour
# ---------------------------------------------------------------------------

class TestConversion:

    def test_ancestry_url_resolves_to_asso(self, tmp_copy):
        convert_wlnk(tmp_copy)
        lines = lines_of(tmp_copy)
        assert any('1 ASSO @I382540076099@' in l for l in lines), \
            'Expected ASSO record for resolved Ancestry person ID'

    def test_asso_rela_matches_titl(self, tmp_copy):
        convert_wlnk(tmp_copy)
        lines = lines_of(tmp_copy)
        asso_idx = next(
            i for i, l in enumerate(lines) if '1 ASSO @I382540076099@' in l
        )
        assert any('2 RELA Godmother' in l for l in lines[asso_idx:asso_idx + 3]), \
            'Expected 2 RELA Godmother immediately after ASSO line'

    def test_ancestry_url_unresolved_becomes_note(self, tmp_copy):
        convert_wlnk(tmp_copy)
        lines = lines_of(tmp_copy)
        assert any('person not in tree' in l for l in lines), \
            'Expected fallback NOTE for unresolved Ancestry person ID'
        assert any('999999999' in l for l in lines), \
            'Unresolved URL should still appear in the NOTE'

    def test_external_url_becomes_note(self, tmp_copy):
        convert_wlnk(tmp_copy)
        lines = lines_of(tmp_copy)
        assert any('themonth.com' in l for l in lines), \
            'External URL must be preserved in a NOTE'
        assert any('Philip Caraman' in l for l in lines), \
            'TITL text must appear in the NOTE'

    def test_no_wlnk_remain(self, tmp_copy):
        convert_wlnk(tmp_copy)
        content = Path(tmp_copy).read_text(encoding='utf-8')
        assert '_WLNK' not in content

    def test_standard_tags_preserved(self, tmp_copy):
        convert_wlnk(tmp_copy)
        content = Path(tmp_copy).read_text(encoding='utf-8')
        for tag in ('Adelaide /Dellatolla/', 'Philip /Caraman/', 'Angela /Dellatolla/',
                    '6 JAN 1884', 'Smyrna, Izmir, Turkey', '@S1@'):
            assert tag in content, f'Standard content {tag!r} was removed'

    def test_multiple_wlnk_all_converted(self, tmp_copy):
        """@I4@ has two _WLNK blocks — both must be converted."""
        convert_wlnk(tmp_copy)
        content = Path(tmp_copy).read_text(encoding='utf-8')
        assert '_WLNK' not in content
        # Ancestry link → ASSO; Facebook link → NOTE
        assert '1 ASSO @I382540076099@' in content
        assert 'facebook.com' in content

    def test_asso_rela_for_goddaughter(self, tmp_copy):
        """TITL 'Goddaughter: Frida Dellatolla' → RELA Goddaughter."""
        convert_wlnk(tmp_copy)
        lines = lines_of(tmp_copy)
        # @I4@ has a Goddaughter link pointing to @I382540076099@
        asso_lines = [l for l in lines if '1 ASSO @I382540076099@' in l]
        assert asso_lines, 'No ASSO found for @I382540076099@'
        # Find all RELA values following any of those ASSO lines
        rela_values = []
        for i, l in enumerate(lines):
            if '1 ASSO @I382540076099@' in l:
                for j in range(i + 1, min(i + 4, len(lines))):
                    m = re.match(r'2 RELA (.+)', lines[j])
                    if m:
                        rela_values.append(m.group(1))
        assert 'Goddaughter' in rela_values or 'Godmother' in rela_values, \
            f'Expected relationship RELA, got: {rela_values}'

    def test_sour_after_wlnk_preserved(self, tmp_copy):
        """SOUR on @I4@ must survive even though it follows _WLNK blocks."""
        convert_wlnk(tmp_copy)
        content = Path(tmp_copy).read_text(encoding='utf-8')
        assert '1 SOUR @S1@' in content
        assert 'Birth register, p. 12' in content


# ---------------------------------------------------------------------------
# Return value / statistics
# ---------------------------------------------------------------------------

class TestReturnValues:

    def test_stats_keys_present(self, tmp_copy):
        result = convert_wlnk(tmp_copy)
        for key in ('lines_read', 'lines_removed', 'asso_added', 'notes_added', 'unresolved'):
            assert key in result, f'Missing key {key!r} in return dict'

    def test_lines_read_matches_file(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            file_len = sum(1 for _ in f)
        result = convert_wlnk(tmp_copy)
        assert result['lines_read'] == file_len

    def test_lines_removed_equals_diff(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            before = sum(1 for _ in f)
        result = convert_wlnk(tmp_copy)
        with open(tmp_copy, encoding='utf-8') as f:
            after = sum(1 for _ in f)
        assert result['lines_removed'] == before - after

    def test_asso_added_count(self, tmp_copy):
        result = convert_wlnk(tmp_copy)
        # Fixture: @I1@ + @I4@ both resolve to @I382540076099@ = 2 ASSO records
        assert result['asso_added'] == 2

    def test_unresolved_count(self, tmp_copy):
        result = convert_wlnk(tmp_copy)
        # Fixture: @I2@ has an unresolvable Ancestry URL
        assert result['unresolved'] == 1

    def test_notes_added_count(self, tmp_copy):
        result = convert_wlnk(tmp_copy)
        # @I2@ unresolved→note, @I3@ external→note, @I4@ facebook→note = 3 notes
        assert result['notes_added'] == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_no_wlnk_file_unchanged(self, tmp_path):
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /Wonder/\n1 BIRT\n2 DATE 1 APR 1900\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        original = clean.read_text(encoding='utf-8')
        result = convert_wlnk(str(clean))
        assert result['lines_removed'] == 0
        assert result['asso_added'] == 0
        assert result['notes_added'] == 0
        assert clean.read_text(encoding='utf-8') == original

    def test_dry_run_no_write(self, tmp_copy):
        original = Path(tmp_copy).read_text(encoding='utf-8')
        convert_wlnk(tmp_copy, dry_run=True)
        assert Path(tmp_copy).read_text(encoding='utf-8') == original

    def test_dry_run_returns_correct_stats(self, tmp_copy):
        dry = convert_wlnk(tmp_copy, dry_run=True)
        real = convert_wlnk(tmp_copy)
        assert dry['asso_added'] == real['asso_added']
        assert dry['unresolved'] == real['unresolved']
        assert dry['notes_added'] == real['notes_added']

    def test_output_file_option(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        convert_wlnk(str(FIXTURE), path_out=out)
        assert os.path.exists(out)
        content = Path(out).read_text(encoding='utf-8')
        assert '_WLNK' not in content

    def test_input_unchanged_when_output_specified(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        original = FIXTURE.read_text(encoding='utf-8')
        convert_wlnk(str(FIXTURE), path_out=out)
        assert FIXTURE.read_text(encoding='utf-8') == original
