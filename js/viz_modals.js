// Edit / add / delete modals: notes, events, aliases, names.
// All functions are DOM-dependent and are not exported for tests.

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
      _openDetailKey = null;
      showDetail(xref);
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
      _openDetailKey = null;
      showDetail(xref);
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

function _updateEventModalFields(tag) {
  const inlineRow = document.getElementById('event-modal-inline-row');
  const inlineLbl = document.getElementById('event-modal-inline-label');
  const typeRow   = document.getElementById('event-modal-type-row');
  const causeRow  = document.getElementById('event-modal-cause-row');
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
  setTimeout(() => document.getElementById('event-modal-date').focus(), 50);
}

function addEvent(xref, defaultTag = 'RESI', prefillType) {
  _eventModalXref    = xref;
  _eventModalIdx     = null;
  _eventModalTag     = null;
  _eventModalFamXref = null;
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
  _updateAddrSuggestions('');
  _updateEventModalFields(defaultTag);
  document.getElementById('event-modal-overlay').classList.add('open');
  setTimeout(() => document.getElementById('event-modal-date').focus(), 50);
}

function closeEventModal() {
  document.getElementById('event-modal-overlay').classList.remove('open');
  _eventModalXref = _eventModalIdx = _eventModalTag = _eventModalFamXref = _eventModalMARRIdx = null;
}

async function submitEventModal() {
  const xref     = _eventModalXref;
  const famXref  = _eventModalFamXref;
  const isAdd    = _eventModalIdx === null && !famXref;
  const tag      = isAdd ? document.getElementById('event-modal-tag').value : _eventModalTag;
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
      _openDetailKey = null;
      showDetail(xref);
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
      _openDetailKey = null; showDetail(xref);
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
      _openDetailKey = null; showDetail(xref);
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
      _openDetailKey = null;
      showDetail(xref);
    } else {
      alert('Save failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) { alert('Request failed: ' + e); }
}

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
      _openDetailKey = null;
      showDetail(xref);
    } else {
      alert('Delete failed: ' + (data.error || 'unknown error'));
    }
  } catch (e) {
    alert('Request failed: ' + e);
  }
}
