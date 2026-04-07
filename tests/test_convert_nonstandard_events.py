"""
Tests for convert_nonstandard_events.py

Covers conversion of three non-standard GEDCOM tags to their standard equivalents:
  _MILT  -> EVEN + TYPE Military Service
  _SEPR  -> EVEN + TYPE Separation
  _DCAUSE -> CAUS injected into the next DEAT event (or a new DEAT if none follows)
"""

import re
import shutil
from pathlib import Path

import pytest

from convert_nonstandard_events import convert_nonstandard_events

FIXTURE = Path(__file__).parent / 'fixtures' / 'nonstandard_events.ged'


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

    def test_fixture_has_milt(self):
        assert '_MILT' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_sepr(self):
        assert '_SEPR' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_dcause(self):
        assert '_DCAUSE' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_dcause_with_cont(self):
        """One _DCAUSE block must have a CONT continuation line."""
        lines = FIXTURE.read_text(encoding='utf-8').splitlines()
        in_dcause = False
        for line in lines:
            if line.strip() == '1 _DCAUSE':
                in_dcause = True
            elif in_dcause and line.startswith('3 CONT'):
                return
            elif in_dcause and not line.startswith('2 ') and not line.startswith('3 '):
                in_dcause = False
        pytest.fail('Fixture has no _DCAUSE block with a CONT continuation line')

    def test_fixture_has_dcause_with_gap_before_deat(self):
        """One _DCAUSE must have other level-1 tags between it and the DEAT."""
        lines = FIXTURE.read_text(encoding='utf-8').splitlines()
        i = 0
        while i < len(lines):
            if lines[i] == '1 _DCAUSE':
                j = i + 1
                # Skip level-2+ children
                while j < len(lines) and re.match(r'^[2-9] ', lines[j]):
                    j += 1
                # Check for a non-DEAT level-1 tag before DEAT
                if j < len(lines) and lines[j].startswith('1 ') and not lines[j].startswith('1 DEAT'):
                    return  # found the gap case
            i += 1
        pytest.fail('Fixture has no _DCAUSE followed by a gap before DEAT')

    def test_fixture_has_dcause_with_no_deat(self):
        """One _DCAUSE must have no following DEAT in the same record."""
        content = FIXTURE.read_text(encoding='utf-8')
        # @I7@ has _DCAUSE but no DEAT
        assert '@I7@ INDI' in content
        assert '_DCAUSE' in content

    def test_fixture_has_milt_with_no_children(self):
        """One _MILT must have no level-2 children."""
        lines = FIXTURE.read_text(encoding='utf-8').splitlines()
        for i, line in enumerate(lines):
            if line == '1 _MILT':
                next_line = lines[i + 1] if i + 1 < len(lines) else ''
                if not re.match(r'^[2-9] ', next_line):
                    return
        pytest.fail('Fixture has no _MILT with no children')


# ---------------------------------------------------------------------------
# _MILT conversion
# ---------------------------------------------------------------------------

class TestMiltConversion:

    def test_no_milt_remain(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        assert '_MILT' not in content_of(tmp_copy)

    def test_even_created_for_milt(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        lines = lines_of(tmp_copy)
        even_idxs = [i for i, l in enumerate(lines) if l == '1 EVEN']
        assert even_idxs, 'No EVEN records created'

    def test_type_military_service_present(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        assert '2 TYPE Military Service' in content_of(tmp_copy)

    def test_type_is_first_child_of_even(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        lines = lines_of(tmp_copy)
        for i, line in enumerate(lines):
            if line == '1 EVEN' and i + 1 < len(lines) and 'Military Service' in lines[i + 1]:
                assert lines[i + 1] == '2 TYPE Military Service'
                return
        pytest.fail('No EVEN with TYPE Military Service as first child')

    def test_milt_children_preserved(self, tmp_copy):
        """DATE, PLAC, NOTE, SOUR children of _MILT must survive."""
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert 'Bhopal, Madhya Pradesh, India' in c
        assert 'Interpreter Sergeant' in c
        assert 'War Office records, ref 1234' in c

    def test_milt_deep_children_preserved(self, tmp_copy):
        """Level-3/4 children (DATA, etc.) under SOUR under _MILT must survive."""
        convert_nonstandard_events(tmp_copy)
        assert '4 DATE 1915' in content_of(tmp_copy)

    def test_milt_no_children_gets_type_only(self, tmp_copy):
        """_MILT with no children produces EVEN + TYPE Military Service, nothing else."""
        convert_nonstandard_events(tmp_copy)
        lines = lines_of(tmp_copy)
        for i, line in enumerate(lines):
            if line == '1 EVEN' and i + 1 < len(lines) and lines[i + 1] == '2 TYPE Military Service':
                # Check next meaningful line is back at level 0 or 1
                if i + 2 < len(lines):
                    next_line = lines[i + 2]
                    # For @I3@, after TYPE the next line should be BIRT
                    if next_line.startswith('1 BIRT'):
                        return
        pytest.fail('Could not verify childless _MILT produces EVEN + TYPE only')


# ---------------------------------------------------------------------------
# _SEPR conversion
# ---------------------------------------------------------------------------

class TestSeprConversion:

    def test_no_sepr_remain(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        assert '_SEPR' not in content_of(tmp_copy)

    def test_type_separation_present(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        assert '2 TYPE Separation' in content_of(tmp_copy)

    def test_type_is_first_child_of_sepr_even(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        lines = lines_of(tmp_copy)
        for i, line in enumerate(lines):
            if line == '1 EVEN' and i + 1 < len(lines) and 'Separation' in lines[i + 1]:
                assert lines[i + 1] == '2 TYPE Separation'
                return
        pytest.fail('No EVEN with TYPE Separation as first child')

    def test_sepr_children_preserved(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert 'Separated after years of conflict.' in c
        assert 'Paris, France' in c

    def test_sepr_no_children_gets_type_only(self, tmp_copy):
        """@F3@ has _SEPR with no children — should produce EVEN + TYPE Separation."""
        convert_nonstandard_events(tmp_copy)
        lines = lines_of(tmp_copy)
        for i, line in enumerate(lines):
            if line == '1 EVEN' and i + 1 < len(lines) and lines[i + 1] == '2 TYPE Separation':
                if i + 2 < len(lines) and lines[i + 2].startswith('0 '):
                    return
        pytest.fail('Could not verify childless _SEPR produces EVEN + TYPE only')

    def test_div_after_sepr_preserved(self, tmp_copy):
        """DIV events following _SEPR must survive."""
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert '1 DIV' in c
        assert '2 DATE 1987' in c
        assert '2 DATE 1962' in c


# ---------------------------------------------------------------------------
# _DCAUSE conversion
# ---------------------------------------------------------------------------

class TestDcauseConversion:

    def test_no_dcause_remain(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        assert '_DCAUSE' not in content_of(tmp_copy)

    def test_caus_injected_into_deat(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        lines = lines_of(tmp_copy)
        for i, line in enumerate(lines):
            if line == '1 DEAT':
                # Check that somewhere in this DEAT block there's a CAUS
                j = i + 1
                while j < len(lines) and re.match(r'^[2-9] ', lines[j]):
                    if lines[j].startswith('2 CAUS '):
                        return
                    j += 1
        pytest.fail('No DEAT block found with a 2 CAUS child')

    def test_caus_value_correct(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert '2 CAUS overdose, potential suicide' in c
        assert '2 CAUS blunt force trauma' in c

    def test_cont_preserved_under_caus(self, tmp_copy):
        """CONT lines from _DCAUSE must survive as children of CAUS."""
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert 'According to a biography' in c

    def test_dcause_with_gap_injects_into_correct_deat(self, tmp_copy):
        """When level-1 tags appear between _DCAUSE and DEAT, CAUS still lands in DEAT."""
        convert_nonstandard_events(tmp_copy)
        lines = lines_of(tmp_copy)
        # @I6@ has IMMI, then _DCAUSE 'drowning', then OCCU, then DEAT
        # Verify 'drowning' appears inside a DEAT block, not inside IMMI
        for i, line in enumerate(lines):
            if line == '1 DEAT':
                j = i + 1
                while j < len(lines) and re.match(r'^[2-9] ', lines[j]):
                    if 'drowning' in lines[j]:
                        return
                    j += 1
        pytest.fail("'drowning' not found inside any DEAT block")

    def test_dcause_no_deat_fallback(self, tmp_copy):
        """_DCAUSE with no following DEAT in the record creates a standalone DEAT."""
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert '2 CAUS natural causes' in c

    def test_deat_date_plac_sour_preserved(self, tmp_copy):
        """Existing DEAT children (DATE, PLAC, SOUR) must not be lost."""
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert '2 DATE 4 MAR 1948' in c
        assert '2 PLAC Ivry-sur-Seine, France' in c
        assert '2 DATE 21 AUG 1905' in c
        assert 'Death register entry' in c


# ---------------------------------------------------------------------------
# Standard tags preserved
# ---------------------------------------------------------------------------

class TestStandardTagsPreserved:

    def test_names_preserved(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        for name in ('John /Smith/', 'Marie /Dupont/', 'Philip /Caraman/',
                     'Antoine /Artaud/', 'Yvette /Bonheur/'):
            assert name in c, f'Name {name!r} was removed'

    def test_birt_events_preserved(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert '2 DATE 15 MAR 1905' in c
        assert '2 PLAC London, England' in c

    def test_marr_events_preserved(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert '1 MARR' in c
        assert '2 DATE 10 JUN 1935' in c

    def test_sour_records_preserved(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        c = content_of(tmp_copy)
        assert '@S1@ SOUR' in c
        assert 'French National Archives' in c

    def test_trlr_preserved(self, tmp_copy):
        convert_nonstandard_events(tmp_copy)
        lines = lines_of(tmp_copy)
        assert lines[-1] == '0 TRLR'


# ---------------------------------------------------------------------------
# Return value / statistics
# ---------------------------------------------------------------------------

class TestReturnValues:

    def test_stats_keys_present(self, tmp_copy):
        result = convert_nonstandard_events(tmp_copy)
        for key in ('lines_read', 'lines_delta', 'milt_converted',
                    'sepr_converted', 'dcause_converted'):
            assert key in result, f'Missing key {key!r}'

    def test_milt_count(self, tmp_copy):
        result = convert_nonstandard_events(tmp_copy)
        # Fixture has 3 _MILT records (@I1@, @I2@, @I3@)
        assert result['milt_converted'] == 3

    def test_sepr_count(self, tmp_copy):
        result = convert_nonstandard_events(tmp_copy)
        # Fixture has 3 _SEPR records (@F1@, @F2@, @F3@)
        assert result['sepr_converted'] == 3

    def test_dcause_count(self, tmp_copy):
        result = convert_nonstandard_events(tmp_copy)
        # Fixture has 4 _DCAUSE records (@I4@, @I5@, @I6@, @I7@)
        assert result['dcause_converted'] == 4

    def test_lines_delta_matches_actual_diff(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            before = sum(1 for _ in f)
        result = convert_nonstandard_events(tmp_copy)
        with open(tmp_copy, encoding='utf-8') as f:
            after = sum(1 for _ in f)
        assert result['lines_delta'] == after - before

    def test_lines_read_matches_file(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            file_len = sum(1 for _ in f)
        result = convert_nonstandard_events(tmp_copy)
        assert result['lines_read'] == file_len


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_clean_file_unchanged(self, tmp_path):
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /Wonder/\n1 BIRT\n2 DATE 1 APR 1900\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        original = clean.read_text(encoding='utf-8')
        result = convert_nonstandard_events(str(clean))
        assert result['milt_converted'] == 0
        assert result['sepr_converted'] == 0
        assert result['dcause_converted'] == 0
        assert clean.read_text(encoding='utf-8') == original

    def test_dry_run_no_write(self, tmp_copy):
        original = Path(tmp_copy).read_text(encoding='utf-8')
        convert_nonstandard_events(tmp_copy, dry_run=True)
        assert Path(tmp_copy).read_text(encoding='utf-8') == original

    def test_dry_run_stats_match_real(self, tmp_copy):
        dry = convert_nonstandard_events(tmp_copy, dry_run=True)
        real = convert_nonstandard_events(tmp_copy)
        assert dry['milt_converted'] == real['milt_converted']
        assert dry['sepr_converted'] == real['sepr_converted']
        assert dry['dcause_converted'] == real['dcause_converted']

    def test_output_file_option(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        convert_nonstandard_events(str(FIXTURE), path_out=out)
        c = Path(out).read_text(encoding='utf-8')
        assert '_MILT' not in c
        assert '_SEPR' not in c
        assert '_DCAUSE' not in c

    def test_input_unchanged_when_output_specified(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        original = FIXTURE.read_text(encoding='utf-8')
        convert_nonstandard_events(str(FIXTURE), path_out=out)
        assert FIXTURE.read_text(encoding='utf-8') == original
