# Task Completion: Fix Citation Paste Button Silently Doing Nothing

**Date**: 2026-04-24

---

## What was done

Added `type="button"` to all five dynamically-generated `<button>` elements inside `_buildSourcesModalContent` in `js/viz_modals.js` (copy, edit, delete, add-source, paste). Without the explicit type, buttons default to `type="submit"`, which Chrome treats as form-submission relative to the hidden form fields (select, input, textarea) always present in the DOM from other modals (add-citation, edit-citation, etc.). The submit interception silently prevented `handleCitationPaste`'s onclick from completing.

## Files changed

- `js/viz_modals.js` — added `type="button"` to copy/edit/delete citation action buttons and to the `citation-add-primary` / `citation-paste-btn` buttons in `_buildSourcesModalContent`

## Key decisions

The symptom — "nothing happens" plus Chrome's "A form field element should have an id or name attribute" console warning — is the canonical Chrome signal for an implicit form submission being triggered by a `type="submit"` button that finds loose form fields in the DOM. The hidden modals (add-citation-modal, edit-citation-modal, etc.) are always in the DOM even when not visible, so Chrome associates their inputs with any nearby `type="submit"` button.

The static buttons in `viz_ancestors.html` (the event modal's paste button at line 150) already had `type="button"` explicitly — only the dynamically-generated buttons in `_buildSourcesModalContent` were missing it.

## Tests added/modified

No new tests — all 163 existing `viz_modals.test.js` tests continue to pass.

## Follow-up / known gaps

`viz_panel.js` also generates many `<button>` elements without `type="button"` (add-event, edit-name, marr-edit, etc.). Those live in the `detail-panel`, which contains no form fields, so they don't currently trigger the same issue. They could be hardened preemptively but are out of scope for this fix.
