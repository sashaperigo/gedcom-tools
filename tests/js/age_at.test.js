import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// Stub globals viz_panel.js touches at load time
global.document = { getElementById: () => null, addEventListener: () => {} };
global.PEOPLE = {};
global.SOURCES = {};
global.setState = () => {};
global.getState = () => ({});
global.onStateChange = () => {};

const { _ageAt } = require('../../js/viz_panel.js');

describe('_ageAt', () => {
    it('returns age as string for a single year after birth', () => {
        expect(_ageAt(1942, 1926)).toBe('16');
    });

    it('returns "0" when event year equals birth year (birth row)', () => {
        expect(_ageAt(1926, 1926)).toBe('0');
    });

    it('returns range for an en-dash year range', () => {
        expect(_ageAt('1942–1944', 1926)).toBe('16–18');
    });

    it('returns range for a hyphen year range', () => {
        expect(_ageAt('1942-1944', 1926)).toBe('16–18');
    });

    it('collapses range to a single value when start equals end', () => {
        expect(_ageAt('1942–1942', 1926)).toBe('16');
    });

    it('returns null when birth year is null', () => {
        expect(_ageAt(1942, null)).toBe(null);
    });

    it('returns null when birth year is undefined', () => {
        expect(_ageAt(1942, undefined)).toBe(null);
    });

    it('returns null when year is null', () => {
        expect(_ageAt(null, 1926)).toBe(null);
    });

    it('returns null when year is empty string', () => {
        expect(_ageAt('', 1926)).toBe(null);
    });

    it('returns null when year input is unparseable', () => {
        expect(_ageAt('abc', 1926)).toBe(null);
    });

    it('returns null when range has non-numeric end', () => {
        expect(_ageAt('1942–xx', 1926)).toBe(null);
    });

    it('accepts numeric and string years equivalently', () => {
        expect(_ageAt('1942', 1926)).toBe('16');
    });
});
