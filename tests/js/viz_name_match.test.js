import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { stripAccents, normSearch, getParsed, nameMatches } = require('../../js/viz_name_match.js');

describe('stripAccents', () => {
    it('strips accents', () => {
        expect(stripAccents('café')).toBe('cafe');
        expect(stripAccents('résumé')).toBe('resume');
    });
});

describe('normSearch', () => {
    it('lowercases and strips accents', () => {
        expect(normSearch('Ángel')).toBe('angel');
    });
});

describe('getParsed', () => {
    it('extracts first and last name tokens', () => {
        const p = { id: 'I1', name: 'Joseph /Vella/' };
        const r = getParsed(p);
        expect(r.normFirst).toBe('joseph');
        expect(r.normLast).toBe('vella');
    });
    it('caches by id', () => {
        const p = { id: 'I2', name: 'Maria Caruana' };
        expect(getParsed(p)).toBe(getParsed(p));
    });
});

describe('nameMatches', () => {
    it('substring matches accent-insensitively', () => {
        expect(nameMatches({ name: 'José García' }, 'jose')).toBe(true);
        expect(nameMatches({ name: 'José García' }, 'garcia')).toBe(true);
    });
    it('returns true on empty query', () => {
        expect(nameMatches({ name: 'Anyone' }, '')).toBe(true);
    });
    it('returns false on no name', () => {
        expect(nameMatches({ name: '' }, 'x')).toBe(false);
    });
    it('accepts a raw string', () => {
        expect(nameMatches('Joseph Vella', 'vella')).toBe(true);
    });
});
