# Common Mistakes

**⚠️ CRITICAL — Read at session start**

---

## 1. Running tests or the server against `merged.ged`

**Always use the canonical path:**
```bash
GED_FILE=../smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged pytest
GED_FILE=../smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged python serve_viz.py
```
Never reference `merged.ged` in test runs or dev server invocations.

---

## 2. Writing output files directly instead of through `gedcom_io.write_lines`

All cleaning scripts must use `write_lines(lines_out, path_in, path_out, dry_run, changed)` for atomic, dry-run-aware writes. Opening a file with `open(..., 'w')` directly bypasses dry-run and in-place logic.

---

## 3. Committing merge output files

Never commit `merged.ged`, `merge-session.json`, or `merge-report.txt` — they are ephemeral outputs, not source files.

---

## 4. Forgetting that cleaning scripts are also importable

Each standalone cleaner returns `(lines_out, changed)` when called as a function. `normalize_ancestry.py` imports and chains them — don't add subprocess calls or file I/O inside a cleaner's transform function.

---

## 5. Fixing SVG layout bugs by tweaking data without checking the rendered geometry

When a viz bug is reported via screenshot, the fix is a rendering property, not just an edge-list shape. Two horizontal SVG segments sharing a Y and an endpoint render as one continuous line — emitting them as separate edge objects does not make them look separate. A bigger gap on the child row does not prevent a line above it from crossing the gap. Before committing a layout fix:

- Write tests for the **geometric invariant** (e.g. "no horizontal at umbrellaY crosses personCenter"), not just for the edge-list shape.
- If a prior fix shipped and the user still sees the bug, stop iterating on the same design — the invariant isn't what you thought.
- For visual fixes, open the browser once before calling it done.

See `docs/learnings/common-pitfalls.md` → **SVG edge geometry** for the umbrella-bug case study (commits `42a3592`, `e5c4697`, `ae71df0` all partly addressed it; `cf86699` finally did).

---

## 6. Fixing event card behavior for INDI events but not FAM events (or vice versa)

FAM events (MARR/DIV) use different fields than INDI events:

| | INDI events | FAM events (MARR/DIV) |
|---|---|---|
| Occurrence key | `event_idx` (integer) | `marr_idx` / `div_idx` (integer) + `fam_xref` |
| `event_idx` value | set | `null` |

Any change to event card logic — lookup, pre-fill, display, save — must handle **both** flows. A fix that only checks `event_idx` will silently fail for MARR/DIV (the field is null). Write tests covering both branches.

Affected functions: `showEditCitationModal`, `showEditEventModal`, `_buildSourcesModalContent`, and any event-level lookup in `viz_modals.js`.

---

## 7. Smart quotes inside JS template literals silently break HTML attributes

A `class=”foo”` attribute (U+201C/U+201D curly quotes) is *not* a parse error in either JS (it's just a normal character inside a backticked string) or HTML (the browser silently treats the whole thing as junk and drops the class). The failure mode is purely visual — styles disappear and the element renders as raw unstyled text. Easy to introduce when an editor or paste step auto-corrects ASCII `"` to typographic `”` inside a template literal.

If a recently-styled UI element suddenly looks completely unstyled, before debugging CSS run:

```bash
grep -nP '[\x{201C}\x{201D}]' js/*.js
```

Bug case study: commit `1bfbc5b` introduced the corruption inside `_buildSourcesModalContent` in `js/viz_modals.js`; commit `e894866` restored ASCII quotes. The CSS was never broken.

---

## 8. `_citation_already_exists` scans across event boundaries

The duplicate-citation check scans backward from `insert_pos`. The boundary is now `level <= cite_level - 1`, so fact-level checks (`cite_level=2`) stop at level-1 event boundaries and person-level checks (`cite_level=1`) stop at level-0 record boundaries. **Do not revert this to `raw.startswith('0 ')`.** Scanning all the way back to level-0 crosses into earlier events in the same INDI record and falsely detects "duplicates" — the citation is silently not written while the server still returns `ok: true`. This is the hardest kind of bug to notice because there is no error.

---

## 9. Modal checkbox DOM diverging from state after toggle

Modals that pre-render checkbox state from implicit/derived logic (e.g., "primary FAM is always checked") will silently desync from `visibleSpouseFams` (or any similar Set) when `setState` is called in response to a toggle. The symptom is counterintuitive: the user thinks they're selecting *both* items, but subsequent clicks remove one instead of keeping both.

**Root cause:** The modal HTML is rendered once in `openXxxModal` and never updated by `toggleXxxFam`. If the initial render reflects an implicit default (primary = checked) rather than the actual state, the first toggle writes to state correctly but the DOM stays wrong — the next toggle sees a `checked` DOM element and removes the value.

**Fix pattern:** Call `_buildXxxRows` and update `element.innerHTML` at the end of every `toggleXxxFam`, mirroring the initial render call in `openXxxModal`. Re-rendering is safe inside `onchange` (click already completed) and guarantees DOM ↔ state correctness.

See commit `d5f910d` for the spouse-menu case study (`toggleSpouseMenuFam` in `js/viz_modals.js`).

---

## 10. Edit tool fails on `viz_panel.js` lines containing unicode escape sequences

`viz_panel.js` stores sex symbols and special characters as JS escape sequences (`'♂'`, `'♀'`, `'✏'`) — not as literal characters. The Edit tool matches raw file bytes, so passing actual `♂`, `♀`, `✏` characters in `old_string` will silently fail with "String to replace not found."

**Fix:** Use Python to perform the substitution:
```python
with open('js/viz_panel.js', 'r', encoding='utf-8') as f:
    content = f.read()
content = content.replace(old, new, 1)
with open('js/viz_panel.js', 'w', encoding='utf-8') as f:
    f.write(content)
```
The `old` string in Python source must contain the literal backslash-u sequences (e.g., `"'\\u2642'"`) to match the file bytes.

---

## 11. Renaming a JS CSS class without updating the matching CSS rule

When refactoring event card or panel HTML in `viz_panel.js`, renaming a class (e.g. `evt-prose` → `evt-prose-text`) silently un-styles the element — no error, no console warning, element just inherits browser defaults. The symptom is "broken CSS" on that element even though nothing in the CSS file looks obviously wrong.

**Check pattern:** After any JS class rename, grep for the old name in CSS:
```bash
grep -r "old-class-name" viz_ancestors.css js/
```
If it only appears in CSS (not JS), the CSS rule is now dead and must be renamed too.

Case study: commit `3ad4447` renamed the event title element from `evt-prose` to `evt-prose-text` in `viz_panel.js` but left `.evt-prose` in `viz_ancestors.css`. Fixed in commit `f142da9`.

---

## 12. Inter-cluster gap for half-sibling groups defaults to CHEVRON_CLEARANCE, not INTER_FAM_GAP

In `_placeChildrenOfPerson`, after placing the visible-FAM cluster, `pickStartInFreeGap` places the other-FAMs cluster with only `CHEVRON_CLEARANCE` (40px) between them — the same gap as between any two adjacent sibling nodes. Two distinct family groups must instead be separated by `INTER_FAM_GAP` (H_GAP × 8 = 96px), the same gap used between different FAMs *within* the other-FAMs cluster.

**Root cause:** `pickStartInFreeGap` knows nothing about cluster boundaries — it just avoids node collisions at `childY`. After `emitClusterNodes` for the visible cluster, `otherIdealStart` must be explicitly advanced past the visible cluster's actual right edge by `INTER_FAM_GAP`.

**Fix pattern** (in `_placeChildrenOfPerson`, before the `pickStartInFreeGap` call for the other cluster):
```js
if (visibleGroups.length > 0) {
    const spouseRight = visibleSpouseNode && visibleSpouseNode.x > personNode.x;
    // CRITICAL: only apply when visible cluster landed on its EXPECTED side.
    // If obstacles pushed it to the wrong side, skip — don't compound the displacement.
    if (spouseRight && actualVisibleStart + visibleWidth > personCenter) {
        otherIdealStart = Math.min(otherIdealStart, actualVisibleStart - INTER_FAM_GAP - otherWidth);
    } else if (!spouseRight && actualVisibleStart < personCenter) {
        otherIdealStart = Math.max(otherIdealStart, actualVisibleStart + visibleWidth + INTER_FAM_GAP);
    }
}
```

**The guard is essential.** Without it, when the visible cluster gets pushed to the wrong side by obstacles (e.g. ancestor nodes occupy its ideal position), the unconditional `max(...)` pushes `otherIdealStart` even further in the same wrong direction — piling both clusters on one side of the tree.

Apply the same pattern at ALL levels — both `_placeChildrenOfPerson` (Phase 3) and the focus-person children block (Phase 2). In Phase 2, replace `INTER_GROUP_GAP = H_GAP * 4` with `INTER_CLUSTER_GAP = H_GAP * 8` and enforce the gap bidirectionally.

Test invariant: gap between the rightmost node of one cluster and the leftmost node of the other `>= INTER_FAM_GAP` (only guaranteed when no obstacles displaced the visible cluster).

**Corollary — pre-nudge when obstacle is in the gap:** When ancestor nodes are already at childY between the two clusters' ideal positions (e.g. Michael+Monica placed by Phase 2 ancestry sit right of the visible cluster's ideal right edge), `pickStartInFreeGap` may skip the available gap entirely if `otherIdealStart` is pushed too far. The fix is to pre-adjust `visibleIdealStart` BEFORE the first `pickStartInFreeGap` call:

```js
// Find nearest obstacle to the right of visibleIdealStart + visibleWidth
const rightObstacle = nodes
    .filter(n => n.y === childY && n.x > visibleIdealStart + visibleWidth - CHEVRON_CLEARANCE)
    .reduce((best, n) => (!best || n.x < best.x) ? n : best, null);
if (rightObstacle) {
    const maxStart = rightObstacle.x - 2 * CHEVRON_CLEARANCE - otherWidth - visibleWidth;
    if (visibleIdealStart > maxStart) {
        visibleIdealStart = maxStart;   // shift visible left to open gap
        shiftedForGap = true;
    }
}
```

When `shiftedForGap`, skip the INTER_FAM_GAP push — the other cluster finds the now-212px gap via `pickStartInFreeGap(personCenter, otherWidth)`. This was diagnosed via console.log instrumentation that revealed the real layout coordinates.

---

## 13. OCCU/TITL/DSCR events silently dropped by `allVisible` when they lack date/place/type

The `allVisible` filter in `renderPanel` requires at least one of: `date`, `place`, `note`, `type`, `cause`, `addr`, or `tag === 'MARR'`. Events like OCCU, TITL, DSCR, and NCHI store their primary value in `inline_val` (not any of those fields). An undated, unplaced OCCU event with only `inline_val: 'Merchant'` passes none of the checks and is silently dropped — it never reaches `undatedFactoids`, never renders, and no error is thrown.

**Fix:** Include `|| e.inline_val` in the `allVisible` filter:
```js
const allVisible = (data.events || []).map((e, i) => ({ ...e, _origIdx: i })).filter(e =>
    e.tag !== 'NATI' &&
    (e.tag === 'MARR' || e.date || e.place || e.note || e.type || e.cause || e.addr || e.inline_val) &&
    !e._name_record
);
```

**Symptom in tests:** A test that stubs a minimal OCCU event `{ tag: 'OCCU', inline_val: 'Merchant', date: null, place: '' }` will find `alsoLivedEl.innerHTML` contains only the heading and add-fact button — no `fact-row`, no color. The event existed in the data but was discarded before `undatedRows` ran.

---

## 14. CSS stacking contexts trap child z-index values

Any element with `position` + `z-index` (or certain other properties like `transform`, `filter`, `opacity < 1`) creates a **stacking context**. A child's `z-index` is only meaningful *within* that context — it cannot escape it to paint above a sibling element with a higher z-index in the parent context.

**Symptom:** A dropdown or overlay with `z-index: 500` renders *below* a panel with `z-index: 50`, even though 500 > 50. This happens when the dropdown is a descendant of a stacking context whose own z-index (e.g. 2) is lower than the panel's.

**Diagnosis pattern:**
1. Identify the element that should be on top (e.g. `#search-results`, `z-index: 500`).
2. Walk up its DOM ancestors looking for any element with `position` + `z-index` set — that ancestor's z-index is the effective ceiling.
3. Compare that ceiling against the z-index of the element it must paint above.

**Fix:** Raise the ancestor's z-index so its stacking context wins. Alternatively, restructure the DOM so the floating element is not nested inside a stacking context at all.

**Case study:** `header` had `z-index: 2`; `#detail-panel` had `z-index: 50`. The search dropdown (`#search-results`, `z-index: 500`) lived inside the header — so it was capped at z-index 2 in the root context and always painted below the panel. Fix: set `header { z-index: 100 }` (commit `e820d36`).

---

## 15. Conflating "no death year" with "person is living"

`death_year` is `None` for anyone who has a `DEAT` record without a `DATE` subfield (e.g. `1 DEAT Y` with only `AGE`). Code that gates "Living" on `!death_year` will wrongly label deceased people as alive.

**Correct pattern:** Use `has_death` (a boolean set `True` whenever a `DEAT` event is opened) alongside `death_year`. Only show "Living" when both `!death_year` and `!has_death`.

Both `indis` (parse layer) and the `build_people_json` output carry `has_death`. The JS panel reads `data.has_death`.

---

## Testing pitfalls

- Tests with a module-level `GED_PATH` variable are skipped when `GED_FILE` is not set — this is intentional, not a test framework bug.
- Unit tests for merge logic (`tests/test_gedcom_merge_*.py`) do not need `GED_FILE`; they use `tests/helpers.py` builder functions.
- Fixture files live in `tests/fixtures/` — add small `.ged` snippets there for new unit tests rather than constructing long inline strings.

---

---

## 16. Dynamically-generated `<button>` elements without `type="button"` are silently treated as form-submit

Any `<button>` element without an explicit `type` defaults to `type="submit"`. In Chrome, when such a button is clicked and there are form fields (`<input>`, `<select>`, `<textarea>`) anywhere in the DOM — including inside *hidden* modals — Chrome creates an implicit form, treats the button as its submit control, and intercepts the click before the `onclick` handler completes. The symptom is **"nothing happens"** with a Chrome console warning: "A form field element should have an id or name attribute."

**This is especially treacherous with dynamically-generated HTML** (JS template literals building `innerHTML`). Static HTML in `viz_ancestors.html` already uses `type="button"` explicitly, but dynamically-generated buttons in `_buildSourcesModalContent` were missing it — allowing hidden modals' form fields to intercept clicks.

**Fix:** Always include `type="button"` in dynamically-generated button HTML:
```js
`<button type="button" class="citation-paste-btn" onclick="...">`
```

**Symptom checklist:**
- User clicks a button → nothing visible happens
- No alert, no error shown, no network request
- Chrome DevTools console shows "A form field element should have an id or name attribute"

Case study: `js/viz_modals.js` `_buildSourcesModalContent` — paste/copy/edit/delete/add buttons lacked `type="button"`. The hidden `add-citation-modal` and `edit-citation-modal` form fields in the DOM caused Chrome to intercept the paste click as a form submission. Fixed in commit `8d48bcb`.

---

---

## 17. `_TAG_RE` does not match xref-style level-0 GEDCOM lines

`_TAG_RE = re.compile(r'^(\d+)\s+(\w+)(?:\s+(.*))?$')` requires `\w+` (word characters) for the tag field. Xref-style records like `0 @I123@ INDI`, `0 @F1@ FAM`, `0 @S1@ SOUR` have `@I123@` in the tag position — `@` is not a word character — so `_TAG_RE.match(...)` returns `None` for these lines.

**Any code that uses `_TAG_RE` to detect level-0 record boundaries will silently fail to stop at xref-style headers.**

The canonical pattern elsewhere in the file is `raw.startswith('0 ')` for boundary detection (e.g. `_find_record_block`). Use that, not `_TAG_RE`, when you need to stop at any level-0 line.

**Affected bug**: `_citation_already_exists` used `_TAG_RE` for its backward-scan boundary check. It blew past `0 @I123@ INDI` lines and scanned back into earlier records, finding the same source+page in a *different* person's citation and falsely returning True. Result: `ok: true` returned to the client but no citation written — the hardest kind of bug because there is no error. Fixed in commit `3f1149a` with `if not m and raw.startswith('0 '): break`.

---

---

## 18. `:first-child` fails when a sibling element precedes the target class

If you write `.family-sub:first-child .family-sub-heading` to style the first section after a toggle button, it will never match — because the button element precedes all `.family-sub` divs, so no `.family-sub` is ever `:first-child` of its parent.

**Fix**: Use the adjacent sibling combinator instead:
```css
.family-toggle-btn + .family-sub .family-sub-heading { … }
```
This matches the first `.family-sub` immediately following the button, regardless of DOM position.

**Applies whenever**: you're styling the "first item of class X" but another element type always appears before it in the parent.

---

---

## 19. `editEvent` vs `addEvent` — only `addEvent` resets DOM input state

`addEvent()` explicitly resets every field including `dateInp.disabled = false` and unchecks the date-unknown checkbox. `editEvent()` only sets field *values*. Any `disabled`, `checked`, or `readOnly` state set during a previous `addEvent` call persists into the next `editEvent` call.

**Concrete failure**: user checks "Date unknown" in an Add Death modal → date input becomes `disabled`. They close that modal. They then click ✏ on a marriage card. `editEvent` opens the modal, sets `value = ''`, but leaves `disabled = true`. The date field is uneditable — the user cannot type a date.

**Fix pattern**: when adding a new toggle or "field unknown" control, add a matching reset inside `editEvent` (or a shared `_resetModalFieldState()` helper). The reset must run even when the corresponding row is hidden, because the field's DOM state persists across modal opens regardless of visibility.

**Fixed in**: commit `da38b09` — added `_duCb.checked = false` and `_dateInp.disabled = false` to `editEvent()` after hiding the date-unknown row.

---

**Last Updated**: 2026-04-24 (added #19 editEvent vs addEvent DOM state divergence)
