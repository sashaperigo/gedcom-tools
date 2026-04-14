"""
Tests for scan_curly_quotes / fix_curly_quotes.

GEDCOM files must use straight ASCII quotes (" and ') throughout so that
nickname extraction and other text processing works reliably.
"""
import textwrap
from pathlib import Path

import pytest

from gedcom_linter import scan_curly_quotes, fix_curly_quotes


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def write_ged(tmp_path: Path, content: str) -> Path:
    p = tmp_path / 'test.ged'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


# ---------------------------------------------------------------------------
# scan_curly_quotes
# ---------------------------------------------------------------------------

class TestScanCurlyQuotes:
    def test_clean_file_returns_empty(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 NAME Adelaide "Edla" /Dellatolla/
            0 TRLR
        """)
        assert scan_curly_quotes(p) == []

    def test_left_double_curly_quote_detected(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Adelaide \u201cEdla\u201d /Dellatolla/
            0 TRLR
        """)
        hits = scan_curly_quotes(p)
        assert len(hits) == 1
        lineno, line = hits[0]
        assert 'Adelaide' in line
        assert lineno == 3

    def test_right_single_curly_quote_detected(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            2 NOTE It\u2019s a note.
            0 TRLR
        """)
        hits = scan_curly_quotes(p)
        assert len(hits) == 1

    def test_multiple_lines_all_reported(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Adelaide \u201cEdla\u201d /Dellatolla/
            2 NOTE He said \u201chello\u201d.
            0 TRLR
        """)
        hits = scan_curly_quotes(p)
        assert len(hits) == 2
        line_numbers = [ln for ln, _ in hits]
        assert sorted(line_numbers) == line_numbers  # reported in order

    def test_all_curly_variants_detected(self, tmp_path):
        # One line per curly-quote character
        chars = ['\u2018', '\u2019', '\u201a', '\u201b',
                 '\u201c', '\u201d', '\u201e', '\u201f',
                 '\u2039', '\u203a', '\u00ab', '\u00bb']
        lines = ['0 HEAD\n'] + [f'2 NOTE word{c}word\n' for c in chars] + ['0 TRLR\n']
        p = tmp_path / 'test.ged'
        p.write_text(''.join(lines), encoding='utf-8')
        hits = scan_curly_quotes(p)
        assert len(hits) == len(chars)

    def test_straight_quotes_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Pol "Polly" /Bonnici/
            2 NOTE He said "hello" and it's fine.
            0 TRLR
        """)
        assert scan_curly_quotes(p) == []


# ---------------------------------------------------------------------------
# fix_curly_quotes
# ---------------------------------------------------------------------------

class TestFixCurlyQuotes:
    def test_double_curly_replaced_with_straight(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Adelaide \u201cEdla\u201d /Dellatolla/
            0 TRLR
        """)
        changed = fix_curly_quotes(p)
        assert changed == 1
        text = p.read_text(encoding='utf-8')
        assert '\u201c' not in text
        assert '\u201d' not in text
        assert '"Edla"' in text

    def test_single_curly_replaced_with_straight(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            2 NOTE It\u2019s fine.
            0 TRLR
        """)
        changed = fix_curly_quotes(p)
        assert changed == 1
        text = p.read_text(encoding='utf-8')
        assert '\u2019' not in text
        assert "It's fine." in text

    def test_returns_zero_when_nothing_to_fix(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Pol "Polly" /Bonnici/
            0 TRLR
        """)
        assert fix_curly_quotes(p) == 0

    def test_dry_run_does_not_modify_file(self, tmp_path):
        original = '0 HEAD\n0 @I1@ INDI\n2 NOTE \u201chello\u201d\n0 TRLR\n'
        p = tmp_path / 'test.ged'
        p.write_text(original, encoding='utf-8')
        changed = fix_curly_quotes(p, dry_run=True)
        assert changed == 1
        assert p.read_text(encoding='utf-8') == original  # untouched

    def test_multiple_curly_chars_on_same_line(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            2 NOTE \u201chello\u201d and \u2018world\u2019
            0 TRLR
        """)
        changed = fix_curly_quotes(p)
        assert changed == 1
        text = p.read_text(encoding='utf-8')
        assert '"hello"' in text
        assert "'world'" in text

    def test_all_curly_variants_replaced(self, tmp_path):
        chars = ['\u2018', '\u2019', '\u201a', '\u201b',
                 '\u201c', '\u201d', '\u201e', '\u201f',
                 '\u2039', '\u203a', '\u00ab', '\u00bb']
        lines = ['0 HEAD\n'] + [f'2 NOTE word{c}word\n' for c in chars] + ['0 TRLR\n']
        p = tmp_path / 'test.ged'
        p.write_text(''.join(lines), encoding='utf-8')
        changed = fix_curly_quotes(p)
        assert changed == len(chars)
        text = p.read_text(encoding='utf-8')
        for c in chars:
            assert c not in text

    def test_nickname_extraction_works_after_fix(self, tmp_path):
        """After fixing, the name with curly-quoted nickname uses straight quotes."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Adelaide \u201cEdla\u201d /Dellatolla/
            0 TRLR
        """)
        fix_curly_quotes(p)
        text = p.read_text(encoding='utf-8')
        assert '1 NAME Adelaide "Edla" /Dellatolla/' in text

    def test_non_quote_unicode_untouched(self, tmp_path):
        """Accented letters and other Unicode outside the curly-quote set are left alone."""
        content = '0 HEAD\n0 @I1@ INDI\n1 NAME Jos\u00e9phine /Pradelle/\n0 TRLR\n'
        p = tmp_path / 'test.ged'
        p.write_text(content, encoding='utf-8')
        changed = fix_curly_quotes(p)
        assert changed == 0
        assert p.read_text(encoding='utf-8') == content
