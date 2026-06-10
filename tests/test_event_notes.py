import pytest
from pathlib import Path
from viz_ancestors import parse_gedcom

_HEADER = (
    '0 HEAD\n1 GEDC\n2 VERS 5.5.1\n2 FORM LINEAGE-LINKED\n1 CHAR UTF-8\n'
    '0 @U1@ SUBM\n1 NAME Test\n'
)
_TRAILER = '0 TRLR\n'


def _write_ged(tmp_path, name, body):
    ged = tmp_path / name
    ged.write_text(_HEADER + body + _TRAILER, encoding='utf-8')
    return ged


class TestIndiEventNotes:
    def test_event_notes_field_exists(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE Inline note\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert 'event_notes' in occu

    def test_single_inline_note_in_list(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE Co-founder firm\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert len(occu['event_notes']) == 1
        assert occu['event_notes'][0] == {'text': 'Co-founder firm', 'shared': False, 'note_xref': None}

    def test_evt_note_field_is_first_inline_text(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE Co-founder firm\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert occu['note'] == 'Co-founder firm'

    def test_two_inline_notes_both_in_list(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE First note\n2 NOTE Second note\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert len(occu['event_notes']) == 2
        assert occu['event_notes'][1]['text'] == 'Second note'

    def test_evt_note_field_is_first_not_last_when_two_inline(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE First note\n2 NOTE Second note\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert occu['note'] == 'First note'

    def test_shared_note_in_event_notes_list(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @N1@ NOTE Shared note text.\n'
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE @N1@\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert len(occu['event_notes']) == 1
        n = occu['event_notes'][0]
        assert n['shared'] is True
        assert n['note_xref'] == '@N1@'
        assert n['text'] == 'Shared note text.'

    def test_inline_then_shared_preserves_both(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @N1@ NOTE Shared note text.\n'
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE Inline text\n2 NOTE @N1@\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert len(occu['event_notes']) == 2
        assert occu['event_notes'][0] == {'text': 'Inline text', 'shared': False, 'note_xref': None}
        assert occu['event_notes'][1]['shared'] is True
        assert occu['note'] == 'Inline text'

    def test_shared_only_does_not_set_evt_note(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @N1@ NOTE Shared note text.\n'
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE @N1@\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert occu['note'] is None

    def test_event_without_notes_has_empty_list(self, tmp_path):
        ged = _write_ged(tmp_path, 'e.ged',
            '0 @I1@ INDI\n1 NAME Test /Person/\n1 OCCU Merchant\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert occu['event_notes'] == []


class TestFamEventNotes:
    def test_marr_event_has_event_notes_field(self, tmp_path):
        ged = _write_ged(tmp_path, 'f.ged',
            '0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n'
            '1 MARR\n2 NOTE Inline marriage note\n'
            '0 @I1@ INDI\n1 NAME Husb /Test/\n1 FAMS @F1@\n'
            '0 @I2@ INDI\n1 NAME Wife /Test/\n1 FAMS @F1@\n'
        )
        _, fams, _, _ = parse_gedcom(str(ged))
        marr = fams['@F1@']['marrs'][0]
        assert 'event_notes' in marr

    def test_marr_shared_note_in_event_notes(self, tmp_path):
        ged = _write_ged(tmp_path, 'f.ged',
            '0 @N1@ NOTE Shared marriage note.\n'
            '0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n'
            '1 MARR\n2 NOTE @N1@\n'
            '0 @I1@ INDI\n1 NAME Husb /Test/\n1 FAMS @F1@\n'
            '0 @I2@ INDI\n1 NAME Wife /Test/\n1 FAMS @F1@\n'
        )
        _, fams, _, _ = parse_gedcom(str(ged))
        marr = fams['@F1@']['marrs'][0]
        assert len(marr['event_notes']) == 1
        assert marr['event_notes'][0]['shared'] is True
        assert marr['event_notes'][0]['note_xref'] == '@N1@'
        assert marr['note'] is None

    def test_marr_inline_then_shared_preserves_both(self, tmp_path):
        ged = _write_ged(tmp_path, 'f.ged',
            '0 @N1@ NOTE Shared marriage note.\n'
            '0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n'
            '1 MARR\n2 NOTE Inline\n2 NOTE @N1@\n'
            '0 @I1@ INDI\n1 NAME Husb /Test/\n1 FAMS @F1@\n'
            '0 @I2@ INDI\n1 NAME Wife /Test/\n1 FAMS @F1@\n'
        )
        _, fams, _, _ = parse_gedcom(str(ged))
        marr = fams['@F1@']['marrs'][0]
        assert len(marr['event_notes']) == 2
        assert marr['note'] == 'Inline'

    def test_marr_inline_cont_appended(self, tmp_path):
        ged = _write_ged(tmp_path, 'f.ged',
            '0 @F1@ FAM\n1 HUSB @I1@\n1 WIFE @I2@\n'
            '1 MARR\n2 NOTE First line\n3 CONT Second line\n'
            '0 @I1@ INDI\n1 NAME Husb /Test/\n1 FAMS @F1@\n'
            '0 @I2@ INDI\n1 NAME Wife /Test/\n1 FAMS @F1@\n'
        )
        _, fams, _, _ = parse_gedcom(str(ged))
        marr = fams['@F1@']['marrs'][0]
        assert marr['event_notes'][0]['text'] == 'First line\nSecond line'
        assert marr['note'] == 'First line\nSecond line'


class TestEventNoteContinuation:
    def test_cont_appended_to_event_notes_text(self, tmp_path):
        ged = _write_ged(tmp_path, 'c.ged',
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE First line\n3 CONT Second line\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert occu['event_notes'][0]['text'] == 'First line\nSecond line'

    def test_cont_also_updates_evt_note_field(self, tmp_path):
        ged = _write_ged(tmp_path, 'c.ged',
            '0 @I1@ INDI\n1 NAME Test /Person/\n'
            '1 OCCU Merchant\n2 NOTE First line\n3 CONT Second line\n'
        )
        indis, _, _, _ = parse_gedcom(str(ged))
        occu = next(e for e in indis['@I1@']['events'] if e['tag'] == 'OCCU')
        assert occu['note'] == 'First line\nSecond line'
