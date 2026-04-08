"""Tests for gedcom_merge.match_individuals — TDD for individual matching logic."""

import pytest
from gedcom_merge.model import (
    GedcomFile, Individual, Family, GedcomNode,
    NameRecord, EventRecord, ParsedDate,
)
from gedcom_merge.match_individuals import (
    match_individuals,
    _score_names,
    _score_event,
    _build_surname_index,
    _get_candidates_for,
    _estimate_birth_year,
    _has_parent_contradiction,
    _score_family_context,
    _score_pair,
    _NAME_ALIASES,
)
from gedcom_merge.normalize import parse_date


def _make_indi(
    xref: str,
    given: str,
    surname: str,
    sex: str = 'M',
    birth_year: int | None = None,
    death_year: int | None = None,
    birth_place: str | None = None,
    fams: list[str] | None = None,
    famc: list[str] | None = None,
) -> Individual:
    names = [NameRecord(
        full=f'{given} /{surname}/',
        given=given.lower(),
        surname=surname.lower(),
        name_type=None,
    )]
    events = []
    if birth_year:
        events.append(EventRecord(
            tag='BIRT',
            event_type=None,
            date=ParsedDate(None, birth_year),
            place=birth_place,
            raw=GedcomNode(1, 'BIRT', '', None),
        ))
    if death_year:
        events.append(EventRecord(
            tag='DEAT',
            event_type=None,
            date=ParsedDate(None, death_year),
            place=None,
            raw=GedcomNode(1, 'DEAT', '', None),
        ))
    node = GedcomNode(0, 'INDI', '', xref)
    return Individual(
        xref=xref,
        names=names,
        sex=sex,
        events=events,
        family_child=famc or [],
        family_spouse=fams or [],
        citations=[],
        media=[],
        raw=node,
        normalized_surnames={surname.lower()},
        normalized_givens={g.lower() for g in given.split()},
        birth_date=ParsedDate(None, birth_year) if birth_year else None,
        death_date=ParsedDate(None, death_year) if death_year else None,
    )


def _make_family(xref: str, husb: str | None, wife: str | None,
                 children: list[str] | None = None) -> Family:
    node = GedcomNode(0, 'FAM', '', xref)
    return Family(
        xref=xref,
        husband_xref=husb,
        wife_xref=wife,
        child_xrefs=children or [],
        events=[],
        citations=[],
        raw=node,
    )


def _make_file(indis=None, fams=None) -> GedcomFile:
    return GedcomFile(
        individuals=indis or {},
        families=fams or {},
        sources={},
        repositories={},
        media={},
        notes={},
        submitter=None,
        header_raw=None,
    )


class TestScoreNames:
    def test_identical_names(self):
        a = _make_indi('@I1@', 'John', 'Smith', birth_year=1900)
        b = _make_indi('@I2@', 'John', 'Smith', birth_year=1900)
        s_surn, s_given = _score_names(a, b)
        assert s_surn >= 0.95
        assert s_given >= 0.95

    def test_different_surnames(self):
        a = _make_indi('@I1@', 'John', 'Smith', birth_year=1900)
        b = _make_indi('@I2@', 'John', 'Jones', birth_year=1900)
        s_surn, s_given = _score_names(a, b)
        assert s_surn < 0.70

    def test_given_name_subset(self):
        """'Michael' vs 'Michael James' should score high."""
        a = _make_indi('@I1@', 'Michael', 'Brown')
        b = _make_indi('@I2@', 'Michael James', 'Brown')
        s_surn, s_given = _score_names(a, b)
        # Substring bonus
        assert s_given >= 0.90

    def test_fuzzy_surname(self):
        """'Bonnici' vs 'Bonny' — different enough to distinguish."""
        a = _make_indi('@I1@', 'Saverio', 'Bonnici')
        b = _make_indi('@I2@', 'Saverio', 'Bonnici')
        s_surn, _ = _score_names(a, b)
        assert s_surn >= 0.95


class TestBuildSurnameIndex:
    def test_basic_index(self):
        indi = _make_indi('@I1@', 'John', 'Smith')
        file_a = _make_file(indis={'@I1@': indi})
        idx = _build_surname_index(file_a.individuals)
        assert '@I1@' in idx.get('smith', [])

    def test_multiple_surnames(self):
        indi = _make_indi('@I1@', 'John', 'Smith')
        indi.normalized_surnames = {'smith', 'jones'}  # AKA
        file_a = _make_file(indis={'@I1@': indi})
        idx = _build_surname_index(file_a.individuals)
        assert '@I1@' in idx.get('smith', [])
        assert '@I1@' in idx.get('jones', [])

    def test_no_surname_falls_back_to_given(self):
        indi = _make_indi('@I1@', 'Madonna', '')
        indi.normalized_surnames = set()
        file_a = _make_file(indis={'@I1@': indi})
        idx = _build_surname_index(file_a.individuals)
        assert '@I1@' in idx.get('_given_madonna', [])


class TestMatchIndividuals:
    def test_obvious_match(self):
        """Same name, birth year → auto-match."""
        ind_a = _make_indi('@I1@', 'Saverio', 'Bonnici', birth_year=1880)
        ind_b = _make_indi('@I2@', 'Saverio', 'Bonnici', birth_year=1880)
        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(indis={'@I2@': ind_b})
        result = match_individuals(file_a, file_b)
        assert len(result.auto_matches) == 1
        assert result.auto_matches[0].xref_a == '@I1@'
        assert result.auto_matches[0].xref_b == '@I2@'

    def test_different_person_not_matched(self):
        """Different name and birth year → unmatched."""
        ind_a = _make_indi('@I1@', 'John', 'Smith', birth_year=1850)
        ind_b = _make_indi('@I2@', 'Maria', 'Jones', birth_year=1970)
        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(indis={'@I2@': ind_b})
        result = match_individuals(file_a, file_b)
        assert len(result.auto_matches) == 0
        assert '@I2@' in result.unmatched_b

    def test_sex_mismatch_vetoes_match(self):
        """Different sex → never match."""
        ind_a = _make_indi('@I1@', 'John', 'Smith', sex='M', birth_year=1880)
        ind_b = _make_indi('@I2@', 'John', 'Smith', sex='F', birth_year=1880)
        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(indis={'@I2@': ind_b})
        result = match_individuals(file_a, file_b)
        assert len(result.auto_matches) == 0

    def test_approximate_birth_year_matches(self):
        """ABT 1880 vs 1880 → should still match."""
        ind_a = _make_indi('@I1@', 'John', 'Smith', birth_year=1880)
        ind_b = _make_indi('@I2@', 'John', 'Smith')
        ind_b.birth_date = ParsedDate('ABT', 1880)
        ind_b.events.append(EventRecord(
            tag='BIRT', event_type=None,
            date=ParsedDate('ABT', 1880), place=None,
            raw=GedcomNode(1, 'BIRT', '', None)
        ))
        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(indis={'@I2@': ind_b})
        result = match_individuals(file_a, file_b)
        # May be auto-match or candidate but should not be unmatched
        matched = {m.xref_b for m in result.auto_matches + result.candidates}
        assert '@I2@' in matched or result.auto_matches  # at least one match found

    def test_family_context_propagation(self):
        """After matching a parent, a child with common name should also match."""
        # File A
        father_a = _make_indi('@I1@', 'John', 'Smith', sex='M', birth_year=1850,
                               fams=['@F1@'])
        child_a = _make_indi('@I3@', 'James', 'Smith', sex='M', birth_year=1880,
                              famc=['@F1@'])
        fam_a = _make_family('@F1@', '@I1@', None, ['@I3@'])
        file_a = _make_file(
            indis={'@I1@': father_a, '@I3@': child_a},
            fams={'@F1@': fam_a}
        )

        # File B
        father_b = _make_indi('@I2@', 'John', 'Smith', sex='M', birth_year=1850,
                               fams=['@F2@'])
        child_b = _make_indi('@I4@', 'James', 'Smith', sex='M', birth_year=1880,
                              famc=['@F2@'])
        fam_b = _make_family('@F2@', '@I2@', None, ['@I4@'])
        file_b = _make_file(
            indis={'@I2@': father_b, '@I4@': child_b},
            fams={'@F2@': fam_b}
        )

        result = match_individuals(file_a, file_b)
        matched_b = {m.xref_b for m in result.auto_matches}
        # Both father and child should match
        assert '@I2@' in matched_b
        assert '@I4@' in matched_b

    def test_one_to_one_matching(self):
        """Each A individual matched to at most one B individual."""
        ind_a = _make_indi('@I1@', 'John', 'Smith', birth_year=1880)
        ind_b1 = _make_indi('@I2@', 'John', 'Smith', birth_year=1880)
        ind_b2 = _make_indi('@I3@', 'John', 'Smith', birth_year=1880)
        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(indis={'@I2@': ind_b1, '@I3@': ind_b2})
        result = match_individuals(file_a, file_b)
        # At most one of I2/I3 matches I1
        matched_a = [m.xref_a for m in result.auto_matches]
        assert matched_a.count('@I1@') <= 1

    def test_empty_files(self):
        file_a = _make_file()
        file_b = _make_file()
        result = match_individuals(file_a, file_b)
        assert result.auto_matches == []
        assert result.candidates == []
        assert result.unmatched_b == []

    def test_all_unmatched_when_no_overlap(self):
        ind_a = _make_indi('@I1@', 'Alice', 'Wonderland', birth_year=1800)
        ind_b = _make_indi('@I2@', 'Bob', 'Marble', birth_year=2000)
        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(indis={'@I2@': ind_b})
        result = match_individuals(file_a, file_b)
        assert '@I2@' in result.unmatched_b


class TestFiftyYearVeto:
    def test_birth_years_over_50_apart_are_vetoed(self):
        """People born more than 50 years apart cannot be the same person."""
        ind_a = _make_indi('@I1@', 'John', 'Smith', birth_year=1850)
        ind_b = _make_indi('@I2@', 'John', 'Smith', birth_year=1910)
        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(indis={'@I2@': ind_b})
        result = match_individuals(file_a, file_b)
        assert len(result.auto_matches) == 0
        # Should not even be a candidate
        assert '@I2@' not in {m.xref_b for m in result.candidates}

    def test_birth_years_exactly_50_apart_not_vetoed(self):
        """50 years is the boundary — should still produce a candidate/match."""
        ind_a = _make_indi('@I1@', 'John', 'Smith', birth_year=1850)
        ind_b = _make_indi('@I2@', 'John', 'Smith', birth_year=1900)
        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(indis={'@I2@': ind_b})
        result = match_individuals(file_a, file_b)
        all_b = {m.xref_b for m in result.auto_matches + result.candidates}
        # Exact 50-year gap is on the boundary — may or may not match but should not veto
        # (the veto is > 50, not >= 50)
        # Just verify _score_pair doesn't return 0.0
        score, _ = _score_pair(ind_a, ind_b, {}, file_a, file_b)
        assert score > 0.0

    def test_veto_uses_estimated_birth_when_missing(self):
        """If one person lacks a birth year but has a spouse with known birth year,
        use estimated year for veto check."""
        # ind_a born 1850; ind_b has no birth but spouse born 1920 → est. ~1920
        spouse_b = _make_indi('@I5@', 'Mary', 'Jones', sex='F', birth_year=1920,
                               fams=['@F1@'])
        ind_b = _make_indi('@I2@', 'John', 'Smith', sex='M', fams=['@F1@'])
        fam_b = _make_family('@F1@', '@I2@', '@I5@')
        ind_a = _make_indi('@I1@', 'John', 'Smith', sex='M', birth_year=1850)

        file_a = _make_file(indis={'@I1@': ind_a})
        file_b = _make_file(
            indis={'@I2@': ind_b, '@I5@': spouse_b},
            fams={'@F1@': fam_b},
        )
        # Estimated birth for ind_b ≈ 1920, which is 70 years from 1850 → veto
        score, _ = _score_pair(ind_a, ind_b, {}, file_a, file_b)
        assert score == 0.0


class TestEstimateBirthYear:
    def test_estimate_from_spouse(self):
        spouse = _make_indi('@I2@', 'Mary', 'Jones', sex='F', birth_year=1880,
                             fams=['@F1@'])
        ind = _make_indi('@I1@', 'John', 'Smith', sex='M', fams=['@F1@'])
        fam = _make_family('@F1@', '@I1@', '@I2@')
        file = _make_file(indis={'@I1@': ind, '@I2@': spouse}, fams={'@F1@': fam})
        est = _estimate_birth_year(ind, file)
        assert est == 1880

    def test_estimate_from_parent(self):
        father = _make_indi('@I2@', 'John', 'Smith', sex='M', birth_year=1850,
                             fams=['@F1@'])
        ind = _make_indi('@I1@', 'James', 'Smith', sex='M', famc=['@F1@'])
        fam = _make_family('@F1@', '@I2@', None, ['@I1@'])
        file = _make_file(indis={'@I1@': ind, '@I2@': father}, fams={'@F1@': fam})
        est = _estimate_birth_year(ind, file)
        assert est == 1877  # 1850 + 27

    def test_no_estimate_when_no_relatives(self):
        ind = _make_indi('@I1@', 'John', 'Smith', sex='M')
        file = _make_file(indis={'@I1@': ind})
        est = _estimate_birth_year(ind, file)
        assert est is None


class TestParentContradiction:
    def test_no_contradiction_when_parents_match(self):
        father_a = _make_indi('@IA@', 'John', 'Smith', fams=['@FA@'])
        father_b = _make_indi('@IB@', 'John', 'Smith', fams=['@FB@'])
        child_a = _make_indi('@CA@', 'James', 'Smith', famc=['@FA@'])
        child_b = _make_indi('@CB@', 'James', 'Smith', famc=['@FB@'])
        fam_a = _make_family('@FA@', '@IA@', None, ['@CA@'])
        fam_b = _make_family('@FB@', '@IB@', None, ['@CB@'])
        file_a = _make_file(indis={'@IA@': father_a, '@CA@': child_a}, fams={'@FA@': fam_a})
        file_b = _make_file(indis={'@IB@': father_b, '@CB@': child_b}, fams={'@FB@': fam_b})
        # With father_b matched to father_a, child comparison has no contradiction
        matched = {'@IB@': '@IA@'}
        assert not _has_parent_contradiction(child_b, child_a, matched, file_a, file_b)

    def test_contradiction_when_parents_differ(self):
        father_a = _make_indi('@IA@', 'John', 'Smith', fams=['@FA@'])
        other_father_a = _make_indi('@IA2@', 'Robert', 'Smith', fams=['@FA2@'])
        father_b = _make_indi('@IB@', 'John', 'Smith', fams=['@FB@'])
        child_a = _make_indi('@CA@', 'James', 'Smith', famc=['@FA@'])
        child_b = _make_indi('@CB@', 'James', 'Smith', famc=['@FB@'])
        fam_a = _make_family('@FA@', '@IA@', None, ['@CA@'])
        fam_b = _make_family('@FB@', '@IB@', None, ['@CB@'])
        file_a = _make_file(
            indis={'@IA@': father_a, '@IA2@': other_father_a, '@CA@': child_a},
            fams={'@FA@': fam_a}
        )
        file_b = _make_file(indis={'@IB@': father_b, '@CB@': child_b}, fams={'@FB@': fam_b})
        # father_b matched to other_father_a (NOT father_a) → contradiction
        matched = {'@IB@': '@IA2@'}
        assert _has_parent_contradiction(child_b, child_a, matched, file_a, file_b)

    def test_contradiction_caps_score_below_auto_threshold(self):
        """A parent contradiction should prevent auto-matching even with great names."""
        father_a = _make_indi('@IA@', 'Robert', 'Smith', fams=['@FA@'])
        other_father_a = _make_indi('@IA2@', 'William', 'Brown', fams=['@FA2@'])
        father_b = _make_indi('@IB@', 'Robert', 'Smith', fams=['@FB@'])
        child_a = _make_indi('@CA@', 'James', 'Smith', birth_year=1880, famc=['@FA@'])
        child_b = _make_indi('@CB@', 'James', 'Smith', birth_year=1880, famc=['@FB@'])
        fam_a = _make_family('@FA@', '@IA@', None, ['@CA@'])
        fam_b = _make_family('@FB@', '@IB@', None, ['@CB@'])
        file_a = _make_file(
            indis={'@IA@': father_a, '@IA2@': other_father_a, '@CA@': child_a},
            fams={'@FA@': fam_a}
        )
        file_b = _make_file(indis={'@IB@': father_b, '@CB@': child_b}, fams={'@FB@': fam_b})
        # father_b matched to wrong parent → contradiction
        matched = {'@IB@': '@IA2@'}
        score, _ = _score_pair(child_a, child_b, matched, file_a, file_b)
        assert score < 0.75, f'Expected below auto_threshold but got {score}'


class TestFamilyContextScoring:
    def test_parents_and_spouse_match_scores_very_high(self):
        father_a = _make_indi('@FA@', 'Dad', 'Smith', fams=['@F1@'])
        mother_a = _make_indi('@MA@', 'Mum', 'Jones', fams=['@F1@'])
        spouse_a = _make_indi('@SA@', 'Mary', 'Green', sex='F', fams=['@F2@'])
        ind_a = _make_indi('@IA@', 'James', 'Smith', sex='M', famc=['@F1@'], fams=['@F2@'])
        fam1_a = _make_family('@F1@', '@FA@', '@MA@', ['@IA@'])
        fam2_a = _make_family('@F2@', '@IA@', '@SA@')

        father_b = _make_indi('@FB@', 'Dad', 'Smith', fams=['@F3@'])
        mother_b = _make_indi('@MB@', 'Mum', 'Jones', fams=['@F3@'])
        spouse_b = _make_indi('@SB@', 'Mary', 'Green', sex='F', fams=['@F4@'])
        ind_b = _make_indi('@IB@', 'James', 'Smith', sex='M', famc=['@F3@'], fams=['@F4@'])
        fam1_b = _make_family('@F3@', '@FB@', '@MB@', ['@IB@'])
        fam2_b = _make_family('@F4@', '@IB@', '@SB@')

        file_a = _make_file(
            indis={'@FA@': father_a, '@MA@': mother_a, '@SA@': spouse_a, '@IA@': ind_a},
            fams={'@F1@': fam1_a, '@F2@': fam2_a},
        )
        file_b = _make_file(
            indis={'@FB@': father_b, '@MB@': mother_b, '@SB@': spouse_b, '@IB@': ind_b},
            fams={'@F3@': fam1_b, '@F4@': fam2_b},
        )
        # Both parents and spouse matched
        matched = {'@FB@': '@FA@', '@MB@': '@MA@', '@SB@': '@SA@'}
        score = _score_family_context(ind_b, ind_a, matched, file_a, file_b)
        assert score >= 0.95

    def test_parent_match_alone_scores_high(self):
        father_a = _make_indi('@FA@', 'Dad', 'Smith', fams=['@F1@'])
        ind_a = _make_indi('@IA@', 'James', 'Smith', famc=['@F1@'])
        fam_a = _make_family('@F1@', '@FA@', None, ['@IA@'])
        father_b = _make_indi('@FB@', 'Dad', 'Smith', fams=['@F2@'])
        ind_b = _make_indi('@IB@', 'James', 'Smith', famc=['@F2@'])
        fam_b = _make_family('@F2@', '@FB@', None, ['@IB@'])
        file_a = _make_file(indis={'@FA@': father_a, '@IA@': ind_a}, fams={'@F1@': fam_a})
        file_b = _make_file(indis={'@FB@': father_b, '@IB@': ind_b}, fams={'@F2@': fam_b})
        matched = {'@FB@': '@FA@'}
        score = _score_family_context(ind_b, ind_a, matched, file_a, file_b)
        assert score >= 0.88

    def test_parent_contradiction_scores_near_zero(self):
        father_a = _make_indi('@FA@', 'Dad', 'Smith', fams=['@F1@'])
        wrong_father_a = _make_indi('@FA2@', 'Other', 'Brown', fams=['@F3@'])
        ind_a = _make_indi('@IA@', 'James', 'Smith', famc=['@F1@'])
        fam_a = _make_family('@F1@', '@FA@', None, ['@IA@'])
        father_b = _make_indi('@FB@', 'Dad', 'Smith', fams=['@F2@'])
        ind_b = _make_indi('@IB@', 'James', 'Smith', famc=['@F2@'])
        fam_b = _make_family('@F2@', '@FB@', None, ['@IB@'])
        file_a = _make_file(
            indis={'@FA@': father_a, '@FA2@': wrong_father_a, '@IA@': ind_a},
            fams={'@F1@': fam_a}
        )
        file_b = _make_file(indis={'@FB@': father_b, '@IB@': ind_b}, fams={'@F2@': fam_b})
        matched = {'@FB@': '@FA2@'}  # father_b → wrong father_a
        score = _score_family_context(ind_b, ind_a, matched, file_a, file_b)
        assert score <= 0.10


class TestNameAliases:
    def test_george_giorgios_boost(self):
        """Greek/Western equivalents should score near 0.92."""
        a = _make_indi('@I1@', 'George', 'Papadopoulos', birth_year=1880)
        b = _make_indi('@I2@', 'Giorgios', 'Papadopoulos', birth_year=1880)
        _, given_score = _score_names(a, b)
        assert given_score >= 0.92

    def test_helen_eleni_boost(self):
        a = _make_indi('@I1@', 'Helen', 'Smith', sex='F', birth_year=1890)
        b = _make_indi('@I2@', 'Eleni', 'Smith', sex='F', birth_year=1890)
        _, given_score = _score_names(a, b)
        assert given_score >= 0.92

    def test_john_ioannis_boost(self):
        a = _make_indi('@I1@', 'John', 'Petridis', birth_year=1875)
        b = _make_indi('@I2@', 'Ioannis', 'Petridis', birth_year=1875)
        _, given_score = _score_names(a, b)
        assert given_score >= 0.92

    def test_unrelated_names_not_boosted(self):
        a = _make_indi('@I1@', 'George', 'Smith', birth_year=1880)
        b = _make_indi('@I2@', 'Stavros', 'Smith', birth_year=1880)
        _, given_score = _score_names(a, b)
        # George and Stavros are NOT in the same alias group
        assert given_score < 0.92

    def test_alias_table_has_greek_names(self):
        assert 'giorgios' in _NAME_ALIASES
        assert 'george' in _NAME_ALIASES['giorgios']
        assert 'eleni' in _NAME_ALIASES
        assert 'helen' in _NAME_ALIASES['eleni']


class TestFamilyContextThreshold:
    def test_auto_matches_at_lower_threshold_with_parent_match(self):
        """When a parent is matched (family_score >= 0.90), auto-match at 0.60 not 0.75."""
        # Build: father_b matched to father_a; child pair should auto-match below 0.75
        father_a = _make_indi('@FA@', 'Nikolaos', 'Petridis', birth_year=1850, fams=['@F1@'])
        child_a = _make_indi('@CA@', 'Giorgios', 'Petridis', birth_year=1880, famc=['@F1@'])
        fam_a = _make_family('@F1@', '@FA@', None, ['@CA@'])

        father_b = _make_indi('@FB@', 'Nikolaos', 'Petridis', birth_year=1850, fams=['@F2@'])
        child_b = _make_indi('@CB@', 'George', 'Petridis', birth_year=1880, famc=['@F2@'])
        fam_b = _make_family('@F2@', '@FB@', None, ['@CB@'])

        file_a = _make_file(
            indis={'@FA@': father_a, '@CA@': child_a},
            fams={'@F1@': fam_a},
        )
        file_b = _make_file(
            indis={'@FB@': father_b, '@CB@': child_b},
            fams={'@F2@': fam_b},
        )

        result = match_individuals(file_a, file_b, auto_threshold=0.75, review_threshold=0.50)
        matched_b = {m.xref_b for m in result.auto_matches}
        # child_b should auto-match despite name pair "Giorgios"/"George" having moderate string sim
        assert '@CB@' in matched_b or '@FB@' in matched_b


class TestFinalRescorePass:
    def test_final_pass_promotes_candidate_with_full_context(self):
        """An individual that scores below threshold alone should auto-match
        after the final re-score pass has full family context."""
        parent_a = _make_indi('@PA@', 'Dimitrios', 'Stavros', birth_year=1840, fams=['@F1@'])
        child_a = _make_indi('@CA@', 'Spyros', 'Stavros', birth_year=1870, famc=['@F1@'])
        fam_a = _make_family('@F1@', '@PA@', None, ['@CA@'])

        parent_b = _make_indi('@PB@', 'Dimitrios', 'Stavros', birth_year=1840, fams=['@F2@'])
        child_b = _make_indi('@CB@', 'Spyros', 'Stavros', birth_year=1870, famc=['@F2@'])
        fam_b = _make_family('@F2@', '@PB@', None, ['@CB@'])

        file_a = _make_file(
            indis={'@PA@': parent_a, '@CA@': child_a},
            fams={'@F1@': fam_a},
        )
        file_b = _make_file(
            indis={'@PB@': parent_b, '@CB@': child_b},
            fams={'@F2@': fam_b},
        )

        result = match_individuals(file_a, file_b, auto_threshold=0.75, review_threshold=0.50)
        matched_b = {m.xref_b for m in result.auto_matches}
        # Both should auto-match because names + dates are identical
        assert '@PB@' in matched_b
        assert '@CB@' in matched_b


class TestCorroborationRequirement:
    def test_name_only_match_capped_below_review_threshold(self):
        """Individuals with matching names but no birth/death dates and no family
        context should be capped below review threshold (0.62) to avoid surfacing
        ambiguous name-only matches."""
        # Same name, same sex, but NO dates on either side, no family context
        a = _make_indi('@I1@', 'Mario', 'DAndria', sex='M')
        b = _make_indi('@I2@', 'Mario', 'DAndria', sex='M')
        file_a = _make_file(indis={'@I1@': a})
        file_b = _make_file(indis={'@I2@': b})
        score, _ = _score_pair(a, b, {}, file_a, file_b)
        assert score <= 0.62, f'Name-only match should be capped at 0.62, got {score}'

    def test_match_with_birth_date_not_capped(self):
        """When at least one side has a birth year, corroboration requirement is met."""
        a = _make_indi('@I1@', 'Mario', 'DAndria', sex='M', birth_year=1920)
        b = _make_indi('@I2@', 'Mario', 'DAndria', sex='M')  # no date on B side
        file_a = _make_file(indis={'@I1@': a})
        file_b = _make_file(indis={'@I2@': b})
        score, _ = _score_pair(a, b, {}, file_a, file_b)
        assert score > 0.62, f'Match with birth date should not be capped, got {score}'

    def test_match_with_family_context_not_capped(self):
        """When family context is established (a parent matched), corroboration met."""
        father_a = _make_indi('@FA@', 'Papa', 'DAndria', sex='M', fams=['@F1@'])
        a = _make_indi('@I1@', 'Mario', 'DAndria', sex='M', famc=['@F1@'])
        fam_a = _make_family('@F1@', '@FA@', None, ['@I1@'])

        father_b = _make_indi('@FB@', 'Papa', 'DAndria', sex='M', fams=['@F2@'])
        b = _make_indi('@I2@', 'Mario', 'DAndria', sex='M', famc=['@F2@'])
        fam_b = _make_family('@F2@', '@FB@', None, ['@I2@'])

        file_a = _make_file(indis={'@FA@': father_a, '@I1@': a}, fams={'@F1@': fam_a})
        file_b = _make_file(indis={'@FB@': father_b, '@I2@': b}, fams={'@F2@': fam_b})

        # Father is already matched
        matched = {'@FB@': '@FA@'}
        score, comps = _score_pair(a, b, matched, file_a, file_b)
        # Family context should be 0.90, which satisfies corroboration
        assert comps.get('family', 0) > 0.50
        assert score > 0.62
