# Task Completion: Add undated death via UI (DEAT Y)

**Date**: 2026-04-24

---

## What was done

Added a "Date unknown" checkbox to the Add Event modal that appears only when the Death event type is selected. Checking it disables the date field and causes the server to write `1 DEAT Y` (the GEDCOM sentinel for "confirmed deceased, date unknown") rather than a bare `1 DEAT`. Undated death events now appear in the timeline panel, and the `DEAT Y` `Y` value is no longer rendered as a note.

## Files changed

- `viz_ancestors.html` — added `#event-modal-date-unknown-row` checkbox row (hidden by default)
- `js/viz_modals.js` — `_updateEventModalFields` shows/hides row for DEAT; `_onDateUnknownChange` disables date input; `submitEventModal` sends `DATE:'Y'` when checked and validates that DEAT adds without a date or checkbox are rejected; `editEvent` always hides the row (adds only); `_onDateUnknownChange` and `_updateEventModalFields` exported for testing
- `serve_viz.py` — `/api/add_event` skips date normalization for `DATE='Y'` on DEAT; `_insert_new_event` writes `1 DEAT Y` as inline value (not `2 DATE Y` subline) and skips the DATE subtag loop entry when `deat_y` is set
- `viz_ancestors.py` — `_indi_open_event` detects `DEAT Y` and clears both `note` and `inline_val` so the `Y` sentinel never renders as user-visible text
- `js/viz_panel.js` — `allVisible` does NOT unconditionally include DEAT; bare `DEAT Y` (no date/place/note/cause) is filtered out so no empty card appears; `has_death` on the person data is what suppresses "Living" in the lifespan bar

## Key decisions

- Sent `DATE: 'Y'` as the field value rather than a separate flag, reusing the existing add_event endpoint — avoids a new API endpoint for what is structurally a date value.
- `DEAT Y` is detected in `_insert_new_event` (not at the handler level) so the logic is co-located with the line-writing code.
- "Date unknown" checkbox only appears on Add (not Edit) — editing an existing `DEAT Y` event would require converting the inline value, which is a separate concern.
- Validation requires either a date OR the checkbox for DEAT adds, preventing accidental bare `1 DEAT` records with no content.

## Tests added/modified

- `tests/test_serve_viz_http.py::TestAddEventEndpoint` — 3 new tests: `1 DEAT Y` written correctly (not `2 DATE Y`), `has_death=True` in refreshed payload, DEAT event appears in refreshed events list
- `tests/js/viz_panel.test.js` — 1 new test: bare `DEAT Y` produces no timeline card (only one `evt-entry` for BIRT, no "Death" text)
- `tests/js/viz_modals.test.js` — 3 new tests: `_updateEventModalFields` shows date-unknown row for DEAT, hides for RESI and BIRT

## Follow-up / known gaps

- Editing an existing `DEAT Y` record from the timeline is not yet supported (the edit modal opens but shows a blank date). This is an edge case; the record is still valid in the GEDCOM.
