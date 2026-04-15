// Search / autocomplete functions.
//
// stripAccents, normSearch, getParsed, personMatches, highlightName are pure
// and exported for testing.  renderResults and navigate touch the DOM and are
// not tested directly.

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function stripAccents(s) { return s.normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }
function normSearch(s)   { return stripAccents((s || '').toLowerCase()); }

// Pre-parse each person's name into searchable fields (lazy, cached per session).
// p = { id, name, birth_year, death_year }
const _parseCache = new Map();
function getParsed(p) {
  if (_parseCache.has(p.id)) return _parseCache.get(p.id);
  const raw = p.name || '';
  // Collapse slashes, normalize spaces
  const flat = raw.replace(/\//g, '').replace(/\s+/g, ' ').trim();
  // Extract nicknames (text in straight or curly double quotes: "Nick" or \u201cNick\u201d)
  const nicks = [];
  const noNicks = flat.replace(/[\u201c"]([^\u201c\u201d"]+)[\u201d"]/g, (_, n) => { nicks.push(n.trim()); return ' '; })
                      .replace(/\s+/g, ' ').trim();
  const tokens = noNicks.split(' ').filter(Boolean);
  // Display: title-case the flat form (keeps quotes visible)
  const disp = flat.replace(/(^|[\s\-])(\p{L})/gu, (_, sep, c) => sep + c.toUpperCase());
  const normDisp = normSearch(flat);  // same .length as flat (accent strip is length-preserving for NFC)
  const result = {
    disp,
    normDisp,
    normFirst: normSearch(tokens[0] || ''),
    normLast:  normSearch(tokens[tokens.length - 1] || ''),
    normNicks: nicks.map(normSearch),
  };
  _parseCache.set(p.id, result);
  return result;
}

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
  const qLast  = qToks[qToks.length - 1];
  const qMid   = qToks.slice(1, -1);
  if (!parsed.normLast.startsWith(qLast)) return false;
  if (!qMid.every(m => parsed.normDisp.includes(m))) return false;
  return parsed.normFirst.startsWith(qFirst) ||
         parsed.normNicks.some(n => n.startsWith(qFirst)) ||
         dispWords.some(w => w.startsWith(qFirst));
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
  let html = '', last = 0;
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

function renderResults(hits, qNorm) {
  const list = document.getElementById('search-results');
  list.innerHTML = '';
  let activeIdx = -1;
  hits.forEach(p => {
    const parsed = getParsed(p);
    const li = document.createElement('li');
    const dates = [p.birth_year && `b.\u2009${p.birth_year}`,
                   p.death_year && `d.\u2009${p.death_year}`].filter(Boolean).join(' \u2013 ');
    const nameHtml = highlightName(parsed.disp, parsed.normDisp, qNorm);
    li.innerHTML = nameHtml + (dates ? `<span class="srch-dates">(${escHtml(dates)})</span>` : '');
    li.dataset.id = p.id;
    li.addEventListener('click', () => navigate(p.id));
    list.appendChild(li);
  });
  list.classList.toggle('open', hits.length > 0);
}

function navigate(personId) {
  const list = document.getElementById('search-results');
  const input = document.getElementById('search-input');
  list.classList.remove('open');
  list.innerHTML = '';
  input.value = '';
  changeRoot(personId);
}

// ---------------------------------------------------------------------------
// Search IIFE wiring (browser only)
// ---------------------------------------------------------------------------

if (typeof document !== 'undefined') {
  (function() {
    const input = document.getElementById('search-input');
    const list  = document.getElementById('search-results');
    let activeIdx = -1;

    input.addEventListener('input', () => {
      const qNorm = normSearch(input.value.replace(/\//g, '').replace(/\s+/g, ' ').trim());
      if (!qNorm) { list.classList.remove('open'); list.innerHTML = ''; return; }
      const hits = ALL_PEOPLE.filter(p => personMatches(getParsed(p), qNorm)).slice(0, 20);
      renderResults(hits, qNorm);
    });

    input.addEventListener('keydown', e => {
      const items = list.querySelectorAll('li');
      if (!items.length) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); activeIdx = Math.min(activeIdx + 1, items.length - 1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); activeIdx = Math.max(activeIdx - 1, 0); }
      else if (e.key === 'Enter') { if (activeIdx >= 0) navigate(items[activeIdx].dataset.id); return; }
      else if (e.key === 'Escape') { list.classList.remove('open'); list.innerHTML = ''; input.blur(); return; }
      items.forEach((li, i) => li.classList.toggle('active', i === activeIdx));
      if (activeIdx >= 0) items[activeIdx].scrollIntoView({ block: 'nearest' });
    });

    document.addEventListener('click', e => {
      if (!e.target.closest('#search-container')) { list.classList.remove('open'); list.innerHTML = ''; }
    });
  })();
}

// ---------------------------------------------------------------------------
// Node export (for tests)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
  module.exports = { stripAccents, normSearch, getParsed, personMatches, highlightName };
}
