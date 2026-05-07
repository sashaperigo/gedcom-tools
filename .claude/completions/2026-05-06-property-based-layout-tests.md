# Task Completion: Property-based layout test suite

**Date**: 2026-05-06
**Branch**: main

---

## What was done

Landed a property-based test suite for `computeLayout`: random GED-shaped inputs run through `assertAllLayoutInvariants`, with shrinking on failure. Adds 3 new geometric invariants. 200 seeds by default; full `npm test` runs in ~1.2s. Independent of any tier-2/tier-3 layout refactor — lands as a regression net so future architectural changes have a strong test bed.

## Files changed

- `docs/superpowers/specs/2026-05-06-property-based-layout-tests-design.md` — design spec
- `tests/js/_layout_invariants.js` — added `assertGenerationsAligned`, `assertClusterXRangesDisjoint`, `assertChildWithinParentSpanRange`, plus `_clustersByUmbrella` helper. All wired into `assertAllLayoutInvariants` runner.
- `tests/js/_layout_invariants.test.js` — unit tests for the 3 new invariants
- `tests/js/_layout_generator.js` — deterministic mulberry32 PRNG, recursive ancestor/descendant builders, internal-consistency validator
- `tests/js/_layout_generator.test.js` — determinism + invariants on output structure
- `tests/js/_layout_shrink.js` — greedy single-pass shrinker
- `tests/js/_layout_shrink.test.js` — shrinker correctness
- `tests/js/viz_layout_property.test.js` — runner, env-var overrides, `KNOWN_FAILURES` allowlist

## Key decisions

- **Tier C (property tests) before tier 2/3 layout refactor**, per the doc at `docs/learnings/viz-expand-layout-bugs.md` line 205. The suite is architecture-independent and becomes a safety net for any subsequent rewrite.
- **`KNOWN_FAILURES` allowlist** rather than seed-based xfail or generator filtering. New patterns still break CI; the existing multi-FAM connector-overlap bug stays visible (and the suite keeps catching it) without blocking other work.
- **`assertChildWithinParentSpanRange` is restricted to focus-side descendants from fully-rendered couples without other-spouse multi-FAM**. The naive symmetric-span check doesn't generalize to ancestor-side descendants or to cases where the cluster legitimately anchors asymmetrically. The other two new invariants are unconditional.
- **Generator emits in-memory globals directly**, not raw GEDCOM. The layout doesn't read `.ged` files — it reads `PEOPLE/PARENTS/CHILDREN/RELATIVES/FAMILIES`. Skipping GEDCOM serialization saves ~0 value and a lot of complexity.
- **`maxTotalPersons` cap (default 30)** keeps property runs fast and shrinking tractable. Real bugs in larger trees would be caught regardless because they reduce to small failing inputs.

## Tests added/modified

- `tests/js/_layout_invariants.test.js` — 13 new tests covering the 3 new invariants (passing, failing, edge cases including focus-pill asymmetry and on-row spouse spans)
- `tests/js/_layout_generator.test.js` — 22 tests: PRNG determinism, output internal consistency across many seeds, structural invariants on generated globals
- `tests/js/_layout_shrink.test.js` — 9 tests: deep-copy isolation, person/expansion-set removal, greedy shrinking on synthetic and generated inputs
- `tests/js/viz_layout_property.test.js` — 200 generated seeds, all green via known-failure classification

## Follow-up / known gaps

- **Multi-FAM other-cluster connector overlap is on the `KNOWN_FAILURES` list** (`Descendant crossbar overlap at y=106` pattern). Investigation queued as the next task. Completion docs `2026-04-23-inter-cluster-gap-*.md` and `2026-04-25-merge-non-visible-fam-children-cluster.md` cover related work but didn't fix this exact configuration.
- **Generator does not bias toward "scenario templates"** named in the spec. First cut uses uniform-random with biased probabilities. If new bugs slip through, scenario templates ("both focus and adjacent sibling have expanded kids," etc.) are the next iteration.
- **Shrinking is greedy single-pass**, not full delta-debugging. Reducible cases that depend on removing two things together stay at the larger size. Acceptable for now.
- **Structural-impossibility filter not implemented**. The spec called for it; in practice the generator hasn't produced any provably-impossible configurations yet. Defer until needed.
