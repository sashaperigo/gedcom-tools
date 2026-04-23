// Thin wrapper around POST /api/ calls.

async function _post(endpoint, body) {
    const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
}

// ── Person / fact operations ──────────────────────────────────────────────

async function apiDeleteFact(xref, factKey) {
    return _post('/api/delete_fact', { xref, fact_key: factKey });
}

async function apiDeleteNote(xref, noteIdx) {
    return _post('/api/delete_note', { xref, note_idx: noteIdx });
}

async function apiAddNote(xref, text) {
    return _post('/api/add_note', { xref, text });
}

async function apiEditNote(xref, noteIdx, text) {
    return _post('/api/edit_note', { xref, note_idx: noteIdx, text });
}

async function apiEditEvent(xref, factKey, fields) {
    return _post('/api/edit_event', { xref, fact_key: factKey, ...fields });
}

async function apiAddEvent(xref, fields) {
    return _post('/api/add_event', { xref, ...fields });
}

async function apiDeleteMarriage(xref, famXref) {
    return _post('/api/delete_marriage', { xref, fam_xref: famXref });
}

async function apiAddMarriage(xref, spouseXref) {
    return _post('/api/add_marriage', { xref, spouse_xref: spouseXref });
}

async function apiEditName(xref, given, surn) {
    return _post('/api/edit_name', { xref, given, surn });
}

async function apiAddSecondaryName(xref, name, type) {
    return _post('/api/add_secondary_name', { xref, name, type });
}

async function apiEditSecondaryName(xref, nameIdx, name, type) {
    return _post('/api/edit_secondary_name', { xref, name_idx: nameIdx, name, type });
}

async function apiDeleteSecondaryName(xref, nameIdx) {
    return _post('/api/delete_secondary_name', { xref, name_idx: nameIdx });
}

// ── Source operations ─────────────────────────────────────────────────────

async function apiAddSource(titl, auth, publ, repo, note) {
    return _post('/api/add_source', { titl, auth, publ, repo, note });
}

async function apiEditSourceRecord(sourXref, fields) {
    return _post('/api/edit_source_record', { xref: sourXref, ...fields });
}

// ── Citation operations ───────────────────────────────────────────────────

async function apiAddCitation(xref, sourXref, factKey, page, text, note, url, quay, date) {
    return _post('/api/add_citation', {
        xref, sour_xref: sourXref, fact_key: factKey,
        page, text, note, url,
        quay: quay || '', date: date || '',
    });
}

async function apiEditCitation(xref, citationKey, page, text, note, url, quay, date) {
    return _post('/api/edit_citation', {
        xref, citation_key: citationKey,
        page, text, note, url,
        quay: quay || '', date: date || '',
    });
}

async function apiDeleteCitation(xref, citationKey) {
    return _post('/api/delete_citation', { xref, citation_key: citationKey });
}

// ── Relationship operations ───────────────────────────────────────────────

async function apiAddPerson(given, surn, sex, birthYear, relType, relXref) {
    return _post('/api/add_person', { given, surn, sex, birth_year: birthYear, rel_type: relType, rel_xref: relXref });
}

async function apiAddGodparent(xref, godparentXref, rela) {
    const body = { xref, godparent_xref: godparentXref };
    if (rela) body.rela = rela;
    return _post('/api/add_godparent', body);
}

async function apiDeleteGodparent(xref, godparentXref) {
    return _post('/api/delete_godparent', { xref, godparent_xref: godparentXref });
}

async function apiConvertEvent(xref, eventIdx, fromTag, toTag) {
    return _post('/api/convert_event', { xref, event_idx: eventIdx, from_tag: fromTag, to_tag: toTag });
}

async function apiDeletePerson(xref) {
    return _post('/api/delete_person', { xref });
}

if (typeof module !== 'undefined') module.exports = {
    apiDeleteFact,
    apiDeleteNote,
    apiAddNote,
    apiEditNote,
    apiEditEvent,
    apiAddEvent,
    apiDeleteMarriage,
    apiAddMarriage,
    apiEditName,
    apiAddSecondaryName,
    apiEditSecondaryName,
    apiDeleteSecondaryName,
    apiAddSource,
    apiEditSourceRecord,
    apiAddCitation,
    apiEditCitation,
    apiDeleteCitation,
    apiAddPerson,
    apiAddGodparent,
    apiDeleteGodparent,
    apiConvertEvent,
    apiDeletePerson,
};