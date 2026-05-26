import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { extractYear } = require('../../js/viz_advanced_search.js');

describe('extractYear', () => {
    it('returns the year for a bare year', () => {
        expect(extractYear('1892')).toBe(1892);
    });
    it('finds year in "15 Mar 1892"', () => {
        expect(extractYear('15 Mar 1892')).toBe(1892);
    });
    it('handles ABT prefix', () => {
        expect(extractYear('ABT 1892')).toBe(1892);
    });
    it('handles BEF prefix', () => {
        expect(extractYear('BEF 1900')).toBe(1900);
    });
    it('handles BET ... AND ... — returns first year', () => {
        expect(extractYear('BET 1880 AND 1890')).toBe(1880);
    });
    it('returns null for empty / null / undefined', () => {
        expect(extractYear('')).toBe(null);
        expect(extractYear(null)).toBe(null);
        expect(extractYear(undefined)).toBe(null);
    });
    it('returns null when no year present', () => {
        expect(extractYear('unknown')).toBe(null);
    });
});

const { buildRelIndex } = require('../../js/viz_advanced_search.js');

describe('buildRelIndex', () => {
    const FAMILIES = {
        F1: { husb: 'I1', wife: 'I2', chil: ['I3', 'I4'] },
        F2: { husb: 'I3', wife: 'I5', chil: ['I6'] },
        F3: { husb: 'I1', wife: 'I7', chil: ['I8'] },  // I1 has second marriage
    };
    const PARENTS = {
        I3: { father: 'I1', mother: 'I2' },
        I4: { father: 'I1', mother: 'I2' },
        I6: { father: 'I3', mother: 'I5' },
        I8: { father: 'I1', mother: 'I7' },
    };

    const idx = buildRelIndex(FAMILIES, PARENTS);

    it('lists all spouses (including from second marriage)', () => {
        expect(new Set(idx.spousesOf.I1)).toEqual(new Set(['I2', 'I7']));
        expect(idx.spousesOf.I3).toEqual(['I5']);
    });
    it('lists all children across families', () => {
        expect(new Set(idx.childrenOf.I1)).toEqual(new Set(['I3', 'I4', 'I8']));
    });
    it('lists siblings (same FAMC, excluding self)', () => {
        expect(idx.siblingsOf.I3).toEqual(['I4']);
        expect(idx.siblingsOf.I4).toEqual(['I3']);
    });
    it('excludes half-siblings (different FAMC) from siblingsOf', () => {
        // I8 is a half-sibling of I3 (same father, different mother → different FAMC)
        expect(idx.siblingsOf.I8 || []).toEqual([]);
    });
    it('returns empty arrays for unknown people', () => {
        expect(idx.spousesOf.I99 || []).toEqual([]);
    });
});
