// Person-level modals: notes, alias, name, godparent, add-person,
// change-parent, spouse-menu, fact/person delete.


let _noteEditXref = null,
    _noteEditIdx = null,
    _noteEditEventCtx = null;

// Citation clipboard — persists across modal opens within the same page session.


async function deleteNote(xref, noteIdx, eventCtx = null) {
    if (!confirm('Delete this note? The GEDCOM file will be updated immediately (a backup will be saved).')) return;
    try {
        let url, body;
        if (eventCtx) {
            const evt = PEOPLE[xref] && PEOPLE[xref].events &&
                PEOPLE[xref].events.find(e => e.tag === eventCtx.tag && e.event_idx === eventCtx.eventIdx);
            const note = evt && evt.event_notes && evt.event_notes[noteIdx];
            url = '/api/delete_event_note';
            body = {
                xref,
                tag: eventCtx.tag,
                event_idx: eventCtx.eventIdx,
                note_idx: noteIdx,
                note_xref: (note && note.shared) ? note.note_xref : null,
                current_person: window._currentPerson || null,
            };
        } else {
            url = '/api/delete_note';
            body = { xref, note_idx: noteIdx, current_person: window._currentPerson || null };
        }
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
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
    _noteEditIdx = null; // null = add mode
    _noteEditEventCtx = null;
    document.getElementById('note-modal-title').textContent = 'Add Note';
    document.getElementById('note-modal-textarea').value = '';
    document.getElementById('note-modal-overlay').classList.add('open');
    setTimeout(() => { const el = document.getElementById('note-modal-textarea'); if (el) el.focus && el.focus(); }, 50);
}


function editNote(xref, noteIdx) {
    _noteEditXref = xref;
    _noteEditIdx = noteIdx;
    _noteEditEventCtx = null;
    const note = PEOPLE[xref] && PEOPLE[xref].notes[noteIdx];
    const noteObj = (note && typeof note === 'object') ? note : { text: note || '', shared: false, note_xref: null };
    document.getElementById('note-modal-title').textContent = 'Edit Note';
    document.getElementById('note-modal-textarea').value = noteObj.text;
    const warning = document.getElementById('note-modal-shared-warning');
    if (warning) warning.style.display = noteObj.shared ? 'block' : 'none';
    document.getElementById('note-modal-overlay').classList.add('open');
    setTimeout(() => { const el = document.getElementById('note-modal-textarea'); if (el) el.focus && el.focus(); }, 50);
}


function editEventNote(xref, tag, eventIdx, noteIdx) {
    const evt = PEOPLE[xref] && PEOPLE[xref].events &&
        PEOPLE[xref].events.find(e => e.tag === tag && e.event_idx === eventIdx);
    const note = evt && evt.event_notes && evt.event_notes[noteIdx];
    if (!note) return;
    _noteEditXref = xref;
    _noteEditIdx = noteIdx;
    _noteEditEventCtx = { tag, eventIdx };
    document.getElementById('note-modal-title').textContent = 'Edit Note';
    document.getElementById('note-modal-textarea').value = note.text;
    const warning = document.getElementById('note-modal-shared-warning');
    if (warning) warning.style.display = note.shared ? 'block' : 'none';
    document.getElementById('note-modal-overlay').classList.add('open');
    setTimeout(() => { const el = document.getElementById('note-modal-textarea'); if (el) el.focus && el.focus(); }, 50);
}


function closeNoteModal() {
    document.getElementById('note-modal-overlay').classList.remove('open');
    const warning = document.getElementById('note-modal-shared-warning');
    if (warning) warning.style.display = 'none';
    _noteEditXref = _noteEditIdx = null;
    _noteEditEventCtx = null;
}


async function submitNoteEdit() {
    const newText = document.getElementById('note-modal-textarea').value;
    const xref = _noteEditXref;
    const noteIdx = _noteEditIdx;
    const eventCtx = _noteEditEventCtx;  // capture BEFORE closeNoteModal clears it
    closeNoteModal();

    if (eventCtx) {
        const evt = PEOPLE[xref] && PEOPLE[xref].events &&
            PEOPLE[xref].events.find(e => e.tag === eventCtx.tag && e.event_idx === eventCtx.eventIdx);
        const note = evt && evt.event_notes && evt.event_notes[noteIdx];
        const noteXref = (note && note.shared) ? note.note_xref : null;
        const url = noteXref ? '/api/edit_note' : '/api/edit_event_note';
        const body = noteXref
            ? { xref, note_xref: noteXref, note_idx: noteIdx, new_text: newText, current_person: window._currentPerson || null }
            : { xref, tag: eventCtx.tag, event_idx: eventCtx.eventIdx, note_idx: noteIdx, new_text: newText, current_person: window._currentPerson || null };
        try {
            const resp = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json();
            if (data.ok) {
                if (data.people && data.people[xref]) PEOPLE[xref] = data.people[xref];
                setState({ panelXref: xref, panelOpen: true });
            } else {
                alert('Edit failed: ' + (data.error || 'unknown error'));
            }
        } catch (e) { alert('Request failed: ' + e); }
        return;
    }

    // existing top-level note path (unchanged)
    const isAdd = noteIdx === null;
    const url = isAdd ? '/api/add_note' : '/api/edit_note';
    const existingNote = !isAdd && PEOPLE[xref] && PEOPLE[xref].notes[noteIdx];
    const noteXref = (existingNote && typeof existingNote === 'object' && existingNote.shared) ? existingNote.note_xref : null;
    const payload = isAdd ?
        { xref, new_text: newText, current_person: window._currentPerson || null } :
        { xref, note_idx: noteIdx, note_xref: noteXref, new_text: newText, current_person: window._currentPerson || null };
    try {
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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


let _aliasModalXref = null,
    _aliasModalNameOccurrence = null,
    _aliasModalIsNameRecord = false;


function openAliasModal(xref, nameOccurrence, currentName, currentType, isNameRecord) {
    _aliasModalXref = xref;
    _aliasModalNameOccurrence = nameOccurrence; // null = add mode
    _aliasModalIsNameRecord = !!isNameRecord;
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
    setTimeout(() => document.getElementById('alias-modal-given')?.focus?.(), 50);
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
        body = {
            xref,
            tag: evt.tag,
            date: evt.date || null,
            place: evt.place || null,
            type: evt.type || null,
            inline_val: evt.inline_val || null,
            current_person: xref
        };
    }
    try {
        const resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.ok) {
            if (data.people)
                for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
            setState({ panelXref: xref, panelOpen: true });
        } else { alert('Delete failed: ' + (data.error || 'unknown error')); }
    } catch (e) { alert('Request failed: ' + e); }
}


async function submitAliasModal() {
    const xref = _aliasModalXref;
    const nameOcc = _aliasModalNameOccurrence;
    const isAdd = nameOcc === null || nameOcc === undefined;
    const given = document.getElementById('alias-modal-given').value.trim();
    const surname = document.getElementById('alias-modal-surname').value.trim();
    const name = [given, surname].filter(Boolean).join(' ');
    const nameType = document.getElementById('alias-modal-type').value;
    if (!name) { alert('Please enter a given name or surname.'); return; }
    closeAliasModal();
    let endpoint, body;
    if (isAdd) {
        endpoint = '/api/add_secondary_name';
        body = { xref, name, name_type: nameType, current_person: window._currentPerson || null };
    } else {
        endpoint = '/api/edit_secondary_name';
        body = {
            xref,
            name_occurrence: nameOcc,
            name,
            name_type: nameType,
            current_person: window._currentPerson || null
        };
    }
    try {
        const resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.ok) {
            if (data.people)
                for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
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
    const person = PEOPLE[xref] || {};
    const name = (person.name || '').trim();

    // Use explicit sub-tag fields when present; fall back to heuristic string split
    let given = '', surname = '', suffix = '';
    if (person.name_given != null || person.name_surname != null) {
        given   = person.name_given   || '';
        surname = person.name_surname || '';
        suffix  = person.name_suffix  || '';
    } else {
        const surnameMatch = name.match(/^(.*?)\s*\/([^/]*)\/\s*(.*)$/);
        if (surnameMatch) {
            given   = (surnameMatch[1] + ' ' + (surnameMatch[3] || '')).trim();
            surname = surnameMatch[2].trim();
        } else {
            const parts = name.split(' ');
            surname = parts.length > 1 ? parts.pop() : '';
            given   = parts.join(' ');
        }
    }

    document.getElementById('name-modal-title').textContent = 'Edit Name \u2014 ' + name;
    document.getElementById('name-modal-given').value   = given;
    document.getElementById('name-modal-surname').value = surname;
    const suffixEl = document.getElementById('name-modal-suffix');
    if (suffixEl) suffixEl.value = suffix;
    document.getElementById('name-modal-overlay').classList.add('open');
    setTimeout(() => document.getElementById('name-modal-given')?.focus?.(), 50);
}


function closeNameModal() {
    document.getElementById('name-modal-overlay').classList.remove('open');
    _nameModalXref = null;
}


async function submitNameModal() {
    const xref = _nameModalXref;
    const givenName = document.getElementById('name-modal-given').value.trim();
    const surname   = document.getElementById('name-modal-surname').value.trim();
    const suffixEl  = document.getElementById('name-modal-suffix');
    const suffix    = suffixEl ? suffixEl.value.trim() : '';
    closeNameModal();
    try {
        const resp = await fetch('/api/edit_name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                xref,
                given_name: givenName,
                surname,
                suffix,
                current_person: window._currentPerson || null
            }),
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


async function deleteFact(xref, evt) {
    const label = (evt.date || '') + (evt.place ? ' \u00b7 ' + evt.place : '') || evt.tag;
    if (!confirm('Delete this fact? The GEDCOM file will be updated immediately (a backup will be saved).\n\n' + evt.tag + (label ? ': ' + label : ''))) return;
    try {
        const resp = await fetch('/api/delete_fact', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                xref,
                tag: evt.tag,
                date: evt.date || null,
                place: evt.place || null,
                type: evt.type || null,
                inline_val: evt.inline_val || null,
                ...(evt.event_idx != null ? { event_idx: evt.event_idx } : {}),
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


let _editNameModalXref = null;


function showEditNameModal(xref) {
    _editNameModalXref = xref;
    const name = (_personName(xref) || '').trim();

    // Parse "Given /Surname/" GEDCOM format or fallback heuristic
    const surnameMatch = name.match(/^(.*?)\s*\/([^/]*)\/\s*(.*)$/);
    let given = '',
        surname = '';
    if (surnameMatch) {
        given = (surnameMatch[1] + ' ' + (surnameMatch[3] || '')).trim();
        surname = surnameMatch[2].trim();
    } else {
        const parts = name.split(' ');
        surname = parts.length > 1 ? parts.pop() : '';
        given = parts.join(' ');
    }

    const titleEl = document.getElementById('edit-name-modal-title');
    const givenEl = document.getElementById('edit-name-modal-given');
    const surnameEl = document.getElementById('edit-name-modal-surname');
    const overlayEl = document.getElementById('edit-name-modal-overlay');

    if (titleEl) titleEl.textContent = 'Edit Name \u2014 ' + name;
    if (givenEl) givenEl.value = given;
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
    const xref = _editNameModalXref;
    const givenEl = document.getElementById('edit-name-modal-given');
    const surnameEl = document.getElementById('edit-name-modal-surname');
    const given = givenEl ? givenEl.value.trim() : '';
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

    const titleEl = document.getElementById('add-note-modal-title');
    const textEl = document.getElementById('add-note-modal-text');
    const overlayEl = document.getElementById('add-note-modal-overlay');

    if (titleEl) titleEl.textContent = 'Add Note';
    if (textEl) textEl.value = '';
    if (overlayEl) overlayEl.classList.add('open');

    if (textEl) setTimeout(() => textEl.focus && textEl.focus(), 50);
}


function closeAddNoteModal() {
    const overlayEl = document.getElementById('add-note-modal-overlay');
    if (overlayEl) overlayEl.classList.remove('open');
    _addNoteModalXref = null;
}


async function submitAddNoteModal() {
    const xref = _addNoteModalXref;
    const textEl = document.getElementById('add-note-modal-text');
    const text = textEl ? textEl.value.trim() : '';
    closeAddNoteModal();
    if (!text) return;
    try {
        await apiAddNote(xref, text);
        if (typeof renderPanel !== 'undefined') renderPanel();
    } catch (e) {
        alert('Save failed: ' + e);
    }
}

// ── Apply-to-events picker (person-level source modals only) ──────────────
//
// When a user adds or edits a *person-level* source, the modal shows a
// checklist of the person's events. Checking events causes that source to be
// attached at the event level too. State is shared between the add and edit
// modals (only one is open at a time).


async function deleteGodparent(xref, godparentXref) {
    const gpName = (typeof PEOPLE !== 'undefined' && PEOPLE[godparentXref]?.name) || godparentXref;
    if (!confirm('Remove ' + gpName + ' as godparent? The GEDCOM file will be updated immediately.')) return;
    try {
        const resp = await apiDeleteGodparent(xref, godparentXref);
        if (resp && resp.people && resp.people[xref]) PEOPLE[xref] = resp.people[xref];
        if (typeof renderPanel !== 'undefined') renderPanel();
    } catch (e) {
        alert('Delete failed: ' + e);
    }
}

// ── openAddPersonModal ────────────────────────────────────────────────────


let _addPersonRelXref = null,
    _addPersonRelType = null;

let _addPersonFromTreeXref = null;

const _ADD_PERSON_REL_LABELS = {
    parent_of: 'Parent',
    sibling_of: 'Sibling',
    spouse_of: 'Spouse',
    child_of: 'Child',
    godparent_of: 'Godparent',
};


function _renderAddPersonTreeResults(query) {
    const q = (query || '').trim().toLowerCase();
    if (!q) return [];
    const qNorm = (typeof _normSearchS !== 'undefined') ? _normSearchS(q) : q;
    const all = (typeof ALL_PEOPLE !== 'undefined' ? ALL_PEOPLE : [])
        .filter(p => p.name && p.name.toLowerCase().includes(q));
    const sorted = (typeof sortHits !== 'undefined') ? sortHits(all, qNorm) : all;
    return sorted.map(p => {
        const dates = [p.birth_year && `b. ${p.birth_year}`,
            p.death_year && `d. ${p.death_year}`
        ].filter(Boolean).join(' – ');
        return { id: p.id, name: p.name, label: p.name + (dates ? ` (${dates})` : '') };
    });
}


function _onAddPersonModeChange() {
    let mode = 'new';
    for (const r of document.getElementsByName('add-person-mode')) {
        if (r.checked) { mode = r.value; break; }
    }
    const modal = document.getElementById('add-person-modal');
    const formRows = modal ? modal.querySelectorAll(
        '.add-person-row-name, .add-person-row-full, .add-person-row-2col, #add-person-modal-death-row'
    ) : [];
    const fromTree = document.getElementById('add-person-from-tree');
    if (mode === 'existing') {
        formRows.forEach(el => { el.style.display = 'none'; });
        if (fromTree) fromTree.style.display = '';
        const searchEl = document.getElementById('add-person-tree-search');
        if (searchEl) setTimeout(() => searchEl.focus && searchEl.focus(), 50);
    } else {
        formRows.forEach(el => { el.style.display = ''; });
        if (fromTree) fromTree.style.display = 'none';
        _onAddPersonStatusChange();
    }
}


function openAddPersonModal(xref, relType) {
    _addPersonRelXref = xref;
    _addPersonRelType = relType;

    const overlayEl = document.getElementById('add-person-modal-overlay');
    const titleEl = document.getElementById('add-person-modal-title');
    const givenEl = document.getElementById('add-person-modal-given');
    const surnEl = document.getElementById('add-person-modal-surname');
    const suffixEl = document.getElementById('add-person-modal-suffix');
    const sexEl = document.getElementById('add-person-modal-sex');
    const bdEl = document.getElementById('add-person-modal-birth-date');
    const bpEl = document.getElementById('add-person-modal-birth-place');
    const ddEl = document.getElementById('add-person-modal-death-date');
    const dpEl = document.getElementById('add-person-modal-death-place');
    const otherRowEl = document.getElementById('add-person-modal-other-parent-row');
    const otherSelEl = document.getElementById('add-person-modal-other-parent');

    const label = _ADD_PERSON_REL_LABELS[relType] || 'Person';
    if (titleEl) titleEl.textContent = 'Add ' + label;
    if (givenEl) givenEl.value = '';
    if (surnEl) surnEl.value = '';
    if (suffixEl) suffixEl.value = '';
    if (sexEl) sexEl.value = 'U';
    if (bdEl) bdEl.value = '';
    if (bpEl) bpEl.value = '';
    if (ddEl) ddEl.value = '';
    if (dpEl) dpEl.value = '';

    // Default status = Deceased; show death row.
    const statusRadios = document.getElementsByName('add-person-modal-status');
    for (const r of statusRadios) r.checked = (r.value === 'deceased');
    _onAddPersonStatusChange();

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
        const opts = spouses.map(s => `<option value="${escHtml(s.xref)}">${escHtml(s.name)}</option>`).join('') +
            '<option value="__none__">No other parent (new family)</option>';
        otherSelEl.innerHTML = opts;
        otherSelEl.value = spouses.length ? spouses[0].xref : '__none__';
        otherRowEl.style.display = '';
    } else if (otherRowEl) {
        otherRowEl.style.display = 'none';
    }

    if (overlayEl) overlayEl.classList.add('open');
    const defaultMode = (relType === 'godparent_of') ? 'existing' : 'new';
    for (const r of document.getElementsByName('add-person-mode')) r.checked = (r.value === defaultMode);
    _addPersonFromTreeXref = null;
    const treeSearchEl = document.getElementById('add-person-tree-search');
    if (treeSearchEl) treeSearchEl.value = '';
    const treeResultsEl = document.getElementById('add-person-tree-results');
    if (treeResultsEl) treeResultsEl.innerHTML = '';
    _onAddPersonModeChange();
    if (defaultMode === 'new' && givenEl) setTimeout(() => givenEl.focus && givenEl.focus(), 50);
}


function closeAddPersonModal() {
    const overlayEl = document.getElementById('add-person-modal-overlay');
    if (overlayEl) overlayEl.classList.remove('open');
    _addPersonRelXref = _addPersonRelType = null;
    _addPersonFromTreeXref = null;
}


function _onAddPersonStatusChange() {
    const radios = document.getElementsByName('add-person-modal-status');
    let val = '';
    for (const r of radios) if (r.checked) { val = r.value; break; }
    const row = document.getElementById('add-person-modal-death-row');
    if (row) row.style.display = (val === 'deceased') ? 'grid' : 'none';
}


function _surnameOf(person) {
    if (!person) return '';
    if (person.name_surname) return person.name_surname;
    const m = (person.name || '').match(/\/([^/]*)\//);
    if (m) return m[1].trim();
    const parts = (person.name || '').trim().split(/\s+/);
    return parts.length > 1 ? parts[parts.length - 1] : '';
}


function _inferSurname(xref, relType, otherSelEl) {
    if (relType === 'sibling_of') return _surnameOf(PEOPLE[xref]);
    if (relType === 'child_of') {
        const person = PEOPLE[xref] || {};
        if (person.sex === 'M') return _surnameOf(person);
        const otherId = otherSelEl && otherSelEl.value !== '__none__' ? otherSelEl.value : null;
        return otherId ? _surnameOf(PEOPLE[otherId]) : '';
    }
    return '';
}

// ── changeParent (pencil + X next to a parent row) ────────────────────────


let _changeParentChildXref = null,
    _changeParentCurrentXref = null,
    _changeParentNewXref = null;


function openChangeParentModal(childXref, currentParentXref) {
    _changeParentChildXref = childXref;
    _changeParentCurrentXref = currentParentXref;
    _changeParentNewXref = null;

    const overlayEl = document.getElementById('change-parent-modal-overlay');
    const titleEl = document.getElementById('change-parent-modal-title');
    const searchEl = document.getElementById('change-parent-modal-search');
    const resultsEl = document.getElementById('change-parent-modal-results');

    const curName = (PEOPLE[currentParentXref] && PEOPLE[currentParentXref].name) || currentParentXref;
    if (titleEl) titleEl.textContent = 'Change parent: ' + curName;
    if (searchEl) searchEl.value = '';
    if (resultsEl) resultsEl.innerHTML = '';
    if (overlayEl) overlayEl.classList.add('open');
    if (searchEl) setTimeout(() => searchEl.focus && searchEl.focus(), 50);
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

function _selectAddPersonFromTree(xref, name) {
    _addPersonFromTreeXref = xref;
    const inp = document.getElementById('add-person-tree-search');
    const res = document.getElementById('add-person-tree-results');
    if (inp) inp.value = name;
    if (res) res.innerHTML = '';
}

document.addEventListener('click', e => {
    const cpItem = e.target.closest('.change-parent-result-item');
    if (cpItem) { _selectChangeParent(cpItem.dataset.xref, cpItem.dataset.name); return; }
    const apItem = e.target.closest('.add-person-tree-result-item');
    if (apItem) _selectAddPersonFromTree(apItem.dataset.xref, apItem.dataset.name);
});

document.addEventListener('input', e => {
    if (e.target.id === 'change-parent-modal-search') {
        _changeParentNewXref = null;
        _renderChangeParentResults(e.target.value);
    }
    if (e.target.id === 'add-person-tree-search') {
        _addPersonFromTreeXref = null;
        const results = _renderAddPersonTreeResults(e.target.value);
        const container = document.getElementById('add-person-tree-results');
        if (container) {
            container.innerHTML = results.map(r =>
                `<div class="add-person-tree-result-item" data-xref="${escHtml(r.id)}" data-name="${escHtml(r.name)}">${escHtml(r.label)}</div>`
            ).join('');
        }
    }
});


async function submitChangeParentModal() {
    const childXref = _changeParentChildXref;
    const currentXref = _changeParentCurrentXref;
    const newXref = _changeParentNewXref; // may be null when user cleared / never selected
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                xref: childXref,
                current_parent_xref: currentXref,
                new_parent_xref: newXref,
                current_person: window._currentPerson || null,
            }),
        });
        const data = await resp.json();
        if (data.ok) {
            if (data.people)
                for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
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


function _relaForSex(sex) {
    return sex === 'M' ? 'Godfather' : sex === 'F' ? 'Godmother' : 'Godparent';
}


async function _submitGodparentFromAddPersonModal(mode, childXref) {
    if (!childXref) { alert('Missing relationship context.'); return; }

    let opts;
    if (mode === 'existing') {
        if (!_addPersonFromTreeXref) {
            alert('Please select a person from the search results.');
            return;
        }
        const pickedSex = (typeof PEOPLE !== 'undefined' && PEOPLE[_addPersonFromTreeXref]?.sex) || 'U';
        opts = { godparent_xref: _addPersonFromTreeXref, rela: _relaForSex(pickedSex) };
    } else {
        const given      = (document.getElementById('add-person-modal-given').value       || '').trim();
        const surn       = (document.getElementById('add-person-modal-surname').value     || '').trim();
        const suffix     = (document.getElementById('add-person-modal-suffix').value      || '').trim();
        const sex        = document.getElementById('add-person-modal-sex').value || 'U';
        const birthDate  = (document.getElementById('add-person-modal-birth-date').value  || '').trim();
        const birthPlace = (document.getElementById('add-person-modal-birth-place').value || '').trim();
        const deathDate  = (document.getElementById('add-person-modal-death-date').value  || '').trim();
        const deathPlace = (document.getElementById('add-person-modal-death-place').value || '').trim();
        let status = '';
        for (const r of document.getElementsByName('add-person-modal-status')) {
            if (r.checked) { status = r.value; break; }
        }
        if (!given && !surn) { alert('Given name or surname is required.'); return; }
        opts = {
            new_person: {
                given, surn, suffix, sex,
                birth_date: birthDate, birth_place: birthPlace,
                status, death_date: deathDate, death_place: deathPlace,
            },
            rela: _relaForSex(sex),
        };
    }

    try {
        const resp = await apiAddGodparent(childXref, opts);
        if (resp && resp.people)
            for (const [k, v] of Object.entries(resp.people)) PEOPLE[k] = v;
        closeAddPersonModal();
        if (typeof renderPanel !== 'undefined') renderPanel();
    } catch (e) {
        alert('Save failed: ' + e);
    }
}


async function submitAddPersonModal() {
    let mode = 'new';
    for (const r of document.getElementsByName('add-person-mode')) {
        if (r.checked) { mode = r.value; break; }
    }

    const relXref = _addPersonRelXref;
    const relType = _addPersonRelType;

    if (relType === 'godparent_of') {
        await _submitGodparentFromAddPersonModal(mode, relXref);
        return;
    }

    if (mode === 'existing') {
        if (!_addPersonFromTreeXref) {
            alert('Please select a person from the search results.');
            return;
        }
        if (!relXref || !relType) { alert('Missing relationship context.'); return; }
        const body = {
            existing_xref: _addPersonFromTreeXref,
            rel_type: relType,
            rel_xref: relXref,
            current_person: window._currentPerson || null,
        };
        if (relType === 'child_of') {
            const otherSelEl = document.getElementById('add-person-modal-other-parent');
            const v = otherSelEl ? otherSelEl.value : '';
            body.other_parent_xref = (v === '__none__') ? '' : v;
        }
        try {
            const resp = await fetch('/api/link_person', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json();
            if (data.ok) {
                if (data.people)
                    for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
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
        return;
    }

    // mode === 'new': original path below, unchanged
    const given      = (document.getElementById('add-person-modal-given').value       || '').trim();
    const surn       = (document.getElementById('add-person-modal-surname').value     || '').trim();
    const suffix     = (document.getElementById('add-person-modal-suffix').value      || '').trim();
    const sex        = document.getElementById('add-person-modal-sex').value || 'U';
    const birthDate  = (document.getElementById('add-person-modal-birth-date').value  || '').trim();
    const birthPlace = (document.getElementById('add-person-modal-birth-place').value || '').trim();
    const deathDate  = (document.getElementById('add-person-modal-death-date').value  || '').trim();
    const deathPlace = (document.getElementById('add-person-modal-death-place').value || '').trim();
    let status = '';
    for (const r of document.getElementsByName('add-person-modal-status')) {
        if (r.checked) { status = r.value; break; }
    }

    if (!given && !surn) { alert('Given name or surname is required.'); return; }
    if (!relXref || !relType) { alert('Missing relationship context.'); return; }

    const body = {
        given,
        surn,
        suffix,
        sex,
        birth_date: birthDate,
        birth_place: birthPlace,
        status,
        death_date: deathDate,
        death_place: deathPlace,
        rel_type: relType,
        rel_xref: relXref,
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.ok) {
            if (data.people)
                for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
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


function _famsForPerson(xref) {
    if (typeof FAMILIES === 'undefined' || !FAMILIES) return [];
    const out = [];
    for (const f in FAMILIES) {
        const fam = FAMILIES[f];
        if (fam && (fam.husb === xref || fam.wife === xref)) out.push(f);
    }
    return out;
}


function _buildSpouseMenuRows(xref, visibleSpouseFams, focusXref) {
    const fams = _famsForPerson(xref);
    const visible = visibleSpouseFams || new Set();
    const anyVisible = fams.some(f => visible.has(f));
    let effectiveChecked;
    if (anyVisible) {
        effectiveChecked = new Set(fams.filter(f => visible.has(f)));
    } else if (typeof primaryFamFor === 'function') {
        const p = primaryFamFor(xref, focusXref);
        effectiveChecked = p ? new Set([p]) : new Set();
    } else {
        effectiveChecked = new Set(fams.slice(0, 1));
    }
    return fams.filter(f => {
        const fam = FAMILIES[f];
        const other = fam.husb === xref ? fam.wife : fam.husb;
        return !!other;
    }).map(f => {
        const fam = FAMILIES[f];
        const other = fam.husb === xref ? fam.wife : fam.husb;
        const otherName = (PEOPLE[other] && PEOPLE[other].name) || other;
        const year = fam.marr_year ? ` (${fam.marr_year})` : '';
        const checked = effectiveChecked.has(f) ? ' checked' : '';
        const fQ = escHtml(f);
        return (
            `<label class="spouse-menu-row" data-fam="${fQ}">` +
            `<input type="checkbox"${checked} onchange="toggleSpouseMenuFam('${fQ}')">` +
            `<span>${escHtml(otherName)}${escHtml(year)}</span>` +
            `</label>`
        );
    }).join('');
}


let _spouseMenuXref = null;


function openSpouseMenuModal(xref) {
    _spouseMenuXref = xref;
    const overlay = document.getElementById('spouse-menu-modal-overlay');
    const list = document.getElementById('spouse-menu-modal-list');
    const title = document.getElementById('spouse-menu-modal-title');
    const name = (PEOPLE && PEOPLE[xref] && PEOPLE[xref].name) || xref;
    if (title) title.textContent = 'Spouses — ' + name;
    const state = (typeof getState === 'function') ? getState() : {};
    const visible = state.visibleSpouseFams || new Set();
    if (list) list.innerHTML = _buildSpouseMenuRows(xref, visible, state.focusXref);
    if (overlay) overlay.classList.add('open');
}


function closeSpouseMenuModal() {
    _spouseMenuXref = null;
    const overlay = document.getElementById('spouse-menu-modal-overlay');
    if (overlay) overlay.classList.remove('open');
}


function toggleSpouseMenuFam(famXref) {
    const state = (typeof getState === 'function') ? getState() : {};
    const cur = state.visibleSpouseFams || new Set();
    const next = new Set(cur);
    // If none of the opened person's FAMs are in the set yet, the primary was
    // implicitly visible. When enabling any FAM, seed with the primary too so
    // the currently-shown spouse stays visible.
    const xref = _spouseMenuXref;
    if (xref && typeof FAMILIES !== 'undefined' && FAMILIES) {
        const personFams = _famsForPerson(xref);
        const anyPersonFamInSet = personFams.some(f => cur.has(f));
        if (!anyPersonFamInSet && !cur.has(famXref) && typeof primaryFamFor === 'function') {
            const primary = primaryFamFor(xref, state.focusXref);
            if (primary && primary !== famXref) next.add(primary);
        }
    }
    if (next.has(famXref)) next.delete(famXref);
    else next.add(famXref);
    setState({ visibleSpouseFams: next });
    // Re-render the modal list so checkboxes always reflect the true state.
    // Without this, the DOM diverges from visibleSpouseFams: e.g. the primary
    // FAM is shown as checked initially even when visibleSpouseFams is empty,
    // so a subsequent click on that checkbox removes it from the set instead of
    // keeping both FAMs selected.
    if (xref) {
        const list = document.getElementById('spouse-menu-modal-list');
        const newState = (typeof getState === 'function') ? getState() : {};
        if (list) list.innerHTML = _buildSpouseMenuRows(xref, newState.visibleSpouseFams, newState.focusXref);
    }
}

// ── Delete person ─────────────────────────────────────────────────────────────


function deletePerson(xref) {
    const person = PEOPLE[xref];
    const name = person ? (person.name || xref) : xref;
    const overlay = document.getElementById('confirm-delete-overlay');
    const body = document.getElementById('confirm-delete-body');
    const cancelBtn = document.getElementById('confirm-delete-cancel');
    const okBtn = document.getElementById('confirm-delete-ok');
    if (!overlay) { return; }
    body.textContent = `Delete "${name}" and all references to them from the GEDCOM? A backup will be saved to .ged.bak.`;
    overlay.classList.add('open');

    const cleanup = () => { overlay.classList.remove('open'); cancelBtn.onclick = null; okBtn.onclick = null; };
    cancelBtn.onclick = cleanup;
    okBtn.onclick = async () => {
        cleanup();
        try {
            const data = await apiDeletePerson(xref);
            if (!data.ok) {
                alert('Delete failed: ' + (data.error || 'unknown error'));
                return;
            }
            const dest = data.navigate_to
                ? `/viz.html?person=${encodeURIComponent(data.navigate_to)}`
                : '/viz.html';
            window.location.href = dest;
        } catch (e) {
            alert('Delete failed: ' + e.message);
        }
    };
}

// ---------------------------------------------------------------------------
// Exports (for Vitest unit tests via CommonJS require)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Exports (for Vitest unit tests via CommonJS require)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        showEditNameModal,
        showAddNoteModal,
        deleteGodparent,
        editName,
        deleteNote,
        submitNoteEdit,
        editNote,
        editEventNote,
        deleteFact,
        openSpouseMenuModal,
        closeSpouseMenuModal,
        toggleSpouseMenuFam,
        _buildSpouseMenuRows,
        deletePerson,
        openAddPersonModal,
        closeAddPersonModal,
        submitAddPersonModal,
        _selectAddPersonFromTree,
        _onAddPersonModeChange,
        _renderAddPersonTreeResults,
        _surnameOf,
        _inferSurname,
    };
}
