// Single state object with URL sync and re-render callback system.

let _state = {
  focusXref:             null,
  expandedNodes:         new Set(),
  expandedSiblingsXrefs: new Set(),
  panelOpen:             false,
  panelXref:             null,
};

const _callbacks = [];

// ── helpers ───────────────────────────────────────────────────────────────

function _setToParam(set) {
  if (!set || set.size === 0) return null;
  return Array.from(set)
    .map(x => x.replace(/@/g, ''))
    .sort()
    .join(',');
}

function _setFromParam(search, paramName) {
  const params = new URLSearchParams(search);
  const raw = params.get(paramName);
  if (!raw) return new Set();
  return new Set(raw.split(',').filter(Boolean).map(x => '@' + x + '@'));
}

function _expandedToParam(expandedNodes) {
  return _setToParam(expandedNodes);
}

function _expandedFromParam(search) {
  return _setFromParam(search, 'expanded');
}

function _siblingsToParam(expandedSiblingsXrefs) {
  return _setToParam(expandedSiblingsXrefs);
}

function _siblingsFromParam(search) {
  return _setFromParam(search, 'siblings');
}

function _xrefFromUrl(search) {
  const params = new URLSearchParams(search);
  const person = params.get('person');
  if (person) return '@' + person + '@';
  return null;
}

function _buildUrl(focusXref, expandedNodes, expandedSiblingsXrefs) {
  if (!focusXref) return '';
  const clean = focusXref.replace(/@/g, '');
  const expandedParam = _expandedToParam(expandedNodes);
  const siblingsParam = _siblingsToParam(expandedSiblingsXrefs);
  let url = '?person=' + clean;
  if (expandedParam) url += '&expanded=' + expandedParam;
  if (siblingsParam) url += '&siblings=' + siblingsParam;
  return url;
}

function _historyState(focusXref, expandedNodes, expandedSiblingsXrefs) {
  return {
    focusXref,
    expandedXrefs: _expandedToParam(expandedNodes),
    siblingsXrefs: _siblingsToParam(expandedSiblingsXrefs),
  };
}

function _pushHistory(focusXref, expandedNodes, expandedSiblingsXrefs) {
  if (typeof history === 'undefined') return;
  history.pushState(
    _historyState(focusXref, expandedNodes, expandedSiblingsXrefs),
    '',
    _buildUrl(focusXref, expandedNodes, expandedSiblingsXrefs),
  );
}

function _replaceHistory(focusXref, expandedNodes, expandedSiblingsXrefs) {
  if (typeof history === 'undefined') return;
  history.replaceState(
    _historyState(focusXref, expandedNodes, expandedSiblingsXrefs),
    '',
    _buildUrl(focusXref, expandedNodes, expandedSiblingsXrefs),
  );
}

// ── public API ────────────────────────────────────────────────────────────

function initState(rootXref) {
  const search = typeof location !== 'undefined' ? location.search : '';
  const fromUrl = _xrefFromUrl(search);
  _state = {
    focusXref:             fromUrl || rootXref,
    expandedNodes:         _expandedFromParam(search),
    expandedSiblingsXrefs: _siblingsFromParam(search),
    panelOpen:             false,
    panelXref:             null,
  };

  if (typeof addEventListener !== 'undefined') {
    addEventListener('popstate', function (event) {
      let newXref = null;
      if (event.state && event.state.focusXref) {
        newXref = event.state.focusXref;
      } else if (typeof location !== 'undefined') {
        newXref = _xrefFromUrl(location.search);
      }
      const locSearch = typeof location !== 'undefined' ? location.search : '';

      let newExpanded;
      if (event.state && event.state.expandedXrefs !== undefined) {
        newExpanded = event.state.expandedXrefs
          ? new Set(event.state.expandedXrefs.split(',').map(x => '@' + x + '@'))
          : new Set();
      } else {
        newExpanded = _expandedFromParam(locSearch);
      }

      let newSiblings;
      if (event.state && event.state.siblingsXrefs !== undefined) {
        newSiblings = event.state.siblingsXrefs
          ? new Set(event.state.siblingsXrefs.split(',').map(x => '@' + x + '@'))
          : new Set();
      } else {
        newSiblings = _siblingsFromParam(locSearch);
      }

      if (newXref) {
        _state = Object.assign({}, _state, {
          focusXref:             newXref,
          expandedNodes:         newExpanded,
          expandedSiblingsXrefs: newSiblings,
        });
        _callbacks.forEach(cb => cb(_state));
      }
    });
  }
}

function setState(updates) {
  const prevFocusXref = _state.focusXref;
  const prevExpanded = _state.expandedNodes;
  const prevSiblings = _state.expandedSiblingsXrefs;
  _state = Object.assign({}, _state, updates);

  const focusChanged    = 'focusXref' in updates && updates.focusXref !== prevFocusXref;
  const expandedChanged = 'expandedNodes' in updates && updates.expandedNodes !== prevExpanded;
  const siblingsChanged = 'expandedSiblingsXrefs' in updates && updates.expandedSiblingsXrefs !== prevSiblings;

  if (focusChanged) {
    _pushHistory(_state.focusXref, _state.expandedNodes, _state.expandedSiblingsXrefs);
  } else if (expandedChanged || siblingsChanged) {
    _replaceHistory(_state.focusXref, _state.expandedNodes, _state.expandedSiblingsXrefs);
  }

  _callbacks.forEach(cb => cb(_state));
}

function onStateChange(callback) {
  _callbacks.push(callback);
}

function getState() {
  return _state;
}

if (typeof module !== 'undefined') module.exports = {
  initState,
  setState,
  onStateChange,
  getState,
  _expandedToParam,
  _expandedFromParam,
  _siblingsToParam,
  _siblingsFromParam,
};
