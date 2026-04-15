import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// viz_modals.js references DOM globals; stub the minimum needed for import.
global.document = {
  getElementById: () => null,
  addEventListener: () => {},
};
global.ALL_PEOPLE = [];
global.PEOPLE = {};
global.escHtml = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
global.ADDR_BY_PLACE = {};

const { _filterSpouseResults, _isFamEventTag } = require('../../js/viz_modals.js');

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
