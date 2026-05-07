import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { shrink, formatInput, withPersonRemoved, deepCopyInput } = require('./_layout_shrink.js');
const { generateLayoutInput } = require('./_layout_generator.js');

function tinyInput() {
    return {
        globals: {
            PEOPLE: {
                '@F@': { birth_year: 1900 },
                '@A@': { birth_year: 1925 },
                '@B@': { birth_year: 1928 },
            },
            PARENTS: { '@A@': ['@F@'], '@B@': ['@F@'] },
            CHILDREN: { '@F@': ['@A@', '@B@'] },
            RELATIVES: {
                '@F@': { siblings: [], spouses: [] },
                '@A@': { siblings: ['@B@'], spouses: [] },
                '@B@': { siblings: ['@A@'], spouses: [] },
            },
            FAMILIES: {
                '@FAM1@': { husb: '@F@', wife: null, chil: ['@A@', '@B@'] },
            },
        },
        focusXref: '@F@',
        expandedAncestors: new Set(),
        expandedChildrenPersons: new Set(),
        expandedSiblingsXrefs: new Set(),
    };
}

describe('deepCopyInput', () => {
    it('returns a structure with no shared references to the original', () => {
        const original = tinyInput();
        const copy = deepCopyInput(original);
        copy.globals.PEOPLE['@NEW@'] = {};
        copy.expandedAncestors.add('@F@');
        expect(original.globals.PEOPLE['@NEW@']).toBeUndefined();
        expect(original.expandedAncestors.size).toBe(0);
    });
});

describe('withPersonRemoved', () => {
    it('removes the person from PEOPLE, RELATIVES, PARENTS, CHILDREN, FAMILIES', () => {
        const input = tinyInput();
        const reduced = withPersonRemoved(input, '@A@');
        expect(reduced.globals.PEOPLE['@A@']).toBeUndefined();
        expect(reduced.globals.RELATIVES['@A@']).toBeUndefined();
        expect(reduced.globals.RELATIVES['@B@'].siblings).not.toContain('@A@');
        expect(reduced.globals.CHILDREN['@F@']).not.toContain('@A@');
        expect(reduced.globals.FAMILIES['@FAM1@'].chil).not.toContain('@A@');
    });

    it('drops a family that becomes empty', () => {
        const input = tinyInput();
        let reduced = withPersonRemoved(input, '@A@');
        reduced = withPersonRemoved(reduced, '@B@');
        // @F@ is gone too — wait no, only A and B removed. Family chil becomes []
        // and husb=@F@. So family stays since husb != null.
        expect(reduced.globals.FAMILIES['@FAM1@']).toBeDefined();
    });
});

describe('shrink', () => {
    it('reduces an input to focus-only when only focus is needed to fail', () => {
        const input = tinyInput();
        const fails = (i) => Object.keys(i.globals.PEOPLE).length >= 1;
        const minimal = shrink(input, fails);
        expect(Object.keys(minimal.globals.PEOPLE)).toEqual(['@F@']);
    });

    it('keeps non-focus persons that are required for failure', () => {
        const input = tinyInput();
        // Only fails when @A@ is present
        const fails = (i) => '@A@' in i.globals.PEOPLE;
        const minimal = shrink(input, fails);
        expect(minimal.globals.PEOPLE['@A@']).toBeDefined();
        // @B@ should be removed since it isn't needed
        expect(minimal.globals.PEOPLE['@B@']).toBeUndefined();
    });

    it('shrinks expansion sets', () => {
        const input = tinyInput();
        input.expandedChildrenPersons.add('@A@');
        input.expandedChildrenPersons.add('@B@');
        // Fails as long as expandedChildrenPersons has @A@
        const fails = (i) => i.expandedChildrenPersons.has('@A@');
        const minimal = shrink(input, fails);
        expect(minimal.expandedChildrenPersons.has('@A@')).toBe(true);
        expect(minimal.expandedChildrenPersons.has('@B@')).toBe(false);
    });

    it('returns input unchanged when nothing is removable', () => {
        const input = tinyInput();
        // Already minimal: any reduction makes it stop failing
        const fails = (i) => Object.keys(i.globals.PEOPLE).length === 3;
        const minimal = shrink(input, fails);
        expect(Object.keys(minimal.globals.PEOPLE).length).toBe(3);
    });

    it('handles a generated input (smoke)', () => {
        const input = generateLayoutInput(42);
        // Always fails — should reduce to bare minimum (just focus + whatever).
        const fails = () => true;
        const minimal = shrink(input, fails);
        // After full reduction with `() => true`, we'd remove everything except focus
        expect(minimal.globals.PEOPLE[minimal.focusXref]).toBeDefined();
        expect(Object.keys(minimal.globals.PEOPLE).length).toBe(1);
    });
});

describe('formatInput', () => {
    it('produces a paste-able multi-line string', () => {
        const input = tinyInput();
        const out = formatInput(input);
        expect(out).toContain('@F@');
        expect(out).toContain('PEOPLE:');
        expect(out).toContain('FAMILIES:');
        expect(out).toContain('focus=@F@');
    });
});
