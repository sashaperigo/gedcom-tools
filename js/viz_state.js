// Single state object with URL sync and re-render callback system.

let _state = {
  focusXref:     null,
  expandedNodes: new Set(),
  panelOpen:     false,
  panelXref:     null,
};

const _callbacks = [];

// ── helpers ───────────────────────────────────────────────────────────────

function _xrefFromUrl(search) {
  const params = new URLSearchParams(search);
  const person = params.get('person');
  if (person) return '@' + person + '@';
  return null;
}

function _pushHistory(focusXref) {
  if (typeof history === 'undefined') return;
  const clean = focusXref.replace(/@/g, '');
  history.pushState({ focusXref }, '', '?person=' + clean);
}

// ── public API ────────────────────────────────────────────────────────────

function initState(rootXref) {
  const fromUrl = _xrefFromUrl(
    typeof location !== 'undefined' ? location.search : ''
  );
  _state = {
    focusXref:     fromUrl || rootXref,
    expandedNodes: new Set(),
    panelOpen:     false,
    panelXref:     null,
  };

  // Register popstate listener (browser only)
  if (typeof addEventListener !== 'undefined') {
    addEventListener('popstate', function (event) {
      let newXref = null;
      if (event.state && event.state.focusXref) {
        newXref = event.state.focusXref;
      } else if (typeof location !== 'undefined') {
        newXref = _xrefFromUrl(location.search);
      }
      if (newXref) {
        // Update state directly without pushing to history
        _state = Object.assign({}, _state, { focusXref: newXref });
        _callbacks.forEach(cb => cb(_state));
      }
    });
  }
}

function setState(updates) {
  const prevFocusXref = _state.focusXref;
  _state = Object.assign({}, _state, updates);

  // Push to history only when focusXref actually changed
  if ('focusXref' in updates && updates.focusXref !== prevFocusXref) {
    _pushHistory(updates.focusXref);
  }

  _callbacks.forEach(cb => cb(_state));
}

function onStateChange(callback) {
  _callbacks.push(callback);
}

function getState() {
  return _state;
}

if (typeof module !== 'undefined') module.exports = { initState, setState, onStateChange, getState };
