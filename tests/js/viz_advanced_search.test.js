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

const { eventSectionMatches } = require('../../js/viz_advanced_search.js');

function mkPerson(events) {
    return { id: 'I1', name: 'Test Person', events };
}

describe('eventSectionMatches — birth', () => {
    const p = mkPerson([{ tag: 'BIRT', date: '15 Mar 1892', place: 'Smyrna' }]);

    it('matches when place + year are in range', () => {
        const sec = { kind: 'birth', place: 'Smyrna', yearFrom: 1880, yearTo: 1900 };
        expect(eventSectionMatches(p, sec)).toBe(true);
    });
    it('matches with only yearFrom (open-ended upper)', () => {
        const sec = { kind: 'birth', place: '', yearFrom: 1880, yearTo: null };
        expect(eventSectionMatches(p, sec)).toBe(true);
    });
    it('matches with only yearTo (open-ended lower)', () => {
        const sec = { kind: 'birth', place: '', yearFrom: null, yearTo: 1900 };
        expect(eventSectionMatches(p, sec)).toBe(true);
    });
    it('matches when from === to (exact year)', () => {
        const sec = { kind: 'birth', place: '', yearFrom: 1892, yearTo: 1892 };
        expect(eventSectionMatches(p, sec)).toBe(true);
    });
    it('rejects when place mismatches', () => {
        const sec = { kind: 'birth', place: 'Athens', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(p, sec)).toBe(false);
    });
    it('rejects when year out of range', () => {
        const sec = { kind: 'birth', place: '', yearFrom: 1900, yearTo: 1920 };
        expect(eventSectionMatches(p, sec)).toBe(false);
    });
    it('matches accent-insensitively on place', () => {
        const px = mkPerson([{ tag: 'BIRT', date: '1892', place: 'Île-de-France' }]);
        const sec = { kind: 'birth', place: 'ile-de-france', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(px, sec)).toBe(true);
    });
    it('rejects person with no BIRT event when filter is set', () => {
        const px = mkPerson([{ tag: 'DEAT', date: '1900', place: '' }]);
        const sec = { kind: 'birth', place: 'Smyrna', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(px, sec)).toBe(false);
    });
});

describe('eventSectionMatches — death', () => {
    it('excludes person with no DEAT event when any filter is set', () => {
        const p = mkPerson([{ tag: 'BIRT', date: '1892', place: 'Smyrna' }]);
        const sec = { kind: 'death', place: 'Athens', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(p, sec)).toBe(false);
    });
    it('matches DEAT event', () => {
        const p = mkPerson([{ tag: 'DEAT', date: '1965', place: 'Athens' }]);
        expect(eventSectionMatches(p, { kind: 'death', place: 'athens', yearFrom: null, yearTo: null })).toBe(true);
    });
});

describe('eventSectionMatches — marriage', () => {
    it('matches if any MARR event satisfies', () => {
        const p = mkPerson([
            { tag: 'MARR', date: '1910', place: 'Smyrna' },
            { tag: 'MARR', date: '1925', place: 'Athens' },
        ]);
        const sec = { kind: 'marriage', place: 'athens', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(p, sec)).toBe(true);
    });
    it('rejects when no MARR matches', () => {
        const p = mkPerson([{ tag: 'MARR', date: '1910', place: 'Smyrna' }]);
        const sec = { kind: 'marriage', place: 'Athens', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(p, sec)).toBe(false);
    });
});

describe('eventSectionMatches — residence', () => {
    it('matches RESI events', () => {
        const p = mkPerson([{ tag: 'RESI', date: '1950', place: 'Valletta' }]);
        const sec = { kind: 'residence', place: 'valletta', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(p, sec)).toBe(true);
    });
});

describe('eventSectionMatches — any event', () => {
    it('matches across event types', () => {
        const p = mkPerson([
            { tag: 'BIRT', date: '1892', place: 'Smyrna' },
            { tag: 'BAPM', date: '1893', place: 'Valletta' },
        ]);
        const sec = { kind: 'any', place: 'valletta', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(p, sec)).toBe(true);
    });
    it('place-only "any" matches if any event has the place', () => {
        const p = mkPerson([{ tag: 'OCCU', date: '', place: 'Cairo' }]);
        expect(eventSectionMatches(p, { kind: 'any', place: 'cairo', yearFrom: null, yearTo: null })).toBe(true);
    });
});

describe('eventSectionMatches — empty section', () => {
    it('returns true (no filter active)', () => {
        const p = mkPerson([{ tag: 'BIRT', date: '1892', place: 'Smyrna' }]);
        const sec = { kind: 'birth', place: '', yearFrom: null, yearTo: null };
        expect(eventSectionMatches(p, sec)).toBe(true);
    });
});

const { familySectionMatches } = require('../../js/viz_advanced_search.js');

describe('familySectionMatches', () => {
    const PARENTS = {
        I1: { father: 'I10', mother: 'I11' },
    };
    const ctx = {
        PARENTS,
        PEOPLE_BY_ID: {
            I10: { id: 'I10', name: 'Antonio Vella' },
            I11: { id: 'I11', name: 'Maria Caruana' },
            I20: { id: 'I20', name: 'Joseph Mifsud' },
            I21: { id: 'I21', name: 'Carmela Borg' },
            I30: { id: 'I30', name: 'Pietro Vella' },
        },
        relIndex: {
            spousesOf: { I1: ['I20'] },
            childrenOf: { I1: ['I21'] },
            siblingsOf: { I1: ['I30'] },
        },
    };
    const person = { id: 'I1', name: 'Test' };

    it('spouse matches', () => {
        expect(familySectionMatches(person, { kind: 'spouse', name: 'mifsud' }, ctx)).toBe(true);
    });
    it('spouse rejects when no match', () => {
        expect(familySectionMatches(person, { kind: 'spouse', name: 'unknown' }, ctx)).toBe(false);
    });
    it('father matches FAMC husband', () => {
        expect(familySectionMatches(person, { kind: 'father', name: 'antonio' }, ctx)).toBe(true);
    });
    it('mother matches FAMC wife', () => {
        expect(familySectionMatches(person, { kind: 'mother', name: 'caruana' }, ctx)).toBe(true);
    });
    it('father rejects when matching wife', () => {
        expect(familySectionMatches(person, { kind: 'father', name: 'caruana' }, ctx)).toBe(false);
    });
    it('other person matches sibling', () => {
        expect(familySectionMatches(person, { kind: 'other', name: 'pietro' }, ctx)).toBe(true);
    });
    it('other person matches child', () => {
        expect(familySectionMatches(person, { kind: 'other', name: 'borg' }, ctx)).toBe(true);
    });
    it('other person matches parent', () => {
        expect(familySectionMatches(person, { kind: 'other', name: 'antonio' }, ctx)).toBe(true);
    });
    it('other person matches spouse', () => {
        expect(familySectionMatches(person, { kind: 'other', name: 'mifsud' }, ctx)).toBe(true);
    });
    it('other person rejects unrelated', () => {
        expect(familySectionMatches(person, { kind: 'other', name: 'stranger' }, ctx)).toBe(false);
    });
    it('empty name = no filter', () => {
        expect(familySectionMatches(person, { kind: 'spouse', name: '' }, ctx)).toBe(true);
    });
});

const { personMatchesAdvanced, runAdvancedSearch } = require('../../js/viz_advanced_search.js');

describe('personMatchesAdvanced', () => {
    const PARENTS = { I1: { father: 'I10', mother: 'I11' } };
    const PEOPLE_BY_ID = {
        I1: { id: 'I1', name: 'Joseph Vella', sex: 'M',
              events: [{ tag: 'BIRT', date: '1892', place: 'Smyrna' },
                       { tag: 'DEAT', date: '1965', place: 'Athens' }] },
        I10: { id: 'I10', name: 'Antonio Vella' },
        I11: { id: 'I11', name: 'Maria Caruana' },
    };
    const ctx = {
        PARENTS,
        PEOPLE_BY_ID,
        relIndex: { spousesOf: {}, childrenOf: {}, siblingsOf: {} },
    };
    const person = PEOPLE_BY_ID.I1;

    it('matches first + last name', () => {
        const q = { firstName: 'joseph', lastName: 'vella', sex: new Set(), events: [], family: [] };
        expect(personMatchesAdvanced(person, q, ctx)).toBe(true);
    });
    it('rejects name mismatch', () => {
        const q = { firstName: '', lastName: 'mifsud', sex: new Set(), events: [], family: [] };
        expect(personMatchesAdvanced(person, q, ctx)).toBe(false);
    });
    it('matches sex filter', () => {
        const q = { firstName: '', lastName: '', sex: new Set(['M']), events: [], family: [] };
        expect(personMatchesAdvanced(person, q, ctx)).toBe(true);
    });
    it('rejects when sex not in set', () => {
        const q = { firstName: '', lastName: '', sex: new Set(['F']), events: [], family: [] };
        expect(personMatchesAdvanced(person, q, ctx)).toBe(false);
    });
    it('empty sex set = no filter', () => {
        const q = { firstName: '', lastName: '', sex: new Set(), events: [], family: [] };
        expect(personMatchesAdvanced(person, q, ctx)).toBe(true);
    });
    it('ANDs across all sections — rejects when one fails', () => {
        const q = {
            firstName: '', lastName: 'vella', sex: new Set(),
            events: [
                { kind: 'birth', place: 'Smyrna', yearFrom: null, yearTo: 1920 },
                { kind: 'death', place: 'Greece', yearFrom: null, yearTo: null },
            ],
            family: [],
        };
        expect(personMatchesAdvanced(person, q, ctx)).toBe(false);
    });
    it('passes when all filters satisfied', () => {
        const q = {
            firstName: '', lastName: 'vella', sex: new Set(['M']),
            events: [{ kind: 'birth', place: 'smyrna', yearFrom: null, yearTo: 1920 }],
            family: [{ kind: 'father', name: 'antonio' }],
        };
        expect(personMatchesAdvanced(person, q, ctx)).toBe(true);
    });
});

describe('runAdvancedSearch', () => {
    const PARENTS = {};
    const PEOPLE_BY_ID = {
        I1: { id: 'I1', name: 'Joseph Vella', sex: 'M', birth_year: 1892,
              events: [{ tag: 'BIRT', date: '1892', place: 'Smyrna' },
                       { tag: 'DEAT', date: '1965', place: 'Athens, Greece' }] },
        I2: { id: 'I2', name: 'Maria Vella', sex: 'F', birth_year: 1895,
              events: [{ tag: 'BIRT', date: '1895', place: 'Smyrna' },
                       { tag: 'DEAT', date: '1972', place: 'Valletta, Malta' }] },
        I3: { id: 'I3', name: 'Antonio Vella', sex: 'M', birth_year: 1901,
              events: [{ tag: 'BIRT', date: '1901', place: 'Smyrna' },
                       { tag: 'DEAT', date: '1968', place: 'Piraeus, Greece' }] },
    };
    const allPeople = Object.values(PEOPLE_BY_ID).map(p =>
        ({ id: p.id, name: p.name, sex: p.sex, birth_year: p.birth_year, death_year: null }));
    const ctx = {
        PARENTS, PEOPLE_BY_ID,
        relIndex: { spousesOf: {}, childrenOf: {}, siblingsOf: {} },
    };

    it('canonical query: Vella born ≤1920 Smyrna, died Greece', () => {
        const q = {
            firstName: '', lastName: 'vella', sex: new Set(),
            events: [
                { kind: 'birth', place: 'smyrna', yearFrom: null, yearTo: 1920 },
                { kind: 'death', place: 'Greece', yearFrom: null, yearTo: null },
            ],
            family: [],
        };
        const results = runAdvancedSearch(q, allPeople, ctx);
        const ids = results.map(r => r.id).sort();
        expect(ids).toEqual(['I1', 'I3']);
    });

    it('sorts by birth year asc within same last name', () => {
        const q = { firstName: '', lastName: 'vella', sex: new Set(), events: [], family: [] };
        const results = runAdvancedSearch(q, allPeople, ctx);
        expect(results.map(r => r.id)).toEqual(['I1', 'I2', 'I3']);
    });
});
