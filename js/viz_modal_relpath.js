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
    path.forEach((node) => {
        const row = document.createElement('div');
        row.className = 'relpath-row';

        const link = document.createElement('span');
        link.className = 'relpath-person';
        const nm = (typeof _personName === 'function') ? _personName(node.xref) : node.xref;
        const span = _relpathLifespan(node.xref);
        let text = span ? `${nm} ${span}` : nm;
        if (node.isViewer) text += ' — You';
        link.textContent = text;
        link.addEventListener('click', () => {
            closeRelationshipPathModal();
            if (typeof navigate === 'function') {
                navigate(node.xref);
            } else if (typeof setState === 'function') {
                setState({ focusXref: node.xref, panelOpen: true, panelXref: node.xref });
            }
        });
        row.appendChild(link);

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
            step.textContent = `↑ ${node.relToNext}`;
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
