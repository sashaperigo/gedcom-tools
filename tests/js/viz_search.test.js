import { describe, it, expect, beforeEach } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(
    import.meta.url);

// viz_search.js reads escHtml from global scope (defined in viz_design.js)
const { escHtml } = require('../../js/viz_design.js');
global.escHtml = escHtml;

const {
    stripAccents,
    normSearch,
    getParsed,
    personMatches,
    highlightName,
    matchScore,
    estDob,
    sortHits,
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

// ── matchScore / estDob / sortHits ─────────────────────────────────────────

describe('matchScore', () => {
    const score = (name, q) => matchScore(getParsed({ id: name, name }), normSearch(q));

    it('tier 1: exact first-name match', () => {
        expect(score('John Smith', 'john')).toBe(1);
    });

    it('tier 2: exact last-name or nickname match', () => {
        expect(score('Mary Johnson', 'johnson')).toBe(2);
        expect(score('William "Bill" Jones', 'bill')).toBe(2);
    });

    it('tier 3: starts-with on first name', () => {
        expect(score('Johnny Aslanidis', 'john')).toBe(3);
        expect(score('Johnathan Reeves', 'john')).toBe(3);
    });

    it('tier 4: starts-with on last name or nickname', () => {
        expect(score('Mary Johnson', 'john')).toBe(4);
    });

    it('tier 5: substring only', () => {
        expect(score('Aaron Stjohnson', 'john')).toBe(5);
    });

    it('multi-token query scores by first token vs first name', () => {
        expect(score('John Papadopoulos', 'john pap')).toBe(1);
        expect(score('Johnny Papadakis', 'john pap')).toBe(3);
    });
});

describe('estDob', () => {
    it('returns birth_year when present', () => {
        expect(estDob({ birth_year: 1900, death_year: 1980 })).toBe(1900);
    });

    it('estimates as death_year - 70 when only DOD present', () => {
        expect(estDob({ death_year: 1980 })).toBe(1910);
    });

    it('returns Infinity when neither present', () => {
        expect(estDob({})).toBe(Infinity);
    });
});

describe('sortHits', () => {
    it('orders by tier then alphabetical last, first', () => {
        const people = [
            { id: '1', name: 'John Smith' },
            { id: '2', name: 'John Papadopoulos' },
            { id: '3', name: 'Johnny Aslanidis' },
            { id: '4', name: 'Mary Johnson' },
        ];
        const sorted = sortHits(people, normSearch('john'));
        expect(sorted.map(p => p.id)).toEqual(['2', '1', '3', '4']);
    });

    it('uses estimated DOB as final tiebreaker (older first)', () => {
        const people = [
            { id: 'young', name: 'John Smith', birth_year: 1950 },
            { id: 'old', name: 'John Smith', birth_year: 1850 },
        ];
        const sorted = sortHits(people, normSearch('john'));
        expect(sorted.map(p => p.id)).toEqual(['old', 'young']);
    });

    it('uses DOD-70 estimate when DOB missing', () => {
        const people = [
            { id: 'dob1900', name: 'John Smith', birth_year: 1900 },
            { id: 'dod1960', name: 'John Smith', death_year: 1960 }, // est 1890
        ];
        const sorted = sortHits(people, normSearch('john'));
        expect(sorted.map(p => p.id)).toEqual(['dod1960', 'dob1900']);
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
        expect(result).not.toContain('</b><b>'); // no adjacent unmerged bold tags for same match
    });
});