// Relationship-path modal: renders the chain of people connecting the selected
// person (top) to the viewer / "You" (bottom). Given an ordered array from
// buildRelationshipPath(); name/year lookups via PEOPLE / _personName.

function _relpathLifespan(xref) {
    const p = (typeof PEOPLE !== 'undefined' && PEOPLE[xref]) || {};
    const by = p.birth_year, dy = p.death_year;
    if (by && dy) return `(${by}–${dy})`;
    if (by) return `(b. ${by})`;
    if (dy) return `(d. ${dy})`;
    return '';
}

// Glyph per edge kind. Intentionally direction-agnostic within a pair
// (spouse/ex-spouse share ⚭; godparent/godchild share ✝) — the adjacent
// gendered term ("ex-wife of", "godson of") carries direction/divorce.
const _RELPATH_GLYPH = {
  'descent-up': '↑',
  'descent-down': '↓',
  'spouse': '⚭',
  'ex-spouse': '⚭',
  'godparent': '✝',
  'godchild': '✝',
};

function _renderRelationshipPath(path) {
    const body = document.getElementById('relpath-modal-body');
    if (!body) return;
    body.innerHTML = '';
    path.forEach((node) => {
        const row = document.createElement('div');
        row.className = 'relpath-row';

        const link = document.createElement('span');
        link.className = node.isMrca ? 'relpath-person relpath-person-mrca' : 'relpath-person';
        link.textContent = (typeof _personName === 'function') ? _personName(node.xref) : node.xref;
        link.addEventListener('click', () => {
            closeRelationshipPathModal();
            if (typeof navigate === 'function') {
                navigate(node.xref);
            } else if (typeof setState === 'function') {
                setState({ focusXref: node.xref, panelOpen: true, panelXref: node.xref });
            }
        });
        row.appendChild(link);

        const years = _relpathLifespan(node.xref);
        if (years) {
            const y = document.createElement('span');
            y.className = 'relpath-years';
            y.textContent = years;
            row.appendChild(y);
        }

        if (node.isViewer) {
            const you = document.createElement('span');
            you.className = 'relpath-you';
            you.textContent = 'You';
            row.appendChild(you);
        }

        if (node.isMrca) {
            const tag = document.createElement('span');
            tag.className = 'relpath-mrca';
            tag.textContent = 'common ancestor';
            row.appendChild(tag);
        }
        body.appendChild(row);

        if (node.relToNext) {
            const step = document.createElement('div');
            step.className = 'relpath-step';
            const arrow = document.createElement('span');
            arrow.className = 'relpath-arrow';
            arrow.textContent = _RELPATH_GLYPH[node.edgeKind] || '↓';
            const rel = document.createElement('span');
            rel.textContent = node.relToNext;
            step.appendChild(arrow);
            step.appendChild(rel);
            body.appendChild(step);
        }
    });
}

let _relpathEntries = [];

function _renderRelationshipTabs(entries, activeIdx) {
    const existing = document.getElementById('relpath-tabs');
    if (existing) existing.remove();
    if (!entries || entries.length < 2) return;
    const body = document.getElementById('relpath-modal-body');
    if (!body) return;
    const bar = document.createElement('div');
    bar.id = 'relpath-tabs';
    bar.className = 'relpath-tabs';
    entries.forEach((e, i) => {
        const tab = document.createElement('button');
        tab.className = 'relpath-tab' + (i === activeIdx ? ' active' : '');
        tab.textContent = e.label;
        tab.addEventListener('click', () => _selectRelationshipTab(i));
        bar.appendChild(tab);
    });
    body.parentNode.insertBefore(bar, body);
}

function _selectRelationshipTab(i) {
    _renderRelationshipTabs(_relpathEntries, i);
    _renderRelationshipPath(_relpathEntries[i].path);
}

// entries: [{ kind, label, path }]; title: the displayed (possibly combined) label.
function showRelationshipPathModal(entries, title) {
    const renderable = (entries || []).filter(e => e.path && e.path.length);
    if (!renderable.length) return;
    const overlay = document.getElementById('relpath-modal-overlay');
    const titleEl = document.getElementById('relpath-modal-title');
    if (titleEl) titleEl.textContent = title ? `Relationship — ${title}` : 'Relationship';
    _relpathEntries = renderable;
    _renderRelationshipTabs(renderable, 0);
    _renderRelationshipPath(renderable[0].path);
    if (overlay) overlay.classList.add('open');
}

function closeRelationshipPathModal() {
    const overlay = document.getElementById('relpath-modal-overlay');
    if (overlay) overlay.classList.remove('open');
    const bar = document.getElementById('relpath-tabs');
    if (bar) bar.remove();
}

// Escape closes the modal when it's open (matches event/note modal behavior).
if (typeof document !== 'undefined') {
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        const o = document.getElementById('relpath-modal-overlay');
        if (o && o.classList.contains('open')) closeRelationshipPathModal();
    });
}
