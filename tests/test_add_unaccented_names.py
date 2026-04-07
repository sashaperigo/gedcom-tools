"""
Tests for add_unaccented_names.py

Covers:
  - _remove_accents: unit tests for transliteration
  - add_unaccented_names: integration tests (insertion, dedup, dry-run, counts)
"""
import shutil
import textwrap
from pathlib import Path

import pytest

from add_unaccented_names import _remove_accents, add_unaccented_names

FIXTURE = Path(__file__).parent / 'fixtures' / 'accented_names.ged'


def write_ged(tmp_path, content: str) -> Path:
    p = tmp_path / 'test.ged'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


@pytest.fixture()
def tmp_copy(tmp_path):
    dest = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, dest)
    return str(dest)


# ---------------------------------------------------------------------------
# _remove_accents — unit tests
# ---------------------------------------------------------------------------

class TestRemoveAccents:

    def test_plain_ascii_unchanged(self):
        assert _remove_accents('John /Smith/') == 'John /Smith/'

    def test_e_acute_stripped(self):
        assert _remove_accents('Pérez') == 'Perez'

    def test_o_acute_stripped(self):
        assert _remove_accents('Faraón') == 'Faraon'

    def test_o_umlaut_expands_to_oe(self):
        assert _remove_accents('Köttner') == 'Koettner'

    def test_O_umlaut_expands_to_Oe(self):
        assert _remove_accents('Österreich') == 'Oesterreich'

    def test_u_umlaut_expands_to_ue(self):
        assert _remove_accents('Müller') == 'Mueller'

    def test_a_umlaut_expands_to_ae(self):
        assert _remove_accents('Bräuer') == 'Braeuer'

    def test_e_grave_stripped(self):
        assert _remove_accents('Maréchal') == 'Marechal'

    def test_i_with_diaeresis_stripped(self):
        assert _remove_accents('Anaïs') == 'Anais'

    def test_c_cedilla_stripped(self):
        assert _remove_accents('François') == 'Francois'

    def test_mixed_umlauts_and_accents(self):
        assert _remove_accents('José /García/') == 'Jose /Garcia/'

    def test_surname_slashes_preserved(self):
        result = _remove_accents('Manon /Pérez/')
        assert result == 'Manon /Perez/'
        assert result.startswith('Manon /')
        assert result.endswith('/')


# ---------------------------------------------------------------------------
# add_unaccented_names — integration tests
# ---------------------------------------------------------------------------

class TestAddUnaccentedNames:

    def test_accented_name_gets_aka(self, tmp_copy):
        add_unaccented_names(tmp_copy)
        c = Path(tmp_copy).read_text(encoding='utf-8')
        assert '1 NAME Manon /Perez/' in c
        assert '2 TYPE AKA' in c

    def test_umlaut_o_expands_to_oe(self, tmp_copy):
        add_unaccented_names(tmp_copy)
        c = Path(tmp_copy).read_text(encoding='utf-8')
        assert '1 NAME Klara /Koettner/' in c

    def test_plain_name_unchanged(self, tmp_copy):
        original = Path(tmp_copy).read_text(encoding='utf-8')
        add_unaccented_names(tmp_copy)
        c = Path(tmp_copy).read_text(encoding='utf-8')
        # @I3@ John Smith should have no new NAME line added
        lines = c.splitlines()
        i3_idx = lines.index('0 @I3@ INDI')
        # Next record starts at the next level-0 line
        next_record = next(
            i for i, l in enumerate(lines) if i > i3_idx and l.startswith('0 ')
        )
        i3_block = lines[i3_idx:next_record]
        name_lines = [l for l in i3_block if l.startswith('1 NAME')]
        assert len(name_lines) == 1

    def test_no_duplicate_aka_added(self, tmp_copy):
        """@I7@ already has Jose /Garcia/ as AKA — should not be added again."""
        add_unaccented_names(tmp_copy)
        c = Path(tmp_copy).read_text(encoding='utf-8')
        assert c.count('1 NAME Jose /Garcia/') == 1

    def test_aka_inserted_after_name_children(self, tmp_copy):
        """AKA for @I1@ must come after GIVN/SURN children, not between them."""
        add_unaccented_names(tmp_copy)
        lines = Path(tmp_copy).read_text(encoding='utf-8').splitlines()
        # Find the AKA for Pérez
        aka_idx = next(i for i, l in enumerate(lines) if l == '1 NAME Manon /Perez/')
        # The line immediately before the AKA is the last child of the original NAME block
        assert lines[aka_idx - 1] == '2 SURN Pérez'

    def test_aka_has_type_tag(self, tmp_copy):
        add_unaccented_names(tmp_copy)
        lines = Path(tmp_copy).read_text(encoding='utf-8').splitlines()
        aka_idx = next(i for i, l in enumerate(lines) if l == '1 NAME Manon /Perez/')
        assert lines[aka_idx + 1] == '2 TYPE AKA'

    def test_original_name_preserved(self, tmp_copy):
        add_unaccented_names(tmp_copy)
        c = Path(tmp_copy).read_text(encoding='utf-8')
        assert '1 NAME Manon /Pérez/' in c
        assert '1 NAME Klara /Köttner/' in c

    def test_name_with_children_aka_after_block(self, tmp_copy):
        """@I8@ has GIVN/SURN/NOTE children — AKA goes after all of them."""
        add_unaccented_names(tmp_copy)
        lines = Path(tmp_copy).read_text(encoding='utf-8').splitlines()
        aka_idx = next(i for i, l in enumerate(lines) if l == '1 NAME Euphemie /Giulietti/')
        # Line before the AKA should be the NOTE child (last child of original NAME)
        assert lines[aka_idx - 1] == '2 NOTE Born in Smyrna'

    # ── Return values ────────────────────────────────────────────────────────

    def test_names_added_count(self, tmp_copy):
        result = add_unaccented_names(tmp_copy)
        # @I1@ Pérez, @I2@ Köttner, @I4@ Faraón, @I5@ Maréchal, @I6@ Anaïs, @I8@ Euphémie
        # @I7@ José/García already has AKA → skipped
        assert result['names_added'] == 6

    def test_lines_delta_matches_added(self, tmp_copy):
        result = add_unaccented_names(tmp_copy)
        # Each AKA adds 2 lines (NAME + TYPE)
        assert result['lines_delta'] == result['names_added'] * 2

    def test_lines_read_correct(self, tmp_copy):
        before = sum(1 for _ in open(tmp_copy, encoding='utf-8'))
        result = add_unaccented_names(tmp_copy)
        assert result['lines_read'] == before

    # ── Dry-run ──────────────────────────────────────────────────────────────

    def test_dry_run_no_write(self, tmp_copy):
        original = Path(tmp_copy).read_text(encoding='utf-8')
        add_unaccented_names(tmp_copy, dry_run=True)
        assert Path(tmp_copy).read_text(encoding='utf-8') == original

    def test_dry_run_correct_count(self, tmp_copy):
        dry = add_unaccented_names(tmp_copy, dry_run=True)
        real_copy = str(Path(tmp_copy).parent / 'real.ged')
        shutil.copy(tmp_copy, real_copy)
        real = add_unaccented_names(real_copy)
        assert dry['names_added'] == real['names_added']

    # ── Output file ──────────────────────────────────────────────────────────

    def test_output_file_written(self, tmp_path):
        out = str(tmp_path / 'out.ged')
        add_unaccented_names(str(FIXTURE), path_out=out)
        c = Path(out).read_text(encoding='utf-8')
        assert '1 NAME Manon /Perez/' in c

    def test_input_unchanged_when_output_specified(self, tmp_path):
        out = str(tmp_path / 'out.ged')
        original = FIXTURE.read_text(encoding='utf-8')
        add_unaccented_names(str(FIXTURE), path_out=out)
        assert FIXTURE.read_text(encoding='utf-8') == original
