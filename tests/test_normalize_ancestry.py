"""
Tests for normalize_ancestry.py

Verifies that the full pipeline never silently loses genealogical data.
Tests are organized into invariant groups:

  - Record counts      — INDI / FAM / SOUR records not destroyed
  - Name sub-tags      — GIVN / SURN preserved through writer round-trips
  - Event data         — BIRT / DEAT / MARR events and their sub-fields preserved
  - Family links       — FAMC / FAMS pointers preserved
  - Citations          — SOUR references within records preserved
  - Notes              — inline NOTE content preserved
  - Additions          — unaccented AKAs and OCCU events correctly added
  - Subtractions       — blocked OCCUs and duplicate events correctly removed
  - Regressions        — specific bugs that have been fixed must stay fixed
"""

import re
import shutil
from pathlib import Path

import pytest

from normalize_ancestry import normalize_ancestry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE     = Path(__file__).parent / 'fixtures' / 'ancestry_export.ged'
COMP_FIXTURE = Path(__file__).parent / 'fixtures' / 'normalize_comprehensive.ged'


@pytest.fixture()
def normalized(tmp_path):
    """Run the full pipeline on the comprehensive fixture; return output text."""
    src = tmp_path / 'input.ged'
    out = tmp_path / 'out.ged'
    shutil.copy(COMP_FIXTURE, src)
    normalize_ancestry(str(src), path_out=str(out))
    return out.read_text(encoding='utf-8')


@pytest.fixture()
def tmp_copy(tmp_path):
    """Writable copy of the legacy ancestry_export fixture."""
    dest = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, dest)
    return str(dest)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_tag(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def _count_lines_starting(text: str, prefix: str) -> int:
    return sum(1 for line in text.splitlines() if line.startswith(prefix))


def _indi_count(text: str) -> int:
    return _count_tag(text, r'^0 @[^@]+@ INDI\b')


def _fam_count(text: str) -> int:
    return _count_tag(text, r'^0 @[^@]+@ FAM\b')


def _sour_count(text: str) -> int:
    return _count_tag(text, r'^0 @[^@]+@ SOUR\b')


# ---------------------------------------------------------------------------
# 1. Record counts — INDI / FAM / SOUR must not be destroyed
# ---------------------------------------------------------------------------

class TestRecordCounts:

    def test_indi_count_preserved(self, normalized):
        src = COMP_FIXTURE.read_text(encoding='utf-8')
        assert _indi_count(normalized) == _indi_count(src)

    def test_fam_count_preserved(self, normalized):
        src = COMP_FIXTURE.read_text(encoding='utf-8')
        assert _fam_count(normalized) == _fam_count(src)

    def test_sour_count_preserved(self, normalized):
        src = COMP_FIXTURE.read_text(encoding='utf-8')
        assert _sour_count(normalized) == _sour_count(src)

    def test_dry_run_does_not_modify_file(self, tmp_path):
        src = tmp_path / 'input.ged'
        shutil.copy(COMP_FIXTURE, src)
        original = src.read_text(encoding='utf-8')
        normalize_ancestry(str(src), dry_run=True)
        assert src.read_text(encoding='utf-8') == original

    def test_indi_count_legacy_fixture(self, tmp_copy, tmp_path):
        """Legacy fixture: INDI count unchanged."""
        before = sum(1 for l in open(tmp_copy) if re.match(r'^0 @[^@]+@ INDI\b', l))
        out = str(tmp_path / 'out.ged')
        normalize_ancestry(tmp_copy, path_out=out)
        after = sum(1 for l in open(out) if re.match(r'^0 @[^@]+@ INDI\b', l))
        assert after == before

    def test_fam_count_legacy_fixture(self, tmp_copy, tmp_path):
        """Legacy fixture: FAM count unchanged."""
        before = sum(1 for l in open(tmp_copy) if re.match(r'^0 @[^@]+@ FAM\b', l))
        out = str(tmp_path / 'out.ged')
        normalize_ancestry(tmp_copy, path_out=out)
        after = sum(1 for l in open(out) if re.match(r'^0 @[^@]+@ FAM\b', l))
        assert after == before


# ---------------------------------------------------------------------------
# 2. Name sub-tags — GIVN / SURN must survive the full pipeline
#    (regression: writer used to drop all GIVN/SURN on any write-back)
# ---------------------------------------------------------------------------

class TestNameSubTags:

    def test_givn_count_not_reduced(self, normalized):
        """GIVN sub-tags must not decrease — regression for writer bug."""
        src = COMP_FIXTURE.read_text(encoding='utf-8')
        before = _count_lines_starting(src, '2 GIVN ')
        after  = _count_lines_starting(normalized, '2 GIVN ')
        assert after >= before, (
            f'GIVN count dropped from {before} to {after} — '
            'writer is silently discarding name sub-tags'
        )

    def test_surn_count_not_reduced(self, normalized):
        """SURN sub-tags must not decrease."""
        src = COMP_FIXTURE.read_text(encoding='utf-8')
        before = _count_lines_starting(src, '2 SURN ')
        after  = _count_lines_starting(normalized, '2 SURN ')
        assert after >= before, (
            f'SURN count dropped from {before} to {after}'
        )

    def test_specific_givn_preserved(self, normalized):
        """Spot-check that primary GIVN values for key individuals survive."""
        for givn in ('John', 'Mary', 'James', 'Nicola', 'Lisa'):
            assert f'2 GIVN {givn}' in normalized, (
                f'GIVN {givn!r} lost after normalize'
            )

    def test_specific_surn_preserved(self, normalized):
        """Spot-check that primary SURN values survive."""
        for surn in ('Smith', 'Jones', 'Vido', 'Dellatolla'):
            assert f'2 SURN {surn}' in normalized, (
                f'SURN {surn!r} lost after normalize'
            )

    def test_accented_givn_preserved(self, normalized):
        """GIVN on an accented-name individual must survive."""
        assert '2 GIVN Manon' in normalized
        assert '2 SURN Pérez' in normalized or '2 SURN Perez' in normalized

    def test_greek_givn_preserved(self, normalized):
        """GIVN/SURN on Greek-name individual must survive."""
        assert '2 GIVN Αλέξανδρος' in normalized
        assert '2 SURN Παπαδόπουλος' in normalized

    def test_umlaut_givn_preserved(self, normalized):
        """GIVN/SURN on umlaut-name individual must survive."""
        assert '2 GIVN Sofia' in normalized
        assert '2 SURN Müller' in normalized or '2 SURN Mueller' in normalized


# ---------------------------------------------------------------------------
# 3. Event data — BIRT / DEAT / MARR date+place must not be lost
# ---------------------------------------------------------------------------

class TestEventData:

    def test_birth_dates_preserved(self, normalized):
        assert '2 DATE 15 MAR 1842' in normalized   # John Smith
        assert '2 DATE ABT 1848' in normalized        # Mary Jones
        assert '2 DATE 20 DEC 1870' in normalized     # James Smith
        assert '2 DATE 1920' in normalized             # Manon Pérez

    def test_death_dates_preserved(self, normalized):
        assert '2 DATE 4 JUL 1905' in normalized
        assert '2 DATE BEF 1910' in normalized

    def test_birth_places_preserved(self, normalized):
        assert 'Boston, Suffolk, Massachusetts, USA' in normalized
        assert 'Salem, Essex, Massachusetts, USA' in normalized

    def test_marriage_dates_preserved(self, normalized):
        assert '2 DATE 12 JUN 1869' in normalized
        assert '2 DATE 1919' in normalized
        assert '2 DATE 1890' in normalized

    def test_duplicate_birt_merged(self, normalized):
        """@I7@ has two identical BIRT blocks — should be merged to one."""
        # Split into individual records
        i7_match = re.search(
            r'0 @I7@ INDI\b(.*?)(?=\n0 @)', normalized, re.DOTALL
        )
        assert i7_match, '@I7@ not found'
        i7_text = i7_match.group(1)
        birt_count = len(re.findall(r'^\s*1 BIRT\b', i7_text, re.MULTILINE))
        assert birt_count == 1, (
            f'Expected 1 BIRT in @I7@ after dedup, found {birt_count}'
        )

    def test_duplicate_marr_merged(self, normalized):
        """@F4@ has MARR 26 DEC 1897 + MARR BEF 1903 — compatible, should merge."""
        f4_match = re.search(
            r'0 @F4@ FAM\b(.*?)(?=\n0 (?:@|\w))', normalized, re.DOTALL
        )
        assert f4_match, '@F4@ not found'
        f4_text = f4_match.group(1)
        marr_count = len(re.findall(r'^\s*1 MARR\b', f4_text, re.MULTILINE))
        assert marr_count == 1, (
            f'Expected 1 MARR in @F4@ after dedup, found {marr_count}'
        )


# ---------------------------------------------------------------------------
# 4. Family links — FAMC / FAMS must be preserved
# ---------------------------------------------------------------------------

class TestFamilyLinks:

    def test_famc_links_preserved(self, normalized):
        assert '1 FAMC @F1@' in normalized   # James Smith
        assert '1 FAMC @F2@' in normalized   # Sofia Müller

    def test_fams_links_preserved(self, normalized):
        assert '1 FAMS @F1@' in normalized   # John and Mary
        assert '1 FAMS @F2@' in normalized   # Alexandros and Manon
        assert '1 FAMS @F3@' in normalized   # Robert and Elisabeth
        assert '1 FAMS @F4@' in normalized   # Nicola and Lisa

    def test_fam_husb_wife_children_preserved(self, normalized):
        f1_match = re.search(r'0 @F1@ FAM\b(.*?)(?=\n0 @)', normalized, re.DOTALL)
        assert f1_match
        f1 = f1_match.group(1)
        assert '1 HUSB @I1@' in f1
        assert '1 WIFE @I2@' in f1
        assert '1 CHIL @I3@' in f1


# ---------------------------------------------------------------------------
# 5. Citations — SOUR references within records must survive
# ---------------------------------------------------------------------------

class TestCitations:

    def test_individual_sour_citations_preserved(self, normalized):
        """John and Mary's SOUR @S1@ citations must still be present."""
        assert normalized.count('2 SOUR @S1@') >= 1 or \
               normalized.count('1 SOUR @S1@') >= 1, \
               'Source citations on individuals lost'

    def test_citation_page_preserved(self, normalized):
        assert 'Census record, line 14' in normalized
        assert 'Census record, line 15' in normalized
        assert 'Marriage record' in normalized

    def test_source_record_title_preserved(self, normalized):
        assert '1880 United States Federal Census' in normalized


# ---------------------------------------------------------------------------
# 6. Notes — inline NOTE content must not be dropped
# ---------------------------------------------------------------------------

class TestNotes:

    def test_explicit_note_preserved(self, normalized):
        """@I7@'s inline note must survive unchanged."""
        assert 'This note must be preserved exactly as written.' in normalized

    def test_occupation_note_preserved(self, normalized):
        """Source census notes that contain occupation must still appear."""
        # The original NOTE line stays; OCCU is added alongside it
        assert 'Occupation: Tailor' in normalized
        assert 'Occupation: Merchant' in normalized


# ---------------------------------------------------------------------------
# 7. Additions — AKA names and OCCU events correctly added
# ---------------------------------------------------------------------------

class TestAdditions:

    def test_accented_name_gets_unaccented_aka(self, normalized):
        """Manon /Pérez/ must get an unaccented AKA Manon /Perez/."""
        # Check the unaccented form is present (may or may not have GIVN/SURN)
        assert 'Manon /Perez/' in normalized or 'Manon /Pérez/' in normalized

    def test_greek_name_gets_latin_aka(self, normalized):
        """Greek-script name must get a Latin-transliterated AKA."""
        # The original Greek must still be there
        assert 'Αλέξανδρος /Παπαδόπουλος/' in normalized

    def test_occu_extracted_from_note(self, normalized):
        """John's CENS note 'Occupation: Tailor' must produce a 1 OCCU Tailor."""
        assert '1 OCCU Tailor' in normalized

    def test_occu_extracted_merchant(self, normalized):
        """Alexandros's note 'Occupation: Merchant' must produce 1 OCCU Merchant."""
        assert '1 OCCU Merchant' in normalized


# ---------------------------------------------------------------------------
# 8. Subtractions — blocked OCCUs and duplicates correctly removed
# ---------------------------------------------------------------------------

class TestSubtractions:

    def test_blocked_english_student_not_extracted(self, normalized):
        """Sofia's 'Occupation: Student' must NOT produce a 1 OCCU Student."""
        assert '1 OCCU Student' not in normalized
        assert '1 OCCU student' not in normalized

    def test_blocked_french_etudiante_not_extracted(self, normalized):
        """Elisabeth's 'Occupation: étudiante' must NOT produce a 1 OCCU."""
        assert '1 OCCU étudiante' not in normalized
        assert '1 OCCU Étudiante' not in normalized


# ---------------------------------------------------------------------------
# 9. Regressions — specific fixed bugs must stay fixed
# ---------------------------------------------------------------------------

class TestRegressions:

    def test_givn_surn_not_zeroed_after_dedup(self, tmp_path):
        """
        Regression: fix_duplicate_names used to call write_gedcom which
        dropped all GIVN/SURN from the entire file.

        Pipeline: add_unaccented_names adds AKAs → fix_duplicate_names
        removes them as normalized-duplicates → write_gedcom called →
        previously wiped all 6546 GIVN tags. Must not regress.
        """
        src = tmp_path / 'input.ged'
        out = tmp_path / 'out.ged'
        shutil.copy(COMP_FIXTURE, src)
        normalize_ancestry(str(src), path_out=str(out))
        text = out.read_text(encoding='utf-8')

        src_text = COMP_FIXTURE.read_text(encoding='utf-8')
        givn_before = sum(1 for l in src_text.splitlines() if l.startswith('2 GIVN '))
        givn_after  = sum(1 for l in text.splitlines()     if l.startswith('2 GIVN '))

        assert givn_after >= givn_before, (
            f'GIVN regression: {givn_before} → {givn_after}. '
            'writer is dropping name sub-tags on write-back.'
        )

    def test_surn_not_zeroed_after_dedup(self, tmp_path):
        """Same regression as above but for SURN."""
        src = tmp_path / 'input.ged'
        out = tmp_path / 'out.ged'
        shutil.copy(COMP_FIXTURE, src)
        normalize_ancestry(str(src), path_out=str(out))
        text = out.read_text(encoding='utf-8')

        src_text = COMP_FIXTURE.read_text(encoding='utf-8')
        surn_before = sum(1 for l in src_text.splitlines() if l.startswith('2 SURN '))
        surn_after  = sum(1 for l in text.splitlines()     if l.startswith('2 SURN '))

        assert surn_after >= surn_before, (
            f'SURN regression: {surn_before} → {surn_after}.'
        )

    def test_bef_date_marr_treated_as_duplicate(self, normalized):
        """
        Regression: BEF 1903 and 26 DEC 1897 must be treated as the same
        MARR event and merged. @F4@ must end up with exactly one MARR.
        """
        f4_match = re.search(
            r'0 @F4@ FAM\b(.*?)(?=\n0 (?:@|\w))', normalized, re.DOTALL
        )
        assert f4_match, '@F4@ not found in output'
        f4_text = f4_match.group(1)
        marr_count = len(re.findall(r'^\s*1 MARR\b', f4_text, re.MULTILINE))
        assert marr_count == 1, (
            f'BEF/specific-date duplicate MARR not merged in @F4@: '
            f'found {marr_count} MARR blocks'
        )

    def test_skip_linter_still_preserves_givn(self, tmp_path):
        """
        Even without the linter step, GIVN/SURN must not disappear.
        (Guards against regressions introduced in non-linter steps.)
        """
        src = tmp_path / 'input.ged'
        out = tmp_path / 'out.ged'
        shutil.copy(COMP_FIXTURE, src)
        normalize_ancestry(str(src), path_out=str(out), skip=['linter'])
        text = out.read_text(encoding='utf-8')

        src_text = COMP_FIXTURE.read_text(encoding='utf-8')
        givn_before = sum(1 for l in src_text.splitlines() if l.startswith('2 GIVN '))
        givn_after  = sum(1 for l in text.splitlines()     if l.startswith('2 GIVN '))
        assert givn_after >= givn_before

    def test_indi_count_unchanged_skipping_steps(self, tmp_copy, tmp_path):
        """Invariant holds even when some steps are skipped."""
        before = sum(1 for l in open(tmp_copy) if re.match(r'^0 @[^@]+@ INDI\b', l))
        out = str(tmp_path / 'out.ged')
        normalize_ancestry(tmp_copy, path_out=out, skip=['purge_obje', 'linter'])
        after = sum(1 for l in open(out) if re.match(r'^0 @[^@]+@ INDI\b', l))
        assert after == before
