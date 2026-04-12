"""
Tests for the event editing / creation features added to serve_viz.py and
viz_ancestors.py.

Covers:
  - _find_indi_block      – shared INDI block locator
  - _find_event_block     – locates Nth occurrence of a tag in an INDI block
  - _edit_event_fields    – updates / adds / removes sub-fields in an event block
  - _insert_new_event     – inserts a new event block into an INDI record
  - build_people_json     – event_idx per-tag occurrence counting; MARR → None
  - _HTML_TEMPLATE        – UI elements present; no insertAdjacentHTML accumulation
"""

import json
import os
import re
from pathlib import Path

import pytest

# serve_viz.py sys.exit()s at import if GED_FILE is not set; point at the
# existing fixture so the module loads cleanly.
_FIXTURE_GED = str(Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged')
os.environ.setdefault('GED_FILE', _FIXTURE_GED)

from serve_viz import (          # noqa: E402  (after env var is set)
    _apply_deletion,
    _edit_event_fields,
    _edit_name,
    _find_event_block,
    _find_fam_block,
    _find_fam_event_block,
    _find_indi_block,
    _insert_new_event,
)
from viz_ancestors import (      # noqa: E402
    _HTML_TEMPLATE,
    build_people_json,
    build_tree_json,
    parse_gedcom,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'ancestors_sample.ged'


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def parsed():
    return parse_gedcom(str(FIXTURE))


@pytest.fixture(scope='module')
def indis(parsed):
    return parsed[0]


@pytest.fixture(scope='module')
def fams(parsed):
    return parsed[1]


@pytest.fixture(scope='module')
def lines():
    """Raw GEDCOM lines as a list (no trailing newline per line)."""
    return FIXTURE.read_text(encoding='utf-8').splitlines()


# Minimal multi-event GEDCOM used by serve_viz unit tests
MULTI_EVENT_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Test /Person/
1 SEX M
1 BIRT
2 DATE 1 JAN 1900
2 PLAC London, England
1 OCCU Merchant
2 DATE 1920
2 TYPE Wool Merchant
1 RESI
2 DATE 1925
2 PLAC Paris, France
1 RESI
2 DATE 1930
2 PLAC Marseille, France
1 NATI French
1 NATI Greek
2 DATE 1895
1 DEAT
2 DATE 15 MAR 1950
0 TRLR
""".splitlines()


# ---------------------------------------------------------------------------
# TestFindIndiBlock
# ---------------------------------------------------------------------------

class TestFindIndiBlock:

    def test_finds_known_xref(self):
        start, end, err = _find_indi_block(MULTI_EVENT_GED, '@I1@')
        assert err is None
        assert start is not None
        assert end is not None
        assert MULTI_EVENT_GED[start] == '0 @I1@ INDI'

    def test_end_is_exclusive_trlr(self):
        """end should point past the last line of the INDI block."""
        start, end, err = _find_indi_block(MULTI_EVENT_GED, '@I1@')
        assert err is None
        # The line at `end` must be level-0 (TRLR or next record)
        assert MULTI_EVENT_GED[end].startswith('0 ')

    def test_returns_error_for_unknown_xref(self):
        _, _, err = _find_indi_block(MULTI_EVENT_GED, '@NOBODY@')
        assert err is not None
        assert '@NOBODY@' in err

    def test_all_lines_inside_block_are_level_1_or_2(self):
        start, end, err = _find_indi_block(MULTI_EVENT_GED, '@I1@')
        assert err is None
        for line in MULTI_EVENT_GED[start + 1: end]:
            lvl = int(line.split(' ', 1)[0])
            assert lvl >= 1


# ---------------------------------------------------------------------------
# TestFindEventBlock
# ---------------------------------------------------------------------------

class TestFindEventBlock:

    def test_finds_first_occurrence(self):
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'RESI', 0)
        assert err is None
        assert MULTI_EVENT_GED[start] == '1 RESI'
        # Block content should include Paris
        block = MULTI_EVENT_GED[start:end]
        assert any('Paris' in l for l in block)

    def test_finds_second_occurrence(self):
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'RESI', 1)
        assert err is None
        block = MULTI_EVENT_GED[start:end]
        assert any('Marseille' in l for l in block)

    def test_finds_birt(self):
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'BIRT', 0)
        assert err is None
        assert MULTI_EVENT_GED[start] == '1 BIRT'
        assert any('1 JAN 1900' in l for l in MULTI_EVENT_GED[start:end])

    def test_finds_inline_val_tag(self):
        """NATI has an inline value; first occurrence still findable."""
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'NATI', 0)
        assert err is None
        assert MULTI_EVENT_GED[start] == '1 NATI French'

    def test_finds_second_nati(self):
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'NATI', 1)
        assert err is None
        assert MULTI_EVENT_GED[start] == '1 NATI Greek'

    def test_returns_error_for_missing_tag(self):
        _, _, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'IMMI', 0)
        assert err is not None

    def test_returns_error_for_out_of_range_occurrence(self):
        _, _, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'BIRT', 1)
        assert err is not None

    def test_block_end_stops_at_next_level1(self):
        """end must not include lines from the next event."""
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'BIRT', 0)
        assert err is None
        # The line at `end` is the next level-1 tag (OCCU)
        assert MULTI_EVENT_GED[end].startswith('1 ')


# ---------------------------------------------------------------------------
# TestEditEventFields
# ---------------------------------------------------------------------------

class TestEditEventFields:

    def _block(self, tag_occurrence=0):
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'RESI', tag_occurrence)
        assert err is None
        return MULTI_EVENT_GED, start, end

    def test_update_existing_date(self):
        lines, start, end = self._block(0)
        new_lines = _edit_event_fields(lines, start, end, {'DATE': '1926'})
        block = new_lines[start:start + (end - start)]
        assert any('1926' in l for l in block)
        assert not any('1925' in l for l in block)

    def test_update_existing_place(self):
        lines, start, end = self._block(0)
        new_lines = _edit_event_fields(lines, start, end, {'PLAC': 'Lyon, France'})
        block = new_lines[start:start + (end - start)]
        assert any('Lyon' in l for l in block)
        assert not any('Paris' in l for l in block)

    def test_add_new_subfield(self):
        """Adding NOTE to an event that has none."""
        lines, start, end = self._block(0)
        new_lines = _edit_event_fields(lines, start, end, {'NOTE': 'First residence'})
        block = '\n'.join(new_lines[start:start + (end - start) + 2])
        assert '2 NOTE First residence' in block

    def test_remove_subfield_with_empty_string(self):
        """Empty string value removes the sub-field line."""
        lines, start, end = self._block(0)
        new_lines = _edit_event_fields(lines, start, end, {'PLAC': ''})
        block = new_lines[start:start + (end - start)]
        assert not any(l.strip().startswith('2 PLAC') for l in block)

    def test_remove_subfield_with_none(self):
        lines, start, end = self._block(0)
        new_lines = _edit_event_fields(lines, start, end, {'DATE': None})
        block = new_lines[start:start + (end - start)]
        assert not any(l.strip().startswith('2 DATE') for l in block)

    def test_update_inline_val(self):
        """inline_val update rewrites the level-1 header line."""
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'NATI', 0)
        assert err is None
        new_lines = _edit_event_fields(MULTI_EVENT_GED, start, end, {'inline_val': 'Ottoman'})
        assert new_lines[start] == '1 NATI Ottoman'

    def test_clear_inline_val(self):
        """Empty inline_val leaves just the tag with no value."""
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'NATI', 0)
        assert err is None
        new_lines = _edit_event_fields(MULTI_EVENT_GED, start, end, {'inline_val': ''})
        assert new_lines[start] == '1 NATI'

    def test_preserves_unrecognized_subfields(self):
        """TYPE sub-field on OCCU must not be dropped when updating DATE."""
        start, end, err = _find_event_block(MULTI_EVENT_GED, '@I1@', 'OCCU', 0)
        assert err is None
        new_lines = _edit_event_fields(MULTI_EVENT_GED, start, end, {'DATE': '1921'})
        block = new_lines[start:end]
        assert any('Wool Merchant' in l for l in block)

    def test_total_line_count_when_updating(self):
        """Updating a value must not change the number of lines in the block."""
        lines, start, end = self._block(0)
        orig_count = end - start
        new_lines = _edit_event_fields(lines, start, end, {'DATE': '1926', 'PLAC': 'Lyon, France'})
        new_end = start + orig_count
        assert len(new_lines[start:new_end]) == orig_count

    def test_lines_outside_block_unchanged(self):
        lines, start, end = self._block(0)
        new_lines = _edit_event_fields(lines, start, end, {'DATE': '1926'})
        assert new_lines[:start] == lines[:start]
        assert new_lines[end:] == lines[end:]

    def test_update_note_drops_stale_cont_lines(self):
        """Replacing a 2 NOTE that has 2 CONT lines must not leave stale CONT lines."""
        # Build a GEDCOM with an event whose NOTE has continuation lines
        ged = """\
0 HEAD
0 @I1@ INDI
1 NAME Test /Person/
1 BIRT
2 DATE 1900
2 NOTE Original first line
2 CONT Original second line
2 CONT Original third line
0 TRLR""".splitlines()
        start, end, err = _find_event_block(ged, '@I1@', 'BIRT', 0)
        assert err is None
        new_lines = _edit_event_fields(ged, start, end, {'NOTE': 'Replacement note'})
        block = new_lines[start:end]
        assert any('Replacement note' in l for l in block), 'new NOTE must be present'
        assert not any('2 CONT' in l for l in block), \
            'stale CONT lines from old NOTE must be removed'
        assert not any('Original' in l for l in block), \
            'no content from old NOTE should remain'

    def test_delete_note_also_drops_cont_lines(self):
        """Setting NOTE to empty must also remove any following CONT lines."""
        ged = """\
0 HEAD
0 @I1@ INDI
1 NAME Test /Person/
1 BIRT
2 DATE 1900
2 NOTE First line
2 CONT Second line
0 TRLR""".splitlines()
        start, end, err = _find_event_block(ged, '@I1@', 'BIRT', 0)
        assert err is None
        new_lines = _edit_event_fields(ged, start, end, {'NOTE': ''})
        block = new_lines[start:end]
        assert not any('2 NOTE' in l for l in block)
        assert not any('2 CONT' in l for l in block)


# ---------------------------------------------------------------------------
# TestInsertNewEvent
# ---------------------------------------------------------------------------

class TestInsertNewEvent:

    def test_insert_resi(self):
        new_lines, err = _insert_new_event(
            MULTI_EVENT_GED, '@I1@', 'RESI',
            {'DATE': '1940', 'PLAC': 'Athens, Greece'}
        )
        assert err is None
        joined = '\n'.join(new_lines)
        assert '1 RESI' in joined
        assert '2 DATE 1940' in joined
        assert '2 PLAC Athens, Greece' in joined

    def test_insert_inline_val_tag(self):
        """NATI with inline value must go on the level-1 line."""
        new_lines, err = _insert_new_event(
            MULTI_EVENT_GED, '@I1@', 'NATI', {'inline_val': 'British'}
        )
        assert err is None
        assert any(l == '1 NATI British' for l in new_lines)

    def test_insert_occu_with_inline_val_and_type(self):
        new_lines, err = _insert_new_event(
            MULTI_EVENT_GED, '@I1@', 'OCCU',
            {'inline_val': 'Consul', 'TYPE': 'French Consul', 'DATE': '1910'}
        )
        assert err is None
        joined = '\n'.join(new_lines)
        assert '1 OCCU Consul' in joined
        assert '2 TYPE French Consul' in joined
        assert '2 DATE 1910' in joined

    def test_event_inserted_inside_indi_block(self):
        """New event must appear before TRLR (inside the INDI block)."""
        new_lines, err = _insert_new_event(
            MULTI_EVENT_GED, '@I1@', 'RESI', {'DATE': '1945'}
        )
        assert err is None
        trlr_idx = next(i for i, l in enumerate(new_lines) if l == '0 TRLR')
        new_resi_idx = next(
            i for i, l in enumerate(new_lines)
            if l == '1 RESI' and i + 1 < len(new_lines) and '1945' in new_lines[i + 1]
        )
        assert new_resi_idx < trlr_idx

    def test_insert_empty_fields_skipped(self):
        """Sub-fields with empty values must not be written."""
        new_lines, err = _insert_new_event(
            MULTI_EVENT_GED, '@I1@', 'BURI',
            {'DATE': '', 'PLAC': '', 'NOTE': ''}
        )
        assert err is None
        buri_idx = next(i for i, l in enumerate(new_lines) if l == '1 BURI')
        # The line after '1 BURI' must be level-0 (TRLR) since no sub-fields
        assert new_lines[buri_idx + 1].startswith('0 ')

    def test_returns_error_for_unknown_xref(self):
        _, err = _insert_new_event(MULTI_EVENT_GED, '@NOBODY@', 'RESI', {})
        assert err is not None

    def test_original_line_count_increases_by_block_size(self):
        fields = {'DATE': '1945', 'PLAC': 'Rome, Italy'}
        new_lines, err = _insert_new_event(MULTI_EVENT_GED, '@I1@', 'RESI', fields)
        assert err is None
        # 1 header line + DATE + PLAC = 3 new lines
        assert len(new_lines) == len(MULTI_EVENT_GED) + 3

    def test_round_trips_through_parse_gedcom(self, tmp_path):
        """Inserted event must be parseable by parse_gedcom."""
        new_lines, err = _insert_new_event(
            MULTI_EVENT_GED, '@I1@', 'RESI',
            {'DATE': '1945', 'PLAC': 'Rome, Italy'}
        )
        assert err is None
        ged = tmp_path / 'test.ged'
        ged.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
        indis, _, _ = parse_gedcom(str(ged))
        resi_events = [e for e in indis['@I1@']['events'] if e['tag'] == 'RESI']
        assert any(e['place'] and 'Rome' in e['place'] for e in resi_events)


# ---------------------------------------------------------------------------
# TestApplyDeletionRefactor
# ---------------------------------------------------------------------------

class TestApplyDeletionRefactor:
    """Verify _apply_deletion still works after the _find_indi_block refactor."""

    def test_deletes_known_event(self):
        d = {'xref': '@I1@', 'tag': 'RESI', 'date': '1925',
             'place': 'Paris, France', 'type': None, 'inline_val': None}
        new_lines, err = _apply_deletion(MULTI_EVENT_GED, d)
        assert err is None
        assert not any('Paris' in l for l in new_lines)

    def test_returns_error_for_missing_event(self):
        d = {'xref': '@I1@', 'tag': 'IMMI', 'date': None,
             'place': None, 'type': None, 'inline_val': None}
        _, err = _apply_deletion(MULTI_EVENT_GED, d)
        assert err is not None


# ---------------------------------------------------------------------------
# TestEventIdxInBuildPeopleJson
# ---------------------------------------------------------------------------

class TestEventIdxInBuildPeopleJson:

    @pytest.fixture(scope='class')
    def people(self, indis, fams, parsed):
        _, _, sources = parsed
        return build_people_json({'@I2@'}, indis, fams=fams, sources=sources)

    def test_events_have_event_idx(self, people):
        events = people['@I2@']['events']
        for e in events:
            assert 'event_idx' in e

    def test_birt_gets_event_idx_zero(self, people):
        birt = next(e for e in people['@I2@']['events'] if e['tag'] == 'BIRT')
        assert birt['event_idx'] == 0

    def test_marr_events_have_event_idx_none(self, indis, fams, parsed):
        """MARR events appended from FAM records must have event_idx=None."""
        _, _, sources = parsed
        people = build_people_json({'@I1@'}, indis, fams=fams, sources=sources)
        marr_events = [e for e in people['@I1@']['events'] if e['tag'] == 'MARR']
        assert len(marr_events) > 0, 'Rose should have a MARR event from @F5@'
        for e in marr_events:
            assert e['event_idx'] is None

    def test_multiple_events_same_tag_get_sequential_idx(self, tmp_path):
        """Two RESI events on the same individual get event_idx 0 and 1."""
        ged = tmp_path / 'multi_resi.ged'
        ged.write_text('\n'.join(MULTI_EVENT_GED) + '\n', encoding='utf-8')
        indis, fams, sources = parse_gedcom(str(ged))
        people = build_people_json({'@I1@'}, indis, fams=fams, sources=sources)
        resi_events = [e for e in people['@I1@']['events'] if e['tag'] == 'RESI']
        assert len(resi_events) == 2
        indices = {e['event_idx'] for e in resi_events}
        assert indices == {0, 1}

    def test_event_idx_stable_after_exclusion(self, tmp_path):
        """
        event_idx is assigned before exclusion filtering, so a surviving event's
        index reflects its position among ALL events of that tag, not just the
        visible ones.
        """
        ged = tmp_path / 'multi_resi2.ged'
        ged.write_text('\n'.join(MULTI_EVENT_GED) + '\n', encoding='utf-8')
        indis, fams, sources = parse_gedcom(str(ged))
        # Exclude the first RESI (Paris, 1925) — the second should still be idx=1
        exclude = [{'xref': '@I1@', 'tag': 'RESI', 'date': '1925',
                    'place': 'Paris, France', 'type': None, 'inline_val': None}]
        people = build_people_json({'@I1@'}, indis, fams=fams, sources=sources,
                                   exclude=exclude)
        resi_events = [e for e in people['@I1@']['events'] if e['tag'] == 'RESI']
        assert len(resi_events) == 1
        assert resi_events[0]['event_idx'] == 1   # kept index, not re-numbered to 0


# ---------------------------------------------------------------------------
# TestTemplateUIElements
# ---------------------------------------------------------------------------

class TestTemplateUIElements:

    def test_event_modal_overlay_present(self):
        assert 'id="event-modal-overlay"' in _HTML_TEMPLATE

    def test_event_modal_tag_select_present(self):
        assert 'id="event-modal-tag"' in _HTML_TEMPLATE

    def test_event_modal_date_input_present(self):
        assert 'id="event-modal-date"' in _HTML_TEMPLATE

    def test_event_modal_place_input_present(self):
        assert 'id="event-modal-place"' in _HTML_TEMPLATE

    def test_add_event_btn_class_present(self):
        assert 'add-event-btn' in _HTML_TEMPLATE

    def test_add_nationality_btn_present(self):
        assert 'Add nationality' in _HTML_TEMPLATE

    def test_edit_event_js_function_defined(self):
        assert 'function editEvent(' in _HTML_TEMPLATE

    def test_add_event_js_function_defined(self):
        assert 'function addEvent(' in _HTML_TEMPLATE

    def test_submit_event_modal_js_function_defined(self):
        assert 'function submitEventModal(' in _HTML_TEMPLATE

    def test_edit_buttons_use_event_idx(self):
        """The edit button onclick must reference evt.event_idx, not a positional index."""
        assert 'evt.event_idx' in _HTML_TEMPLATE

    def test_no_insert_adjacent_html_for_add_event_btn(self):
        """
        Regression guard: add-event-btn must NOT be appended via
        insertAdjacentHTML (which caused multiple buttons to accumulate).
        The button must be part of innerHTML assignment instead.
        """
        assert "insertAdjacentHTML" not in _HTML_TEMPLATE or \
               "add-event-btn" not in re.search(
                   r'insertAdjacentHTML[^;]+', _HTML_TEMPLATE, re.DOTALL
               ).group(0) if re.search(r'insertAdjacentHTML', _HTML_TEMPLATE) else True

    def test_modal_title_shows_person_name(self):
        """Modal title must include the person's name (via _personName helper)."""
        assert '_personName(' in _HTML_TEMPLATE

    def test_api_edit_event_endpoint_referenced(self):
        assert '/api/edit_event' in _HTML_TEMPLATE

    def test_api_add_event_endpoint_referenced(self):
        assert '/api/add_event' in _HTML_TEMPLATE

    def test_delete_fact_uses_immediate_confirm(self):
        """deleteFact must say 'updated immediately', not 'Queue' (staged model removed)."""
        assert 'updated immediately' in _HTML_TEMPLATE
        assert 'Queue this fact' not in _HTML_TEMPLATE

    def test_no_pending_bar_in_template(self):
        """pending-bar was removed with the staging model."""
        assert 'id="pending-bar"' not in _HTML_TEMPLATE

    def test_no_commit_deletions_in_template(self):
        assert 'commitDeletions' not in _HTML_TEMPLATE

    def test_no_clear_pending_in_template(self):
        assert 'clearPending' not in _HTML_TEMPLATE

    def test_addr_field_in_event_modal(self):
        """ADDR input must be present in the event modal."""
        assert 'event-modal-addr' in _HTML_TEMPLATE

    def test_addr_suggestions_datalist_present(self):
        assert 'addr-suggestions' in _HTML_TEMPLATE

    def test_name_modal_present(self):
        assert 'name-modal-overlay' in _HTML_TEMPLATE

    def test_name_edit_button_rendered(self):
        assert 'editName(' in _HTML_TEMPLATE

    def test_api_edit_name_referenced(self):
        assert '/api/edit_name' in _HTML_TEMPLATE

    def test_marr_edit_button_rendered(self):
        assert 'marr-edit-btn' in _HTML_TEMPLATE

    def test_aka_add_button_rendered(self):
        assert 'openAliasModal' in _HTML_TEMPLATE

    def test_fam_xref_in_submit_modal(self):
        assert 'fam_xref' in _HTML_TEMPLATE

    def test_addr_by_place_constant(self):
        assert 'ADDR_BY_PLACE' in _HTML_TEMPLATE

    def test_allvisible_filter_includes_marr_tag(self):
        """
        Regression: MARR events must pass the allVisible filter even when they have no
        date/place/note/type/cause — the filter must short-circuit on e.tag === 'MARR'.
        Without this fix a bare 1 MARR (or one with only ADDR) is invisible and has no
        edit button, so the user cannot add ADDR via the UI.
        """
        assert "e.tag === 'MARR'" in _HTML_TEMPLATE

    def test_keep_in_timeline_includes_marr_tag(self):
        """
        Regression: undated MARR events must stay in the timeline (not fall into
        undatedFactoids where they render without an edit button).
        """
        # The keepInTimeline predicate must include MARR so the MARR card (with its
        # edit button) is rendered even for marriages with no date.
        assert "e.tag === 'MARR'" in _HTML_TEMPLATE

    def test_type_field_uses_uppercase_key(self):
        """
        Regression: the TYPE key sent to the server must be uppercase so that
        _edit_event_fields (which checks _MANAGED_SUBTAGS with uppercase 'TYPE') can
        update / add a 2 TYPE sub-tag.  Sending lowercase 'type' silently dropped the
        value.
        """
        assert "fields.TYPE" in _HTML_TEMPLATE

    def test_type_only_sent_when_row_visible(self):
        """TYPE must only be included in fields when the type row is visible, so that
        existing 2 TYPE sub-tags are not deleted for events (like MARR) where the
        type row is hidden."""
        assert "typeRow.style.display !== 'none'" in _HTML_TEMPLATE

    def test_open_detail_key_cleared_before_show_detail(self):
        """
        Regression: submitEventModal must null _openDetailKey before calling showDetail
        so the early-return guard inside showDetail does not fire.

        Without this fix: after saving an event while the same person's panel is open,
        _openDetailKey still equals xref when showDetail(xref) is called, triggering
        the early-return guard and leaving the panel displaying stale data.
        """
        # Locate the submitEventModal function body in the template
        fn_start = _HTML_TEMPLATE.find('async function submitEventModal(')
        assert fn_start != -1, 'submitEventModal must be present'
        # Find the closing brace of the function (search for showDetail after fn_start)
        show_detail_pos = _HTML_TEMPLATE.find('showDetail(xref)', fn_start)
        assert show_detail_pos != -1, 'showDetail(xref) call must be present in submitEventModal'
        # _openDetailKey = null must appear somewhere between fn_start and the showDetail call
        null_assign_pos = _HTML_TEMPLATE.find('_openDetailKey = null', fn_start)
        assert null_assign_pos != -1, '_openDetailKey must be nulled in submitEventModal'
        assert null_assign_pos < show_detail_pos, \
            '_openDetailKey = null must come BEFORE showDetail(xref) so the re-render is not skipped'


# ---------------------------------------------------------------------------
# _edit_name tests
# ---------------------------------------------------------------------------

SIMPLE_NAME_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5
0 @I1@ INDI
1 NAME John /Smith/
2 GIVN John
2 SURN Smith
1 BIRT
2 DATE 1900
0 TRLR""".splitlines()

FAM_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5
0 @I1@ INDI
1 NAME John /Smith/
2 GIVN John
2 SURN Smith
1 FAMS @F1@
0 @I2@ INDI
1 NAME Mary /Jones/
2 GIVN Mary
2 SURN Jones
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1925
2 PLAC London, England
0 TRLR""".splitlines()


class TestEditName:
    def test_rename_given_and_surname(self):
        new_lines, err = _edit_name(SIMPLE_NAME_GED, '@I1@', 'James', 'Brown')
        assert err is None
        name_line = next(l for l in new_lines if '1 NAME' in l)
        assert 'James /Brown/' in name_line

    def test_givn_surn_subtags_updated(self):
        new_lines, err = _edit_name(SIMPLE_NAME_GED, '@I1@', 'James', 'Brown')
        assert err is None
        givn = next(l for l in new_lines if '2 GIVN' in l)
        surn = next(l for l in new_lines if '2 SURN' in l)
        assert 'James' in givn
        assert 'Brown' in surn

    def test_no_extra_name_lines(self):
        new_lines, err = _edit_name(SIMPLE_NAME_GED, '@I1@', 'James', 'Brown')
        assert err is None
        assert sum(1 for l in new_lines if '1 NAME' in l) == 1
        assert sum(1 for l in new_lines if '2 GIVN' in l) == 1
        assert sum(1 for l in new_lines if '2 SURN' in l) == 1

    def test_empty_surname(self):
        new_lines, err = _edit_name(SIMPLE_NAME_GED, '@I1@', 'Madonna', '')
        assert err is None
        name_line = next(l for l in new_lines if '1 NAME' in l)
        assert 'Madonna' in name_line
        # SURN sub-tag should be absent when surname is empty
        assert not any('2 SURN' in l for l in new_lines)

    def test_missing_xref_returns_error(self):
        _, err = _edit_name(SIMPLE_NAME_GED, '@I99@', 'X', 'Y')
        assert err is not None

    def test_line_count_stable(self):
        """Renaming should not change the total line count (same NAME block size)."""
        new_lines, err = _edit_name(SIMPLE_NAME_GED, '@I1@', 'James', 'Brown')
        assert err is None
        assert len(new_lines) == len(SIMPLE_NAME_GED)


class TestFamBlock:
    def test_find_fam_block_found(self):
        start, end, err = _find_fam_block(FAM_GED, '@F1@')
        assert err is None
        assert start is not None
        assert end is not None
        assert 'FAM' in FAM_GED[start]

    def test_find_fam_block_missing(self):
        _, _, err = _find_fam_block(FAM_GED, '@F99@')
        assert err is not None

    def test_find_fam_event_block_marr(self):
        start, end, err = _find_fam_event_block(FAM_GED, '@F1@', 'MARR')
        assert err is None
        assert '1 MARR' in FAM_GED[start]
        # Block should include DATE and PLAC
        block = FAM_GED[start:end]
        assert any('DATE' in l for l in block)
        assert any('PLAC' in l for l in block)

    def test_find_fam_event_block_missing_tag(self):
        _, _, err = _find_fam_event_block(FAM_GED, '@F1@', 'DIV')
        assert err is not None

    def test_edit_marr_date_via_fam_block(self):
        start, end, err = _find_fam_event_block(FAM_GED, '@F1@', 'MARR')
        assert err is None
        new_lines = _edit_event_fields(FAM_GED, start, end, {'DATE': '5 MAR 1930'})
        marr_idx = next(i for i, l in enumerate(new_lines) if '1 MARR' in l)
        block = new_lines[marr_idx:marr_idx + 5]
        assert any('5 MAR 1930' in l for l in block)

    def test_edit_marr_add_note_via_fam_block(self):
        start, end, err = _find_fam_event_block(FAM_GED, '@F1@', 'MARR')
        assert err is None
        new_lines = _edit_event_fields(FAM_GED, start, end, {'NOTE': 'Civil ceremony'})
        assert any('Civil ceremony' in l for l in new_lines)

    def test_edit_marr_add_addr_via_fam_block(self):
        """Regression: adding ADDR to a MARR event must write '2 ADDR' into the FAM block."""
        start, end, err = _find_fam_event_block(FAM_GED, '@F1@', 'MARR')
        assert err is None
        new_lines = _edit_event_fields(FAM_GED, start, end, {'ADDR': 'St. Paul Cathedral'})
        marr_idx = next(i for i, l in enumerate(new_lines) if '1 MARR' in l)
        block = new_lines[marr_idx:marr_idx + 6]
        assert any('2 ADDR St. Paul Cathedral' in l for l in block), \
            'ADDR must appear as a sub-tag of MARR'

    def test_edit_marr_replace_existing_addr(self):
        """Editing an existing ADDR sub-tag on a MARR event must replace the value."""
        ged_with_addr = FAM_GED + [
            '0 @F2@ FAM',
            '1 HUSB @I1@',
            '1 WIFE @I2@',
            '1 MARR',
            '2 DATE 1 JAN 1900',
            '2 PLAC London, England',
            '2 ADDR Old Church',
            '0 TRLR',
        ]
        # Remove original TRLR from FAM_GED before appending
        ged = [l for l in FAM_GED if l != '0 TRLR'] + [
            '0 @F2@ FAM',
            '1 HUSB @I1@',
            '1 WIFE @I2@',
            '1 MARR',
            '2 DATE 1 JAN 1900',
            '2 PLAC London, England',
            '2 ADDR Old Church',
            '0 TRLR',
        ]
        start, end, err = _find_fam_event_block(ged, '@F2@', 'MARR')
        assert err is None
        new_lines = _edit_event_fields(ged, start, end, {'ADDR': 'New Venue'})
        assert any('2 ADDR New Venue' in l for l in new_lines), 'ADDR must be replaced'
        assert not any('Old Church' in l for l in new_lines), 'old ADDR must be gone'

    def test_edit_marr_addr_preserved_in_marr_event_dict(self, tmp_path):
        """After adding ADDR, parse_gedcom must read it back into the MARR event dict."""
        ged = tmp_path / 'addr_marr.ged'
        new_lines, err = None, None
        # Start with FAM_GED, add ADDR to the MARR block
        start, end, e = _find_fam_event_block(FAM_GED, '@F1@', 'MARR')
        assert e is None
        new_lines = _edit_event_fields(FAM_GED, start, end, {'ADDR': 'St. Paul Cathedral'})
        ged.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
        indis, fams, sources = parse_gedcom(str(ged))
        assert fams['@F1@']['marr']['addr'] == 'St. Paul Cathedral'

    def test_build_people_json_includes_marr_addr(self, tmp_path):
        """build_people_json must include the ADDR field in MARR events."""
        ged = tmp_path / 'addr_marr2.ged'
        start, end, e = _find_fam_event_block(FAM_GED, '@F1@', 'MARR')
        assert e is None
        new_lines = _edit_event_fields(FAM_GED, start, end, {'ADDR': 'St. Paul Cathedral'})
        ged.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')
        indis, fams, sources = parse_gedcom(str(ged))
        people = build_people_json({'@I1@'}, indis, fams=fams, sources=sources)
        marr_evts = [e for e in people['@I1@']['events'] if e['tag'] == 'MARR']
        assert marr_evts, 'Expected a MARR event'
        assert marr_evts[0]['addr'] == 'St. Paul Cathedral'


class TestBuildPeopleJsonFamXref:
    """fam_xref must be present on MARR events in build_people_json output."""

    def test_marr_has_fam_xref(self, parsed):
        indis, fams, sources = parsed
        # Find someone with a FAMS link
        xref = next(
            x for x, info in indis.items()
            if info.get('fams') and any(
                fams.get(f, {}).get('marr') for f in info['fams']
            )
        )
        people = build_people_json({xref}, indis, fams=fams, sources=sources)
        marr_evts = [e for e in people[xref]['events'] if e['tag'] == 'MARR']
        assert marr_evts, 'Expected at least one MARR event'
        for e in marr_evts:
            assert 'fam_xref' in e
            assert e['fam_xref'] is not None


# ---------------------------------------------------------------------------
# Duplicate 1 MARR in FAM block — parse_gedcom must not overwrite first block
# ---------------------------------------------------------------------------

DUPLICATE_MARR_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME John /Smith/
1 FAMS @F1@
0 @I2@ INDI
1 NAME Mary /Jones/
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1925
2 PLAC London, England
2 ADDR St. Paul Cathedral
2 SOUR @S1@
3 DATA
1 MARR
2 DATE 1 JAN 1925
2 PLAC London, England
2 SOUR @S2@
0 TRLR""".splitlines()


class TestDuplicateMarrBlock:

    def test_addr_from_first_marr_preserved(self, tmp_path):
        """
        Regression: when a FAM record contains two '1 MARR' blocks (a merge
        artifact), parse_gedcom must keep the sub-tags from the first block
        rather than overwriting with the bare second block.

        Without the fix, the second '1 MARR' replaced fams[xref]['marr'] with a
        fresh empty dict, silently discarding the ADDR written to the first block.
        """
        ged = tmp_path / 'dup_marr.ged'
        ged.write_text('\n'.join(DUPLICATE_MARR_GED) + '\n', encoding='utf-8')
        _, fams, _ = parse_gedcom(str(ged))
        marr = fams['@F1@']['marr']
        assert marr['addr'] == 'St. Paul Cathedral', \
            'ADDR from first MARR block must survive a duplicate bare 1 MARR line'

    def test_date_and_place_still_present(self, tmp_path):
        """DATE and PLAC from the first block must also be preserved."""
        ged = tmp_path / 'dup_marr2.ged'
        ged.write_text('\n'.join(DUPLICATE_MARR_GED) + '\n', encoding='utf-8')
        _, fams, _ = parse_gedcom(str(ged))
        marr = fams['@F1@']['marr']
        assert marr['date'] == '1 JAN 1925'
        assert marr['place'] == 'London, England'


# ---------------------------------------------------------------------------
# MARR ADDR round-trip: write via _edit_event_fields → parse → build_people_json
# ---------------------------------------------------------------------------

# Realistic FAM GED with SOUR/DATA/WWW sub-records under MARR subtags, matching
# real-world structure (this is what caused the addr to be invisible in the UI
# even after _edit_event_fields correctly wrote it to disk).
MARR_WITH_SOURCES_GED = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME John /Smith/
1 SEX M
1 BIRT
2 DATE 1880
1 FAMS @F1@
0 @I2@ INDI
1 NAME Mary /Jones/
1 SEX F
1 BIRT
2 DATE 1882
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1910
2 PLAC London, England
2 SOUR @S1@
3 PAGE Marriage register
3 DATA
4 DATE 1910
2 SOUR @S2@
3 PAGE Witness testimony
0 TRLR""".splitlines()


class TestMarrAddrRoundTrip:
    """
    Verify the complete path: edit → GED write → parse → build_people_json.

    The test uses a realistic FAM structure with SOUR/DATA sub-records to ensure
    the parser isn't confused by citations interleaved with MARR sub-tags.
    """

    def test_addr_survives_parse_after_edit(self, tmp_path):
        """
        _edit_event_fields writes ADDR; re-parsing the GED must return it in fams.
        This is the exact sequence that failed: ADDR written but parse_gedcom
        lost it (in production due to a duplicate 1 MARR, here we test the parser
        correctly reads ADDR even when SOUR/DATA records follow).
        """
        ged = tmp_path / 'round_trip.ged'
        ged.write_text('\n'.join(MARR_WITH_SOURCES_GED) + '\n', encoding='utf-8')

        lines = ged.read_text(encoding='utf-8').splitlines()
        start, end, err = _find_fam_event_block(lines, '@F1@', 'MARR')
        assert err is None

        new_lines = _edit_event_fields(lines, start, end, {'ADDR': 'St. Paul Cathedral'})
        ged.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')

        # Re-parse from disk (same as serve_viz does after _write_gedcom_atomic)
        _, fams, _ = parse_gedcom(str(ged))
        assert fams['@F1@']['marr']['addr'] == 'St. Paul Cathedral', \
            'ADDR must survive write → disk → re-parse'

    def test_addr_present_in_build_people_json_after_edit(self, tmp_path):
        """
        After editing ADDR, build_people_json must include it in the MARR event
        for both spouses — this is what populates PEOPLE[xref] on the client.
        """
        ged = tmp_path / 'round_trip2.ged'
        ged.write_text('\n'.join(MARR_WITH_SOURCES_GED) + '\n', encoding='utf-8')

        lines = ged.read_text(encoding='utf-8').splitlines()
        start, end, err = _find_fam_event_block(lines, '@F1@', 'MARR')
        assert err is None
        new_lines = _edit_event_fields(lines, start, end, {'ADDR': 'St. Paul Cathedral'})
        ged.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')

        indis, fams, sources = parse_gedcom(str(ged))
        people = build_people_json({'@I1@', '@I2@'}, indis, fams=fams, sources=sources)

        for xref in ('@I1@', '@I2@'):
            marr_evts = [e for e in people[xref]['events'] if e['tag'] == 'MARR']
            assert marr_evts, f'{xref} must have a MARR event'
            assert marr_evts[0].get('addr') == 'St. Paul Cathedral', \
                f'addr must be in MARR event for {xref} after edit → parse → build_people_json'

    def test_existing_addr_visible_on_initial_load(self, tmp_path):
        """
        When the GED already has ADDR on a MARR, build_people_json must include
        it without any edit — i.e. the initial page load shows the addr.
        """
        ged_with_addr = MARR_WITH_SOURCES_GED[:]
        # Inject a 2 ADDR line right after 2 PLAC in the MARR block
        insert_after = next(
            i for i, l in enumerate(ged_with_addr) if l == '2 PLAC London, England'
        )
        ged_with_addr = (
            ged_with_addr[:insert_after + 1]
            + ['2 ADDR St. Paul Cathedral']
            + ged_with_addr[insert_after + 1:]
        )
        ged = tmp_path / 'initial_load.ged'
        ged.write_text('\n'.join(ged_with_addr) + '\n', encoding='utf-8')

        indis, fams, sources = parse_gedcom(str(ged))
        assert fams['@F1@']['marr']['addr'] == 'St. Paul Cathedral'

        people = build_people_json({'@I1@'}, indis, fams=fams, sources=sources)
        marr_evts = [e for e in people['@I1@']['events'] if e['tag'] == 'MARR']
        assert marr_evts and marr_evts[0].get('addr') == 'St. Paul Cathedral', \
            'Pre-existing ADDR must appear in MARR event on initial page load'

    def test_addr_not_lost_when_sour_follows_addr(self, tmp_path):
        """
        Regression guard: SOUR/DATA/WWW lines after 2 ADDR must not interfere
        with the parsed addr value.
        """
        ged_lines = """\
0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME John /Smith/
1 FAMS @F1@
0 @I2@ INDI
1 NAME Mary /Jones/
1 FAMS @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 MARR
2 DATE 1 JAN 1910
2 PLAC London, England
2 ADDR Notre Dame Cathedral
2 SOUR @S1@
3 DATA
4 WWW https://example.com/source
2 SOUR @S2@
3 PAGE p. 42
3 DATA
4 DATE 1910
0 TRLR""".splitlines()
        ged = tmp_path / 'sour_after_addr.ged'
        ged.write_text('\n'.join(ged_lines) + '\n', encoding='utf-8')

        _, fams, _ = parse_gedcom(str(ged))
        assert fams['@F1@']['marr']['addr'] == 'Notre Dame Cathedral', \
            'ADDR must be preserved even when SOUR/DATA/WWW sub-records follow it'
