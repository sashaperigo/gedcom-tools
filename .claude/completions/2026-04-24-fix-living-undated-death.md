# Task Completion: Fix "Living" shown for undated death records

**Date**: 2026-04-24

---

## What was done

People with a `DEAT` record but no date were incorrectly shown as "Living" in the info panel header. Added a `has_death` boolean to INDI parsing that is set `True` whenever any `DEAT` event is opened, regardless of whether it carries a date. Threaded `has_death` through `build_people_json` and into the JS panel, which now gates the Living label on `!hasDeath` instead of `!death_year`.

## Files changed

- `viz_ancestors.py` — initialize `has_death: False` on every INDI record; set to `True` in `_indi_open_event` when `tag == 'DEAT'`; emit `has_death` from `build_people_json`
- `js/viz_panel.js` — introduce `hasDeath = !!data.has_death`; condition both Living spans on `!hasDeath`
- `tests/test_viz_ancestors.py` — 5 new tests covering `has_death` on undated DEAT (`@I9@`), no DEAT (`@I3@`), and dated DEAT (`@I4@`) at both the parse and `build_people_json` layers

## Key decisions

- Tracked `has_death` at the parse layer (`indis`) rather than inferring it from the events list at serialization time, because the pattern is consistent with how `death_year` is tracked and avoids a second pass over events.
- Used `has_death` as a boolean rather than a tristate, keeping the distinction simple: either a `DEAT` record exists (deceased) or it doesn't (potentially living).

## Tests added/modified

- `tests/test_viz_ancestors.py::TestParsing::test_has_death_true_when_deat_record_exists` — `@I9@` (`DEAT Y`, no date): `has_death True`, `death_year None`
- `tests/test_viz_ancestors.py::TestParsing::test_has_death_false_when_no_deat_record` — `@I3@` (no DEAT): `has_death False`
- `tests/test_viz_ancestors.py::TestParsing::test_has_death_true_when_deat_has_date` — `@I4@` (dated DEAT): `has_death True`
- `tests/test_viz_ancestors.py::TestPeople::test_has_death_propagated_to_people` — same undated-death case through `build_people_json`
- `tests/test_viz_ancestors.py::TestPeople::test_has_death_false_propagated_to_people` — no-DEAT case through `build_people_json`

## Follow-up / known gaps

None. The node label in `viz_render.js` only uses `death_year` for "d. {year}" badges and never shows "Living", so no change was needed there.
