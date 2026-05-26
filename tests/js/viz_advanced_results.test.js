import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { buildFilterChipsHTML } = require('../../js/viz_advanced_results.js');

describe('buildFilterChipsHTML', () => {
    it('emits chips for name + sex + event + family criteria', () => {
        const html = buildFilterChipsHTML({
            firstName: 'Maria',
            lastName: 'Aliotti',
            sex: new Set(['F']),
            events: [{ kind: 'birth', place: 'Smyrna', yearFrom: 1850, yearTo: 1920 }],
            family: [{ kind: 'spouse', name: 'Domenico' }],
        });
        expect(html).toContain('First: Maria');
        expect(html).toContain('Last: Aliotti');
        expect(html).toContain('Female');
        expect(html).toContain('Born in Smyrna 1850–1920');
        expect(html).toContain('Spouse: Domenico');
        expect(html).toContain('class="adv-chip"');
    });

    it('skips empty event/family sections', () => {
        const html = buildFilterChipsHTML({
            firstName: 'X', lastName: '', sex: new Set(),
            events: [{ kind: 'birth', place: '', yearFrom: null, yearTo: null }],
            family: [{ kind: 'spouse', name: '' }],
        });
        expect(html).toContain('First: X');
        expect(html).not.toContain('Born');
        expect(html).not.toContain('Spouse');
    });

    it('formats year ranges: from-only, to-only, exact, range', () => {
        const mk = (yf, yt) => buildFilterChipsHTML({
            firstName: '', lastName: '', sex: new Set(),
            events: [{ kind: 'death', place: 'Izmir', yearFrom: yf, yearTo: yt }],
            family: [],
        });
        expect(mk(1900, 1920)).toContain('Died in Izmir 1900–1920');
        expect(mk(1900, null)).toContain('Died in Izmir 1900–');
        expect(mk(null, 1920)).toContain('Died in Izmir –1920');
        expect(mk(1900, 1900)).toContain('Died in Izmir 1900');
    });

    it('escapes HTML in user-entered text', () => {
        const html = buildFilterChipsHTML({
            firstName: '<script>', lastName: '', sex: new Set(),
            events: [], family: [],
        });
        expect(html).not.toContain('<script>');
        expect(html).toContain('&lt;script&gt;');
    });
});
