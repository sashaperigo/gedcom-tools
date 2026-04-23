// Right-side detail panel for the Obsidian-themed genealogy visualizer.
// Ported from viz_detail.js, adapted to use setState/getState/onStateChange.
//
// Depends on globals:
//   PEOPLE, SOURCES, PARENTS, CHILDREN, RELATIVES  — data from Python template
//   setState, getState, onStateChange               — from viz_state.js
//   editEvent, deleteFact, deleteAlias, addEvent,   — from viz_modals.js
//   editNote, deleteNote, addNote,
//   openAliasModal, deleteMarriage

// ── HTML utilities ────────────────────────────────────────────────────────

function escHtml(s) {
    return String(s || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function linkify(s) {
    const URL_RE = /https?:\/\/\S+/g;
    let result = '',
        last = 0,
        m;
    while ((m = URL_RE.exec(s)) !== null) {
        result += escHtml(s.slice(last, m.index));
        const rawUrl = m[0].replace(/[.,;:!?)]+$/, '');
        const href = rawUrl.replace(/&amp;/g, '&');
        result += `<a href="${escHtml(href)}" target="_blank" rel="noopener">${escHtml(rawUrl)}</a>`;
        last = m.index + rawUrl.length;
    }
    result += escHtml(s.slice(last));
    return result;
}

// ── Date / place formatting ───────────────────────────────────────────────

const _MONTH_ABBR = {
    JAN: 'January',
    FEB: 'February',
    MAR: 'March',
    APR: 'April',
    MAY: 'May',
    JUN: 'June',
    JUL: 'July',
    AUG: 'August',
    SEP: 'September',
    OCT: 'October',
    NOV: 'November',
    DEC: 'December'
};

function fmtDate(raw) {
    if (!raw) return '';
    const s = raw.trim().toUpperCase();
    let prefix = '',
        rest = s;
    if (s.startsWith('ABT ')) { prefix = 'about ';
        rest = s.slice(4); } else if (s.startsWith('BEF ')) { prefix = 'before ';
        rest = s.slice(4); } else if (s.startsWith('AFT ')) { prefix = 'after ';
        rest = s.slice(4); } else if (s.startsWith('CAL ') || s.startsWith('EST ')) { prefix = 'about ';
        rest = s.slice(4); }
    const bet = rest.match(/^BET\s+(.+?)\s+AND\s+(.+)$/);
    if (bet) return fmtDate(bet[1]) + ' \u2013 ' + fmtDate(bet[2]);
    const dmy = rest.match(/^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$/);
    if (dmy) return prefix + (_MONTH_ABBR[dmy[2]] || dmy[2]) + ' ' + dmy[1] + ', ' + dmy[3];
    const my = rest.match(/^([A-Z]{3})\s+(\d{4})$/);
    if (my) return prefix + (_MONTH_ABBR[my[1]] || my[1]) + ' ' + my[2];
    const y = rest.match(/^(\d{4})$/);
    if (y) return prefix + y[1];
    return prefix + raw;
}

function fmtPlace(raw) {
    if (!raw) return '';
    const parts = raw.split(',').map(s => s.trim()).filter(Boolean);
    if (parts.length <= 1) return parts[0] || '';
    const last = parts[parts.length - 1];
    const isUSA = /^(USA|United States|United States of America)$/i.test(last);
    if (isUSA) {
        const city = parts[0];
        const state = parts.length >= 3 ? parts[parts.length - 2] : '';
        if (!state) return city;
        const stateOut = /^District of Columbia$/i.test(state) ? 'D.C.' : state;
        return city + ', ' + stateOut;
    }
    return parts.length === 2 ? parts.join(', ') : parts[0] + ', ' + last;
}

function fmtAge(raw) {
    if (!raw) return '';
    const s = raw.trim();
    const uc = s.toUpperCase().replace(/^[<>]/, '');
    if (uc === 'INFANT') return 'in infancy';
    if (uc === 'STILLBORN') return 'stillborn';
    if (uc === 'CHILD') return 'in childhood';
    const prefix = s.startsWith('>') ? 'over ' : s.startsWith('<') ? 'under ' : '';
    let r = s.replace(/^[<>]/, '');
    r = r.replace(/(\d+)y\b/g, (_, n) => `${n} year${n === '1' ? '' : 's'}`);
    r = r.replace(/(\d+)m\b/g, (_, n) => `${n} month${n === '1' ? '' : 's'}`);
    r = r.replace(/(\d+)d\b/g, (_, n) => `${n} day${n === '1' ? '' : 's'}`);
    return (prefix + r.trim().replace(/\s+/g, ' ')).trim();
}

// ── Event labels and prose ────────────────────────────────────────────────

const EVENT_LABELS = {
    BIRT: 'Birth',
    DEAT: 'Death',
    BURI: 'Burial',
    RESI: 'Residence',
    OCCU: 'Occupation',
    IMMI: 'Immigration',
    NATU: 'Naturalization',
    ADOP: 'Adoption',
    EDUC: 'Education',
    RETI: 'Retirement',
    TITL: 'Title',
    CHR: 'Christening',
    BAPM: 'Baptism',
    CONF: 'Confirmation',
    NATI: 'Nationality',
    RELI: 'Religion',
    DIV: 'Divorce',
    FACT: 'Fact',
    MARR: 'Marriage',
    PROB: 'Probate',
    ARRV: 'Arrival',
    DEPA: 'Departure',
    NCHI: 'Children (count)',
    DSCR: 'Physical Description',
};

function buildProse(evt) {
    const date = fmtDate(evt.date);
    const place = evt.place || '';
    const short = fmtPlace(place);
    const type = evt.type || '';
    const addr = evt.addr || '';
    const meta = () => [addr, place, date].filter(Boolean).join(' \u00b7 ');
    switch (evt.tag) {
        case 'BIRT':
            return { prose: short ? `Born in ${short}` : (date ? `Born ${date}` : 'Birth'), meta: meta() };
        case 'DEAT':
            {
                const cause = evt.cause ? `of ${evt.cause}` : '';
                const age = evt.age || '';
                if (cause && short) return { prose: `Died ${cause} in ${short}`, meta: meta() };
                if (cause) return { prose: `Died ${cause}`, meta: meta() };
                if (short) return { prose: `Died in ${short}`, meta: meta() };
                if (!date && age) {
                    const ageUC = age.toUpperCase().replace(/^[<>]/, '');
                    if (ageUC === 'STILLBORN') return { prose: 'Stillborn', meta: meta() };
                    return { prose: `Died at ${fmtAge(age)}`, meta: meta() };
                }
                return { prose: date ? `Died ${date}` : 'Death', meta: meta() };
            }
        case 'BURI':
            return { prose: short ? `Buried in ${short}` : (date ? `Buried ${date}` : 'Burial'), meta: meta() };
        case 'RESI':
            return { prose: short ? `Lived in ${short}` : (date ? `Lived ${date}` : 'Residence'), meta: meta() };
        case 'OCCU':
            {
                const jobTitle = evt.inline_val || '';
                return { prose: jobTitle ? `Worked as ${jobTitle}` : (short ? `Worked in ${short}` : 'Occupation'), meta: meta() };
            }
        case 'IMMI':
            return { prose: short ? `Immigrated to ${short}` : (date ? `Immigrated ${date}` : 'Immigration'), meta: meta() };
        case 'NATU':
            return { prose: short ? `Naturalized in ${short}` : (date ? `Naturalized ${date}` : 'Naturalization'), meta: meta() };
        case 'ADOP':
            return { prose: date ? `Adopted ${date}` : 'Adoption', meta: short };
        case 'EDUC':
            return { prose: 'Education', meta: [type, place, date].filter(Boolean).join(' \u00b7 ') };
        case 'RETI':
            return { prose: date ? `Retired ${date}` : 'Retirement', meta: short };
        case 'TITL':
            return { prose: type ? `Held title: ${type}` : 'Title', meta: date };
        case 'CHR':
            return { prose: short ? `Christened in ${short}` : (date ? `Christened ${date}` : 'Christening'), meta: meta() };
        case 'BAPM':
            return { prose: short ? `Baptized in ${short}` : (date ? `Baptized ${date}` : 'Baptism'), meta: meta() };
        case 'CONF':
            return { prose: short ? `Confirmed in ${short}` : (date ? `Confirmed ${date}` : 'Confirmation'), meta: meta() };
        case 'NATI':
            return { prose: type ? `Nationality: ${type}` : (short ? `Nationality: ${short}` : 'Nationality'), meta: date };
        case 'RELI':
            return { prose: 'Religion', meta: type || date };
        case 'DIV':
            return { prose: date ? `Divorced ${date}` : 'Divorce', meta: short };
        case 'FACT':
            {
                if (type && type.toUpperCase() === 'AKA')
                    return { prose: `Also known as: ${evt.note || ''}`, meta: date };
                return { prose: type || short || 'Fact', meta: date };
            }
        case 'MARR':
            {
                const who = evt.spouse || '';
                const prose = who ? `Married ${who}` : 'Marriage';
                return { prose, meta: meta() };
            }
        case 'NCHI':
            {
                const count = evt.inline_val || '';
                return { prose: count ? `${count} children` : 'Children (count)', meta: date };
            }
        case 'DSCR':
            {
                const desc = evt.inline_val || '';
                return { prose: desc ? `Description: ${desc}` : 'Physical Description', meta: date };
            }
        case 'PROB':
            return { prose: short ? `Probate in ${short}` : (date ? `Probate ${date}` : 'Probate'), meta: meta() };
        case 'ARRV':
            return { prose: short ? `Arrived in ${short}` : (date ? `Arrived ${date}` : 'Arrival'), meta: meta() };
        case 'DEPA':
            return { prose: short ? `Departed from ${short}` : (date ? `Departed ${date}` : 'Departure'), meta: meta() };
        default:
            {
                if (type === 'Arrival')
                    return { prose: short ? `Arrived in ${short}` : (date ? `Arrived ${date}` : 'Arrival'), meta: meta() };
                if (type === 'Departure')
                    return { prose: short ? `Departed from ${short}` : (date ? `Departed ${date}` : 'Departure'), meta: meta() };
                if (type === 'Church') {
                    return { prose: evt.addr || short || 'Church', meta: meta() };
                }
                return {
                    prose: type || (short ? short : (EVENT_LABELS[evt.tag] || evt.tag)),
                    meta: meta()
                };
            }
    }
}

function dotColor(evt) {
    if (evt.type === 'Name Change') return '#f97316';
    if (evt.tag === 'MARR') return '#e879f9';
    switch (evt.tag) {
        case 'BIRT':
        case 'DEAT':
            return '#e4e4ff';
        case 'BURI':
            return '#727298';
        case 'RESI':
            return '#38bdf8';
        case 'OCCU':
        case 'RETI':
            return '#fbbf24';
        case 'IMMI':
        case 'NATU':
            return '#34d399';
        case 'CHR':
        case 'BAPM':
        case 'CONF':
        case 'RELI':
            return '#2dd4bf';
        case 'EDUC':
            return '#818cf8';
        default:
            return '#727298';
    }
}

// ── Residence collapsing ──────────────────────────────────────────────────

const _YR_RE = /\b(\d{4})\b/;

// Keys: `${xref}:${startEventIdx}` for collapsed RESI runs that are expanded.
const _expandedResiRuns = new Set();

function toggleResiExpand(xref, startIdx) {
    const key = `${xref}:${startIdx}`;
    if (_expandedResiRuns.has(key)) _expandedResiRuns.delete(key);
    else _expandedResiRuns.add(key);
    renderPanel();
}

function collapseResidences(events) {
    const result = [];
    let i = 0;
    while (i < events.length) {
        const evt = events[i];
        if (evt.tag !== 'RESI') { result.push(evt);
            i++; continue; }
        const short = fmtPlace(evt.place || '');
        const run = [evt];
        let j = i + 1;
        while (j < events.length && events[j].tag === 'RESI' &&
            fmtPlace(events[j].place || '') === short) {
            run.push(events[j]);
            j++;
        }
        if (run.length < 2) { result.push(evt);
            i = j; continue; }
        const years = run.map(e => (_YR_RE.exec(e.date || '') || [, null])[1]).filter(Boolean);
        // For BET ranges, _YR_RE only grabs the first year; extract the last 4-digit year
        // from the last event's date to use as the end of the displayed range.
        const lastDateYears = [...(run[run.length - 1].date || '').matchAll(/\b(\d{4})\b/g)];
        const endYear = lastDateYears.length ? lastDateYears[lastDateYears.length - 1][1] : years[years.length - 1];
        const startYear = years[0];
        const yearRange = (startYear && endYear && startYear !== endYear)
            ? `${startYear}\u2013${endYear}`
            : (startYear || endYear || '');
        const notes = run.flatMap(e => {
            if (!e.note) return [];
            const yr = (_YR_RE.exec(e.date || '') || [, null])[1];
            return [yr ? `${yr}: ${e.note}` : e.note];
        });
        result.push({ ...evt, _yearRange: yearRange, _run: run, note: notes.length ? notes.join('\n') : null });
        i = j;
    }
    return result;
}

// ── Citation badge helper ─────────────────────────────────────────────────

function buildSourceBadgeHtml(citations, xref, origIdx) {
    const n = (citations && citations.length) || 0;
    const label = n === 0 ? 'Add a source' : (n === 1 ? '1 source' : `${n} sources`);
    const text = n === 0 ? '+ src' : `${n} src`;
    const cls = n === 0 ? 'evt-src-badge evt-src-badge-empty' : 'evt-src-badge';
    const xrefQ = JSON.stringify(String(xref)).replace(/"/g, '&quot;');
    return `<span class="${cls}" title="${label}" onclick="event.stopPropagation();openSourcesModal(${xrefQ},${origIdx})">${text}</span>`;
}

function buildNoteSourceBadgeHtml(citations, xref, noteDisplayIdx) {
    const n = (citations && citations.length) || 0;
    const label = n === 0 ? 'Add a source' : (n === 1 ? '1 source' : `${n} sources`);
    const text = n === 0 ? '+ src' : `${n} src`;
    const cls = n === 0 ? 'note-src-badge note-src-badge-empty' : 'note-src-badge';
    const xrefQ = JSON.stringify(String(xref)).replace(/"/g, '&quot;');
    return `<span class="${cls}" title="${label}" onclick="event.stopPropagation();openNoteSourcesModal(${xrefQ},${noteDisplayIdx})">${text}</span>`;
}

// ── Godparent click handler (exported for tests) ───────────────────────────

const _GODPARENT_RELAS = new Set(['Godparent', 'Godfather', 'Godmother']);

function _handleGodparentClick(godparentXref) {
    setState({ focusXref: godparentXref, panelXref: godparentXref, panelOpen: true });
}

function _buildGodparentPillsHtml(evt, xref, xrefQ) {
    const assoArr = (evt.asso || []).filter(a => _GODPARENT_RELAS.has(a.rela));
    const isChrOrBapm = evt.tag === 'CHR' || evt.tag === 'BAPM';
    if (!isChrOrBapm && assoArr.length === 0) return '';
    let html = `<div class="panel-godparents">`;
    for (const asso of assoArr) {
        const gp = (typeof PEOPLE !== 'undefined') && PEOPLE[asso.xref];
        const gpName = gp ? escHtml(gp.name) : escHtml(asso.xref);
        const xrefJs = JSON.stringify(asso.xref).replace(/"/g, '&quot;');
        const roleSuffix = (asso.rela === 'Godfather' || asso.rela === 'Godmother') ?
            ` <span class="panel-godparent-role">(${asso.rela === 'Godfather' ? '\u2642' : '\u2640'})</span>` :
            '';
        html += `<span class="panel-godparent-pill" data-xref="${escHtml(asso.xref)}" onclick="setState({focusXref:${xrefJs},panelXref:${xrefJs},panelOpen:true})">${gpName}${roleSuffix}</span>`;
    }
    if (assoArr.length < 2) {
        html += `<button class="panel-add-godparent-btn" onclick="showAddGodparentModal(${xrefQ})">+ Add Godparent</button>`;
    }
    html += `</div>`;
    return html;
}

// ── Module state ──────────────────────────────────────────────────────────

let _panelEl = null;
let _familyOpen = false;

function _toggleSourcesSection(btn) {
    const section = document.getElementById('detail-sources');
    if (!section) return;
    const collapsed = section.classList.toggle('sources-collapsed');
    btn.setAttribute('aria-expanded', String(!collapsed));
    const arrow = btn.querySelector('.sources-toggle-arrow');
    if (arrow) arrow.textContent = collapsed ? '▶' : '▼';
}

function _toggleFamily() {
    _familyOpen = !_familyOpen;
    renderPanel();
}

// ── Main render function ──────────────────────────────────────────────────

function renderPanel() {
    if (!_panelEl) return;

    const state = getState();

    if (!state.panelOpen) {
        _panelEl.classList.remove('panel-open');
        return;
    }

    const xref = state.panelXref;
    if (!xref) {
        _panelEl.classList.remove('panel-open');
        return;
    }

    const data = (typeof PEOPLE !== 'undefined') && PEOPLE[xref];
    if (!data) {
        _panelEl.classList.remove('panel-open');
        return;
    }

    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#818cf8';
    const xrefQ = JSON.stringify(xref).replace(/"/g, '&quot;');

    // ── Accent bar ────────────────────────────────────────────────────────
    const accentEl = document.getElementById('detail-accent-bar');
    if (accentEl) accentEl.style.background = '';

    // ── ID badge ──────────────────────────────────────────────────────────
    const headerInner = document.getElementById('detail-header-inner');
    if (headerInner) {
        const existing = headerInner.querySelector('.detail-person-id');
        if (existing) existing.remove();
        const idBadge = document.createElement('div');
        idBadge.className = 'detail-person-id';
        idBadge.textContent = 'Person \xb7 ' + xref.toUpperCase();
        headerInner.insertBefore(idBadge, headerInner.firstChild);
    }

    // ── Name + sex symbol + edit button ──────────────────────────────────
    const nameEl = document.getElementById('detail-name');
    if (nameEl) {
        const sexSym = { 'M': '\u2642', 'F': '\u2640' } [data.sex] || '';
        nameEl.innerHTML =
            escHtml(data.name || '') +
            (sexSym ? `<span class="sex-sym">${sexSym}</span>` : '') +
            `<button class="name-edit-btn" title="Edit name" onclick="editName(${xrefQ})">\u270f</button>`;
    }

    // ── Close button ──────────────────────────────────────────────────────
    const closeBtn = document.getElementById('panel-close-btn');
    if (closeBtn) {
        closeBtn.onclick = () => setState({ panelOpen: false });
    }

    // ── Set-root button ───────────────────────────────────────────────────
    const setRootBtn = document.getElementById('detail-set-root-btn');
    if (setRootBtn) {
        setRootBtn.onclick = () => setState({ focusXref: xref });
    }

    // ── Lifespan bar ──────────────────────────────────────────────────────
    const by = data.birth_year ? parseInt(data.birth_year) : null;
    const dy = data.death_year ? parseInt(data.death_year) : null;
    // Lifespan — mono text only (bar hidden via CSS)
    const lifespanRow = document.getElementById('detail-lifespan-row');
    if (lifespanRow) {
        if (by) {
            const span = (dy && dy > by) ? dy - by : null;
            const deathPart = dy
                ? `<span class="lifespan-year">${dy}</span>`
                : `<span class="lifespan-year lifespan-living"><em>Living</em></span>`;
            lifespanRow.innerHTML =
                `<span class="lifespan-year">${by}</span>` +
                `<span class="lifespan-sep">\u2013</span>` +
                deathPart +
                (span ? `<span class="lifespan-age">\u00b7 ${span} yrs</span>` : '');
        } else {
            lifespanRow.innerHTML = '';
        }
    } else {
        const lifespanEl = document.getElementById('detail-lifespan');
        if (lifespanEl) {
            let html = '';
            if (by) html += `<span class="panel-birth-year">${escHtml(String(by))}</span>`;
            if (by) html += `<span class="panel-lifespan-sep">\u2013</span>`;
            if (dy) html += `<span class="panel-death-year">${escHtml(String(dy))}</span>`;
            else if (by) html += `<span class="panel-death-year panel-living"><em>Living</em></span>`;
            if (by && dy) {
                const age = dy - by;
                if (age > 0) html += `<span class="panel-age">\u00b7 ${age} yrs</span>`;
            }
            lifespanEl.innerHTML = html;
        }
    }

    // ── AKA aliases ───────────────────────────────────────────────────────
    const akaDiv = document.getElementById('detail-aka');
    if (akaDiv) {
        const xrefQA = JSON.stringify(xref).replace(/"/g, '&quot;');
        const akaEvents = (data.events || []).map((e, i) => ({ ...e, _origIdx: i }))
            .filter(e => e._name_record && e.note);
        const addAkaBtn = `<button class="aka-btn" title="Add secondary name" style="font-size:11px;color:var(--text-disabled);margin-left:4px" onclick="openAliasModal(${xrefQA},null,'','AKA',true)">&#43; alias</button>`;
        if (akaEvents.length) {
            const entries = akaEvents.map(e => {
                const editBtn = e._name_record === true ?
                    `<button class="aka-btn" title="Edit name" onclick="openAliasModal(${xrefQA},${e._name_occurrence},${JSON.stringify(e.note).replace(/"/g,'&quot;')},${JSON.stringify(e.type || 'AKA').replace(/"/g,'&quot;')},true)">\u270f</button>` :
                    (e.event_idx !== null && e.event_idx !== undefined ?
                        `<button class="aka-btn" title="Edit alias" onclick="editEvent(${xrefQA},${e.event_idx},'FACT')">\u270f</button>` :
                        '');
                const delBtn = `<button class="aka-btn del" title="Delete name" onclick="deleteAlias(${xrefQA},PEOPLE[${xrefQA}].events[${e._origIdx}])">\u2715</button>`;
                const typeLabel = (e.type && e.type.toUpperCase() !== 'AKA') ? `<span style="font-size:10px;color:var(--text-secondary);margin-right:2px">${escHtml(e.type)}:</span>` : '';
                return `<span class="aka-entry">${typeLabel}<span style="font-style:italic">${escHtml(e.note)}</span>${editBtn}${delBtn}</span>`;
            }).join(' \xb7 ');
            akaDiv.innerHTML = entries + addAkaBtn;
        } else {
            akaDiv.innerHTML = addAkaBtn;
        }
    }

    // ── Notes ─────────────────────────────────────────────────────────────
    const notesDiv = document.getElementById('detail-notes');
    if (notesDiv) {
        const notes = data.notes || [];
        const xrefQN = JSON.stringify(xref).replace(/"/g, '&quot;');
        if (notes.length) {
            const count = notes.length;
            const label = count === 1 ? '1 Note' : `${count} Notes`;
            const cards = notes.map((n, i) => {
                const noteText = (n && typeof n === 'object') ? n.text : n;
                const isShared = n && n.shared;
                const citations = (n && n.citations) || [];
                const sharedClass = isShared ? ' shared' : '';
                const borderStyle = isShared ? '' : ` style="border-left-color:${accent}"`;
                const srcBadge = buildNoteSourceBadgeHtml(citations, xref, i);
                return `<div class="note-card-wrap">` +
                    `<div class="note-card${sharedClass}"${borderStyle}>${linkify(noteText)}</div>` +
                    `<div class="note-actions">` +
                    `<button class="note-action-btn" title="Edit note" onclick="editNote(${xrefQN},${i})">\u270f</button>` +
                    `<button class="note-action-btn" title="Delete note" onclick="deleteNote(${xrefQN},${i})">\u2715</button>` +
                    `</div>` +
                    srcBadge +
                    `</div>`;
            }).join('');
            notesDiv.innerHTML =
                `<div class="notes-header">` +
                `<button class="notes-toggle open" onclick="this.closest('.notes-header').nextElementSibling.style.display=` +
                `this.classList.toggle('open')?'block':'none'">` +
                `<span class="notes-toggle-arrow">&#9658;</span>${escHtml(label)}</button>` +
                `<button class="note-add-btn" title="Add note" onclick="addNote(${xrefQN})">&#43; Add Note</button>` +
                `</div>` +
                `<div class="notes-body">${cards}</div>`;
        } else {
            notesDiv.innerHTML =
                `<button class="note-add-btn" onclick="addNote(${xrefQN})">&#43; Add Note</button>`;
        }
    }

    // ── Nationalities (header section) ───────────────────────────────────
    const natiHeaderDiv = document.getElementById('detail-nationalities');
    if (natiHeaderDiv) {
        const natiEvents = (data.events || []).map((e, i) => ({ ...e, _origIdx: i }))
            .filter(e => e.tag === 'NATI');
        const addNatiBtn = `<button class="add-event-btn" onclick="addEvent(${xrefQ},'NATI')">&#43; Add nationality</button>`;
        if (natiEvents.length) {
            const pills = natiEvents.map(e => {
                const _pillYr = e.date ? ((_YR_RE.exec(e.date) || [, null])[1]) : null;
                const dateStr = _pillYr ? `<span class="pill-date">${_pillYr}</span>` : '';
                const editBtn = e.event_idx !== null && e.event_idx !== undefined ?
                    `<button class="facts-pill-btn" title="Edit" onclick="editEvent(${xrefQ},${e.event_idx},'NATI')">\u270f</button>` :
                    '';
                const delBtn = `<button class="facts-pill-btn del" title="Delete" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${e._origIdx}])">\u2715</button>`;
                const actions = `<span class="facts-pill-actions">${editBtn}${delBtn}</span>`;
                return `<span class="facts-pill-wrap"><span class="facts-pill">${escHtml(e.inline_val || '')}${dateStr}</span>${actions}</span>`;
            }).join('');
            natiHeaderDiv.innerHTML = `<div class="facts-pills">${pills}${addNatiBtn}</div>`;
        } else {
            natiHeaderDiv.innerHTML = addNatiBtn;
        }
    }

    // ── Facts section (no longer includes NATI) ───────────────────────────
    const factsDiv = document.getElementById('detail-facts');
    if (factsDiv) {
        factsDiv.innerHTML = '';
        factsDiv.className = '';
    }

    // ── Timeline events ────────────────────────────────────────────────────
    const evtDiv = document.getElementById('detail-events');
    const alsoLivedDiv = document.getElementById('detail-also-lived');

    // Filter: exclude NATI (shown above), name records, and blank events
    const allVisible = (data.events || []).map((e, i) => ({ ...e, _origIdx: i })).filter(e =>
        e.tag !== 'NATI' &&
        (e.tag === 'MARR' || e.date || e.place || e.note || e.type || e.cause || e.addr) &&
        !e._name_record
    );
    const _keepInTimeline = e =>
        e.tag !== 'RELI' && (
            e.date ||
            e.tag === 'BIRT' || e.tag === 'DEAT' || e.tag === 'BURI' || e.tag === 'PROB' || e.tag === 'MARR' ||
            e.tag === 'BAPM' || e.tag === 'CONF' ||
            e.type === 'Arrival' || e.type === 'Departure');
    const undatedFactoids = allVisible.filter(e => !_keepInTimeline(e));
    const visible = allVisible.filter(_keepInTimeline);
    const sorted = collapseResidences(visible);

    if (evtDiv) {
        const _addEvtBtn = `<button class="add-event-btn" onclick="addEvent(${xrefQ})">&#43; Add event</button>`;
        if (!sorted.length) { evtDiv.innerHTML = _addEvtBtn; } else {
            let html = '',
                lastSection = '';
            for (const evt of sorted) {
                let section = 'Life';
                const evtYear = evt.date ? ((_YR_RE.exec(evt.date) || [, 0])[1] | 0) : null;
                const _typ = (evt.type || '').toLowerCase();
                const _isDeathRelated = evt.tag === 'DEAT' || evt.tag === 'BURI' || evt.tag === 'PROB' ||
                    (evt.tag === 'EVEN' && (_typ.includes('death') || _typ.includes('obituar') || _typ.includes('avis de d') || _typ.includes('probate')));
                if (evt.tag === 'BIRT' || (evtYear && by && evtYear <= by + 18)) section = 'Early Life';
                else if (_isDeathRelated) section = 'Later Life';

                if (section !== lastSection) {
                    html += `<span class="timeline-section-label">${escHtml(section).toUpperCase()}</span>`;
                    lastSection = section;
                }

                const { prose, meta } = buildProse(evt);
                const color = dotColor(evt);
                const noteInl = evt.note ?
                    evt.note.split('\n').map(l => `<div class="evt-note-inline">${escHtml(l)}</div>`).join('') : '';

                if (evt.tag === 'MARR') {
                    const yearLabel = evtYear ? `<div class="marr-year">${evtYear}</div>` : '';
                    const spXref = evt.spouse_xref;
                    const spClickable = spXref && (typeof PARENTS !== 'undefined') && PARENTS[spXref];
                    const spXrefAttr = spClickable ? escHtml(spXref) : '';
                    const marrClick = spClickable ?
                        ` style="cursor:pointer" data-spouse-xref="${spXrefAttr}" onclick="setState({focusXref:this.dataset.spouseXref,panelXref:this.dataset.spouseXref,panelOpen:true})"` : '';
                    const proseHtml = spClickable ?
                        `<div class="marr-prose marr-link">${escHtml(prose)}</div>` :
                        `<div class="marr-prose">${escHtml(prose)}</div>`;
                    const marrEditBtn = evt.fam_xref ?
                        `<button class="marr-edit-btn" title="Edit marriage" onclick="event.stopPropagation();editEvent(${xrefQ},null,'MARR',${JSON.stringify(evt.fam_xref).replace(/"/g,'&quot;')},${evt.marr_idx ?? 0})">\u270f</button>` :
                        '';
                    const marrDelBtn = evt.fam_xref ?
                        `<button class="marr-del-btn" title="Delete marriage" onclick="event.stopPropagation();deleteMarriage(${xrefQ},${JSON.stringify(evt.fam_xref).replace(/"/g,'&quot;')},${evt.marr_idx ?? 0})">\u2715</button>` :
                        '';
                    const marrSrcBadge = buildSourceBadgeHtml(evt.citations, xref, evt._origIdx);
                    html +=
                        `<div class="marr-card"${marrClick}>` +
                        marrEditBtn +
                        marrDelBtn +
                        yearLabel +
                        proseHtml +
                        (meta && meta !== String(evtYear) ? `<div class="marr-meta">${escHtml(meta)}</div>` : '') +
                        noteInl +
                        marrSrcBadge +
                        `</div>`;
                    continue;
                }

                // Collapsed RESI run \u2014 expand-to-edit
                if (evt._run) {
                    const runKey = `${xref}:${evt.event_idx}`;
                    const isExpanded = _expandedResiRuns.has(runKey);
                    const tagAbbr = 'RESI';

                    if (isExpanded) {
                        for (let ri = 0; ri < evt._run.length; ri++) {
                            const re = evt._run[ri];
                            const reYear = re.date ? ((_YR_RE.exec(re.date) || [, 0])[1] | 0) : null;
                            const reYearStr = reYear ? `<span class="evt-year">${reYear}</span>` : '';
                            const { prose: reProse, meta: reMeta } = buildProse(re);
                            const reEditBtn = re.event_idx !== null && re.event_idx !== undefined
                                ? `<button class="evt-edit-btn" title="Edit event" onclick="editEvent(${xrefQ},${re.event_idx},'RESI')">\u270f</button>`
                                : '';
                            const reDelBtn = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${re._origIdx}])">\u2715</button>`;
                            const collapseBtn = ri === 0
                                ? `<button class="evt-edit-btn" title="Collapse" onclick="toggleResiExpand(${xrefQ},${evt.event_idx})">\u25b4</button>`
                                : '';
                            const reSrcBadge = buildSourceBadgeHtml(re.citations, xref, re._origIdx);
                            html +=
                                `<div class="evt-entry evt-entry-expanded">` +
                                `<div class="evt-year-col">${reYearStr}<span class="evt-tag-abbrev">${tagAbbr}</span></div>` +
                                `<div class="evt-content">` +
                                `<span class="evt-prose-text">${escHtml(reProse)}</span>` +
                                (reMeta && reMeta !== String(reYear) ? `<div class="evt-meta">${escHtml(reMeta)}</div>` : '') +
                                `<div class="evt-actions">${collapseBtn}${reEditBtn}${reDelBtn}</div>` +
                                `</div>` +
                                reSrcBadge +
                                `</div>`;
                        }
                    } else {
                        const yearStr = `<span class="evt-year">${escHtml(evt._yearRange)}</span>`;
                        const expandBtn = `<button class="evt-edit-btn" title="Expand to edit" onclick="toggleResiExpand(${xrefQ},${evt.event_idx})">\u270f</button>`;
                        const delBtn = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">\u2715</button>`;
                        const srcBadge = buildSourceBadgeHtml(evt.citations, xref, evt._origIdx);
                        html +=
                            `<div class="evt-entry">` +
                            `<div class="evt-year-col">${yearStr}<span class="evt-tag-abbrev">${tagAbbr}</span></div>` +
                            `<div class="evt-content">` +
                            `<span class="evt-prose-text">${escHtml(prose)}</span>` +
                            (meta && meta !== String(evtYear) ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
                            noteInl +
                            `<div class="evt-actions">${expandBtn}${delBtn}</div>` +
                            `</div>` +
                            srcBadge +
                            `</div>`;
                    }
                    continue;
                }

                const isAnch = evt.tag === 'BIRT' || evt.tag === 'DEAT';
                const dotCls = isAnch ? 'evt-dot dot-anchor' : 'evt-dot';
                const yearStr = evtYear ? `<span class="evt-year">${evtYear}</span>` : '';
                const delBtn = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">\u2715</button>`;
                const editBtn = evt.event_idx !== null && evt.event_idx !== undefined ?
                    `<button class="evt-edit-btn" title="Edit event" onclick="editEvent(${xrefQ},${evt.event_idx},${JSON.stringify(evt.tag).replace(/"/g,'&quot;')})">\u270f</button>` :
                    '';
                const convertBtn = evt.tag === 'BIRT' && evt.event_idx !== null && evt.event_idx !== undefined ?
                    `<button class="evt-convert-btn" title="Convert to Baptism" onclick="convertEventTag(${xrefQ},${evt.event_idx},'BIRT','BAPM')">\u2192 Baptism</button>` :
                    '';
                const srcBadge = buildSourceBadgeHtml(evt.citations, xref, evt._origIdx);

                // Godparents (CHR/BAPM)
                const godparentHtml = _buildGodparentPillsHtml(evt, xref, xrefQ);

                const tagAbbr = evt.tag ? evt.tag.substring(0, 4) : '';
                html +=
                    `<div class="evt-entry">` +
                    `<div class="evt-year-col">${yearStr}<span class="evt-tag-abbrev">${tagAbbr}</span></div>` +
                    `<div class="evt-content">` +
                    `<span class="evt-prose-text">${escHtml(prose)}</span>` +
                    (meta && meta !== String(evtYear) ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
                    noteInl +
                    godparentHtml +
                    `<div class="evt-actions">${convertBtn}${editBtn}${delBtn}</div>` +
                    `</div>` +
                    srcBadge +
                    `</div>`;
            }
            html += _addEvtBtn;
            evtDiv.innerHTML = html;
        }
    }

    // ── Undated bottom sections ────────────────────────────────────────────
    if (alsoLivedDiv) {
        function undatedRows(evts) {
            return evts.map(evt => {
                const { prose, meta } = buildProse(evt);
                const color = dotColor(evt);
                const noteInl = evt.note ? evt.note.split('\n').map(l => `<div class="evt-note-inline">${escHtml(l)}</div>`).join('') : '';
                const delBtn = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">\u2715</button>`;
                const editBtn = evt.event_idx !== null && evt.event_idx !== undefined ?
                    `<button class="evt-edit-btn" title="Edit event" onclick="editEvent(${xrefQ},${evt.event_idx},${JSON.stringify(evt.tag).replace(/"/g,'&quot;')})">\u270f</button>` :
                    '';
                const srcBadge = buildSourceBadgeHtml(evt.citations, xref, evt._origIdx);
                const undGpHtml = _buildGodparentPillsHtml(evt, xref, xrefQ);
                const undTagAbbr = evt.tag ? evt.tag.substring(0, 4) : '';
                return `<div class="evt-entry">` +
                    `<div class="evt-year-col"><span class="evt-tag-abbrev">${undTagAbbr}</span></div>` +
                    `<div class="evt-content">` +
                    `<span class="evt-prose-text">${escHtml(prose)}</span>` +
                    (meta ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
                    noteInl +
                    undGpHtml +
                    `<div class="evt-actions">${editBtn}${delBtn}</div>` +
                    `</div>` +
                    srcBadge +
                    `</div>`;
            }).join('');
        }

        const _xrefQ2 = JSON.stringify(xref).replace(/"/g, '&quot;');
        const _addFactBtn = `<select class="add-fact-select" onchange="if(this.value){addEvent(${_xrefQ2},this.value);this.selectedIndex=0}">` +
            `<option value="" disabled selected>&#43; Add fact\u2026</option>` +
            `<option value="ADOP">Adoption</option>` +
            `<option value="NCHI">Children (count)</option>` +
            `<option value="CHR">Christening</option>` +
            `<option value="EDUC">Education</option>` +
            `<option value="FACT:Languages">Languages</option>` +
            `<option value="FACT:Literacy">Literacy</option>` +
            `<option value="FACT:Medical condition">Medical condition</option>` +
            `<option value="OCCU">Occupation</option>` +
            `<option value="DSCR">Physical Description</option>` +
            `<option value="FACT:Politics">Politics</option>` +
            `<option value="RELI">Religion</option>` +
            `<option value="RETI">Retirement</option>` +
            `<option value="TITL">Title</option>` +
            `</select>`;

        let bottomHtml = ''; {
            const residences = undatedFactoids.filter(e => e.tag === 'RESI');
            const otherFacts = undatedFactoids.filter(e => e.tag !== 'RESI');
            otherFacts.sort((a, b) => {
                const tagCmp = (a.tag || '').localeCompare(b.tag || '');
                if (tagCmp !== 0) return tagCmp;
                return (a.type || a.inline_val || '').localeCompare(b.type || b.inline_val || '');
            });
            if (residences.length) {
                bottomHtml += `<span class="also-lived-heading">Also lived in</span>` + undatedRows(residences);
            }
            bottomHtml += `<span class="also-lived-heading">Facts</span>`;
            if (otherFacts.length) bottomHtml += undatedRows(otherFacts);
            bottomHtml += _addFactBtn;
        }

        alsoLivedDiv.innerHTML = bottomHtml;
        alsoLivedDiv.className = 'has-content';
    }

    // ── Family section ────────────────────────────────────────────────────
    const familyDiv = document.getElementById('detail-family');
    if (familyDiv) {
        const _ly = p => {
            if (!p) return '';
            const b = p.birth_year || '',
                d = p.death_year || '';
            return (b || d) ? `${b}\u2013${d}` : '';
        };
        const _sx = p => !p ? '' :
            p.sex === 'M' ? '<span class="family-sex-m">\u2022</span>' :
            p.sex === 'F' ? '<span class="family-sex-f">\u2022</span>' : '';
        const _pr = px => {
            const p = (typeof PEOPLE !== 'undefined') && PEOPLE[px];
            const name = p ? escHtml(p.name || '?') : '?';
            const ly = _ly(p);
            const sx = _sx(p);
            const pxQ = JSON.stringify(px).replace(/"/g, '&quot;');
            const link = `<span class="family-link" onclick="setState({focusXref:${pxQ},panelXref:${pxQ},panelOpen:true})">${name}</span>`;
            const years = ly ? `<span class="family-years">${escHtml(ly)}</span>` : '';
            return `<div class="family-row">${sx}${link}${years}</div>`;
        };
        const _sortByBirth = arr => arr.slice().sort((a, b) => {
            const ay = ((typeof PEOPLE !== 'undefined' && PEOPLE[a]) || {}).birth_year || '9999';
            const by_ = ((typeof PEOPLE !== 'undefined' && PEOPLE[b]) || {}).birth_year || '9999';
            return ay < by_ ? -1 : ay > by_ ? 1 : 0;
        });

        let _parHtml = '',
            _sibHtml = '',
            _spChHtml = '';

        const _parentRow = px => {
            const p = (typeof PEOPLE !== 'undefined') && PEOPLE[px];
            const name = p ? escHtml(p.name || '?') : '?';
            const ly = _ly(p);
            const sx = _sx(p);
            const pxQ = JSON.stringify(px).replace(/"/g, '&quot;');
            const link = `<span class="family-link" onclick="setState({focusXref:${pxQ},panelXref:${pxQ},panelOpen:true})">${name}</span>`;
            const years = ly ? `<span class="family-years">${escHtml(ly)}</span>` : '';
            const actions = `<span class="family-parent-actions">` +
                `<button class="family-parent-btn" title="Change parent" onclick="openChangeParentModal(${xrefQ},${pxQ})">\u270f</button>` +
                `<button class="family-parent-btn del" title="Remove parent" onclick="removeParent(${xrefQ},${pxQ})">\u2715</button>` +
                `</span>`;
            return `<div class="family-row">${sx}${link}${years}${actions}</div>`;
        };

        const [fa, mo] = (typeof PARENTS !== 'undefined' && PARENTS[xref]) || [null, null];
        if (fa || mo) {
            _parHtml += '<div class="family-sub"><span class="family-sub-heading">Parents</span>';
            if (fa) _parHtml += _parentRow(fa);
            if (mo) _parHtml += _parentRow(mo);
            _parHtml += '</div>';
        }

        const sibs = _sortByBirth(((typeof RELATIVES !== 'undefined' && RELATIVES[xref]) || {}).siblings || []);
        if (sibs.length) {
            _sibHtml += '<div class="family-sub"><span class="family-sub-heading">Siblings</span>';
            for (const sx of sibs) _sibHtml += _pr(sx);
            _sibHtml += '</div>';
        }

        const halfSibGroups = ((typeof RELATIVES !== 'undefined' && RELATIVES[xref]) || {}).half_siblings || [];
        if (halfSibGroups.length) {
            _sibHtml += '<div class="family-sub"><span class="family-sub-heading">Half-siblings</span>';
            for (const grp of halfSibGroups) {
                const sp = (typeof PEOPLE !== 'undefined') && PEOPLE[grp.shared_parent];
                const sharedName = sp ? escHtml(sp.name || '?') : '?';
                const sharedQ = JSON.stringify(grp.shared_parent).replace(/"/g, '&quot;');
                const sharedLink = `<span class="family-link" onclick="setState({focusXref:${sharedQ},panelXref:${sharedQ},panelOpen:true})">${sharedName}</span>`;
                const op = grp.other_parent ? ((typeof PEOPLE !== 'undefined') && PEOPLE[grp.other_parent]) : null;
                const otherName = op ? escHtml(op.name || '?') : '?';
                const otherLink = grp.other_parent ?
                    `<span class="family-link" onclick="setState({focusXref:${JSON.stringify(grp.other_parent).replace(/"/g, '&quot;')},panelXref:${JSON.stringify(grp.other_parent).replace(/"/g, '&quot;')},panelOpen:true})">${otherName}</span>` :
                    `<span class="family-unknown">unknown</span>`;
                _sibHtml += `<div class="family-halfsib-group">`;
                _sibHtml += `<div class="family-halfsib-label">${sharedLink} &amp; ${otherLink}</div>`;
                _sibHtml += '<div class="family-children">';
                _sortByBirth(grp.half_sibs).forEach(cx => { _sibHtml += _pr(cx); });
                _sibHtml += '</div></div>';
            }
            _sibHtml += '</div>';
        }

        const marrEvts = (data.events || []).filter(e => e.tag === 'MARR');
        const allCh = (typeof CHILDREN !== 'undefined' && CHILDREN[xref]) || [];
        if (marrEvts.length || allCh.length) {
            _spChHtml += '<div class="family-sub"><span class="family-sub-heading">Spouses &amp; Children</span>';
            const accounted = new Set();
            for (const marr of marrEvts) {
                const spXref = marr.spouse_xref;
                if (spXref) {
                    _spChHtml += _pr(spXref);
                    const shared = _sortByBirth(allCh.filter(cx => {
                        const [cfa, cmo] = (typeof PARENTS !== 'undefined' && PARENTS[cx]) || [null, null];
                        return cfa === spXref || cmo === spXref;
                    }));
                    if (shared.length) {
                        _spChHtml += '<div class="family-children">';
                        shared.forEach(cx => { accounted.add(cx);
                            _spChHtml += _pr(cx); });
                        _spChHtml += '</div>';
                    }
                }
            }
            const unaccounted = _sortByBirth(allCh.filter(cx => !accounted.has(cx)));
            if (unaccounted.length) {
                _spChHtml += '<div class="family-children">';
                unaccounted.forEach(cx => { _spChHtml += _pr(cx); });
                _spChHtml += '</div>';
            }
            _spChHtml += '</div>';
        }

        const _addBtns = `<div class="family-add-btns">
      <button class="family-add-btn" onclick="openAddPersonModal(${xrefQ},'parent_of')">+ Parent</button>
      <button class="family-add-btn" onclick="openAddPersonModal(${xrefQ},'sibling_of')">+ Sibling</button>
      <button class="family-add-btn" onclick="openAddPersonModal(${xrefQ},'spouse_of')">+ Spouse</button>
      <button class="family-add-btn" onclick="openAddPersonModal(${xrefQ},'child_of')">+ Child</button>
    </div>`;

        const _hasFamily = _parHtml || _sibHtml || _spChHtml;
        const _arr = _familyOpen ? '\u25bc' : '\u25b6';
        const _toggleHtml = `<button class="family-toggle-btn" onclick="_toggleFamily()" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:11px;text-transform:uppercase;letter-spacing:0.08em;padding:0 0 10px 0">Family ${_arr}</button>`;
        const _subStyle = _familyOpen ? '' : ' style="display:none"';
        const _wrapSub = (html) => html ? html.replace(/<div class="family-sub"/g, `<div class="family-sub"${_subStyle}`) : '';
        const _addBtnsWrapped = _familyOpen || !_hasFamily ? _addBtns : `<div${_subStyle}>${_addBtns}</div>`;
        familyDiv.innerHTML = _toggleHtml + _wrapSub(_parHtml) + _wrapSub(_sibHtml) + _wrapSub(_spChHtml) + _addBtnsWrapped;
        familyDiv.className = 'has-content';
    }

    // ── Sources (person-level) ──────────────────────────────────────────
    const sourcesDiv = document.getElementById('detail-sources');
    if (sourcesDiv) {
        const srcs = data.sources || [];
        const xrefQ = escHtml(JSON.stringify(xref));
        const bookIconSvg =
            `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ` +
            `stroke-linecap="round" stroke-linejoin="round">` +
            `<path d="M2 3.5A1.5 1.5 0 013.5 2h9A1.5 1.5 0 0114 3.5v9a1.5 1.5 0 01-1.5 1.5h-9A1.5 1.5 0 012 12.5v-9z"/>` +
            `<path d="M5 2v12M5 6h4"/>` +
            `</svg>`;
        const _srcTitleHtml = s => s.url ?
            `<a href="${escHtml(s.url)}" target="_blank" rel="noopener">${escHtml(s.title)}</a>` :
            escHtml(s.title);
        const manageBtn = `<button class="sources-manage-btn" onclick="openIndiSourcesModal(${xrefQ})">Manage</button>`;

        if (srcs.length) {
            const count = srcs.length;
            const cards = srcs.map(s =>
                `<div class="source-card">` +
                `<div class="source-card-icon">${bookIconSvg}</div>` +
                `<div class="source-card-body"><div class="source-card-title">${_srcTitleHtml(s)}</div></div>` +
                `<div class="source-card-actions">` +
                `<button class="source-card-action" title="Edit" onclick="openIndiSourcesModal(${xrefQ})">✎</button>` +
                `</div>` +
                `</div>`
            ).join('');
            sourcesDiv.className = 'sources-collapsed';
            sourcesDiv.innerHTML =
                `<div class="sources-section-header">` +
                `<button class="sources-section-title sources-toggle" onclick="_toggleSourcesSection(this)" aria-expanded="false">` +
                `<span class="sources-toggle-arrow">▶</span>` +
                `Sources<span class="sources-count-pill">${count}</span>` +
                `</button>` +
                manageBtn +
                `</div>` +
                `<div class="sources-cards">${cards}</div>`;
        } else {
            sourcesDiv.className = '';
            sourcesDiv.innerHTML =
                `<div class="sources-section-header">` +
                `<div class="sources-section-title">Sources</div>` +
                manageBtn +
                `</div>` +
                `<div class="sources-empty">` +
                `<div class="sources-empty-text">No person-level sources recorded</div>` +
                `<button class="sources-add-btn" onclick="openIndiSourcesModal(${xrefQ})">+ Add source</button>` +
                `</div>`;
        }
    }

    // ── Delete person button ──────────────────────────────────────────────────
    const footerDiv = document.getElementById('detail-footer');
    if (footerDiv) {
        footerDiv.innerHTML =
            `<button class="delete-person-btn" onclick="deletePerson(${xrefQ})">Delete Person</button>`;
    }

    _panelEl.classList.add('panel-open');
}

// ── Init ──────────────────────────────────────────────────────────────────

async function convertEventTag(xref, eventIdx, fromTag, toTag) {
    if (!confirm(`Convert this Birth to a Baptism? This will change the event type in the GEDCOM file.`)) return;
    try {
        const resp = await apiConvertEvent(xref, eventIdx, fromTag, toTag);
        if (resp && resp.people) {
            for (const [k, v] of Object.entries(resp.people)) PEOPLE[k] = v;
        }
        renderPanel();
    } catch (e) {
        alert('Conversion failed: ' + e);
    }
}

function initPanel(panelEl) {
    _panelEl = panelEl;
    onStateChange(function(state) {
        renderPanel();
    });
}

// ── Exports ───────────────────────────────────────────────────────────────

if (typeof module !== 'undefined') {
    module.exports = {
        initPanel,
        renderPanel,
        fmtDate,
        fmtPlace,
        fmtAge,
        buildProse,
        dotColor,
        collapseResidences,
        toggleResiExpand,
        buildSourceBadgeHtml,
        buildNoteSourceBadgeHtml,
        _handleGodparentClick,
        _buildGodparentPillsHtml,
        convertEventTag,
    };
}