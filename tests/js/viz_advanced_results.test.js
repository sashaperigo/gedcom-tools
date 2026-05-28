import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { buildFilterChipsHTML, buildCountBarHTML } = require('../../js/viz_advanced_results.js');

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

describe('buildCountBarHTML', () => {
    it('shows count with correct pluralization and selected sort', () => {
        const h0 = buildCountBarHTML(0, 'name');
        expect(h0).toContain('0 matches');
        const h1 = buildCountBarHTML(1, 'name');
        expect(h1).toContain('1 match');
        expect(h1).not.toContain('1 matches');
        const h2 = buildCountBarHTML(156, 'birth');
        expect(h2).toContain('156 matches');
    });

    it('marks the selected sort option', () => {
        const html = buildCountBarHTML(10, 'birth');
        expect(html).toMatch(/<option[^>]*value="birth"[^>]*selected/);
        expect(html).not.toMatch(/<option[^>]*value="name"[^>]*selected/);
    });

    it('includes both sort options', () => {
        const html = buildCountBarHTML(10, 'name');
        expect(html).toContain('value="name"');
        expect(html).toContain('value="birth"');
        expect(html).toContain('Name');
        expect(html).toContain('Birth year');
    });
});

const { buildResultRowsHTML, paginate, sortResults } = require('../../js/viz_advanced_results.js');

describe('paginate', () => {
    it('returns the requested page slice', () => {
        const arr = Array.from({ length: 60 }, (_, i) => i);
        expect(paginate(arr, 1, 25)).toEqual(arr.slice(0, 25));
        expect(paginate(arr, 2, 25)).toEqual(arr.slice(25, 50));
        expect(paginate(arr, 3, 25)).toEqual(arr.slice(50, 60));
    });
    it('returns [] for out-of-range pages', () => {
        expect(paginate([1, 2, 3], 5, 25)).toEqual([]);
    });
});

describe('sortResults', () => {
    const rows = [
        { id: 'a', name: 'Zara', birth_year: 1900 },
        { id: 'b', name: 'Anna', birth_year: 1850 },
        { id: 'c', name: 'Mia',  birth_year: null },
    ];
    it('sorts by name alphabetically', () => {
        const out = sortResults(rows, 'name');
        expect(out.map(r => r.id)).toEqual(['b', 'c', 'a']);
    });
    it('sorts by birth year ascending, undated last', () => {
        const out = sortResults(rows, 'birth');
        expect(out.map(r => r.id)).toEqual(['b', 'a', 'c']);
    });
    it('does not mutate the input array', () => {
        const original = rows.map(r => r.id);
        sortResults(rows, 'name');
        expect(rows.map(r => r.id)).toEqual(original);
    });
});

describe('buildResultRowsHTML', () => {
    const peopleById = {
        I1: { name: 'Anna Aliotti', events: [
            { tag: 'BIRT', date: '1850', place: 'Smyrna, Izmir, Turkey' },
            { tag: 'DEAT', date: '1920', place: 'Smyrna' },
        ]},
        I2: { name: 'Bob Smith', events: [
            { tag: 'BIRT', date: '1900', place: '' },
        ]},
        I3: { name: 'No Dates', events: [] },
    };
    const spousesOf = { I1: ['I2'] };

    it('renders one row per person with name + meta line', () => {
        const html = buildResultRowsHTML(
            [{ id: 'I1' }, { id: 'I2' }],
            { peopleById, spousesOf }
        );
        expect(html).toContain('Anna Aliotti');
        expect(html).toContain('Bob Smith');
        expect(html.match(/class="adv-row"/g).length).toBe(2);
    });

    it('formats years as b–d, b–, b only', () => {
        const h1 = buildResultRowsHTML([{ id: 'I1' }], { peopleById, spousesOf });
        expect(h1).toMatch(/1850–1920/);
        const h2 = buildResultRowsHTML([{ id: 'I2' }], { peopleById, spousesOf });
        expect(h2).toMatch(/b\.\s*1900/);
        const h3 = buildResultRowsHTML([{ id: 'I3' }], { peopleById, spousesOf });
        expect(h3).not.toMatch(/\d{4}/);
    });

    it('shows spouse name when available', () => {
        const html = buildResultRowsHTML([{ id: 'I1' }], { peopleById, spousesOf });
        expect(html).toContain('spouse Bob Smith');
    });

    it('truncates long place names to the last two segments', () => {
        const html = buildResultRowsHTML([{ id: 'I1' }], { peopleById, spousesOf });
        expect(html).toContain('Izmir, Turkey');
        expect(html).not.toContain('Smyrna, Izmir, Turkey');
    });

    it('embeds the person xref as data-id', () => {
        const html = buildResultRowsHTML([{ id: 'I1' }], { peopleById, spousesOf });
        expect(html).toContain('data-id="I1"');
    });
});

describe('buildPagerHTML', () => {
    const { buildPagerHTML } = require('../../js/viz_advanced_results.js');

    it('renders "X–Y of N" range', () => {
        expect(buildPagerHTML(1, 156, 25)).toContain('1–25 of 156');
        expect(buildPagerHTML(2, 156, 25)).toContain('26–50 of 156');
        expect(buildPagerHTML(7, 156, 25)).toContain('151–156 of 156');
    });

    it('disables prev on page 1 and next on last page', () => {
        const h1 = buildPagerHTML(1, 60, 25);
        expect(h1).toMatch(/data-page="prev"[^>]*disabled/);
        expect(h1).not.toMatch(/data-page="next"[^>]*disabled/);
        const hLast = buildPagerHTML(3, 60, 25);
        expect(hLast).toMatch(/data-page="next"[^>]*disabled/);
    });

    it('marks the current page button as active', () => {
        const html = buildPagerHTML(2, 100, 25);
        expect(html).toMatch(/data-page="2"[^>]*class="[^"]*active/);
    });

    it('renders nothing when total fits in one page', () => {
        expect(buildPagerHTML(1, 10, 25)).toBe('');
    });

    it('windows page buttons around the current page for many pages', () => {
        const html = buildPagerHTML(25, 25 * 50, 25);
        expect(html).toMatch(/data-page="1"/);
        expect(html).toMatch(/data-page="24"/);
        expect(html).toMatch(/data-page="25"[^>]*active/);
        expect(html).toMatch(/data-page="26"/);
        expect(html).toMatch(/data-page="50"/);
        expect(html).toContain('…');
        expect(html).not.toMatch(/data-page="10"/);
    });
});
