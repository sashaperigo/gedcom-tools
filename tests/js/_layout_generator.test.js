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
