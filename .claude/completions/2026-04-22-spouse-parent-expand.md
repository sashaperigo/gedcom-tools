# Task Completion: Spouse Parent-Expand Chevron + Collision Avoidance

**Date**: 2026-04-22
**Branch**: main

---

## What was done

Extended the ancestor-visualization's parent-expand chevron to the focus person's spouse, so the spouse's ancestry is explorable with the same recursion and UI affordances as the focus-side ancestors. When both sides are expanded, the spouse's ancestor subtree is spaced from the focus's ancestor subtree via the same Reingold-Tilford contour-comparison that already separates a single ancestor's father-subtree from mother-subtree (`_requiredSeparation` in `viz_layout.js`).

## Files changed

- `js/viz_layout.js` — tagged focus-spouse nodes with `isFocusSpouse: true`; moved per-spouse `_placeAncestors` / `_placeAncestorSiblings` into a new Phase 1.5 pass that runs after focus-parents placement; added `_computeFocusSpouseShift` and `_shiftFocusSpouseSubtree` helpers.
- `js/viz_render.js` — one-line change: parent-expand chevron gate now includes `node.isFocusSpouse` in addition to ancestor role.
- `tests/js/viz_layout.test.js` — added 9 new cases covering: the flag, recursive placement, collision avoidance (both sides expanded), no-shift edge cases, and younger-sibling cascade.
- `tests/js/viz_render.test.js` — source-contract test confirming the chevron gate includes `isFocusSpouse`.
- `docs/superpowers/specs/2026-04-22-spouse-parent-expand-design.md` — design doc.
- `docs/superpowers/plans/2026-04-22-spouse-parent-expand.md` — implementation plan (pre-collision-fix).

## Key decisions

- **Added an `isFocusSpouse` flag rather than a new role.** Many existing tests and code paths filter on `role === 'spouse'` (focus's spouse, focus-sibling's spouse, co-spouses all share that role). Changing the role would have been invasive; a flag is additive and precisely tags the focus person's own primary spouse(s).
- **Reused `_placeAncestors` as-is for spouse-side ancestry.** The function is xref-agnostic — it just takes a child anchor (xref + x + y + generation) and recursively places parents above. Passing `(spouseXref, spouseX, 0, 0, …)` gives us spouse's parents at `y = -ROW_HEIGHT`, grandparents recursively, sibling chevrons on the new ancestor pills, etc., all for free.
- **Collision is fixed in a new Phase 1.5 pass, not by reordering the entire layout.** Phase 1.5 runs after both focus-parents and all gen-0 placement are done, so we have concrete xrefs + positions to feed into `_requiredSeparation`. Shifts are applied to already-placed gen-0 nodes and marriage-row edges.
- **`_shiftFocusSpouseSubtree` uses `y >= ancUmbrellaY` as the "gen-0 zone" filter.** That deliberately includes the focus-ancestor umbrella drops into gen-0 child centers (so when a younger focus-sibling shifts right, its drop from the umbrella also shifts), but excludes the focus-ancestor marriage edge (at `y = -ROW_HEIGHT + NODE_H/2`), so the focus-parents subtree is not disturbed.
- **Left-side focus-spouse uses the symmetric rule.** Same algorithm against focus's father.

## Tests added/modified

- `tests/js/viz_layout.test.js` — `computeLayout — focus spouse parent expansion` describe:
  - Focus spouse tagged with `isFocusSpouse`; sibling-of-focus's spouse is not.
  - Spouse's parents placed at `y = -ROW_HEIGHT` when spouse is expanded; not placed when collapsed.
  - Recursive grandparent placement when spouse's father is also expanded.
- `tests/js/viz_layout.test.js` — `computeLayout — focus-parents ↔ spouse-parents collision avoidance` describe:
  - Required center-to-center gap preserved between focus-mother and spouse-father when both sides expanded.
  - No shift when focus has no parents in the tree.
  - No spouse parents placed when spouse side is collapsed.
  - Younger focus-sibling stays right of the shifted spouse (guards the shift cascade).
- `tests/js/viz_render.test.js` — chevron gate includes `node.isFocusSpouse`.

## Follow-up / known gaps

- **Pedigree collapse** (focus and spouse sharing an ancestor) is not deduplicated. Same situation already exists for focus-father/focus-mother shared ancestors — out of scope here.
- **Left-side focus-spouse collision** is implemented symmetrically but not covered by a test case. The naive "x ≤ originalSpouseX + NODE_W" selector also captures older focus-siblings, which is the right behavior in most cases (they shift together with the left spouse) but the `focusGroupCenterX` umbrella-anchor-drop edge is not updated after the shift, so the anchor drop can become a diagonal line instead of vertical. No real-world data exposed this yet; revisit if it shows up.
- **Multiple right-side spouses with both expanded** will each compute shifts independently. The second spouse's shift is computed against focus-mother as if the first spouse's shift hasn't happened; this works because focus-mother's position is the reference, not the first spouse's. Not tested explicitly.
