import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

global.document = { getElementById: () => null, addEventListener: () => {} };
global.PEOPLE = {};
global.SOURCES = {};
global.setState = () => {};
global.getState = () => ({});
global.onStateChange = () => {};

const { _buildAgeHtml } = require('../../js/viz_panel.js');

describe('_buildAgeHtml', () => {
    it('emits an evt-age span for a non-BIRT event with a single year', () => {
        const evt = { tag: 'DEAT' };
        expect(_buildAgeHtml(evt, 1941, 1926)).toBe('<span class="evt-age">15</span>');
    });

    it('emits an evt-age span with a range when the event year is a range string', () => {
        const evt = { tag: 'RESI' };
        expect(_buildAgeHtml(evt, '1942–1944', 1926)).toBe('<span class="evt-age">16–18</span>');
    });

    it('emits an evt-age span for a marriage range (defensive against future buildProse change)', () => {
        const evt = { tag: 'MARR' };
        expect(_buildAgeHtml(evt, '1925–1926', 1900)).toBe('<span class="evt-age">25–26</span>');
    });

    it('emits the (age) hint for BIRT regardless of computed age', () => {
        const evt = { tag: 'BIRT' };
        expect(_buildAgeHtml(evt, 1926, 1926)).toBe('<span class="evt-age-hint">(age)</span>');
    });

    it('uses the custom ageClass argument when provided', () => {
        const evt = { tag: 'DEAT' };
        expect(_buildAgeHtml(evt, 1941, 1926, 'age')).toBe('<span class="age">15</span>');
    });

    it('accepts a null evt (for relative-event rows)', () => {
        expect(_buildAgeHtml(null, 1941, 1926, 'age')).toBe('<span class="age">15</span>');
    });

    it('returns empty string when birth year is null', () => {
        const evt = { tag: 'DEAT' };
        expect(_buildAgeHtml(evt, 1941, null)).toBe('');
    });

    it('returns empty string when year is null', () => {
        const evt = { tag: 'DEAT' };
        expect(_buildAgeHtml(evt, null, 1926)).toBe('');
    });

    it('returns empty string when year is empty', () => {
        const evt = { tag: 'DEAT' };
        expect(_buildAgeHtml(evt, '', 1926)).toBe('');
    });

    it('returns empty string when _ageAt cannot parse the input', () => {
        const evt = { tag: 'DEAT' };
        expect(_buildAgeHtml(evt, 'not-a-year', 1926)).toBe('');
    });
});
