// Single state object with URL sync and re-render callback system.

let _state = {
  focusXref:             null,
  expandedNodes:         new Set(),
  expandedSiblingsXrefs: new Set(),
  panelOpen:             false,
  panelXref:             null,
};

const _callbacks = [];

// ── base62 helpers ────────────────────────────────────────────────────────

const BASE62 = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';

function _toBase62(n) {
  if (n === 0) return '0';
  let s = '';
  while (n > 0) {
    s = BASE62[n % 62] + s;
    n = Math.floor(n / 62);
  }
  return s;
}

function _fromBase62(s) {
  let n = 0;
  for (const c of s) n = n * 62 + BASE62.indexOf(c);
  return n;
}

function _xrefToToken(xref) {
  // '@I380071267816@' → '6GRCj0Y'
  const inner = xref.replace(/@/g, '').slice(1);
  return /^\d+$/.test(inner) ? _toBase62(Number(inner)) : inner;
}

function _tokenToXref(token) {
  // '6GRCj0Y' → '@I380071267816@'
  return '@I' + _fromBase62(token) + '@';
}

// ── URL helpers ───────────────────────────────────────────────────────────

// Extract raw param value from search string without URLSearchParams
// so that literal '+' characters are preserved (URLSearchParams decodes '+' as space).
function _getRawParam(search, name) {
  const m = new RegExp('[?&]' + name + '=([^&]*)').exec(search);
  return m ? m[1] : null;
}

function _isLegacyUrl(search) {
  return new URLSearchParams(search).has('person');
}

function _legacySetFromParam(search, paramName) {
  const params = new URLSearchParams(search);
  const raw = params.get(paramName);
  if (!raw) return new Set();
  return new Set(raw.split(',').filter(Boolean).map(x => '@' + x + '@'));
}

function _setToParam(set) {
  if (!set || set.size === 0) return null;
  return Array.from(set)
    .map(_xrefToToken)
    .sort()
    .join('+');
}

function _setFromParam(search, paramName) {
  const raw = _getRawParam(search, paramName);
  if (!raw) return new Set();
  return new Set(raw.split('+').filter(Boolean).map(_tokenToXref));
}

function _expandedToParam(expandedNodes) {
  return _setToParam(expandedNodes);
}

function _expandedFromParam(search) {
  return _setFromParam(search, 'e');
}

function _siblingsToParam(expandedSiblingsXrefs) {
  return _setToParam(expandedSiblingsXrefs);
}

function _siblingsFromParam(search) {
  return _setFromParam(search, 's');
}

function _xrefFromUrl(search) {
  const params = new URLSearchParams(search);
  const p = params.get('p');
  if (p) return _tokenToXref(p);
  const person = params.get('person');
  if (person) return '@' + person + '@';
  return null;
}

function _buildUrl(focusXref, expandedNodes, expandedSiblingsXrefs) {
  if (!focusXref) return '';
  const token = _xrefToToken(focusXref);
  const expandedParam = _expandedToParam(expandedNodes);
  const siblingsParam = _siblingsToParam(expandedSiblingsXrefs);
  let url = '?p=' + token;
  if (expandedParam) url += '&e=' + expandedParam;
  if (siblingsParam) url += '&s=' + siblingsParam;
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

  let expandedNodes, expandedSiblingsXrefs;
  if (_isLegacyUrl(search)) {
    expandedNodes         = _legacySetFromParam(search, 'expanded');
    expandedSiblingsXrefs = _legacySetFromParam(search, 'siblings');
  } else {
    expandedNodes         = _expandedFromParam(search);
    expandedSiblingsXrefs = _siblingsFromParam(search);
  }

  _state = {
    focusXref:             fromUrl || rootXref,
    expandedNodes,
    expandedSiblingsXrefs,
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
          ? new Set(event.state.expandedXrefs.split('+').map(_tokenToXref))
          : new Set();
      } else if (_isLegacyUrl(locSearch)) {
        newExpanded = _legacySetFromParam(locSearch, 'expanded');
      } else {
        newExpanded = _expandedFromParam(locSearch);
      }

      let newSiblings;
      if (event.state && event.state.siblingsXrefs !== undefined) {
        newSiblings = event.state.siblingsXrefs
          ? new Set(event.state.siblingsXrefs.split('+').map(_tokenToXref))
          : new Set();
      } else if (_isLegacyUrl(locSearch)) {
        newSiblings = _legacySetFromParam(locSearch, 'siblings');
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
  _toBase62,
  _fromBase62,
  _xrefToToken,
  _tokenToXref,
  _expandedToParam,
  _expandedFromParam,
  _siblingsToParam,
  _siblingsFromParam,
};
