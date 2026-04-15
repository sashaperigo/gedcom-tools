// Edit / add / delete modals: notes, events, aliases, names.
// Pure helpers exported for testing (node require-compatible at the bottom).

// ---------------------------------------------------------------------------
// Note edit / delete
// ---------------------------------------------------------------------------

let _noteEditXref = null, _noteEditIdx = null;

async function deleteNote(xref, noteIdx) {
  if (!confirm('Delete this note? The GEDCOM file will be updated immediately (a backup will be saved).')) return;
  try {
    const resp = await fetch('/api/delete_note', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({xref, note_idx: noteIdx, current_person: window._currentPerson || null}),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      showDetail(xref, true);
    } else {
      alert('Delete failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) { alert('Request failed: ' + e); }
}

function addNote(xref) {
  _noteEditXref = xref;
  _noteEditIdx  = null;  // null = add mode
  document.getElementById('note-modal-title').textContent = 'Add Note';
  document.getElementById('note-modal-textarea').value = '';
  document.getElementById('note-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('note-modal-textarea').focus(), 50);
}

function editNote(xref, noteIdx) {
  _noteEditXref = xref;
  _noteEditIdx  = noteIdx;
  document.getElementById('note-modal-title').textContent = 'Edit Note';
  document.getElementById('note-modal-textarea').value = (PEOPLE[xref] && PEOPLE[xref].notes[noteIdx]) || '';
  document.getElementById('note-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('note-modal-textarea').focus(), 50);
}

function closeNoteModal() {
  document.getElementById('note-modal-overlay').classList.remove('open');
  _noteEditXref = _noteEditIdx = null;
}

async function submitNoteEdit() {
  const newText  = document.getElementById('note-modal-textarea').value;
  const xref     = _noteEditXref;
  const noteIdx  = _noteEditIdx;
  closeNoteModal();
  const isAdd = noteIdx === null;
  const url   = isAdd ? '/api/add_note' : '/api/edit_note';
  const payload = isAdd
    ? {xref, new_text: newText, current_person: window._currentPerson || null}
    : {xref, note_idx: noteIdx, new_text: newText, current_person: window._currentPerson || null};
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      showDetail(xref, true);
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) { alert('Request failed: ' + e); }
}

// ---------------------------------------------------------------------------
// Event edit / add
// ---------------------------------------------------------------------------

// Tags whose level-1 line carries an inline value (e.g. "1 OCCU Consul")
const _INLINE_TYPE_TAGS = new Set(['OCCU','TITL','NATI','RELI','EDUC']);
// Tags that use a 2 TYPE sub-field for description
const _TYPE_TAGS = new Set(['EVEN','FACT','OCCU','TITL','EDUC','NATI','RELI']);

let _eventModalXref = null, _eventModalIdx = null, _eventModalTag = null,
    _eventModalFamXref = null, _eventModalMARRIdx = null;

// Fact presets — each key is the pseudo-tag used in the UI (option value).
// baseTag:     the real GEDCOM tag submitted to the server
// type:        value for 2 TYPE sub-tag (null for tags that don't use TYPE)
// showInline:  true → show the inline value field (for DSCR, NCHI)
// inlineLabel: label for the inline field when showInline is true
const _FACT_PRESETS = {
  'FACT:Languages':         { label: 'Languages',           baseTag: 'FACT', type: 'Languages',         showInline: false },
  'FACT:Literacy':          { label: 'Literacy',            baseTag: 'FACT', type: 'Literacy',          showInline: false },
  'FACT:Politics':          { label: 'Politics',            baseTag: 'FACT', type: 'Politics',          showInline: false },
  'FACT:Medical condition': { label: 'Medical condition',   baseTag: 'FACT', type: 'Medical condition', showInline: false },
  'DSCR':                   { label: 'Physical Description', baseTag: 'DSCR', type: null,              showInline: true,  inlineLabel: 'Description' },
  'NCHI':                   { label: 'Children (count)',    baseTag: 'NCHI', type: null,              showInline: true,  inlineLabel: 'Count' },
};

function _updateEventModalFields(tag) {
  const inlineRow = document.getElementById('event-modal-inline-row');
  const inlineLbl = document.getElementById('event-modal-inline-label');
  const typeRow   = document.getElementById('event-modal-type-row');
  const causeRow  = document.getElementById('event-modal-cause-row');
  const placeRow  = document.getElementById('event-modal-place-row');
  const addrRow   = document.getElementById('event-modal-addr-row');

  const preset = _FACT_PRESETS[tag];
  if (preset) {
    // Preset fact: hide cause, place, address — only date and note are relevant.
    causeRow.style.display = 'none';
    if (placeRow) placeRow.style.display = 'none';
    if (addrRow)  addrRow.style.display  = 'none';
    if (preset.showInline) {
      // DSCR / NCHI: show inline field (value goes on the tag line), hide TYPE row
      inlineRow.style.display = '';
      inlineLbl.textContent   = preset.inlineLabel;
      typeRow.style.display   = 'none';
    } else {
      // FACT: show type row pre-filled and read-only, hide inline field
      inlineRow.style.display = 'none';
      typeRow.style.display   = '';
      const typeInp = document.getElementById('event-modal-type');
      if (typeInp && !typeInp.value) typeInp.value = preset.type;
      if (typeInp) typeInp.readOnly = true;
    }
    _updateSpouseRow(tag);
    return;
  }

  // Clear any read-only state (and pre-filled value) set by a previous preset selection
  const typeInp = document.getElementById('event-modal-type');
  if (typeInp) { typeInp.readOnly = false; typeInp.value = ''; }

  if (_INLINE_TYPE_TAGS.has(tag)) {
    inlineRow.style.display = '';
    const labelMap = {OCCU:'Occupation',TITL:'Title',NATI:'Nationality',RELI:'Religion',EDUC:'Education'};
    inlineLbl.textContent = labelMap[tag] || 'Value';
  } else {
    inlineRow.style.display = 'none';
  }
  // For inline-type tags (EDUC, OCCU, etc.) the inline value IS the type —
  // showing a separate TYPE field would duplicate it and cause confusion.
  typeRow.style.display = (_TYPE_TAGS.has(tag) && !_INLINE_TYPE_TAGS.has(tag)) ? '' : 'none';
  causeRow.style.display = (tag === 'DEAT') ? '' : 'none';
  const hidePlaceAddr = (tag === 'NATI');
  if (placeRow) placeRow.style.display = hidePlaceAddr ? 'none' : '';
  if (addrRow)  addrRow.style.display  = hidePlaceAddr ? 'none' : '';
  _updateSpouseRow(tag);
}

function _updateAddrSuggestions(place) {
  const dl = document.getElementById('addr-suggestions');
  if (!dl) return;
  dl.innerHTML = '';
  const suggestions = ADDR_BY_PLACE[place] || [];
  for (const s of suggestions) {
    const opt = document.createElement('option');
    opt.value = s;
    dl.appendChild(opt);
  }
}

// Populate the PLAC suggestions datalist once on load
(function() {
  const dl = document.getElementById('plac-suggestions');
  if (!dl) return;
  for (const p of ALL_PLACES) {
    const opt = document.createElement('option');
    opt.value = p;
    dl.appendChild(opt);
  }
})();

function _personName(xref) {
  return (PEOPLE[xref] && PEOPLE[xref].name) ||
    ((ALL_PEOPLE.find(p => p.id === xref) || {}).name) || xref;
}

function editEvent(xref, eventIdx, tag, famXref, marrIdx) {
  _eventModalXref    = xref;
  _eventModalIdx     = eventIdx;
  _eventModalTag     = tag;
  _eventModalFamXref = famXref || null;
  _eventModalMARRIdx = (marrIdx !== undefined && marrIdx !== null) ? marrIdx : null;
  document.getElementById('event-modal-title').textContent = 'Edit Event \u2014 ' + _personName(xref);
  document.getElementById('event-modal-save-btn').textContent = 'Save';
  document.getElementById('event-modal-tag-row').style.display = 'none';
  const events = (PEOPLE[xref] && PEOPLE[xref].events) || [];
  // For FAM events (MARR), match by fam_xref + marr_idx; otherwise match by tag + event_idx
  const evt = famXref
    ? (events.find(e => e.fam_xref === famXref && e.tag === tag && (marrIdx == null || e.marr_idx === marrIdx)) || {})
    : (events.find(e => e.tag === tag && e.event_idx === eventIdx) || {});
  const placeVal = evt.place || '';
  document.getElementById('event-modal-inline').value = evt.inline_val || '';
  document.getElementById('event-modal-type').value   = evt.type || '';
  document.getElementById('event-modal-date').value   = evt.date || '';
  document.getElementById('event-modal-place').value  = placeVal;
  document.getElementById('event-modal-cause').value  = evt.cause || '';
  document.getElementById('event-modal-note').value   = evt.note || '';
  document.getElementById('event-modal-addr').value   = evt.addr || '';
  _updateAddrSuggestions(placeVal);
  _updateEventModalFields(tag);
  document.getElementById('event-modal-overlay').classList.add('open');
  const focusId = _INLINE_TYPE_TAGS.has(tag) ? 'event-modal-inline' : 'event-modal-date';
  setTimeout(() => document.getElementById(focusId).focus(), 50);
}

function addEvent(xref, defaultTag = 'RESI', prefillType) {
  _eventModalXref    = xref;
  _eventModalIdx     = null;
  _eventModalTag     = null;
  _eventModalFamXref = null;
  _eventModalSpouseXref = null;
  document.getElementById('event-modal-title').textContent = 'Add Event \u2014 ' + _personName(xref);
  document.getElementById('event-modal-save-btn').textContent = 'Add';
  document.getElementById('event-modal-tag-row').style.display = '';
  document.getElementById('event-modal-tag').value    = defaultTag;
  document.getElementById('event-modal-inline').value = '';
  document.getElementById('event-modal-type').value   = prefillType || '';
  document.getElementById('event-modal-date').value   = '';
  document.getElementById('event-modal-place').value  = '';
  document.getElementById('event-modal-cause').value  = '';
  document.getElementById('event-modal-note').value   = '';
  document.getElementById('event-modal-addr').value   = '';
  const spouseInp = document.getElementById('event-modal-spouse-input');
  const spouseRes = document.getElementById('event-modal-spouse-results');
  if (spouseInp) spouseInp.value = '';
  if (spouseRes) spouseRes.innerHTML = '';
  _updateAddrSuggestions('');
  _updateEventModalFields(defaultTag);
  document.getElementById('event-modal-overlay').classList.add('open');
  const _dfPreset = _FACT_PRESETS[defaultTag];
  const focusId = _dfPreset
                ? (_dfPreset.showInline ? 'event-modal-inline' : 'event-modal-note')
                : _INLINE_TYPE_TAGS.has(defaultTag) ? 'event-modal-inline'
                : 'event-modal-date';
  setTimeout(() => document.getElementById(focusId).focus(), 50);
}

function closeEventModal() {
  document.getElementById('event-modal-overlay').classList.remove('open');
  _eventModalXref = _eventModalIdx = _eventModalTag = _eventModalFamXref = _eventModalMARRIdx = null;
  _eventModalSpouseXref = null;
}

async function submitEventModal() {
  const xref     = _eventModalXref;
  const famXref  = _eventModalFamXref;
  const isAdd    = _eventModalIdx === null && !famXref;
  const rawTag   = isAdd ? document.getElementById('event-modal-tag').value : _eventModalTag;
  // Resolve preset pseudo-tags to their real GEDCOM tag (e.g. 'FACT:Languages' → 'FACT').
  const preset   = _FACT_PRESETS[rawTag];
  const tag      = preset ? preset.baseTag : rawTag;
  const typeRow  = document.getElementById('event-modal-type-row');
  const causeRow = document.getElementById('event-modal-cause-row');
  const fields = {
    inline_val: document.getElementById('event-modal-inline').value.trim(),
    DATE:        document.getElementById('event-modal-date').value.trim(),
    PLAC:        document.getElementById('event-modal-place').value.trim(),
    NOTE:        document.getElementById('event-modal-note').value.trim(),
    ADDR:        document.getElementById('event-modal-addr').value.trim(),
  };
  // Only include TYPE when the row is visible; omitting it preserves existing 2 TYPE sub-tags
  // for events (like MARR) where the type row is hidden.
  if (typeRow && typeRow.style.display !== 'none') {
    fields.TYPE = document.getElementById('event-modal-type').value.trim();
  }
  // Only include CAUS when the cause row is visible (DEAT events)
  if (causeRow && causeRow.style.display !== 'none') {
    fields.CAUS = document.getElementById('event-modal-cause').value.trim();
  }

  // Marriage / divorce events route to /api/add_marriage (FAM-level, requires spouse)
  if (isAdd && _isFamEventTag(tag)) {
    if (!_eventModalSpouseXref) {
      alert('Please select a spouse or other party from the search results.');
      return;
    }
    closeEventModal();
    try {
      const resp = await fetch('/api/add_marriage', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          xref, spouse_xref: _eventModalSpouseXref, tag, fields,
          current_person: window._currentPerson || null,
        }),
      });
      const data = await resp.json();
      if (data.ok) {
        if (data.people) for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
        window._openDetailKey = null;
        showDetail(xref, true);
      } else {
        alert('Save failed: ' + (data.error || 'unknown error'));
      }
    } catch (e) {
      alert('Request failed: ' + e);
    }
    return;
  }

  const endpoint = isAdd ? '/api/add_event' : '/api/edit_event';
  let body;
  if (isAdd) {
    body = { xref, tag, fields, current_person: window._currentPerson || null };
  } else if (famXref) {
    body = { xref, tag, fam_xref: famXref, marr_occurrence: _eventModalMARRIdx ?? 0,
             updates: fields, current_person: window._currentPerson || null };
  } else {
    body = { xref, tag, event_idx: _eventModalIdx, updates: fields, current_person: window._currentPerson || null };
  }
  closeEventModal();
  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.ok) {
      // Update all returned people (may include both spouses for marriage edits)
      if (data.people) {
        for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      }
      window._openDetailKey = null;
      showDetail(xref, true);
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}

// Update field visibility when the tag selector changes (add mode only)
document.addEventListener('change', e => {
  if (e.target.id === 'event-modal-tag') _updateEventModalFields(e.target.value);
});
// Update ADDR suggestions as the place field changes
document.addEventListener('input', e => {
  if (e.target.id === 'event-modal-place') _updateAddrSuggestions(e.target.value.trim());
});

// ---------------------------------------------------------------------------
// Alias (secondary name) add / edit / delete
// ---------------------------------------------------------------------------

let _aliasModalXref = null, _aliasModalNameOccurrence = null, _aliasModalIsNameRecord = false;

function openAliasModal(xref, nameOccurrence, currentName, currentType, isNameRecord) {
  _aliasModalXref            = xref;
  _aliasModalNameOccurrence  = nameOccurrence;   // null = add mode
  _aliasModalIsNameRecord    = !!isNameRecord;
  const isAdd = nameOccurrence === null || nameOccurrence === undefined;
  document.getElementById('alias-modal-title').textContent =
    (isAdd ? 'Add Secondary Name \u2014 ' : 'Edit Name \u2014 ') + _personName(xref);
  document.getElementById('alias-modal-save-btn').textContent = isAdd ? 'Add' : 'Save';
  document.getElementById('alias-modal-name').value = currentName || '';
  // Set the dropdown; fall back to AKA if the value isn't in the list
  const sel = document.getElementById('alias-modal-type');
  const opt = [...sel.options].find(o => o.value === (currentType || 'AKA'));
  sel.value = opt ? opt.value : 'AKA';
  document.getElementById('alias-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('alias-modal-name').focus(), 50);
}

function closeAliasModal() {
  document.getElementById('alias-modal-overlay').classList.remove('open');
  _aliasModalXref = _aliasModalNameOccurrence = null;
}

async function deleteAlias(xref, evt) {
  const label = evt.note || evt.inline_val || '';
  if (!confirm('Delete this name? The GEDCOM file will be updated immediately.\n\n' + label)) return;
  let endpoint, body;
  if (evt._name_record) {
    endpoint = '/api/delete_secondary_name';
    body = { xref, name_occurrence: evt._name_occurrence, current_person: window._currentPerson || null };
  } else {
    // FACT-based AKA — use existing delete_fact
    endpoint = '/api/delete_fact';
    body = { xref, tag: evt.tag, date: evt.date || null, place: evt.place || null,
             type: evt.type || null, inline_val: evt.inline_val || null,
             current_person: xref };
  }
  try {
    const resp = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people) for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      showDetail(xref, true);
    } else { alert('Delete failed: ' + (data.error || 'unknown error')); }
  } catch (e) { alert('Request failed: ' + e); }
}

async function submitAliasModal() {
  const xref      = _aliasModalXref;
  const nameOcc   = _aliasModalNameOccurrence;
  const isAdd     = nameOcc === null || nameOcc === undefined;
  const name      = document.getElementById('alias-modal-name').value.trim();
  const nameType  = document.getElementById('alias-modal-type').value;
  if (!name) { alert('Please enter a name.'); return; }
  closeAliasModal();
  let endpoint, body;
  if (isAdd) {
    endpoint = '/api/add_secondary_name';
    body = { xref, name, name_type: nameType, current_person: window._currentPerson || null };
  } else {
    endpoint = '/api/edit_secondary_name';
    body = { xref, name_occurrence: nameOcc, name, name_type: nameType,
             current_person: window._currentPerson || null };
  }
  try {
    const resp = await fetch(endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people) for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      showDetail(xref, true);
    } else { alert('Save failed: ' + (data.error || 'unknown error')); }
  } catch (e) { alert('Request failed: ' + e); }
}

// ---------------------------------------------------------------------------
// Name editing
// ---------------------------------------------------------------------------

let _nameModalXref = null;

function editName(xref) {
  _nameModalXref = xref;
  const name = (_personName(xref) || '').trim();
  // Split "Given /Surname/" or just "Given Surname" into parts
  const surnameMatch = name.match(/^(.*?)\s*\/([^/]*)\/\s*(.*)$/);
  let given = '', surname = '';
  if (surnameMatch) {
    given   = (surnameMatch[1] + ' ' + (surnameMatch[3] || '')).trim();
    surname = surnameMatch[2].trim();
  } else {
    // Try to split on last word as surname heuristic
    const parts = name.split(' ');
    surname = parts.length > 1 ? parts.pop() : '';
    given   = parts.join(' ');
  }
  document.getElementById('name-modal-title').textContent = 'Edit Name \u2014 ' + name;
  document.getElementById('name-modal-given').value   = given;
  document.getElementById('name-modal-surname').value = surname;
  document.getElementById('name-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('name-modal-given').focus(), 50);
}

function closeNameModal() {
  document.getElementById('name-modal-overlay').classList.remove('open');
  _nameModalXref = null;
}

async function submitNameModal() {
  const xref      = _nameModalXref;
  const givenName = document.getElementById('name-modal-given').value.trim();
  const surname   = document.getElementById('name-modal-surname').value.trim();
  closeNameModal();
  try {
    const resp = await fetch('/api/edit_name', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ xref, given_name: givenName, surname,
                             current_person: window._currentPerson || null }),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      showDetail(xref, true);
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) { alert('Request failed: ' + e); }
}

// ---------------------------------------------------------------------------
// Marriage / divorce add + delete
// ---------------------------------------------------------------------------

// Tags whose events live in FAM records (not in INDI)
const _FAM_EVENT_TAGS = new Set(['MARR', 'DIV']);

// Pure helper: filter ALL_PEOPLE by name substring (case-insensitive), max 12
function _filterSpouseResults(query, allPeople) {
  const q = (query || '').trim().toLowerCase();
  if (!q) return [];
  return allPeople.filter(p => (p.name || '').toLowerCase().includes(q)).slice(0, 12);
}

// Pure helper: is this tag a FAM-level event?
function _isFamEventTag(tag) {
  return _FAM_EVENT_TAGS.has(tag);
}

let _eventModalSpouseXref = null;

function _updateSpouseRow(tag) {
  const row = document.getElementById('event-modal-spouse-row');
  if (!row) return;
  if (_isFamEventTag(tag)) {
    row.style.display = '';
  } else {
    row.style.display = 'none';
    const inp = document.getElementById('event-modal-spouse-input');
    const res = document.getElementById('event-modal-spouse-results');
    if (inp) inp.value = '';
    if (res) res.innerHTML = '';
    _eventModalSpouseXref = null;
  }
}

function _buildSpouseResultsHtml(hits) {
  return hits.map(p =>
    `<div class="spouse-result-item" data-xref="${escHtml(p.id)}" data-name="${escHtml(p.name)}">${escHtml(p.name)}${p.birth_year ? ' (' + p.birth_year + ')' : ''}</div>`
  ).join('');
}

function _renderSpouseResults(query) {
  const container = document.getElementById('event-modal-spouse-results');
  if (!container) return;
  const hits = _filterSpouseResults(query, typeof ALL_PEOPLE !== 'undefined' ? ALL_PEOPLE : []);
  if (!hits.length) { container.innerHTML = ''; return; }
  container.innerHTML = _buildSpouseResultsHtml(hits);
}

function _selectSpouse(xref, name) {
  const inp = document.getElementById('event-modal-spouse-input');
  const res = document.getElementById('event-modal-spouse-results');
  if (inp) inp.value = name;
  if (res) res.innerHTML = '';
  _eventModalSpouseXref = xref;
}

// Use event delegation on the results container so data-attribute clicks work
document.addEventListener('click', e => {
  const item = e.target.closest('.spouse-result-item');
  if (item) _selectSpouse(item.dataset.xref, item.dataset.name);
});

async function deleteMarriage(xref, famXref, marrIdx) {
  if (!confirm('Delete this marriage record? The GEDCOM file will be updated immediately (a backup will be saved).')) return;
  try {
    const resp = await fetch('/api/delete_marriage', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        xref,
        fam_xref: famXref,
        marr_occurrence: marrIdx,
        current_person: xref,
      }),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people) for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      showDetail(xref, true);
    } else {
      alert('Delete failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}

// Wire spouse-picker input to autocomplete
document.addEventListener('input', e => {
  if (e.target.id === 'event-modal-spouse-input') _renderSpouseResults(e.target.value);
});

// ---------------------------------------------------------------------------
// Fact delete
// ---------------------------------------------------------------------------

async function deleteFact(xref, evt) {
  const label = (evt.date || '') + (evt.place ? ' \u00b7 ' + evt.place : '') || evt.tag;
  if (!confirm('Delete this fact? The GEDCOM file will be updated immediately (a backup will be saved).\n\n' + evt.tag + (label ? ': ' + label : ''))) return;
  try {
    const resp = await fetch('/api/delete_fact', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        xref,
        tag: evt.tag,
        date: evt.date || null,
        place: evt.place || null,
        type: evt.type || null,
        inline_val: evt.inline_val || null,
        current_person: xref,
      }),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      showDetail(xref, true);
    } else {
      alert('Delete failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}

// ---------------------------------------------------------------------------
// Exports (for Vitest unit tests via CommonJS require)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { _filterSpouseResults, _isFamEventTag, _buildSpouseResultsHtml, _FACT_PRESETS };
}
