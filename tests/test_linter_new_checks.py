"""
Unit tests for the new scan/fix functions added in the linter expansion.

Pattern: write_ged(tmp_path, content) → call scan_*/fix_* → assert.
Follows the style of tests/test_fix_name_case.py.
"""
import textwrap
from pathlib import Path

import pytest

from gedcom_linter import (
    scan_html_entities,
    fix_html_entities,
    _decode_html_value,
    scan_bapm_without_birth,
    fix_bapm_without_birth,
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
    scan_name_piece_order,
    fix_name_piece_order,
    scan_event_source_order,
    fix_event_source_order,
    scan_redundant_citation_page,
    fix_redundant_citation_page,
    scan_repeated_citation_text,
    fix_repeated_citation_text,
    normalize_date,
    scan_sole_event_type_alternate,
    fix_sole_event_type_alternate,
    scan_name_piece_case,
    fix_name_piece_case,
    scan_unknown_surname,
    fix_unknown_surname,
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


# ===========================================================================
# scan_name_piece_order / fix_name_piece_order
# ===========================================================================

class TestScanNamePieceOrder:
    def test_type_before_givn_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Sasha N /Perigo/
            2 TYPE AKA
            2 SOUR @S1@
            2 GIVN Sasha N
            2 SURN Perigo
            0 TRLR
        """)
        result = scan_name_piece_order(str(p))
        assert len(result) == 1
        assert 'Sasha N /Perigo/' in result[0][1]

    def test_type_before_surn_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            2 GIVN John
            2 TYPE AKA
            2 SURN Smith
            0 TRLR
        """)
        result = scan_name_piece_order(str(p))
        assert len(result) == 1

    def test_correct_order_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Sasha N /Perigo/
            2 GIVN Sasha N
            2 SURN Perigo
            2 TYPE AKA
            2 SOUR @S1@
            0 TRLR
        """)
        assert scan_name_piece_order(str(p)) == []

    def test_no_type_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            2 SOUR @S1@
            2 GIVN John
            2 SURN Smith
            0 TRLR
        """)
        assert scan_name_piece_order(str(p)) == []

    def test_multiple_names_only_bad_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            2 GIVN John
            2 SURN Smith
            2 TYPE birth
            1 NAME Johnny /Smith/
            2 TYPE AKA
            2 GIVN Johnny
            2 SURN Smith
            0 TRLR
        """)
        result = scan_name_piece_order(str(p))
        assert len(result) == 1
        assert 'Johnny /Smith/' in result[0][1]


class TestFixNamePieceOrder:
    def test_moves_givn_surn_before_type(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Sasha N /Perigo/
            2 TYPE AKA
            2 SOUR @S1496244647@
            2 GIVN Sasha N
            2 SURN Perigo
            0 TRLR
        """)
        count = fix_name_piece_order(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        givn_pos = content.index('2 GIVN')
        surn_pos = content.index('2 SURN')
        type_pos = content.index('2 TYPE')
        sour_pos = content.index('2 SOUR')
        assert givn_pos < type_pos
        assert surn_pos < type_pos
        assert type_pos < sour_pos

    def test_preserves_sour_children(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Sasha N /Perigo/
            2 TYPE AKA
            2 SOUR @S1@
            3 PAGE Some page reference
            2 GIVN Sasha N
            2 SURN Perigo
            0 TRLR
        """)
        fix_name_piece_order(str(p))
        content = p.read_text(encoding='utf-8')
        assert '3 PAGE Some page reference' in content
        # PAGE must still follow its SOUR
        sour_pos = content.index('2 SOUR')
        page_pos = content.index('3 PAGE')
        assert sour_pos < page_pos

    def test_already_correct_order_unchanged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            2 GIVN John
            2 SURN Smith
            2 TYPE AKA
            2 SOUR @S1@
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        count = fix_name_piece_order(str(p))
        assert count == 0
        assert p.read_text(encoding='utf-8') == original

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Sasha N /Perigo/
            2 TYPE AKA
            2 GIVN Sasha N
            2 SURN Perigo
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_name_piece_order(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original

    def test_nsfx_treated_as_name_piece(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/ Jr.
            2 TYPE AKA
            2 GIVN John
            2 SURN Smith
            2 NSFX Jr.
            0 TRLR
        """)
        count = fix_name_piece_order(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        type_pos = content.index('2 TYPE')
        nsfx_pos = content.index('2 NSFX')
        assert nsfx_pos < type_pos


# ===========================================================================
# scan_event_source_order / fix_event_source_order
# ===========================================================================

class TestScanEventSourceOrder:
    def test_sour_before_other_flagged(self, tmp_path):
        """SOUR appearing before DATE in a DEAT block is a violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            2 SOUR @S1@
            2 DATE 6 SEP 1922
            2 PLAC Smyrna, Turkey
            0 TRLR
        """)
        violations = scan_event_source_order(str(p))
        assert len(violations) == 1
        assert violations[0][1] == 'DEAT'

    def test_note_before_sour_flagged(self, tmp_path):
        """NOTE appearing before SOUR is a violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 1 JAN 1900
            2 NOTE Born at home
            2 SOUR @S1@
            0 TRLR
        """)
        violations = scan_event_source_order(str(p))
        assert len(violations) == 1
        assert violations[0][1] == 'BIRT'

    def test_note_before_other_flagged(self, tmp_path):
        """NOTE appearing before DATE is a violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 MARR
            2 NOTE Wedding in church
            2 DATE 15 JUN 1950
            0 TRLR
        """)
        violations = scan_event_source_order(str(p))
        assert len(violations) == 1
        assert violations[0][1] == 'MARR'

    def test_correct_order_not_flagged(self, tmp_path):
        """DATE → PLAC → ADDR → SOUR → NOTE is the correct order."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            2 DATE 6 SEP 1922
            2 PLAC Smyrna, Izmir, Turkey
            2 ADDR Notre Dame du Rosaire Church
            2 SOUR @S1@
            3 PAGE Death record
            2 NOTE died a week before Smyrna was burned
            0 TRLR
        """)
        violations = scan_event_source_order(str(p))
        assert violations == []

    def test_no_sour_or_note_not_flagged(self, tmp_path):
        """Event with only DATE and PLAC is fine."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1885
            2 PLAC Greece
            0 TRLR
        """)
        violations = scan_event_source_order(str(p))
        assert violations == []

    def test_name_block_not_affected(self, tmp_path):
        """NAME blocks are governed by name_piece_order, not this check."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            2 SOUR @S1@
            2 GIVN John
            2 SURN Smith
            0 TRLR
        """)
        violations = scan_event_source_order(str(p))
        assert violations == []

    def test_multiple_events_only_bad_ones_flagged(self, tmp_path):
        """Only events with wrong order are flagged; correct events are not."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 1 JAN 1900
            2 PLAC Paris, France
            1 DEAT
            2 SOUR @S1@
            2 DATE 6 SEP 1922
            0 TRLR
        """)
        violations = scan_event_source_order(str(p))
        assert len(violations) == 1
        assert violations[0][1] == 'DEAT'


class TestFixEventSourceOrder:
    def test_moves_sour_after_details(self, tmp_path):
        """SOUR appearing before DATE is moved to after DATE and PLAC."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            2 SOUR @S1@
            2 DATE 6 SEP 1922
            2 PLAC Smyrna, Turkey
            0 TRLR
        """)
        count = fix_event_source_order(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        date_pos = content.index('2 DATE')
        sour_pos = content.index('2 SOUR')
        assert date_pos < sour_pos

    def test_moves_note_last(self, tmp_path):
        """NOTE appearing before SOUR is moved to after SOUR."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 1 JAN 1900
            2 NOTE Born at home
            2 SOUR @S1@
            0 TRLR
        """)
        count = fix_event_source_order(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        sour_pos = content.index('2 SOUR')
        note_pos = content.index('2 NOTE')
        assert sour_pos < note_pos

    def test_preserves_sour_children(self, tmp_path):
        """PAGE and DATA children of SOUR stay attached to their SOUR."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            2 SOUR @S1@
            3 PAGE Death record p.42
            3 DATA
            4 DATE 1922
            2 DATE 6 SEP 1922
            2 ADDR Notre Dame du Rosaire
            0 TRLR
        """)
        fix_event_source_order(str(p))
        content = p.read_text(encoding='utf-8')
        # PAGE must still follow its SOUR
        sour_pos = content.index('2 SOUR')
        page_pos = content.index('3 PAGE')
        date_pos = content.index('2 DATE')
        assert date_pos < sour_pos
        assert sour_pos < page_pos

    def test_full_example_reorder(self, tmp_path):
        """Reproduces the exact incorrect→correct example from the spec."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            2 DATE 6 SEP 1922
            2 PLAC Smyrna, Izmir, Turkey
            2 SOUR @S1@
            2 SOUR @S2@
            3 PAGE Death record
            3 DATA
            4 DATE 1922
            2 NOTE died a week before Smyrna was burned to the ground
            2 ADDR Notre Dame du Rosaire Church
            0 TRLR
        """)
        count = fix_event_source_order(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 1
        addr_pos = content.index('2 ADDR')
        sour_pos = content.index('2 SOUR')
        note_pos = content.index('2 NOTE')
        assert addr_pos < sour_pos
        assert sour_pos < note_pos

    def test_already_correct_unchanged(self, tmp_path):
        """Correctly ordered event returns count=0 and file unchanged."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            2 DATE 6 SEP 1922
            2 PLAC Smyrna, Izmir, Turkey
            2 ADDR Notre Dame du Rosaire Church
            2 SOUR @S1@
            2 NOTE died a week before Smyrna was burned
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        count = fix_event_source_order(str(p))
        assert count == 0
        assert p.read_text(encoding='utf-8') == original

    def test_dry_run_no_write(self, tmp_path):
        """dry_run=True computes changes but does not write the file."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            2 DATE 1 JAN 1900
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        count = fix_event_source_order(str(p), dry_run=True)
        assert count == 1
        assert p.read_text(encoding='utf-8') == original


# ===========================================================================
# scan_redundant_citation_page / fix_redundant_citation_page
# ===========================================================================

class TestScanRedundantCitationPage:
    def test_page_matching_titl_flagged(self, tmp_path):
        """PAGE value identical to source TITL is a violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Ancestry Family Trees
            0 TRLR
        """)
        violations = scan_redundant_citation_page(str(p))
        assert len(violations) == 1
        assert violations[0][1] == '@S1@'

    def test_page_different_from_titl_not_flagged(self, tmp_path):
        """PAGE with actual locator info is not flagged."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Page 42
            0 TRLR
        """)
        assert scan_redundant_citation_page(str(p)) == []

    def test_no_page_not_flagged(self, tmp_path):
        """Bare citation with no PAGE is not flagged."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            0 TRLR
        """)
        assert scan_redundant_citation_page(str(p)) == []

    def test_case_insensitive_match(self, tmp_path):
        """Match is case-insensitive."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE ancestry family trees
            0 TRLR
        """)
        assert len(scan_redundant_citation_page(str(p))) == 1

    def test_plural_singular_normalised(self, tmp_path):
        """PAGE 'Ancestry Family Tree' matches TITL 'Ancestry Family Trees'."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Ancestry Family Tree
            0 TRLR
        """)
        violations = scan_redundant_citation_page(str(p))
        assert len(violations) == 1

    def test_only_matching_source_flagged(self, tmp_path):
        """Two sources; only the one whose PAGE matches its TITL is flagged."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @S2@ SOUR
            1 TITL Other Source
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Ancestry Family Trees
            2 SOUR @S2@
            3 PAGE Page 7
            0 TRLR
        """)
        violations = scan_redundant_citation_page(str(p))
        assert len(violations) == 1
        assert violations[0][1] == '@S1@'


class TestFixRedundantCitationPage:
    def test_removes_redundant_page_line(self, tmp_path):
        """The matching PAGE line is deleted from the citation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Ancestry Family Trees
            0 TRLR
        """)
        count = fix_redundant_citation_page(str(p))
        assert count == 1
        assert '3 PAGE Ancestry Family Trees' not in p.read_text(encoding='utf-8')

    def test_preserves_informative_page(self, tmp_path):
        """PAGE with an actual locator is not touched; count=0, file unchanged."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Page 42
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        count = fix_redundant_citation_page(str(p))
        assert count == 0
        assert p.read_text(encoding='utf-8') == original

    def test_preserves_data_and_note_in_citation(self, tmp_path):
        """Other citation sub-tags (DATA, NOTE) survive the fix."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Ancestry Family Trees
            3 DATA
            4 DATE 1900
            2 NOTE Some note
            0 TRLR
        """)
        fix_redundant_citation_page(str(p))
        content = p.read_text(encoding='utf-8')
        assert '4 DATE 1900' in content
        assert '2 NOTE Some note' in content

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Ancestry Family Trees
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_redundant_citation_page(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original

    def test_multiple_redundant_pages_all_removed(self, tmp_path):
        """All matching PAGE lines across multiple citations are removed."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Ancestry Family Trees
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE Ancestry Family Trees
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S1@
            3 PAGE Ancestry Family Trees
            0 TRLR
        """)
        count = fix_redundant_citation_page(str(p))
        assert count == 2
        assert p.read_text(encoding='utf-8').count('PAGE Ancestry Family Trees') == 0


# ===========================================================================
# scan_repeated_citation_text / fix_repeated_citation_text
# ===========================================================================

class TestScanRepeatedCitationText:
    def test_two_identical_texts_same_source_flagged(self, tmp_path):
        """Same TEXT in ≥2 citations to the same source → violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Some Essay
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 DATA
            4 TEXT Family history narrative here.
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S1@
            3 DATA
            4 TEXT Family history narrative here.
            0 TRLR
        """)
        violations = scan_repeated_citation_text(str(p))
        assert len(violations) == 1
        assert violations[0][0] == '@S1@'
        assert violations[0][2] == 2

    def test_different_texts_same_source_not_flagged(self, tmp_path):
        """Different TEXT values for the same source are not flagged."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Some Essay
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 DATA
            4 TEXT Unique text for person one.
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S1@
            3 DATA
            4 TEXT Different text for person two.
            0 TRLR
        """)
        assert scan_repeated_citation_text(str(p)) == []

    def test_single_occurrence_not_flagged(self, tmp_path):
        """TEXT appearing only once is not flagged."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Some Essay
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 DATA
            4 TEXT Only appears once.
            0 TRLR
        """)
        assert scan_repeated_citation_text(str(p)) == []

    def test_same_text_different_sources_not_grouped(self, tmp_path):
        """Same TEXT in citations to DIFFERENT sources is not a violation."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Source One
            0 @S2@ SOUR
            1 TITL Source Two
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 DATA
            4 TEXT Same narrative text.
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S2@
            3 DATA
            4 TEXT Same narrative text.
            0 TRLR
        """)
        assert scan_repeated_citation_text(str(p)) == []


class TestFixRepeatedCitationText:
    def test_text_moved_to_source_record(self, tmp_path):
        """TEXT that repeats in citations is injected into the source record."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Some Essay
            1 AUTH Someone
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 DATA
            4 TEXT Family history narrative.
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S1@
            3 DATA
            4 TEXT Family history narrative.
            0 TRLR
        """)
        count = fix_repeated_citation_text(str(p))
        content = p.read_text(encoding='utf-8')
        assert count == 2
        assert '1 TEXT Family history narrative.' in content

    def test_text_removed_from_citations(self, tmp_path):
        """After the fix, inline citations no longer carry the repeated TEXT."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Some Essay
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 DATA
            4 TEXT Family history narrative.
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S1@
            3 DATA
            4 TEXT Family history narrative.
            0 TRLR
        """)
        fix_repeated_citation_text(str(p))
        content = p.read_text(encoding='utf-8')
        assert content.count('4 TEXT Family history narrative.') == 0

    def test_preserves_other_citation_content(self, tmp_path):
        """PAGE, DATA/DATE, and WWW lines are preserved after TEXT removal."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Essay Source
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 PAGE pages 11-39
            3 DATA
            4 DATE 1993
            4 TEXT Family narrative.
            4 WWW https://example.com
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S1@
            3 PAGE pages 11-39
            3 DATA
            4 DATE 1993
            4 TEXT Family narrative.
            4 WWW https://example.com
            0 TRLR
        """)
        fix_repeated_citation_text(str(p))
        content = p.read_text(encoding='utf-8')
        assert content.count('3 PAGE pages 11-39') == 2
        assert content.count('4 DATE 1993') == 2
        assert content.count('4 WWW https://example.com') == 2

    def test_cont_lines_moved_correctly(self, tmp_path):
        """Multi-line TEXT with CONT lines is moved with CONT → level 2 CONT."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Essay
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 DATA
            4 TEXT First line of text.
            5 CONT Second line.
            5 CONT Third line.
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S1@
            3 DATA
            4 TEXT First line of text.
            5 CONT Second line.
            5 CONT Third line.
            0 TRLR
        """)
        fix_repeated_citation_text(str(p))
        content = p.read_text(encoding='utf-8')
        assert '1 TEXT First line of text.' in content
        assert '2 CONT Second line.' in content
        assert '2 CONT Third line.' in content
        assert '5 CONT Second line.' not in content

    def test_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Some Essay
            0 @I1@ INDI
            1 BIRT
            2 SOUR @S1@
            3 DATA
            4 TEXT Narrative.
            0 @I2@ INDI
            1 DEAT
            2 SOUR @S1@
            3 DATA
            4 TEXT Narrative.
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_repeated_citation_text(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original


# ===========================================================================
# scan_bapm_without_birth / fix_bapm_without_birth
# ===========================================================================

class TestFixBirthFromBapm:

    def test_scan_finds_bapm_without_birth(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BAPM
            2 DATE 15 MAR 1875
            0 TRLR
        """)
        result = scan_bapm_without_birth(str(p))
        assert len(result) == 1
        xref, _lineno, year = result[0]
        assert xref == '@I1@'
        assert year == 1875

    def test_scan_uses_chr_tag(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 CHR
            2 DATE 3 JUN 1902
            0 TRLR
        """)
        result = scan_bapm_without_birth(str(p))
        assert len(result) == 1
        assert result[0][2] == 1902

    def test_scan_ignores_individual_with_birth_date(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 10 FEB 1875
            1 BAPM
            2 DATE 15 MAR 1875
            0 TRLR
        """)
        assert scan_bapm_without_birth(str(p)) == []

    def test_scan_ignores_birt_with_no_date(self, tmp_path):
        # BIRT block exists but has no DATE → still needs EST birth date
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC London, England
            1 BAPM
            2 DATE 1 JAN 1880
            0 TRLR
        """)
        result = scan_bapm_without_birth(str(p))
        assert len(result) == 1
        assert result[0][2] == 1880

    def test_scan_ignores_bapm_without_date(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BAPM
            2 PLAC Paris, France
            0 TRLR
        """)
        assert scan_bapm_without_birth(str(p)) == []

    def test_fix_inserts_birt_block(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BAPM
            2 DATE 15 MAR 1875
            0 TRLR
        """)
        count = fix_bapm_without_birth(str(p))
        assert count == 1
        content = p.read_text(encoding='utf-8')
        lines = content.splitlines()
        # Find the INDI header line
        indi_idx = next(i for i, l in enumerate(lines) if '0 @I1@ INDI' in l)
        # The two inserted lines should be immediately after it
        assert lines[indi_idx + 1].strip() == '1 BIRT'
        assert lines[indi_idx + 2].strip() == '2 DATE EST 1875'

    def test_fix_adds_date_to_existing_birt(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 PLAC London, England
            1 BAPM
            2 DATE 1 JAN 1880
            0 TRLR
        """)
        count = fix_bapm_without_birth(str(p))
        assert count == 1
        content = p.read_text(encoding='utf-8')
        lines = content.splitlines()
        birt_idx = next(i for i, l in enumerate(lines) if l.strip() == '1 BIRT')
        # DATE should be inserted right after the 1 BIRT line
        assert lines[birt_idx + 1].strip() == '2 DATE EST 1880'

    def test_fix_dry_run_makes_no_changes(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BAPM
            2 DATE 15 MAR 1875
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        count = fix_bapm_without_birth(str(p), dry_run=True)
        assert count == 1
        assert p.read_text(encoding='utf-8') == original

    def test_fix_idempotent(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BAPM
            2 DATE 15 MAR 1875
            0 TRLR
        """)
        fix_bapm_without_birth(str(p))
        count2 = fix_bapm_without_birth(str(p))
        assert count2 == 0

    def test_fix_leaves_unaffected_individuals_alone(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 5 APR 1870
            1 BAPM
            2 DATE 20 APR 1870
            0 @I2@ INDI
            1 BAPM
            2 DATE 10 JUL 1890
            0 TRLR
        """)
        count = fix_bapm_without_birth(str(p))
        assert count == 1
        content = p.read_text(encoding='utf-8')
        # I1 should keep only its original BIRT DATE (5 APR 1870), not gain an EST date
        assert 'EST 1870' not in content
        # I2 should get the estimated birth date
        assert 'EST 1890' in content


# ===========================================================================
# scan_sole_event_type_alternate / fix_sole_event_type_alternate
# ===========================================================================

class TestSoleEventTypeAlternate:

    # --- scan ---

    def test_scan_sole_birt_with_type_alternate(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            2 TYPE alternate
            0 TRLR
        """)
        hits = scan_sole_event_type_alternate(str(p))
        assert len(hits) == 1
        assert hits[0][1] == 'BIRT'

    def test_scan_sole_deat_with_type_alternate(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 DEAT
            2 DATE 1910
            2 TYPE alternate
            0 TRLR
        """)
        hits = scan_sole_event_type_alternate(str(p))
        assert len(hits) == 1
        assert hits[0][1] == 'DEAT'

    def test_scan_no_hit_when_two_births(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 MAR 1842
            1 BIRT
            2 DATE ABT 1840
            2 TYPE alternate
            0 TRLR
        """)
        assert scan_sole_event_type_alternate(str(p)) == []

    def test_scan_no_hit_when_no_type_alternate(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 MAR 1842
            0 TRLR
        """)
        assert scan_sole_event_type_alternate(str(p)) == []

    def test_scan_case_insensitive(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            2 TYPE Alternate
            0 TRLR
        """)
        assert len(scan_sole_event_type_alternate(str(p))) == 1

    def test_scan_other_type_value_not_flagged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            2 TYPE calculated
            0 TRLR
        """)
        assert scan_sole_event_type_alternate(str(p)) == []

    def test_scan_multiple_individuals(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            2 TYPE alternate
            0 @I2@ INDI
            1 BIRT
            2 DATE 10 JUN 1860
            1 BIRT
            2 DATE ABT 1860
            2 TYPE alternate
            0 @I3@ INDI
            1 DEAT
            2 DATE 1930
            2 TYPE alternate
            0 TRLR
        """)
        hits = scan_sole_event_type_alternate(str(p))
        # I1 (sole BIRT) and I3 (sole DEAT) are flagged; I2 has two BIRTs so not flagged
        assert len(hits) == 2
        xrefs = {h[2] for h in hits}
        assert '@I1@' in xrefs
        assert '@I3@' in xrefs
        assert '@I2@' not in xrefs

    # --- fix ---

    def test_fix_removes_type_alternate_line(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            2 TYPE alternate
            0 TRLR
        """)
        count = fix_sole_event_type_alternate(str(p))
        assert count == 1
        assert '2 TYPE alternate' not in p.read_text(encoding='utf-8')

    def test_fix_preserves_date_and_other_fields(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            2 PLAC Boston, Massachusetts
            2 TYPE alternate
            0 TRLR
        """)
        fix_sole_event_type_alternate(str(p))
        content = p.read_text(encoding='utf-8')
        assert '2 DATE ABT 1850' in content
        assert '2 PLAC Boston, Massachusetts' in content
        assert '2 TYPE alternate' not in content

    def test_fix_leaves_two_birt_alternate_alone(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE 15 MAR 1842
            1 BIRT
            2 DATE ABT 1840
            2 TYPE alternate
            0 TRLR
        """)
        count = fix_sole_event_type_alternate(str(p))
        assert count == 0
        assert '2 TYPE alternate' in p.read_text(encoding='utf-8')

    def test_fix_idempotent(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            2 TYPE alternate
            0 TRLR
        """)
        fix_sole_event_type_alternate(str(p))
        count2 = fix_sole_event_type_alternate(str(p))
        assert count2 == 0

    def test_fix_dry_run_does_not_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 BIRT
            2 DATE ABT 1850
            2 TYPE alternate
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_sole_event_type_alternate(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original


# ===========================================================================
# scan_name_piece_case / fix_name_piece_case
# ===========================================================================

class TestNamePieceCase:

    # --- scan ---

    def test_scan_detects_allcaps_givn_under_titlecase_name(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Anitsa /Vitali/
            2 GIVN ANITSA
            2 SURN VITALI
            0 TRLR
        """)
        hits = scan_name_piece_case(str(p))
        assert len(hits) == 2
        tags = {h[1] for h in hits}
        assert tags == {'GIVN', 'SURN'}

    def test_scan_no_hit_when_pieces_match_name_case(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Anitsa /Vitali/
            2 GIVN Anitsa
            2 SURN Vitali
            0 TRLR
        """)
        assert scan_name_piece_case(str(p)) == []

    def test_scan_no_hit_when_both_allcaps(self, tmp_path):
        """Both NAME and pieces all-caps is consistent — fix_name_case handles it."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME ANITSA /VITALI/
            2 GIVN ANITSA
            2 SURN VITALI
            0 TRLR
        """)
        assert scan_name_piece_case(str(p)) == []

    def test_scan_detects_only_givn_when_surn_is_fine(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Anitsa /Vitali/
            2 GIVN ANITSA
            2 SURN Vitali
            0 TRLR
        """)
        hits = scan_name_piece_case(str(p))
        assert len(hits) == 1
        assert hits[0][1] == 'GIVN'

    def test_scan_multiple_individuals(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Anitsa /Vitali/
            2 GIVN ANITSA
            2 SURN VITALI
            0 @I2@ INDI
            1 NAME John /Smith/
            2 GIVN John
            2 SURN Smith
            0 TRLR
        """)
        hits = scan_name_piece_case(str(p))
        assert len(hits) == 2  # only I1's GIVN and SURN

    # --- fix ---

    def test_fix_title_cases_allcaps_givn_surn(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Anitsa /Vitali/
            2 GIVN ANITSA
            2 SURN VITALI
            0 TRLR
        """)
        count = fix_name_piece_case(str(p))
        assert count == 2
        content = p.read_text(encoding='utf-8')
        assert '2 GIVN Anitsa' in content
        assert '2 SURN Vitali' in content
        assert '2 GIVN ANITSA' not in content
        assert '2 SURN VITALI' not in content

    def test_fix_name_line_unchanged(self, tmp_path):
        """fix_name_piece_case must not touch the NAME line itself."""
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Anitsa /Vitali/
            2 GIVN ANITSA
            2 SURN VITALI
            0 TRLR
        """)
        fix_name_piece_case(str(p))
        content = p.read_text(encoding='utf-8')
        assert '1 NAME Anitsa /Vitali/' in content

    def test_fix_name_case_also_fixes_pieces(self, tmp_path):
        """fix_name_case on an all-caps NAME should fix GIVN/SURN in the same pass."""
        from gedcom_linter import fix_name_case
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME ANITSA /VITALI/
            2 GIVN ANITSA
            2 SURN VITALI
            0 TRLR
        """)
        fix_name_case(str(p))
        content = p.read_text(encoding='utf-8')
        assert '1 NAME Anitsa /Vitali/' in content
        assert '2 GIVN Anitsa' in content
        assert '2 SURN Vitali' in content

    def test_fix_idempotent(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Anitsa /Vitali/
            2 GIVN ANITSA
            2 SURN VITALI
            0 TRLR
        """)
        fix_name_piece_case(str(p))
        count2 = fix_name_piece_case(str(p))
        assert count2 == 0

    def test_fix_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Anitsa /Vitali/
            2 GIVN ANITSA
            2 SURN VITALI
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_name_piece_case(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original


# ===========================================================================
# scan_unknown_surname / fix_unknown_surname
# ===========================================================================

class TestUnknownSurname:

    # --- scan ---

    def test_scan_detects_unknown_surname(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Zabelu /UNKNOWN/
            2 GIVN Zabelu
            2 SURN UNKNOWN
            0 TRLR
        """)
        hits = scan_unknown_surname(str(p))
        # Both the NAME line and the SURN sub-tag are flagged
        assert len(hits) == 2

    def test_scan_case_insensitive(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Zabelu /Unknown/
            0 TRLR
        """)
        assert len(scan_unknown_surname(str(p))) == 1

    def test_scan_no_hit_when_no_unknown(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            2 GIVN John
            2 SURN Smith
            0 TRLR
        """)
        assert scan_unknown_surname(str(p)) == []

    def test_scan_no_hit_for_empty_surname(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John //
            0 TRLR
        """)
        assert scan_unknown_surname(str(p)) == []

    def test_scan_multiple_individuals(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Zabelu /UNKNOWN/
            0 @I2@ INDI
            1 NAME John /Smith/
            0 @I3@ INDI
            1 NAME Marie /UNKNOWN/
            0 TRLR
        """)
        hits = scan_unknown_surname(str(p))
        assert len(hits) == 2

    # --- fix ---

    def test_fix_replaces_unknown_with_empty_slashes(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Zabelu /UNKNOWN/
            0 TRLR
        """)
        count = fix_unknown_surname(str(p))
        assert count == 1
        content = p.read_text(encoding='utf-8')
        assert '1 NAME Zabelu //' in content
        assert 'UNKNOWN' not in content

    def test_fix_removes_surn_unknown_subtag(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Zabelu /UNKNOWN/
            2 GIVN Zabelu
            2 SURN UNKNOWN
            0 TRLR
        """)
        fix_unknown_surname(str(p))
        content = p.read_text(encoding='utf-8')
        assert '2 SURN UNKNOWN' not in content
        assert '2 GIVN Zabelu' in content

    def test_fix_preserves_real_surnames(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME John /Smith/
            2 GIVN John
            2 SURN Smith
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        count = fix_unknown_surname(str(p))
        assert count == 0
        assert p.read_text(encoding='utf-8') == original

    def test_fix_idempotent(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Zabelu /UNKNOWN/
            2 GIVN Zabelu
            2 SURN UNKNOWN
            0 TRLR
        """)
        fix_unknown_surname(str(p))
        count2 = fix_unknown_surname(str(p))
        assert count2 == 0

    def test_fix_dry_run_no_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Zabelu /UNKNOWN/
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_unknown_surname(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original


# ===========================================================================
# _decode_html_value / scan_html_entities / fix_html_entities
# ===========================================================================

class TestDecodeHtmlValue:
    """Unit tests for the _decode_html_value helper."""

    def test_italic_tags_stripped(self):
        assert _decode_html_value('&lt;i&gt;Find a Grave&lt;/i&gt;') == 'Find a Grave'

    def test_nbsp_replaced_with_space(self):
        assert _decode_html_value('Cauchi 2 —&nbsp;MaltaGenealogy') == 'Cauchi 2 — MaltaGenealogy'

    def test_amp_decoded(self):
        assert _decode_html_value('England &amp; Wales') == 'England & Wales'

    def test_double_encoded_amp_in_url(self):
        val = 'https://example.com?a=1&amp;amp;b=2'
        assert _decode_html_value(val) == 'https://example.com?a=1&b=2'

    def test_apos_decoded(self):
        assert _decode_html_value("Angela&apos;s marriage") == "Angela's marriage"

    def test_quot_decoded(self):
        assert _decode_html_value('She said &quot;hello&quot;') == 'She said "hello"'

    def test_p_tag_becomes_space(self):
        result = _decode_html_value('&lt;p&gt;First.&lt;/p&gt;&lt;p&gt;Second.&lt;/p&gt;')
        assert result == 'First. Second.'

    def test_br_tag_becomes_space(self):
        result = _decode_html_value('Line one.&lt;br&gt;Line two.')
        assert result == 'Line one. Line two.'

    def test_anchor_preserved_as_text_url(self):
        val = ('Publication A1 848, NAID: &lt;a href="https://catalog.archives.gov/id/1227672"'
               ' target="_blank"&gt;1227672&lt;/a&gt;. General Records.')
        result = _decode_html_value(val)
        assert result == ('Publication A1 848, NAID: 1227672 '
                          '(https://catalog.archives.gov/id/1227672). General Records.')

    def test_anchor_template_url_drops_href(self):
        val = '&lt;a href="##SearchUrlPrefix##/search/dbextra.aspx?dbid=1082"&gt;View Sources&lt;/a&gt;.'
        assert _decode_html_value(val) == 'View Sources.'

    def test_anchor_url_equals_text_no_duplication(self):
        val = '&lt;a href="http://www.findagrave.com"&gt;http://www.findagrave.com&lt;/a&gt;'
        assert _decode_html_value(val) == 'http://www.findagrave.com'

    def test_bold_tags_stripped(self):
        assert _decode_html_value('&lt;b&gt;First name&lt;/b&gt; Alice') == 'First name Alice'

    def test_plain_value_unchanged(self):
        val = 'England and Wales, Death Index, 1989-2025'
        assert _decode_html_value(val) == val

    def test_multiple_spaces_collapsed(self):
        result = _decode_html_value('A &lt;b&gt;B&lt;/b&gt;  C')
        assert '  ' not in result


class TestScanHtmlEntities:

    def test_detects_encoded_italic(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 NOTE &lt;i&gt;Find a Grave&lt;/i&gt;.
            0 TRLR
        """)
        issues = scan_html_entities(str(p))
        assert len(issues) == 1
        assert issues[0][0] == 3  # line number

    def test_detects_nbsp(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Cauchi 2 —&nbsp;MaltaGenealogy Surname Page
            0 TRLR
        """)
        issues = scan_html_entities(str(p))
        assert len(issues) == 1

    def test_clean_file_no_issues(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Alice /Wonder/
            1 NOTE A plain note with & ampersand already decoded.
            0 TRLR
        """)
        assert scan_html_entities(str(p)) == []


class TestFixHtmlEntities:

    def test_italic_tags_removed(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 NOTE &lt;i&gt;Find a Grave&lt;/i&gt;. Find a Grave.
            0 TRLR
        """)
        fix_html_entities(str(p))
        content = p.read_text(encoding='utf-8')
        assert '&lt;' not in content
        assert '&gt;' not in content
        assert 'Find a Grave.' in content

    def test_anchor_becomes_text_url(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 NOTE NAID: &lt;a href="https://catalog.archives.gov/id/613857"&gt;613857&lt;/a&gt;.
            0 TRLR
        """)
        fix_html_entities(str(p))
        content = p.read_text(encoding='utf-8')
        assert '613857 (https://catalog.archives.gov/id/613857)' in content
        assert '&lt;' not in content

    def test_nbsp_in_title_replaced(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 TITL Cauchi 2 —&nbsp;MaltaGenealogy Surname Page
            0 TRLR
        """)
        fix_html_entities(str(p))
        content = p.read_text(encoding='utf-8')
        assert '&nbsp;' not in content
        assert 'Cauchi 2 — MaltaGenealogy Surname Page' in content

    def test_returns_changed_count(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 NOTE &lt;i&gt;Title One&lt;/i&gt;.
            1 NOTE &lt;i&gt;Title Two&lt;/i&gt;.
            1 NOTE Plain note, no HTML.
            0 TRLR
        """)
        n = fix_html_entities(str(p))
        assert n == 2

    def test_dry_run_does_not_write(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 NOTE &lt;i&gt;Find a Grave&lt;/i&gt;.
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        fix_html_entities(str(p), dry_run=True)
        assert p.read_text(encoding='utf-8') == original

    def test_clean_file_unchanged(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @I1@ INDI
            1 NAME Alice /Wonder/
            1 NOTE A plain note.
            0 TRLR
        """)
        original = p.read_text(encoding='utf-8')
        n = fix_html_entities(str(p))
        assert n == 0
        assert p.read_text(encoding='utf-8') == original

    def test_no_trailing_whitespace_after_fix(self, tmp_path):
        p = write_ged(tmp_path, """\
            0 HEAD
            0 @S1@ SOUR
            1 ADDR &lt;line /&gt;
            0 TRLR
        """)
        fix_html_entities(str(p))
        for line in p.read_text(encoding='utf-8').splitlines():
            assert line == line.rstrip(), f'trailing whitespace: {line!r}'
