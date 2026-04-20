// Single state object with URL sync and re-render callback system.

let _state = {
  focusXref:     null,
  expandedNodes: new Set(),
  panelOpen:     false,
  panelXref:     null,
};

const _callbacks = [];

// ── helpers ───────────────────────────────────────────────────────────────

function _expandedToParam(expandedNodes) {
  if (!expandedNodes || expandedNodes.size === 0) return null;
  return Array.from(expandedNodes)
    .map(x => x.replace(/@/g, ''))
    .sort()
    .join(',');
}

function _expandedFromParam(search) {
  const params = new URLSearchParams(search);
  const raw = params.get('expanded');
  if (!raw) return new Set();
  return new Set(raw.split(',').filter(Boolean).map(x => '@' + x + '@'));
}

function _xrefFromUrl(search) {
  const params = new URLSearchParams(search);
  const person = params.get('person');
  if (person) return '@' + person + '@';
  return null;
}

function _buildUrl(focusXref, expandedNodes) {
  if (!focusXref) return '';
  const clean = focusXref.replace(/@/g, '');
  const expandedParam = _expandedToParam(expandedNodes);
  return expandedParam
    ? '?person=' + clean + '&expanded=' + expandedParam
    : '?person=' + clean;
}

function _pushHistory(focusXref, expandedNodes) {
  if (typeof history === 'undefined') return;
  history.pushState({ focusXref, expandedXrefs: _expandedToParam(expandedNodes) }, '', _buildUrl(focusXref, expandedNodes));
}

function _replaceHistory(focusXref, expandedNodes) {
  if (typeof history === 'undefined') return;
  history.replaceState({ focusXref, expandedXrefs: _expandedToParam(expandedNodes) }, '', _buildUrl(focusXref, expandedNodes));
}

// ── public API ────────────────────────────────────────────────────────────

function initState(rootXref) {
  const search = typeof location !== 'undefined' ? location.search : '';
  const fromUrl = _xrefFromUrl(search);
  _state = {
    focusXref:     fromUrl || rootXref,
    expandedNodes: _expandedFromParam(search),
    panelOpen:     false,
    panelXref:     null,
  };

  if (typeof addEventListener !== 'undefined') {
    addEventListener('popstate', function (event) {
      let newXref = null;
      if (event.state && event.state.focusXref) {
        newXref = event.state.focusXref;
      } else if (typeof location !== 'undefined') {
        newXref = _xrefFromUrl(location.search);
      }
      let newExpanded;
      if (event.state && event.state.expandedXrefs !== undefined) {
        newExpanded = event.state.expandedXrefs
          ? new Set(event.state.expandedXrefs.split(',').map(x => '@' + x + '@'))
          : new Set();
      } else if (typeof location !== 'undefined') {
        newExpanded = _expandedFromParam(location.search);
      } else {
        newExpanded = new Set();
      }
      if (newXref) {
        _state = Object.assign({}, _state, { focusXref: newXref, expandedNodes: newExpanded });
        _callbacks.forEach(cb => cb(_state));
      }
    });
  }
}

function setState(updates) {
  const prevFocusXref = _state.focusXref;
  const prevExpanded = _state.expandedNodes;
  _state = Object.assign({}, _state, updates);

  const focusChanged = 'focusXref' in updates && updates.focusXref !== prevFocusXref;
  const expandedChanged = 'expandedNodes' in updates && updates.expandedNodes !== prevExpanded;

  if (focusChanged) {
    _pushHistory(_state.focusXref, _state.expandedNodes);
  } else if (expandedChanged) {
    _replaceHistory(_state.focusXref, _state.expandedNodes);
  }

  _callbacks.forEach(cb => cb(_state));
}

function onStateChange(callback) {
  _callbacks.push(callback);
}

function getState() {
  return _state;
}

if (typeof module !== 'undefined') module.exports = { initState, setState, onStateChange, getState, _expandedToParam, _expandedFromParam };
