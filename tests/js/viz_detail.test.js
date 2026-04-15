import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// viz_detail.js references DOM globals and some browser-only APIs; stub the
// minimum needed so the module can be imported without errors.
global.document = {
  getElementById: () => null,
  addEventListener: () => {},
};
global.EVENT_LABELS = {
  BIRT: 'Birth', DEAT: 'Death', BURI: 'Burial', RESI: 'Residence',
  OCCU: 'Occupation', EVEN: 'Event', FACT: 'Fact', MARR: 'Marriage',
  NATI: 'Nationality', IMMI: 'Immigration', EMIG: 'Emigration',
};
global.escHtml = s => String(s)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const { buildSourceBadgeHtml } = require('../../js/viz_detail.js');

// ── buildSourceBadgeHtml ──────────────────────────────────────────────────

describe('buildSourceBadgeHtml', () => {
  it('returns empty string when citations is undefined', () => {
    expect(buildSourceBadgeHtml(undefined, '@I1@', 0)).toBe('');
  });

  it('returns empty string when citations is empty array', () => {
    expect(buildSourceBadgeHtml([], '@I1@', 0)).toBe('');
  });

  it('renders badge for a single citation', () => {
    const html = buildSourceBadgeHtml([{ sour_xref: '@S1@', page: '1' }], '@I1@', 0);
    expect(html).toContain('evt-src-badge');
    expect(html).toContain('1 src');
  });

  it('renders the count for multiple citations', () => {
    const citations = [
      { sour_xref: '@S1@', page: null },
      { sour_xref: '@S2@', page: '7' },
      { sour_xref: '@S3@', page: null },
    ];
    const html = buildSourceBadgeHtml(citations, '@I1@', 2);
    expect(html).toContain('3 src');
  });

  it('includes an onclick calling openSourcesModal with xref and origIdx', () => {
    const html = buildSourceBadgeHtml([{ sour_xref: '@S1@', page: null }], '@I1@', 5);
    expect(html).toContain('openSourcesModal');
    expect(html).toContain('@I1@');
    expect(html).toContain('5');
  });

  it('stops propagation to avoid triggering parent click handlers', () => {
    const html = buildSourceBadgeHtml([{ sour_xref: '@S1@', page: null }], '@I1@', 0);
    expect(html).toContain('stopPropagation');
  });

  it('HTML-escapes the xref in the onclick attribute', () => {
    // xrefs with special chars shouldn't break the attribute
    const html = buildSourceBadgeHtml([{ sour_xref: '@S1@', page: null }], '@I1@', 0);
    // The xref should appear properly escaped (no raw double-quotes breaking the attribute)
    expect(html).not.toMatch(/onclick="[^"]*"[^"]*"/);
  });
});
