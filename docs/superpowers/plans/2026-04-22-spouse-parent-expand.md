# Spouse Parent-Expand Chevron Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the parent-expand chevron on the focus person's spouse when that spouse has parents, and expand/contract those parents exactly like focus-side ancestors.

**Architecture:** Tag focus-spouse nodes in `computeLayout` with `isFocusSpouse: true` to distinguish them from focus-siblings' spouses and co-spouses. Call the existing `_placeAncestorSiblings` and `_placeAncestors` helpers for each focus-spouse so the same expansion machinery runs. In render, extend the parent-expand chevron gate to include `node.isFocusSpouse`.

**Tech Stack:** Vanilla JS (ES module-style with `require`), Vitest for JS tests, Python/pytest for Python-side tests.

---

## Files touched

- Modify: `js/viz_layout.js`
  - Tag focus-spouse nodes with `isFocusSpouse: true` at the two focus-spouse emission sites (right-side primary spouse ~line 198, left-side spouse ~line 261).
  - After each focus-spouse is pushed, call `_placeAncestorSiblings` and `_placeAncestors` for that spouse xref.
- Modify: `js/viz_render.js`
  - Extend the parent-expand chevron gate at line 301 from `if (isAncestor)` to `if (isAncestor || node.isFocusSpouse)`.
- Add: `tests/js/viz_layout.test.js`
  - New `describe('computeLayout — focus spouse parent expansion', ...)` block.
- Add: `tests/js/viz_render.test.js`
  - New test verifying the chevron gate includes `isFocusSpouse`.

---

### Task 1: Failing test — focus spouse node carries `isFocusSpouse` flag

**Files:**
- Test: `tests/js/viz_layout.test.js` (append new `describe` block at end of file)

- [ ] **Step 1: Write the failing test**

Append to `tests/js/viz_layout.test.js`:

```js
describe('computeLayout — focus spouse parent expansion', () => {
    beforeEach(() => {
        resetGlobals({
            people: {
                '@FOCUS@': { birth_year: 1765 },
                '@SPOUSE@': { birth_year: 1765 },
                '@SPDAD@':  { birth_year: 1735 },
                '@SPMOM@':  { birth_year: 1740 },
                '@SIB@':    { birth_year: 1770 },
                '@SIBSP@':  { birth_year: 1768 },
            },
            relatives: {
                '@FOCUS@':  { siblings: ['@SIB@'], spouses: ['@SPOUSE@'] },
                '@SPOUSE@': { siblings: [], spouses: ['@FOCUS@'] },
                '@SIB@':    { siblings: ['@FOCUS@'], spouses: ['@SIBSP@'] },
                '@SIBSP@':  { siblings: [], spouses: ['@SIB@'] },
            },
            parents: {
                '@SPOUSE@': ['@SPDAD@', '@SPMOM@'],
            },
        });
    });

    it('marks focus spouse with isFocusSpouse=true', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const spouse = nodes.find(n => n.xref === '@SPOUSE@');
        expect(spouse).toBeDefined();
        expect(spouse.isFocusSpouse).toBe(true);
    });

    it('does NOT mark a sibling-of-focus spouse as isFocusSpouse', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        const sibSpouse = nodes.find(n => n.xref === '@SIBSP@');
        expect(sibSpouse).toBeDefined();
        expect(sibSpouse.isFocusSpouse).toBeFalsy();
    });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/viz_layout.test.js -t "focus spouse parent expansion"`

Expected: FAIL — `spouse.isFocusSpouse` is `undefined`, first assertion fails.

- [ ] **Step 3: Implement the minimal code to make the test pass**

In `js/viz_layout.js`, update the right-side primary spouse emission (~line 198):

```js
    rightSpouseXrefs.forEach((spouseXref, si) => {
        const thisSpouseX = firstSpouseX + si * SLOT;
        rightmostSpouseAreaX = thisSpouseX;
        nodes.push({
            xref: spouseXref,
            x: thisSpouseX,
            y: 0,
            generation: 0,
            role: 'spouse',
            isFocusSpouse: true,
        });
```

And the left-side spouse emission (~line 261):

```js
    if (leftSpouseXref) {
        nodes.push({
            xref: leftSpouseXref,
            x: leftSpouseX,
            y: 0,
            generation: 0,
            role: 'spouse',
            isFocusSpouse: true,
        });
```

**Do NOT** add the flag to:
- Co-spouse emission (~line 231, `nodes.push({ xref: coXref, ..., role: 'spouse' })`) — those are co-marriage partners of the focus's spouse, not the focus's spouse.
- Sibling-spouse emission (~line 178 and ~line 304) — those are spouses of the focus's siblings.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/viz_layout.test.js -t "focus spouse parent expansion"`

Expected: PASS (both test cases).

- [ ] **Step 5: Run the full JS test suite to verify no regressions**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/`

Expected: all tests pass. The added property is additive, so existing role-based checks are unaffected.

- [ ] **Step 6: Commit**

```bash
git add js/viz_layout.js tests/js/viz_layout.test.js
git commit -m "feat(viz): tag focus-spouse nodes with isFocusSpouse flag"
```

---

### Task 2: Failing test — spouse in `expandedNodes` places spouse's parents above

**Files:**
- Test: `tests/js/viz_layout.test.js` (extend the `describe` block added in Task 1)

- [ ] **Step 1: Write the failing test**

Inside the same `describe('computeLayout — focus spouse parent expansion', ...)` block, add:

```js
    it('places spouse parents at y=-ROW_HEIGHT when spouse xref is in expandedAncestors', () => {
        const expanded = new Set(['@SPOUSE@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());
        const spDad = nodes.find(n => n.xref === '@SPDAD@');
        const spMom = nodes.find(n => n.xref === '@SPMOM@');
        expect(spDad).toBeDefined();
        expect(spMom).toBeDefined();
        expect(spDad.y).toBe(-ROW_HEIGHT);
        expect(spMom.y).toBe(-ROW_HEIGHT);
        expect(spDad.role).toBe('ancestor');
        expect(spMom.role).toBe('ancestor');
    });

    it('does NOT place spouse parents when spouse xref is NOT in expandedAncestors', () => {
        const { nodes } = computeLayout('@FOCUS@', new Set(), new Set());
        expect(nodes.find(n => n.xref === '@SPDAD@')).toBeUndefined();
        expect(nodes.find(n => n.xref === '@SPMOM@')).toBeUndefined();
    });
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/viz_layout.test.js -t "places spouse parents"`

Expected: FAIL — first test fails because `@SPDAD@` is not found (spouse's parents are never placed today).

- [ ] **Step 3: Implement the minimal code to make the test pass**

In `js/viz_layout.js`, after the right-spouse emission loop and after the left-spouse emission block, add calls to the existing ancestor-placement helpers for each focus spouse. The cleanest place is immediately after each `nodes.push({ ..., isFocusSpouse: true })` added in Task 1.

Right-side spouse — inside the `rightSpouseXrefs.forEach` loop, after the node push and its `edges.push({ type: 'marriage', ... })` (after ~line 215):

```js
        // Spouse's ancestors (if expanded). The spouse is treated as a y=0
        // anchor identical to the focus: _placeAncestors short-circuits when
        // the xref is not in expandedAncestors, so this is a no-op by default.
        _placeAncestorSiblings(spouseXref, thisSpouseX, 0, expandedSiblingsXrefs, effectiveExpandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
        _placeAncestors(spouseXref, thisSpouseX, 0, 0, effectiveExpandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
```

Place this block INSIDE the `rightSpouseXrefs.forEach((spouseXref, si) => { ... })`, AFTER the `edges.push({ x1: edgeX1, ..., type: 'marriage' })` block and BEFORE the co-spouse `if (si === 0)` block.

Left-side spouse — inside `if (leftSpouseXref) { ... }` after the marriage edge push (after ~line 274):

```js
        _placeAncestorSiblings(leftSpouseXref, leftSpouseX, 0, expandedSiblingsXrefs, effectiveExpandedAncestors, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
        _placeAncestors(leftSpouseXref, leftSpouseX, 0, 0, effectiveExpandedAncestors, expandedSiblingsXrefs, expandedChildrenPersons, nodes, edges, visibleSpouseFams, focusXref);
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/viz_layout.test.js -t "places spouse parents"`

Expected: PASS (both test cases).

- [ ] **Step 5: Run the full JS test suite to verify no regressions**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add js/viz_layout.js tests/js/viz_layout.test.js
git commit -m "feat(viz): place focus-spouse ancestors when spouse is expanded"
```

---

### Task 3: Failing test — spouse's grandparents placed when spouse's parent is recursively expanded

**Files:**
- Test: `tests/js/viz_layout.test.js` (extend the same `describe` block)

- [ ] **Step 1: Write the failing test**

Add to the same `describe` block:

```js
    it('recursively places spouse grandparents when spouse father is also expanded', () => {
        // Extend the fixture with grandparents on the spouse side.
        global.PEOPLE['@SPGRANDPA@'] = { birth_year: 1705 };
        global.PEOPLE['@SPGRANDMA@'] = { birth_year: 1710 };
        global.PARENTS['@SPDAD@'] = ['@SPGRANDPA@', '@SPGRANDMA@'];

        const expanded = new Set(['@SPOUSE@', '@SPDAD@']);
        const { nodes } = computeLayout('@FOCUS@', expanded, new Set());

        const gpa = nodes.find(n => n.xref === '@SPGRANDPA@');
        const gma = nodes.find(n => n.xref === '@SPGRANDMA@');
        expect(gpa).toBeDefined();
        expect(gma).toBeDefined();
        expect(gpa.y).toBe(-2 * ROW_HEIGHT);
        expect(gma.y).toBe(-2 * ROW_HEIGHT);
        expect(gpa.role).toBe('ancestor');
    });
```

- [ ] **Step 2: Run the test to verify it fails or passes**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/viz_layout.test.js -t "recursively places spouse grandparents"`

Expected: PASS — `_placeAncestors` is already recursive, so Task 2's implementation should already cover this. The test guards against future regression. If it fails, re-check Task 2's `_placeAncestors` call.

- [ ] **Step 3: Commit**

```bash
git add tests/js/viz_layout.test.js
git commit -m "test(viz): cover recursive spouse-ancestor expansion"
```

---

### Task 4: Failing test — render chevron gate includes `isFocusSpouse`

**Files:**
- Test: `tests/js/viz_render.test.js` (append a new `describe` or `it` block at the end)

- [ ] **Step 1: Read the current render-test structure to match conventions**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && head -50 tests/js/viz_render.test.js`

Note the top-of-file setup (globals, imports). Mirror it in the new test.

- [ ] **Step 2: Write the failing test**

Append to `tests/js/viz_render.test.js`:

```js
describe('_renderNode — parent-expand chevron on focus spouse', () => {
    it('chevron gate includes node.isFocusSpouse', () => {
        // Source-level contract check: the render gate must accept a focus
        // spouse, not just a role === 'ancestor' node.
        const renderSrc = require('fs').readFileSync(
            require.resolve('../../js/viz_render.js'),
            'utf8',
        );
        expect(renderSrc).toMatch(/isAncestor\s*\|\|\s*node\.isFocusSpouse/);
    });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/viz_render.test.js -t "parent-expand chevron on focus spouse"`

Expected: FAIL — the regex does not match; today's code only checks `isAncestor`.

- [ ] **Step 4: Implement the minimal code to make the test pass**

In `js/viz_render.js`, change the gate at line 301:

From:
```js
    // Expand button on ancestor nodes — floats above the top edge with a small gap.
    // Only rendered when the ancestor has parents. Two visual states:
    //   can expand   → green up-chevron (click to reveal parents)
    //   can collapse → blue down-chevron (click to hide parents)
    if (isAncestor) {
        const parents = PARENTS[node.xref] || [null, null];
        const hasParents = parents.some(p => p !== null);
        if (hasParents) {
```

To:
```js
    // Expand button on ancestor nodes (and on the focus person's spouse) —
    // floats above the top edge with a small gap. Only rendered when the
    // person has parents. Two visual states:
    //   can expand   → green up-chevron (click to reveal parents)
    //   can collapse → blue down-chevron (click to hide parents)
    if (isAncestor || node.isFocusSpouse) {
        const parents = PARENTS[node.xref] || [null, null];
        const hasParents = parents.some(p => p !== null);
        if (hasParents) {
```

Everything inside the block (chevron geometry, click handler wired to `onExpandClick(node.xref)`) stays the same — the click handler already toggles `expandedNodes` via `setState`, which is exactly what we want.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/viz_render.test.js -t "parent-expand chevron on focus spouse"`

Expected: PASS.

- [ ] **Step 6: Run the full JS test suite to verify no regressions**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && npx vitest run tests/js/`

Expected: all tests pass.

- [ ] **Step 7: Run the Python test suite that touches the HTML template**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && GED_FILE=../smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged pytest tests/test_viz_ancestors_rendering.py -q`

Expected: all tests pass. (These tests are HTML/Python-contract; they should be unaffected but verify.)

- [ ] **Step 8: Commit**

```bash
git add js/viz_render.js tests/js/viz_render.test.js
git commit -m "feat(viz): render parent-expand chevron on focus spouse"
```

---

### Task 5: Manual browser verification

**Files:** none (manual check).

- [ ] **Step 1: Start the dev server**

Run: `cd /Users/sashaperigo/claude-code/gedcom-tools && GED_FILE=../smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged python serve_viz.py`

Browse to http://localhost:8080/viz.html and navigate to a focus person whose spouse has parents in the tree (e.g. the Maria Borg ↔ Emanuele Bonnici example from the original screenshot — use the search box if needed).

- [ ] **Step 2: Verify chevron visibility**

Expected:
- A small up-chevron circle (green) sits just above the spouse pill's top edge.
- No chevron appears above the spouse if the GEDCOM has no parents recorded for that spouse.
- No chevron appears above sibling-spouses (spouses of focus's siblings).

- [ ] **Step 3: Verify expansion behavior**

Click the chevron on the spouse. Expected:
- Spouse's parents appear at the same y-row as the focus's parents (if any), above the spouse pill.
- The chevron flips to a down-chevron (blue, `btn-collapse` class) indicating collapse.
- If the spouse's parent also has parents in the GEDCOM, clicking that new ancestor's chevron recursively expands to grandparents — same behavior as focus-side ancestors.

- [ ] **Step 4: Verify collapse behavior**

Click the now-blue chevron on the spouse. Expected:
- Spouse's parents (and any deeper ancestors) disappear.
- Chevron flips back to green up-chevron.

- [ ] **Step 5: Verify URL state round-trip**

After expanding, copy the URL and paste into a new tab. Expected: the page reloads with the spouse's parents still expanded (because `expandedNodes` is serialized into the URL state by existing infra — no code changes here).

- [ ] **Step 6: Note any collision**

If the spouse's parents visually overlap with the focus's right parent (e.g. Angela on top of Emanuele's father), note it but do not attempt a fix in this plan. Per the design spec, collision handling is deferred.

- [ ] **Step 7: Commit completion doc if the milestone is coherent**

Per this repo's session protocol, write a short completion note to `.claude/completions/2026-04-22-spouse-parent-expand.md` summarizing what shipped and any manual-test observations (including whether collision appeared).

```bash
git add .claude/completions/2026-04-22-spouse-parent-expand.md
git commit -m "docs: completion note for spouse parent-expand chevron"
```

---

## Out of scope (do not implement)

- `role: 'spouse_sibling'`, `role: 'ancestor_sibling_spouse'`, and co-spouse chevrons.
- Collision handling between focus-parents subtree and spouse-parents subtree — deferred per spec.
- Changes to `viz_primary_spouse.js`.

## Risks / things to watch for during implementation

- `_placeAncestors` emits a child-umbrella via `_emitChildUmbrella(xref, x, y, anchorY, ...)` at `viz_layout.js:852`. For the spouse (y=0), this will emit an edge from the spouse's parents' marriage-line down to the spouse pill's top. That's the desired behavior.
- `_emitChildUmbrella` looks for siblings of `xref` at the same y. The focus-spouse's siblings (role `'spouse_sibling'`) only exist at y=0 when `expandedSiblingsXrefs.has(spouseXref)`. If they are present, the umbrella will include them — visually reasonable (parents umbrella spans all their children at that row).
- If the spouse has only one parent in the GEDCOM, `_placeAncestors` takes the single-parent branch and places the single parent centered over the spouse — same behavior as focus-side single-parent case. No special handling needed.
