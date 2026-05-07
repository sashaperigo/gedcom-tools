# Property-based layout tests

**Status**: Draft (awaiting review)
**Author**: Claude
**Related**: `docs/learnings/viz-expand-layout-bugs.md` (line 205); the `genealogy-tree-layout` skill.

---

## Goal

Catch the "expand-layout" bug class at PR time by running `computeLayout` on randomly-generated genealogical inputs and asserting the geometric invariants we already know.

Lazy expansion is correct; within-frame placement is buggy. The existing example-based tests fix specific shapes after each bug ships. Random inputs that *vary* the shape (sibling counts, expansion sets, multi-FAM, on-row spouses) catch the class without us having to predict which shape will fail next.

This effort is independent of any architectural change to the layout engine. It lands first as a regression net so a future tier-2 (`{leftExtent, rightExtent}` pre-pass) or tier-3 (Reingold-Tilford rewrite) refactor can lean on it.

---

## Scope

**In scope**:
- A deterministic, seed-driven random generator that produces valid `(PEOPLE, PARENTS, CHILDREN, RELATIVES, FAMILIES)` globals plus expansion sets.
- A vitest suite that runs `computeLayoutChecked` on N seeds and reports failures with a reproducible seed.
- A small number of new invariants the doc names but the current suite doesn't enforce (see "New invariants" below).
- Shrinking on failure: when a seed fails, reduce the input to the smallest still-failing shape so the bug report is debuggable.

**Out of scope**:
- Visual / browser verification (CLAUDE.md requires this for UI work, but this work is layout-correctness only — no rendering).
- Property tests for non-layout JS (modals, panels, search).
- Any change to `viz_layout.js` itself.
- Generating raw `.ged` files. The layout consumes in-memory globals; we generate those directly.
- Configurations the doc declares structurally impossible (gotcha section starting line 99). Generator avoids them; if it produces one, we accept the failure as not-a-bug rather than asserting cleanliness.

---

## Existing infrastructure (do not rebuild)

Already present and load-bearing — the design integrates with these, not around them:

- `tests/js/_layout_invariants.js` — 6 invariants (`assertNoNodeOverlap`, `assertExactlyOneFocus`, `assertSiblingOrderMonotonic`, `assertChildrenInParentClusterRange`, `assertUmbrellasDisjointAtY`, `assertNoUmbrellaCrossesPersonCenter`) and `computeLayoutChecked` drop-in.
- `tests/js/viz_layout.test.js` — `resetGlobals({ people, parents, children, relatives, families })` helper for injecting layout inputs.
- `computeLayout(focusXref, expandedAncestors, expandedChildrenPersons, expandedSiblingsXrefs?)` — already returns `{ nodes, edges }`.

---

## Architecture

Three new modules, all under `tests/js/`:

```
tests/js/
  _layout_invariants.js          (existing)
  _layout_generator.js           (new) — random GED-shaped input generator
  _layout_shrink.js              (new) — failure-input minimization
  viz_layout_property.test.js    (new) — vitest suite using the above
```

### `_layout_generator.js`

Pure function: `generateLayoutInput(seed, options) → { globals, focusXref, expandedAncestors, expandedChildrenPersons, expandedSiblingsXrefs }`.

**Seeded PRNG** (mulberry32 or similar 1-line Lehmer — vendored, not a dep). Same seed → same input, always.

**Shape parameters** (the `options`):
| Knob | Default range | Why |
|---|---|---|
| `numGenerations` | 1–4 (ancestors) + 1–3 (descendants) | Most bugs in completion docs are within this depth. |
| `siblingsPerCouple` | 0–4 | Triggers multi-sibling packer cases. |
| `pSecondMarriage` | 0.2 | Multi-FAM children clusters live here. |
| `pOnRowSpouse` | 0.6 | On-row spouses are the source of half the gotchas. |
| `pSiblingHasOwnKids` | 0.4 | Required for the "sibling's child cluster spills past focus" bug. |
| `pExpandSibling` / `pExpandAncestor` / `pExpandChild` | 0.5 each | The whole point is to vary which subtrees are open. |

**Generation strategy**:
1. Build the ancestor tree top-down from `numGenerations` of focal-line ancestors. Each generation picks 0–4 siblings.
2. Each individual gets a marriage probability and 0–N children, recursively into descendants.
3. Birth years assigned by generation band so `assertSiblingOrderMonotonic` has something to check (gen 0 ≈ 1900, each generation up = −30, each generation down = +30, with ±5 jitter).
4. Choose a focus uniformly from generation 0; populate `expandedAncestors`, `expandedChildrenPersons`, `expandedSiblingsXrefs` from random subsets of eligible nodes.
5. Validate the output is internally consistent (every parent referenced exists, every CHIL is bidirectional with PARENTS, etc.) — reject and resample if not. This bug is in the generator, not the layout.

**Bias toward bug shapes**: completion docs name specific configurations that took weeks to find. The generator should oversample these:
- "Both focus and adjacent sibling have expanded kids" (gotcha #1)
- "Sibling has 2+ FAMs each with kids, one expanded" (multi-FAM merge)
- "Focus has on-row spouse and visible-FAM children plus other-FAM children" (focus pill asymmetry)
- "Two adjacent gen-1 siblings each with expanded gen-2 cluster" (Phase 2 mirror gotcha)

Implementation: keep these as named "scenario templates" the generator can roll into instead of pure random — the seed picks both the scenario template and the within-template parameters.

### `_layout_shrink.js`

When a seed fails, the raw input may have 50+ people. Debugging needs the minimal shape.

Shrinking strategy (greedy, single-pass — not full QuickCheck):
1. Try removing each non-focus person (and their FAM links). If still fails, keep removed.
2. Try removing each entry from each expansion set. If still fails, keep removed.
3. Try removing each spouse. If still fails, keep removed.
4. Stop when no single removal still fails.

Output: minimal `(globals, focus, expansion-sets)` plus a printable summary (xref tree + expansion sets) so the developer can paste it into a regression test.

### `viz_layout_property.test.js`

Structure:
```js
describe('layout invariants — property tests', () => {
  for (const seed of seeds(N)) {
    it(`seed=${seed}`, () => {
      const input = generateLayoutInput(seed);
      resetGlobals(input.globals);
      try {
        computeLayoutChecked(input.focusXref, input.expandedAncestors,
                             input.expandedChildrenPersons, input.expandedSiblingsXrefs);
      } catch (e) {
        const minimal = shrink(input, (i) => fails(i));
        throw new Error(`seed=${seed}\n${formatMinimal(minimal)}\n\nOriginal: ${e.message}`);
      }
    });
  }
});
```

**Seed source**: deterministic by default (`seeds(N)` returns `[1, 2, ..., N]` so CI is reproducible). Override with `LAYOUT_PROPERTY_SEED=<n>` env var to focus on one seed during debugging, and `LAYOUT_PROPERTY_COUNT=<n>` to scale up locally before merging a layout change.

**Default N**: 200. Vitest run target: under 5s on the existing `npm test`.

---

## New invariants

These are named in the doc (line 205) but the current `_layout_invariants.js` doesn't enforce them. Adding them as part of this work because the property suite is what makes them tractable to assert generically.

### `assertGenerationsAligned(nodes)`
Every node with the same `generation` field must share a single `y` coordinate. Catches: any future bug where a node lands on the wrong row.

### `assertClusterXRangesDisjoint(nodes, edges)`
A cluster = the set of descendant nodes that share a single umbrella crossbar (or, for the single-child case, share a colinear anchor drop). For each cluster, compute its x-range `[min(node.x), max(node.x + width)]`. At any given y, x-ranges of distinct clusters at that y must not overlap. Catches the inter-cluster-gap bug class (`2026-04-23-inter-cluster-gap-half-siblings.md` and follow-ups).

Cluster identification helper goes in `_layout_invariants.js` so example-based tests can reuse it. Implementation: group descendant nodes by which crossbar (or single-child anchor edge) their drop hangs from — re-using the lookup logic in `assertChildrenInParentClusterRange`.

### `assertChildWithinParentSpanRange(nodes, edges)`
For each descendant node `c` with parent `p`:
- `parentSpan` = `[p.x, p.x + width(p)]` if `p` has no on-row spouse, else `[min(p.x, spouse.x), max(p.x + width(p), spouse.x + width(spouse))]`.
- The cluster `c` belongs to has half-width `halfCluster = (clusterRight − clusterLeft) / 2`.
- Assert `c.x + NODE_W/2 ∈ [parentSpan.left − halfCluster, parentSpan.right + halfCluster]`.

`width(p)` is `NODE_W_FOCUS` for the focus, `NODE_W` otherwise (see gotcha #3). Catches the "child appears far past parent on the wrong side" variant — `assertChildrenInParentClusterRange` only checks crossbar containment, not whether the cluster itself is anchored to the right person.

All three go into `_layout_invariants.js` and into the `assertAllLayoutInvariants` runner so existing example-based tests benefit too.

---

## What the test output looks like on failure

Sample failure message (designed for actionability):

```
seed=47

Minimal failing input (after shrinking):
  PEOPLE:    @F@ (b.1900), @S@ (b.1898), @C@ (b.1925), @G@ (b.1950)
  FAMILIES:  @FAM1@ husb=@F@ wife=@S@ chil=[@C@]
             @FAM2@ husb=@C@ chil=[@G@]
  PARENTS:   @C@→[@F@,@S@], @G@→[@C@]
  focus=@F@
  expandedChildrenPersons={@C@}
  expandedAncestors={}
  expandedSiblingsXrefs={}

Invariant violation: Descendant crossbar overlap at y=296: [-150..50] and [40..240]
```

The developer can paste the input straight into a regression test, debug, and the regression sticks.

---

## Testing strategy for this work

- Unit tests on the generator: same seed → same output (determinism); generated inputs always pass internal-consistency checks.
- Unit tests on the shrinker: known reducible cases minimize correctly; non-reducible cases are returned unchanged.
- Unit tests on each new invariant: hand-built passing and failing layouts (mirroring the existing pattern in `_layout_invariants.test.js`).
- The property suite itself needs no extra tests — it *is* the test.

---

## Implementation plan (order)

1. Add the 3 new invariants + their unit tests. Land first; existing example-based tests get the coverage immediately.
2. Build the generator + its determinism unit tests. Land before the property suite so failures on day 1 of the suite aren't generator bugs.
3. Build the shrinker + its unit tests.
4. Wire up `viz_layout_property.test.js` with N=200. Triage any failures: real bugs filed as completion docs; structurally-impossible configurations marked as generator-bias issues and excluded.
5. Tune defaults so green CI runs <5s. If that's not achievable at N=200, drop default to N=100 and document the ceiling.

Estimate: each step is roughly half a day. Total ~2 days.

---

## Risks and open questions

**Risk: false positives from structurally-impossible inputs.** The doc (line 99) names configurations that genuinely cannot be drawn cleanly. If the generator produces one and `computeLayout` does its best but violates an invariant, the suite will fail on a non-bug. Mitigation: the generator has a structural-impossibility filter that rejects inputs matching the patterns the doc names (3+ children each with in-laws whose parents are also expanded, etc.). Imperfect — accept some manual triage in the first week.

**Risk: shrinking is greedy, not optimal.** A failing input might shrink to a still-too-large minimum because removing person A alone passes, removing person B alone passes, but removing both fails. Acceptable for now; full delta-debugging is out of scope.

**Open question: should the generator also produce inputs that exercise `_packRow`, `_rightContour`, etc. directly?** Currently it only drives `computeLayout` end-to-end. If sub-helpers have their own invariants worth checking in isolation, those would be a follow-up. Default: no, keep this end-to-end only.

**Open question: where does the structural-impossibility filter live?** Either in the generator (refuses to emit) or the test runner (catches and skips). Generator is cleaner; runner is more conservative. Default: generator.

---

## Non-goals

- Replacing example-based tests. The completion docs' regression tests stay — they document specific bugs and stay readable. The property suite is *additional*.
- Catching layout-rendering mismatches (i.e., layout is correct but the SVG renderer draws wrong). Out of scope; needs visual/browser verification.
- Performance benchmarks. Layout perf is fine at current scale; not a goal of this work.
