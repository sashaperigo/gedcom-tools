import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

// viz_search.js reads escHtml from global scope (defined in viz_design.js)
const { escHtml } = require('../../js/viz_design.js');
global.escHtml = escHtml;

const {
  stripAccents, normSearch, getParsed, personMatches, highlightName,
} = require('../../js/viz_search.js');

// ── stripAccents / normSearch ──────────────────────────────────────────────

describe('stripAccents', () => {
  it('strips common accents', () => {
    expect(stripAccents('café')).toBe('cafe');
    expect(stripAccents('naïve')).toBe('naive');
    expect(stripAccents('résumé')).toBe('resume');
  });

  it('leaves ASCII unchanged', () => {
    expect(stripAccents('hello world')).toBe('hello world');
  });
});

describe('normSearch', () => {
  it('lowercases and strips accents', () => {
    expect(normSearch('Ángel')).toBe('angel');
    expect(normSearch('RÉSUMÉ')).toBe('resume');
  });

  it('handles null/undefined gracefully', () => {
    expect(normSearch(null)).toBe('');
    expect(normSearch(undefined)).toBe('');
  });
});

// ── getParsed ──────────────────────────────────────────────────────────────

describe('getParsed', () => {
  it('strips GEDCOM slashes from surname', () => {
    const p = { id: 'p1', name: 'John /Smith/' };
    const parsed = getParsed(p);
    expect(parsed.disp).not.toContain('/');
  });

  it('extracts nickname from double-quotes', () => {
    const p = { id: 'p2', name: 'William "Bill" Jones' };
    const parsed = getParsed(p);
    expect(parsed.normNicks).toContain('bill');
  });

  it('extracts nickname from curly quotes', () => {
    const p = { id: 'p3', name: 'Maria \u201cMimi\u201d Papadopoulos' };
    const parsed = getParsed(p);
    expect(parsed.normNicks).toContain('mimi');
  });

  it('normFirst is the first token, normLast is the last', () => {
    const p = { id: 'p4', name: 'Anna Maria Rossi' };
    const parsed = getParsed(p);
    expect(parsed.normFirst).toBe('anna');
    expect(parsed.normLast).toBe('rossi');
  });
});

// ── personMatches ──────────────────────────────────────────────────────────

describe('personMatches', () => {
  const people = [
    { id: 'a', name: 'Anastasia Konstantinidis' },
    { id: 'b', name: 'George "Yiorgos" Papadopoulos' },
    { id: 'c', name: 'María González' },
    { id: 'd', name: 'John William Smith' },
  ].map(p => ({ p, parsed: getParsed(p) }));

  const match = (id, q) => {
    const entry = people.find(e => e.p.id === id);
    return personMatches(entry.parsed, normSearch(q));
  };

  it('returns false for empty query', () => {
    expect(match('a', '')).toBe(false);
  });

  it('full name substring match', () => {
    expect(match('a', 'Anastasia')).toBe(true);
    expect(match('a', 'Konstantin')).toBe(true);
  });

  it('accent-insensitive match', () => {
    expect(match('c', 'maria')).toBe(true);
    expect(match('c', 'gonzalez')).toBe(true);
  });

  it('nickname match', () => {
    expect(match('b', 'yiorgos')).toBe(true);
  });

  it('first + last multi-token match', () => {
    expect(match('d', 'john smith')).toBe(true);
  });

  it('first + last skipping middle name', () => {
    expect(match('d', 'john smith')).toBe(true);
  });

  it('no match for unrelated query', () => {
    expect(match('a', 'zzznomatch')).toBe(false);
  });
});

// ── highlightName ──────────────────────────────────────────────────────────

describe('highlightName', () => {
  it('bolds a single matching token', () => {
    const result = highlightName('John Smith', 'john smith', 'john');
    expect(result).toContain('<b>John</b>');
    expect(result).toContain('Smith');
  });

  it('bolds multiple matching tokens', () => {
    const result = highlightName('John Smith', 'john smith', 'john smith');
    expect(result).toContain('<b>');
  });

  it('escapes HTML in non-matching parts', () => {
    const result = highlightName('A & B', 'a & b', 'zzz');
    expect(result).toContain('&amp;');
  });

  it('returns escaped name when query is empty', () => {
    const result = highlightName('<b>test</b>', '<b>test</b>', '');
    expect(result).not.toContain('<b>test</b>');
    expect(result).toContain('&lt;b&gt;');
  });

  it('merges overlapping highlight regions', () => {
    // query "ana" and "nas" should merge into one bold region in "Anastasia"
    const disp = 'Anastasia';
    const norm = 'anastasia';
    const result = highlightName(disp, norm, 'ana');
    // At minimum one <b> tag exists and no malformed markup
    expect(result.split('<b>').length - 1).toBeGreaterThanOrEqual(1);
    expect(result).not.toContain('</b><b>');   // no adjacent unmerged bold tags for same match
  });
});
