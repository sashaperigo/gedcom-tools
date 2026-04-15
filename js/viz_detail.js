// Detail panel, event formatting, and pure utility helpers.

// ---------------------------------------------------------------------------
// HTML utilities
// ---------------------------------------------------------------------------

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function linkify(s) {
  // Match URLs in the raw string before HTML-escaping, so & in query strings isn't truncated
  const URL_RE = /https?:\/\/\S+/g;
  let result = '', last = 0, m;
  while ((m = URL_RE.exec(s)) !== null) {
    result += escHtml(s.slice(last, m.index));
    const rawUrl = m[0].replace(/[.,;:!?)]+$/, ''); // strip trailing punctuation
    const href   = rawUrl.replace(/&amp;/g, '&');   // decode any HTML entities in URL
    result += `<a href="${escHtml(href)}" target="_blank" rel="noopener">${escHtml(rawUrl)}</a>`;
    last = m.index + rawUrl.length;
  }
  result += escHtml(s.slice(last));
  return result;
}

// ---------------------------------------------------------------------------
// Date / place formatting
// ---------------------------------------------------------------------------

const _MONTH_ABBR = {
  JAN:'January', FEB:'February', MAR:'March',    APR:'April',
  MAY:'May',     JUN:'June',     JUL:'July',     AUG:'August',
  SEP:'September',OCT:'October', NOV:'November', DEC:'December'
};

function fmtDate(raw) {
  if (!raw) return '';
  const s = raw.trim().toUpperCase();
  let prefix = '', rest = s;
  if      (s.startsWith('ABT ')) { prefix = 'around ';  rest = s.slice(4); }
  else if (s.startsWith('BEF ')) { prefix = 'before ';  rest = s.slice(4); }
  else if (s.startsWith('AFT ')) { prefix = 'after ';   rest = s.slice(4); }
  else if (s.startsWith('CAL ') || s.startsWith('EST ')) { prefix = 'around '; rest = s.slice(4); }
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
    // City, [County], State, USA → City, State
    const city  = parts[0];
    const state = parts.length >= 3 ? parts[parts.length - 2] : '';
    if (!state) return city;
    const stateOut = /^District of Columbia$/i.test(state) ? 'D.C.' : state;
    return city + ', ' + stateOut;
  }
  // Non-US: City, Country (first + last, skipping intermediate parts)
  return parts.length === 2 ? parts.join(', ') : parts[0] + ', ' + last;
}

function fmtAge(raw) {
  if (!raw) return '';
  const s = raw.trim();
  const uc = s.toUpperCase().replace(/^[<>]/, '');
  if (uc === 'INFANT')    return 'in infancy';
  if (uc === 'STILLBORN') return 'stillborn';
  if (uc === 'CHILD')     return 'in childhood';
  const prefix = s.startsWith('>') ? 'over ' : s.startsWith('<') ? 'under ' : '';
  let r = s.replace(/^[<>]/, '');
  r = r.replace(/(\d+)y\b/g, (_, n) => `${n} year${n === '1' ? '' : 's'}`);
  r = r.replace(/(\d+)m\b/g, (_, n) => `${n} month${n === '1' ? '' : 's'}`);
  r = r.replace(/(\d+)d\b/g, (_, n) => `${n} day${n === '1' ? '' : 's'}`);
  return (prefix + r.trim().replace(/\s+/g, ' ')).trim();
}

// ---------------------------------------------------------------------------
// Per-event prose + dot colour
// ---------------------------------------------------------------------------

const EVENT_LABELS = {
  BIRT:'Birth', DEAT:'Death', BURI:'Burial', RESI:'Residence',
  OCCU:'Occupation', IMMI:'Immigration', NATU:'Naturalization',
  ADOP:'Adoption', EDUC:'Education', RETI:'Retirement',
  TITL:'Title', CHR:'Christening', BAPM:'Baptism',
  CONF:'Confirmation', NATI:'Nationality', RELI:'Religion',
  DIV:'Divorce', FACT:'Fact', MARR:'Marriage',
  PROB:'Probate', ARRV:'Arrival', DEPA:'Departure',
};

function buildProse(evt) {
  const date  = fmtDate(evt.date);
  const place = evt.place || '';
  const short = fmtPlace(place);
  const type  = evt.type || '';
  const addr  = evt.addr || '';
  const meta  = () => [addr, place, date].filter(Boolean).join(' \u00b7 ');
  switch (evt.tag) {
    case 'BIRT': return { prose: short ? `Born in ${short}` : (date ? `Born ${date}` : 'Birth'),          meta: meta() };
    case 'DEAT': {
      const cause = evt.cause ? `of ${evt.cause}` : '';
      const age   = evt.age  || '';
      if (cause && short) return { prose: `Died ${cause} in ${short}`, meta: meta() };
      if (cause)          return { prose: `Died ${cause}`,             meta: meta() };
      if (short)          return { prose: `Died in ${short}`,          meta: meta() };
      if (!date && age) {
        const ageUC = age.toUpperCase().replace(/^[<>]/, '');
        if (ageUC === 'STILLBORN') return { prose: 'Stillborn',                   meta: meta() };
        return { prose: `Died at ${fmtAge(age)}`, meta: meta() };
      }
      return { prose: date ? `Died ${date}` : 'Death', meta: meta() };
    }
    case 'BURI': return { prose: short ? `Buried in ${short}` : (date ? `Buried ${date}` : 'Burial'),    meta: meta() };
    case 'RESI': return { prose: short ? `Lived in ${short}` : (date ? `Lived ${date}` : 'Residence'),   meta: meta() };
    case 'OCCU': {
      const jobTitle = evt.inline_val || '';
      return { prose: jobTitle ? `Worked as ${jobTitle}` : (short ? `Worked in ${short}` : 'Occupation'), meta: meta() };
    }
    case 'IMMI': return { prose: short ? `Immigrated to ${short}` : (date ? `Immigrated ${date}` : 'Immigration'), meta: meta() };
    case 'NATU': return { prose: short ? `Naturalized in ${short}` : (date ? `Naturalized ${date}` : 'Naturalization'), meta: meta() };
    case 'ADOP': return { prose: date ? `Adopted ${date}` : 'Adoption', meta: short };
    case 'EDUC': return { prose: 'Education', meta: [type, place, date].filter(Boolean).join(' \u00b7 ') };
    case 'RETI': return { prose: date ? `Retired ${date}` : 'Retirement', meta: short };
    case 'TITL': return { prose: type ? `Held title: ${type}` : 'Title', meta: date };
    case 'CHR':  return { prose: short ? `Christened in ${short}` : (date ? `Christened ${date}` : 'Christening'), meta: meta() };
    case 'BAPM': return { prose: short ? `Baptized in ${short}` : (date ? `Baptized ${date}` : 'Baptism'), meta: meta() };
    case 'CONF': return { prose: short ? `Confirmed in ${short}` : (date ? `Confirmed ${date}` : 'Confirmation'), meta: meta() };
    case 'NATI': return { prose: type ? `Nationality: ${type}` : (short ? `Nationality: ${short}` : 'Nationality'), meta: date };
    case 'RELI': return { prose: 'Religion', meta: type || date };
    case 'DIV':  return { prose: date ? `Divorced ${date}` : 'Divorce', meta: short };
    case 'FACT': {
      if (type && type.toUpperCase() === 'AKA')
        return { prose: `Also known as: ${evt.note || ''}`, meta: date };
      return { prose: type || short || 'Fact', meta: date };
    }
    case 'MARR': {
      const who = evt.spouse || '';
      const prose = who ? `Married ${who}` : 'Marriage';
      return { prose, meta: meta() };
    }
    case 'PROB': return { prose: short ? `Probate in ${short}` : (date ? `Probate ${date}` : 'Probate'), meta: meta() };
    case 'ARRV': return { prose: short ? `Arrived in ${short}` : (date ? `Arrived ${date}` : 'Arrival'),     meta: meta() };
    case 'DEPA': return { prose: short ? `Departed from ${short}` : (date ? `Departed ${date}` : 'Departure'), meta: meta() };
    default: {
      if (type === 'Arrival')
        return { prose: short ? `Arrived in ${short}` : (date ? `Arrived ${date}` : 'Arrival'), meta: meta() };
      if (type === 'Departure')
        return { prose: short ? `Departed from ${short}` : (date ? `Departed ${date}` : 'Departure'), meta: meta() };
      if (type === 'Church') {
        return { prose: evt.addr || short || 'Church', meta: meta() };
      }
      return {
        prose: type || (short ? short : (EVENT_LABELS[evt.tag] || evt.tag)),
        meta:  meta()
      };
    }
  }
}

function dotColor(evt) {
  if (evt.type === 'Name Change') return '#f97316';
  if (evt.tag === 'MARR') return '#e879f9';
  switch (evt.tag) {
    case 'BIRT': case 'DEAT':              return '#f1f5f9';
    case 'BURI':                           return '#94a3b8';
    case 'RESI':                           return '#38bdf8';
    case 'OCCU': case 'RETI':             return '#fbbf24';
    case 'IMMI': case 'NATU':             return '#34d399';
    case 'CHR':  case 'BAPM': case 'CONF': case 'RELI': return '#2dd4bf';
    case 'EDUC':                           return '#a78bfa';
    default:                               return '#64748b';
  }
}

// ---------------------------------------------------------------------------
// Residence collapsing
// ---------------------------------------------------------------------------

const _YR_RE = /\b(\d{4})\b/;
function sortEvents(events) { return events; }  // pre-sorted by Python

function collapseResidences(events) {
  const result = [];
  let i = 0;
  while (i < events.length) {
    const evt = events[i];
    if (evt.tag !== 'RESI') { result.push(evt); i++; continue; }
    const short = fmtPlace(evt.place || '');
    // Collect consecutive RESI events with the same short place name
    const run = [evt];
    let j = i + 1;
    while (j < events.length && events[j].tag === 'RESI' &&
           fmtPlace(events[j].place || '') === short) {
      run.push(events[j]);
      j++;
    }
    if (run.length < 2) { result.push(evt); i = j; continue; }
    const years = run.map(e => (_YR_RE.exec(e.date || '') || [,null])[1]).filter(Boolean);
    const yearRange = years.length >= 2 ? `${years[0]}\u2013${years[years.length - 1]}` : (years[0] || '');
    const notes = run.flatMap(e => {
      if (!e.note) return [];
      const yr = (_YR_RE.exec(e.date || '') || [,null])[1];
      return [yr ? `${yr}: ${e.note}` : e.note];
    });
    result.push({ ...evt, _yearRange: yearRange, note: notes.length ? notes.join('\n') : null });
    i = j;
  }
  return result;
}

// ---------------------------------------------------------------------------
// Detail panel (DOM-dependent — not exported for tests)
// ---------------------------------------------------------------------------

let _openDetailKey = null;

function showDetail(xref) {
  if (_openDetailKey === xref) {
    return;  // already open for this person
  }
  const panelWasOpen = _openDetailKey !== null;
  const data = PEOPLE[xref] || (() => {
    const p = ALL_PEOPLE.find(x => x.id === xref);
    return p ? { name: p.name, birth_year: p.birth_year, death_year: p.death_year,
                 sex: null, events: [], notes: [], sources: [] } : null;
  })();
  if (!data) return;
  const panel = document.getElementById('detail-panel');

  try {
  // Accent color by sex
  const accent = {'M':'#3b82f6','F':'#a855f7'}[data.sex] || '#475569';
  document.getElementById('detail-accent-bar').style.background = accent;

  // Name + sex symbol + edit button
  const sexSym = {'M':'\u2642','F':'\u2640'}[data.sex] || '';
  const xrefQN  = JSON.stringify(xref).replace(/"/g, '&quot;');
  document.getElementById('detail-name').innerHTML =
    escHtml(data.name) +
    (sexSym ? `<span class="sex-sym">${sexSym}</span>` : '') +
    `<button class="name-edit-btn" title="Edit name" onclick="editName(${xrefQN})">\u270f</button>`;

  // Lifespan bar
  const by = data.birth_year ? parseInt(data.birth_year) : null;
  const dy = data.death_year ? parseInt(data.death_year) : null;
  const lifespanRow = document.getElementById('detail-lifespan-row');
  if (by) {
    const span = (dy && dy > by) ? dy - by : null;
    const fillStyle = dy
      ? `background: linear-gradient(90deg, ${accent}, #6366f1); width: 100%;`
      : `background: linear-gradient(90deg, ${accent}, transparent); width: 100%;`;
    lifespanRow.innerHTML =
      `<span class="lifespan-year">${by}</span>` +
      `<div class="lifespan-bar-track"><div class="lifespan-bar-fill" style="${fillStyle}"></div></div>` +
      `<span class="lifespan-year">${dy || '\u2014'}</span>` +
      (span ? `<span class="lifespan-age">~${span} years</span>` : '');
  } else {
    lifespanRow.innerHTML = '';
  }

  // AKA aliases — shown under the name, not in the timeline
  const akaDiv = document.getElementById('detail-aka');
  {
    const xrefQA = JSON.stringify(xref).replace(/"/g, '&quot;');
    const akaEvents = (data.events || []).map((e, i) => ({...e, _origIdx: i}))
      .filter(e => e._name_record && e.note);
    const addAkaBtn = `<button class="aka-btn" title="Add secondary name" style="font-size:11px;color:#475569;margin-left:4px" onclick="openAliasModal(${xrefQA},null,'','AKA',true)">&#43; alias</button>`;
    if (akaEvents.length) {
      const entries = akaEvents.map(e => {
        const isNameRec = e._name_record === true;
        const editBtn = isNameRec
          ? `<button class="aka-btn" title="Edit name" onclick="openAliasModal(${xrefQA},${e._name_occurrence},${JSON.stringify(e.note).replace(/"/g,'&quot;')},${JSON.stringify(e.type || 'AKA').replace(/"/g,'&quot;')},true)">\u270f</button>`
          : (e.event_idx !== null && e.event_idx !== undefined
            ? `<button class="aka-btn" title="Edit alias" onclick="editEvent(${xrefQA},${e.event_idx},'FACT')">\u270f</button>`
            : '');
        const delBtn = `<button class="aka-btn del" title="Delete name" onclick="deleteAlias(${xrefQA},PEOPLE[${xrefQA}].events[${e._origIdx}])">\u2715</button>`;
        const typeLabel = (e.type && e.type.toUpperCase() !== 'AKA') ? `<span style="font-size:10px;color:#94a3b8;margin-right:2px">${escHtml(e.type)}:</span>` : '';
        return `<span class="aka-entry">${typeLabel}<span style="font-style:italic">${escHtml(e.note)}</span>${editBtn}${delBtn}</span>`;
      }).join(' \xb7 ');
      akaDiv.innerHTML = entries + addAkaBtn;
    } else {
      akaDiv.innerHTML = addAkaBtn;
    }
  }

  // Notes — collapsible
  const notesDiv = document.getElementById('detail-notes');
  const notes = data.notes || [];
  if (notes.length) {
    const count = notes.length;
    const label = count === 1 ? '1 Note' : `${count} Notes`;
    const xrefQ = JSON.stringify(xref).replace(/"/g, '&quot;');
    const cards = notes.map((n, i) => {
      return `<div class="note-card-wrap">` +
        `<div class="note-card" style="border-left-color:${accent}">${linkify(n)}</div>` +
        `<div class="note-actions">` +
        `<button class="note-action-btn" title="Edit note" onclick="editNote(${xrefQ},${i})">\u270f</button>` +
        `<button class="note-action-btn" title="Delete note" onclick="deleteNote(${xrefQ},${i})">\u2715</button>` +
        `</div></div>`;
    }).join('');
    notesDiv.innerHTML =
      `<div class="notes-header">` +
      `<button class="notes-toggle open" onclick="this.closest('.notes-header').nextElementSibling.style.display=` +
      `this.classList.toggle('open')?'block':'none'">` +
      `<span class="notes-toggle-arrow">&#9658;</span>${escHtml(label)}</button>` +
      `<button class="note-add-btn" title="Add note" onclick="addNote(${xrefQ})">&#43; Add Note</button>` +
      `</div>` +
      `<div class="notes-body">${cards}</div>`;
  } else {
    const xrefQ = JSON.stringify(xref).replace(/"/g, '&quot;');
    notesDiv.innerHTML =
      `<button class="note-add-btn" onclick="addNote(${xrefQ})">&#43; Add Note</button>`;
  }

  // Timeline events (AKA excluded — shown above; NATI shown in facts; undated RESI shown below)
  const evtDiv  = document.getElementById('detail-events');
  const alsoLivedDiv = document.getElementById('detail-also-lived');
  const factsDiv = document.getElementById('detail-facts');

  // Nationalities — always shown as pills in facts section, never in the timeline
  const natiEvents = (data.events || []).map((e, i) => ({...e, _origIdx: i}))
    .filter(e => e.tag === 'NATI');
  {
    const xrefQ = JSON.stringify(xref).replace(/"/g, '&quot;');
    const addNatiBtn = `<button class="add-event-btn" onclick="addEvent(${xrefQ},'NATI')">&#43; Add nationality</button>`;
    if (natiEvents.length) {
      const pills = natiEvents.map(e => {
        const _pillYr = e.date ? ((_YR_RE.exec(e.date) || [,null])[1]) : null;
        const dateStr = _pillYr ? `<span class="pill-date">${_pillYr}</span>` : '';
        const editBtn = e.event_idx !== null && e.event_idx !== undefined
          ? `<button class="facts-pill-btn" title="Edit" onclick="editEvent(${xrefQ},${e.event_idx},'NATI')">\u270f</button>`
          : '';
        const delBtn = `<button class="facts-pill-btn del" title="Delete" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${e._origIdx}])">\u2715</button>`;
        const actions = `<span class="facts-pill-actions">${editBtn}${delBtn}</span>`;
        return `<span class="facts-pill-wrap"><span class="facts-pill">${escHtml(e.inline_val || '')}${dateStr}</span>${actions}</span>`;
      }).join('');
      factsDiv.innerHTML = `<span class="facts-heading">Nationality</span><div class="facts-pills">${pills}${addNatiBtn}</div>`;
      factsDiv.className = 'has-content';
    } else {
      factsDiv.innerHTML = addNatiBtn;
      factsDiv.className = 'has-content';
    }
  }

  const allVisible = (data.events || []).map((e, i) => ({...e, _origIdx: i})).filter(e =>
    e.tag !== 'NATI' &&
    (e.tag === 'MARR' || e.date || e.place || e.note || e.type || e.cause || e.addr) &&
    !e._name_record
  );
  const _keepInTimeline = e =>
    e.tag !== 'RELI' && (
    e.date ||
    e.tag === 'BIRT' || e.tag === 'DEAT' || e.tag === 'BURI' || e.tag === 'PROB' || e.tag === 'MARR' ||
    e.type === 'Arrival' || e.type === 'Departure');
  const undatedFactoids = allVisible.filter(e => !_keepInTimeline(e));
  const visible = allVisible.filter(_keepInTimeline);
  const sorted  = collapseResidences(sortEvents(visible));

  const _addEvtBtn = `<button class="add-event-btn" onclick="addEvent(${JSON.stringify(xref).replace(/"/g,'&quot;')})">&#43; Add event</button>`;
  if (!sorted.length) { evtDiv.innerHTML = _addEvtBtn; }
  else {
    let html = '', lastSection = '';
    for (const evt of sorted) {
      let section = 'Life';
      const evtYear = evt.date ? ((_YR_RE.exec(evt.date) || [,0])[1] | 0) : null;
      const _typ = (evt.type || '').toLowerCase();
      const _isDeathRelated = evt.tag === 'DEAT' || evt.tag === 'BURI' || evt.tag === 'PROB' ||
        (evt.tag === 'EVEN' && (_typ.includes('death') || _typ.includes('obituar') || _typ.includes('avis de d') || _typ.includes('probate')));
      if (evt.tag === 'BIRT' || (evtYear && by && evtYear <= by + 18)) section = 'Early Life';
      else if (_isDeathRelated) section = 'Later Life';

      if (section !== lastSection) {
        html += `<span class="timeline-section-label">${escHtml(section)}</span>`;
        lastSection = section;
      }

      const { prose, meta } = buildProse(evt);
      const color   = dotColor(evt);
      const noteInl = evt.note
        ? evt.note.split('\n').map(l => `<div class="evt-note-inline">${escHtml(l)}</div>`).join('') : '';

      if (evt.tag === 'MARR') {
        const evtYear2 = evtYear;
        const yearLabel = evtYear2 ? `<div class="marr-year">${evtYear2}</div>` : '';
        const spXref = evt.spouse_xref;
        const spClickable = spXref && PARENTS[spXref];
        const spXrefAttr = spClickable ? escHtml(spXref) : '';
        const marrClick = spClickable
          ? ` style="cursor:pointer" data-spouse-xref="${spXrefAttr}" onclick="changeRoot(this.dataset.spouseXref)"` : '';
        const proseHtml = spClickable
          ? `<div class="marr-prose marr-link">${escHtml(prose)}</div>`
          : `<div class="marr-prose">${escHtml(prose)}</div>`;
        const xrefQ = JSON.stringify(xref).replace(/"/g, '&quot;');
        const marrEditBtn = evt.fam_xref
          ? `<button class="marr-edit-btn" title="Edit marriage" onclick="event.stopPropagation();editEvent(${xrefQ},null,'MARR',${JSON.stringify(evt.fam_xref).replace(/"/g,'&quot;')},${evt.marr_idx ?? 0})">\u270f</button>`
          : '';
        html +=
          `<div class="marr-card"${marrClick}>` +
          marrEditBtn +
          yearLabel +
          proseHtml +
          (meta && meta !== String(evtYear2) ? `<div class="marr-meta">${escHtml(meta)}</div>` : '') +
          noteInl +
          `</div>`;
        continue;
      }

      const isAnch  = evt.tag === 'BIRT' || evt.tag === 'DEAT';
      const dotCls  = isAnch ? 'evt-dot dot-anchor' : 'evt-dot';
      const yearStr = evt._yearRange
        ? `<span class="evt-year">${escHtml(evt._yearRange)}</span>`
        : (evtYear ? `<span class="evt-year">${evtYear}</span>` : '');
      const xrefQ   = JSON.stringify(xref).replace(/"/g, '&quot;');
      const delBtn  = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">\u2715</button>`;
      const editBtn = evt.event_idx !== null && evt.event_idx !== undefined
        ? `<button class="evt-edit-btn" title="Edit event" onclick="editEvent(${xrefQ},${evt.event_idx},${JSON.stringify(evt.tag).replace(/"/g,'&quot;')})">\u270f</button>`
        : '';
      html +=
        `<div class="evt-entry">` +
        `<div class="${dotCls}" style="background:${color}"></div>` +
        `<div class="evt-prose">${yearStr}${escHtml(prose)}</div>` +
        (meta && meta !== String(evtYear) ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
        noteInl +
        editBtn +
        delBtn +
        `</div>`;
    }
    html += _addEvtBtn;
    evtDiv.innerHTML = html;
  }

  // Undated bottom sections — rendered as timeline-style rows, no spine
  function undatedRows(evts) {
    return evts.map(evt => {
      const { prose, meta } = buildProse(evt);
      const color   = dotColor(evt);
      const noteInl = evt.note ? evt.note.split('\n').map(l => `<div class="evt-note-inline">${escHtml(l)}</div>`).join('') : '';
      const xrefQ   = JSON.stringify(xref).replace(/"/g, '&quot;');
      const delBtn  = `<button class="fact-del" title="Delete fact" onclick="deleteFact(${xrefQ},PEOPLE[${xrefQ}].events[${evt._origIdx}])">\u2715</button>`;
      const editBtn = evt.event_idx !== null && evt.event_idx !== undefined
        ? `<button class="evt-edit-btn" title="Edit event" onclick="editEvent(${xrefQ},${evt.event_idx},${JSON.stringify(evt.tag).replace(/"/g,'&quot;')})">\u270f</button>`
        : '';
      return `<div class="evt-entry">` +
        `<div class="evt-dot" style="background:${color}"></div>` +
        `<div class="evt-prose">${escHtml(prose)}</div>` +
        (meta ? `<div class="evt-meta">${escHtml(meta)}</div>` : '') +
        noteInl +
        editBtn +
        delBtn +
        `</div>`;
    }).join('');
  }

  let bottomHtml = '';
  if (undatedFactoids.length) {
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
    if (otherFacts.length) {
      bottomHtml += `<span class="also-lived-heading">Facts</span>` + undatedRows(otherFacts);
    }
  }

  alsoLivedDiv.innerHTML = bottomHtml;
  alsoLivedDiv.className = bottomHtml ? 'has-content' : '';

  // ── Family section ────────────────────────────────────────
  const familyDiv = document.getElementById('detail-family');
  {
    const _ly = p => {
      if (!p) return '';
      const b = p.birth_year || '', d = p.death_year || '';
      return (b || d) ? `${b}\u2013${d}` : '';
    };
    const _sx = p => !p ? '' :
      p.sex === 'M' ? '<span class="family-sex-m">\u2022</span>' :
      p.sex === 'F' ? '<span class="family-sex-f">\u2022</span>' : '';
    const _pr = px => {
      const p = PEOPLE[px];
      const name = p ? escHtml(p.name || '?') : '?';
      const ly = _ly(p);
      const sx = _sx(p);
      const pxQ = JSON.stringify(px).replace(/"/g, '&quot;');
      const link = `<span class="family-link" onclick="changeRoot(${pxQ})">${name}</span>`;
      const years = ly ? `<span class="family-years">${escHtml(ly)}</span>` : '';
      return `<div class="family-row">${sx}${link}${years}</div>`;
    };
    const _sortByBirth = arr => arr.slice().sort((a, b) => {
      const ay = (PEOPLE[a] || {}).birth_year || '9999';
      const by_ = (PEOPLE[b] || {}).birth_year || '9999';
      return ay < by_ ? -1 : ay > by_ ? 1 : 0;
    });

    let fhtml = '';

    // Parents
    const [fa, mo] = PARENTS[xref] || [null, null];
    if (fa || mo) {
      fhtml += '<div class="family-sub"><span class="family-sub-heading">Parents</span>';
      if (fa) fhtml += _pr(fa);
      if (mo) fhtml += _pr(mo);
      fhtml += '</div>';
    }

    // Siblings (sorted by birth year) — only full siblings (same FAMC)
    const sibs = _sortByBirth((RELATIVES[xref] || {}).siblings || []);
    if (sibs.length) {
      fhtml += '<div class="family-sub"><span class="family-sub-heading">Siblings</span>';
      for (const sx of sibs) fhtml += _pr(sx);
      fhtml += '</div>';
    }

    // Half-siblings: pre-computed in Python and shipped in RELATIVES
    const halfSibGroups = (RELATIVES[xref] || {}).half_siblings || [];
    if (halfSibGroups.length) {
      fhtml += '<div class="family-sub"><span class="family-sub-heading">Half-siblings</span>';
      for (const grp of halfSibGroups) {
        const sp = PEOPLE[grp.shared_parent];
        const sharedName = sp ? escHtml(sp.name || '?') : '?';
        const sharedQ = JSON.stringify(grp.shared_parent).replace(/"/g, '&quot;');
        const sharedLink = `<span class="family-link" onclick="changeRoot(${sharedQ})">${sharedName}</span>`;
        const op = grp.other_parent ? PEOPLE[grp.other_parent] : null;
        const otherName = op ? escHtml(op.name || '?') : '?';
        const otherLink = grp.other_parent
          ? `<span class="family-link" onclick="changeRoot(${JSON.stringify(grp.other_parent).replace(/"/g, '&quot;')})">${otherName}</span>`
          : `<span class="family-unknown">unknown</span>`;
        fhtml += `<div class="family-halfsib-group">`;
        fhtml += `<div class="family-halfsib-label">${sharedLink} &amp; ${otherLink}</div>`;
        fhtml += '<div class="family-children">';
        _sortByBirth(grp.half_sibs).forEach(cx => { fhtml += _pr(cx); });
        fhtml += '</div></div>';
      }
      fhtml += '</div>';
    }

    // Spouses & Children
    const marrEvts = (data.events || []).filter(e => e.tag === 'MARR');
    const allCh = CHILDREN[xref] || [];
    if (marrEvts.length || allCh.length) {
      fhtml += '<div class="family-sub"><span class="family-sub-heading">Spouses &amp; Children</span>';
      const accounted = new Set();
      for (const marr of marrEvts) {
        const spXref = marr.spouse_xref;
        if (spXref) {
          fhtml += _pr(spXref);
          const shared = _sortByBirth(allCh.filter(cx => {
            const [cfa, cmo] = PARENTS[cx] || [null, null];
            return cfa === spXref || cmo === spXref;
          }));
          if (shared.length) {
            fhtml += '<div class="family-children">';
            shared.forEach(cx => { accounted.add(cx); fhtml += _pr(cx); });
            fhtml += '</div>';
          }
        }
      }
      // Children not tied to any listed spouse
      const unaccounted = _sortByBirth(allCh.filter(cx => !accounted.has(cx)));
      if (unaccounted.length) {
        fhtml += '<div class="family-children">';
        unaccounted.forEach(cx => { fhtml += _pr(cx); });
        fhtml += '</div>';
      }
      fhtml += '</div>';
    }

    familyDiv.innerHTML = fhtml;
    familyDiv.className = fhtml ? 'has-content' : '';
  }

  const sourcesDiv = document.getElementById('detail-sources');
  const srcs = (data.sources || []).slice().sort((a, b) => (a.title||'').localeCompare(b.title||''));
  const _srcHtml = s => s.url
    ? `<a href="${escHtml(s.url)}" target="_blank" rel="noopener" class="source-link">${escHtml(s.title)}</a>`
    : escHtml(s.title);
  sourcesDiv.innerHTML = srcs.length
    ? `<span class="sources-heading">Sources</span>` +
      (srcs.length === 1
        ? `<div class="source-item">${_srcHtml(srcs[0])}</div>`
        : `<ul class="source-list">${srcs.map(s => `<li class="source-item">${_srcHtml(s)}</li>`).join('')}</ul>`)
    : '';

  } catch (err) {
    console.error('[showDetail] error rendering', xref, err);
    return;
  }
  panel.classList.add('panel-open');
  _openDetailKey = xref;
  const vp = document.getElementById('viewport');
  vp.style.marginRight = '480px';
  document.getElementById('home-btn').style.right = (480 + 24) + 'px';
  if (!panelWasOpen) _animateFitAndCenter(220);
}

function closeDetail() {
  document.getElementById('detail-panel').classList.remove('panel-open');
  _openDetailKey = null;
  const vp = document.getElementById('viewport');
  vp.style.marginRight = '';
  document.getElementById('home-btn').style.right = '24px';
  _animateFitAndCenter(220);
}

// ---------------------------------------------------------------------------
// Node export (for tests)
// ---------------------------------------------------------------------------

if (typeof module !== 'undefined') {
  module.exports = {
    escHtml, linkify,
    fmtDate, fmtPlace, fmtAge,
    buildProse, dotColor,
    sortEvents, collapseResidences,
    EVENT_LABELS, _MONTH_ABBR,
  };
}
