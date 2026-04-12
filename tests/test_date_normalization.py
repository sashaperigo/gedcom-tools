"""
Tests for the _normalize_event_date helper in serve_viz.py.

Covers:
  - Valid GEDCOM dates pass through unchanged
  - Common non-standard formats are auto-normalized
  - Dates that can't be normalized produce an error
  - Empty / None input is accepted (deleting a date is valid)
"""

import os
from pathlib import Path

import pytest

_FIXTURE_GED = str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged')
os.environ.setdefault('GED_FILE', _FIXTURE_GED)

from serve_viz import _normalize_event_date  # noqa: E402


# ---------------------------------------------------------------------------
# Valid GEDCOM dates — must pass through without modification
# ---------------------------------------------------------------------------

class TestValidDatesPassThrough:
    @pytest.mark.parametrize('date', [
        '5 JAN 1900',
        '1900',
        'ABT 1850',
        'BEF 1920',
        'AFT 1800',
        'CAL 1775',
        'EST 1650',
        'BET 1900 AND 1910',
        'JAN 1900',
        '14 MAR 1990',
    ])
    def test_valid_date_unchanged(self, date):
        result, err = _normalize_event_date(date)
        assert err is None
        assert result == date


# ---------------------------------------------------------------------------
# Non-standard formats that should auto-normalize
# ---------------------------------------------------------------------------

class TestNormalization:
    def test_english_month_name_day_year(self):
        result, err = _normalize_event_date('January 5, 1900')
        assert err is None
        assert result == '5 JAN 1900'

    def test_english_month_name_lowercase(self):
        result, err = _normalize_event_date('january 5, 1900')
        assert err is None
        assert result == '5 JAN 1900'

    def test_lowercase_month_abbreviation(self):
        result, err = _normalize_event_date('5 jan 1900')
        assert err is None
        assert result == '5 JAN 1900'

    def test_about_qualifier(self):
        result, err = _normalize_event_date('about 1850')
        assert err is None
        assert result == 'ABT 1850'

    def test_circa_qualifier(self):
        result, err = _normalize_event_date('circa 1850')
        assert err is None
        assert result == 'ABT 1850'

    def test_before_qualifier(self):
        result, err = _normalize_event_date('before 1920')
        assert err is None
        assert result == 'BEF 1920'

    def test_after_qualifier(self):
        result, err = _normalize_event_date('after 1800')
        assert err is None
        assert result == 'AFT 1800'

    def test_year_range_hyphen(self):
        result, err = _normalize_event_date('1850-1900')
        assert err is None
        assert result == 'BET 1850 AND 1900'

    def test_ordinal_day(self):
        result, err = _normalize_event_date('1st January 1900')
        assert err is None
        assert result == '1 JAN 1900'

    def test_trailing_comma_in_date(self):
        result, err = _normalize_event_date('5 January, 1900')
        assert err is None
        assert result == '5 JAN 1900'

    def test_leading_trailing_whitespace_stripped(self):
        result, err = _normalize_event_date('  5 JAN 1900  ')
        assert err is None
        assert result == '5 JAN 1900'


# ---------------------------------------------------------------------------
# Invalid / unparseable dates — must return an error
# ---------------------------------------------------------------------------

class TestInvalidDates:
    def test_iso_format_rejected(self):
        # "1900-01-05" is not a date range and can't be normalized
        result, err = _normalize_event_date('1900-01-05')
        assert err is not None
        assert 'Invalid date' in err

    def test_completely_unparseable(self):
        result, err = _normalize_event_date('not a date at all')
        assert err is not None

    def test_month_day_no_year(self):
        # "31 JAN" with no year is not valid GEDCOM (no extractable year)
        result, err = _normalize_event_date('31 JAN')
        assert err is not None

    def test_error_includes_original_value(self):
        _, err = _normalize_event_date('1900-01-05')
        assert '1900-01-05' in err


# ---------------------------------------------------------------------------
# Empty / None input — must be accepted (deleting a date is valid)
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_string_accepted(self):
        result, err = _normalize_event_date('')
        assert err is None

    def test_whitespace_only_accepted(self):
        result, err = _normalize_event_date('   ')
        assert err is None

    def test_none_accepted(self):
        result, err = _normalize_event_date(None)
        assert err is None
