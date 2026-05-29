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

function _renderRelationshipPath(path) {
    const body = document.getElementById('relpath-modal-body');
    if (!body) return;
    body.innerHTML = '';
    // Arrows point down on the focus person's leg (them → common ancestor) and up
    // on the viewer's leg (common ancestor → you); the MRCA row begins the up leg.
    let reachedMrca = false;
    path.forEach((node) => {
        if (node.isMrca) reachedMrca = true;
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
            arrow.textContent = reachedMrca ? '↑' : '↓';
            const rel = document.createElement('span');
            rel.textContent = node.relToNext;
            step.appendChild(arrow);
            step.appendChild(rel);
            body.appendChild(step);
        }
    });
}

function showRelationshipPathModal(path, label) {
    if (!path || !path.length) return;
    const overlay = document.getElementById('relpath-modal-overlay');
    const title = document.getElementById('relpath-modal-title');
    if (title) title.textContent = label ? `Relationship — ${label}` : 'Relationship';
    _renderRelationshipPath(path);
    if (overlay) overlay.classList.add('open');
}

function closeRelationshipPathModal() {
    const overlay = document.getElementById('relpath-modal-overlay');
    if (overlay) overlay.classList.remove('open');
}

// Escape closes the modal when it's open (matches event/note modal behavior).
if (typeof document !== 'undefined') {
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;
        const o = document.getElementById('relpath-modal-overlay');
        if (o && o.classList.contains('open')) closeRelationshipPathModal();
    });
}
