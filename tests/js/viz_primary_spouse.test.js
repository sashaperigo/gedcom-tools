import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);

function loadModule({ people = {}, families = {}, parents = {} } = {}) {
    vi.resetModules();
    const modPath = require.resolve('../../js/viz_primary_spouse.js');
    delete require.cache[modPath];
    global.PEOPLE = people;
    global.FAMILIES = families;
    global.PARENTS = parents;
    return require('../../js/viz_primary_spouse.js');
}

beforeEach(() => {
    delete global.PEOPLE;
    delete global.FAMILIES;
    delete global.PARENTS;
});

// Test xrefs:
//   @I1@ = focus
//   @I2@ = grandfather (person being resolved)
//   @I3@ = grandmother (lineage spouse)
//   @I4@ = non-lineage spouse
//   @I5@ = father (lineage child of grandfather)
//   @I6@ = half-uncle (child of non-lineage FAM)

describe('primaryFamFor — Rule 0: focusXref is other parent', () => {
    it('returns the FAM where focusXref is the other parent even when another FAM has earlier marr_year', () => {
        // Michele has two FAMs: @F1@ (with Josephina = focus) and @F2@ (with Maria Elena).
        // @F2@ has an earlier marriage year, but Rule 0 should return @F1@ because focusXref
        // (Josephina) is the other parent in exactly one FAM.
        const mod = loadModule({
            families: {
                '@F1@': { husb: '@Michele@', wife: '@Josephina@', chil: [], marr_year: 1920 },
                '@F2@': { husb: '@Michele@', wife: '@MariaElena@', chil: [], marr_year: 1910 },
            },
        });
        expect(mod.primaryFamFor('@Michele@', '@Josephina@')).toBe('@F1@');
    });

    it('falls through to Rule 1 when focusXref appears in more than one FAM', () => {
        // focusXref is other parent in both FAMs — Rule 0 cannot resolve; falls to Rule 1.
        const mod = loadModule({
            families: {
                '@F1@': { husb: '@I1@', wife: '@Focus@', chil: ['@Child@'], marr_year: 1940 },
                '@F2@': { husb: '@I1@', wife: '@Focus@', chil: [], marr_year: 1920 },
            },
            parents: {
                '@I99@': ['@Child@', null],
                '@Child@': ['@I1@', '@Focus@'],
            },
        });
        // Rule 0 sees focusXref in both FAMs → no Rule 0 decision.
        // Rule 1 (lineage) is not applicable here (no lineage child path from focusXref to @I99@).
        // Falls to Rule 2 (earliest marr_year) → @F2@.
        expect(mod.primaryFamFor('@I1@', '@Focus@')).toBe('@F2@');
    });

    it('Rule 0 takes precedence over Rule 1 (lineage)', () => {
        // @I2@ has two FAMs: @F1@ (with @Focus@, no lineage child) and @F2@ (lineage FAM).
        // Normally Rule 1 would pick @F2@, but Rule 0 fires first.
        const mod = loadModule({
            families: {
                '@F1@': { husb: '@I2@', wife: '@Focus@', chil: [], marr_year: 1950 },
                '@F2@': { husb: '@I2@', wife: '@I3@', chil: ['@I5@'], marr_year: 1940 },
            },
            parents: {
                '@Focus@': ['@I5@', null],
                '@I5@': ['@I2@', '@I3@'],
            },
        });
        expect(mod.primaryFamFor('@I2@', '@Focus@')).toBe('@F1@');
    });
});

describe('primaryFamFor — lineage rule', () => {
    it('picks the FAM containing the lineage child when ancestor has two FAMs', () => {
        const mod = loadModule({
            people: {
                '@I1@': {},
                '@I2@': {},
                '@I3@': {},
                '@I4@': {},
                '@I5@': {},
                '@I6@': {},
            },
            families: {
                '@F1@': { husb: '@I2@', wife: '@I3@', chil: ['@I5@'], marr_year: 1950 },
                '@F2@': { husb: '@I2@', wife: '@I4@', chil: ['@I6@'], marr_year: 1940 },
            },
            parents: {
                '@I1@': ['@I5@', null],
                '@I5@': ['@I2@', '@I3@'],
            },
        });
        expect(mod.primaryFamFor('@I2@', '@I1@')).toBe('@F1@');
    });
});

describe('primaryFamFor — earliest marriage year', () => {
    it('picks FAM with smaller marr_year when lineage rule does not apply', () => {
        const mod = loadModule({
            families: {
                '@F1@': { husb: '@I1@', wife: '@I2@', chil: [], marr_year: 1935 },
                '@F2@': { husb: '@I1@', wife: '@I3@', chil: [], marr_year: 1920 },
            },
        });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe('@F2@');
    });
});

describe('primaryFamFor — earliest other-parent birth year', () => {
    it('uses other-parent birth year when marriage years are tied', () => {
        const mod = loadModule({
            people: {
                '@I2@': { birth_year: 1910 },
                '@I3@': { birth_year: 1900 },
            },
            families: {
                '@F1@': { husb: '@I1@', wife: '@I2@', chil: [], marr_year: 1930 },
                '@F2@': { husb: '@I1@', wife: '@I3@', chil: [], marr_year: 1930 },
            },
        });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe('@F2@');
    });

    it('uses other-parent birth year when marriage years both missing', () => {
        const mod = loadModule({
            people: {
                '@I2@': { birth_year: 1910 },
                '@I3@': { birth_year: 1900 },
            },
            families: {
                '@F1@': { husb: '@I1@', wife: '@I2@', chil: [], marr_year: null },
                '@F2@': { husb: '@I1@', wife: '@I3@', chil: [], marr_year: null },
            },
        });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe('@F2@');
    });

    it('treats null spouse as Infinity birth year so named spouse wins', () => {
        const mod = loadModule({
            people: {
                '@I2@': { birth_year: 1900 },
            },
            families: {
                '@F1@': { husb: '@I1@', wife: '@I2@', chil: [], marr_year: null },
                '@F2@': { husb: '@I1@', wife: null, chil: [], marr_year: null },
            },
        });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe('@F1@');
    });
});

describe('primaryFamFor — numeric xref order fallback', () => {
    it('picks numerically smaller FAM xref when nothing else discriminates', () => {
        const mod = loadModule({
            families: {
                '@F12@': { husb: '@I1@', wife: null, chil: [], marr_year: null },
                '@F77@': { husb: '@I1@', wife: null, chil: [], marr_year: null },
            },
        });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe('@F12@');
    });

    it('compares numerically, not lexically (F9 beats F12)', () => {
        const mod = loadModule({
            families: {
                '@F9@': { husb: '@I1@', wife: null, chil: [], marr_year: null },
                '@F12@': { husb: '@I1@', wife: null, chil: [], marr_year: null },
            },
        });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe('@F9@');
    });
});

describe('primaryFamFor — combined priority order', () => {
    it('lineage wins over earlier marriage year', () => {
        const mod = loadModule({
            families: {
                '@F1@': { husb: '@I2@', wife: '@I3@', chil: ['@I5@'], marr_year: 1950 },
                '@F2@': { husb: '@I2@', wife: '@I4@', chil: [], marr_year: 1930 },
            },
            parents: {
                '@I1@': ['@I5@', null],
                '@I5@': ['@I2@', '@I3@'],
            },
        });
        expect(mod.primaryFamFor('@I2@', '@I1@')).toBe('@F1@');
    });

    it('earlier marriage year wins over earlier birth year', () => {
        const mod = loadModule({
            people: {
                '@I2@': { birth_year: 1910 },
                '@I3@': { birth_year: 1900 },
            },
            families: {
                '@F1@': { husb: '@I1@', wife: '@I2@', chil: [], marr_year: 1920 },
                '@F2@': { husb: '@I1@', wife: '@I3@', chil: [], marr_year: 1925 },
            },
        });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe('@F1@');
    });
});

describe('primaryFamFor — single FAM', () => {
    it('returns the only FAM', () => {
        const mod = loadModule({
            families: {
                '@F1@': { husb: '@I1@', wife: '@I2@', chil: [], marr_year: 1920 },
            },
        });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe('@F1@');
    });

    it('returns null for a person with no FAMs', () => {
        const mod = loadModule({ families: {} });
        expect(mod.primaryFamFor('@I1@', '@I99@')).toBe(null);
    });
});
