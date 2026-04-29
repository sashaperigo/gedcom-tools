import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);

function loadModule({ allPeople = [], parents = {}, children = {}, families = {} } = {}) {
    vi.resetModules();
    const modPath = require.resolve('../../js/viz_relative_events.js');
    delete require.cache[modPath];
    global.ALL_PEOPLE = allPeople;
    global.ALL_PEOPLE_BY_ID = Object.fromEntries(allPeople.map(p => [p.id, p]));
    global.PARENTS = parents;
    global.CHILDREN = children;
    global.FAMILIES = families;
    return require('../../js/viz_relative_events.js');
}

beforeEach(() => {
    delete global.ALL_PEOPLE;
    delete global.ALL_PEOPLE_BY_ID;
    delete global.PARENTS;
    delete global.CHILDREN;
    delete global.FAMILIES;
});

describe('_role — child', () => {
    it('returns "son" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'child')).toBe('son');
    });
    it('returns "daughter" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'child')).toBe('daughter');
    });
    it('returns "child" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'child')).toBe('child');
    });
});

describe('_role — spouse', () => {
    it('returns "husband" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'spouse')).toBe('husband');
    });
    it('returns "wife" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'spouse')).toBe('wife');
    });
    it('returns "spouse" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'spouse')).toBe('spouse');
    });
});

describe('_role — parent', () => {
    it('returns "father" when sex is M', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'M' }, 'parent')).toBe('father');
    });
    it('returns "mother" when sex is F', () => {
        const mod = loadModule();
        expect(mod._role({ sex: 'F' }, 'parent')).toBe('mother');
    });
    it('returns "parent" when sex is empty', () => {
        const mod = loadModule();
        expect(mod._role({ sex: '' }, 'parent')).toBe('parent');
    });
});

describe('_lifetimeBounds', () => {
    it('returns null when birth_year is missing', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: '', death_year: '', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toBe(null);
    });
    it('returns {lo: birth, hi: death} when both known', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: 1880, death_year: 1945, sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1945 });
    });
    it('caps at birth_year+100 when death year is missing', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: 1880, death_year: '', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1980 });
    });
    it('handles string years from JSON payload', () => {
        const mod = loadModule({
            allPeople: [{ id: '@I1@', name: 'X', birth_year: '1880', death_year: '1945', sex: '' }],
        });
        expect(mod._lifetimeBounds('@I1@')).toEqual({ lo: 1880, hi: 1945 });
    });
    it('returns null when xref not found in ALL_PEOPLE_BY_ID', () => {
        const mod = loadModule();
        expect(mod._lifetimeBounds('@IX@')).toBe(null);
    });
});
