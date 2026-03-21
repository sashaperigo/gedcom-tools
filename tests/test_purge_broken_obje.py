"""
Tests for purge_broken_obje.py

Uses tests/fixtures/obje_mixed.ged plus real temp files to simulate present/absent
media. The fixture references:

  Top-level OBJE records:
    @O1@  FILE exists_portrait.jpg       ← file will be created → KEPT
    @O2@  FILE missing_document.pdf      ← file absent           → REMOVED
    @O3@  FILE https://example.com/...   ← URL, never removed    → KEPT
    @O4@  FILE also_missing.png          ← file absent           → REMOVED

  OBJE pointer lines on @I1@:
    1 OBJE @O1@   → kept   (O1 has valid file)
    1 OBJE @O2@   → removed (O2 is broken)
    1 OBJE @O3@   → kept   (O3 is a URL)

  OBJE pointer line on @I2@:
    1 OBJE @O4@   → removed (O4 is broken)

  Inline OBJE subrecords on @I1@:
    FILE inline_exists.jpg   → file will be created → KEPT
    FILE inline_missing.jpg  → file absent           → REMOVED

  Inline OBJE subrecord on @F1@:
    FILE family_photo_exists.jpg → file will be created → KEPT
"""

import re
import shutil
from pathlib import Path

import pytest

from purge_broken_obje import purge_broken_obje

FIXTURE = Path(__file__).parent / 'fixtures' / 'obje_mixed.ged'

# Files we'll create in the fixture dir so they appear to "exist"
PRESENT_FILES = [
    'exists_portrait.jpg',
    'inline_exists.jpg',
    'family_photo_exists.jpg',
]
ABSENT_FILES = [
    'missing_document.pdf',
    'also_missing.png',
    'inline_missing.jpg',
]


@pytest.fixture()
def ged(tmp_path) -> Path:
    """
    Copy the fixture into tmp_path and create the 'present' media files there
    so path resolution works correctly.
    """
    dest = tmp_path / 'test.ged'
    shutil.copy(FIXTURE, dest)
    for name in PRESENT_FILES:
        (tmp_path / name).write_bytes(b'(placeholder)')
    return dest


# ---------------------------------------------------------------------------
# Fixture sanity
# ---------------------------------------------------------------------------

class TestFixture:
    def test_fixture_exists(self):
        assert FIXTURE.exists()

    def test_fixture_has_top_level_obje(self):
        content = FIXTURE.read_text(encoding='utf-8')
        assert '0 @O1@ OBJE' in content
        assert '0 @O2@ OBJE' in content
        assert '0 @O3@ OBJE' in content
        assert '0 @O4@ OBJE' in content

    def test_fixture_has_inline_obje(self):
        content = FIXTURE.read_text(encoding='utf-8')
        assert 'inline_exists.jpg' in content
        assert 'inline_missing.jpg' in content

    def test_fixture_has_pointer_obje(self):
        content = FIXTURE.read_text(encoding='utf-8')
        assert '1 OBJE @O1@' in content
        assert '1 OBJE @O2@' in content


# ---------------------------------------------------------------------------
# Return value / statistics
# ---------------------------------------------------------------------------

class TestReturnValues:
    def test_lines_read_matches_file_length(self, ged):
        n = sum(1 for _ in ged.open(encoding='utf-8'))
        result = purge_broken_obje(str(ged))
        assert result['lines_read'] == n

    def test_obje_removed_count(self, ged):
        # @O2@, @O4@ (top-level) + inline_missing.jpg = 3
        result = purge_broken_obje(str(ged))
        assert result['obje_removed'] == 3

    def test_broken_files_list(self, ged):
        result = purge_broken_obje(str(ged))
        assert set(result['broken_files']) == {
            'missing_document.pdf',
            'also_missing.png',
            'inline_missing.jpg',
        }

    def test_lines_removed_equals_diff(self, ged):
        before = sum(1 for _ in ged.open(encoding='utf-8'))
        result = purge_broken_obje(str(ged))
        after = sum(1 for _ in ged.open(encoding='utf-8'))
        assert result['lines_removed'] == before - after

    def test_no_broken_returns_zero(self, tmp_path):
        ged = tmp_path / 'clean.ged'
        img = tmp_path / 'photo.jpg'
        img.write_bytes(b'(placeholder)')
        ged.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @O1@ OBJE\n'
            '1 FILE photo.jpg\n'
            '2 FORM JPG\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = purge_broken_obje(str(ged))
        assert result['obje_removed'] == 0
        assert result['lines_removed'] == 0
        assert result['broken_files'] == []


# ---------------------------------------------------------------------------
# Top-level OBJE records
# ---------------------------------------------------------------------------

class TestTopLevelObje:
    def test_broken_top_level_records_removed(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '0 @O2@ OBJE' not in content
        assert '0 @O4@ OBJE' not in content

    def test_valid_top_level_record_kept(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '0 @O1@ OBJE' in content

    def test_url_top_level_record_kept(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '0 @O3@ OBJE' in content

    def test_child_lines_of_broken_record_removed(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert 'missing_document.pdf' not in content
        assert 'also_missing.png' not in content

    def test_child_lines_of_valid_record_kept(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert 'exists_portrait.jpg' in content
        assert 'Portrait' in content


# ---------------------------------------------------------------------------
# OBJE pointer references
# ---------------------------------------------------------------------------

class TestPointerReferences:
    def test_pointer_to_broken_record_removed(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '1 OBJE @O2@' not in content
        assert '1 OBJE @O4@' not in content

    def test_pointer_to_valid_record_kept(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '1 OBJE @O1@' in content

    def test_pointer_to_url_record_kept(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '1 OBJE @O3@' in content


# ---------------------------------------------------------------------------
# Inline OBJE subrecords
# ---------------------------------------------------------------------------

class TestInlineObje:
    def test_inline_with_missing_file_removed(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert 'inline_missing.jpg' not in content

    def test_inline_with_existing_file_kept(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert 'inline_exists.jpg' in content

    def test_inline_on_fam_record_kept(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert 'family_photo_exists.jpg' in content

    def test_inline_child_lines_removed_with_block(self, ged):
        """The TITL child of a broken inline OBJE must also be gone."""
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert 'Inline photo — file is missing' not in content

    def test_inline_child_lines_of_valid_block_kept(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert 'Inline photo — file exists' in content


# ---------------------------------------------------------------------------
# Output file / dry-run
# ---------------------------------------------------------------------------

class TestOutputAndDryRun:
    def test_output_to_separate_file(self, ged, tmp_path):
        out = tmp_path / 'clean.ged'
        purge_broken_obje(str(ged), path_out=str(out))
        assert out.exists()
        content = out.read_text(encoding='utf-8')
        assert '0 @O2@ OBJE' not in content
        assert '0 @O1@ OBJE' in content

    def test_input_unchanged_when_output_specified(self, ged, tmp_path):
        original = ged.read_text(encoding='utf-8')
        out = tmp_path / 'clean.ged'
        purge_broken_obje(str(ged), path_out=str(out))
        assert ged.read_text(encoding='utf-8') == original

    def test_dry_run_does_not_modify_file(self, ged):
        original = ged.read_text(encoding='utf-8')
        purge_broken_obje(str(ged), dry_run=True)
        assert ged.read_text(encoding='utf-8') == original

    def test_dry_run_returns_same_stats_as_real_run(self, ged, tmp_path):
        copy = tmp_path / 'copy.ged'
        shutil.copy(ged, copy)
        dry = purge_broken_obje(str(ged), dry_run=True)
        real = purge_broken_obje(str(copy))
        assert dry['lines_removed'] == real['lines_removed']
        assert dry['obje_removed'] == real['obje_removed']
        assert set(dry['broken_files']) == set(real['broken_files'])


# ---------------------------------------------------------------------------
# Structure preservation
# ---------------------------------------------------------------------------

class TestStructurePreservation:
    def test_indi_records_preserved(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '@I1@ INDI' in content
        assert '@I2@ INDI' in content

    def test_fam_record_preserved(self, ged):
        purge_broken_obje(str(ged))
        content = ged.read_text(encoding='utf-8')
        assert '@F1@ FAM' in content

    def test_trlr_preserved(self, ged):
        lines = ged.read_text(encoding='utf-8').splitlines()
        non_empty = [l for l in lines if l.strip()]
        assert non_empty[-1] == '0 TRLR'

    def test_all_lines_are_valid_gedcom(self, ged):
        purge_broken_obje(str(ged))
        bad = []
        level_re = re.compile(r'^\d+ ')
        for i, line in enumerate(ged.read_text(encoding='utf-8').splitlines(), 1):
            if line and not level_re.match(line):
                bad.append((i, line))
        assert bad == []


# ---------------------------------------------------------------------------
# URL handling
# ---------------------------------------------------------------------------

class TestUrlHandling:
    def test_http_url_not_removed(self, tmp_path):
        ged = tmp_path / 'url.ged'
        ged.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @O1@ OBJE\n'
            '1 FILE https://example.com/photo.jpg\n'
            '2 FORM JPG\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = purge_broken_obje(str(ged))
        assert result['obje_removed'] == 0
        assert '0 @O1@ OBJE' in ged.read_text(encoding='utf-8')

    def test_ftp_url_not_removed(self, tmp_path):
        ged = tmp_path / 'ftp.ged'
        ged.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @O1@ OBJE\n'
            '1 FILE ftp://files.example.com/photo.jpg\n'
            '2 FORM JPG\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = purge_broken_obje(str(ged))
        assert result['obje_removed'] == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_obje_with_no_file_tag_kept(self, tmp_path):
        """An OBJE record with no FILE child is unusual but should not crash or be removed."""
        ged = tmp_path / 'nofile.ged'
        ged.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @O1@ OBJE\n'
            '1 TITL Just a title, no FILE\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = purge_broken_obje(str(ged))
        assert result['obje_removed'] == 0
        assert '0 @O1@ OBJE' in ged.read_text(encoding='utf-8')

    def test_absolute_path_resolved_correctly(self, tmp_path):
        img = tmp_path / 'photo.jpg'
        img.write_bytes(b'(placeholder)')
        ged = tmp_path / 'abs.ged'
        ged.write_text(
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            f'0 @O1@ OBJE\n'
            f'1 FILE {img}\n'
            '2 FORM JPG\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        result = purge_broken_obje(str(ged))
        assert result['obje_removed'] == 0

    def test_empty_file_keeps_nothing_to_remove(self, tmp_path):
        ged = tmp_path / 'empty.ged'
        ged.write_text('0 HEAD\n0 TRLR\n', encoding='utf-8')
        result = purge_broken_obje(str(ged))
        assert result['obje_removed'] == 0
        assert result['lines_removed'] == 0
