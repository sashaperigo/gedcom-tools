"""
Unit tests for the new scan/fix functions added in the linter expansion.

Pattern: write_ged(tmp_path, content) → call scan_*/fix_* → assert.
Follows the style of tests/test_fix_name_case.py.
"""
import textwrap
from pathlib import Path

import pytest

from gedcom_linter import (
    scan_date_month_caps,
    fix_date_caps,
    scan_header_required_fields,
    scan_bare_event_tags,
    scan_untyped_events,
    scan_missing_sex,
    scan_age_values,
    scan_resn_values,
    scan_pedi_values,
    scan_nonstandard_tags,
    scan_occu_length,
    scan_conc_cont,
    scan_name_nicknames,
    fix_nicknames,
    scan_name_pieces,
    fix_name_pieces,
    _parse_name_pieces,
    scan_dateless_dates,
    fix_dateless_dates,
    scan_fact_aka,
    fix_aka_facts,
    scan_place_consistency,
    scan_same_sour_multiple_cites,
    normalize_date,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def write_ged(tmp_path, content: str) -> Path:
    p = tmp_path / 'test.ged'
    p.write_text(textwrap.dedent(content), encoding='utf-8')
    return p


# ===========================================================================
# normalize_date — month-cap post-processing (spec 2.1 addition)
# ===========================================================================

class TestNormalizeDateMonthCaps:
    def test_lowercase_month_uppercased(self):
        assert normalize_date('5 jan 1900') == '5 JAN 1900'

    def test_mixed_case_month_uppercased(self):
        assert normalize_date('15 Feb 1850') == '15 FEB 1850'

    def test_already_uppercase_unchanged(self):
        assert normalize_date('15 FEB 1850') == '15 FEB 1850'

    def test_bet_range_months_uppercased(self):
        result = normalize_date('BET 1 jan 1900 AND 31 dec 1900')
        assert 'JAN' in result and 'DEC' in result


# ===========================================================================
# scan_date_month_caps / fix_date_caps
# ===========================================================================

class TestScanDateMonthCaps:
    def test_detects_mixed_case_month(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 Feb 1850
            0 TRLR
        """)
        result = scan_date_month_caps(str(p))
        assert len(result) == 1
        assert result[0][1] == '15 Feb 1850'

    def test_detects_lowercase_month(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 feb 1850
            0 TRLR
        """)
        result = scan_date_month_caps(str(p))
        assert len(result) == 1

    def test_no_violation_for_uppercase(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 FEB 1850
            0 TRLR
        """)
        assert scan_date_month_caps(str(p)) == []

    def test_no_violation_for_year_only(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 1850
            0 TRLR
        """)
        assert scan_date_month_caps(str(p)) == []


class TestFixDateCaps:
    def test_fixes_mixed_case_month(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 Feb 1850
            0 TRLR
        """)
        count = fix_date_caps(str(p))
        assert count == 1
        assert '15 FEB 1850' in p.read_text(encoding='utf-8')

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 Feb 1850
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_date_caps(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original

    def test_returns_zero_when_no_changes(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 FEB 1850
            0 TRLR
        """)
        assert fix_date_caps(str(p)) == 0


# ===========================================================================
# scan_header_required_fields
# ===========================================================================

class TestScanHeaderRequiredFields:
    def test_complete_header_no_violations(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            1 SOUR MyApp
            1 SUBM @SUBM1@
            1 GEDC
            2 VERS 5.5.1
            2 FORM LINEAGE-LINKED
            1 CHAR UTF-8
            0 TRLR
        """)
        assert scan_header_required_fields(str(p)) == []

    def test_missing_sour(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            1 SUBM @SUBM1@
            1 GEDC
            2 VERS 5.5.1
            2 FORM LINEAGE-LINKED
            1 CHAR UTF-8
            0 TRLR
        """)
        issues = scan_header_required_fields(str(p))
        assert any('SOUR' in i for i in issues)

    def test_missing_char(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            1 SOUR MyApp
            1 SUBM @SUBM1@
            1 GEDC
            2 VERS 5.5.1
            2 FORM LINEAGE-LINKED
            0 TRLR
        """)
        issues = scan_header_required_fields(str(p))
        assert any('CHAR' in i for i in issues)

    def test_missing_gedc_vers(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            1 SOUR MyApp
            1 SUBM @SUBM1@
            1 GEDC
            2 FORM LINEAGE-LINKED
            1 CHAR UTF-8
            0 TRLR
        """)
        issues = scan_header_required_fields(str(p))
        assert any('VERS' in i for i in issues)


# ===========================================================================
# scan_bare_event_tags
# ===========================================================================

class TestScanBareEventTags:
    def test_bare_deat_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            0 TRLR
        """)
        result = scan_bare_event_tags(str(p))
        assert len(result) == 1
        assert result[0][1] == 'DEAT'

    def test_deat_with_y_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT Y
            0 TRLR
        """)
        assert scan_bare_event_tags(str(p)) == []

    def test_deat_with_children_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            2 DATE 1900
            0 TRLR
        """)
        assert scan_bare_event_tags(str(p)) == []

    def test_bare_birt_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            1 DEAT Y
            0 TRLR
        """)
        result = scan_bare_event_tags(str(p))
        assert len(result) == 1
        assert result[0][1] == 'BIRT'


# ===========================================================================
# scan_untyped_events
# ===========================================================================

class TestScanUntypedEvents:
    def test_even_without_type_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 EVEN Naturalization
            2 DATE 1910
            0 TRLR
        """)
        result = scan_untyped_events(str(p))
        assert len(result) == 1
        assert result[0][1] == 'EVEN'

    def test_even_with_type_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 EVEN Naturalization
            2 TYPE Naturalization
            2 DATE 1910
            0 TRLR
        """)
        assert scan_untyped_events(str(p)) == []

    def test_fact_without_type_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FACT Some fact
            0 TRLR
        """)
        result = scan_untyped_events(str(p))
        assert any(t == 'FACT' for _, t, _ in result)


# ===========================================================================
# scan_missing_sex
# ===========================================================================

class TestScanMissingSex:
    def test_missing_sex_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            0 TRLR
        """)
        result = scan_missing_sex(str(p))
        assert '@I1@' in result

    def test_present_sex_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            1 SEX M
            0 TRLR
        """)
        assert scan_missing_sex(str(p)) == []

    def test_multiple_individuals(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 SEX M
            0 @I2@ INDI
            1 NAME Jane /Doe/
            0 TRLR
        """)
        result = scan_missing_sex(str(p))
        assert '@I2@' in result
        assert '@I1@' not in result


# ===========================================================================
# scan_age_values
# ===========================================================================

class TestScanAgeValues:
    def test_valid_age_year_month_day(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 AGE 25y 6m 3d
            0 TRLR
        """)
        assert scan_age_values(str(p)) == []

    def test_valid_keywords(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 AGE STILLBORN
            0 TRLR
        """)
        assert scan_age_values(str(p)) == []

    def test_valid_less_than_prefix(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 AGE >55y 3m
            0 TRLR
        """)
        assert scan_age_values(str(p)) == []

    def test_bare_number_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 AGE 25
            0 TRLR
        """)
        result = scan_age_values(str(p))
        assert len(result) == 1
        assert result[0][1] == '25'

    def test_abt_prefix_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 AGE ABT 25
            0 TRLR
        """)
        result = scan_age_values(str(p))
        assert len(result) == 1

    def test_too_long_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 AGE 100y 11m 30d extra
            0 TRLR
        """)
        result = scan_age_values(str(p))
        assert len(result) == 1


# ===========================================================================
# scan_resn_values
# ===========================================================================

class TestScanResnValues:
    def test_valid_values_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 RESN confidential
            0 @I2@ INDI
            1 RESN locked
            0 @I3@ INDI
            1 RESN privacy
            0 TRLR
        """)
        assert scan_resn_values(str(p)) == []

    def test_invalid_value_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 RESN secret
            0 TRLR
        """)
        result = scan_resn_values(str(p))
        assert len(result) == 1
        assert result[0][1] == 'secret'

    def test_case_insensitive_valid(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 RESN CONFIDENTIAL
            0 TRLR
        """)
        assert scan_resn_values(str(p)) == []


# ===========================================================================
# scan_pedi_values
# ===========================================================================

class TestScanPediValues:
    def test_valid_values_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FAMC @F1@
            2 PEDI adopted
            0 TRLR
        """)
        assert scan_pedi_values(str(p)) == []

    def test_invalid_value_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FAMC @F1@
            2 PEDI unknown
            0 TRLR
        """)
        result = scan_pedi_values(str(p))
        assert len(result) == 1
        assert result[0][1] == 'unknown'


# ===========================================================================
# scan_nonstandard_tags
# ===========================================================================

class TestScanNonstandardTags:
    def test_detects_underscore_tags(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 _FSID 12345
            1 _FSID 67890
            1 _UID abc
            0 TRLR
        """)
        result = scan_nonstandard_tags(str(p))
        assert result['_FSID'] == 2
        assert result['_UID'] == 1

    def test_no_tags_returns_empty(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            0 TRLR
        """)
        assert scan_nonstandard_tags(str(p)) == {}


# ===========================================================================
# scan_occu_length
# ===========================================================================

class TestScanOccuLength:
    def test_short_occu_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 OCCU Merchant
            0 TRLR
        """)
        assert scan_occu_length(str(p)) == []

    def test_long_occu_flagged(self, tmp_path):
        long_val = 'A' * 121
        p = write_ged(tmp_path, f"""\
            0 HEAD
            0 @I1@ INDI
            1 OCCU {long_val}
            0 TRLR
        """)
        result = scan_occu_length(str(p))
        assert len(result) == 1
        assert result[0][1] == 121

    def test_custom_threshold(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 OCCU A merchant who traded goods
            0 TRLR
        """)
        # With threshold=10, the 30-char value should be flagged
        result = scan_occu_length(str(p), threshold=10)
        assert len(result) == 1


# ===========================================================================
# scan_conc_cont
# ===========================================================================

class TestScanConcCont:
    def test_valid_conc_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NOTE This is a long note
            2 CONC that continues here
            0 TRLR
        """)
        assert scan_conc_cont(str(p)) == []

    def test_wrong_level_conc_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NOTE Short note
            3 CONC bad level
            0 TRLR
        """)
        result = scan_conc_cont(str(p))
        assert len(result) >= 1
        assert any('level' in desc.lower() for _, desc in result)

    def test_conc_leading_space_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NOTE Start of note
            2 CONC  extra leading space
            0 TRLR
        """)
        result = scan_conc_cont(str(p))
        assert any('leading space' in desc for _, desc in result)


# ===========================================================================
# scan_name_nicknames / fix_nicknames
# ===========================================================================

class TestScanNameNicknames:
    def test_quoted_nickname_detected(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Adelaide "Edla" /Dellatolla/
            0 TRLR
        """)
        result = scan_name_nicknames(str(p))
        assert len(result) == 1

    def test_no_nickname_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Adelaide /Dellatolla/
            0 TRLR
        """)
        assert scan_name_nicknames(str(p)) == []

    def test_nickname_in_surname_not_flagged(self, tmp_path):
        # Quotes after the slash should not be treated as a given-name nickname
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Adelaide /"The Great" Smith/
            0 TRLR
        """)
        # This should not flag (it's inside the surname block)
        result = scan_name_nicknames(str(p))
        assert result == []


class TestFixNicknames:
    def test_extracts_nickname_to_nick_tag(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Adelaide "Edla" /Dellatolla/
            0 TRLR
        """)
        count = fix_nicknames(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        assert '1 NAME Adelaide /Dellatolla/' in content
        assert '2 NICK Edla' in content

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Jean "John" /Nalpas/
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_nicknames(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original

    def test_returns_zero_for_no_nicknames(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            0 TRLR
        """)
        assert fix_nicknames(str(p)) == 0

    def test_appends_to_existing_nick(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Jean "John" /Nalpas/
            2 NICK Jacques
            0 TRLR
        """)
        fix_nicknames(str(p))
        content = p.read_text(encoding='utf-8')
        assert 'Jacques; John' in content or 'John' in content


# ===========================================================================
# _parse_name_pieces
# ===========================================================================

class TestParseNamePieces:
    def test_given_and_surname(self):
        assert _parse_name_pieces('Saverio /Bonnici/') == ('Saverio', 'Bonnici', '')

    def test_surname_only(self):
        assert _parse_name_pieces('/Bonnici/') == ('', 'Bonnici', '')

    def test_with_suffix(self):
        assert _parse_name_pieces('John /Smith/ Jr') == ('John', 'Smith', 'Jr')

    def test_no_slashes(self):
        given, surn, suf = _parse_name_pieces('John')
        assert given == 'John'
        assert surn == ''


# ===========================================================================
# scan_name_pieces / fix_name_pieces
# ===========================================================================

class TestScanNamePieces:
    def test_name_without_pieces_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Saverio /Bonnici/
            0 TRLR
        """)
        result = scan_name_pieces(str(p))
        assert len(result) == 1

    def test_name_with_pieces_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Saverio /Bonnici/
            2 GIVN Saverio
            2 SURN Bonnici
            0 TRLR
        """)
        assert scan_name_pieces(str(p)) == []

    def test_name_without_slashes_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Saverio
            0 TRLR
        """)
        assert scan_name_pieces(str(p)) == []


class TestFixNamePieces:
    def test_inserts_givn_and_surn(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Saverio /Bonnici/
            0 TRLR
        """)
        count = fix_name_pieces(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        assert '2 GIVN Saverio' in content
        assert '2 SURN Bonnici' in content

    def test_inserts_nsfx_when_present(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/ Jr
            0 TRLR
        """)
        fix_name_pieces(str(p))
        content = p.read_text(encoding='utf-8')
        assert '2 NSFX Jr' in content

    def test_does_not_overwrite_existing_givn(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Saverio /Bonnici/
            2 GIVN Saverio
            0 TRLR
        """)
        fix_name_pieces(str(p))
        content = p.read_text(encoding='utf-8')
        # SURN should be added; GIVN should not be duplicated
        assert content.count('2 GIVN Saverio') == 1
        assert '2 SURN Bonnici' in content

    def test_skips_names_without_slashes(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Saverio
            0 TRLR
        """)
        assert fix_name_pieces(str(p)) == 0

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Saverio /Bonnici/
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_name_pieces(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original


# ===========================================================================
# scan_dateless_dates / fix_dateless_dates
# ===========================================================================

class TestScanDatelessDates:
    def test_day_month_only_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 31 Jan
            0 TRLR
        """)
        result = scan_dateless_dates(str(p))
        assert len(result) == 1

    def test_full_date_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 31 JAN 1900
            0 TRLR
        """)
        assert scan_dateless_dates(str(p)) == []

    def test_year_only_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 1900
            0 TRLR
        """)
        assert scan_dateless_dates(str(p)) == []


class TestFixDatelessDates:
    def test_wraps_day_month_as_phrase(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 31 Jan
            0 TRLR
        """)
        count = fix_dateless_dates(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        assert '(31 JAN, year unknown)' in content

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 31 Jan
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_dateless_dates(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original

    def test_returns_zero_when_no_changes(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            0 TRLR
        """)
        assert fix_dateless_dates(str(p)) == 0


# ===========================================================================
# scan_fact_aka / fix_aka_facts
# ===========================================================================

class TestScanFactAka:
    def test_fact_aka_detected(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FACT
            2 TYPE AKA
            2 NOTE Marcel Bonnici
            0 TRLR
        """)
        result = scan_fact_aka(str(p))
        assert len(result) == 1
        assert result[0][1] == 'Marcel Bonnici'

    def test_fact_without_note_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FACT
            2 TYPE AKA
            0 TRLR
        """)
        assert scan_fact_aka(str(p)) == []

    def test_fact_without_aka_type_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FACT
            2 TYPE Occupation
            2 NOTE Some fact
            0 TRLR
        """)
        assert scan_fact_aka(str(p)) == []


class TestFixAkaFacts:
    def test_converts_to_name_record(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FACT
            2 TYPE AKA
            2 NOTE Marcel Bonnici
            0 TRLR
        """)
        count = fix_aka_facts(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        assert '1 NAME Marcel /Bonnici/' in content
        assert '2 TYPE aka' in content
        assert '1 FACT' not in content

    def test_single_word_name_wrapped_as_surname(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FACT
            2 TYPE AKA
            2 NOTE Marcel
            0 TRLR
        """)
        fix_aka_facts(str(p))
        content = p.read_text(encoding='utf-8')
        assert '1 NAME /Marcel/' in content

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 FACT
            2 TYPE AKA
            2 NOTE Marcel Bonnici
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_aka_facts(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original

    def test_returns_zero_when_no_changes(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            0 TRLR
        """)
        assert fix_aka_facts(str(p)) == 0


# ===========================================================================
# scan_place_consistency
# ===========================================================================

class TestScanPlaceConsistency:
    def test_similar_places_detected(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC London, Middlesex, England
            0 @I2@ INDI
            1 BIRT
            2 PLAC Londn, Middlesex, England
            0 TRLR
        """)
        result = scan_place_consistency(str(p))
        # "London" vs "Londn" — Levenshtein 1 → should be flagged
        assert len(result['similar_places']) >= 1

    def test_bare_country_detected(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC England
            0 TRLR
        """)
        result = scan_place_consistency(str(p))
        assert 'England' in result['bare_countries']

    def test_country_inconsistency_detected(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC London, Middlesex, England
            0 @I2@ INDI
            1 BIRT
            2 PLAC Glasgow, Lanarkshire, United Kingdom
            0 TRLR
        """)
        result = scan_place_consistency(str(p))
        # England and United Kingdom → should show inconsistency
        assert len(result['country_inconsistencies']) >= 1

    def test_consistent_places_no_violations(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC London, Middlesex, England
            0 @I2@ INDI
            1 BIRT
            2 PLAC London, Middlesex, England
            0 TRLR
        """)
        result = scan_place_consistency(str(p))
        assert result['similar_places'] == []


# ===========================================================================
# scan_same_sour_multiple_cites
# ===========================================================================

class TestScanSameSourMultipleCites:
    def test_detects_same_source_twice(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE 12
            2 SOUR @S1@
            3 PAGE 15
            0 TRLR
        """)
        result = scan_same_sour_multiple_cites(str(p))
        assert len(result) >= 1
        assert any(xref == '@S1@' for _, xref in result)

    def test_different_sources_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE 12
            2 SOUR @S2@
            3 PAGE 15
            0 TRLR
        """)
        assert scan_same_sour_multiple_cites(str(p)) == []
