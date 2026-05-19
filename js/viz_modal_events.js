// Event edit/add modal: tag/type/place/spouse-picker form behavior,
// and FAM event helpers (marriage / divorce / annulment add + delete).

let _eventModalPasteOnSave = false;

const _INLINE_TYPE_TAGS = new Set(['OCCU', 'TITL', 'NATI', 'RELI', 'EDUC']);
// Tags that use a 2 TYPE sub-field for description

const _TYPE_TAGS = new Set(['EVEN', 'FACT', 'OCCU', 'TITL', 'EDUC', 'NATI', 'RELI']);


let _eventModalXref = null,
    _eventModalIdx = null,
    _eventModalTag = null,
    _eventModalFamXref = null,
    _eventModalMARRIdx = null,
    _eventModalAddTag = null;

// Fact presets — each key is the pseudo-tag used in the UI (option value).
// baseTag:     the real GEDCOM tag submitted to the server
// type:        value for 2 TYPE sub-tag (null for tags that don't use TYPE)
// showInline:  true → show the inline value field (for DSCR, NCHI)
// inlineLabel: label for the inline field when showInline is true

const _FACT_PRESETS = {
    'FACT:Languages': { label: 'Languages', baseTag: 'FACT', type: 'Languages', showInline: false },
    'FACT:Literacy': { label: 'Literacy', baseTag: 'FACT', type: 'Literacy', showInline: false },
    'FACT:Politics': { label: 'Politics', baseTag: 'FACT', type: 'Politics', showInline: false },
    'FACT:Medical condition': { label: 'Medical condition', baseTag: 'FACT', type: 'Medical condition', showInline: false },
    'DSCR': { label: 'Physical Description', baseTag: 'DSCR', type: null, showInline: true, inlineLabel: 'Description' },
    'NCHI': { label: 'Children (count)', baseTag: 'NCHI', type: null, showInline: true, inlineLabel: 'Count' },
};


function _updateEventModalFields(tag) {
    const inlineRow = document.getElementById('event-modal-inline-row');
    const inlineLbl = document.getElementById('event-modal-inline-label');
    const typeRow = document.getElementById('event-modal-type-row');
    const ageRow = document.getElementById('event-modal-age-row');
    const causeRow = document.getElementById('event-modal-cause-row');
    const placeRow = document.getElementById('event-modal-place-row');
    const addrRow = document.getElementById('event-modal-addr-row');

    const preset = _FACT_PRESETS[tag];
    if (preset) {
        // Preset fact: hide cause, place, address — only date and note are relevant.
        if (ageRow) ageRow.style.display = 'none';
        causeRow.style.display = 'none';
        if (placeRow) placeRow.style.display = 'none';
        if (addrRow) addrRow.style.display = 'none';
        if (preset.showInline) {
            // DSCR / NCHI: show inline field (value goes on the tag line), hide TYPE row
            inlineRow.style.display = '';
            inlineLbl.textContent = preset.inlineLabel;
            typeRow.style.display = 'none';
        } else {
            // FACT: the preset label is already in the modal title, so hide both the
            // inline row and the TYPE row. The server still receives TYPE because
            // submitEventModal falls back to preset.type when the type row is hidden.
            inlineRow.style.display = 'none';
            typeRow.style.display = 'none';
            const typeInp = document.getElementById('event-modal-type');
            if (typeInp) { typeInp.value = preset.type;
                typeInp.readOnly = true; }
        }
        _updateSpouseRow(tag);
        return;
    }

    // Clear any read-only state (and pre-filled value) set by a previous preset selection
    const typeInp = document.getElementById('event-modal-type');
    if (typeInp) { typeInp.readOnly = false;
        typeInp.value = ''; }

    if (_INLINE_TYPE_TAGS.has(tag)) {
        inlineRow.style.display = '';
        const labelMap = { OCCU: 'Occupation', TITL: 'Title', NATI: 'Nationality', RELI: 'Religion', EDUC: 'Education' };
        inlineLbl.textContent = labelMap[tag] || 'Value';
    } else {
        inlineRow.style.display = 'none';
    }
    // For inline-type tags (EDUC, OCCU, etc.) the inline value IS the type —
    // showing a separate TYPE field would duplicate it and cause confusion.
    typeRow.style.display = (_TYPE_TAGS.has(tag) && !_INLINE_TYPE_TAGS.has(tag)) ? '' : 'none';
    if (ageRow) ageRow.style.display = (tag === 'DEAT') ? '' : 'none';
    causeRow.style.display = (tag === 'DEAT') ? '' : 'none';
    const dateUnknownRow = document.getElementById('event-modal-date-unknown-row');
    if (dateUnknownRow) dateUnknownRow.style.display = (tag === 'DEAT') ? '' : 'none';
    const hidePlaceAddr = (tag === 'NATI');
    if (placeRow) placeRow.style.display = hidePlaceAddr ? 'none' : '';
    if (addrRow) addrRow.style.display = hidePlaceAddr ? 'none' : '';
    _updateSpouseRow(tag);
}


function _onDateUnknownChange(checked) {
    const dateInp = document.getElementById('event-modal-date');
    if (!dateInp) return;
    if (checked) {
        dateInp.value = '';
        dateInp.disabled = true;
    } else {
        dateInp.disabled = false;
    }
}


function _toggleEventModalSourceSection() {
    const sourRow = document.getElementById('event-modal-source-row');
    const pageRow = document.getElementById('event-modal-page-row');
    const btn = document.getElementById('event-modal-source-toggle');
    const isOpen = sourRow.style.display !== 'none';
    sourRow.style.display = isOpen ? 'none' : '';
    pageRow.style.display = isOpen ? 'none' : '';
    btn.textContent = isOpen ? '+ Add source citation (optional)' : '− Remove source citation';
    if (!isOpen && typeof SOURCES !== 'undefined') {
        _populateEventModalSources();
    }
}


function _refreshEventModalPasteBtn() {
    const row = document.getElementById('event-modal-paste-citation-row');
    const btn = document.getElementById('event-modal-paste-citation-btn');
    if (!btn || !row) return;
    const c = getCopiedCitation();
    if (!c) {
        row.style.display = 'none';
        return;
    }
    row.style.display = '';
    const label = (c.label || '').slice(0, 50) || 'citation';
    if (_eventModalPasteOnSave) {
        btn.innerHTML = _pasteIconSvg + `Paste: “${label}” ✓`;
        btn.classList.add('armed');
    } else {
        btn.innerHTML = _pasteIconSvg + `Paste: “${label}”`;
        btn.classList.remove('armed');
    }
}


function _toggleEventModalPasteBtn() {
    _eventModalPasteOnSave = !_eventModalPasteOnSave;
    // Collapse the manual source section when arming — they're mutually exclusive.
    if (_eventModalPasteOnSave) {
        document.getElementById('event-modal-source-row').style.display = 'none';
        document.getElementById('event-modal-page-row').style.display = 'none';
        document.getElementById('event-modal-source-toggle').textContent = '+ Add source citation (optional)';
    }
    _refreshEventModalPasteBtn();
}


function _populateEventModalSources() {
    const sourceEl = document.getElementById('event-modal-source');
    if (!sourceEl) return;
    sourceEl.innerHTML = '<option value="">— select source —</option>';
    const entries = Object.entries(SOURCES).map(([sxref, src]) => ({
        sxref,
        label: (src && src.titl) || sxref,
    }));
    entries.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }));
    for (const { sxref, label } of entries) {
        const opt = document.createElement('option');
        opt.value = sxref;
        opt.textContent = label;
        sourceEl.appendChild(opt);
    }
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


function _onPlaceInput(val, inputId) {
    inputId = inputId || 'event-modal-place';
    const q = val.trim();
    const el = document.getElementById(inputId + '-results');
    if (!el) return;
    if (!q) { el.innerHTML = ''; return; }
    const ql = q.toLowerCase();
    const matches = (typeof ALL_PLACES !== 'undefined' ? ALL_PLACES : [])
        .filter(p => p.toLowerCase().startsWith(ql))
        .slice(0, 8);
    if (!matches.length) { el.innerHTML = ''; return; }
    const inputIdQ = JSON.stringify(inputId).replace(/"/g, '&quot;');
    el.innerHTML = matches.map(p =>
        `<div class="place-result-item" onmousedown="event.preventDefault();_selectPlace(${JSON.stringify(p).replace(/"/g, '&quot;')},${inputIdQ})">${escHtml(p)}</div>`
    ).join('');
}


function _selectPlace(place, inputId) {
    inputId = inputId || 'event-modal-place';
    const inp = document.getElementById(inputId);
    if (inp) inp.value = place;
    _clearPlaceResults(inputId);
    if (inputId === 'event-modal-place') _updateAddrSuggestions(place);
}


function _clearPlaceResults(inputId) {
    inputId = inputId || 'event-modal-place';
    const el = document.getElementById(inputId + '-results');
    if (el) el.innerHTML = '';
}


const _placeBlurTimers = {};


function _schedulePlaceResultsClear(inputId) {
    inputId = inputId || 'event-modal-place';
    clearTimeout(_placeBlurTimers[inputId]);
    _placeBlurTimers[inputId] = setTimeout(() => _clearPlaceResults(inputId), 150);
}


function editEvent(xref, eventIdx, tag, famXref, marrIdx) {
    _eventModalXref = xref;
    _eventModalIdx = eventIdx;
    _eventModalTag = tag;
    _eventModalFamXref = famXref || null;
    _eventModalMARRIdx = (marrIdx !== undefined && marrIdx !== null) ? marrIdx : null;
    document.getElementById('event-modal-save-btn').textContent = 'Save';
    document.getElementById('event-modal-tag-row').style.display = 'none';
    const events = (PEOPLE[xref] && PEOPLE[xref].events) || [];
    // For FAM events (MARR), match by fam_xref + marr_idx; otherwise match by tag + event_idx
    const evt = famXref ?
        (events.find(e => e.fam_xref === famXref && e.tag === tag &&
            (marrIdx == null || (e.marr_idx ?? e.div_idx) === marrIdx)) || {}) :
        (events.find(e => e.tag === tag && e.event_idx === eventIdx) || {});
    document.getElementById('event-modal-title').textContent = 'Edit ' + _evtLabel(tag, evt.type) + ' \u2014 ' + _personName(xref);
    const placeVal = evt.place || '';
    document.getElementById('event-modal-inline').value = evt.inline_val || '';
    document.getElementById('event-modal-date').value = evt.date || '';
    document.getElementById('event-modal-place').value = placeVal;
    document.getElementById('event-modal-age').value = evt.age || '';
    document.getElementById('event-modal-cause').value = evt.cause || '';
    document.getElementById('event-modal-note').value = evt.note || '';
    document.getElementById('event-modal-addr').value = evt.addr || '';
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
    // Date-unknown checkbox is for adds only — hide it and reset its state when editing.
    // The disabled state of the date input persists across modal opens, so we must
    // explicitly re-enable it here even though the checkbox row is hidden.
    const _duRow = document.getElementById('event-modal-date-unknown-row');
    if (_duRow) _duRow.style.display = 'none';
    const _duCb = document.getElementById('event-modal-date-unknown');
    if (_duCb) _duCb.checked = false;
    const _dateInp = document.getElementById('event-modal-date');
    if (_dateInp) _dateInp.disabled = false;
    const convertRow = document.getElementById('event-modal-convert-row');
    if (convertRow) convertRow.style.display = tag === 'BIRT' ? '' : 'none';
    // Set type AFTER _updateEventModalFields so its reset-from-preset logic doesn't wipe the prefill.
    document.getElementById('event-modal-type').value = evt.type || '';
    document.getElementById('event-modal-overlay').classList.add('open');
    const focusId = _INLINE_TYPE_TAGS.has(tag) ? 'event-modal-inline' : 'event-modal-date';
    setTimeout(() => { const el = document.getElementById(focusId); if (el) el.focus?.(); }, 50);
}


function addEvent(xref, defaultTag = 'RESI', prefillType) {
    _eventModalXref = xref;
    _eventModalIdx = null;
    _eventModalTag = null;
    _eventModalAddTag = defaultTag;
    _eventModalFamXref = null;
    _eventModalSpouseXref = null;
    const _preset = _FACT_PRESETS[defaultTag];
    const _title = _preset ?
        'Add ' + _preset.label + ' \u2014 ' + _personName(xref) :
        'Add Event \u2014 ' + _personName(xref);
    document.getElementById('event-modal-title').textContent = _title;
    document.getElementById('event-modal-save-btn').textContent = 'Add';
    // Preset fact adds (Languages, Literacy, DSCR, NCHI, …) lock the event type —
    // the title already says what you're adding, and the dropdown doesn't carry
    // the preset pseudo-tag as an option anyway.
    document.getElementById('event-modal-tag-row').style.display = _preset ? 'none' : '';
    document.getElementById('event-modal-tag').value = defaultTag;
    document.getElementById('event-modal-inline').value = '';
    document.getElementById('event-modal-type').value = prefillType || '';
    document.getElementById('event-modal-date').value = '';
    document.getElementById('event-modal-date').disabled = false;
    const _duCb = document.getElementById('event-modal-date-unknown');
    if (_duCb) { _duCb.checked = false; }
    document.getElementById('event-modal-place').value = '';
    document.getElementById('event-modal-age').value = '';
    document.getElementById('event-modal-cause').value = '';
    document.getElementById('event-modal-note').value = '';
    document.getElementById('event-modal-addr').value = '';
    document.getElementById('event-modal-source-row').style.display = 'none';
    document.getElementById('event-modal-page-row').style.display = 'none';
    document.getElementById('event-modal-source-toggle').textContent = '+ Add source citation (optional)';
    document.getElementById('event-modal-source').value = '';
    document.getElementById('event-modal-page').value = '';
    const _convertRow = document.getElementById('event-modal-convert-row');
    if (_convertRow) _convertRow.style.display = 'none';
    _eventModalPasteOnSave = false;
    _refreshEventModalPasteBtn();
    const spouseInp = document.getElementById('event-modal-spouse-input');
    const spouseRes = document.getElementById('event-modal-spouse-results');
    if (spouseInp) spouseInp.value = '';
    if (spouseRes) spouseRes.innerHTML = '';
    _updateAddrSuggestions('');
    _updateEventModalFields(defaultTag);
    document.getElementById('event-modal-overlay').classList.add('open');
    const _dfPreset = _FACT_PRESETS[defaultTag];
    const focusId = _dfPreset ?
        (_dfPreset.showInline ? 'event-modal-inline' : 'event-modal-note') :
        'event-modal-tag';
    setTimeout(() => document.getElementById(focusId).focus(), 50);
}


function closeEventModal() {
    document.getElementById('event-modal-overlay').classList.remove('open');
    _eventModalXref = _eventModalIdx = _eventModalTag = _eventModalFamXref = _eventModalMARRIdx = null;
    _eventModalSpouseXref = null;
    _clearPlaceResults();
}


async function submitEventModal() {
    const xref = _eventModalXref;
    const famXref = _eventModalFamXref;
    const isAdd = _eventModalIdx === null && !famXref;
    // For adds, use the stored _eventModalAddTag (which may hold a preset pseudo-tag
    // like 'FACT:Languages' that isn't in the select's <option> list). Fall back to
    // the select value if the user changed the event type via the dropdown.
    const rawTag = isAdd ?
        (_eventModalAddTag || document.getElementById('event-modal-tag').value) :
        _eventModalTag;
    // Resolve preset pseudo-tags to their real GEDCOM tag (e.g. 'FACT:Languages' → 'FACT').
    const preset = _FACT_PRESETS[rawTag];
    const tag = preset ? preset.baseTag : rawTag;
    const typeRow = document.getElementById('event-modal-type-row');
    const ageRow = document.getElementById('event-modal-age-row');
    const causeRow = document.getElementById('event-modal-cause-row');
    const _dateUnknownCb = document.getElementById('event-modal-date-unknown');
    const _dateUnknown = isAdd && tag === 'DEAT' && _dateUnknownCb && _dateUnknownCb.checked;
    // Validate: adding a DEAT without a date requires the "Date unknown" checkbox.
    if (isAdd && tag === 'DEAT' && !_dateUnknown) {
        const _dateVal = document.getElementById('event-modal-date').value.trim();
        if (!_dateVal) {
            alert('Please enter a date, or check “Date unknown” to record death without a date.');
            return;
        }
    }
    const fields = {
        inline_val: document.getElementById('event-modal-inline').value.trim(),
        DATE: _dateUnknown ? 'Y' : document.getElementById('event-modal-date').value.trim(),
        PLAC: document.getElementById('event-modal-place').value.trim(),
        NOTE: document.getElementById('event-modal-note').value.trim(),
        ADDR: document.getElementById('event-modal-addr').value.trim(),
    };
    // Include TYPE when the row is visible. For preset FACT adds (Languages,
    // Literacy, …) the row is hidden but the server still needs the TYPE value,
    // so we pull it from the preset itself.
    if (typeRow && typeRow.style.display !== 'none') {
        fields.TYPE = document.getElementById('event-modal-type').value.trim();
    } else if (isAdd && preset && !preset.showInline && preset.type) {
        fields.TYPE = preset.type;
    }
    // Only include AGE/CAUS when their rows are visible (DEAT events)
    if (ageRow && ageRow.style.display !== 'none') {
        const _age = document.getElementById('event-modal-age').value.trim();
        fields.AGE = /^\d+$/.test(_age) ? _age + 'y' : _age;
    }
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
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    xref,
                    spouse_xref: _eventModalSpouseXref,
                    tag,
                    fields,
                    current_person: window._currentPerson || null,
                }),
            });
            const data = await resp.json();
            if (data.ok) {
                if (data.people)
                    for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
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
        body = {
            xref,
            tag,
            fam_xref: famXref,
            marr_occurrence: _eventModalMARRIdx ?? 0,
            updates: fields,
            current_person: window._currentPerson || null
        };
    } else {
        body = { xref, tag, event_idx: _eventModalIdx, updates: fields, current_person: window._currentPerson || null };
    }
    closeEventModal();
    try {
        const resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (data.ok) {
            // Update all returned people (may include both spouses for marriage edits)
            if (data.people) {
                for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
            }
            // If the user chose a source or pasted a citation, attach it to the newly created event.
            if (isAdd && data.people && data.people[xref]) {
                const events = (data.people[xref].events || []).filter(e => e.tag === tag);
                if (events.length > 0) {
                    const newEvent = events.reduce((max, e) =>
                        (e.event_idx > max.event_idx ? e : max), events[0]);
                    const factKey = `${tag}:${newEvent.event_idx}`;
                    let citArgs = null;
                    if (_eventModalPasteOnSave && getCopiedCitation()) {
                        const c = getCopiedCitation();
                        citArgs = [xref, c.sourceXref, factKey, c.page || '', c.text || '', c.note || '', c.url || '', c.quay || '', c.date || ''];
                    } else {
                        const sourXref = document.getElementById('event-modal-source').value;
                        const page = document.getElementById('event-modal-page').value.trim();
                        if (sourXref) {
                            citArgs = [xref, sourXref, factKey, page, '', '', '', '', ''];
                        }
                    }
                    if (citArgs) {
                        try {
                            const citResp = await apiAddCitation(...citArgs);
                            if (citResp && citResp.people) {
                                for (const [k, v] of Object.entries(citResp.people)) PEOPLE[k] = v;
                            }
                        } catch (_e) {
                            // Citation failed silently — event was still saved.
                        }
                    }
                }
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

const _FAM_EVENT_TAGS = new Set(['MARR', 'DIV', 'ANUL']);

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


async function deleteMarriage(xref, famXref, marrIdx, tag = 'MARR') {
    const label = tag === 'DIV' ? 'divorce' : 'marriage';
    if (!confirm(`Delete this ${label} record? The GEDCOM file will be updated immediately (a backup will be saved).`)) return;
    try {
        const resp = await fetch('/api/delete_marriage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                xref,
                fam_xref: famXref,
                marr_occurrence: marrIdx,
                tag,
                current_person: xref,
            }),
        });
        const data = await resp.json();
        if (data.ok) {
            if (data.people)
                for (const [k, v] of Object.entries(data.people)) PEOPLE[k] = v;
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

// ---------------------------------------------------------------------------
// Exports (for Vitest unit tests via CommonJS require)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        _filterSpouseResults,
        _isFamEventTag,
        _buildSpouseResultsHtml,
        _FACT_PRESETS,
        addEvent,
        editEvent,
        _onPlaceInput,
        _selectPlace,
        _clearPlaceResults,
        _updateEventModalFields,
        _onDateUnknownChange,
    };
}
