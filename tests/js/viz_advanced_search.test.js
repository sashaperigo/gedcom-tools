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
