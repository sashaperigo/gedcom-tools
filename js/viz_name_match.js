// Shared pure helpers for accent-insensitive name matching.
// Imported by viz_search.js and viz_advanced_search.js.

function stripAccents(s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, ''); }

function normSearch(s) { return stripAccents((s || '').toLowerCase()); }

const _parseCache = new Map();

function getParsed(p) {
    if (_parseCache.has(p.id)) return _parseCache.get(p.id);
    const raw = p.name || '';
    const flat = raw.replace(/\//g, '').replace(/\s+/g, ' ').trim();
    const nicks = [];
    const noNicks = flat.replace(/[“"]([^“”"]+)[”"]/g, (_, n) => { nicks.push(n.trim()); return ' '; })
        .replace(/\s+/g, ' ').trim();
    const tokens = noNicks.split(' ').filter(Boolean);
    const disp = flat.replace(/(^|[\s\-])(\p{L})/gu, (_, sep, c) => sep + c.toUpperCase());
    const normDisp = normSearch(flat);
    const result = {
        disp,
        normDisp,
        normFirst: normSearch(tokens[0] || ''),
        normLast: normSearch(tokens[tokens.length - 1] || ''),
        normNicks: nicks.map(normSearch),
    };
    _parseCache.set(p.id, result);
    return result;
}

// Substring + accent-insensitive match for advanced-search name fields.
// Accepts a person-like {id, name} or any object with a `name` string, or a raw string.
function nameMatches(personOrName, query) {
    if (!query) return true;
    const name = typeof personOrName === 'string' ? personOrName : (personOrName && personOrName.name) || '';
    if (!name) return false;
    return normSearch(name).includes(normSearch(query));
}

if (typeof module !== 'undefined') {
    module.exports = { stripAccents, normSearch, getParsed, nameMatches };
}
