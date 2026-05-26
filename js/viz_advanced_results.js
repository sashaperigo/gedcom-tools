// Pure render-to-HTML helpers for the advanced-search results mode.

const _hu = (typeof require !== 'undefined')
    ? require('./viz_html_utils.js')
    : { escapeHtml };
const escapeHtml = _hu.escapeHtml;

const _EVENT_VERB = { birth: 'Born', death: 'Died', marriage: 'Married', residence: 'Lived', any: 'Event' };
const _FAMILY_LABEL = { spouse: 'Spouse', father: 'Father', mother: 'Mother', other: 'Person' };

function _yearRange(yf, yt) {
    if (yf != null && yt != null) return yf === yt ? String(yf) : `${yf}–${yt}`;
    if (yf != null) return `${yf}–`;
    if (yt != null) return `–${yt}`;
    return '';
}

function _eventChipText(evt) {
    const verb = _EVENT_VERB[evt.kind] || 'Event';
    const place = evt.place ? ` in ${escapeHtml(evt.place)}` : '';
    const yr = _yearRange(evt.yearFrom, evt.yearTo);
    return `${verb}${place}${yr ? ' ' + yr : ''}`;
}

function buildFilterChipsHTML(criteria) {
    const chips = [];
    if (criteria.firstName) chips.push(`First: ${escapeHtml(criteria.firstName)}`);
    if (criteria.lastName)  chips.push(`Last: ${escapeHtml(criteria.lastName)}`);
    if (criteria.sex && criteria.sex.has('M')) chips.push('Male');
    if (criteria.sex && criteria.sex.has('F')) chips.push('Female');
    for (const e of (criteria.events || [])) {
        if (!e.place && e.yearFrom == null && e.yearTo == null) continue;
        chips.push(_eventChipText(e));
    }
    for (const f of (criteria.family || [])) {
        if (!f.name) continue;
        chips.push(`${_FAMILY_LABEL[f.kind] || 'Person'}: ${escapeHtml(f.name)}`);
    }
    return chips.map(c => `<span class="adv-chip">${c}</span>`).join('');
}

if (typeof module !== 'undefined') {
    module.exports = { buildFilterChipsHTML, escapeHtml };
}
