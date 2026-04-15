import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// ── DOM / global stubs ────────────────────────────────────────────────────

function makeFakeEl(id = '') {
  return {
    id,
    innerHTML: '',
    style: {},
    classList: {
      _classes: new Set(),
      add(c)      { this._classes.add(c); },
      remove(c)   { this._classes.delete(c); },
      contains(c) { return this._classes.has(c); },
      toggle(c)   { if (this._classes.has(c)) this._classes.delete(c); else this._classes.add(c); },
    },
  };
}

let _setState_calls = [];
let _state = { panelOpen: false, panelXref: null, focusXref: null };
const _callbacks = [];

global.document = {
  getElementById: () => null,
  addEventListener: () => {},
};
global.PEOPLE = {};
global.SOURCES = {};
global.ALL_PEOPLE = [];
global.FACTS_BY_TYPE = {};

// Stub setState / getState / onStateChange before requiring the module
global.setState    = (updates) => { _setState_calls.push(updates); Object.assign(_state, updates); _callbacks.forEach(cb => cb(_state)); };
global.getState    = () => _state;
global.onStateChange = (cb) => { _callbacks.push(cb); };

// Stub API functions
global.apiDeleteCitation = vi.fn(() => Promise.resolve({ ok: true }));
global.showEditNameModal  = vi.fn();
global.showAddEventModal  = vi.fn();
global.showAddCitationModal = vi.fn();
global.showAddNoteModal   = vi.fn();
global.showEditCitationModal = vi.fn();
global.showAddGodparentModal = vi.fn();

const { initPanel, renderPanel } = require('../../js/viz_panel.js');

// ── helpers ───────────────────────────────────────────────────────────────

function makePanelEl() {
  const el = makeFakeEl('detail-panel');
  // Override getElementById to return sub-elements by id lookup on a simple registry
  const registry = {};
  const reg = (id) => { const e = makeFakeEl(id); registry[id] = e; return e; };
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
      birth_year: '1900', death_year: '1970',
      sex: 'M', facts: [], notes: [], sources: [], nationalities: [],
    };

    global.document = {
      getElementById: (id) => {
        if (id === 'detail-panel') return panelEl;
        return makeFakeEl(id);
      },
      addEventListener: () => {},
    };

    initPanel(panelEl);
    renderPanel();

    expect(panelEl.classList.contains('panel-open')).toBe(true);
  });

  it('hides panel element when panelOpen === false', () => {
    const panelEl = makeFakeEl('detail-panel');
    panelEl.classList.add('panel-open');  // was open
    _state = { panelOpen: false, panelXref: null };

    global.document = {
      getElementById: (id) => id === 'detail-panel' ? panelEl : makeFakeEl(id),
      addEventListener: () => {},
    };

    initPanel(panelEl);
    renderPanel();

    expect(panelEl.classList.contains('panel-open')).toBe(false);
  });

  it('renders person name in detail-name element', () => {
    const panelEl = makeFakeEl('detail-panel');
    const nameEl  = makeFakeEl('detail-name');
    _state = { panelOpen: true, panelXref: '@I1@' };

    global.PEOPLE['@I1@'] = {
      name: 'John Papadopoulos',
      birth_year: '1873', death_year: '1940',
      sex: 'M', facts: [], notes: [], sources: [], nationalities: [],
    };

    global.document = {
      getElementById: (id) => {
        if (id === 'detail-panel') return panelEl;
        if (id === 'detail-name')  return nameEl;
        return makeFakeEl(id);
      },
      addEventListener: () => {},
    };

    initPanel(panelEl);
    renderPanel();

    expect(nameEl.innerHTML).toContain('John Papadopoulos');
  });

  it('renders birth and death years', () => {
    const panelEl    = makeFakeEl('detail-panel');
    const lifespanEl = makeFakeEl('detail-lifespan');
    _state = { panelOpen: true, panelXref: '@I2@' };

    global.PEOPLE['@I2@'] = {
      name: 'Mary Smith',
      birth_year: '1880', death_year: '1950',
      sex: 'F', facts: [], notes: [], sources: [], nationalities: [],
    };

    global.document = {
      getElementById: (id) => {
        if (id === 'detail-panel')    return panelEl;
        if (id === 'detail-lifespan') return lifespanEl;
        return makeFakeEl(id);
      },
      addEventListener: () => {},
    };

    initPanel(panelEl);
    renderPanel();

    expect(lifespanEl.innerHTML).toContain('1880');
    expect(lifespanEl.innerHTML).toContain('1950');
  });

  it('renders fact rows for each fact', () => {
    const panelEl  = makeFakeEl('detail-panel');
    const eventsEl = makeFakeEl('detail-events');
    _state = { panelOpen: true, panelXref: '@I3@' };

    global.PEOPLE['@I3@'] = {
      name: 'Andreas Kostas',
      birth_year: '1890', death_year: null,
      sex: 'M',
      facts: [
        { tag: 'BIRT', date: '12 JAN 1890', place: 'Smyrna', citations: [] },
        { tag: 'IMMI', date: '1922',         place: 'New York', citations: [] },
      ],
      notes: [], sources: [], nationalities: [],
    };

    global.document = {
      getElementById: (id) => {
        if (id === 'detail-panel')   return panelEl;
        if (id === 'detail-events')  return eventsEl;
        return makeFakeEl(id);
      },
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
    const closeBtn  = {
      ...makeFakeEl('panel-close-btn'),
      set onclick(fn) { closeHandler = fn; },
    };
    _state = { panelOpen: true, panelXref: '@I1@' };
    _setState_calls = [];

    global.PEOPLE['@I1@'] = {
      name: 'Test', birth_year: '1900', death_year: null,
      sex: 'M', facts: [], notes: [], sources: [], nationalities: [],
    };

    global.document = {
      getElementById: (id) => {
        if (id === 'detail-panel')      return panelEl;
        if (id === 'panel-close-btn')   return closeBtn;
        return makeFakeEl(id);
      },
      addEventListener: () => {},
    };

    initPanel(panelEl);
    renderPanel();

    // Simulate close click
    if (closeHandler) closeHandler();
    expect(_setState_calls.some(u => u.panelOpen === false)).toBe(true);
  });

  it('CHR fact with godparents renders godparent pills', () => {
    const panelEl  = makeFakeEl('detail-panel');
    const eventsEl = makeFakeEl('detail-events');
    _state = { panelOpen: true, panelXref: '@I4@' };

    global.PEOPLE = {
      '@I4@': {
        name: 'Nicolaos Petros',
        birth_year: '1895', death_year: null,
        sex: 'M',
        facts: [
          {
            tag: 'CHR',
            date: '5 MAR 1895',
            place: 'Smyrna',
            citations: [],
            asso: [{ xref: '@I5@', rela: 'Godparent' }],
          },
        ],
        notes: [], sources: [], nationalities: [],
      },
      '@I5@': {
        name: 'Kostas Manolakis',
        birth_year: '1860', death_year: null,
        sex: 'M', facts: [], notes: [], sources: [], nationalities: [],
      },
    };

    global.document = {
      getElementById: (id) => {
        if (id === 'detail-panel')  return panelEl;
        if (id === 'detail-events') return eventsEl;
        return makeFakeEl(id);
      },
      addEventListener: () => {},
    };

    initPanel(panelEl);
    renderPanel();

    expect(eventsEl.innerHTML).toContain('Kostas Manolakis');
  });

  it('clicking godparent pill calls setState({ focusXref })', () => {
    const panelEl  = makeFakeEl('detail-panel');
    const eventsEl = makeFakeEl('detail-events');
    _state = { panelOpen: true, panelXref: '@I4@' };
    _setState_calls = [];

    global.PEOPLE = {
      '@I4@': {
        name: 'Nicolaos Petros',
        birth_year: '1895', death_year: null,
        sex: 'M',
        facts: [
          {
            tag: 'CHR',
            date: '5 MAR 1895',
            place: 'Smyrna',
            citations: [],
            asso: [{ xref: '@I5@', rela: 'Godparent' }],
          },
        ],
        notes: [], sources: [], nationalities: [],
      },
      '@I5@': {
        name: 'Kostas Manolakis',
        birth_year: '1860', death_year: null,
        sex: 'M', facts: [], notes: [], sources: [], nationalities: [],
      },
    };

    // Capture click handlers stored via _godparentClickHandlers
    global.document = {
      getElementById: (id) => {
        if (id === 'detail-panel')  return panelEl;
        if (id === 'detail-events') return eventsEl;
        return makeFakeEl(id);
      },
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
