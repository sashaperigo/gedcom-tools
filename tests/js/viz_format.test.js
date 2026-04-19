/**
 * Unit tests for fmtDate and fmtPlace, exported from viz_panel.js.
 *
 * These functions were silently removed when viz_detail.js was replaced.
 * No previous tests guarded them, so their absence went unnoticed.
 * This file prevents that regression from recurring.
 */

import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// Stub the minimum globals needed to load viz_panel.js
global.document       = { getElementById: () => null, addEventListener: () => {} };
global.PEOPLE         = {};
global.SOURCES        = {};
global.ALL_PEOPLE     = [];
global.setState       = () => {};
global.getState       = () => ({});
global.onStateChange  = () => {};
global.apiDeleteCitation = () => Promise.resolve();
global.showEditNameModal  = () => {};
global.showAddEventModal  = () => {};
global.showAddCitationModal = () => {};
global.showAddNoteModal   = () => {};
global.showEditCitationModal = () => {};
global.showAddGodparentModal = () => {};

const { fmtDate, fmtPlace } = require('../../js/viz_panel.js');

// ── fmtDate ───────────────────────────────────────────────────────────────

describe('fmtDate', () => {
  it('"ABT 1820" → "about 1820"', () => {
    expect(fmtDate('ABT 1820')).toBe('about 1820');
  });

  it('"BEF 1900" → "before 1900"', () => {
    expect(fmtDate('BEF 1900')).toBe('before 1900');
  });

  it('"AFT 1900" → "after 1900"', () => {
    expect(fmtDate('AFT 1900')).toBe('after 1900');
  });

  it('"CAL 1835" → "about 1835"', () => {
    expect(fmtDate('CAL 1835')).toBe('about 1835');
  });

  it('"EST 1835" → "about 1835"', () => {
    expect(fmtDate('EST 1835')).toBe('about 1835');
  });

  it('"BET SEP 1942 AND DEC 1944" → "September 1942 – December 1944"', () => {
    // fmtDate recursively formats each half so SEP 1942 → September 1942
    expect(fmtDate('BET SEP 1942 AND DEC 1944')).toBe('September 1942 \u2013 December 1944');
  });

  it('"26 FEB 1785" → "February 26, 1785"', () => {
    expect(fmtDate('26 FEB 1785')).toBe('February 26, 1785');
  });

  it('"MAR 1901" → "March 1901"', () => {
    expect(fmtDate('MAR 1901')).toBe('March 1901');
  });

  it('"1835" → "1835" (year-only pass-through)', () => {
    expect(fmtDate('1835')).toBe('1835');
  });

  it('empty string → ""', () => {
    expect(fmtDate('')).toBe('');
  });

  it('null → ""', () => {
    expect(fmtDate(null)).toBe('');
  });
});

// ── fmtPlace ──────────────────────────────────────────────────────────────

describe('fmtPlace', () => {
  it('US with county: "Springfield, Sangamon, Illinois, USA" → "Springfield, Illinois"', () => {
    expect(fmtPlace('Springfield, Sangamon, Illinois, USA')).toBe('Springfield, Illinois');
  });

  it('International multi-part: "Corfu, Kerkira, Ionian Islands, Greece" → "Corfu, Greece"', () => {
    expect(fmtPlace('Corfu, Kerkira, Ionian Islands, Greece')).toBe('Corfu, Greece');
  });

  it('Two-part unchanged: "Mexico City, Mexico" → "Mexico City, Mexico"', () => {
    expect(fmtPlace('Mexico City, Mexico')).toBe('Mexico City, Mexico');
  });

  it('"Washington, District of Columbia, USA" → "Washington, D.C."', () => {
    expect(fmtPlace('Washington, District of Columbia, USA')).toBe('Washington, D.C.');
  });

  it('empty string → ""', () => {
    expect(fmtPlace('')).toBe('');
  });

  it('null → ""', () => {
    expect(fmtPlace(null)).toBe('');
  });

  it('single part → returned as-is', () => {
    expect(fmtPlace('Athens')).toBe('Athens');
  });
});
