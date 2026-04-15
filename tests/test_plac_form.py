"""
Tests for scan_plac_form() in gedcom_linter.py.
"""

from gedcom_linter import scan_plac_form


def _write(tmp_path, content: str) -> str:
    p = tmp_path / 'test.ged'
    p.write_text(content, encoding='utf-8')
    return str(p)


class TestScanPlacForm:

    def test_returns_form_value_when_present(self, tmp_path):
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '1 PLAC\n'
            '2 FORM City, County, State, Country\n'
            '0 @I1@ INDI\n'
            '1 NAME Alice /Test/\n'
            '0 TRLR\n'
        )
        assert scan_plac_form(path) == 'City, County, State, Country'

    def test_returns_none_when_plac_missing_from_header(self, tmp_path):
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 NAME Alice /Test/\n'
            '0 TRLR\n'
        )
        assert scan_plac_form(path) is None

    def test_returns_none_when_plac_has_no_form_child(self, tmp_path):
        """1 PLAC present in header but no 2 FORM underneath."""
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '1 PLAC\n'
            '0 @I1@ INDI\n'
            '1 NAME Alice /Test/\n'
            '0 TRLR\n'
        )
        assert scan_plac_form(path) is None

    def test_ignores_plac_outside_header(self, tmp_path):
        """PLAC/FORM on records outside HEAD must not be mistaken for the declaration."""
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 BIRT\n'
            '2 PLAC London, England\n'
            '0 TRLR\n'
        )
        assert scan_plac_form(path) is None

    def test_stops_reading_at_first_non_head_record(self, tmp_path):
        """Scanning stops at the next level-0 line after HEAD."""
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 GEDC\n'
            '2 VERS 5.5.1\n'
            '0 @I1@ INDI\n'
            '1 PLAC\n'
            '2 FORM City, County, State, Country\n'
            '0 TRLR\n'
        )
        assert scan_plac_form(path) is None

    def test_form_value_is_stripped(self, tmp_path):
        """Leading/trailing whitespace in the FORM value is stripped."""
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 PLAC\n'
            '2 FORM   City, County, State, Country   \n'
            '0 TRLR\n'
        )
        assert scan_plac_form(path) == 'City, County, State, Country'

    def test_other_form_values_returned_verbatim(self, tmp_path):
        """Any FORM value is returned, not just the canonical four-field one."""
        path = _write(tmp_path,
            '0 HEAD\n'
            '1 PLAC\n'
            '2 FORM City, County, Country\n'
            '0 TRLR\n'
        )
        assert scan_plac_form(path) == 'City, County, Country'
