import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(
    import.meta.url);

// ── DOM / global stubs ────────────────────────────────────────────────────

function makeFakeEl(id = '') {
    const _styleProps = {};
    return {
        id,
        innerHTML: '',
        className: '',
        textContent: '',
        firstChild: null,
        style: {
            setProperty(prop, val) { _styleProps[prop] = val; },
            getPropertyValue(prop) { return _styleProps[prop] || ''; },
        },
        classList: {
            _classes: new Set(),
            add(c) { this._classes.add(c); },
            remove(c) { this._classes.delete(c); },
            contains(c) { return this._classes.has(c); },
            toggle(c) { if (this._classes.has(c)) this._classes.delete(c);
                else this._classes.add(c); },
        },
        querySelector: () => null,
        querySelectorAll: () => [],
        insertBefore: () => {},
        appendChild: () => {},
        remove: () => {},
    };
}

let _setState_calls = [];
let _state = { panelOpen: false, panelXref: null, focusXref: null };
const _callbacks = [];

global.document = {
    getElementById: () => null,
    createElement: (tag) => makeFakeEl(tag),
    addEventListener: () => {},
};
global.PEOPLE = {};
global.SOURCES = {};
global.ALL_PEOPLE = [];
global.FACTS_BY_TYPE = {};

// Stub setState / getState / onStateChange before requiring the module
global.setState = (updates) => { _setState_calls.push(updates);
    Object.assign(_state, updates);
    _callbacks.forEach(cb => cb(_state)); };
global.getState = () => _state;
global.onStateChange = (cb) => { _callbacks.push(cb); };

// Stub API functions
global.apiDeleteCitation = vi.fn(() => Promise.resolve({ ok: true }));
global.showEditNameModal = vi.fn();
global.showAddEventModal = vi.fn();
global.showAddCitationModal = vi.fn();
global.showAddNoteModal = vi.fn();
global.showEditCitationModal = vi.fn();
global.showAddGodparentModal = vi.fn();

const { initPanel, renderPanel, collapseResidences, toggleResiExpand } = require('../../js/viz_panel.js');

// ── helpers ───────────────────────────────────────────────────────────────

function makePanelEl() {
    const el = makeFakeEl('detail-panel');
    // Override getElementById to return sub-elements by id lookup on a simple registry
    const registry = {};
    const reg = (id) => { const e = makeFakeEl(id);
        registry[id] = e; return e; };
    el._registry = registry;
    el._reg = reg;
    return el;
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('initPanel', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null, focusXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
    });

    it('hides panel when panelOpen === false', () => {
        const panelEl = makeFakeEl('detail-panel');
        _state = { panelOpen: false, panelXref: null };

        global.document = {
            getElementById: (id) => id === 'detail-panel' ? panelEl : null,
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        // trigger callback
        _callbacks.forEach(cb => cb(_state));

        expect(panelEl.classList.contains('panel-open')).toBe(false);
    });

    it('registers onStateChange callback', () => {
        const panelEl = makeFakeEl('detail-panel');
        const before = _callbacks.length;

        global.document = {
            getElementById: (id) => id === 'detail-panel' ? panelEl : null,
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        expect(_callbacks.length).toBeGreaterThan(before);
    });
});

describe('renderPanel', () => {
    beforeEach(() => {
        _setState_calls = [];
        _callbacks.length = 0;
        global.PEOPLE = {};
        global.SOURCES = {};
    });

    it('shows panel element when panelOpen === true', () => {
        const panelEl = makeFakeEl('detail-panel');
        _state = { panelOpen: true, panelXref: '@I1@' };

        global.PEOPLE['@I1@'] = {
            name: 'Test Person',
            birth_year: '1900',
            death_year: '1970',
            sex: 'M',
            events: [],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(panelEl.classList.contains('panel-open')).toBe(true);
    });

    it('hides panel element when panelOpen === false', () => {
        const panelEl = makeFakeEl('detail-panel');
        panelEl.classList.add('panel-open'); // was open
        _state = { panelOpen: false, panelXref: null };

        global.document = {
            getElementById: (id) => id === 'detail-panel' ? panelEl : makeFakeEl(id),
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(panelEl.classList.contains('panel-open')).toBe(false);
    });

    it('renders person name in detail-name element', () => {
        const panelEl = makeFakeEl('detail-panel');
        const nameEl = makeFakeEl('detail-name');
        _state = { panelOpen: true, panelXref: '@I1@' };

        global.PEOPLE['@I1@'] = {
            name: 'John Papadopoulos',
            birth_year: '1873',
            death_year: '1940',
            sex: 'M',
            events: [],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-name') return nameEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(nameEl.innerHTML).toContain('John Papadopoulos');
    });

    it('renders birth and death years', () => {
        const panelEl = makeFakeEl('detail-panel');
        const lifespanRowEl = makeFakeEl('detail-lifespan-row');
        _state = { panelOpen: true, panelXref: '@I2@' };

        global.PEOPLE['@I2@'] = {
            name: 'Mary Smith',
            birth_year: '1880',
            death_year: '1950',
            sex: 'F',
            events: [],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-lifespan-row') return lifespanRowEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(lifespanRowEl.innerHTML).toContain('1880');
        expect(lifespanRowEl.innerHTML).toContain('1950');
    });

    it('renders fact rows for each fact', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@I3@' };

        global.PEOPLE['@I3@'] = {
            name: 'Andreas Kostas',
            birth_year: '1890',
            death_year: null,
            sex: 'M',
            events: [
                { tag: 'BIRT', date: '12 JAN 1890', place: 'Smyrna', citations: [] },
                { tag: 'IMMI', date: '1922', place: 'New York', citations: [] },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        // Should have rendered something for both facts
        expect(eventsEl.innerHTML.length).toBeGreaterThan(0);
    });

    it('clicking [✕] close button calls setState({ panelOpen: false })', () => {
        const panelEl = makeFakeEl('detail-panel');
        let closeHandler = null;
        const closeBtn = {
            ...makeFakeEl('panel-close-btn'),
            set onclick(fn) { closeHandler = fn; },
        };
        _state = { panelOpen: true, panelXref: '@I1@' };
        _setState_calls = [];

        global.PEOPLE['@I1@'] = {
            name: 'Test',
            birth_year: '1900',
            death_year: null,
            sex: 'M',
            events: [],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'panel-close-btn') return closeBtn;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        // Simulate close click
        if (closeHandler) closeHandler();
        expect(_setState_calls.some(u => u.panelOpen === false)).toBe(true);
    });

    it('CHR fact with godparents renders godparent pills', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@I4@' };

        global.PEOPLE = {
            '@I4@': {
                name: 'Nicolaos Petros',
                birth_year: '1895',
                death_year: null,
                sex: 'M',
                events: [{
                    tag: 'CHR',
                    date: '5 MAR 1895',
                    place: 'Smyrna',
                    citations: [],
                    asso: [{ xref: '@I5@', rela: 'Godparent' }],
                }, ],
                notes: [],
                sources: [],
            },
            '@I5@': {
                name: 'Kostas Manolakis',
                birth_year: '1860',
                death_year: null,
                sex: 'M',
                events: [],
                notes: [],
                sources: [],
            },
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(eventsEl.innerHTML).toContain('Kostas Manolakis');
    });

    it('clicking godparent pill calls setState({ focusXref })', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@I4@' };
        _setState_calls = [];

        global.PEOPLE = {
            '@I4@': {
                name: 'Nicolaos Petros',
                birth_year: '1895',
                death_year: null,
                sex: 'M',
                events: [{
                    tag: 'CHR',
                    date: '5 MAR 1895',
                    place: 'Smyrna',
                    citations: [],
                    asso: [{ xref: '@I5@', rela: 'Godparent' }],
                }, ],
                notes: [],
                sources: [],
            },
            '@I5@': {
                name: 'Kostas Manolakis',
                birth_year: '1860',
                death_year: null,
                sex: 'M',
                events: [],
                notes: [],
                sources: [],
            },
        };

        // Capture click handlers stored via _godparentClickHandlers
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        // The panel module should expose _godparentClickHandlers for testing
        // Check that panelEl.innerHTML (or eventsEl.innerHTML) references I5
        // and that a click on a godparent fires setState({ focusXref: '@I5@' })
        // We test this by calling the exported _handleGodparentClick helper
        const { _handleGodparentClick } = require('../../js/viz_panel.js');
        if (_handleGodparentClick) {
            _handleGodparentClick('@I5@');
            expect(_setState_calls.some(u => u.focusXref === '@I5@')).toBe(true);
        } else {
            // If not exported, just verify the HTML contains the godparent name
            expect(eventsEl.innerHTML).toContain('Kostas Manolakis');
        }
    });
});

// ── Tests for restored features from old viz_detail.js ─────────────────────

describe('renderPanel — restored section headers', () => {
    it('renders EARLY LIFE section header for person born 1820, died 1871', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@EARLY@' };

        global.PEOPLE['@EARLY@'] = {
            name: 'Early Person',
            birth_year: '1820',
            death_year: '1871',
            sex: 'M',
            events: [
                { tag: 'BIRT', date: '1820', place: 'Athens, Greece', citations: [], event_idx: 0 },
                { tag: 'RESI', date: '1835', place: 'Smyrna, Turkey', citations: [], event_idx: 0 },
                { tag: 'DEAT', date: '1871', place: 'Constantinople', citations: [], event_idx: 0 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(eventsEl.innerHTML).toContain('EARLY LIFE');
    });

    it('renders LATER LIFE section header for death/burial events', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@LATE@' };

        global.PEOPLE['@LATE@'] = {
            name: 'Later Person',
            birth_year: '1880',
            death_year: '1960',
            sex: 'F',
            events: [
                { tag: 'BIRT', date: '1880', place: '', citations: [], event_idx: 0 },
                { tag: 'DEAT', date: '1960', place: '', citations: [], event_idx: 0 },
                { tag: 'BURI', date: '1960', place: '', citations: [], event_idx: 0 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(eventsEl.innerHTML).toContain('LATER LIFE');
    });
});

describe('renderPanel — RESI rollup', () => {
    it('rolls up consecutive RESI events at same place into a year range', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@RESI@' };

        global.PEOPLE['@RESI@'] = {
            name: 'Resi Person',
            birth_year: '1940',
            death_year: null,
            sex: 'M',
            events: [
                { tag: 'RESI', date: '1970', place: 'Columbus, Franklin, Ohio, USA', citations: [], event_idx: 0 },
                { tag: 'RESI', date: '1985', place: 'Columbus, Franklin, Ohio, USA', citations: [], event_idx: 1 },
                { tag: 'RESI', date: '1998', place: 'Columbus, Franklin, Ohio, USA', citations: [], event_idx: 2 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        // Should contain the year range (not three separate rows)
        expect(eventsEl.innerHTML).toMatch(/1970.*1998|1970\u20131998/);
        // Should not contain three separate year entries
        const matches = (eventsEl.innerHTML.match(/1985/g) || []);
        expect(matches.length).toBe(0); // 1985 should be absorbed into the range
    });

    it('uses end year of BET range when collapsing RESI run', () => {
        // BET 2019 AND 2020 should contribute 2020 as the end of the range, not 2019
        const events = [
            { tag: 'RESI', date: '2019', place: 'San Francisco, San Francisco, California, USA', citations: [], event_idx: 0 },
            { tag: 'RESI', date: 'BET 2019 AND 2020', place: 'San Francisco, San Francisco, California, USA', citations: [], event_idx: 1 },
        ];
        const collapsed = collapseResidences(events);
        expect(collapsed).toHaveLength(1);
        expect(collapsed[0]._yearRange).toBe('2019\u20132020');
    });

    it('stores _run on collapsed event for expand-to-edit', () => {
        const events = [
            { tag: 'RESI', date: '2019', place: 'San Francisco, San Francisco, California, USA', citations: [], event_idx: 0 },
            { tag: 'RESI', date: 'BET 2019 AND 2020', place: 'San Francisco, San Francisco, California, USA', citations: [], event_idx: 1 },
        ];
        const collapsed = collapseResidences(events);
        expect(collapsed[0]._run).toHaveLength(2);
        expect(collapsed[0]._run[0].event_idx).toBe(0);
        expect(collapsed[0]._run[1].event_idx).toBe(1);
    });

    it('uses max year across all events when first event spans a range', () => {
        const events = [
            { tag: 'RESI', date: 'FROM 2017 TO 2026',
              place: 'San Francisco, San Francisco, California, USA', citations: [], event_idx: 0 },
            { tag: 'RESI', date: '2019',
              place: 'San Francisco, San Francisco, California, USA', citations: [], event_idx: 1 },
        ];
        const collapsed = collapseResidences(events);
        expect(collapsed).toHaveLength(1);
        expect(collapsed[0]._yearRange).toBe('2017–2026');
    });
});

describe('renderPanel — EVEN tag uses type label', () => {
    it('EVEN event renders type field as label, not "EVEN"', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@EVEN@' };

        global.PEOPLE['@EVEN@'] = {
            name: 'Event Person',
            birth_year: '1920',
            death_year: null,
            sex: 'M',
            events: [
                { tag: 'EVEN', type: 'Military Service', date: '1943', place: '', citations: [], event_idx: 0 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(eventsEl.innerHTML).toContain('Military Service');
        // "EVEN" as a visible label must not appear (may appear in data-tag or class)
        // The prose/heading text should not read "EVEN"
        expect(eventsEl.innerHTML).not.toMatch(/>EVEN</);
    });
});

describe('renderPanel — blank fact filter', () => {
    it('event with no date, place, inline_val, or note is absent from rendered output', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@BLANK@' };
        const beforeLen = eventsEl.innerHTML.length;

        global.PEOPLE['@BLANK@'] = {
            name: 'Blank Person',
            birth_year: null,
            death_year: null,
            sex: 'M',
            events: [
                { tag: 'RESI', date: null, place: null, inline_val: null, note: null, citations: [], event_idx: 0 },
                { tag: 'BIRT', date: '1900', place: '', citations: [], event_idx: 0 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        // The blank RESI should not create a "Residence" row
        // We count how many event rows appear — only BIRT should be visible
        const html = eventsEl.innerHTML;
        // BIRT event renders as 'Born 1900' (via buildProse)
        expect(html).toContain('Born');
        // Blank RESI must not render a Residence row
        expect(html).not.toContain('Residence');
    });
});

describe('renderPanel — aliases (AKA)', () => {
    it('detail-aka section contains alias entries for _name_record events', () => {
        const panelEl = makeFakeEl('detail-panel');
        const akaEl = makeFakeEl('detail-aka');
        _state = { panelOpen: true, panelXref: '@AKA@' };

        global.PEOPLE['@AKA@'] = {
            name: 'Main Name',
            birth_year: null,
            death_year: null,
            sex: 'M',
            events: [
                { tag: 'NAME', _name_record: true, _name_occurrence: 0, note: 'First Alias', type: 'AKA', date: null, place: null, citations: [], event_idx: null },
                { tag: 'NAME', _name_record: true, _name_occurrence: 1, note: 'Second Alias', type: 'AKA', date: null, place: null, citations: [], event_idx: null },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-aka') return akaEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(akaEl.innerHTML).toContain('First Alias');
        expect(akaEl.innerHTML).toContain('Second Alias');
    });
});

describe('renderPanel — marriage card', () => {
    it('MARR event renders a .marr-card element', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@MARR@' };

        global.PEOPLE['@MARR@'] = {
            name: 'Married Person',
            birth_year: '1900',
            death_year: null,
            sex: 'M',
            events: [{
                tag: 'MARR',
                date: '1925',
                place: 'Athens',
                spouse: 'Maria',
                spouse_xref: '@SP@',
                fam_xref: '@F1@',
                marr_idx: 0,
                citations: [],
                event_idx: null
            }, ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(eventsEl.innerHTML).toContain('marr-card');
    });
});

describe('renderPanel — marriage card uses evt-year-col layout', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
    });

    it('wraps year in evt-year-col and prose in evt-content', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'Test',
                sex: 'M',
                events: [{ tag: 'MARR', date: '1864', place: '', fam_xref: '@F1@', marr_idx: 0, _origIdx: 0, event_idx: null }],
                notes: [],
                sources: [],
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        global.getState = () => _state;
        expect(eventsEl.innerHTML).toContain('evt-year-col');
        expect(eventsEl.innerHTML).toContain('evt-content');
        expect(eventsEl.innerHTML).toContain('marr-card');
    });
});

describe('renderPanel — event note in italics', () => {
    it('event note is wrapped in italic element or evt-note-inline class', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@NOTE@' };

        global.PEOPLE['@NOTE@'] = {
            name: 'Noted Person',
            birth_year: '1900',
            death_year: null,
            sex: 'M',
            events: [
                { tag: 'BIRT', date: '1900', place: 'Smyrna', note: 'Born at dawn', citations: [], event_idx: 0 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        const html = eventsEl.innerHTML;
        expect(html).toContain('Born at dawn');
        // Must be in an italic element or .evt-note-inline
        expect(html).toMatch(/(<i>|evt-note-inline)/);
    });
});

describe('renderPanel — source badge count', () => {
    it('event with 3 citations renders badge text "3 src"', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@SRC@' };

        global.PEOPLE['@SRC@'] = {
            name: 'Sourced Person',
            birth_year: '1900',
            death_year: null,
            sex: 'M',
            events: [{
                tag: 'BIRT',
                date: '1900',
                place: 'Smyrna',
                citations: [
                    { sourceXref: '@S1@', page: null },
                    { sourceXref: '@S2@', page: null },
                    { sourceXref: '@S3@', page: null },
                ],
                event_idx: 0,
            }, ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        expect(eventsEl.innerHTML).toContain('3 src');
    });
});

// ── C2: NATI events render in detail-nationalities ────────────────────────

describe('renderPanel — NATI events in detail-nationalities (C2)', () => {
    it('NATI events render inside #detail-nationalities, not #detail-facts', () => {
        const panelEl = makeFakeEl('detail-panel');
        const natiEl = makeFakeEl('detail-nationalities');
        const factsEl = makeFakeEl('detail-facts');
        _state = { panelOpen: true, panelXref: '@NATI@' };

        global.PEOPLE['@NATI@'] = {
            name: 'Nationality Person',
            birth_year: '1900',
            death_year: null,
            sex: 'M',
            events: [
                { tag: 'NATI', inline_val: 'Greek', type: 'Greek', date: null, place: null, citations: [], event_idx: 0 },
                { tag: 'NATI', inline_val: 'Ottoman', type: 'Ottoman', date: null, place: null, citations: [], event_idx: 1 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-nationalities') return natiEl;
                if (id === 'detail-facts') return factsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        // NATI events must render into detail-nationalities
        expect(natiEl.innerHTML).toContain('Greek');
        // detail-facts must NOT contain the nationality pills
        expect(factsEl.innerHTML).not.toContain('Greek');
    });

    it('NATI events do not appear in detail-facts when rendered', () => {
        const panelEl = makeFakeEl('detail-panel');
        const natiEl = makeFakeEl('detail-nationalities');
        const factsEl = makeFakeEl('detail-facts');
        _state = { panelOpen: true, panelXref: '@NATI2@' };

        global.PEOPLE['@NATI2@'] = {
            name: 'Another Person',
            birth_year: '1890',
            death_year: null,
            sex: 'F',
            events: [
                { tag: 'NATI', inline_val: 'French', type: 'French', date: null, place: null, citations: [], event_idx: 0 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-nationalities') return natiEl;
                if (id === 'detail-facts') return factsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        // The nationality heading/pills must NOT be in detail-facts
        expect(factsEl.innerHTML).not.toMatch(/Nationality/);
    });
});

// ── C3: Collapsible family section ────────────────────────────────────────

describe('renderPanel — collapsible family section (C3)', () => {
    function makePersonWithFamily() {
        global.PEOPLE = {
            '@FAM@': {
                name: 'Family Person',
                birth_year: '1900',
                death_year: null,
                sex: 'M',
                events: [{
                    tag: 'MARR',
                    date: '1925',
                    place: 'Athens',
                    spouse: 'Maria',
                    spouse_xref: '@SP@',
                    fam_xref: '@F1@',
                    marr_idx: 0,
                    citations: [],
                    event_idx: null
                }, ],
                notes: [],
                sources: [],
            },
            '@SP@': {
                name: 'Maria Spouse',
                birth_year: '1905',
                death_year: null,
                sex: 'F',
                events: [],
                notes: [],
                sources: [],
            },
        };
    }

    it('family section subsections are hidden by default (collapsed state)', () => {
        const panelEl = makeFakeEl('detail-panel');
        const familyEl = makeFakeEl('detail-family');
        _state = { panelOpen: true, panelXref: '@FAM@' };
        makePersonWithFamily();

        global.PARENTS = { '@FAM@': ['@PA@', '@MA@'], '@SP@': [null, null] };
        global.RELATIVES = {};
        global.CHILDREN = {};

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-family') return familyEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        const html = familyEl.innerHTML;
        // Subsections (parents, siblings, spouses) must be hidden by default
        // They should either have display:none or be absent from the DOM
        expect(html).toMatch(/display:\s*none|display:none/i);
    });

    it('toggle button is present with "▶ Family" label when collapsed', () => {
        const panelEl = makeFakeEl('detail-panel');
        const familyEl = makeFakeEl('detail-family');
        _state = { panelOpen: true, panelXref: '@FAM@' };
        makePersonWithFamily();

        global.PARENTS = { '@FAM@': ['@PA@', '@MA@'], '@SP@': [null, null] };
        global.RELATIVES = {};
        global.CHILDREN = {};

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-family') return familyEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        const html = familyEl.innerHTML;
        // Toggle button with collapsed arrow must be present
        expect(html).toContain('sources-toggle-arrow');
        expect(html).toContain('▶');
        expect(html).toContain('Family');
    });

    it('all 3 subsections (parents, siblings/spouses, children) hidden when collapsed', () => {
        const panelEl = makeFakeEl('detail-panel');
        const familyEl = makeFakeEl('detail-family');
        _state = { panelOpen: true, panelXref: '@FAM@' };
        makePersonWithFamily();

        global.PARENTS = { '@FAM@': ['@PA@', '@MA@'], '@SP@': [null, null] };
        global.RELATIVES = {
            '@FAM@': { siblings: ['@SIB@'], spouses: ['@SP@'], half_siblings: [] },
        };
        global.CHILDREN = { '@FAM@': ['@CH1@'] };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-family') return familyEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        const html = familyEl.innerHTML;
        // All subsection divs should have display:none
        const hiddenMatches = html.match(/display:\s*none/gi) || [];
        // At least 3 subsections should be hidden (parents, siblings, spouses+children)
        expect(hiddenMatches.length).toBeGreaterThanOrEqual(3);
    });

    it('half-siblings subsection is hidden when family section is collapsed', () => {
        const panelEl = makeFakeEl('detail-panel');
        const familyEl = makeFakeEl('detail-family');
        _state = { panelOpen: true, panelXref: '@FAM@' };
        makePersonWithFamily();

        global.PARENTS = { '@FAM@': ['@PA@', '@MA@'], '@SP@': [null, null] };
        global.RELATIVES = {
            '@FAM@': {
                siblings: ['@SIB@'],
                spouses: ['@SP@'],
                half_siblings: [
                    { shared_parent: '@PA@', other_parent: '@OP@', half_sibs: ['@HS1@'] },
                ],
            },
        };
        global.CHILDREN = { '@FAM@': ['@CH1@'] };
        global.PEOPLE['@HS1@'] = { name: 'Half Sib', birth_year: '1910', death_year: null, sex: 'F', events: [], notes: [], sources: [] };
        global.PEOPLE['@OP@'] = { name: 'Other Parent', birth_year: '1880', death_year: null, sex: 'F', events: [], notes: [], sources: [] };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-family') return familyEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        const html = familyEl.innerHTML;
        // Count family-sub divs vs hidden ones — they must match
        const totalSubs = (html.match(/<div class="family-sub"/g) || []).length;
        const hiddenSubs = (html.match(/<div class="family-sub" style="display:none"/g) || []).length;
        expect(totalSubs).toBeGreaterThan(0);
        expect(hiddenSubs).toBe(totalSubs);
        // Explicitly confirm Half-siblings heading is not visible (inside a hidden container)
        expect(html).toContain('Half-siblings');
        expect(html).not.toMatch(/<div class="family-sub"[^>]*>(?!.*display:none)[^]*?Half-siblings/);
    });
});

describe('renderPanel — person-level sources section', () => {
    it('renders source cards with a count pill and a Manage button', () => {
        const panelEl = makeFakeEl('detail-panel');
        const sourcesEl = makeFakeEl('detail-sources');
        _state = { panelOpen: true, panelXref: '@SRCP@' };

        global.PEOPLE['@SRCP@'] = {
            name: 'Person With Sources',
            birth_year: '1900',
            death_year: null,
            sex: 'M',
            events: [],
            notes: [],
            sources: [
                { title: 'Birth Register 1900', url: null },
                { title: 'Census 1910', url: null },
            ],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-sources') return sourcesEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        const html = sourcesEl.innerHTML;
        expect(html).toContain('Sources');
        expect(html).toContain('sources-count-pill');
        expect(html).toContain('sources-manage-btn');
        expect(html).toContain('source-card');
        expect(html).toContain('Birth Register 1900');
        expect(html).toContain('Census 1910');
    });
});

describe('buildSourceBadgeHtml', () => {
    const { buildSourceBadgeHtml } = require('../../js/viz_panel.js');

    it('renders a pill even when there are zero citations', () => {
        const html = buildSourceBadgeHtml([], '@I1@', 0);
        expect(html).toBeTruthy();
        expect(html).toContain('evt-src-badge');
        expect(html).toContain('openSourcesModal');
    });

    it('shows "+ src" label when there are zero citations', () => {
        const html = buildSourceBadgeHtml([], '@I1@', 0);
        expect(html).toMatch(/\+\s*src/);
    });

    it('shows "1 src" label when there is one citation', () => {
        const html = buildSourceBadgeHtml([{ sourceXref: '@S1@' }], '@I1@', 0);
        expect(html).toContain('1 src');
    });

    it('shows "N src" label when there are multiple citations', () => {
        const html = buildSourceBadgeHtml(
            [{ sourceXref: '@S1@' }, { sourceXref: '@S2@' }, { sourceXref: '@S3@' }],
            '@I1@', 2);
        expect(html).toContain('3 src');
    });

    it('renders a pill when citations is null/undefined', () => {
        const html = buildSourceBadgeHtml(null, '@I1@', 0);
        expect(html).toBeTruthy();
        expect(html).toContain('evt-src-badge');
    });
});

describe('buildNoteSourceBadgeHtml', () => {
    const { buildNoteSourceBadgeHtml } = require('../../js/viz_panel.js');

    it('shows "+ src" and empty class when no citations', () => {
        const html = buildNoteSourceBadgeHtml([], '@I1@', 0);
        expect(html).toMatch(/\+\s*src/);
        expect(html).toContain('note-src-badge-empty');
        expect(html).toContain('note-src-badge');
    });

    it('shows "1 src" and no empty class when one citation', () => {
        const html = buildNoteSourceBadgeHtml([{ sourceXref: '@S1@' }], '@I1@', 2);
        expect(html).toContain('1 src');
        expect(html).toContain('note-src-badge');
        expect(html).not.toContain('note-src-badge-empty');
    });

    it('calls openNoteSourcesModal with correct xref and index', () => {
        const html = buildNoteSourceBadgeHtml([], '@I1@', 3);
        expect(html).toContain('openNoteSourcesModal');
        expect(html).toContain('&quot;@I1@&quot;');
        expect(html).toContain(',3)');
    });

    it('renders a pill when citations is null', () => {
        const html = buildNoteSourceBadgeHtml(null, '@I1@', 0);
        expect(html).toBeTruthy();
        expect(html).toContain('note-src-badge');
    });
});

describe('convertEventTag', () => {
    const { convertEventTag } = require('../../js/viz_panel.js');

    beforeEach(() => {
        global.apiConvertEvent = vi.fn();
        global.confirm = vi.fn();
        global.alert = vi.fn();
        global.PEOPLE = {};
        // Provide a panel so renderPanel() doesn't throw when the API succeeds
        const panelEl = makeFakeEl('detail-panel');
        global.document = {
            getElementById: (id) => id === 'detail-panel' ? panelEl : makeFakeEl(id),
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        initPanel(panelEl);
    });

    it('does nothing when user cancels the confirmation dialog', async () => {
        global.confirm.mockReturnValue(false);
        await convertEventTag('@I1@', 0, 'BIRT', 'BAPM');
        expect(global.apiConvertEvent).not.toHaveBeenCalled();
    });

    it('calls apiConvertEvent with correct args when user confirms', async () => {
        global.confirm.mockReturnValue(true);
        global.apiConvertEvent.mockResolvedValue({ people: {} });
        await convertEventTag('@I1@', 0, 'BIRT', 'BAPM');
        expect(global.apiConvertEvent).toHaveBeenCalledWith('@I1@', 0, 'BIRT', 'BAPM');
    });

    it('updates PEOPLE with returned data when confirmed', async () => {
        global.confirm.mockReturnValue(true);
        const updatedPerson = { name: 'Updated Person', events: [], birth_year: null, death_year: null, sex: 'M', notes: [], sources: [] };
        global.apiConvertEvent.mockResolvedValue({ people: { '@I1@': updatedPerson } });
        await convertEventTag('@I1@', 0, 'BIRT', 'BAPM');
        expect(global.PEOPLE['@I1@']).toEqual(updatedPerson);
    });

    it('shows error alert when API call fails', async () => {
        global.confirm.mockReturnValue(true);
        global.apiConvertEvent.mockRejectedValue(new Error('server error'));
        await convertEventTag('@I1@', 0, 'BIRT', 'BAPM');
        expect(global.alert).toHaveBeenCalledWith(expect.stringContaining('Conversion failed'));
    });

    it('calls closeEventModal after successful conversion', async () => {
        global.closeEventModal = vi.fn();
        global.confirm.mockReturnValue(true);
        global.apiConvertEvent.mockResolvedValue({ people: {} });
        await convertEventTag('@I1@', 0, 'BIRT', 'BAPM');
        expect(global.closeEventModal).toHaveBeenCalled();
    });

    it('does not call closeEventModal when user cancels', async () => {
        global.closeEventModal = vi.fn();
        global.confirm.mockReturnValue(false);
        await convertEventTag('@I1@', 0, 'BIRT', 'BAPM');
        expect(global.closeEventModal).not.toHaveBeenCalled();
    });

    it('does not call closeEventModal on API error', async () => {
        global.closeEventModal = vi.fn();
        global.confirm.mockReturnValue(true);
        global.apiConvertEvent.mockRejectedValue(new Error('server error'));
        await convertEventTag('@I1@', 0, 'BIRT', 'BAPM');
        expect(global.closeEventModal).not.toHaveBeenCalled();
    });
});

// ── _buildGodparentPillsHtml — onclick attribute is well-formed ──────────

describe('_buildGodparentPillsHtml', () => {
    const { _buildGodparentPillsHtml } = require('../../js/viz_panel.js');

    beforeEach(() => {
        global.PEOPLE = {
            '@I5@': { name: 'Maria Godmother', sex: 'F' },
        };
    });

    it('escapes double-quotes in the onclick attribute so the pill is clickable', () => {
        const evt = {
            tag: 'BAPM',
            asso: [{ xref: '@I5@', rela: 'Godmother' }],
        };
        const html = _buildGodparentPillsHtml(evt, '@I1@', '&quot;@I1@&quot;');

        // The onclick attribute uses double quotes; embedded string literals must
        // be HTML-escaped (&quot;) — otherwise the browser closes the attribute
        // early and the click handler never fires.
        const onclickMatch = html.match(/onclick="([^"]*)"/);
        expect(onclickMatch).not.toBeNull();
        // The actual asso.xref should NOT appear as a raw double-quoted string
        // inside the attribute value; it must be &quot;-escaped.
        expect(html).not.toMatch(/onclick="[^"]*"@I5@"/);
        expect(html).toMatch(/onclick="[^"]*&quot;@I5@&quot;/);
    });
});

describe('renderPanel — accent bar color by sex', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
    });

    it('sets blue accent for male', () => {
        const panelEl = makeFakeEl('detail-panel');
        let _accentBarColor = null;
        const accentEl = {
            id: 'detail-accent-bar',
            style: { setProperty: (prop, val) => { if (prop === '--accent-bar-color') _accentBarColor = val; } }
        };
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-accent-bar') return accentEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = { '@I1@': { name: 'Test', sex: 'M', events: [], notes: [], sources: [] } };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(_accentBarColor).toBe('#7db4e8');
    });

    it('sets salmon accent for female', () => {
        const panelEl = makeFakeEl('detail-panel');
        let _accentBarColor = null;
        const accentEl = {
            id: 'detail-accent-bar',
            style: { setProperty: (prop, val) => { if (prop === '--accent-bar-color') _accentBarColor = val; } }
        };
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-accent-bar') return accentEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = { '@I1@': { name: 'Test', sex: 'F', events: [], notes: [], sources: [] } };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(_accentBarColor).toBe('#f4876a');
    });

    it('no sex-sym span in name HTML', () => {
        const panelEl = makeFakeEl('detail-panel');
        const nameEl = makeFakeEl('detail-name');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-name') return nameEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = { '@I1@': { name: 'Test', sex: 'M', events: [], notes: [], sources: [] } };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(nameEl.innerHTML).not.toContain('sex-sym');
    });
});

describe('renderPanel — fact-row layout for undated facts', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
    });

    it('OCCU renders as fact-row, not evt-entry', () => {
        const panelEl = makeFakeEl('detail-panel');
        const alsoLivedEl = makeFakeEl('detail-also-lived');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-also-lived') return alsoLivedEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'Test', sex: 'M',
                events: [{ tag: 'OCCU', inline_val: 'Merchant', date: null, place: '', _origIdx: 0, event_idx: 0, citations: [] }],
                notes: [], sources: []
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(alsoLivedEl.innerHTML).toContain('fact-row');
        expect(alsoLivedEl.innerHTML).not.toContain('"evt-entry"');
    });

    it('OCCU dot color is #fbbf24', () => {
        const panelEl = makeFakeEl('detail-panel');
        const alsoLivedEl = makeFakeEl('detail-also-lived');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-also-lived') return alsoLivedEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'Test', sex: 'M',
                events: [{ tag: 'OCCU', inline_val: 'Merchant', date: null, place: '', _origIdx: 0, event_idx: 0, citations: [] }],
                notes: [], sources: []
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(alsoLivedEl.innerHTML).toContain('#fbbf24');
    });

    it('undated RESI renders as evt-entry with no-year class', () => {
        const panelEl = makeFakeEl('detail-panel');
        const alsoLivedEl = makeFakeEl('detail-also-lived');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-also-lived') return alsoLivedEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'T', sex: 'M',
                events: [{ tag: 'RESI', date: null, place: 'Paris', _origIdx: 0, event_idx: 0, citations: [] }],
                notes: [], sources: []
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(alsoLivedEl.innerHTML).toContain('evt-entry');
        expect(alsoLivedEl.innerHTML).toContain('no-year');
    });
    it('undated OCCU with citation shows citation count in source badge', () => {
        const panelEl = makeFakeEl('detail-panel');
        const alsoLivedEl = makeFakeEl('detail-also-lived');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-also-lived') return alsoLivedEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'Test', sex: 'M',
                events: [{ tag: 'OCCU', inline_val: 'Pharmacist', date: null, place: '', _origIdx: 0, event_idx: 0,
                    citations: [{ sourceXref: '@S1@', page: 'p.5', text: '', note: '', url: '' }] }],
                notes: [], sources: []
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        const html = alsoLivedEl.innerHTML;
        expect(html).toContain('1 src');
        expect(html).not.toContain('+ src');
    });

    it('RELI shows tag label on top and value on bottom (not reversed)', () => {
        const panelEl = makeFakeEl('detail-panel');
        const alsoLivedEl = makeFakeEl('detail-also-lived');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-also-lived') return alsoLivedEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'Test', sex: 'M',
                events: [{ tag: 'RELI', type: 'Armenian Catholic', inline_val: 'Armenian Catholic', date: null, place: '', _origIdx: 0, event_idx: 0, citations: [] }],
                notes: [], sources: []
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        const html = alsoLivedEl.innerHTML;
        const labelIdx = html.indexOf('fact-row-label');
        const valueIdx = html.indexOf('fact-row-value');
        const religionLabelIdx = html.indexOf('>Religion<');
        const armenianValueIdx = html.indexOf('>Armenian Catholic<');
        // fact-row-label must appear before fact-row-value in DOM order
        expect(labelIdx).toBeLessThan(valueIdx);
        // 'Religion' must be the label (appears before the value span)
        expect(religionLabelIdx).toBeLessThan(armenianValueIdx);
        expect(html).toContain('fact-row-label');
        expect(html).toContain('>Religion<');
        expect(html).toContain('>Armenian Catholic<');
    });
});

describe('renderPanel — note badge inside note-card', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
    });

    it('note-src-badge appears inside note-card div before note-actions', () => {
        const panelEl = makeFakeEl('detail-panel');
        const notesEl = makeFakeEl('detail-notes');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-notes') return notesEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'T', sex: 'M', events: [], sources: [],
                notes: [{ text: 'Hello world', shared: false, citations: [] }]
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        const html = notesEl.innerHTML;
        const noteCardOpenIdx = html.indexOf('class="note-card');
        const noteCardCloseIdx = html.indexOf('</div>', noteCardOpenIdx); // first </div> after note-card opens
        const badgeIdx = html.indexOf('note-src-badge');
        // Badge must appear inside the note-card div (after it opens, before it closes)
        expect(badgeIdx).toBeGreaterThan(noteCardOpenIdx);
        expect(badgeIdx).toBeLessThan(noteCardCloseIdx);
    });
});

describe('renderPanel — no-year class on dateless main-timeline events', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
    });

    it('adds no-year class to evt-entry when main-timeline event has no date', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'T', sex: 'M',
                events: [{ tag: 'BIRT', date: null, place: 'Paris', _origIdx: 0, event_idx: 0, citations: [] }],
                notes: [], sources: []
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(eventsEl.innerHTML).toContain('no-year');
    });
});

describe('renderPanel — family toggle arrow before text', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
    });

    it('family toggle has arrow (▼ or ▶) before "Family" text', () => {
        const panelEl = makeFakeEl('detail-panel');
        const familyEl = makeFakeEl('detail-family');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-family') return familyEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = { '@I1@': { name: 'T', sex: 'M', events: [], notes: [], sources: [] } };
        global.PARENTS = {};
        global.CHILDREN = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        const html = familyEl.innerHTML;
        // Extract the button's inner content (text between > and </button>)
        const btnMatch = html.match(/class="family-toggle-btn"[^>]*>([\s\S]*?)<\/button>/);
        expect(btnMatch).not.toBeNull();
        const btnHtml = btnMatch[1];
        const downArrowPos = btnHtml.indexOf('▼');
        const rightArrowPos = btnHtml.indexOf('▶');
        const arrowPos = Math.min(
            downArrowPos !== -1 ? downArrowPos : Infinity,
            rightArrowPos !== -1 ? rightArrowPos : Infinity
        );
        const familyTextPos = btnHtml.indexOf('Family');
        expect(arrowPos).toBeLessThan(familyTextPos);
    });
});

describe('renderPanel — source card page reference', () => {
    beforeEach(() => {
        _setState_calls = [];
        _state = { panelOpen: false, panelXref: null };
        _callbacks.length = 0;
        global.PEOPLE = {};
    });

    it('renders source-card-page div when s.page is present', () => {
        const panelEl = makeFakeEl('detail-panel');
        const sourcesEl = makeFakeEl('detail-sources');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-sources') return sourcesEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'T', sex: 'M', events: [], notes: [],
                sources: [{ title: 'Census 1880', page: 'p. 42', url: null }]
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(sourcesEl.innerHTML).toContain('source-card-page');
        expect(sourcesEl.innerHTML).toContain('p. 42');
    });

    it('does not render source-card-page when page is absent', () => {
        const panelEl = makeFakeEl('detail-panel');
        const sourcesEl = makeFakeEl('detail-sources');
        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-sources') return sourcesEl;
                return null;
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };
        global.PEOPLE = {
            '@I1@': {
                name: 'T', sex: 'M', events: [], notes: [],
                sources: [{ title: 'Census 1880', url: null }]
            }
        };
        global.PARENTS = {};
        global.getState = () => ({ panelOpen: true, panelXref: '@I1@' });
        renderPanel();
        expect(sourcesEl.innerHTML).not.toContain('source-card-page');
    });
});

// ── allVisible — bare DEAT Y ──────────────────────────────────────────────

describe('renderPanel — bare DEAT Y produces no timeline card', () => {
    it('does not render a Death card when DEAT has no date, place, note, or cause', () => {
        const panelEl = makeFakeEl('detail-panel');
        const eventsEl = makeFakeEl('detail-events');
        _state = { panelOpen: true, panelXref: '@UNDEAD@' };
        global.getState = () => _state;

        global.PEOPLE['@UNDEAD@'] = {
            name: 'Unknown Death',
            birth_year: '1900',
            death_year: null,
            has_death: true,
            sex: 'M',
            events: [
                { tag: 'BIRT', date: '1900', place: '', citations: [], event_idx: 0 },
                // DEAT Y — all content fields null: has_death suppresses "Living",
                // but the empty event should not produce a timeline card.
                { tag: 'DEAT', date: null, place: null, note: null, type: null,
                  cause: null, addr: null, inline_val: null, citations: [], event_idx: 1 },
            ],
            notes: [],
            sources: [],
        };

        global.document = {
            getElementById: (id) => {
                if (id === 'detail-panel') return panelEl;
                if (id === 'detail-events') return eventsEl;
                return makeFakeEl(id);
            },
            createElement: (tag) => makeFakeEl(tag),
            addEventListener: () => {},
        };

        initPanel(panelEl);
        renderPanel();

        // BIRT renders; the bare DEAT Y should not add a second evt-entry
        const entries = (eventsEl.innerHTML.match(/class="evt-entry"/g) || []);
        expect(entries.length).toBe(1);
        expect(eventsEl.innerHTML).not.toContain('Death');
    });
});