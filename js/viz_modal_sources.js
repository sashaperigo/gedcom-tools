// Sources viewer modal and add/edit citation + source modals,
// including the "apply to events" state used by person-level sources.


let _sourcesModalXref = null;

let _sourcesModalEventIdx = null;

let _sourcesModalNoteIdx = null;

let _sourcesModalIndiLevel = false;


function openSourcesModal(xref, eventIdx) {
    _sourcesModalXref = xref;
    _sourcesModalEventIdx = eventIdx;
    _sourcesModalNoteIdx = null;
    _sourcesModalIndiLevel = false;
    _refreshSourcesModalContent();
    document.getElementById('sources-modal-overlay').classList.add('open');
}


function openNoteSourcesModal(xref, noteIdx) {
    _sourcesModalXref = xref;
    _sourcesModalEventIdx = null;
    _sourcesModalNoteIdx = noteIdx;
    _sourcesModalIndiLevel = false;
    _refreshSourcesModalContent();
    document.getElementById('sources-modal-overlay').classList.add('open');
}


function openIndiSourcesModal(xref) {
    _sourcesModalXref = xref;
    _sourcesModalEventIdx = null;
    _sourcesModalNoteIdx = null;
    _sourcesModalIndiLevel = true;
    _refreshSourcesModalContent();
    document.getElementById('sources-modal-overlay').classList.add('open');
}


function closeSourcesModal() {
    document.getElementById('sources-modal-overlay').classList.remove('open');
    _sourcesModalXref = null;
    _sourcesModalEventIdx = null;
    _sourcesModalNoteIdx = null;
    _sourcesModalIndiLevel = false;
}


function _setSourcesModalHeader(eventLabel, title) {
    const labelEl = document.getElementById('sources-modal-event-label');
    const titleEl = document.getElementById('sources-modal-title');
    if (labelEl) labelEl.textContent = eventLabel || '';
    if (titleEl) titleEl.textContent = title || 'Sources';
}


function _refreshSourcesModalContent() {
    const xref = _sourcesModalXref;
    const eventIdx = _sourcesModalEventIdx;
    if (xref == null) return;

    const _topListEl = document.getElementById('sources-modal-list');

    if (_sourcesModalIndiLevel) {
        const person = (typeof PEOPLE !== 'undefined') && PEOPLE[xref];
        const citations = (person && person.sources) || [];
        const sources = (typeof SOURCES !== 'undefined') ? SOURCES : {};
        const name = (person && (person.name || person.display_name)) || '';
        _setSourcesModalHeader('Person sources', name || 'Person Sources');
        if (_topListEl) _topListEl.innerHTML = _buildSourcesModalContent(citations, sources, xref, { tag: 'SOUR' });
        return;
    }

    if (_sourcesModalNoteIdx == null && eventIdx == null) return;

    if (_sourcesModalNoteIdx != null) {
        const noteIdx = _sourcesModalNoteIdx;
        const note = (typeof PEOPLE !== 'undefined') && PEOPLE[xref] && PEOPLE[xref].notes && PEOPLE[xref].notes[noteIdx];
        const rawText = (note && note.text) || '';
        const label = rawText.length > 60 ? rawText.slice(0, 60) + '\u2026' : rawText;
        const noteEvt = {
            tag: (note && note.shared) ? 'SNOTE' : 'NOTE',
            note_xref: note && note.note_xref,
            note_idx: note && note.note_idx,
            citations: (note && note.citations) || [],
        };
        const sources = (typeof SOURCES !== 'undefined') ? SOURCES : {};
        _setSourcesModalHeader(noteEvt.tag === 'SNOTE' ? 'Shared note' : 'Note', label || 'Note Sources');
        if (_topListEl) _topListEl.innerHTML = _buildSourcesModalContent(noteEvt.citations, sources, xref, noteEvt);
        return;
    }
    const evt = PEOPLE[xref] && PEOPLE[xref].events && PEOPLE[xref].events[eventIdx];
    const citations = (evt && evt.citations) || [];
    const sources = (typeof SOURCES !== 'undefined') ? SOURCES : {};

    // Split header: small uppercase "Arrival · 1922" + larger prose "Arrived in Southampton".
    let eventLabel = '';
    let title = 'Sources';
    if (evt) {
        const labelMap = (typeof EVENT_LABELS !== 'undefined') ? EVENT_LABELS : {};
        const tag = labelMap[evt.tag] || evt.tag;
        const type = evt.type ? ` (${evt.type})` : '';
        const year = evt.date ? (' \u00b7 ' + (evt.date.match(/\b\d{4}\b/) || [''])[0]) : '';
        eventLabel = tag + type + year;
        if (typeof buildProse === 'function') {
            try {
                const p = buildProse(evt);
                title = (p && p.prose) ? p.prose : eventLabel;
            } catch (_e) { title = eventLabel; }
        } else {
            title = eventLabel;
        }
    }
    _setSourcesModalHeader(eventLabel, title);
    if (_topListEl) _topListEl.innerHTML = _buildSourcesModalContent(citations, sources, xref, evt);
}


const CITATION_TEXT_COLLAPSE_THRESHOLD = 280;

function _renderCitationText(text) {
    const escaped = escHtml(text);
    if (text.length <= CITATION_TEXT_COLLAPSE_THRESHOLD) {
        return `<span class="citation-field-value citation-field-value--quoted">“${escaped}”</span>`;
    }
    return (
        `<span class="citation-field-value citation-field-value--quoted citation-field-value--collapsible is-collapsed">` +
        `<span class="citation-text-body">“${escaped}”</span>` +
        `<button type="button" class="citation-text-toggle" onclick="toggleCitationText(this)">Show more</button>` +
        `</span>`
    );
}

function toggleCitationText(btn) {
    const wrap = btn.closest('.citation-field-value--collapsible');
    if (!wrap) return;
    const collapsed = wrap.classList.toggle('is-collapsed');
    btn.textContent = collapsed ? 'Show more' : 'Show less';
}

function _buildSourcesModalContent(citations, sources, xref, evt) {
    const tag = (evt && evt.tag) || '';
    // FAM-originated events (MARR/DIV) carry fam_xref + marr_idx/div_idx.
    // Citations on those events live on the FAM record, so we must address
    // them via the FAM xref — not the INDI xref of the currently-viewed person.
    const isFamEvt = !!(evt && evt.fam_xref);
    const targetXref = isFamEvt ? evt.fam_xref : xref;
    let eventOcc;
    if (isFamEvt) {
        eventOcc = (tag === 'DIV') ? (evt.div_idx != null ? evt.div_idx : 0) :
            (tag === 'ANUL') ? (evt.anul_idx != null ? evt.anul_idx : 0) :
            (evt.marr_idx != null ? evt.marr_idx : 0);
    } else {
        eventOcc = (evt && evt.event_idx != null) ? evt.event_idx : 0;
    }
    const isIndiSour = (tag === 'SOUR');
    const xrefQ = JSON.stringify(String(targetXref || '')).replace(/"/g, '&quot;');
    let factKey;
    if (tag === 'NOTE') factKey = `NOTE:${evt && evt.note_idx}`;
    else if (tag === 'SNOTE') factKey = `SNOTE:${evt && evt.note_xref}`;
    else if (isIndiSour) factKey = 'null';
    else factKey = tag ? `${tag}:${eventOcc}` : '';
    const factKeyQ = JSON.stringify(factKey).replace(/"/g, '&quot;');

    const bookIconSvg =
        `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ` +
        `stroke-linecap="round" stroke-linejoin="round">` +
        `<path d="M2 3.5A1.5 1.5 0 013.5 2h9A1.5 1.5 0 0114 3.5v9a1.5 1.5 0 01-1.5 1.5h-9A1.5 1.5 0 012 12.5v-9z"/>` +
        `<path d="M5 2v12M5 6h4"/>` +
        `</svg>`;
    const plusIconSvg =
        `<svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" ` +
        `stroke-width="2" stroke-linecap="round"><path d="M6 1v10M1 6h10"/></svg>`;
    const pasteIconSvg = _pasteIconSvg;

    let html = '';
    if (!citations || citations.length === 0) {
        html += '<div class="citation-empty">No sources recorded for this fact.</div>';
    } else {
        html += citations.map((c, idx) => {
            const xrefKey = c.sourceXref || c.sour_xref;
            const src = sources[xrefKey] || {};
            const title = src.titl || src.title || xrefKey || 'Unknown source';
            const citUrl = c.url;
            const titleHtml = citUrl ?
                `<a href="${escHtml(citUrl)}" target="_blank" rel="noopener">${escHtml(title)}</a>` :
                escHtml(title);
            const quayLabels = { '3': 'Direct (3)', '2': 'Secondary (2)', '1': 'Questionable (1)', '0': 'Unreliable (0)' };
            const quayDisplay = c.quay ? (quayLabels[String(c.quay)] || String(c.quay)) : '';
            const fieldRows = [
                c.page ? `<div class="citation-field"><span class="citation-field-label">Page</span><span class="citation-field-value">${escHtml(/^p\.?\s*/i.test(c.page) ? c.page : 'p. ' + c.page)}</span></div>` : '',
                c.date ? `<div class="citation-field"><span class="citation-field-label">Date</span><span class="citation-field-value">${escHtml(c.date)}</span></div>` : '',
                c.text ? `<div class="citation-field"><span class="citation-field-label">Text</span>${_renderCitationText(c.text)}</div>` : '',
                c.note ? `<div class="citation-field"><span class="citation-field-label">Note</span><span class="citation-field-value">${escHtml(c.note)}</span></div>` : '',
                quayDisplay ? `<div class="citation-field"><span class="citation-field-label">Qual</span><span class="citation-field-value">${escHtml(quayDisplay)}</span></div>` : '',
            ].filter(Boolean).join('');
            const fieldsHtml = fieldRows ? `<div class="citation-fields">${fieldRows}</div>` : '';
            const citeKey = isIndiSour ? (c.citationKey || `SOUR:${idx}`) :
                (tag === 'NOTE') ? `NOTE:${evt && evt.note_idx}:${idx}` :
                (tag === 'SNOTE') ? `SNOTE:${evt && evt.note_xref}:${idx}` :
                `${tag}:${eventOcc}:${idx}`;
            const citeKeyQ = JSON.stringify(citeKey).replace(/"/g, '&quot;');
            // For FAM events the API must target the FAM xref, but PEOPLE lookup uses the INDI xref.
            const indiXrefQ = JSON.stringify(String(xref || '')).replace(/"/g, '&quot;');
            const apiXrefQ = xrefQ; // targetXref (FAM or INDI)
            const noteEventOcc = (tag === 'NOTE') ? (evt && evt.note_idx) : (evt && evt.note_xref);
            const editOnclick = isIndiSour ?
                `showEditCitationModal(${xrefQ},null,${idx},undefined,0)` :
                (tag === 'NOTE' || tag === 'SNOTE') ?
                `showEditCitationModal(${xrefQ},${JSON.stringify(tag).replace(/"/g,'&quot;')},${idx},undefined,${JSON.stringify(noteEventOcc).replace(/"/g,'&quot;')})` :
                isFamEvt ?
                `showEditCitationModal(${indiXrefQ},${JSON.stringify(tag).replace(/"/g,'&quot;')},${idx},${apiXrefQ},${eventOcc})` :
                `showEditCitationModal(${xrefQ},${JSON.stringify(tag).replace(/"/g,'&quot;')},${idx},undefined,${eventOcc})`;
            const xrefKey2 = c.sourceXref || c.sour_xref || '';
            const pageVal = c.page || '';
            const copyDataAttrs =
                `data-sour-xref="${escHtml(xrefKey2)}" ` +
                `data-page="${escHtml(pageVal)}" ` +
                `data-text="${escHtml(c.text || '')}" ` +
                `data-note="${escHtml(c.note || '')}" ` +
                `data-url="${escHtml(c.url || '')}" ` +
                `data-quay="${escHtml(c.quay || '')}" ` +
                `data-date="${escHtml(c.date || '')}" ` +
                `data-label="${escHtml((src.titl || src.title || xrefKey2) + (pageVal ? ' p. ' + pageVal : ''))}"`;
            return (
                `<div class="citation-card">` +
                `<div class="citation-card-icon">${bookIconSvg}</div>` +
                `<div class="citation-card-body"><div class="citation-title">${titleHtml}</div>${fieldsHtml}</div>` +
                `<div class="citation-card-actions">` +
                `<button type="button" class="citation-action copy" title="Copy citation" ` +
                `${copyDataAttrs} onclick="handleCitationCopy(this)">\u29c9</button>` +
                `<button type="button" class="citation-action" title="Edit this citation" ` +
                `onclick="${editOnclick}">\u270f</button>` +
                `<button type="button" class="citation-action del" title="Remove this citation" ` +
                `onclick="deleteSourceFromModal(${xrefQ},${citeKeyQ})">\u00d7</button>` +
                `</div>` +
                `</div>`
            );
        }).join('');
    }
    const pasteLabel = getCopiedCitation() ?
        escHtml((getCopiedCitation().label || '').slice(0, 60)) :
        '';
    const pasteHidden = getCopiedCitation() ? '' : ' hidden';
    const noBorder = (!citations || citations.length === 0) ? ' no-border' : '';
    html += `<div class="citation-add-row${noBorder}">` +
        `<button type="button" class="citation-add-primary" ` +
        `onclick="showAddCitationModal(${xrefQ},${factKeyQ})">${plusIconSvg}Add source</button>` +
        `<button type="button" class="citation-paste-btn${pasteHidden}" ` +
        `onclick="handleCitationPaste(${xrefQ},${factKeyQ})">` +
        `${pasteIconSvg}Paste: \u201c${pasteLabel}\u201d</button>` +
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


function handleCitationCopy(btn) {
    const xref = btn.dataset.sourXref;
    const page = btn.dataset.page || null;
    const text = btn.dataset.text || '';
    const note = btn.dataset.note || '';
    const url = btn.dataset.url || null;
    const quay = btn.dataset.quay || '';
    const date = btn.dataset.date || '';
    const label = btn.dataset.label || xref;
    copyCitation({ sourceXref: xref, page, text, note, url, quay, date }, label);
    // Flash button to confirm copy, then refresh the modal to show paste button.
    btn.classList.add('copied');
    setTimeout(() => btn.classList.remove('copied'), 700);
    _refreshSourcesModalContent();
}


async function handleCitationPaste(xref, factKey) {
    const c = getCopiedCitation();
    if (!c) return;
    try {
        const resp = await apiAddCitation(
            xref, c.sourceXref, factKey,
            c.page || '', c.text || '', c.note || '', c.url || '',
            c.quay || '', c.date || ''
        );
        if (resp && resp.ok) {
            if (resp.people) {
                for (const [k, v] of Object.entries(resp.people)) PEOPLE[k] = v;
            }
            _refreshSourcesModalContent();
            if (typeof renderPanel === 'function') renderPanel();
        } else {
            alert('Paste failed: ' + ((resp && resp.error) || 'unknown'));
        }
    } catch (e) {
        alert('Paste failed: ' + e);
    }
}

// ---------------------------------------------------------------------------
// Task 14 — New modals
// ---------------------------------------------------------------------------

// ── Helper: _personName (already defined above) ───────────────────────────

// ── showEditNameModal ─────────────────────────────────────────────────────


const _applyToEventsState = { rows: [], mode: null };


function _applyToEventLabel(ev) {
    const tag = ev && ev.tag;
    let label = _evtLabel(tag, ev && ev.type) || tag || '';
    if (ev && ev._name_record) {
        const aliasName = (ev.note || '').trim();
        return aliasName ? `${label} — ${aliasName}` : label;
    }
    if (tag === 'MARR' || tag === 'DIV' || tag === 'ANUL') {
        const fam = (typeof FAMILIES !== 'undefined' && FAMILIES) ? FAMILIES[ev.fam_xref] : null;
        // Best-effort spouse label — fall back silently when data isn't loaded.
        const spouseXref = fam && fam.spouseXrefs && fam.spouseXrefs.find(x => x !== ev.indi_xref);
        const spouse = (typeof PEOPLE !== 'undefined' && PEOPLE && spouseXref) ? PEOPLE[spouseXref] : null;
        if (spouse && spouse.name) label += ' to ' + spouse.name.replace(/\//g, '');
    }
    // For tags whose distinguishing detail is the inline value (NATI: "English",
    // RELI: "Catholic", OCCU: "Dragoman"), surface it so multiple rows of the
    // same tag are distinguishable.
    const inlineDetail = (tag === 'NATI' || tag === 'RELI' || tag === 'OCCU')
        ? ((ev && (ev.inline_val || ev.type)) || '').trim()
        : '';
    if (inlineDetail) label = `${label} — ${inlineDetail}`;
    const date = (ev && ev.date) || '';
    const place = (ev && ev.place) || '';
    const tail = [date, place].filter(Boolean).join(', ');
    return tail ? `${label} — ${tail}` : label;
}


// Two citations are "the same" iff every content field matches. Matching only
// on sourceXref would conflate distinct INDI-level citations to the same
// source — editing one would silently rewire the other's fact-applicability.
function _citationFingerprintsEqual(a, b) {
    if (!a || !b) return false;
    if (a.sourceXref !== b.sourceXref) return false;
    const norm = v => (v == null ? '' : String(v));
    return norm(a.page) === norm(b.page) &&
        norm(a.text) === norm(b.text) &&
        norm(a.note) === norm(b.note) &&
        norm(a.url) === norm(b.url) &&
        norm(a.quay) === norm(b.quay) &&
        norm(a.date) === norm(b.date);
}


// `refCitation` may be:
//   - null/undefined: nothing pre-attached (Add mode)
//   - a string (legacy): match by sourceXref only
//   - a citation object: match by full content fingerprint
function _buildApplyToEventsRows(person, refCitation) {
    const events = (person && person.events) || [];
    const refIsString = typeof refCitation === 'string';
    const refObj = (refCitation && !refIsString) ? refCitation : null;
    const refSourceXref = refIsString ? refCitation : (refObj && refObj.sourceXref) || null;
    return events.map(ev => {
        const isFam = (ev.event_idx == null) && !!ev.fam_xref;
        const isNameRecord = !!ev._name_record;
        let factKey, tagForKey;
        if (isNameRecord) {
            // Secondary NAMEs are level-1 NAME records. Server addresses them
            // as NAME:N where N is the 0-based NAME index in the INDI block:
            // primary NAME is 0, so AKA _name_occurrence K maps to NAME:K+1.
            factKey = `NAME:${(ev._name_occurrence || 0) + 1}`;
        } else {
            const occ = isFam ? (ev.tag === 'MARR' ? ev.marr_idx : (ev.tag === 'ANUL' ? ev.anul_idx : ev.div_idx)) : ev.event_idx;
            factKey = `${ev.tag}:${occ}`;
        }
        const cites = ev.citations || [];
        const matchingIndices = [];
        if (refObj) {
            cites.forEach((c, i) => {
                if (_citationFingerprintsEqual(c, refObj)) matchingIndices.push(i);
            });
        } else if (refSourceXref) {
            cites.forEach((c, i) => {
                if (c && c.sourceXref === refSourceXref) matchingIndices.push(i);
            });
        }
        return {
            factKey,
            apiXref: isFam ? ev.fam_xref : null,
            label: _applyToEventLabel(ev),
            alreadyAttached: matchingIndices.length > 0,
            alreadyAttachedIndices: matchingIndices,
            checked: matchingIndices.length > 0,
        };
    });
}


function _setApplyToEventChecked(idx, checked) {
    const r = _applyToEventsState.rows[idx];
    if (r) r.checked = !!checked;
}


function _renderApplyToEventsList(containerEl, idPrefix) {
    if (!containerEl) return;
    const html = _applyToEventsState.rows.map((r, i) => {
        const checked = r.checked ? ' checked' : '';
        const labelHtml = (typeof escHtml === 'function') ? escHtml(r.label) : r.label;
        return `<label class="apply-to-event-row">` +
               `<input type="checkbox" data-row-idx="${i}"${checked} ` +
               `onchange="_setApplyToEventChecked(${i}, this.checked)"> ${labelHtml}` +
               `</label>`;
    }).join('');
    containerEl.innerHTML = html;
}

// ── showAddCitationModal ──────────────────────────────────────────────────

// `factKey` is the server-side fact key: either null/undefined for a person-level
// citation, or "TAG:N" (e.g. "BIRT:0") for a fact-level citation. Tests in the
// suite still pass a bare tag like "BIRT" — the backend accepts that too when
// there is only one occurrence, but the canonical format is "TAG:N".

let _addCitationModalXref = null,
    _addCitationModalFactKey = null;


function showAddCitationModal(xref, factKey) {
    _addCitationModalXref = xref;
    _addCitationModalFactKey = factKey;

    const overlayEl = document.getElementById('add-citation-modal-overlay');
    const sourceEl = document.getElementById('add-citation-modal-source');
    const pageEl = document.getElementById('add-citation-modal-page');
    const textEl = document.getElementById('add-citation-modal-text');
    const noteEl = document.getElementById('add-citation-modal-note');
    const urlEl = document.getElementById('add-citation-modal-url');
    const quayEl = document.getElementById('add-citation-modal-quay');
    const dateEl = document.getElementById('add-citation-modal-date');
    const titleEl = document.getElementById('add-citation-modal-title');

    const displayTag = factKey ? String(factKey).split(':')[0] : '';
    if (titleEl) titleEl.textContent = displayTag ? `Add Citation — ${displayTag}` : 'Add Person Source';
    if (pageEl) pageEl.value = '';
    if (textEl) textEl.value = '';
    if (noteEl) noteEl.value = '';
    if (urlEl) urlEl.value = '';
    if (quayEl) quayEl.value = '';
    if (dateEl) dateEl.value = '';

    // Populate sourceXref select from global SOURCES, sorted alphabetically by title
    // (case-insensitive) so users can find a specific source.
    if (sourceEl && typeof SOURCES !== 'undefined') {
        sourceEl.innerHTML = '<option value="">— select source —</option>';
        const entries = Object.entries(SOURCES).map(([sxref, src]) => ({
            sxref,
            label: (src && src.titl) || sxref,
        }));
        entries.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' }));
        for (const { sxref, label } of entries) {
            const opt = (typeof document !== 'undefined' && document.createElement) ?
                document.createElement('option') :
                { value: '', textContent: '' };
            opt.value = sxref;
            opt.textContent = label;
            if (sourceEl.appendChild) sourceEl.appendChild(opt);
        }
    }

    // Apply-to-events picker — only for person-level adds (factKey null).
    const applyRow = document.getElementById('add-citation-apply-to-events-row');
    const applyList = document.getElementById('add-citation-apply-to-events-list');
    if (factKey == null) {
        const person = (typeof PEOPLE !== 'undefined' && PEOPLE) ? PEOPLE[xref] : null;
        _applyToEventsState.mode = 'add';
        _applyToEventsState.rows = _buildApplyToEventsRows(person, null);
        _renderApplyToEventsList(applyList, 'add-citation');
        if (applyRow) applyRow.style.display = '';
    } else {
        _applyToEventsState.mode = null;
        _applyToEventsState.rows = [];
        if (applyList) applyList.innerHTML = '';
        if (applyRow) applyRow.style.display = 'none';
    }

    if (overlayEl) overlayEl.classList.add('open');
    if (sourceEl) setTimeout(() => sourceEl.focus && sourceEl.focus(), 50);
}


function closeAddCitationModal() {
    const overlayEl = document.getElementById('add-citation-modal-overlay');
    if (overlayEl) overlayEl.classList.remove('open');
    _addCitationModalXref = _addCitationModalFactKey = null;
    _applyToEventsState.rows = [];
    _applyToEventsState.mode = null;
}


async function submitAddCitationModal() {
    const xref = _addCitationModalXref;
    const factKey = _addCitationModalFactKey;
    const sourceEl = document.getElementById('add-citation-modal-source');
    const pageEl = document.getElementById('add-citation-modal-page');
    const textEl = document.getElementById('add-citation-modal-text');
    const noteEl = document.getElementById('add-citation-modal-note');
    const urlEl = document.getElementById('add-citation-modal-url');
    const quayEl = document.getElementById('add-citation-modal-quay');
    const dateEl = document.getElementById('add-citation-modal-date');
    const sourceXref = sourceEl ? sourceEl.value : '';
    const page = pageEl ? pageEl.value.trim() : '';
    const text = textEl ? textEl.value.trim() : '';
    const note = noteEl ? noteEl.value.trim() : '';
    const url = urlEl ? urlEl.value.trim() : '';
    const quay = quayEl ? quayEl.value : '';
    const date = dateEl ? dateEl.value.trim() : '';
    // Snapshot the picker rows before closeAddCitationModal() resets them.
    const eventRows = (factKey == null) ?
        _applyToEventsState.rows.filter(r => r.checked && !r.alreadyAttached).slice() :
        [];
    closeAddCitationModal();
    if (!sourceXref) { alert('Please select a source.'); return; }
    try {
        const resp = await apiAddCitation(xref, sourceXref, factKey, page, text, note, url, quay, date);
        if (resp && resp.people) {
            for (const [k, v] of Object.entries(resp.people)) PEOPLE[k] = v;
        }
        for (const row of eventRows) {
            const eventXref = row.apiXref || xref;
            const r2 = await apiAddCitation(eventXref, sourceXref, row.factKey, page, text, note, url, quay, date);
            if (r2 && r2.people) {
                for (const [k, v] of Object.entries(r2.people)) PEOPLE[k] = v;
            }
        }
        if (_sourcesModalXref != null) _refreshSourcesModalContent();
        if (typeof renderPanel !== 'undefined') renderPanel();
    } catch (e) {
        alert('Save failed: ' + e);
    }
}

// ── showEditCitationModal ─────────────────────────────────────────────────


let _editCitationXref = null,
    _editCitationFactTag = null,
    _editCitationIndex = null;

let _editCitationSourceXref = null;

let _editCitationApiXref = null; // may differ from _editCitationXref for FAM events

let _editCitationEventOcc = 0;

// apiXref: optional override for the xref sent to the API (use when FAM xref differs from INDI xref)

function showEditCitationModal(xref, factTag, citationIndex, apiXref, eventOcc) {
    _editCitationXref = xref;
    _editCitationApiXref = apiXref || xref;
    _editCitationFactTag = factTag;
    _editCitationIndex = citationIndex;
    _editCitationEventOcc = (eventOcc != null) ? eventOcc : 0;

    // Locate the citation data from the person's events (always keyed by INDI xref)
    const person = (typeof PEOPLE !== 'undefined') && PEOPLE[xref];
    let cite = null;
    if (person) {
        if (factTag === null || factTag === undefined) {
            // person-level source
            cite = (person.sources || [])[citationIndex] || null;
        } else if (factTag === 'NOTE') {
            const noteOcc = typeof eventOcc === 'number' ? eventOcc : parseInt(eventOcc, 10);
            const n = (person.notes || [])[noteOcc];
            cite = (n && n.citations || [])[citationIndex] || null;
        } else if (factTag === 'SNOTE') {
            const n = (person.notes || []).find(n => n.note_xref === String(eventOcc));
            cite = (n && n.citations || [])[citationIndex] || null;
        } else {
            const isFamCite = _editCitationApiXref && _editCitationApiXref !== _editCitationXref;
            const fact = (person.events || []).find(f => {
                if (f.tag !== factTag) return false;
                if (isFamCite) {
                    const famIdx = f.tag === 'MARR' ? f.marr_idx : (f.tag === 'ANUL' ? f.anul_idx : f.div_idx);
                    return f.fam_xref === _editCitationApiXref && famIdx === _editCitationEventOcc;
                }
                return f.event_idx === _editCitationEventOcc;
            });
            if (fact) cite = (fact.citations || [])[citationIndex] || null;
        }
    }
    _editCitationSourceXref = cite ? (cite.sourceXref || null) : null;

    const overlayEl = document.getElementById('edit-citation-modal-overlay');
    const pageEl = document.getElementById('edit-citation-modal-page');
    const textEl = document.getElementById('edit-citation-modal-text');
    const noteEl = document.getElementById('edit-citation-modal-note');
    const urlEl = document.getElementById('edit-citation-modal-url');
    const quayEl = document.getElementById('edit-citation-modal-quay');
    const dateEl = document.getElementById('edit-citation-modal-date');
    const titleEl = document.getElementById('edit-citation-modal-title');
    const sourceNameEl = document.getElementById('edit-citation-modal-source-name');
    const viewSrcBtn = document.getElementById('edit-citation-view-source-btn');

    if (sourceNameEl) {
        const sxref = _editCitationSourceXref;
        const src = (sxref && typeof SOURCES !== 'undefined' && SOURCES) ? SOURCES[sxref] : null;
        const title = (src && (src.titl || src.title)) || sxref || '';
        sourceNameEl.textContent = title;
    }

    if (titleEl) titleEl.textContent = 'Edit Citation' + (factTag ? ' \u2014 ' + factTag : '');
    if (pageEl) pageEl.value = (cite && cite.page) || '';
    if (textEl) textEl.value = (cite && cite.text) || '';
    if (noteEl) noteEl.value = (cite && cite.note) || '';
    if (urlEl) urlEl.value = (cite && cite.url) || '';
    if (quayEl) quayEl.value = (cite && cite.quay) || '';
    if (dateEl) dateEl.value = (cite && cite.date) || '';

    if (viewSrcBtn && _editCitationSourceXref) {
        const sxref = _editCitationSourceXref;
        viewSrcBtn.onclick = () => showEditSourceModal(sxref);
        viewSrcBtn.style = viewSrcBtn.style || {};
        viewSrcBtn.style.display = '';
    } else if (viewSrcBtn) {
        viewSrcBtn.style = viewSrcBtn.style || {};
        viewSrcBtn.style.display = 'none';
    }

    // Apply-to-events picker — only for person-level edits (factTag null).
    const applyRow = document.getElementById('edit-citation-apply-to-events-row');
    const applyList = document.getElementById('edit-citation-apply-to-events-list');
    if (factTag == null && person) {
        _applyToEventsState.mode = 'edit';
        _applyToEventsState.rows = _buildApplyToEventsRows(person, cite || { sourceXref: _editCitationSourceXref });
        _renderApplyToEventsList(applyList, 'edit-citation');
        if (applyRow) applyRow.style.display = '';
    } else {
        _applyToEventsState.mode = null;
        _applyToEventsState.rows = [];
        if (applyList) applyList.innerHTML = '';
        if (applyRow) applyRow.style.display = 'none';
    }

    if (overlayEl) overlayEl.classList.add('open');
    if (pageEl) setTimeout(() => pageEl.focus && pageEl.focus(), 50);
}


function closeEditCitationModal() {
    const overlayEl = document.getElementById('edit-citation-modal-overlay');
    if (overlayEl) overlayEl.classList.remove('open');
    _editCitationXref = _editCitationFactTag = _editCitationIndex = null;
    _editCitationEventOcc = 0;
    _applyToEventsState.rows = [];
    _applyToEventsState.mode = null;
}


async function submitEditCitationModal() {
    const xref = _editCitationApiXref || _editCitationXref;
    const indiXref = _editCitationXref; // for event-level diff dispatch
    const factTag = _editCitationFactTag;
    const index = _editCitationIndex;
    const eventOcc = _editCitationEventOcc != null ? _editCitationEventOcc : 0;
    const sourceXref = _editCitationSourceXref;
    const pageEl = document.getElementById('edit-citation-modal-page');
    const textEl = document.getElementById('edit-citation-modal-text');
    const noteEl = document.getElementById('edit-citation-modal-note');
    const urlEl = document.getElementById('edit-citation-modal-url');
    const quayEl = document.getElementById('edit-citation-modal-quay');
    const dateEl = document.getElementById('edit-citation-modal-date');
    const page = pageEl ? pageEl.value.trim() : '';
    const text = textEl ? textEl.value.trim() : '';
    const note = noteEl ? noteEl.value.trim() : '';
    const url = urlEl ? urlEl.value.trim() : '';
    const quay = quayEl ? quayEl.value : '';
    const date = dateEl ? dateEl.value.trim() : '';
    // Snapshot picker rows for the diff before close resets state.
    const diffRows = (factTag == null) ? _applyToEventsState.rows.slice() : [];
    closeEditCitationModal();
    try {
        const resp = await apiEditCitation(
            xref,
            factTag ? `${factTag}:${eventOcc}:${index}` : `SOUR:${index}`,
            page, text, note, url, quay, date,
        );
        if (resp && resp.ok) {
            if (resp.people) {
                for (const [k, v] of Object.entries(resp.people)) PEOPLE[k] = v;
            }
        } else {
            alert('Save failed: ' + ((resp && resp.error) || 'unknown'));
            return;
        }
        // Diff: was-attached vs is-checked. Already-attached rows that stay
        // checked are left untouched (non-destructive).
        for (const row of diffRows) {
            const eventXref = row.apiXref || indiXref;
            if (!row.alreadyAttached && row.checked) {
                const r2 = await apiAddCitation(eventXref, sourceXref, row.factKey, page, text, note, url, quay, date);
                if (r2 && r2.people) {
                    for (const [k, v] of Object.entries(r2.people)) PEOPLE[k] = v;
                }
            } else if (row.alreadyAttached && !row.checked) {
                // Delete in descending index order so earlier indices stay valid.
                const indices = (row.alreadyAttachedIndices || []).slice().sort((a, b) => b - a);
                for (const ci of indices) {
                    const r2 = await apiDeleteCitation(eventXref, `${row.factKey}:${ci}`);
                    if (r2 && r2.people) {
                        for (const [k, v] of Object.entries(r2.people)) PEOPLE[k] = v;
                    }
                }
            }
        }
        _refreshSourcesModalContent();
        if (typeof renderPanel === 'function') renderPanel();
    } catch (e) {
        alert('Save failed: ' + e);
    }
}

// ── showEditSourceModal ───────────────────────────────────────────────────


let _editSourceXref = null;


function showEditSourceModal(sourceXref) {
    _editSourceXref = sourceXref;
    const src = (typeof SOURCES !== 'undefined' && SOURCES[sourceXref]) || {};

    const overlayEl = document.getElementById('edit-source-modal-overlay');
    const titlEl = document.getElementById('edit-source-modal-titl');
    const authEl = document.getElementById('edit-source-modal-auth');
    const publEl = document.getElementById('edit-source-modal-publ');
    const repoEl = document.getElementById('edit-source-modal-repo');
    const noteEl = document.getElementById('edit-source-modal-note');
    const warningEl = document.getElementById('edit-source-modal-warning');
    const titleEl = document.getElementById('edit-source-modal-title');

    if (titleEl) titleEl.textContent = 'Edit Source Record';
    if (warningEl) warningEl.textContent = 'Changes to this source record affect all citations that reference it.';
    if (titlEl) titlEl.value = src.titl || '';
    if (authEl) authEl.value = src.auth || '';
    if (publEl) publEl.value = src.publ || '';
    if (repoEl) repoEl.value = src.repo || '';
    if (noteEl) noteEl.value = src.note || '';

    if (overlayEl) overlayEl.classList.add('open');
    if (titlEl) setTimeout(() => titlEl.focus && titlEl.focus(), 50);
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


function showAddSourceModal() {
    const overlayEl = document.getElementById('add-source-modal-overlay');
    const titlEl = document.getElementById('add-source-modal-titl');
    const authEl = document.getElementById('add-source-modal-auth');
    const publEl = document.getElementById('add-source-modal-publ');
    const repoEl = document.getElementById('add-source-modal-repo');
    const noteEl = document.getElementById('add-source-modal-note');

    if (titlEl) titlEl.value = '';
    if (authEl) authEl.value = '';
    if (publEl) publEl.value = '';
    if (repoEl) repoEl.value = '';
    if (noteEl) noteEl.value = '';

    if (overlayEl) overlayEl.classList.add('open');
    if (titlEl) setTimeout(() => titlEl.focus && titlEl.focus(), 50);
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
    const titl = titlEl ? titlEl.value.trim() : '';
    const auth = authEl ? authEl.value.trim() : '';
    const publ = publEl ? publEl.value.trim() : '';
    const repo = repoEl ? repoEl.value.trim() : '';
    const note = noteEl ? noteEl.value.trim() : '';
    if (!titl) { alert('Title is required.'); return; }
    closeAddSourceModal();
    try {
        await apiAddSource(titl, auth, publ, repo, note);
        if (typeof setState !== 'undefined') setState({}); // trigger re-render
    } catch (e) {
        alert('Save failed: ' + e);
    }
}

// ---------------------------------------------------------------------------
// Spouse-menu modal (multi-spouse toggle)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Exports (for Vitest unit tests via CommonJS require)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        openSourcesModal,
        openNoteSourcesModal,
        openIndiSourcesModal,
        closeSourcesModal,
        _buildSourcesModalContent,
        deleteSourceFromModal,
        handleCitationPaste,
        handleCitationCopy,
        showAddCitationModal,
        submitAddCitationModal,
        showEditCitationModal,
        submitEditCitationModal,
        _buildApplyToEventsRows,
        _applyToEventLabel,
        _setApplyToEventChecked,
        showEditSourceModal,
        showAddSourceModal,
    };
}
