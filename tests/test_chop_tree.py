"""
Tests for chop_tree.py

Chops at @I1@ (Alice Perigo) using tests/fixtures/chop_test.ged.

Tree layout:

    @I10@ Edward Smith ──┐
                          ├─ @F3@ ─→ @I4@ George Smith ──┐
    @I11@ Mary White  ──┘                                   │
                                                             ├─ @F2@ ─→ @I1@ Alice Perigo (THE CHOP POINT)
    @I12@ William Jones ─┐                                  │                   │
                          ├─ @F6@ ─→ @I5@ Helen Jones ──┘            │
    @I13@ Rose Taylor  ─┘                                             ├─ @F1@
                                                             @I6@ David Smith (sibling)    │
                                                                                            │
    @I14@ Frank Perigo ─┐                                        @I2@ Robert Perigo ──────┘
                         ├─ @F7@ ─→ @I2@ Robert Perigo
    @I15@ Edith Perigo ─┘                                                   │
                                                                         @F4@ ─→ @I3@ Carol Perigo
                                                                  @I7@ Michael Brown ─────┘
                                                                                      │
                                                                                   @I8@ Emma Brown

File A (descendants of @I1@):
  INDIs kept : @I1@, @I2@ (spouse), @I3@ (child), @I7@ (child's spouse), @I8@ (grandchild)
  FAMs kept  : @F1@ (marriage), @F4@ (child's marriage)
  @I1@ FAMC  : stripped (Alice becomes a root)

File B (ancestors + siblings + spouse of @I1@):
  INDIs kept : @I1@, @I2@ (spouse), @I4@, @I5@ (parents), @I6@ (sibling),
               @I10@, @I11@ (paternal grandparents), @I12@, @I13@ (maternal grandparents)
  FAMs kept  : @F1@ (marriage, CHIL stripped), @F2@ (birth family),
               @F3@ (paternal grandparents), @F6@ (maternal grandparents)
  @I2@ FAMC  : stripped (spouse's parents @I14@/@I15@ not included)
  @I6@ FAMS  : stripped (sibling's marriage @F5@ not included)

Sources:
  @S1@ cited by @I1@  → both files
  @S2@ cited by @I3@  → File A only
"""

import re
import shutil
from pathlib import Path

import pytest

# Module under test — not implemented yet; tests are written first.
from chop_tree import chop_tree

FIXTURE = Path(__file__).parent / 'fixtures' / 'chop_test.ged'
CHOP_XREF = '@I1@'


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _parse_records(path: str) -> dict[str, list[str]]:
    """
    Return a dict mapping each level-0 xref (or tag for HEAD/TRLR) to its
    lines (including the opening line), as raw strings without newlines.
    """
    records: dict[str, list[str]] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    level0_re = re.compile(r'^0 (@[^@]+@) (\S+)|^0 (\S+)')

    for raw in Path(path).read_text(encoding='utf-8').splitlines():
        m = level0_re.match(raw)
        if m:
            if current_key is not None:
                records[current_key] = current_lines
            if m.group(1):   # xref record
                current_key = m.group(1)
            else:             # keyword record (HEAD, TRLR)
                current_key = m.group(3)
            current_lines = [raw]
        else:
            if current_key is not None:
                current_lines.append(raw)

    if current_key is not None:
        records[current_key] = current_lines

    return records


def indi_present(path: str, xref: str) -> bool:
    return xref in _parse_records(path)


def fam_present(path: str, xref: str) -> bool:
    return xref in _parse_records(path)


def record_has_line(path: str, xref: str, fragment: str) -> bool:
    """Return True if any line in the record contains fragment."""
    records = _parse_records(path)
    if xref not in records:
        return False
    return any(fragment in line for line in records[xref])


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def chopped(tmp_path) -> tuple[str, str]:
    """Run chop_tree and return (file_a_path, file_b_path)."""
    src = str(FIXTURE)
    out_a = str(tmp_path / 'descendants.ged')
    out_b = str(tmp_path / 'ancestors.ged')
    chop_tree(src, CHOP_XREF, out_a, out_b)
    return out_a, out_b


@pytest.fixture()
def file_a(chopped) -> str:
    return chopped[0]


@pytest.fixture()
def file_b(chopped) -> str:
    return chopped[1]


# ---------------------------------------------------------------------------
# Input file is never modified
# ---------------------------------------------------------------------------

class TestOriginalUnchanged:
    def test_original_file_unchanged(self, tmp_path):
        src = tmp_path / 'orig.ged'
        shutil.copy(FIXTURE, src)
        original = src.read_text(encoding='utf-8')
        out_a = str(tmp_path / 'a.ged')
        out_b = str(tmp_path / 'b.ged')
        chop_tree(str(src), CHOP_XREF, out_a, out_b)
        assert src.read_text(encoding='utf-8') == original

    def test_both_output_files_created(self, chopped):
        out_a, out_b = chopped
        assert Path(out_a).exists()
        assert Path(out_b).exists()


# ---------------------------------------------------------------------------
# File A — individuals
# ---------------------------------------------------------------------------

class TestFileAIndividuals:
    def test_chop_person_present(self, file_a):
        assert indi_present(file_a, '@I1@')

    def test_spouse_present(self, file_a):
        assert indi_present(file_a, '@I2@')

    def test_child_present(self, file_a):
        assert indi_present(file_a, '@I3@')

    def test_childs_spouse_present(self, file_a):
        assert indi_present(file_a, '@I7@')

    def test_grandchild_present(self, file_a):
        assert indi_present(file_a, '@I8@')

    def test_father_absent(self, file_a):
        assert not indi_present(file_a, '@I4@')

    def test_mother_absent(self, file_a):
        assert not indi_present(file_a, '@I5@')

    def test_sibling_absent(self, file_a):
        assert not indi_present(file_a, '@I6@')

    def test_siblings_spouse_absent(self, file_a):
        assert not indi_present(file_a, '@I9@')

    def test_paternal_grandparents_absent(self, file_a):
        assert not indi_present(file_a, '@I10@')
        assert not indi_present(file_a, '@I11@')

    def test_maternal_grandparents_absent(self, file_a):
        assert not indi_present(file_a, '@I12@')
        assert not indi_present(file_a, '@I13@')

    def test_spouses_parents_absent(self, file_a):
        assert not indi_present(file_a, '@I14@')
        assert not indi_present(file_a, '@I15@')


# ---------------------------------------------------------------------------
# File A — family records
# ---------------------------------------------------------------------------

class TestFileAFamilies:
    def test_marriage_family_present(self, file_a):
        assert fam_present(file_a, '@F1@')

    def test_childs_marriage_family_present(self, file_a):
        assert fam_present(file_a, '@F4@')

    def test_birth_family_absent(self, file_a):
        assert not fam_present(file_a, '@F2@')

    def test_paternal_grandparents_family_absent(self, file_a):
        assert not fam_present(file_a, '@F3@')

    def test_siblings_marriage_absent(self, file_a):
        assert not fam_present(file_a, '@F5@')

    def test_maternal_grandparents_family_absent(self, file_a):
        assert not fam_present(file_a, '@F6@')

    def test_spouses_birth_family_absent(self, file_a):
        assert not fam_present(file_a, '@F7@')


# ---------------------------------------------------------------------------
# File A — pointer integrity
# ---------------------------------------------------------------------------

class TestFileAPointers:
    def test_chop_person_has_no_famc(self, file_a):
        assert not record_has_line(file_a, '@I1@', 'FAMC')

    def test_chop_person_has_fams(self, file_a):
        assert record_has_line(file_a, '@I1@', 'FAMS @F1@')

    def test_marriage_fam_has_chil(self, file_a):
        assert record_has_line(file_a, '@F1@', 'CHIL @I3@')

    def test_marriage_fam_has_husb_and_wife(self, file_a):
        assert record_has_line(file_a, '@F1@', 'HUSB @I2@')
        assert record_has_line(file_a, '@F1@', 'WIFE @I1@')

    def test_child_famc_points_to_included_family(self, file_a):
        assert record_has_line(file_a, '@I3@', 'FAMC @F1@')

    def test_grandchild_famc_points_to_included_family(self, file_a):
        assert record_has_line(file_a, '@I8@', 'FAMC @F4@')

    def test_no_dangling_pointers_to_absent_indis(self, file_a):
        absent = {'@I4@', '@I5@', '@I6@', '@I9@', '@I10@', '@I11@', '@I12@', '@I13@'}
        content = Path(file_a).read_text(encoding='utf-8')
        for xref in absent:
            assert xref not in content, f'Dangling pointer to absent {xref} in file_a'

    def test_no_dangling_pointers_to_absent_fams(self, file_a):
        absent = {'@F2@', '@F3@', '@F5@', '@F6@', '@F7@'}
        content = Path(file_a).read_text(encoding='utf-8')
        for xref in absent:
            assert xref not in content, f'Dangling pointer to absent {xref} in file_a'


# ---------------------------------------------------------------------------
# File B — individuals
# ---------------------------------------------------------------------------

class TestFileBIndividuals:
    def test_chop_person_present(self, file_b):
        assert indi_present(file_b, '@I1@')

    def test_spouse_present(self, file_b):
        assert indi_present(file_b, '@I2@')

    def test_father_present(self, file_b):
        assert indi_present(file_b, '@I4@')

    def test_mother_present(self, file_b):
        assert indi_present(file_b, '@I5@')

    def test_sibling_present(self, file_b):
        assert indi_present(file_b, '@I6@')

    def test_paternal_grandparents_present(self, file_b):
        assert indi_present(file_b, '@I10@')
        assert indi_present(file_b, '@I11@')

    def test_maternal_grandparents_present(self, file_b):
        assert indi_present(file_b, '@I12@')
        assert indi_present(file_b, '@I13@')

    def test_child_absent(self, file_b):
        assert not indi_present(file_b, '@I3@')

    def test_childs_spouse_absent(self, file_b):
        assert not indi_present(file_b, '@I7@')

    def test_grandchild_absent(self, file_b):
        assert not indi_present(file_b, '@I8@')

    def test_siblings_spouse_absent(self, file_b):
        assert not indi_present(file_b, '@I9@')

    def test_spouses_parents_absent(self, file_b):
        assert not indi_present(file_b, '@I14@')
        assert not indi_present(file_b, '@I15@')


# ---------------------------------------------------------------------------
# File B — family records
# ---------------------------------------------------------------------------

class TestFileBFamilies:
    def test_birth_family_present(self, file_b):
        assert fam_present(file_b, '@F2@')

    def test_marriage_family_present(self, file_b):
        assert fam_present(file_b, '@F1@')

    def test_paternal_grandparents_family_present(self, file_b):
        assert fam_present(file_b, '@F3@')

    def test_maternal_grandparents_family_present(self, file_b):
        assert fam_present(file_b, '@F6@')

    def test_childs_marriage_absent(self, file_b):
        assert not fam_present(file_b, '@F4@')

    def test_siblings_marriage_absent(self, file_b):
        assert not fam_present(file_b, '@F5@')

    def test_spouses_birth_family_absent(self, file_b):
        assert not fam_present(file_b, '@F7@')


# ---------------------------------------------------------------------------
# File B — pointer integrity
# ---------------------------------------------------------------------------

class TestFileBPointers:
    def test_chop_person_has_famc(self, file_b):
        assert record_has_line(file_b, '@I1@', 'FAMC @F2@')

    def test_chop_person_has_fams(self, file_b):
        assert record_has_line(file_b, '@I1@', 'FAMS @F1@')

    def test_marriage_fam_has_no_chil(self, file_b):
        """Children of @I1@ must be stripped from the marriage FAM in file B."""
        assert not record_has_line(file_b, '@F1@', 'CHIL')

    def test_marriage_fam_retains_husb_and_wife(self, file_b):
        assert record_has_line(file_b, '@F1@', 'HUSB @I2@')
        assert record_has_line(file_b, '@F1@', 'WIFE @I1@')

    def test_birth_family_has_both_chil(self, file_b):
        """Both @I1@ and sibling @I6@ must appear as CHIL in @F2@."""
        assert record_has_line(file_b, '@F2@', 'CHIL @I1@')
        assert record_has_line(file_b, '@F2@', 'CHIL @I6@')

    def test_sibling_has_no_fams(self, file_b):
        """Sibling's own marriage must be stripped."""
        assert not record_has_line(file_b, '@I6@', 'FAMS')

    def test_spouse_has_no_famc(self, file_b):
        """Spouse's birth family must be stripped."""
        assert not record_has_line(file_b, '@I2@', 'FAMC')

    def test_spouse_retains_fams_to_chop_person(self, file_b):
        assert record_has_line(file_b, '@I2@', 'FAMS @F1@')

    def test_father_has_famc(self, file_b):
        """Father's birth family (paternal grandparents) must be in file B."""
        assert record_has_line(file_b, '@I4@', 'FAMC @F3@')

    def test_no_dangling_pointers_to_absent_indis(self, file_b):
        absent = {'@I3@', '@I7@', '@I8@', '@I9@', '@I14@', '@I15@'}
        content = Path(file_b).read_text(encoding='utf-8')
        for xref in absent:
            assert xref not in content, f'Dangling pointer to absent {xref} in file_b'

    def test_no_dangling_pointers_to_absent_fams(self, file_b):
        absent = {'@F4@', '@F5@', '@F7@'}
        content = Path(file_b).read_text(encoding='utf-8')
        for xref in absent:
            assert xref not in content, f'Dangling pointer to absent {xref} in file_b'


# ---------------------------------------------------------------------------
# Source records
# ---------------------------------------------------------------------------

class TestSources:
    def test_source_cited_by_chop_person_in_file_a(self, file_a):
        """@S1@ is cited in @I1@'s BIRT — must appear in file A."""
        assert '@S1@' in Path(file_a).read_text(encoding='utf-8')

    def test_source_cited_by_chop_person_in_file_b(self, file_b):
        """@S1@ is cited in @I1@'s BIRT — must also appear in file B."""
        assert '@S1@' in Path(file_b).read_text(encoding='utf-8')

    def test_source_only_cited_by_descendant_in_file_a(self, file_a):
        """@S2@ is only cited by @I3@ (child) — must appear in file A."""
        assert '@S2@' in Path(file_a).read_text(encoding='utf-8')

    def test_source_only_cited_by_descendant_absent_from_file_b(self, file_b):
        """@S2@ is only cited by @I3@ (child, excluded from file B) — must not appear."""
        assert '@S2@' not in Path(file_b).read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# Structure validity
# ---------------------------------------------------------------------------

class TestStructureValidity:
    @pytest.mark.parametrize('fixture_name', ['file_a', 'file_b'])
    def test_all_lines_are_valid_gedcom(self, fixture_name, request):
        path = request.getfixturevalue(fixture_name)
        level_re = re.compile(r'^\d+ ')
        bad = []
        for i, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
            if line and not level_re.match(line):
                bad.append((i, line))
        assert bad == [], f'Malformed lines in {fixture_name}: {bad[:5]}'

    @pytest.mark.parametrize('fixture_name', ['file_a', 'file_b'])
    def test_has_head_and_trlr(self, fixture_name, request):
        path = request.getfixturevalue(fixture_name)
        content = Path(path).read_text(encoding='utf-8')
        assert content.startswith('0 HEAD')
        assert content.rstrip().endswith('0 TRLR')

    @pytest.mark.parametrize('fixture_name', ['file_a', 'file_b'])
    def test_chop_person_name_preserved(self, fixture_name, request):
        path = request.getfixturevalue(fixture_name)
        assert 'Alice /Perigo/' in Path(path).read_text(encoding='utf-8')
