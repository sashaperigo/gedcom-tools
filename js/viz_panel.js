// Right-side detail panel for the Obsidian-themed genealogy visualizer.
// Renders when state.panelOpen === true using state.panelXref.
//
// Depends on globals: PEOPLE, SOURCES, setState, getState, onStateChange
// and the modal functions from viz_modals.js.

// ── Utility: HTML escaping ─────────────────────────────────────────────────

function _esc(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Utility: format GEDCOM AGE value for display ─────────────────────────

function fmtAge(raw) {
  if (!raw) return '';
  const s = String(raw).toUpperCase().trim();
  if (s === 'INFANT' || s === 'STILLBORN' || s === 'CHILD') return s.charAt(0) + s.slice(1).toLowerCase();
  // Parse "55y 3m 10d" style
  const ym = s.match(/^(\d+)Y(?:\s+(\d+)M)?(?:\s+(\d+)D)?$/);
  if (ym) {
    const parts = [];
    if (ym[1] !== '0') parts.push(ym[1] + ' year' + (ym[1] === '1' ? '' : 's'));
    if (ym[2]) parts.push(ym[2] + ' month' + (ym[2] === '1' ? '' : 's'));
    if (ym[3]) parts.push(ym[3] + ' day' + (ym[3] === '1' ? '' : 's'));
    return parts.join(', ') || '0';
  }
  return raw;
}

// ── Event label map (subset used in panel) ────────────────────────────────

const _TAG_LABELS = {
  BIRT: 'Birth', DEAT: 'Death', BURI: 'Burial', RESI: 'Residence',
  OCCU: 'Occupation', IMMI: 'Immigration', NATU: 'Naturalization',
  ADOP: 'Adoption', EDUC: 'Education', RETI: 'Retirement',
  TITL: 'Title', CHR: 'Christening', BAPM: 'Baptism',
  CONF: 'Confirmation', NATI: 'Nationality', RELI: 'Religion',
  DIV: 'Divorce', FACT: 'Fact', MARR: 'Marriage',
  PROB: 'Probate', ARRV: 'Arrival', DEPA: 'Departure',
};

// ── Module state ──────────────────────────────────────────────────────────

let _panelEl = null;

// ── Public: navigate to a godparent (exported for testing) ────────────────

function _handleGodparentClick(godparentXref) {
  setState({ focusXref: godparentXref });
}

// ── Internal: build fact row HTML ─────────────────────────────────────────

function _buildFactRow(fact, xref) {
  const tagLabel = _TAG_LABELS[fact.tag] || fact.tag;
  const date     = fact.date  ? ` · ${_esc(fact.date)}`  : '';
  const place    = fact.place ? ` · ${_esc(fact.place)}` : '';

  // DEAT with age-but-no-date: show "Died at age …"
  let ageStr = '';
  if (fact.tag === 'DEAT' && fact.age && !fact.date) {
    ageStr = ` · age ${_esc(fmtAge(fact.age))}`;
  }

  // OCCU/TITL/NATI-style inline value: show job title after label
  const inlineVal = (fact.inline_val && fact.tag === 'OCCU')
    ? ` · Worked as ${_esc(fact.inline_val)}`
    : '';

  let html = `<div class="panel-fact-row">`;
  html += `<span class="panel-fact-label">${_esc(tagLabel)}</span>`;
  html += `<span class="panel-fact-meta">${date}${place}${ageStr}${inlineVal}</span>`;

  // Citations badge
  if (fact.citations && fact.citations.length > 0) {
    const n = fact.citations.length;
    html += `<span class="panel-fact-cite-badge">${n} src</span>`;
  }

  // Godparents section: always show for CHR/BAPM, even when assoArr is empty,
  // so users can add the first godparent to a christening or baptism fact.
  const assoArr = (fact.asso || []).filter(a => a.rela === 'Godparent');
  const isChrOrBapm = fact.tag === 'CHR' || fact.tag === 'BAPM';
  if (isChrOrBapm || assoArr.length > 0) {
    html += `<div class="panel-godparents">`;
    if (assoArr.length > 0) {
      html += `<span class="panel-godparents-label">Godparents:</span>`;
      for (const asso of assoArr) {
        const gp     = (typeof PEOPLE !== 'undefined' && PEOPLE[asso.xref]);
        const gpName = gp ? _esc(gp.name) : _esc(asso.xref);
        const xrefJs = JSON.stringify(asso.xref);
        html += `<span class="panel-godparent-pill" data-xref="${_esc(asso.xref)}" onclick="_handleGodparentClick(${xrefJs})">${gpName}</span>`;
      }
    }
    const xrefQ = JSON.stringify(xref);
    html += `<button class="panel-add-godparent-btn" onclick="showAddGodparentModal(${xrefQ})">+ Add Godparent</button>`;
    html += `</div>`;
  }

  html += `</div>`;
  return html;
}

// ── Internal: build citations section HTML ────────────────────────────────

function _buildCitationsSection(xref, facts) {
  const xrefQ = JSON.stringify(xref);
  let html = `<div class="panel-section">`;
  html += `<div class="panel-section-header"><span class="panel-section-title">FACT SOURCES</span>`;
  html += `<button class="panel-section-add" onclick="showAddCitationModal(${xrefQ}, null)">+</button></div>`;

  for (let fi = 0; fi < facts.length; fi++) {
    const fact = facts[fi];
    if (!fact.citations || fact.citations.length === 0) continue;
    const tagLabel = _TAG_LABELS[fact.tag] || fact.tag;
    for (let ci = 0; ci < fact.citations.length; ci++) {
      const cite = fact.citations[ci];
      const src  = (typeof SOURCES !== 'undefined' && SOURCES[cite.sourceXref]) || {};
      const title = src.titl || cite.sourceXref || 'Unknown source';
      const tagBadge = `<span class="panel-cite-tag">${_esc(tagLabel)}</span>`;
      const editBtn  = `<button class="panel-cite-edit" onclick="showEditCitationModal(${xrefQ},${JSON.stringify(fact.tag)},${ci})">✎</button>`;
      const delBtn   = `<button class="panel-cite-del" onclick="_panelDeleteCitation(${xrefQ},${JSON.stringify(fact.tag)},${ci})">✕</button>`;
      html += `<div class="panel-cite-row">${tagBadge}${_esc(title)}${editBtn}${delBtn}</div>`;
    }
  }

  html += `</div>`;
  return html;
}

// ── Internal: build person-level sources section HTML ─────────────────────

function _buildPersonSourcesSection(xref, sources) {
  const xrefQ = JSON.stringify(xref);
  let html = `<div class="panel-section">`;
  html += `<div class="panel-section-header"><span class="panel-section-title">PERSON SOURCES</span>`;
  html += `<button class="panel-section-add" onclick="showAddCitationModal(${xrefQ}, null)">+</button></div>`;

  for (let i = 0; i < sources.length; i++) {
    const cite  = sources[i];
    const src   = (typeof SOURCES !== 'undefined' && SOURCES[cite.sourceXref]) || {};
    const title = src.titl || cite.sourceXref || 'Unknown source';
    const editBtn = `<button class="panel-cite-edit" onclick="showEditCitationModal(${xrefQ},null,${i})">✎</button>`;
    const delBtn  = `<button class="panel-cite-del" onclick="_panelDeleteCitation(${xrefQ},null,${i})">✕</button>`;
    html += `<div class="panel-source-card">`;
    html += `<div class="panel-source-title">${_esc(title)}${editBtn}${delBtn}</div>`;
    html += `</div>`;
  }

  html += `</div>`;
  return html;
}

// ── Internal: build notes section HTML ───────────────────────────────────

function _buildNotesSection(xref, notes) {
  const xrefQ = JSON.stringify(xref);
  let html = `<div class="panel-section">`;
  html += `<div class="panel-section-header"><span class="panel-section-title">NOTES</span>`;
  html += `<button class="panel-section-add" onclick="showAddNoteModal(${xrefQ})">+</button></div>`;

  for (const note of notes) {
    html += `<div class="panel-note-text">${_esc(note)}</div>`;
  }

  html += `</div>`;
  return html;
}

// ── Internal: citation delete (called from inline onclick) ─────────────────

async function _panelDeleteCitation(xref, factTag, index) {
  // apiDeleteCitation expects a formatted "TAG:index" key string
  const citationKey = factTag ? `${factTag}:${index}` : `SOUR:${index}`;
  try {
    await apiDeleteCitation(xref, citationKey);
  } catch (e) {
    // ignore
  }
  renderPanel();
}

// ── Main render function ──────────────────────────────────────────────────

function renderPanel() {
  if (!_panelEl) return;

  const state = getState();

  if (!state.panelOpen) {
    _panelEl.classList.remove('panel-open');
    return;
  }

  const xref = state.panelXref;
  if (!xref) {
    _panelEl.classList.remove('panel-open');
    return;
  }

  const data = (typeof PEOPLE !== 'undefined') && PEOPLE[xref];
  if (!data) {
    _panelEl.classList.remove('panel-open');
    return;
  }

  // ── Header ────────────────────────────────────────────────────────────
  const xrefQ = JSON.stringify(xref);

  // Name element
  const nameEl = document.getElementById('detail-name');
  if (nameEl) {
    nameEl.innerHTML =
      _esc(data.name || '') +
      `<button class="panel-edit-name-btn" title="Edit name" onclick="showEditNameModal(${xrefQ})">✎</button>`;
  }

  // Close button
  const closeBtn = document.getElementById('panel-close-btn');
  if (closeBtn) {
    closeBtn.onclick = () => setState({ panelOpen: false });
  }

  // Lifespan
  const lifespanEl = document.getElementById('detail-lifespan');
  if (lifespanEl) {
    const by = data.birth_year || '';
    const dy = data.death_year || '';
    let html = '';
    if (by) html += `<span class="panel-birth-year">${_esc(String(by))}</span>`;
    if (by && dy) html += `<span class="panel-lifespan-sep">–</span>`;
    if (dy) html += `<span class="panel-death-year">${_esc(String(dy))}</span>`;
    if (by && dy) {
      const age = parseInt(dy) - parseInt(by);
      if (age > 0) html += `<span class="panel-age">age ${age}</span>`;
    }
    lifespanEl.innerHTML = html;
  }

  // Nationality pills (derived from NATI events, shown separately from the timeline)
  const natiEl = document.getElementById('detail-nationalities');
  if (natiEl) {
    const natis = (data.events || []).filter(e => e.tag === 'NATI').map(e => e.inline_val || '').filter(Boolean);
    const natiPills = natis.map(n => `<span class="panel-nati-pill">${_esc(n)}</span>`).join('');
    const addNatiBtn = `<button class="add-event-btn" onclick="showAddEventModal(${xrefQ},'NATI')">+ Add nationality</button>`;
    natiEl.innerHTML = natiPills + addNatiBtn;
  }

  // ── Life Events section ───────────────────────────────────────────────
  const eventsEl = document.getElementById('detail-events');
  if (eventsEl) {
    // Exclude NATI events — those are shown above as nationality pills
    const facts = (data.events || []).filter(e => e.tag !== 'NATI');
    let evtHtml = `<div class="panel-section">`;
    evtHtml += `<div class="panel-section-header"><span class="panel-section-title">LIFE EVENTS</span>`;
    evtHtml += `<button class="panel-section-add" onclick="showAddEventModal(${xrefQ})">+</button></div>`;

    for (const fact of facts) {
      evtHtml += _buildFactRow(fact, xref);
    }

    evtHtml += `</div>`;
    eventsEl.innerHTML = evtHtml;
  }

  // ── Fact Citations section ────────────────────────────────────────────
  const factsEl = document.getElementById('detail-fact-sources');
  if (factsEl) {
    factsEl.innerHTML = _buildCitationsSection(xref, data.events || []);
  }

  // ── Person Sources section ────────────────────────────────────────────
  const sourcesEl = document.getElementById('detail-person-sources');
  if (sourcesEl) {
    sourcesEl.innerHTML = _buildPersonSourcesSection(xref, data.sources || []);
  }

  // ── Notes section ─────────────────────────────────────────────────────
  const notesEl = document.getElementById('detail-notes');
  if (notesEl) {
    notesEl.innerHTML = _buildNotesSection(xref, data.notes || []);
  }

  _panelEl.classList.add('panel-open');
}

// ── Init ──────────────────────────────────────────────────────────────────

function initPanel(panelEl) {
  _panelEl = panelEl;
  onStateChange(function (state) {
    renderPanel();
  });
}

// ── Exports ───────────────────────────────────────────────────────────────

if (typeof module !== 'undefined') {
  module.exports = { initPanel, renderPanel };
}
