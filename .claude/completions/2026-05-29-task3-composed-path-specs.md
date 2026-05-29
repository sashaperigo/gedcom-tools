# Task Completion: Composed Path Specs in `_bestRel` (Task 3)

**Date**: 2026-05-29
**Branch**: feat/relationship-path-nonblood

---

## What was done

Three edits to `_bestRel` in `js/viz_relationship.js` so that composed ("X of Y") affinity labels carry a full path spec instead of `null`. Direct blood candidates now attach a `_bloodPathSpec`; blood-relative splits concatenate `subAtomic.path` with the blood leg spec; spouse splits append the viewer xref and a `spouse`/`ex-spouse` edge to the sub-path.

## Files changed

- `js/viz_relationship.js` — edits (a), (c), (d) in `_bestRel`: direct blood, blood-split, and spouse-split now all produce and propagate path specs
- `tests/js/viz_relationship.test.js` — three new `it` blocks added inside `describe('enumerateRelationships — affinity paths', ...)`: "Wife of 1st Cousin", "Niece of Spouse", and "label-parity" guard

## Key decisions

**Fixture correction for full cousins**: The spec's original test fixtures produced "Half-1st Cousin" and "Half-Niece" because the test people only had a single parent each. `isFullRelationship` requires both MRCA-side children to share the same non-null second parent. Added `@GPA@` (shared second parent) to the cousin fixture, and `@WF@` (shared second parent) to the niece fixture. This is not a change to test expectations — just correcting an incomplete fixture.

**MRCA selection stability with shared grandparents**: When a couple (e.g. `@GMA@` + `@GPA@`) are both common ancestors at the same distance, `findAllBloodRelatives` picks whichever is discovered first in BFS order. BFS processes parents in `[father, mother]` array order. By placing the desired MRCA first in the parents array (`['@GMA@', '@GPA@']`), the test fixture deterministically selects `@GMA@` as MRCA, matching the expected path index 3.

**`mrcaIndex` in composed paths**: For blood-split compositions, `mrcaIndex = (subAtomic.path.nodes.length - 1) + leftSpec.mrcaIndex`. The `- 1` accounts for the shared Z node appearing once in the concatenated node list.

## Tests added/modified

- `tests/js/viz_relationship.test.js`:
  - "Wife of 1st Cousin" — verifies full xref sequence, edgeKind sequence, isMrca index, and relToNext on the spouse edge
  - "Niece of Spouse" — verifies spouse split appends viewer xref with spouse edgeKind and correct relToNext
  - "label-parity" guard — verifies all entries from spouse and mother-in-law fixtures have non-null paths with correct isOther/isViewer endpoints

## Follow-up / known gaps

Task 4 (if any) would cover remaining non-blood path display features. The `mrcaIndex` arithmetic for composed paths is correct for single-level compositions; deeper nesting (depthLeft > 1) is not tested but also not enabled in production (`_MAX_REL_DEPTH = 1`).
