// Search / autocomplete functions.
//
// stripAccents, normSearch, getParsed, personMatches, highlightName are pure
// and exported for testing.  createPersonPicker and navigate touch the DOM and are
// not tested directly.

// ---------------------------------------------------------------------------
// Pure helpers \u2014 delegated to shared viz_name_match.js
// ---------------------------------------------------------------------------

// Shared name-match helpers \u2014 for browser, viz_name_match.js loads first via <script> tag.
const _nameMatchS = (typeof require !== 'undefined')
    ? require('./viz_name_match.js')
    : { stripAccents, normSearch, getParsed };
const { stripAccents: _stripAccentsS, normSearch: _normSearchS, getParsed: _getParsedS } = _nameMatchS;

function personMatches(parsed, qNorm) {
    if (!qNorm) return false;
    // 1. Plain substring anywhere in name (handles most queries)
    if (parsed.normDisp.includes(qNorm)) return true;
    const qToks = qNorm.split(' ').filter(Boolean);
    // Split normDisp into words (strip punctuation) for nickname fallback matching
    const dispWords = parsed.normDisp.split(/[^a-z]+/).filter(Boolean);
    if (qToks.length === 1) {
        // 2. Single token: check nicknames or any word in display name
        return parsed.normNicks.some(n => n.includes(qToks[0])) ||
            dispWords.some(w => w.includes(qToks[0]));
    }
    // 3. Multi-token: first+last match skipping middle names
    //    Query "A B" matches if A is first/nickname/any-name-word and B is last name
    //    Query "A B C" matches if A is first/nickname, C is last, B appears anywhere
    const qFirst = qToks[0];
    const qLast = qToks[qToks.length - 1];
    const qMid = qToks.slice(1, -1);
    if (!parsed.normLast.startsWith(qLast)) return false;
    if (!qMid.every(m => parsed.normDisp.includes(m))) return false;
    return parsed.normFirst.startsWith(qFirst) ||
        parsed.normNicks.some(n => n.startsWith(qFirst)) ||
        dispWords.some(w => w.startsWith(qFirst));
}

// Lower score = better match. Tiers:
//   1 exact first-name, 2 exact last/nickname, 3 starts-with first,
//   4 starts-with last/nickname, 5 substring only.
// For multi-token queries, score against the first token.
function matchScore(parsed, qNorm) {
    const q = qNorm.split(' ').filter(Boolean)[0] || qNorm;
    if (parsed.normFirst === q) return 1;
    if (parsed.normLast === q || parsed.normNicks.some(n => n === q)) return 2;
    if (parsed.normFirst.startsWith(q)) return 3;
    if (parsed.normLast.startsWith(q) || parsed.normNicks.some(n => n.startsWith(q))) return 4;
    return 5;
}

// Estimate DOB for sorting: birth_year, else death_year - 70, else Infinity.
function estDob(p) {
    if (p.birth_year) return p.birth_year;
    if (p.death_year) return p.death_year - 70;
    return Infinity;
}

function sortHits(hits, qNorm) {
    return hits.slice().sort((a, b) => {
        const pa = _getParsedS(a), pb = _getParsedS(b);
        const sa = matchScore(pa, qNorm), sb = matchScore(pb, qNorm);
        if (sa !== sb) return sa - sb;
        if (pa.normLast !== pb.normLast) return pa.normLast < pb.normLast ? -1 : 1;
        if (pa.normFirst !== pb.normFirst) return pa.normFirst < pb.normFirst ? -1 : 1;
        return estDob(a) - estDob(b);
    });
}

// Build innerHTML with query tokens bolded in displayStr.
// normDispStr and displayStr must have equal .length (guaranteed by our parsing).
function highlightName(displayStr, normDispStr, qNorm) {
    if (!qNorm) return escHtml(displayStr);
    const qToks = qNorm.split(' ').filter(Boolean);
    const regions = [];
    for (const tok of qToks) {
        let i = 0;
        while ((i = normDispStr.indexOf(tok, i)) !== -1) {
            regions.push([i, i + tok.length]);
            i++;
        }
    }
    regions.sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const [s, e] of regions) {
        if (merged.length && s <= merged[merged.length - 1][1])
            merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], e);
        else merged.push([s, e]);
    }
    let html = '',
        last = 0;
    for (const [s, e] of merged) {
        html += escHtml(displayStr.slice(last, s));
        html += '<b>' + escHtml(displayStr.slice(s, e)) + '</b>';
        last = e;
    }
    html += escHtml(displayStr.slice(last));
    return html;
}

// ---------------------------------------------------------------------------
// DOM-dependent functions (not exported for tests)
// ---------------------------------------------------------------------------

// Shared person-picker autocomplete component.
// inputEl: text input; resultsEl: result-item container
// opts.onSelect(xref, name) \u2014 called when user confirms a pick
// opts.onTyping()           \u2014 called on each keystroke (caller clears stale selection)
// Returns { reset() } for programmatic clear.
function createPersonPicker(inputEl, resultsEl, opts) {
    const { onSelect = () => {}, onTyping = () => {} } = opts || {};
    let activeIdx = -1;

    function _render(hits, qNorm) {
        resultsEl.innerHTML = '';
        activeIdx = -1;
        hits.forEach(p => {
            const parsed = _getParsedS(p);
            const item = document.createElement('div');
            item.className = 'person-picker-result';
            const dates = [
                p.birth_year && `b.\u2009${p.birth_year}`,
                p.death_year && `d.\u2009${p.death_year}`,
            ].filter(Boolean).join(' \u2013 ');
            const nameHtml = highlightName(parsed.disp, parsed.normDisp, qNorm);
            item.innerHTML = nameHtml + (dates ? `<span class="srch-dates">(${escHtml(dates)})</span>` : '');
            item.dataset.id = p.id;
            item.dataset.name = parsed.disp;
            item.addEventListener('click', () => _pick(p.id, parsed.disp));
            resultsEl.appendChild(item);
        });
        resultsEl.classList.toggle('open', hits.length > 0);
    }

    function _pick(xref, name) {
        resultsEl.innerHTML = '';
        resultsEl.classList.remove('open');
        inputEl.value = name;
        activeIdx = -1;
        onSelect(xref, name);
    }

    inputEl.addEventListener('input', () => {
        onTyping();
        const qNorm = _normSearchS(inputEl.value.replace(/\//g, '').replace(/\s+/g, ' ').trim());
        if (!qNorm) { resultsEl.innerHTML = ''; resultsEl.classList.remove('open'); return; }
        const hits = sortHits(
            (typeof ALL_PEOPLE !== 'undefined' ? ALL_PEOPLE : []).filter(p => personMatches(_getParsedS(p), qNorm)),
            qNorm
        );
        _render(hits, qNorm);
    });

    inputEl.addEventListener('keydown', e => {
        const items = resultsEl.querySelectorAll('.person-picker-result');
        if (!items.length) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIdx = Math.min(activeIdx + 1, items.length - 1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIdx = Math.max(activeIdx - 1, 0);
        } else if (e.key === 'Enter') {
            if (activeIdx >= 0) _pick(items[activeIdx].dataset.id, items[activeIdx].dataset.name);
            return;
        } else if (e.key === 'Escape') {
            resultsEl.innerHTML = '';
            resultsEl.classList.remove('open');
            activeIdx = -1;
            return;
        }
        items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
        if (activeIdx >= 0) items[activeIdx].scrollIntoView({ block: 'nearest' });
    });

    return {
        reset() {
            inputEl.value = '';
            resultsEl.innerHTML = '';
            resultsEl.classList.remove('open');
            activeIdx = -1;
        },
    };
}

function navigate(personId) {
    const list = document.getElementById('search-results');
    const input = document.getElementById('search-input');
    list.classList.remove('open');
    list.innerHTML = '';
    input.value = '';
    setState({ focusXref: personId, panelOpen: true, panelXref: personId });
}

// ---------------------------------------------------------------------------
// Search IIFE wiring (browser only)
// ---------------------------------------------------------------------------

if (typeof document !== 'undefined') {
    (function () {
        const input = document.getElementById('search-input');
        const list = document.getElementById('search-results');
        if (!input || !list) return;

        createPersonPicker(input, list, { onSelect: xref => navigate(xref) });

        // @XREF@ direct navigation \u2014 main search bar only
        input.addEventListener('input', () => {
            const raw = input.value.trim();
            if (/^@[^@]+@$/i.test(raw)) {
                const rawUp = raw.toUpperCase();
                const match = (typeof ALL_PEOPLE !== 'undefined' ? ALL_PEOPLE : [])
                    .find(p => p.id.toUpperCase() === rawUp);
                if (match) { navigate(match.id); input.value = ''; }
            }
        });

        // Click outside to dismiss
        document.addEventListener('click', e => {
            if (!e.target.closest('#search-container')) {
                list.classList.remove('open');
                list.innerHTML = '';
            }
        });
    })();
}

// ---------------------------------------------------------------------------
// Node export (for tests)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
    module.exports = {
        stripAccents: _stripAccentsS,
        normSearch: _normSearchS,
        getParsed: _getParsedS,
        personMatches, highlightName, matchScore, estDob, sortHits,
    };
}