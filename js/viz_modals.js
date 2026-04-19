// Edit / add / delete modals: notes, events, aliases, names.
// Pure helpers exported for testing (node require-compatible at the bottom).

// ---------------------------------------------------------------------------
// Event label lookup (B3)
// ---------------------------------------------------------------------------

const _EVT_LABEL = {
  BIRT:'Birth', DEAT:'Death', BURI:'Burial', CREM:'Cremation',
  MARR:'Marriage', DIV:'Divorce', NATU:'Naturalization',
  EMIG:'Emigration', IMMI:'Immigration', RESI:'Residence',
  OCCU:'Occupation', EDUC:'Education', RELI:'Religion',
  NATI:'Nationality', CENS:'Census', TITL:'Title',
  ADOP:'Adoption', BAPM:'Baptism', CHR:'Christening',
  CONF:'Confirmation', GRAD:'Graduation', WILL:'Will',
  PROB:'Probate',
};
function _evtLabel(tag, typeVal) {
  if ((tag === 'EVEN' || tag === 'FACT') && typeVal) return typeVal;
  return _EVT_LABEL[tag] || tag;
}

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
      setState({ panelXref: xref, panelOpen: true });
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
  setTimeout(() => { const el = document.getElementById('note-modal-textarea'); if (el) el.focus && el.focus(); }, 50);
}

function editNote(xref, noteIdx) {
  _noteEditXref = xref;
  _noteEditIdx  = noteIdx;
  const note = PEOPLE[xref] && PEOPLE[xref].notes[noteIdx];
  const noteObj = (note && typeof note === 'object') ? note : {text: note || '', shared: false, note_xref: null};
  document.getElementById('note-modal-title').textContent = 'Edit Note';
  document.getElementById('note-modal-textarea').value = noteObj.text;
  const warning = document.getElementById('note-modal-shared-warning');
  if (warning) warning.style.display = noteObj.shared ? 'block' : 'none';
  document.getElementById('note-modal-overlay').classList.add('open');
  setTimeout(() => { const el = document.getElementById('note-modal-textarea'); if (el) el.focus && el.focus(); }, 50);
}

function closeNoteModal() {
  document.getElementById('note-modal-overlay').classList.remove('open');
  const warning = document.getElementById('note-modal-shared-warning');
  if (warning) warning.style.display = 'none';
  _noteEditXref = _noteEditIdx = null;
}

async function submitNoteEdit() {
  const newText  = document.getElementById('note-modal-textarea').value;
  const xref     = _noteEditXref;
  const noteIdx  = _noteEditIdx;
  closeNoteModal();
  const isAdd = noteIdx === null;
  const url   = isAdd ? '/api/add_note' : '/api/edit_note';
  const existingNote = !isAdd && PEOPLE[xref] && PEOPLE[xref].notes[noteIdx];
  const noteXref = (existingNote && typeof existingNote === 'object' && existingNote.shared) ? existingNote.note_xref : null;
  const payload = isAdd
    ? {xref, new_text: newText, current_person: window._currentPerson || null}
    : {xref, note_idx: noteIdx, note_xref: noteXref, new_text: newText, current_person: window._currentPerson || null};
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
      setState({ panelXref: xref, panelOpen: true });
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
    _eventModalFamXref = null, _eventModalMARRIdx = null, _eventModalAddTag = null;

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
      // FACT: the preset label is already in the modal title, so hide both the
      // inline row and the TYPE row. The server still receives TYPE because
      // submitEventModal falls back to preset.type when the type row is hidden.
      inlineRow.style.display = 'none';
      typeRow.style.display   = 'none';
      const typeInp = document.getElementById('event-modal-type');
      if (typeInp) { typeInp.value = preset.type; typeInp.readOnly = true; }
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

// ── Place autocomplete ─────────────────────────────────────────────────────

function _onPlaceInput(val) {
  const q = val.trim();
  const el = document.getElementById('event-modal-place-results');
  if (!el) return;
  if (!q) { el.innerHTML = ''; return; }
  const ql = q.toLowerCase();
  const matches = (typeof ALL_PLACES !== 'undefined' ? ALL_PLACES : [])
    .filter(p => p.toLowerCase().startsWith(ql))
    .slice(0, 8);
  if (!matches.length) { el.innerHTML = ''; return; }
  el.innerHTML = matches.map(p =>
    `<div class="place-result-item" onmousedown="event.preventDefault();_selectPlace(${JSON.stringify(p).replace(/"/g, '&quot;')})">${escHtml(p)}</div>`
  ).join('');
}

function _selectPlace(place) {
  const inp = document.getElementById('event-modal-place');
  if (inp) inp.value = place;
  _clearPlaceResults();
  _updateAddrSuggestions(place);
}

function _clearPlaceResults() {
  const el = document.getElementById('event-modal-place-results');
  if (el) el.innerHTML = '';
}

let _placeBlurTimer = null;
function _schedulePlaceResultsClear() {
  clearTimeout(_placeBlurTimer);
  _placeBlurTimer = setTimeout(_clearPlaceResults, 150);
}

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
  document.getElementById('event-modal-save-btn').textContent = 'Save';
  document.getElementById('event-modal-tag-row').style.display = 'none';
  const events = (PEOPLE[xref] && PEOPLE[xref].events) || [];
  // For FAM events (MARR), match by fam_xref + marr_idx; otherwise match by tag + event_idx
  const evt = famXref
    ? (events.find(e => e.fam_xref === famXref && e.tag === tag && (marrIdx == null || e.marr_idx === marrIdx)) || {})
    : (events.find(e => e.tag === tag && e.event_idx === eventIdx) || {});
  document.getElementById('event-modal-title').textContent = 'Edit ' + _evtLabel(tag, evt.type) + ' \u2014 ' + _personName(xref);
  const placeVal = evt.place || '';
  document.getElementById('event-modal-inline').value = evt.inline_val || '';
  document.getElementById('event-modal-type').value   = evt.type || '';
  document.getElementById('event-modal-date').value   = evt.date || '';
  document.getElementById('event-modal-place').value  = placeVal;
  document.getElementById('event-modal-cause').value  = evt.cause || '';
  document.getElementById('event-modal-note').value   = evt.note || '';
  document.getElementById('event-modal-addr').value   = evt.addr || '';
  _updateAddrSuggestions(placeVal);
  // B4: pre-fill spouse for MARR events being edited
  const spouseInp = document.getElementById('event-modal-spouse-input');
  const spouseRes = document.getElementById('event-modal-spouse-results');
  if (tag === 'MARR') {
    const spouseXref = evt.spouse_xref || null;
    const spouseName = evt.spouse || (spouseXref && PEOPLE[spouseXref] && PEOPLE[spouseXref].name) || '';
    if (spouseInp) spouseInp.value = spouseName;
    if (spouseRes) spouseRes.innerHTML = '';
    _eventModalSpouseXref = spouseXref;
  } else {
    if (spouseInp) spouseInp.value = '';
    if (spouseRes) spouseRes.innerHTML = '';
    _eventModalSpouseXref = null;
  }
  _updateEventModalFields(tag);
  document.getElementById('event-modal-overlay').classList.add('open');
  const focusId = _INLINE_TYPE_TAGS.has(tag) ? 'event-modal-inline' : 'event-modal-date';
  setTimeout(() => { const el = document.getElementById(focusId); if (el) el.focus(); }, 50);
}

function addEvent(xref, defaultTag = 'RESI', prefillType) {
  _eventModalXref    = xref;
  _eventModalIdx     = null;
  _eventModalTag     = null;
  _eventModalAddTag  = defaultTag;
  _eventModalFamXref = null;
  _eventModalSpouseXref = null;
  const _preset = _FACT_PRESETS[defaultTag];
  const _title  = _preset
    ? 'Add ' + _preset.label + ' \u2014 ' + _personName(xref)
    : 'Add Event \u2014 ' + _personName(xref);
  document.getElementById('event-modal-title').textContent = _title;
  document.getElementById('event-modal-save-btn').textContent = 'Add';
  // Preset fact adds (Languages, Literacy, DSCR, NCHI, …) lock the event type —
  // the title already says what you're adding, and the dropdown doesn't carry
  // the preset pseudo-tag as an option anyway.
  document.getElementById('event-modal-tag-row').style.display = _preset ? 'none' : '';
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
  _clearPlaceResults();
}

async function submitEventModal() {
  const xref     = _eventModalXref;
  const famXref  = _eventModalFamXref;
  const isAdd    = _eventModalIdx === null && !famXref;
  // For adds, use the stored _eventModalAddTag (which may hold a preset pseudo-tag
  // like 'FACT:Languages' that isn't in the select's <option> list). Fall back to
  // the select value if the user changed the event type via the dropdown.
  const rawTag   = isAdd
    ? (_eventModalAddTag || document.getElementById('event-modal-tag').value)
    : _eventModalTag;
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
  // Include TYPE when the row is visible. For preset FACT adds (Languages,
  // Literacy, …) the row is hidden but the server still needs the TYPE value,
  // so we pull it from the preset itself.
  if (typeRow && typeRow.style.display !== 'none') {
    fields.TYPE = document.getElementById('event-modal-type').value.trim();
  } else if (isAdd && preset && !preset.showInline && preset.type) {
    fields.TYPE = preset.type;
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
        setState({ panelXref: xref, panelOpen: true });
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
      setState({ panelXref: xref, panelOpen: true });
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
  // Split currentName into given/surname for pre-fill
  const nameParts = (currentName || '').trim();
  const lastSpace = nameParts.lastIndexOf(' ');
  document.getElementById('alias-modal-given').value = lastSpace > -1 ? nameParts.slice(0, lastSpace) : nameParts;
  document.getElementById('alias-modal-surname').value = lastSpace > -1 ? nameParts.slice(lastSpace + 1) : '';
  // Set the dropdown; fall back to AKA if the value isn't in the list
  const sel = document.getElementById('alias-modal-type');
  const opt = [...sel.options].find(o => o.value === (currentType || 'AKA'));
  sel.value = opt ? opt.value : 'AKA';
  document.getElementById('alias-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('alias-modal-given').focus(), 50);
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
      setState({ panelXref: xref, panelOpen: true });
    } else { alert('Delete failed: ' + (data.error || 'unknown error')); }
  } catch (e) { alert('Request failed: ' + e); }
}

async function submitAliasModal() {
  const xref      = _aliasModalXref;
  const nameOcc   = _aliasModalNameOccurrence;
  const isAdd     = nameOcc === null || nameOcc === undefined;
  const given     = document.getElementById('alias-modal-given').value.trim();
  const surname   = document.getElementById('alias-modal-surname').value.trim();
  const name      = [given, surname].filter(Boolean).join(' ');
  const nameType  = document.getElementById('alias-modal-type').value;
  if (!name) { alert('Please enter a given name or surname.'); return; }
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
      setState({ panelXref: xref, panelOpen: true });
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
      setState({ panelXref: xref, panelOpen: true });
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
      setState({ panelXref: xref, panelOpen: true });
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
      setState({ panelXref: xref, panelOpen: true });
    } else {
      alert('Delete failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}

// ---------------------------------------------------------------------------
// Sources viewer modal
// ---------------------------------------------------------------------------

let _sourcesModalXref = null;
let _sourcesModalEventIdx = null;

function openSourcesModal(xref, eventIdx) {
  _sourcesModalXref     = xref;
  _sourcesModalEventIdx = eventIdx;
  _refreshSourcesModalContent();
  document.getElementById('sources-modal-overlay').classList.add('open');
}

function closeSourcesModal() {
  document.getElementById('sources-modal-overlay').classList.remove('open');
  _sourcesModalXref = null;
  _sourcesModalEventIdx = null;
}

function _refreshSourcesModalContent() {
  const xref     = _sourcesModalXref;
  const eventIdx = _sourcesModalEventIdx;
  if (xref == null || eventIdx == null) return;
  const evt       = PEOPLE[xref] && PEOPLE[xref].events && PEOPLE[xref].events[eventIdx];
  const citations = (evt && evt.citations) || [];
  const sources   = (typeof SOURCES !== 'undefined') ? SOURCES : {};

  // Build fact label: e.g. "Emigration · 1922"
  let label = '';
  if (evt) {
    const labelMap = (typeof EVENT_LABELS !== 'undefined') ? EVENT_LABELS : {};
    const tag  = labelMap[evt.tag] || evt.tag;
    const type = evt.type ? ` (${evt.type})` : '';
    const year = evt.date ? (' \u00b7 ' + (evt.date.match(/\b\d{4}\b/) || [''])[0]) : '';
    label = tag + type + year;
  }
  const titleEl = document.getElementById('sources-modal-title');
  const listEl  = document.getElementById('sources-modal-list');
  if (titleEl) titleEl.textContent = label || 'Sources';
  if (listEl)  listEl.innerHTML    = _buildSourcesModalContent(citations, sources, xref, evt);
}

function _buildSourcesModalContent(citations, sources, xref, evt) {
  const tag       = (evt && evt.tag) || '';
  // FAM-originated events (MARR/DIV) carry fam_xref + marr_idx/div_idx.
  // Citations on those events live on the FAM record, so we must address
  // them via the FAM xref — not the INDI xref of the currently-viewed person.
  const isFamEvt  = !!(evt && evt.fam_xref);
  const targetXref = isFamEvt ? evt.fam_xref : xref;
  let eventOcc;
  if (isFamEvt) {
    eventOcc = (tag === 'DIV')
      ? (evt.div_idx != null ? evt.div_idx : 0)
      : (evt.marr_idx != null ? evt.marr_idx : 0);
  } else {
    eventOcc = (evt && evt.event_idx != null) ? evt.event_idx : 0;
  }
  const xrefQ     = JSON.stringify(String(targetXref || '')).replace(/"/g, '&quot;');
  const factKey   = tag ? `${tag}:${eventOcc}` : '';
  const factKeyQ  = JSON.stringify(factKey).replace(/"/g, '&quot;');

  let html = '';
  if (!citations || citations.length === 0) {
    html += '<div class="src-modal-empty">No sources recorded for this fact.</div>';
  } else {
    html += citations.map((c, idx) => {
      const xrefKey = c.sourceXref || c.sour_xref;
      const src = sources[xrefKey] || {};
      const title = src.titl || src.title || xrefKey || 'Unknown source';
      const citUrl = c.url;
      const titleHtml = citUrl
        ? `<a href="${escHtml(citUrl)}" target="_blank" rel="noopener">${escHtml(title)}</a>`
        : escHtml(title);
      const pageHtml = c.page ? `<div class="src-modal-page">Page ${escHtml(c.page)}</div>` : '';
      const citeKey  = `${tag}:${eventOcc}:${idx}`;
      const citeKeyQ = JSON.stringify(citeKey).replace(/"/g, '&quot;');
      // For FAM events the API must target the FAM xref, but PEOPLE lookup uses the INDI xref.
      const indiXrefQ   = JSON.stringify(String(xref || '')).replace(/"/g, '&quot;');
      const apiXrefQ    = xrefQ;  // targetXref (FAM or INDI)
      const editOnclick = isFamEvt
        ? `showEditCitationModal(${indiXrefQ},${JSON.stringify(tag).replace(/"/g,'&quot;')},${idx},${apiXrefQ},${eventOcc})`
        : `showEditCitationModal(${xrefQ},${JSON.stringify(tag).replace(/"/g,'&quot;')},${idx},undefined,${eventOcc})`;
      return (
        `<div class="src-modal-item">` +
          `<div class="src-modal-item-body"><div class="src-modal-title">${titleHtml}</div>${pageHtml}</div>` +
          `<button class="src-modal-edit-btn" title="Edit this citation" ` +
            `onclick="${editOnclick}">\u270f</button>` +
          `<button class="src-modal-delete-btn" title="Remove this citation" ` +
            `onclick="deleteSourceFromModal(${xrefQ},${citeKeyQ})">\u00d7</button>` +
        `</div>`
      );
    }).join('');
  }
  html += `<div class="src-modal-add">` +
          `<button class="src-modal-add-btn" ` +
            `onclick="showAddCitationModal(${xrefQ},${factKeyQ})">+ Add source</button>` +
          `</div>`;
  return html;
}

async function deleteSourceFromModal(xref, citationKey) {
  if (typeof confirm === 'function' && !confirm('Remove this citation?')) return;
  try {
    const resp = await apiDeleteCitation(xref, citationKey);
    if (resp && resp.ok) {
      // FAM citations refresh both spouses; merge every returned person so
      // other panels stay in sync if the user navigates to a spouse next.
      if (resp.people) {
        for (const [k, v] of Object.entries(resp.people)) PEOPLE[k] = v;
      }
      _refreshSourcesModalContent();
      if (typeof renderPanel === 'function') renderPanel();
    } else {
      alert('Delete failed: ' + ((resp && resp.error) || 'unknown'));
    }
  } catch (e) {
    alert('Delete failed: ' + e);
  }
}

// ---------------------------------------------------------------------------
// Task 14 — New modals
// ---------------------------------------------------------------------------

// ── Helper: _personName (already defined above) ───────────────────────────

// ── showEditNameModal ─────────────────────────────────────────────────────

let _editNameModalXref = null;

function showEditNameModal(xref) {
  _editNameModalXref = xref;
  const name = (_personName(xref) || '').trim();

  // Parse "Given /Surname/" GEDCOM format or fallback heuristic
  const surnameMatch = name.match(/^(.*?)\s*\/([^/]*)\/\s*(.*)$/);
  let given = '', surname = '';
  if (surnameMatch) {
    given   = (surnameMatch[1] + ' ' + (surnameMatch[3] || '')).trim();
    surname = surnameMatch[2].trim();
  } else {
    const parts = name.split(' ');
    surname = parts.length > 1 ? parts.pop() : '';
    given   = parts.join(' ');
  }

  const titleEl    = document.getElementById('edit-name-modal-title');
  const givenEl    = document.getElementById('edit-name-modal-given');
  const surnameEl  = document.getElementById('edit-name-modal-surname');
  const overlayEl  = document.getElementById('edit-name-modal-overlay');

  if (titleEl)   titleEl.textContent = 'Edit Name \u2014 ' + name;
  if (givenEl)   givenEl.value   = given;
  if (surnameEl) surnameEl.value = surname;
  if (overlayEl) overlayEl.classList.add('open');

  if (givenEl) setTimeout(() => givenEl.focus && givenEl.focus(), 50);
}

function closeEditNameModal() {
  const overlayEl = document.getElementById('edit-name-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
  _editNameModalXref = null;
}

async function submitEditNameModal() {
  const xref    = _editNameModalXref;
  const givenEl   = document.getElementById('edit-name-modal-given');
  const surnameEl = document.getElementById('edit-name-modal-surname');
  const given   = givenEl   ? givenEl.value.trim()   : '';
  const surname = surnameEl ? surnameEl.value.trim() : '';
  closeEditNameModal();
  try {
    await apiEditName(xref, given, surname);
    if (typeof renderPanel !== 'undefined') renderPanel();
  } catch (e) {
    alert('Save failed: ' + e);
  }
}

// ── showAddNoteModal ──────────────────────────────────────────────────────

let _addNoteModalXref = null;

function showAddNoteModal(xref) {
  _addNoteModalXref = xref;

  const titleEl   = document.getElementById('add-note-modal-title');
  const textEl    = document.getElementById('add-note-modal-text');
  const overlayEl = document.getElementById('add-note-modal-overlay');

  if (titleEl)   titleEl.textContent = 'Add Note';
  if (textEl)    textEl.value = '';
  if (overlayEl) overlayEl.classList.add('open');

  if (textEl) setTimeout(() => textEl.focus && textEl.focus(), 50);
}

function closeAddNoteModal() {
  const overlayEl = document.getElementById('add-note-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
  _addNoteModalXref = null;
}

async function submitAddNoteModal() {
  const xref   = _addNoteModalXref;
  const textEl = document.getElementById('add-note-modal-text');
  const text   = textEl ? textEl.value.trim() : '';
  closeAddNoteModal();
  if (!text) return;
  try {
    await apiAddNote(xref, text);
    if (typeof renderPanel !== 'undefined') renderPanel();
  } catch (e) {
    alert('Save failed: ' + e);
  }
}

// ── showAddCitationModal ──────────────────────────────────────────────────

// `factKey` is the server-side fact key: either null/undefined for a person-level
// citation, or "TAG:N" (e.g. "BIRT:0") for a fact-level citation. Tests in the
// suite still pass a bare tag like "BIRT" — the backend accepts that too when
// there is only one occurrence, but the canonical format is "TAG:N".
let _addCitationModalXref = null, _addCitationModalFactKey = null;

function showAddCitationModal(xref, factKey) {
  _addCitationModalXref    = xref;
  _addCitationModalFactKey = factKey;

  const overlayEl  = document.getElementById('add-citation-modal-overlay');
  const sourceEl   = document.getElementById('add-citation-modal-source');
  const pageEl     = document.getElementById('add-citation-modal-page');
  const textEl     = document.getElementById('add-citation-modal-text');
  const noteEl     = document.getElementById('add-citation-modal-note');
  const urlEl      = document.getElementById('add-citation-modal-url');
  const titleEl    = document.getElementById('add-citation-modal-title');

  const displayTag = factKey ? String(factKey).split(':')[0] : '';
  if (titleEl)   titleEl.textContent = displayTag ? `Add Citation — ${displayTag}` : 'Add Person Source';
  if (pageEl)    pageEl.value  = '';
  if (textEl)    textEl.value  = '';
  if (noteEl)    noteEl.value  = '';
  if (urlEl)     urlEl.value   = '';

  // Populate sourceXref select from global SOURCES, sorted alphabetically by title
  // (case-insensitive) so users can find a specific source.
  if (sourceEl && typeof SOURCES !== 'undefined') {
    sourceEl.innerHTML = '<option value="">— select source —</option>';
    const entries = Object.entries(SOURCES).map(([sxref, src]) => ({
      sxref, label: (src && src.titl) || sxref,
    }));
    entries.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }));
    for (const { sxref, label } of entries) {
      const opt = (typeof document !== 'undefined' && document.createElement)
        ? document.createElement('option')
        : { value: '', textContent: '' };
      opt.value       = sxref;
      opt.textContent = label;
      if (sourceEl.appendChild) sourceEl.appendChild(opt);
    }
  }

  if (overlayEl) overlayEl.classList.add('open');
  if (sourceEl)  setTimeout(() => sourceEl.focus && sourceEl.focus(), 50);
}

function closeAddCitationModal() {
  const overlayEl = document.getElementById('add-citation-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
  _addCitationModalXref = _addCitationModalFactKey = null;
}

async function submitAddCitationModal() {
  const xref       = _addCitationModalXref;
  const factKey    = _addCitationModalFactKey;
  const sourceEl   = document.getElementById('add-citation-modal-source');
  const pageEl     = document.getElementById('add-citation-modal-page');
  const textEl     = document.getElementById('add-citation-modal-text');
  const noteEl     = document.getElementById('add-citation-modal-note');
  const urlEl      = document.getElementById('add-citation-modal-url');
  const sourceXref = sourceEl ? sourceEl.value : '';
  const page       = pageEl   ? pageEl.value.trim()   : '';
  const text       = textEl   ? textEl.value.trim()   : '';
  const note       = noteEl   ? noteEl.value.trim()   : '';
  const url        = urlEl    ? urlEl.value.trim()    : '';
  closeAddCitationModal();
  if (!sourceXref) { alert('Please select a source.'); return; }
  try {
    const resp = await apiAddCitation(xref, sourceXref, factKey, page, text, note, url);
    // FAM citations refresh both spouses; merge every returned person.
    if (resp && resp.people) {
      for (const [k, v] of Object.entries(resp.people)) PEOPLE[k] = v;
    }
    // If the Sources modal is still open (we arrived here from its "+ Add source"
    // button), refresh its content in place instead of closing it.
    if (_sourcesModalXref != null) _refreshSourcesModalContent();
    if (typeof renderPanel !== 'undefined') renderPanel();
  } catch (e) {
    alert('Save failed: ' + e);
  }
}

// ── showEditCitationModal ─────────────────────────────────────────────────

let _editCitationXref = null, _editCitationFactTag = null, _editCitationIndex = null;
let _editCitationSourceXref = null;
let _editCitationApiXref = null;  // may differ from _editCitationXref for FAM events
let _editCitationEventOcc = 0;

// apiXref: optional override for the xref sent to the API (use when FAM xref differs from INDI xref)
function showEditCitationModal(xref, factTag, citationIndex, apiXref, eventOcc) {
  _editCitationXref      = xref;
  _editCitationApiXref   = apiXref || xref;
  _editCitationFactTag   = factTag;
  _editCitationIndex     = citationIndex;
  _editCitationEventOcc  = (eventOcc != null) ? eventOcc : 0;

  // Locate the citation data from the person's events (always keyed by INDI xref)
  const person = (typeof PEOPLE !== 'undefined') && PEOPLE[xref];
  let cite = null;
  if (person) {
    if (factTag === null || factTag === undefined) {
      // person-level source
      cite = (person.sources || [])[citationIndex] || null;
    } else {
      const fact = (person.events || []).find(f => f.tag === factTag);
      if (fact) cite = (fact.citations || [])[citationIndex] || null;
    }
  }
  _editCitationSourceXref = cite ? (cite.sourceXref || null) : null;

  const overlayEl  = document.getElementById('edit-citation-modal-overlay');
  const pageEl     = document.getElementById('edit-citation-modal-page');
  const textEl     = document.getElementById('edit-citation-modal-text');
  const noteEl     = document.getElementById('edit-citation-modal-note');
  const urlEl      = document.getElementById('edit-citation-modal-url');
  const titleEl    = document.getElementById('edit-citation-modal-title');
  const viewSrcBtn = document.getElementById('edit-citation-view-source-btn');

  if (titleEl) titleEl.textContent = 'Edit Citation' + (factTag ? ' \u2014 ' + factTag : '');
  if (pageEl)  pageEl.value  = (cite && cite.page)  || '';
  if (textEl)  textEl.value  = (cite && cite.text)  || '';
  if (noteEl)  noteEl.value  = (cite && cite.note)  || '';
  if (urlEl)   urlEl.value   = (cite && cite.url)   || '';

  if (viewSrcBtn && _editCitationSourceXref) {
    const sxref = _editCitationSourceXref;
    viewSrcBtn.onclick = () => showEditSourceModal(sxref);
    viewSrcBtn.style   = viewSrcBtn.style || {};
    viewSrcBtn.style.display = '';
  } else if (viewSrcBtn) {
    viewSrcBtn.style = viewSrcBtn.style || {};
    viewSrcBtn.style.display = 'none';
  }

  if (overlayEl) overlayEl.classList.add('open');
  if (pageEl)    setTimeout(() => pageEl.focus && pageEl.focus(), 50);
}

function closeEditCitationModal() {
  const overlayEl = document.getElementById('edit-citation-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
  _editCitationXref = _editCitationFactTag = _editCitationIndex = null;
  _editCitationEventOcc = 0;
}

async function submitEditCitationModal() {
  const xref     = _editCitationApiXref || _editCitationXref;
  const factTag  = _editCitationFactTag;
  const index    = _editCitationIndex;
  const eventOcc = _editCitationEventOcc != null ? _editCitationEventOcc : 0;
  const pageEl  = document.getElementById('edit-citation-modal-page');
  const textEl  = document.getElementById('edit-citation-modal-text');
  const noteEl  = document.getElementById('edit-citation-modal-note');
  const urlEl   = document.getElementById('edit-citation-modal-url');
  const page    = pageEl ? pageEl.value.trim() : '';
  const text    = textEl ? textEl.value.trim() : '';
  const note    = noteEl ? noteEl.value.trim() : '';
  const url     = urlEl  ? urlEl.value.trim()  : '';
  closeEditCitationModal();
  try {
    const resp = await apiEditCitation(xref, factTag ? `${factTag}:${eventOcc}:${index}` : `SOUR:${index}`, page, text, note, url);
    if (resp && resp.people) {
      for (const [k, v] of Object.entries(resp.people)) PEOPLE[k] = v;
    }
    if (typeof renderPanel !== 'undefined') renderPanel();
  } catch (e) {
    alert('Save failed: ' + e);
  }
}

// ── showEditSourceModal ───────────────────────────────────────────────────

let _editSourceXref = null;

function showEditSourceModal(sourceXref) {
  _editSourceXref = sourceXref;
  const src = (typeof SOURCES !== 'undefined' && SOURCES[sourceXref]) || {};

  const overlayEl  = document.getElementById('edit-source-modal-overlay');
  const titlEl     = document.getElementById('edit-source-modal-titl');
  const authEl     = document.getElementById('edit-source-modal-auth');
  const publEl     = document.getElementById('edit-source-modal-publ');
  const repoEl     = document.getElementById('edit-source-modal-repo');
  const noteEl     = document.getElementById('edit-source-modal-note');
  const warningEl  = document.getElementById('edit-source-modal-warning');
  const titleEl    = document.getElementById('edit-source-modal-title');

  if (titleEl)   titleEl.textContent = 'Edit Source Record';
  if (warningEl) warningEl.textContent = 'Changes to this source record affect all citations that reference it.';
  if (titlEl)    titlEl.value = src.titl || '';
  if (authEl)    authEl.value = src.auth || '';
  if (publEl)    publEl.value = src.publ || '';
  if (repoEl)    repoEl.value = src.repo || '';
  if (noteEl)    noteEl.value = src.note || '';

  if (overlayEl) overlayEl.classList.add('open');
  if (titlEl)    setTimeout(() => titlEl.focus && titlEl.focus(), 50);
}

function closeEditSourceModal() {
  const overlayEl = document.getElementById('edit-source-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
  _editSourceXref = null;
}

async function submitEditSourceModal() {
  const sourceXref = _editSourceXref;
  const titlEl = document.getElementById('edit-source-modal-titl');
  const authEl = document.getElementById('edit-source-modal-auth');
  const publEl = document.getElementById('edit-source-modal-publ');
  const repoEl = document.getElementById('edit-source-modal-repo');
  const noteEl = document.getElementById('edit-source-modal-note');
  const fields = {
    titl: titlEl ? titlEl.value.trim() : '',
    auth: authEl ? authEl.value.trim() : '',
    publ: publEl ? publEl.value.trim() : '',
    repo: repoEl ? repoEl.value.trim() : '',
    note: noteEl ? noteEl.value.trim() : '',
  };
  if (!fields.titl) { alert('Title is required.'); return; }
  closeEditSourceModal();
  try {
    await apiEditSourceRecord(sourceXref, fields);
    if (typeof renderPanel !== 'undefined') renderPanel();
  } catch (e) {
    alert('Save failed: ' + e);
  }
}

// ── showAddGodparentModal ─────────────────────────────────────────────────

let _addGodparentXref = null, _addGodparentSelectedXref = null;

function showAddGodparentModal(xref) {
  _addGodparentXref         = xref;
  _addGodparentSelectedXref = null;

  const overlayEl  = document.getElementById('add-godparent-modal-overlay');
  const searchEl   = document.getElementById('add-godparent-modal-search');
  const resultsEl  = document.getElementById('add-godparent-modal-results');
  const titleEl    = document.getElementById('add-godparent-modal-title');

  if (titleEl)  titleEl.textContent = 'Add Godparent';
  if (searchEl) searchEl.value = '';
  if (resultsEl) resultsEl.innerHTML = '';

  if (overlayEl) overlayEl.classList.add('open');
  if (searchEl)  setTimeout(() => searchEl.focus && searchEl.focus(), 50);
}

function closeAddGodparentModal() {
  const overlayEl = document.getElementById('add-godparent-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
  _addGodparentXref = _addGodparentSelectedXref = null;
}

function _renderGodparentResults(query) {
  const container = document.getElementById('add-godparent-modal-results');
  if (!container) return;
  const q = query.trim().toLowerCase();
  if (!q) { container.innerHTML = ''; return; }
  const hits = (typeof ALL_PEOPLE !== 'undefined' ? ALL_PEOPLE : [])
    .filter(p => p.name && p.name.toLowerCase().includes(q))
    .slice(0, 12);
  container.innerHTML = hits.map(p =>
    `<div class="godparent-result-item" data-xref="${escHtml(p.id)}" data-name="${escHtml(p.name)}">${escHtml(p.name)}${p.birth_year ? ' (' + p.birth_year + ')' : ''}</div>`
  ).join('');
}

function _selectGodparent(xref, name) {
  const inp = document.getElementById('add-godparent-modal-search');
  const res = document.getElementById('add-godparent-modal-results');
  if (inp) inp.value = name;
  if (res) res.innerHTML = '';
  _addGodparentSelectedXref = xref;
}

document.addEventListener('click', e => {
  const item = e.target.closest('.godparent-result-item');
  if (item) _selectGodparent(item.dataset.xref, item.dataset.name);
});

document.addEventListener('input', e => {
  if (e.target.id === 'add-godparent-modal-search') _renderGodparentResults(e.target.value);
});

async function submitAddGodparentModal() {
  const xref          = _addGodparentXref;
  const godparentXref = _addGodparentSelectedXref;
  const sex  = (typeof PEOPLE !== 'undefined' && PEOPLE[godparentXref]?.sex) || 'U';
  const rela = sex === 'M' ? 'Godfather' : sex === 'F' ? 'Godmother' : 'Godparent';
  closeAddGodparentModal();
  if (!godparentXref) { alert('Please select a godparent from the search results.'); return; }
  try {
    const resp = await apiAddGodparent(xref, godparentXref, rela);
    if (resp && resp.people && resp.people[xref]) PEOPLE[xref] = resp.people[xref];
    if (typeof renderPanel !== 'undefined') renderPanel();
  } catch (e) {
    alert('Save failed: ' + e);
  }
}

// ── openAddPersonModal ────────────────────────────────────────────────────

let _addPersonRelXref = null, _addPersonRelType = null;
const _ADD_PERSON_REL_LABELS = {
  parent_of:  'Parent',
  sibling_of: 'Sibling',
  spouse_of:  'Spouse',
  child_of:   'Child',
};

function openAddPersonModal(xref, relType) {
  _addPersonRelXref = xref;
  _addPersonRelType = relType;

  const overlayEl  = document.getElementById('add-person-modal-overlay');
  const titleEl    = document.getElementById('add-person-modal-title');
  const givenEl    = document.getElementById('add-person-modal-given');
  const surnEl     = document.getElementById('add-person-modal-surname');
  const sexEl      = document.getElementById('add-person-modal-sex');
  const byEl       = document.getElementById('add-person-modal-birth-year');
  const otherRowEl = document.getElementById('add-person-modal-other-parent-row');
  const otherSelEl = document.getElementById('add-person-modal-other-parent');

  const label = _ADD_PERSON_REL_LABELS[relType] || 'Person';
  if (titleEl) titleEl.textContent = 'Add ' + label;
  if (givenEl) givenEl.value = '';
  if (surnEl)  surnEl.value = '';
  if (sexEl)   sexEl.value = 'U';
  if (byEl)    byEl.value = '';

  if (relType === 'child_of' && otherSelEl && otherRowEl) {
    const person = PEOPLE[xref] || {};
    const seen = new Set();
    const spouses = [];
    for (const e of (person.events || [])) {
      if (e.tag === 'MARR' && e.spouse_xref && !seen.has(e.spouse_xref)) {
        seen.add(e.spouse_xref);
        spouses.push({ xref: e.spouse_xref, name: e.spouse || (PEOPLE[e.spouse_xref] && PEOPLE[e.spouse_xref].name) || e.spouse_xref });
      }
    }
    const opts = spouses.map(s => `<option value="${escHtml(s.xref)}">${escHtml(s.name)}</option>`).join('')
               + '<option value="__none__">No other parent (new family)</option>';
    otherSelEl.innerHTML = opts;
    otherSelEl.value = spouses.length ? spouses[0].xref : '__none__';
    otherRowEl.style.display = '';
  } else if (otherRowEl) {
    otherRowEl.style.display = 'none';
  }

  if (overlayEl) overlayEl.classList.add('open');
  if (givenEl)   setTimeout(() => givenEl.focus && givenEl.focus(), 50);
}

function closeAddPersonModal() {
  const overlayEl = document.getElementById('add-person-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
  _addPersonRelXref = _addPersonRelType = null;
}

// ── changeParent (pencil + X next to a parent row) ────────────────────────

let _changeParentChildXref = null, _changeParentCurrentXref = null, _changeParentNewXref = null;

function openChangeParentModal(childXref, currentParentXref) {
  _changeParentChildXref   = childXref;
  _changeParentCurrentXref = currentParentXref;
  _changeParentNewXref     = null;

  const overlayEl = document.getElementById('change-parent-modal-overlay');
  const titleEl   = document.getElementById('change-parent-modal-title');
  const searchEl  = document.getElementById('change-parent-modal-search');
  const resultsEl = document.getElementById('change-parent-modal-results');

  const curName = (PEOPLE[currentParentXref] && PEOPLE[currentParentXref].name) || currentParentXref;
  if (titleEl)   titleEl.textContent = 'Change parent: ' + curName;
  if (searchEl)  searchEl.value = '';
  if (resultsEl) resultsEl.innerHTML = '';
  if (overlayEl) overlayEl.classList.add('open');
  if (searchEl)  setTimeout(() => searchEl.focus && searchEl.focus(), 50);
}

function closeChangeParentModal() {
  const overlayEl = document.getElementById('change-parent-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
  _changeParentChildXref = _changeParentCurrentXref = _changeParentNewXref = null;
}

function _renderChangeParentResults(query) {
  const container = document.getElementById('change-parent-modal-results');
  if (!container) return;
  const q = query.trim().toLowerCase();
  if (!q) { container.innerHTML = ''; return; }
  const hits = (typeof ALL_PEOPLE !== 'undefined' ? ALL_PEOPLE : [])
    .filter(p => p.name && p.name.toLowerCase().includes(q))
    .slice(0, 12);
  container.innerHTML = hits.map(p =>
    `<div class="change-parent-result-item" data-xref="${escHtml(p.id)}" data-name="${escHtml(p.name)}">${escHtml(p.name)}${p.birth_year ? ' (' + p.birth_year + ')' : ''}</div>`
  ).join('');
}

function _selectChangeParent(xref, name) {
  const inp = document.getElementById('change-parent-modal-search');
  const res = document.getElementById('change-parent-modal-results');
  if (inp) inp.value = name;
  if (res) res.innerHTML = '';
  _changeParentNewXref = xref;
}

document.addEventListener('click', e => {
  const item = e.target.closest('.change-parent-result-item');
  if (item) _selectChangeParent(item.dataset.xref, item.dataset.name);
});

document.addEventListener('input', e => {
  if (e.target.id === 'change-parent-modal-search') {
    _changeParentNewXref = null;
    _renderChangeParentResults(e.target.value);
  }
});

async function submitChangeParentModal() {
  const childXref = _changeParentChildXref;
  const currentXref = _changeParentCurrentXref;
  const newXref = _changeParentNewXref;  // may be null when user cleared / never selected
  const searchEl = document.getElementById('change-parent-modal-search');
  const searchVal = searchEl ? searchEl.value.trim() : '';

  // If the user typed text but didn't pick a result, refuse to proceed.
  if (searchVal && !newXref) {
    alert('Please select a person from the search results, or clear the field to remove the parent.');
    return;
  }

  await _postChangeParent(childXref, currentXref, newXref || '');
  closeChangeParentModal();
}

async function removeParent(childXref, parentXref) {
  const name = (PEOPLE[parentXref] && PEOPLE[parentXref].name) || parentXref;
  if (!confirm(`Remove ${name} as a parent? The other parent and siblings are preserved.`)) return;
  await _postChangeParent(childXref, parentXref, '');
}

async function _postChangeParent(childXref, currentXref, newXref) {
  try {
    const resp = await fetch('/api/change_parent', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        xref: childXref,
        current_parent_xref: currentXref,
        new_parent_xref: newXref,
        current_person: window._currentPerson || null,
      }),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people) for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      if (typeof _applyFamilyMaps === 'function') _applyFamilyMaps(data.family_maps);
      window._openDetailKey = null;
      setState({ panelXref: childXref, panelOpen: true });
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}

async function submitAddPersonModal() {
  const given = (document.getElementById('add-person-modal-given').value || '').trim();
  const surn  = (document.getElementById('add-person-modal-surname').value || '').trim();
  const sex   = document.getElementById('add-person-modal-sex').value || 'U';
  const birthYear = (document.getElementById('add-person-modal-birth-year').value || '').trim();
  const relXref = _addPersonRelXref;
  const relType = _addPersonRelType;

  if (!given) { alert('Given name is required.'); return; }
  if (!relXref || !relType) { alert('Missing relationship context.'); return; }

  const body = {
    given, surn, sex, birth_year: birthYear,
    rel_type: relType, rel_xref: relXref,
    current_person: window._currentPerson || null,
  };
  if (relType === 'child_of') {
    const otherSelEl = document.getElementById('add-person-modal-other-parent');
    const v = otherSelEl ? otherSelEl.value : '';
    body.other_parent_xref = (v === '__none__') ? '' : v;
  }

  try {
    const resp = await fetch('/api/add_person', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await resp.json();
    if (data.ok) {
      if (data.people) for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
      if (typeof _applyFamilyMaps === 'function') _applyFamilyMaps(data.family_maps);
      closeAddPersonModal();
      window._openDetailKey = null;
      setState({ panelXref: relXref, panelOpen: true });
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}

// ── showAddSourceModal ────────────────────────────────────────────────────

function showAddSourceModal() {
  const overlayEl = document.getElementById('add-source-modal-overlay');
  const titlEl    = document.getElementById('add-source-modal-titl');
  const authEl    = document.getElementById('add-source-modal-auth');
  const publEl    = document.getElementById('add-source-modal-publ');
  const repoEl    = document.getElementById('add-source-modal-repo');
  const noteEl    = document.getElementById('add-source-modal-note');

  if (titlEl) titlEl.value = '';
  if (authEl) authEl.value = '';
  if (publEl) publEl.value = '';
  if (repoEl) repoEl.value = '';
  if (noteEl) noteEl.value = '';

  if (overlayEl) overlayEl.classList.add('open');
  if (titlEl)    setTimeout(() => titlEl.focus && titlEl.focus(), 50);
}

function closeAddSourceModal() {
  const overlayEl = document.getElementById('add-source-modal-overlay');
  if (overlayEl) overlayEl.classList.remove('open');
}

async function submitAddSourceModal() {
  const titlEl = document.getElementById('add-source-modal-titl');
  const authEl = document.getElementById('add-source-modal-auth');
  const publEl = document.getElementById('add-source-modal-publ');
  const repoEl = document.getElementById('add-source-modal-repo');
  const noteEl = document.getElementById('add-source-modal-note');
  const titl   = titlEl ? titlEl.value.trim() : '';
  const auth   = authEl ? authEl.value.trim() : '';
  const publ   = publEl ? publEl.value.trim() : '';
  const repo   = repoEl ? repoEl.value.trim() : '';
  const note   = noteEl ? noteEl.value.trim() : '';
  if (!titl) { alert('Title is required.'); return; }
  closeAddSourceModal();
  try {
    await apiAddSource(titl, auth, publ, repo, note);
    if (typeof setState !== 'undefined') setState({});   // trigger re-render
  } catch (e) {
    alert('Save failed: ' + e);
  }
}

// ---------------------------------------------------------------------------
// Exports (for Vitest unit tests via CommonJS require)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    _filterSpouseResults, _isFamEventTag, _buildSpouseResultsHtml, _FACT_PRESETS,
    openSourcesModal, closeSourcesModal, _buildSourcesModalContent,
    deleteSourceFromModal,
    showEditNameModal, showAddNoteModal, showAddCitationModal,
    showEditCitationModal, submitEditCitationModal, showEditSourceModal, showAddGodparentModal,
    submitAddGodparentModal, _selectGodparent,
    showAddSourceModal,
    _evtLabel, editEvent,
    deleteNote, submitNoteEdit, editNote, deleteFact,
    _onPlaceInput, _selectPlace, _clearPlaceResults,
  };
}
