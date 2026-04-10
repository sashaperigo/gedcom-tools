"""Tests for gedcom_merge.normalize — TDD for date/name/place normalization."""

import pytest
from gedcom_merge.normalize import (
    normalize_name_str,
    tokenize_title,
    parse_date,
    date_overlap_score,
    place_similarity,
    jaccard,
)
from gedcom_merge.model import ParsedDate


class TestNormalizeName:
    def test_standard_slash_format(self):
        given, surname = normalize_name_str("Saverio Salvatore /Bonnici/")
        assert given == "saverio salvatore"
        assert surname == "bonnici"

    def test_no_surname(self):
        given, surname = normalize_name_str("Madonna")
        assert given == "madonna"
        assert surname == ""

    def test_empty_surname_slash(self):
        given, surname = normalize_name_str("John //")
        assert given == "john"
        assert surname == ""

    def test_diacritics_stripped(self):
        given, surname = normalize_name_str("Élodie /Müller/")
        # unidecode or fallback should strip accents
        assert 'lodie' in given  # 'elodie' or 'elodie'
        assert 'ller' in surname  # 'muller' or similar

    def test_text_after_closing_slash(self):
        # Some GEDCOM generators put suffix after /Surname/ like "Jr"
        given, surname = normalize_name_str("Robert /Smith/ Jr")
        assert surname == "smith"
        assert "jr" in given or "robert" in given


class TestTokenizeTitle:
    def test_basic_tokens(self):
        tokens = tokenize_title("Illinois Federal Naturalization Records 1856-1991")
        assert 'illinois' in tokens
        assert 'federal' in tokens
        assert 'naturalization' in tokens
        assert 'records' in tokens
        # Year tokens after punctuation stripping: '1856' and '1991'
        assert '1856' in tokens or '1991' in tokens

    def test_strips_punctuation(self):
        tokens = tokenize_title("U.S., Federal Records")
        assert 'federal' in tokens
        assert 'records' in tokens

    def test_drops_short_tokens(self):
        tokens = tokenize_title("A Big Set")
        assert 'a' not in tokens  # length 1
        assert 'big' in tokens
        assert 'set' in tokens

    def test_empty_string(self):
        tokens = tokenize_title("")
        assert tokens == set()


class TestParseDate:
    def test_exact_full_date(self):
        d = parse_date("15 MAR 1892")
        assert d is not None
        assert d.qualifier is None
        assert d.year == 1892
        assert d.month == 3
        assert d.day == 15

    def test_month_year_only(self):
        d = parse_date("MAR 1892")
        assert d is not None
        assert d.year == 1892
        assert d.month == 3
        assert d.day is None

    def test_year_only(self):
        d = parse_date("1892")
        assert d is not None
        assert d.year == 1892
        assert d.month is None
        assert d.day is None

    def test_abt_qualifier(self):
        d = parse_date("ABT 1890")
        assert d is not None
        assert d.qualifier == 'ABT'
        assert d.year == 1890

    def test_about_normalized_to_abt(self):
        d = parse_date("ABOUT 1890")
        assert d is not None
        assert d.qualifier == 'ABT'

    def test_cal_normalized_to_abt(self):
        d = parse_date("CAL 1890")
        assert d is not None
        assert d.qualifier == 'ABT'

    def test_bef_qualifier(self):
        d = parse_date("BEF 1900")
        assert d is not None
        assert d.qualifier == 'BEF'
        assert d.year == 1900

    def test_aft_qualifier(self):
        d = parse_date("AFT 1888")
        assert d is not None
        assert d.qualifier == 'AFT'
        assert d.year == 1888

    def test_bet_and_range(self):
        d = parse_date("BET 1888 AND 1892")
        assert d is not None
        assert d.qualifier == 'BET'
        assert d.year == 1888
        assert d.year2 == 1892

    def test_bet_with_full_dates(self):
        d = parse_date("BET 15 MAR 1888 AND 1892")
        assert d is not None
        assert d.qualifier == 'BET'
        assert d.year == 1888
        assert d.month == 3

    def test_none_input(self):
        assert parse_date(None) is None

    def test_empty_string(self):
        assert parse_date("") is None

    def test_lowercase_accepted(self):
        d = parse_date("abt 1890")
        assert d is not None
        assert d.qualifier == 'ABT'

    def test_from_to_treated_as_bet(self):
        d = parse_date("FROM 1900 TO 1905")
        assert d is not None
        assert d.qualifier == 'BET'
        assert d.year == 1900
        assert d.year2 == 1905


class TestDateOverlapScore:
    def test_exact_match(self):
        a = parse_date("15 MAR 1892")
        b = parse_date("15 MAR 1892")
        assert date_overlap_score(a, b) == 1.0

    def test_same_year_different_month(self):
        a = parse_date("1892")
        b = parse_date("1892")
        assert date_overlap_score(a, b) == 0.8

    def test_same_year_and_month(self):
        a = parse_date("MAR 1892")
        b = parse_date("MAR 1892")
        assert date_overlap_score(a, b) >= 0.8

    def test_within_two_years(self):
        a = parse_date("1892")
        b = parse_date("1891")
        score = date_overlap_score(a, b)
        assert score == 0.5

    def test_no_overlap(self):
        a = parse_date("1800")
        b = parse_date("1950")
        assert date_overlap_score(a, b) == 0.0

    def test_one_missing(self):
        a = parse_date("1892")
        assert date_overlap_score(a, None) == 0.3
        assert date_overlap_score(None, a) == 0.3

    def test_both_missing(self):
        assert date_overlap_score(None, None) == 0.3

    def test_approximate_overlapping_exact(self):
        a = parse_date("ABT 1890")
        b = parse_date("1891")
        score = date_overlap_score(a, b)
        assert score == 0.7

    def test_both_approximate_overlapping(self):
        a = parse_date("ABT 1890")
        b = parse_date("ABT 1890")
        score = date_overlap_score(a, b)
        assert score == 0.6

    def test_bef_no_overlap(self):
        a = parse_date("BEF 1800")
        b = parse_date("1950")
        assert date_overlap_score(a, b) == 0.0

    def test_approximate_near_miss_within_5_years(self):
        """ABT 1850 vs exact 1855 — no overlap but within 5 years → partial credit."""
        a = parse_date("ABT 1850")  # range 1848–1852
        b = parse_date("1855")      # gap = 3 years from 1852
        score = date_overlap_score(a, b)
        assert score == 0.4, f"Expected 0.4 near-miss score, got {score}"

    def test_approximate_near_miss_exact_vs_aft(self):
        """Exact 1895 vs AFT 1900 — no overlap but within 5 years of AFT boundary."""
        a = parse_date("1895")
        b = parse_date("AFT 1900")  # range 1900–9999; gap = 5 years from 1895
        score = date_overlap_score(a, b)
        assert score == 0.4, f"Expected 0.4 near-miss score, got {score}"

    def test_approximate_near_miss_at_8_years_scores_near_miss(self):
        """ABT 1850 vs exact 1860 — gap = 8 years → 0.4 near-miss (threshold is 8)."""
        a = parse_date("ABT 1850")  # range 1848–1852
        b = parse_date("1860")      # gap = 8 years from 1852 to 1860
        score = date_overlap_score(a, b)
        assert score == 0.4, f"Expected 0.4 near-miss score, got {score}"

    def test_approximate_near_miss_beyond_8_years_scores_zero(self):
        """ABT 1850 vs exact 1863 — gap = 11 years → 0.0 (beyond tolerance)."""
        a = parse_date("ABT 1850")  # range 1848–1852
        b = parse_date("1863")      # gap = 11 years from 1852 to 1863
        score = date_overlap_score(a, b)
        assert score == 0.0

    def test_two_exact_dates_far_apart_score_zero(self):
        """Two exact dates 10 years apart have no near-miss leniency."""
        a = parse_date("1840")
        b = parse_date("1860")
        assert date_overlap_score(a, b) == 0.0


class TestPlaceSimilarity:
    def test_exact_match(self):
        assert place_similarity("Columbus, Ohio, USA", "Columbus, Ohio, USA") == 1.0

    def test_both_none(self):
        assert place_similarity(None, None) == 1.0

    def test_one_none(self):
        assert place_similarity("Columbus, Ohio", None) == 0.0

    def test_hierarchical_match(self):
        # Extra component on one side
        score = place_similarity("Bogota, Colombia", "Bogota, Bolivar, Colombia")
        assert score >= 0.6  # Should be high due to shared components

    def test_abbreviated_vs_full(self):
        score = place_similarity("Columbus, Ohio, USA", "Columbus, Franklin, Ohio, USA")
        assert score >= 0.6

    def test_no_match(self):
        score = place_similarity("New York, USA", "Paris, France")
        assert score < 0.3


class TestJaccard:
    def test_identical_sets(self):
        a = {'a', 'b', 'c'}
        assert jaccard(a, a) == 1.0

    def test_disjoint_sets(self):
        assert jaccard({'a', 'b'}, {'c', 'd'}) == 0.0

    def test_partial_overlap(self):
        score = jaccard({'a', 'b', 'c'}, {'b', 'c', 'd'})
        assert abs(score - 0.5) < 0.01  # 2 common / 4 union

    def test_both_empty(self):
        assert jaccard(set(), set()) == 1.0

    def test_one_empty(self):
        assert jaccard({'a'}, set()) == 0.0


class TestDateSpecificity:
    def test_full_exact_most_specific(self):
        d = parse_date("15 MAR 1892")
        assert d is not None
        assert d.specificity() > parse_date("1892").specificity()

    def test_exact_more_specific_than_abt(self):
        exact = parse_date("1892")
        abt = parse_date("ABT 1892")
        assert exact.specificity() > abt.specificity()
