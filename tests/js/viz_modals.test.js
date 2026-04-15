import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// viz_modals.js references DOM globals; stub the minimum needed for import.
global.document = {
  getElementById: () => null,
  addEventListener: () => {},
};
global.ALL_PEOPLE = [];
global.PEOPLE = {};
global.SOURCES = {};
global.EVENT_LABELS = { BIRT: 'Birth', DEAT: 'Death', RESI: 'Residence', EMIG: 'Emigration' };
global.escHtml = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
global.ADDR_BY_PLACE = {};

const {
  _filterSpouseResults, _isFamEventTag, _buildSpouseResultsHtml, _FACT_PRESETS,
  openSourcesModal, closeSourcesModal, _buildSourcesModalContent,
} = require('../../js/viz_modals.js');

// ── _isFamEventTag ────────────────────────────────────────────────────────

describe('_isFamEventTag', () => {
  it('returns true for MARR', () => {
    expect(_isFamEventTag('MARR')).toBe(true);
  });

  it('returns true for DIV', () => {
    expect(_isFamEventTag('DIV')).toBe(true);
  });

  it('returns false for RESI', () => {
    expect(_isFamEventTag('RESI')).toBe(false);
  });

  it('returns false for BIRT', () => {
    expect(_isFamEventTag('BIRT')).toBe(false);
  });

  it('returns false for OCCU', () => {
    expect(_isFamEventTag('OCCU')).toBe(false);
  });

  it('returns false for empty string', () => {
    expect(_isFamEventTag('')).toBe(false);
  });
});

// ── _filterSpouseResults ──────────────────────────────────────────────────

const SAMPLE_PEOPLE = [
  { id: '@I1@', name: 'Rose Smith', birth_year: '1990', death_year: '' },
  { id: '@I2@', name: 'James Smith', birth_year: '1960', death_year: '' },
  { id: '@I3@', name: 'Clara Jones', birth_year: '1963', death_year: '' },
  { id: '@I4@', name: 'Patrick Smith', birth_year: '1930', death_year: '2005' },
  { id: '@I5@', name: 'Mary O\'Brien', birth_year: '1932', death_year: '' },
  { id: '@I6@', name: 'John Jones', birth_year: '1935', death_year: '2010' },
  { id: '@I7@', name: 'Jane Brown', birth_year: '1938', death_year: '' },
  { id: '@I8@', name: 'William Brown', birth_year: '1908', death_year: '1975' },
  { id: '@I9@', name: 'Helen Taylor', birth_year: '1910', death_year: '' },
  { id: '@I10@', name: 'Thomas Jones', birth_year: '1905', death_year: '' },
  { id: '@I11@', name: 'Alice Smith', birth_year: '1992', death_year: '' },
  { id: '@I12@', name: 'Mark Davis', birth_year: '1988', death_year: '' },
  { id: '@I13@', name: 'Robert Smith', birth_year: '1962', death_year: '' },
];

describe('_filterSpouseResults', () => {
  it('returns empty array for empty query', () => {
    expect(_filterSpouseResults('', SAMPLE_PEOPLE)).toEqual([]);
  });

  it('returns empty array for whitespace-only query', () => {
    expect(_filterSpouseResults('   ', SAMPLE_PEOPLE)).toEqual([]);
  });

  it('returns matching people for a name substring', () => {
    const results = _filterSpouseResults('smith', SAMPLE_PEOPLE);
    const names = results.map(p => p.name);
    expect(names).toContain('Rose Smith');
    expect(names).toContain('James Smith');
    expect(names).toContain('Alice Smith');
    expect(names).toContain('Robert Smith');
    expect(names).toContain('Patrick Smith');
    expect(names).not.toContain('Clara Jones');
  });

  it('is case-insensitive', () => {
    const lower = _filterSpouseResults('smith', SAMPLE_PEOPLE);
    const upper = _filterSpouseResults('SMITH', SAMPLE_PEOPLE);
    const mixed = _filterSpouseResults('SmItH', SAMPLE_PEOPLE);
    expect(lower.map(p => p.id)).toEqual(upper.map(p => p.id));
    expect(lower.map(p => p.id)).toEqual(mixed.map(p => p.id));
  });

  it('returns at most 12 results', () => {
    // All 13 people have an 'a' in their name somewhere; result must be capped
    const results = _filterSpouseResults('a', SAMPLE_PEOPLE);
    expect(results.length).toBeLessThanOrEqual(12);
  });

  it('returns all results when fewer than 12 match', () => {
    const results = _filterSpouseResults('jones', SAMPLE_PEOPLE);
    // Clara Jones, John Jones, Thomas Jones = 3 results
    expect(results.length).toBe(3);
  });

  it('returns empty array when nothing matches', () => {
    const results = _filterSpouseResults('zzznomatch', SAMPLE_PEOPLE);
    expect(results).toEqual([]);
  });

  it('preserves the full person object in results', () => {
    const results = _filterSpouseResults('mark', SAMPLE_PEOPLE);
    expect(results.length).toBe(1);
    expect(results[0]).toMatchObject({ id: '@I12@', name: 'Mark Davis' });
  });
});

// ── _buildSpouseResultsHtml (regression: data-attribute click, not inline onclick) ──

describe('_buildSpouseResultsHtml', () => {
  const people = [
    { id: '@I1@', name: 'Rose Smith', birth_year: '1990', death_year: '' },
    { id: '@I2@', name: 'James "Jimmy" O\'Brien', birth_year: '', death_year: '' },
  ];

  it('renders data-xref and data-name attributes for each item', () => {
    const html = _buildSpouseResultsHtml(people);
    expect(html).toContain('data-xref="@I1@"');
    expect(html).toContain('data-name="Rose Smith"');
    expect(html).toContain('data-xref="@I2@"');
  });

  it('does NOT use inline onclick handlers (regression: double-quote quoting bug)', () => {
    // The original bug: JSON.stringify inside onclick="..." broke attribute boundaries.
    // Clicks silently failed when xrefs like @I1@ were JSON-stringified as "@I1@"
    // and embedded directly in the onclick attribute value.
    const html = _buildSpouseResultsHtml(people);
    expect(html).not.toContain('onclick=');
  });

  it('HTML-escapes special characters in names and xrefs', () => {
    const html = _buildSpouseResultsHtml([
      { id: '@I99@', name: 'A & B <Test>', birth_year: '' },
    ]);
    expect(html).not.toContain('A & B');
    expect(html).toContain('A &amp; B');
    expect(html).not.toContain('<Test>');
    expect(html).toContain('&lt;Test&gt;');
  });

  it('includes birth year in parentheses when present', () => {
    const html = _buildSpouseResultsHtml([people[0]]);
    expect(html).toContain('(1990)');
  });

  it('omits birth year when absent', () => {
    const html = _buildSpouseResultsHtml([people[1]]);
    expect(html).not.toMatch(/\(\s*\)/);
  });

  it('returns empty string for empty array', () => {
    expect(_buildSpouseResultsHtml([])).toBe('');
  });
});

// ── _FACT_PRESETS ─────────────────────────────────────────────────────────

describe('_FACT_PRESETS', () => {
  const EXPECTED_KEYS = [
    'FACT:Languages',
    'FACT:Literacy',
    'FACT:Politics',
    'FACT:Medical condition',
    'DSCR',
    'NCHI',
  ];

  it('exports an object', () => {
    expect(typeof _FACT_PRESETS).toBe('object');
    expect(_FACT_PRESETS).not.toBeNull();
  });

  it('contains all six fact presets', () => {
    for (const key of EXPECTED_KEYS) {
      expect(_FACT_PRESETS).toHaveProperty(key);
    }
  });

  it('every FACT: preset has baseTag FACT and a non-empty type', () => {
    for (const [key, preset] of Object.entries(_FACT_PRESETS)) {
      if (key.startsWith('FACT:')) {
        expect(preset.baseTag).toBe('FACT');
        expect(typeof preset.type).toBe('string');
        expect(preset.type.length).toBeGreaterThan(0);
      }
    }
  });

  it('DSCR preset has baseTag DSCR and showInline true', () => {
    expect(_FACT_PRESETS['DSCR'].baseTag).toBe('DSCR');
    expect(_FACT_PRESETS['DSCR'].showInline).toBe(true);
  });

  it('NCHI preset has baseTag NCHI and showInline true', () => {
    expect(_FACT_PRESETS['NCHI'].baseTag).toBe('NCHI');
    expect(_FACT_PRESETS['NCHI'].showInline).toBe(true);
  });

  it('every preset has a label string', () => {
    for (const preset of Object.values(_FACT_PRESETS)) {
      expect(typeof preset.label).toBe('string');
      expect(preset.label.length).toBeGreaterThan(0);
    }
  });

  it('FACT: presets have showInline false (type field, not inline value)', () => {
    for (const [key, preset] of Object.entries(_FACT_PRESETS)) {
      if (key.startsWith('FACT:')) {
        expect(preset.showInline).toBe(false);
      }
    }
  });

  it('FACT:Languages type matches Languages', () => {
    expect(_FACT_PRESETS['FACT:Languages'].type).toBe('Languages');
  });

  it('DSCR has an inlineLabel', () => {
    expect(typeof _FACT_PRESETS['DSCR'].inlineLabel).toBe('string');
    expect(_FACT_PRESETS['DSCR'].inlineLabel.length).toBeGreaterThan(0);
  });

  it('NCHI has an inlineLabel', () => {
    expect(typeof _FACT_PRESETS['NCHI'].inlineLabel).toBe('string');
    expect(_FACT_PRESETS['NCHI'].inlineLabel.length).toBeGreaterThan(0);
  });
});

// ── _buildSourcesModalContent ─────────────────────────────────────────────

describe('_buildSourcesModalContent', () => {
  const SOURCES = {
    '@S1@': { title: 'Ellis Island Records', url: 'https://example.com/s1' },
    '@S2@': { title: 'Greek Orthodox Ledger', url: null },
  };

  it('returns fallback message when citations is empty', () => {
    const html = _buildSourcesModalContent([], SOURCES);
    expect(html).toContain('No sources recorded');
  });

  it('returns fallback message when citations is null', () => {
    const html = _buildSourcesModalContent(null, SOURCES);
    expect(html).toContain('No sources recorded');
  });

  it('renders source title as link when URL is present', () => {
    const html = _buildSourcesModalContent([{ sour_xref: '@S1@', page: null }], SOURCES);
    expect(html).toContain('<a ');
    expect(html).toContain('Ellis Island Records');
    expect(html).toContain('https://example.com/s1');
  });

  it('renders source title as plain text when URL is absent', () => {
    const html = _buildSourcesModalContent([{ sour_xref: '@S2@', page: null }], SOURCES);
    expect(html).not.toContain('<a ');
    expect(html).toContain('Greek Orthodox Ledger');
  });

  it('renders page info when page is present', () => {
    const html = _buildSourcesModalContent([{ sour_xref: '@S1@', page: '47' }], SOURCES);
    expect(html).toContain('src-modal-page');
    expect(html).toContain('47');
  });

  it('omits page element when page is null', () => {
    const html = _buildSourcesModalContent([{ sour_xref: '@S1@', page: null }], SOURCES);
    expect(html).not.toContain('src-modal-page');
  });

  it('HTML-escapes source title', () => {
    const evilSources = { '@S1@': { title: '<script>alert(1)</script>', url: null } };
    const html = _buildSourcesModalContent([{ sour_xref: '@S1@', page: null }], evilSources);
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('renders all sources when multiple citations', () => {
    const html = _buildSourcesModalContent(
      [{ sour_xref: '@S1@', page: '3' }, { sour_xref: '@S2@', page: null }],
      SOURCES
    );
    expect(html).toContain('Ellis Island Records');
    expect(html).toContain('Greek Orthodox Ledger');
  });

  it('shows xref as fallback when citation xref is not in SOURCES', () => {
    const html = _buildSourcesModalContent([{ sour_xref: '@S99@', page: null }], SOURCES);
    expect(html).toContain('@S99@');
  });
});

// ── openSourcesModal / closeSourcesModal ──────────────────────────────────

describe('openSourcesModal and closeSourcesModal', () => {
  // Build a minimal DOM double that records classList.add/remove calls.
  function makeFakeElement(id) {
    return {
      id,
      textContent: '',
      innerHTML: '',
      classList: {
        _classes: new Set(),
        add(c)    { this._classes.add(c); },
        remove(c) { this._classes.delete(c); },
        contains(c) { return this._classes.has(c); },
      },
    };
  }

  let overlay, title, list;

  beforeEach(() => {
    overlay = makeFakeElement('sources-modal-overlay');
    title   = makeFakeElement('sources-modal-title');
    list    = makeFakeElement('sources-modal-list');

    global.document = {
      getElementById(id) {
        if (id === 'sources-modal-overlay') return overlay;
        if (id === 'sources-modal-title')   return title;
        if (id === 'sources-modal-list')    return list;
        return null;
      },
      addEventListener: () => {},
    };

    global.PEOPLE = {
      '@I1@': {
        events: [
          { tag: 'BIRT', date: '1900', type: null, citations: [{ sour_xref: '@S1@', page: '5' }] },
          { tag: 'DEAT', date: '1970', type: null, citations: [] },
        ],
      },
    };
    global.SOURCES = {
      '@S1@': { title: 'Birth Register', url: null },
    };
    global.EVENT_LABELS = { BIRT: 'Birth', DEAT: 'Death' };
  });

  it('adds "open" class to overlay', () => {
    openSourcesModal('@I1@', 0);
    expect(overlay.classList.contains('open')).toBe(true);
  });

  it('sets title text to include the event label and year', () => {
    openSourcesModal('@I1@', 0);
    expect(title.textContent).toContain('Birth');
    expect(title.textContent).toContain('1900');
  });

  it('populates the list with source content', () => {
    openSourcesModal('@I1@', 0);
    expect(list.innerHTML).toContain('Birth Register');
  });

  it('closeSourcesModal removes "open" class from overlay', () => {
    overlay.classList.add('open');
    closeSourcesModal();
    expect(overlay.classList.contains('open')).toBe(false);
  });

  it('shows fallback text for an event with no citations', () => {
    openSourcesModal('@I1@', 1);
    expect(list.innerHTML).toContain('No sources recorded');
  });
});
