// Pure render-to-HTML helpers for the advanced-search results mode.

const _hu = (typeof require !== 'undefined')
    ? require('./viz_html_utils.js')
    : { escapeHtml };
const _escapeHtml = _hu.escapeHtml;

const _as = (typeof require !== 'undefined')
    ? require('./viz_advanced_search.js')
    : { extractYear };
const extractYear = _as.extractYear;

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
    const place = evt.place ? ` in ${_escapeHtml(evt.place)}` : '';
    const yr = _yearRange(evt.yearFrom, evt.yearTo);
    return `${verb}${place}${yr ? ' ' + yr : ''}`;
}

function buildFilterChipsHTML(criteria) {
    const chips = [];
    if (criteria.firstName) chips.push(`First: ${_escapeHtml(criteria.firstName)}`);
    if (criteria.lastName)  chips.push(`Last: ${_escapeHtml(criteria.lastName)}`);
    if (criteria.sex && criteria.sex.has('M')) chips.push('Male');
    if (criteria.sex && criteria.sex.has('F')) chips.push('Female');
    for (const e of (criteria.events || [])) {
        if (!e.place && e.yearFrom == null && e.yearTo == null) continue;
        chips.push(_eventChipText(e));
    }
    for (const f of (criteria.family || [])) {
        if (!f.name) continue;
        chips.push(`${_FAMILY_LABEL[f.kind] || 'Person'}: ${_escapeHtml(f.name)}`);
    }
    return chips.map(c => `<span class="adv-chip">${c}</span>`).join('');
}

function buildCountBarHTML(total, sortKey) {
    const word = total === 1 ? 'match' : 'matches';
    const opts = [
        { v: 'name',  label: 'Name' },
        { v: 'birth', label: 'Birth year' },
    ];
    const optHTML = opts.map(o =>
        `<option value="${o.v}"${o.v === sortKey ? ' selected' : ''}>${o.label}</option>`
    ).join('');
    return `<span class="adv-count"><b>${total} ${word}</b></span>` +
        `<span class="adv-sort">Sort: <select class="adv-sort-select">${optHTML}</select></span>`;
}

function paginate(arr, page, perPage) {
    const start = (page - 1) * perPage;
    return arr.slice(start, start + perPage);
}

function sortResults(rows, sortKey) {
    const copy = rows.slice();
    if (sortKey === 'birth') {
        copy.sort((a, b) => {
            const ya = a.birth_year, yb = b.birth_year;
            if (ya == null && yb == null) return 0;
            if (ya == null) return 1;
            if (yb == null) return -1;
            return ya - yb;
        });
    } else {
        copy.sort((a, b) => {
            const na = (a.name || '').toLowerCase();
            const nb = (b.name || '').toLowerCase();
            return na < nb ? -1 : na > nb ? 1 : 0;
        });
    }
    return copy;
}

function _truncatePlace(place) {
    if (!place) return '';
    const parts = place.split(',').map(s => s.trim()).filter(Boolean);
    if (parts.length <= 2) return parts.join(', ');
    return parts.slice(-2).join(', ');
}

function _formatRowMeta(person, spouseName) {
    const birth = (person.events || []).find(e => e.tag === 'BIRT');
    const death = (person.events || []).find(e => e.tag === 'DEAT');
    const by = birth ? extractYear(birth.date) : null;
    const dy = death ? extractYear(death.date) : null;
    const segments = [];
    if (by != null && dy != null) segments.push(`${by}–${dy}`);
    else if (by != null)          segments.push(`b. ${by}`);
    else if (dy != null)          segments.push(`d. ${dy}`);
    const place = _truncatePlace((birth && birth.place) || (death && death.place) || '');
    if (place) segments.push(place);
    if (spouseName) segments.push(`spouse ${spouseName}`);
    return segments.join(' · ');
}

function buildResultRowsHTML(rows, ctx) {
    const { peopleById, spousesOf } = ctx;
    const out = [];
    for (const r of rows) {
        const full = peopleById[r.id] || r;
        const spouseXref = (spousesOf && spousesOf[r.id]) ? spousesOf[r.id][0] : null;
        const spouseName = spouseXref && peopleById[spouseXref] ? peopleById[spouseXref].name : null;
        const meta = _formatRowMeta(full, spouseName);
        out.push(
            `<div class="adv-row" data-id="${_escapeHtml(r.id)}">` +
                `<div class="adv-row-name">${_escapeHtml(full.name || '?')}</div>` +
                (meta ? `<div class="adv-row-meta">${_escapeHtml(meta)}</div>` : '') +
            `</div>`
        );
    }
    return out.join('');
}

function buildPagerHTML(page, total, perPage) {
    const pageCount = Math.ceil(total / perPage);
    if (pageCount <= 1) return '';
    const start = (page - 1) * perPage + 1;
    const end = Math.min(page * perPage, total);

    const nums = new Set([1, pageCount, page - 1, page, page + 1]);
    const visible = [...nums].filter(n => n >= 1 && n <= pageCount).sort((a, b) => a - b);
    const btns = [];
    let prev = 0;
    for (const n of visible) {
        if (n - prev > 1) btns.push('<span class="adv-pager-gap">…</span>');
        btns.push(
            `<button type="button" data-page="${n}" ` +
                `class="adv-pager-num${n === page ? ' active' : ''}">${n}</button>`
        );
        prev = n;
    }
    const prevDis = page === 1 ? ' disabled' : '';
    const nextDis = page === pageCount ? ' disabled' : '';
    return (
        `<span class="adv-pager-range">${start}–${end} of ${total}</span>` +
        `<span class="adv-pager-btns">` +
            `<button type="button" data-page="prev"${prevDis}>‹</button>` +
            btns.join('') +
            `<button type="button" data-page="next"${nextDis}>›</button>` +
        `</span>`
    );
}

if (typeof module !== 'undefined') {
    module.exports = {
        buildFilterChipsHTML, buildCountBarHTML, buildResultRowsHTML,
        buildPagerHTML, paginate, sortResults,
    };
}
