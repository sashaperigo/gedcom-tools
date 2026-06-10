# Testing Patterns

---

## Two test categories

**Unit tests** (no real GED file needed): Use `tests/helpers.py` builders to construct in-memory objects.
```python
from tests.helpers import make_indi, make_family, make_file, make_source

def test_match_score():
    a = make_indi('@I1@', given='Maria', surname='Papadopoulos', birth_year=1880)
    b = make_indi('@I2@', given='Maria', surname='Papadopoulou', birth_year=1880)
    # assert match score > threshold
```

**Integration tests** (need a real GED file): Set `GED_PATH` at module level — `conftest.py` auto-skips the module when env var is absent.
```python
import os
GED_PATH = os.environ.get('GED_FILE')

def test_all_names_have_slashes():
    if not GED_PATH:
        pytest.skip('GED_FILE not set')
    # parse GED_PATH and assert
```

---

## `conftest.py` wiring

`conftest.py` reads `--gedfile` CLI option and writes it to `GED_FILE` env var, falling back to the canonical path if it exists. Tests that define `GED_PATH = os.environ.get('GED_FILE')` at module level are auto-skipped via `pytest_runtest_setup` when the value is falsy.

Running a subset:
```bash
# Single test file with GED
GED_FILE=../smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged pytest tests/test_dates.py

# All merge unit tests (no GED needed)
pytest tests/test_gedcom_merge_match_individuals.py tests/test_gedcom_merge_merge.py
```

---

## Fixture files

Small `.ged` snippets live in `tests/fixtures/`. Use these for testing specific parsing edge cases instead of long inline strings. Name fixtures descriptively after the scenario, e.g. `cont_conc_multiline.ged`, `duplicate_birt.ged`.

---

## JavaScript tests (vitest) — caching gotchas

⚠️ **getParsed caching**: The `viz_name_match.getParsed` function caches parsed name data using `id` as the key. If you reuse test IDs across multiple tests in the same suite (e.g., id='a' appears in both the surname-sort test and the given-name-sort test with different names), **the second test will receive stale cached data from the first test**. This can mask bugs — e.g., a wrong implementation that always applies surname sort would still pass both tests if they use identical IDs.

**Fix**: Use unique ID prefixes per test — e.g., `s1, s2, s3, s4` for the surname test, `g1, g2, g3, g4` for the given-name test. This ensures cache keys never collide. See `2026-06-10-fix-sortresults-test-gaps.md` for a concrete example.

---

## JavaScript tests (vitest)

JS modules in `js/` are tested in `tests/js/*.test.js`. Tests run with `npm test` (vitest, node environment). Modules use globals (`PEOPLE`, `PARENTS`, `CHILDREN`, `DESIGN`, `FAMILIES`) rather than imports — inject these as test setup:

```js
import { describe, it, expect, beforeEach } from 'vitest';

globalThis.PEOPLE = { '@I1@': { name: 'Test', sex: 'M', birth_year: 1900 } };
globalThis.PARENTS = {};
globalThis.CHILDREN = {};
// ... then call layout functions
```

---

## What not to test

- Don't test GEDCOM formatting trivia that the spec guarantees (e.g. that level 0 lines exist). Test behavior and data correctness.
- Don't test that `write_lines` writes atomically — that's tested in its own unit; callers just use it.
- Don't add GED_FILE-dependent tests for logic that can be exercised with builder helpers.

---

## Layout geometric invariants

`tests/js/_layout_invariants.js` provides `computeLayoutChecked` — a drop-in for `computeLayout` that runs a suite of geometric invariants (no-overlap, disjoint umbrellas, children-in-cluster-range, etc.) on every result. **Use it by default in any new layout test.** Use plain `computeLayout` only when the test intentionally constructs a malformed layout to verify error handling — and add a comment saying so.

Available invariants (each also exported individually for targeted testing):
- `assertNoNodeOverlap` — no two same-y pills overlap in x
- `assertExactlyOneFocus` — exactly one node with role='focus'
- `assertSiblingOrderMonotonic` — focus-row siblings ordered by birth year
- `assertChildrenInParentClusterRange` — every descendant hangs from a valid umbrella
- `assertUmbrellasDisjointAtY` — crossbars at same y don't overlap in x (strict-less-than: T-junctions sharing a single endpoint are allowed)
- `assertNoUmbrellaCrossesPersonCenter` — opposite-side rule for shared anchors

`assertAllLayoutInvariants(layoutResult)` runs the full suite. Order: focus → overlap → sibling order → umbrellas → cross-anchor → children-in-range (cheapest/most-likely-to-fire first).

See `docs/learnings/viz-expand-layout-bugs.md` for the bug classes each invariant catches.

### When to use plain `computeLayout` instead

All tests in `tests/js/viz_layout.test.js` now use `computeLayoutChecked`. Only use plain `computeLayout` if a test is intentionally exercising a known-broken configuration and you want to assert on the broken output — add a comment explaining why.

---

## Property-based layout tests

`tests/js/viz_layout_property.test.js` generates 200 random GED-shaped inputs per `npm test` run (~1.2s) and runs `assertAllLayoutInvariants` on each. Use `LAYOUT_PROPERTY_COUNT=1000 npm test` to run more seeds locally.

On failure, the shrinker (`_layout_shrink.js`) reduces the input to a minimal reproducer you can paste directly into a unit test. The `KNOWN_FAILURES` array in the runner is the place to park an open layout bug without blocking CI — add an entry with `{ pattern: /matching error message/, doc: 'completion-doc-name' }`. The array is currently empty (no known open layout bugs).

Key files:
- `tests/js/_layout_generator.js` — deterministic PRNG, recursive input builder
- `tests/js/_layout_shrink.js` — greedy single-pass shrinker
- `tests/js/_layout_invariants.js` — all invariant functions + `assertAllLayoutInvariants`

---

## `isFullRelationship` and MRCA stability in JS test fixtures

When building fixtures for "1st Cousin" or "Niece/Nephew" tests, single-parent entries produce half-relationships. `isFullRelationship` requires both MRCA-side children (the first generation below the MRCA on each path leg) to share the same **non-null** second parent. Two pitfalls:

**Pitfall 1 — half labels**: If `@PV@: [null, '@GMA@']` (only mother), then `otherParentInFam(@PV@, @GMA@)` returns `null`. The `opViewer !== null` guard fails → the relationship is classified as half. Fix: add a second parent to both MRCA-side children.

**Pitfall 2 — MRCA selection when both grandparents are shared**: If `@PV@` and `@PC@` share BOTH `@GMA@` and `@GPA@`, BFS finds both as common ancestors at the same distance. `findAllBloodRelatives` picks the first one encountered in BFS order, which is determined by parent array order (`[father, mother]`). To pin a specific MRCA, place it FIRST in the parents array: `'@PV@': ['@GMA@', '@GPA@']` ensures `@GMA@` is discovered first and wins the tiebreak.

---

**Last Updated**: 2026-05-29
