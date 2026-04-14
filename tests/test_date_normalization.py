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
    def test_completely_unparseable(self):
        result, err = _normalize_event_date('not a date at all')
        assert err is not None

    def test_month_day_no_year(self):
        # "31 JAN" with no year is not valid GEDCOM (no extractable year)
        result, err = _normalize_event_date('31 JAN')
        assert err is not None

    def test_error_includes_original_value(self):
        _, err = _normalize_event_date('totally unparseable xyz')
        assert 'totally unparseable xyz' in err


# ---------------------------------------------------------------------------
# Natural-language date inputs — TDD: these define the target behavior
# ---------------------------------------------------------------------------

class TestNaturalLanguageDates:
    def test_before_month_day_comma_year(self):
        # Primary bug: "before April 26, 1962" was erroring
        result, err = _normalize_event_date('before April 26, 1962')
        assert err is None
        assert result == 'BEF 26 APR 1962'

    def test_after_month_day_comma_year(self):
        result, err = _normalize_event_date('after April 26, 1962')
        assert err is None
        assert result == 'AFT 26 APR 1962'

    def test_about_month_day_comma_year(self):
        result, err = _normalize_event_date('about April 26, 1962')
        assert err is None
        assert result == 'ABT 26 APR 1962'

    def test_before_day_month_comma_year(self):
        # "before 26 April, 1962" — trailing comma after month
        result, err = _normalize_event_date('before 26 April, 1962')
        assert err is None
        assert result == 'BEF 26 APR 1962'

    def test_before_month_day_no_comma(self):
        # Should already work, verify it does
        result, err = _normalize_event_date('before April 26 1962')
        assert err is None
        assert result == 'BEF 26 APR 1962'

    def test_before_month_year_only(self):
        # Should already work
        result, err = _normalize_event_date('before April 1962')
        assert err is None
        assert result == 'BEF APR 1962'

    def test_between_multi_word_dates(self):
        # "between April 1962 and June 1963" — multi-word parts require .+?
        result, err = _normalize_event_date('between April 1962 and June 1963')
        assert err is None
        assert result == 'BET APR 1962 AND JUN 1963'

    def test_month_abbrev_with_period(self):
        # "Jan. 5, 1991" → "5 JAN 1991"
        result, err = _normalize_event_date('Jan. 5, 1991')
        assert err is None
        assert result == '5 JAN 1991'

    def test_before_month_abbrev_with_period(self):
        # "before Jan. 5, 1991" → "BEF 5 JAN 1991"
        result, err = _normalize_event_date('before Jan. 5, 1991')
        assert err is None
        assert result == 'BEF 5 JAN 1991'

    def test_us_slash_date(self):
        # "01/15/1985" → "15 JAN 1985"
        result, err = _normalize_event_date('01/15/1985')
        assert err is None
        assert result == '15 JAN 1985'

    def test_iso_date_normalizes(self):
        # "1985-01-15" → "15 JAN 1985"  (ISO format now normalizes instead of errors)
        result, err = _normalize_event_date('1985-01-15')
        assert err is None
        assert result == '15 JAN 1985'

    def test_before_ordinal_month_year(self):
        # Should already work
        result, err = _normalize_event_date('before 5th January 1900')
        assert err is None
        assert result == 'BEF 5 JAN 1900'

    def test_before_the_nth_of_month_year(self):
        # "before the 5th of January, 1900" → "BEF 5 JAN 1900"
        result, err = _normalize_event_date('before the 5th of January, 1900')
        assert err is None
        assert result == 'BEF 5 JAN 1900'

    def test_circa_month_year(self):
        # Should already work
        result, err = _normalize_event_date('circa April 1962')
        assert err is None
        assert result == 'ABT APR 1962'


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
