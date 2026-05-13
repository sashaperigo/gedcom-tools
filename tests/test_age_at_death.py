"""Tests for age-at-death linter functions."""
import textwrap
from pathlib import Path

import pytest

from gedcom_linter import (
    _parse_age_date,
    _age_keyword,
)


def write_ged(tmp_path, content: str) -> Path:
    p = tmp_path / 'test.ged'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


# ---------------------------------------------------------------------------
# _parse_age_date
# ---------------------------------------------------------------------------

class TestParseAgeDate:
    def test_full_date(self):
        assert _parse_age_date('15 JAN 1920') == (1920, 1, 15, False)

    def test_month_year(self):
        assert _parse_age_date('JAN 1920') == (1920, 1, None, False)

    def test_year_only(self):
        assert _parse_age_date('1920') == (1920, None, None, False)

    def test_abt_approximate(self):
        assert _parse_age_date('ABT 1920') == (1920, None, None, True)

    def test_est_approximate(self):
        assert _parse_age_date('EST 1920') == (1920, None, None, True)

    def test_cal_approximate(self):
        assert _parse_age_date('CAL 15 MAR 1920') == (1920, 3, 15, True)

    def test_bef_not_approximate(self):
        assert _parse_age_date('BEF 1920') == (1920, None, None, False)

    def test_aft_not_approximate(self):
        assert _parse_age_date('AFT 1920') == (1920, None, None, False)

    def test_bet_and_uses_first(self):
        assert _parse_age_date('BET 1910 AND 1920') == (1910, None, None, False)

    def test_from_to_uses_first(self):
        assert _parse_age_date('FROM 1910 TO 1920') == (1910, None, None, False)

    def test_unparseable_returns_none(self):
        assert _parse_age_date('UNKNOWN') is None

    def test_empty_returns_none(self):
        assert _parse_age_date('') is None

    def test_all_month_abbreviations(self):
        months = ['JAN','FEB','MAR','APR','MAY','JUN',
                  'JUL','AUG','SEP','OCT','NOV','DEC']
        for i, m in enumerate(months, 1):
            result = _parse_age_date(f'{m} 1900')
            assert result == (1900, i, None, False), f'Failed for {m}'


# ---------------------------------------------------------------------------
# _age_keyword
# ---------------------------------------------------------------------------

class TestAgeKeyword:
    # STILLBORN cases
    def test_same_full_date_stillborn(self):
        assert _age_keyword((1920,1,15,False), (1920,1,15,False)) == 'STILLBORN'

    def test_same_year_only_exact_stillborn(self):
        assert _age_keyword((1920,None,None,False), (1920,None,None,False)) == 'STILLBORN'

    def test_same_year_approx_is_infant_not_stillborn(self):
        # Without day evidence, approx same-year -> INFANT (safer)
        assert _age_keyword((1920,None,None,True), (1920,None,None,True)) == 'INFANT'

    # INFANT cases
    def test_full_date_364_days_infant(self):
        # 1 Jan 1920 -> 30 Dec 1920 = 364 days
        assert _age_keyword((1920,1,1,False), (1920,12,30,False)) == 'INFANT'

    def test_full_date_exactly_one_year_not_infant(self):
        # 1 Jan 1920 -> 1 Jan 1921 = 366 days (leap year) -> past infancy, so CHILD
        assert _age_keyword((1920,1,1,False), (1921,1,1,False)) == 'CHILD'

    def test_month_year_11_months_infant(self):
        assert _age_keyword((1920,1,None,False), (1920,12,None,False)) == 'INFANT'

    def test_year_diff_1_infant(self):
        assert _age_keyword((1920,None,None,False), (1921,None,None,False)) == 'INFANT'

    # CHILD cases
    def test_year_diff_7_child(self):
        assert _age_keyword((1920,None,None,False), (1927,None,None,False)) == 'CHILD'

    def test_month_year_2_years_child(self):
        assert _age_keyword((1920,6,None,False), (1922,6,None,False)) == 'CHILD'

    def test_full_date_under_8_years_child(self):
        # 1 Jan 1920 -> 31 Dec 1927 = just under 8 years
        assert _age_keyword((1920,1,1,False), (1927,12,31,False)) == 'CHILD'

    # None cases (adult)
    def test_year_diff_8_exact_is_none(self):
        assert _age_keyword((1920,None,None,False), (1928,None,None,False)) is None

    def test_death_before_birth_is_none(self):
        assert _age_keyword((1920,None,None,False), (1910,None,None,False)) is None

    # Approximation margin cases (margin = 2 years)
    def test_approx_year_diff_9_still_child(self):
        # With ABT dates, child threshold extends to 10, so diff=9 -> CHILD
        assert _age_keyword((1920,None,None,True), (1929,None,None,False)) == 'CHILD'

    def test_approx_year_diff_10_extends_to_child(self):
        # diff=10 with margin=2 -> threshold is 10, so 10 < 10 is False -> None
        assert _age_keyword((1920,None,None,True), (1930,None,None,False)) is None

    def test_approx_year_diff_2_is_infant_via_margin(self):
        # INFANT upper bound extends to 1+2=3, so diff=2 -> INFANT
        assert _age_keyword((1920,None,None,True), (1922,None,None,False)) == 'INFANT'

    def test_exact_year_diff_2_is_child_not_infant(self):
        # No margin: diff=2, INFANT threshold is diff==1 only
        assert _age_keyword((1920,None,None,False), (1922,None,None,False)) == 'CHILD'
