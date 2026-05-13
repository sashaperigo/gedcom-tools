"""Tests for age-at-death linter functions."""
import textwrap
from pathlib import Path

from gedcom_linter import (
    _parse_age_date,
    _age_keyword,
    scan_missing_age_at_death,
    fix_missing_age_at_death,
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


# ---------------------------------------------------------------------------
# scan_missing_age_at_death / fix_missing_age_at_death
# ---------------------------------------------------------------------------

class TestScanMissingAgeAtDeath:
    def test_detects_infant(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 NAME Alice //
            1 BIRT
            2 DATE 1 JAN 1920
            1 DEAT
            2 DATE 1 JUN 1920
            0 TRLR
        """)
        issues = scan_missing_age_at_death(str(ged))
        assert len(issues) == 1
        xref, name, birt_raw, deat_raw = issues[0]
        assert xref == '@I1@'
        assert birt_raw == '1 JAN 1920'
        assert deat_raw == '1 JUN 1920'

    def test_ignores_existing_age_tag(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1 JAN 1920
            1 DEAT
            2 DATE 1 JUN 1920
            2 AGE INFANT
            0 TRLR
        """)
        assert scan_missing_age_at_death(str(ged)) == []

    def test_ignores_missing_birt(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 DEAT
            2 DATE 1 JUN 1920
            0 TRLR
        """)
        assert scan_missing_age_at_death(str(ged)) == []

    def test_ignores_missing_deat(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1 JAN 1920
            0 TRLR
        """)
        assert scan_missing_age_at_death(str(ged)) == []

    def test_ignores_adult(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1850
            1 DEAT
            2 DATE 1930
            0 TRLR
        """)
        assert scan_missing_age_at_death(str(ged)) == []

    def test_ignores_deat_without_date(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 DEAT Y
            0 TRLR
        """)
        assert scan_missing_age_at_death(str(ged)) == []


class TestFixMissingAgeAtDeath:
    def test_inserts_age_after_date(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1 JAN 1920
            1 DEAT
            2 DATE 1 JUN 1920
            0 TRLR
        """)
        count = fix_missing_age_at_death(str(ged))
        assert count == 1
        content = ged.read_text(encoding='utf-8')
        lines = content.splitlines()
        date_idx = next(i for i, l in enumerate(lines) if '2 DATE 1 JUN 1920' in l)
        assert lines[date_idx + 1].strip() == '2 AGE INFANT'

    def test_inserts_stillborn(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 MAR 1920
            1 DEAT
            2 DATE 15 MAR 1920
            0 TRLR
        """)
        fix_missing_age_at_death(str(ged))
        assert '2 AGE STILLBORN' in ged.read_text(encoding='utf-8')

    def test_inserts_child(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 DEAT
            2 DATE 1925
            0 TRLR
        """)
        fix_missing_age_at_death(str(ged))
        assert '2 AGE CHILD' in ged.read_text(encoding='utf-8')

    def test_dry_run_does_not_write(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 DEAT
            2 DATE 1921
            0 TRLR
        """)
        original = ged.read_text(encoding='utf-8')
        count = fix_missing_age_at_death(str(ged), dry_run=True)
        assert count == 1
        assert ged.read_text(encoding='utf-8') == original

    def test_does_not_touch_existing_age(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 DEAT
            2 DATE 1921
            2 AGE INFANT
            0 TRLR
        """)
        count = fix_missing_age_at_death(str(ged))
        assert count == 0

    def test_multiple_individuals_only_eligible_modified(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 DEAT
            2 DATE 1921
            0 @I2@ INDI
            1 BIRT
            2 DATE 1850
            1 DEAT
            2 DATE 1930
            0 TRLR
        """)
        count = fix_missing_age_at_death(str(ged))
        assert count == 1
        content = ged.read_text(encoding='utf-8')
        assert content.count('2 AGE') == 1

    def test_deat_without_date_not_modified(self, tmp_path):
        ged = write_ged(tmp_path, """\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 BIRT
            2 DATE 1920
            1 DEAT Y
            1 BURI
            0 TRLR
        """)
        count = fix_missing_age_at_death(str(ged))
        assert count == 0
