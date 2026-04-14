"""Tests for gedcom_merge.parser — TDD ensuring no data is silently lost."""

import textwrap
import tempfile
import os
import pytest

from gedcom_merge.parser import parse_gedcom, _build_records
from gedcom_merge.model import GedcomFile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_ged(content: str) -> str:
    """Write a GEDCOM string to a temp file, return path."""
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.ged',
                                    encoding='utf-8', delete=False)
    f.write(content)
    f.close()
    return f.name


MINIMAL_GED = textwrap.dedent("""\
    0 HEAD
    1 GEDC
    2 VERS 5.5.1
    1 CHAR UTF-8
    0 TRLR
""")

SIMPLE_INDI_GED = textwrap.dedent("""\
    0 HEAD
    1 CHAR UTF-8
    0 @I1@ INDI
    1 NAME John /Smith/
    2 GIVN John
    2 SURN Smith
    1 SEX M
    1 BIRT
    2 DATE 15 MAR 1892
    2 PLAC Boston, Massachusetts, USA
    1 DEAT
    2 DATE 24 FEB 1957
    2 PLAC Columbus, Ohio, USA
    1 FAMS @F1@
    0 @F1@ FAM
    1 HUSB @I1@
    0 @S1@ SOUR
    1 TITL Massachusetts Vital Records
    1 AUTH State of Massachusetts
    0 TRLR
""")

MULTI_NAME_GED = textwrap.dedent("""\
    0 HEAD
    1 CHAR UTF-8
    0 @I1@ INDI
    1 NAME Saverio /Bonnici/
    1 NAME Salverio /Bonnici/
    2 TYPE AKA
    1 NAME Sylvere /Bonnici/
    2 TYPE AKA
    1 SEX M
    1 BIRT
    2 DATE 1880
    0 TRLR
""")

CONT_CONC_GED = textwrap.dedent("""\
    0 HEAD
    1 CHAR UTF-8
    0 @S1@ SOUR
    1 TITL A Very Long Title That Spans
    2 CONC  Multiple Lines
    1 NOTE First line of note.
    2 CONT Second line of note.
    2 CONT Third line.
    0 TRLR
""")

NONSTANDARD_TAGS_GED = textwrap.dedent("""\
    0 HEAD
    1 CHAR UTF-8
    0 @I1@ INDI
    1 NAME Test /Person/
    1 _APID 12345
    1 _OID somevalue
    1 BIRT
    2 DATE 1900
    2 _CUSTOM customvalue
    0 TRLR
""")

CITATION_GED = textwrap.dedent("""\
    0 HEAD
    1 CHAR UTF-8
    0 @S1@ SOUR
    1 TITL Census 1900
    0 @I1@ INDI
    1 NAME Jane /Doe/
    1 BIRT
    2 DATE 1880
    2 SOUR @S1@
    3 PAGE Page 42, Line 7
    1 SOUR @S1@
    2 PAGE Individual citation
    0 TRLR
""")

FAMILY_GED = textwrap.dedent("""\
    0 HEAD
    1 CHAR UTF-8
    0 @I1@ INDI
    1 NAME Father /Smith/
    1 SEX M
    1 FAMS @F1@
    0 @I2@ INDI
    1 NAME Mother /Jones/
    1 SEX F
    1 FAMS @F1@
    0 @I3@ INDI
    1 NAME Child /Smith/
    1 FAMC @F1@
    0 @F1@ FAM
    1 HUSB @I1@
    1 WIFE @I2@
    1 CHIL @I3@
    1 MARR
    2 DATE 5 JUN 1910
    2 PLAC New York, USA
    0 TRLR
""")


# ---------------------------------------------------------------------------
# Tests: basic parsing
# ---------------------------------------------------------------------------

class TestParseMinimal:
    def test_parses_without_error(self):
        path = _write_ged(MINIMAL_GED)
        try:
            ged = parse_gedcom(path)
            assert isinstance(ged, GedcomFile)
        finally:
            os.unlink(path)

    def test_header_captured(self):
        path = _write_ged(MINIMAL_GED)
        try:
            ged = parse_gedcom(path)
            assert ged.header_raw is not None
            assert ged.header_raw.tag == 'HEAD'
        finally:
            os.unlink(path)


class TestParseIndividual:
    @pytest.fixture(autouse=True)
    def setup(self):
        path = _write_ged(SIMPLE_INDI_GED)
        self.ged = parse_gedcom(path)
        os.unlink(path)
        yield

    def test_individual_count(self):
        assert len(self.ged.individuals) == 1

    def test_xref_correct(self):
        assert '@I1@' in self.ged.individuals

    def test_name_parsed(self):
        indi = self.ged.individuals['@I1@']
        assert len(indi.names) == 1
        assert indi.names[0].given == 'john'
        assert indi.names[0].surname == 'smith'

    def test_sex_parsed(self):
        indi = self.ged.individuals['@I1@']
        assert indi.sex == 'M'

    def test_birth_event(self):
        indi = self.ged.individuals['@I1@']
        assert indi.birth_date is not None
        assert indi.birth_date.year == 1892
        assert indi.birth_date.month == 3
        assert indi.birth_date.day == 15

    def test_birth_place(self):
        indi = self.ged.individuals['@I1@']
        birt = next(e for e in indi.events if e.tag == 'BIRT')
        assert 'Boston' in birt.place

    def test_death_event(self):
        indi = self.ged.individuals['@I1@']
        assert indi.death_date is not None
        assert indi.death_date.year == 1957

    def test_fams_link(self):
        indi = self.ged.individuals['@I1@']
        assert '@F1@' in indi.family_spouse

    def test_raw_preserved(self):
        indi = self.ged.individuals['@I1@']
        assert indi.raw is not None
        assert indi.raw.tag == 'INDI'


class TestParseMultipleNames:
    @pytest.fixture(autouse=True)
    def setup(self):
        path = _write_ged(MULTI_NAME_GED)
        self.ged = parse_gedcom(path)
        os.unlink(path)
        yield

    def test_three_names_parsed(self):
        indi = self.ged.individuals['@I1@']
        assert len(indi.names) == 3

    def test_primary_name(self):
        indi = self.ged.individuals['@I1@']
        assert indi.names[0].surname == 'bonnici'
        assert indi.names[0].name_type is None

    def test_aka_names(self):
        indi = self.ged.individuals['@I1@']
        akas = [n for n in indi.names if n.name_type == 'AKA']
        assert len(akas) == 2

    def test_normalized_surnames(self):
        indi = self.ged.individuals['@I1@']
        assert 'bonnici' in indi.normalized_surnames


class TestContConc:
    @pytest.fixture(autouse=True)
    def setup(self):
        path = _write_ged(CONT_CONC_GED)
        self.ged = parse_gedcom(path)
        os.unlink(path)
        yield

    def test_conc_joined(self):
        src = self.ged.sources['@S1@']
        assert 'Multiple Lines' in src.title

    def test_cont_joined(self):
        src = self.ged.sources['@S1@']
        notes = src.notes
        assert any('Second line' in n for n in notes)
        assert any('Third line' in n for n in notes) or \
               any('Second line' in n and 'Third line' in n for n in notes)


class TestNonstandardTagsPreserved:
    def test_nonstandard_tags_in_raw(self):
        path = _write_ged(NONSTANDARD_TAGS_GED)
        ged = parse_gedcom(path)
        os.unlink(path)
        indi = ged.individuals['@I1@']
        # Non-standard tags must be preserved in raw node
        raw_tags = {c.tag for c in indi.raw.children}
        assert '_APID' in raw_tags
        assert '_OID' in raw_tags

    def test_nonstandard_tags_dont_cause_crash(self):
        path = _write_ged(NONSTANDARD_TAGS_GED)
        try:
            ged = parse_gedcom(path)
            assert '@I1@' in ged.individuals
        finally:
            os.unlink(path)

    def test_custom_event_tag_preserved(self):
        """Custom sub-tags within events must be in raw."""
        path = _write_ged(NONSTANDARD_TAGS_GED)
        ged = parse_gedcom(path)
        os.unlink(path)
        indi = ged.individuals['@I1@']
        birt = next(e for e in indi.events if e.tag == 'BIRT')
        raw_child_tags = {c.tag for c in birt.raw.children}
        assert '_CUSTOM' in raw_child_tags


class TestCitationParsing:
    @pytest.fixture(autouse=True)
    def setup(self):
        path = _write_ged(CITATION_GED)
        self.ged = parse_gedcom(path)
        os.unlink(path)
        yield

    def test_event_citation(self):
        indi = self.ged.individuals['@I1@']
        birt = next(e for e in indi.events if e.tag == 'BIRT')
        assert len(birt.citations) == 1
        assert birt.citations[0].source_xref == '@S1@'
        assert 'Page 42' in birt.citations[0].page

    def test_individual_citation(self):
        indi = self.ged.individuals['@I1@']
        assert len(indi.citations) == 1
        assert indi.citations[0].source_xref == '@S1@'


class TestFamilyParsing:
    @pytest.fixture(autouse=True)
    def setup(self):
        path = _write_ged(FAMILY_GED)
        self.ged = parse_gedcom(path)
        os.unlink(path)
        yield

    def test_family_count(self):
        assert len(self.ged.families) == 1

    def test_husband_wife_child(self):
        fam = self.ged.families['@F1@']
        assert fam.husband_xref == '@I1@'
        assert fam.wife_xref == '@I2@'
        assert '@I3@' in fam.child_xrefs

    def test_marriage_event(self):
        fam = self.ged.families['@F1@']
        marr = next(e for e in fam.events if e.tag == 'MARR')
        assert marr.date is not None
        assert marr.date.year == 1910

    def test_famc_link_on_child(self):
        child = self.ged.individuals['@I3@']
        assert '@F1@' in child.family_child

    def test_fams_link_on_parents(self):
        father = self.ged.individuals['@I1@']
        mother = self.ged.individuals['@I2@']
        assert '@F1@' in father.family_spouse
        assert '@F1@' in mother.family_spouse


class TestSourceParsing:
    def test_source_title_and_tokens(self):
        path = _write_ged(SIMPLE_INDI_GED)
        ged = parse_gedcom(path)
        os.unlink(path)
        src = ged.sources['@S1@']
        assert src.title == 'Massachusetts Vital Records'
        assert 'massachusetts' in src.title_tokens
        assert 'vital' in src.title_tokens

    def test_source_author(self):
        path = _write_ged(SIMPLE_INDI_GED)
        ged = parse_gedcom(path)
        os.unlink(path)
        src = ged.sources['@S1@']
        assert src.author == 'State of Massachusetts'


class TestNotesParsing:
    def test_inline_note_on_individual(self):
        ged_str = textwrap.dedent("""\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 NAME John /Smith/
            1 NOTE This is a research note.
            0 TRLR
        """)
        path = _write_ged(ged_str)
        ged = parse_gedcom(path)
        os.unlink(path)
        ind = ged.individuals['@I1@']
        assert ind.notes == ['This is a research note.']
        assert ind.note_xrefs == []

    def test_linked_note_xref_on_individual(self):
        ged_str = textwrap.dedent("""\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 NAME John /Smith/
            1 NOTE @N1@
            0 @N1@ NOTE
            1 CONT Full note text here.
            0 TRLR
        """)
        path = _write_ged(ged_str)
        ged = parse_gedcom(path)
        os.unlink(path)
        ind = ged.individuals['@I1@']
        assert '@N1@' in ind.note_xrefs
        assert ind.notes == []

    def test_multiline_note_via_cont(self):
        ged_str = textwrap.dedent("""\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 NAME John /Smith/
            1 NOTE Line one.
            2 CONT Line two.
            2 CONT Line three.
            0 TRLR
        """)
        path = _write_ged(ged_str)
        ged = parse_gedcom(path)
        os.unlink(path)
        ind = ged.individuals['@I1@']
        assert len(ind.notes) == 1
        assert 'Line one.' in ind.notes[0]
        assert 'Line two.' in ind.notes[0]
        assert 'Line three.' in ind.notes[0]

    def test_multiple_notes_on_individual(self):
        ged_str = textwrap.dedent("""\
            0 HEAD
            1 GEDC
            2 VERS 5.5.1
            0 @I1@ INDI
            1 NAME John /Smith/
            1 NOTE First note.
            1 NOTE Second note.
            0 TRLR
        """)
        path = _write_ged(ged_str)
        ged = parse_gedcom(path)
        os.unlink(path)
        ind = ged.individuals['@I1@']
        assert len(ind.notes) == 2
        assert 'First note.' in ind.notes
        assert 'Second note.' in ind.notes


class TestBuildRecords:
    def test_level_structure(self):
        lines = [
            '0 @I1@ INDI',
            '1 NAME John /Smith/',
            '2 GIVN John',
            '1 SEX M',
        ]
        roots = _build_records(lines)
        assert len(roots) == 1
        indi = roots[0]
        assert indi.tag == 'INDI'
        assert len(indi.children) == 2
        name_node = indi.children[0]
        assert name_node.tag == 'NAME'
        assert len(name_node.children) == 1
        assert name_node.children[0].tag == 'GIVN'

    def test_conc_folded(self):
        lines = [
            '0 @S1@ SOUR',
            '1 TITL Long Title',
            '2 CONC  Continued',
        ]
        roots = _build_records(lines)
        src = roots[0]
        titl = src.children[0]
        assert titl.value == 'Long Title Continued'

    def test_cont_folded_with_newline(self):
        lines = [
            '0 @N1@ NOTE',
            '1 CONT Line two',
        ]
        roots = _build_records(lines)
        note = roots[0]
        # NOTE: CONT at level 1 gets folded into level 0
        # The NOTE node's children should be empty (CONT consumed)
        assert '\nLine two' in note.value or len(note.children) == 0


# ---------------------------------------------------------------------------
# NameRecord.raw preservation — GIVN/SURN must survive a parse→write round-trip
# ---------------------------------------------------------------------------

class TestNameRawPreservation:
    GED = textwrap.dedent("""\
        0 HEAD
        1 GEDC
        2 VERS 5.5.1
        0 @I1@ INDI
        1 NAME John /Smith/
        2 GIVN John
        2 SURN Smith
        2 SOUR @S1@
        1 NAME Johnny /Smith/
        2 GIVN Johnny
        2 SURN Smith
        2 TYPE AKA
        1 SEX M
        0 TRLR
    """)

    def test_namerecord_has_raw(self, tmp_path):
        """parse_gedcom must populate NameRecord.raw with the NAME GedcomNode."""
        ged = tmp_path / 'test.ged'
        ged.write_text(self.GED, encoding='utf-8')
        gf = parse_gedcom(str(ged))
        ind = gf.individuals['@I1@']
        for nm in ind.names:
            assert nm.raw is not None, f'NameRecord.raw is None for {nm.full!r}'
            assert nm.raw.tag == 'NAME', f'Expected NAME node, got {nm.raw.tag}'

    def test_givn_surn_survive_write(self, tmp_path):
        """write_gedcom must preserve GIVN and SURN sub-tags on every NAME."""
        from gedcom_merge.writer import write_gedcom
        ged = tmp_path / 'test.ged'
        ged.write_text(self.GED, encoding='utf-8')
        gf = parse_gedcom(str(ged))
        out = tmp_path / 'out.ged'
        write_gedcom(gf, str(out))
        text = out.read_text(encoding='utf-8')
        assert '2 GIVN John' in text,   'GIVN sub-tag lost on primary name'
        assert '2 SURN Smith' in text,  'SURN sub-tag lost on primary name'
        assert '2 GIVN Johnny' in text, 'GIVN sub-tag lost on AKA name'

    def test_givn_surn_survive_dedup_names(self, tmp_path):
        """fix_duplicate_names must not cause write_gedcom to drop GIVN/SURN."""
        import sys
        sys.path.insert(0, str(tmp_path.parent.parent))
        from gedcom_linter import fix_duplicate_names
        ged = tmp_path / 'test.ged'
        ged.write_text(self.GED, encoding='utf-8')
        fix_duplicate_names(str(ged))
        text = ged.read_text(encoding='utf-8')
        assert '2 GIVN John' in text,  'GIVN dropped after fix_duplicate_names'
        assert '2 SURN Smith' in text, 'SURN dropped after fix_duplicate_names'
