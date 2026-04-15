import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const {
  escHtml, linkify,
  fmtDate, fmtPlace, fmtAge,
  buildProse, dotColor,
  collapseResidences,
} = require('../../js/viz_detail.js');

// ── escHtml ────────────────────────────────────────────────────────────────

describe('escHtml', () => {
  it('escapes & < > "', () => {
    expect(escHtml('a & b')).toBe('a &amp; b');
    expect(escHtml('<b>')).toBe('&lt;b&gt;');
    expect(escHtml('"hi"')).toBe('&quot;hi&quot;');
  });
  it('leaves plain text unchanged', () => {
    expect(escHtml('hello world')).toBe('hello world');
  });
});

// ── fmtDate ────────────────────────────────────────────────────────────────

describe('fmtDate', () => {
  it('returns empty string for null/undefined', () => {
    expect(fmtDate(null)).toBe('');
    expect(fmtDate('')).toBe('');
    expect(fmtDate(undefined)).toBe('');
  });

  it('formats a full day-month-year date', () => {
    expect(fmtDate('5 JAN 1900')).toBe('January 5, 1900');
    expect(fmtDate('15 DEC 1999')).toBe('December 15, 1999');
  });

  it('formats a month-year date', () => {
    expect(fmtDate('MAR 1850')).toBe('March 1850');
  });

  it('formats a year-only date', () => {
    expect(fmtDate('1923')).toBe('1923');
  });

  it('handles ABT prefix', () => {
    expect(fmtDate('ABT 1900')).toBe('around 1900');
  });

  it('handles BEF prefix', () => {
    expect(fmtDate('BEF 1900')).toBe('before 1900');
  });

  it('handles AFT prefix', () => {
    expect(fmtDate('AFT 1900')).toBe('after 1900');
  });

  it('handles CAL prefix', () => {
    expect(fmtDate('CAL 1900')).toBe('around 1900');
  });

  it('handles BET...AND ranges', () => {
    const result = fmtDate('BET 1900 AND 1910');
    expect(result).toBe('1900 \u2013 1910');
  });

  it('is case-insensitive for input', () => {
    expect(fmtDate('5 jan 1900')).toBe('January 5, 1900');
  });

  it('passes through unrecognised formats', () => {
    expect(fmtDate('circa 1850')).toBe('circa 1850');
  });
});

// ── fmtPlace ───────────────────────────────────────────────────────────────

describe('fmtPlace', () => {
  it('returns empty string for null/empty', () => {
    expect(fmtPlace(null)).toBe('');
    expect(fmtPlace('')).toBe('');
  });

  it('returns single-part place unchanged', () => {
    expect(fmtPlace('Istanbul')).toBe('Istanbul');
  });

  it('strips USA country suffix, leaving City, State', () => {
    expect(fmtPlace('Springfield, Illinois, USA')).toBe('Springfield, Illinois');
  });

  it('handles USA with county, keeping City, State', () => {
    expect(fmtPlace('Springfield, Sangamon County, Illinois, USA'))
      .toBe('Springfield, Illinois');
  });

  it('maps District of Columbia → D.C.', () => {
    expect(fmtPlace('Washington, District of Columbia, USA')).toBe('Washington, D.C.');
  });

  it('uses first+last parts for non-US multi-part places', () => {
    expect(fmtPlace('Smyrna, Ottoman Empire')).toBe('Smyrna, Ottoman Empire');
    expect(fmtPlace('Athens, Attica, Greece')).toBe('Athens, Greece');
  });
});

// ── fmtAge ─────────────────────────────────────────────────────────────────

describe('fmtAge', () => {
  it('returns empty string for null/empty', () => {
    expect(fmtAge(null)).toBe('');
    expect(fmtAge('')).toBe('');
  });

  it('INFANT → in infancy', () => {
    expect(fmtAge('INFANT')).toBe('in infancy');
  });

  it('STILLBORN → stillborn', () => {
    expect(fmtAge('STILLBORN')).toBe('stillborn');
  });

  it('expands GEDCOM age codes', () => {
    expect(fmtAge('2y 3m')).toBe('2 years 3 months');
    expect(fmtAge('1y')).toBe('1 year');
  });

  it('handles < and > prefixes', () => {
    expect(fmtAge('<1y')).toBe('under 1 year');
    expect(fmtAge('>80y')).toBe('over 80 years');
  });
});

// ── buildProse ─────────────────────────────────────────────────────────────

describe('buildProse', () => {
  it('BIRT with place', () => {
    const { prose } = buildProse({ tag: 'BIRT', place: 'Smyrna, Ottoman Empire', date: null });
    expect(prose).toBe('Born in Smyrna, Ottoman Empire');
  });

  it('BIRT with date only', () => {
    const { prose } = buildProse({ tag: 'BIRT', place: '', date: '5 JAN 1900' });
    expect(prose).toBe('Born January 5, 1900');
  });

  it('DEAT with cause and place', () => {
    const { prose } = buildProse({ tag: 'DEAT', place: 'Paris, France', cause: 'pneumonia', date: null });
    expect(prose).toBe('Died of pneumonia in Paris, France');
  });

  it('DEAT with age stillborn', () => {
    const { prose } = buildProse({ tag: 'DEAT', place: '', date: null, age: 'STILLBORN' });
    expect(prose).toBe('Stillborn');
  });

  it('RESI with place', () => {
    const { prose } = buildProse({ tag: 'RESI', place: 'Athens, Greece', date: null });
    expect(prose).toBe('Lived in Athens, Greece');
  });

  it('OCCU with job title', () => {
    const { prose } = buildProse({ tag: 'OCCU', inline_val: 'Merchant', place: '', date: null });
    expect(prose).toBe('Worked as Merchant');
  });

  it('NATI with type', () => {
    const { prose } = buildProse({ tag: 'NATI', type: 'Greek', place: '', date: null });
    expect(prose).toBe('Nationality: Greek');
  });

  it('MARR with spouse name', () => {
    const { prose } = buildProse({ tag: 'MARR', spouse: 'Jane Doe', place: '', date: null });
    expect(prose).toBe('Married Jane Doe');
  });

  it('FACT AKA uses note', () => {
    const { prose } = buildProse({ tag: 'FACT', type: 'AKA', note: 'Johnny', date: null });
    expect(prose).toBe('Also known as: Johnny');
  });
});

// ── dotColor ───────────────────────────────────────────────────────────────

describe('dotColor', () => {
  it('BIRT and DEAT get light colour', () => {
    expect(dotColor({ tag: 'BIRT' })).toBe('#f1f5f9');
    expect(dotColor({ tag: 'DEAT' })).toBe('#f1f5f9');
  });

  it('RESI gets blue', () => {
    expect(dotColor({ tag: 'RESI' })).toBe('#38bdf8');
  });

  it('Name Change overrides tag colour', () => {
    expect(dotColor({ tag: 'FACT', type: 'Name Change' })).toBe('#f97316');
  });

  it('MARR gets purple', () => {
    expect(dotColor({ tag: 'MARR' })).toBe('#e879f9');
  });

  it('unknown tag gets grey', () => {
    expect(dotColor({ tag: 'UNKN' })).toBe('#64748b');
  });
});

// ── collapseResidences ─────────────────────────────────────────────────────

describe('collapseResidences', () => {
  it('returns non-RESI events unchanged', () => {
    const events = [{ tag: 'BIRT', place: '', date: '1900' }];
    expect(collapseResidences(events)).toEqual(events);
  });

  it('does not collapse a single RESI', () => {
    const events = [{ tag: 'RESI', place: 'Boston, Massachusetts, USA', date: '1920' }];
    const result = collapseResidences(events);
    expect(result).toHaveLength(1);
    expect(result[0]._yearRange).toBeUndefined();
  });

  it('collapses consecutive RESI events at the same place', () => {
    const events = [
      { tag: 'RESI', place: 'Boston, Massachusetts, USA', date: '1920' },
      { tag: 'RESI', place: 'Boston, Massachusetts, USA', date: '1925' },
      { tag: 'RESI', place: 'Boston, Massachusetts, USA', date: '1930' },
    ];
    const result = collapseResidences(events);
    expect(result).toHaveLength(1);
    expect(result[0]._yearRange).toBe('1920\u20131930');
  });

  it('does not collapse RESI at different places', () => {
    const events = [
      { tag: 'RESI', place: 'Boston, Massachusetts, USA', date: '1920' },
      { tag: 'RESI', place: 'New York, New York, USA',    date: '1925' },
    ];
    const result = collapseResidences(events);
    expect(result).toHaveLength(2);
  });

  it('preserves notes across collapsed residences', () => {
    const events = [
      { tag: 'RESI', place: 'Boston, Massachusetts, USA', date: '1920', note: 'Apartment on Beacon St' },
      { tag: 'RESI', place: 'Boston, Massachusetts, USA', date: '1925', note: 'Moved to Back Bay' },
    ];
    const result = collapseResidences(events);
    expect(result[0].note).toContain('1920: Apartment on Beacon St');
    expect(result[0].note).toContain('1925: Moved to Back Bay');
  });
});
