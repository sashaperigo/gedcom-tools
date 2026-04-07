"""
Tests for clean_notexml.py

Covers stripping of Geneanet <notexml> wrappers from GEDCOM NOTE fields:
  - Raw <notexml>: multi-line content spread across NOTE + CONC lines
  - HTML-encoded &lt;notexml&gt;: single URL or short content
  - HTML entity decoding (&amp; → &, &lt; → <, etc.)
  - Empty <line> elements → blank CONT lines
  - Multi-segment notexml → NOTE + CONT lines
  - Regular NOTEs unchanged
"""

import re
import shutil
from pathlib import Path

import pytest

from clean_notexml import clean_notexml

FIXTURE = Path(__file__).parent / 'fixtures' / 'notexml_sample.ged'


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

    def test_fixture_has_raw_notexml(self):
        assert '<notexml>' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_html_encoded_notexml(self):
        assert '&lt;notexml&gt;' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_empty_line_element(self):
        assert '<line></line>' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_amp_entity(self):
        assert '&amp;' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_regular_note(self):
        assert 'regular note with no XML' in FIXTURE.read_text(encoding='utf-8')

    def test_fixture_has_notexml_with_conc(self):
        """@I6@ has a notexml NOTE with a CONC continuation."""
        lines = FIXTURE.read_text(encoding='utf-8').splitlines()
        for i, line in enumerate(lines):
            if '<notexml>' in line:
                if i + 1 < len(lines) and lines[i + 1].startswith('2 CONC'):
                    return
        pytest.fail('Fixture has no notexml NOTE followed by a CONC line')


# ---------------------------------------------------------------------------
# Core cleaning behaviour
# ---------------------------------------------------------------------------

class TestNoteXmlCleaning:

    def test_no_notexml_tags_remain(self, tmp_copy):
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        assert '<notexml>' not in c
        assert '</notexml>' not in c

    def test_no_html_encoded_notexml_remain(self, tmp_copy):
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        assert '&lt;notexml&gt;' not in c
        assert '&lt;/notexml&gt;' not in c

    def test_no_line_tags_remain(self, tmp_copy):
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        assert '<line>' not in c
        assert '</line>' not in c

    def test_url_extracted_from_html_encoded(self, tmp_copy):
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        assert 'https://www.tributearchive.com/obituaries/16758107/gianmarco-pastore' in c
        assert 'https://www.levantineheritage.com/pdf/lista.pdf' in c

    def test_amp_entity_decoded(self, tmp_copy):
        """&amp; in a URL must become & in the cleaned output."""
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        assert 'mibextid=foo&mibextid=bar' in c

    def test_multiline_content_preserved(self, tmp_copy):
        """All non-empty <line> text from @I1@ must appear in output."""
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        assert "fille de Pietro d'Andréa dit Lari" in c
        assert "et sur l'acte de baptême de Stefano D'Andria" in c
        assert 'Translation:' in c
        assert "daughter of Pietro d'Andréa known as Lari" in c
        assert 'Full name may be Cosima?' in c

    def test_cont_lines_created_for_multiline(self, tmp_copy):
        """Multi-segment notexml must produce CONT lines for segments after the first."""
        clean_notexml(tmp_copy)
        lines = lines_of(tmp_copy)
        # Find the NOTE line from @I1@ and check it has CONT children
        for i, line in enumerate(lines):
            if '1 NOTE' in line and "fille de Pietro" in line:
                assert any('2 CONT' in lines[j] for j in range(i + 1, min(i + 10, len(lines))))
                return
        pytest.fail("Could not find cleaned @I1@ NOTE with CONT children")

    def test_empty_line_element_becomes_blank_cont(self, tmp_copy):
        """Empty <line></line> elements must become '2 CONT' lines with no text."""
        clean_notexml(tmp_copy)
        lines = lines_of(tmp_copy)
        # @I1@ has two empty <line> elements
        assert any(l == '2 CONT' for l in lines), \
            "Expected at least one blank '2 CONT' line from empty <line> elements"

    def test_conc_lines_consumed(self, tmp_copy):
        """CONC lines that were part of a notexml block must not remain as CONC."""
        clean_notexml(tmp_copy)
        lines = lines_of(tmp_copy)
        # @I6@ had a notexml NOTE with a CONC continuation.
        # After cleaning, no '2 CONC' lines should remain (they were part of the
        # notexml block and are now replaced by CONT lines from <line> structure).
        assert not any(re.match(r'^\d+ CONC ', l) for l in lines), \
            "CONC lines from notexml block still present after cleaning"

    def test_multiline_conc_content_preserved(self, tmp_copy):
        """Text split across CONC in a notexml NOTE must appear in the cleaned output."""
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        # @I6@: "First line of a multi-segment note, split mid-sentence across a CONC boundary"
        assert 'split mid-sentence' in c
        assert 'CONC boundary' in c  # text that happened to be in the CONC value

    def test_regular_note_unchanged(self, tmp_copy):
        """NOTEs with no notexml content must pass through untouched."""
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        assert 'regular note with no XML content whatsoever.' in c
        assert 'It has a continuation line too.' in c

    def test_second_note_on_same_indi_unchanged(self, tmp_copy):
        """@I4@ has a notexml NOTE followed by a plain NOTE — the plain one must survive."""
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        assert 'A second regular note that should not be touched.' in c

    def test_standard_tags_preserved(self, tmp_copy):
        clean_notexml(tmp_copy)
        c = content_of(tmp_copy)
        for val in ("Cosima /D'Andria/", 'Gianmarco /Pastore/',
                    'Elisabeth /Maraspini/', '1 JAN 1900'):
            assert val in c, f'{val!r} was removed'


# ---------------------------------------------------------------------------
# Return values
# ---------------------------------------------------------------------------

class TestReturnValues:

    def test_keys_present(self, tmp_copy):
        result = clean_notexml(tmp_copy)
        for key in ('lines_read', 'lines_delta', 'notes_cleaned'):
            assert key in result

    def test_notes_cleaned_count(self, tmp_copy):
        result = clean_notexml(tmp_copy)
        # Fixture has 5 notexml NOTE blocks (@I1@, @I2@, @I3@, @I4@ first note, @I6@)
        assert result['notes_cleaned'] == 5

    def test_lines_delta_matches_actual_diff(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            before = sum(1 for _ in f)
        result = clean_notexml(tmp_copy)
        with open(tmp_copy, encoding='utf-8') as f:
            after = sum(1 for _ in f)
        assert result['lines_delta'] == after - before

    def test_lines_read_matches_file(self, tmp_copy):
        with open(tmp_copy, encoding='utf-8') as f:
            file_len = sum(1 for _ in f)
        result = clean_notexml(tmp_copy)
        assert result['lines_read'] == file_len


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_clean_file_unchanged(self, tmp_path):
        clean = tmp_path / 'clean.ged'
        clean.write_text(
            '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n'
            '0 @I1@ INDI\n1 NAME Alice /Wonder/\n'
            '1 NOTE A plain note.\n'
            '0 TRLR\n',
            encoding='utf-8',
        )
        original = clean.read_text(encoding='utf-8')
        result = clean_notexml(str(clean))
        assert result['notes_cleaned'] == 0
        assert clean.read_text(encoding='utf-8') == original

    def test_dry_run_no_write(self, tmp_copy):
        original = Path(tmp_copy).read_text(encoding='utf-8')
        clean_notexml(tmp_copy, dry_run=True)
        assert Path(tmp_copy).read_text(encoding='utf-8') == original

    def test_dry_run_stats_match_real(self, tmp_copy):
        dry = clean_notexml(tmp_copy, dry_run=True)
        real = clean_notexml(tmp_copy)
        assert dry['notes_cleaned'] == real['notes_cleaned']

    def test_output_file_option(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        clean_notexml(str(FIXTURE), path_out=out)
        c = Path(out).read_text(encoding='utf-8')
        assert '<notexml>' not in c
        assert '&lt;notexml&gt;' not in c

    def test_input_unchanged_when_output_specified(self, tmp_path):
        out = str(tmp_path / 'clean.ged')
        original = FIXTURE.read_text(encoding='utf-8')
        clean_notexml(str(FIXTURE), path_out=out)
        assert FIXTURE.read_text(encoding='utf-8') == original
