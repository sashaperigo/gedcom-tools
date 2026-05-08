import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { generateLayoutInput, validateInput, mulberry32 } = require('./_layout_generator.js');

describe('mulberry32', () => {
    it('produces the same sequence for the same seed', () => {
        const a = mulberry32(42);
        const b = mulberry32(42);
        const aSeq = Array.from({ length: 5 }, () => a());
        const bSeq = Array.from({ length: 5 }, () => b());
        expect(aSeq).toEqual(bSeq);
    });

    it('produces different sequences for different seeds', () => {
        const a = mulberry32(1);
        const b = mulberry32(2);
        expect(a()).not.toEqual(b());
    });

    it('returns numbers in [0, 1)', () => {
        const r = mulberry32(7);
        for (let i = 0; i < 100; i++) {
            const v = r();
            expect(v).toBeGreaterThanOrEqual(0);
            expect(v).toBeLessThan(1);
        }
    });
});

describe('generateLayoutInput — determinism', () => {
    it('same seed → identical output', () => {
        const a = generateLayoutInput(123);
        const b = generateLayoutInput(123);
        expect(Object.keys(a.globals.PEOPLE).sort()).toEqual(Object.keys(b.globals.PEOPLE).sort());
        expect(a.focusXref).toEqual(b.focusXref);
        expect([...a.expandedAncestors].sort()).toEqual([...b.expandedAncestors].sort());
        expect([...a.expandedChildrenPersons].sort()).toEqual([...b.expandedChildrenPersons].sort());
        expect([...a.expandedSiblingsXrefs].sort()).toEqual([...b.expandedSiblingsXrefs].sort());
    });

    it('different seeds produce different outputs (smoke)', () => {
        const a = generateLayoutInput(1);
        const b = generateLayoutInput(2);
        // Not strictly required but extremely likely
        const sameSize = Object.keys(a.globals.PEOPLE).length === Object.keys(b.globals.PEOPLE).length;
        const sameAncestors = [...a.expandedAncestors].join(',') === [...b.expandedAncestors].join(',');
        expect(sameSize && sameAncestors).toBe(false);
    });
});

describe('generateLayoutInput — internal consistency', () => {
    // Run validateInput across many seeds; any failure exposes a generator bug.
    for (const seed of [1, 2, 3, 5, 8, 13, 21, 34, 42, 100, 200, 500, 1000]) {
        it(`seed=${seed} produces internally consistent globals`, () => {
            const input = generateLayoutInput(seed);
            const err = validateInput(input);
            expect(err).toBeNull();
        });
    }
});

describe('generateLayoutInput — invariants on output structure', () => {
    it('focusXref is in PEOPLE', () => {
        for (const seed of [1, 7, 99]) {
            const input = generateLayoutInput(seed);
            expect(input.globals.PEOPLE[input.focusXref]).toBeDefined();
        }
    });

    it('expansion sets are subsets of PEOPLE keys', () => {
        for (const seed of [1, 50, 200]) {
            const input = generateLayoutInput(seed);
            const all = new Set(Object.keys(input.globals.PEOPLE));
            for (const x of input.expandedAncestors) expect(all.has(x)).toBe(true);
            for (const x of input.expandedChildrenPersons) expect(all.has(x)).toBe(true);
            for (const x of input.expandedSiblingsXrefs) expect(all.has(x)).toBe(true);
        }
    });

    it('respects maxTotalPersons cap', () => {
        const input = generateLayoutInput(42, { maxTotalPersons: 10 });
        expect(Object.keys(input.globals.PEOPLE).length).toBeLessThanOrEqual(10);
    });

    it('siblings relation is symmetric', () => {
        const input = generateLayoutInput(17);
        for (const [xref, rel] of Object.entries(input.globals.RELATIVES)) {
            for (const sib of rel.siblings) {
                expect(input.globals.RELATIVES[sib].siblings).toContain(xref);
            }
        }
    });
});

// Helpers shared across scenario tests.
function ancestorsOf(xref, PARENTS) {
    const out = new Set();
    const stack = [xref];
    while (stack.length) {
        const cur = stack.pop();
        for (const p of PARENTS[cur] || []) {
            if (!out.has(p)) {
                out.add(p);
                stack.push(p);
            }
        }
    }
    return out;
}

function siblingsOf(xref, RELATIVES) {
    return RELATIVES[xref]?.siblings || [];
}

// Scenario templates bias generateLayoutInput toward specific genealogical
// configurations that historically surfaced layout bugs. Each scenario must
// produce a tree satisfying its defining structural property across many seeds.
// See docs/learnings/viz-expand-layout-bugs.md.
describe('generateLayoutInput — scenario: focus_parent_sibling_with_kids', () => {
    // Property: focus has at least one parent, that parent has at least one
    // sibling (= focus's aunt/uncle), and that aunt/uncle is in
    // expandedChildrenPersons. Exercises Phase 1 ancestor-row sibling packing
    // when the sibling has expanded descendants — the case _focusChildrenExtents
    // does not cover.
    for (const seed of [1, 2, 3, 5, 10, 17, 42, 99, 200, 500]) {
        it(`seed=${seed} produces a focus parent's sibling with expanded kids`, () => {
            const input = generateLayoutInput(seed, { scenario: 'focus_parent_sibling_with_kids' });
            const { PARENTS, CHILDREN, RELATIVES } = input.globals;
            const focusParents = PARENTS[input.focusXref] || [];
            expect(focusParents.length).toBeGreaterThan(0);
            const auntsUncles = focusParents.flatMap(p => siblingsOf(p, RELATIVES));
            expect(auntsUncles.length).toBeGreaterThan(0);
            const expandedAuntUncle = auntsUncles.find(au =>
                input.expandedChildrenPersons.has(au) &&
                (CHILDREN[au] || []).length > 0
            );
            expect(expandedAuntUncle).toBeDefined();
        });
    }
});

describe('generateLayoutInput — scenario: focus_sibling_with_grandkids', () => {
    // Property: focus has at least one sibling, that sibling is in
    // expandedChildrenPersons, AND at least one of the sibling's children is
    // also in expandedChildrenPersons. Exercises Phase 1 ↔ Phase 3 cascade
    // where the sibling's subtree depth exceeds focus's.
    for (const seed of [1, 2, 3, 5, 10, 17, 42, 99, 200, 500]) {
        it(`seed=${seed} produces a focus sibling with expanded grandkids`, () => {
            const input = generateLayoutInput(seed, { scenario: 'focus_sibling_with_grandkids' });
            const { CHILDREN, RELATIVES } = input.globals;
            const focusSibs = siblingsOf(input.focusXref, RELATIVES);
            expect(focusSibs.length).toBeGreaterThan(0);
            const expandedSib = focusSibs.find(s =>
                input.expandedChildrenPersons.has(s) &&
                (CHILDREN[s] || []).some(c => input.expandedChildrenPersons.has(c))
            );
            expect(expandedSib).toBeDefined();
        });
    }
});

describe('generateLayoutInput — scenario: adjacent_siblings_both_expanded', () => {
    // Property: focus has at least two siblings, both in expandedChildrenPersons
    // with at least one child each. Exercises Phase 1 sibling packing where
    // *adjacent* siblings on the focus row both have descendant clusters that
    // must not collide.
    for (const seed of [1, 2, 3, 5, 10, 17, 42, 99, 200, 500]) {
        it(`seed=${seed} produces two adjacent siblings both with expanded kids`, () => {
            const input = generateLayoutInput(seed, { scenario: 'adjacent_siblings_both_expanded' });
            const { CHILDREN, RELATIVES } = input.globals;
            const focusSibs = siblingsOf(input.focusXref, RELATIVES);
            const expandedSibs = focusSibs.filter(s =>
                input.expandedChildrenPersons.has(s) && (CHILDREN[s] || []).length > 0
            );
            expect(expandedSibs.length).toBeGreaterThanOrEqual(2);
        });
    }
});

describe('generateLayoutInput — scenario: multi_gen_ancestor_siblings', () => {
    // Property: at least one ancestor at generation >= 2 (grandparent or higher)
    // has expanded siblings (force-expanded via expandedSiblingsXrefs) AND at
    // least one of those ancestor-row siblings has expanded children. Exercises
    // ancestor-side descendant clusters interacting with deep-row packing.
    for (const seed of [1, 2, 3, 5, 10, 17, 42, 99, 200, 500]) {
        it(`seed=${seed} produces a deep ancestor with expanded sibling+kids`, () => {
            const input = generateLayoutInput(seed, { scenario: 'multi_gen_ancestor_siblings' });
            const { PARENTS, CHILDREN, RELATIVES } = input.globals;
            // Find ancestors at generation >= 2 (focus → parent = gen 1; gen 2 = grandparent)
            const focusParents = PARENTS[input.focusXref] || [];
            const grandparents = new Set();
            for (const p of focusParents) {
                for (const gp of PARENTS[p] || []) grandparents.add(gp);
            }
            expect(grandparents.size).toBeGreaterThan(0);
            const matched = [...grandparents].some(gp => {
                if (!input.expandedSiblingsXrefs.has(gp)) return false;
                const sibs = siblingsOf(gp, RELATIVES);
                return sibs.some(s =>
                    input.expandedChildrenPersons.has(s) && (CHILDREN[s] || []).length > 0
                );
            });
            expect(matched).toBe(true);
        });
    }
});

// Internal-consistency check: every scenario template produces a globals
// structure that passes validateInput, just like the random generator.
describe('generateLayoutInput — scenarios produce consistent globals', () => {
    const scenarios = [
        'focus_parent_sibling_with_kids',
        'focus_sibling_with_grandkids',
        'adjacent_siblings_both_expanded',
        'multi_gen_ancestor_siblings',
    ];
    for (const scenario of scenarios) {
        for (const seed of [1, 7, 42]) {
            it(`scenario=${scenario} seed=${seed} consistent`, () => {
                const input = generateLayoutInput(seed, { scenario });
                const err = validateInput(input);
                expect(err).toBeNull();
            });
        }
    }
});

// Same seed + same scenario must be deterministic.
describe('generateLayoutInput — scenarios are deterministic', () => {
    const scenarios = [
        'focus_parent_sibling_with_kids',
        'focus_sibling_with_grandkids',
        'adjacent_siblings_both_expanded',
        'multi_gen_ancestor_siblings',
    ];
    for (const scenario of scenarios) {
        it(`scenario=${scenario} same seed → identical output`, () => {
            const a = generateLayoutInput(99, { scenario });
            const b = generateLayoutInput(99, { scenario });
            expect(Object.keys(a.globals.PEOPLE).sort()).toEqual(Object.keys(b.globals.PEOPLE).sort());
            expect(a.focusXref).toEqual(b.focusXref);
            expect([...a.expandedChildrenPersons].sort()).toEqual([...b.expandedChildrenPersons].sort());
            expect([...a.expandedSiblingsXrefs].sort()).toEqual([...b.expandedSiblingsXrefs].sort());
        });
    }
});
