// Shared helpers for viz modals: panel-distance close handler,
// event label lookup, citation clipboard, paste icon, person-name helper.

function closeIfFarFromPanel(event, panelId, closeFn) {
    const panel = document.getElementById(panelId);
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const dx = Math.max(r.left - event.clientX, 0, event.clientX - r.right);
    const dy = Math.max(r.top - event.clientY, 0, event.clientY - r.bottom);
    if (Math.sqrt(dx * dx + dy * dy) > 100) closeFn();
}

// ---------------------------------------------------------------------------
// Event label lookup (B3)
// ---------------------------------------------------------------------------


const _EVT_LABEL = {
    BIRT: 'Birth',
    DEAT: 'Death',
    BURI: 'Burial',
    CREM: 'Cremation',
    MARR: 'Marriage',
    DIV: 'Divorce',
    ANUL: 'Annulment',
    NATU: 'Naturalization',
    EMIG: 'Emigration',
    IMMI: 'Immigration',
    RESI: 'Residence',
    OCCU: 'Occupation',
    EDUC: 'Education',
    RELI: 'Religion',
    NATI: 'Nationality',
    CENS: 'Census',
    TITL: 'Title',
    ADOP: 'Adoption',
    BAPM: 'Baptism',
    CHR: 'Christening',
    CONF: 'Confirmation',
    GRAD: 'Graduation',
    WILL: 'Will',
    PROB: 'Probate',
};


function _evtLabel(tag, typeVal) {
    if ((tag === 'EVEN' || tag === 'FACT') && typeVal) return typeVal;
    return _EVT_LABEL[tag] || tag;
}

// ---------------------------------------------------------------------------
// Note edit / delete
// ---------------------------------------------------------------------------

let _copiedCitation = null;


const _pasteIconSvg =
    `<svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" ` +
    `stroke-width="1.8" stroke-linecap="round">` +
    `<rect x="3" y="1" width="7" height="9" rx="1.5"/>` +
    `<path d="M3 3H2a1 1 0 00-1 1v7a1 1 0 001 1h7a1 1 0 001-1v-1"/>` +
    `</svg>`;


function copyCitation(citationFields, label) {
    _copiedCitation = { ...citationFields, label };
}


function getCopiedCitation() { return _copiedCitation; }


function clearCopiedCitation() { _copiedCitation = null; }


function _personName(xref) {
    return (PEOPLE[xref] && PEOPLE[xref].name) ||
        ((ALL_PEOPLE.find(p => p.id === xref) || {}).name) || xref;
}

// ---------------------------------------------------------------------------
// Exports (for Vitest unit tests via CommonJS require)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        copyCitation,
        getCopiedCitation,
        clearCopiedCitation,
        _evtLabel,
        _personName,
        _pasteIconSvg,
    };
}
