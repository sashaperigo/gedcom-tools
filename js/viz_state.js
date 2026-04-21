// Single state object with URL sync and re-render callback system.

let _state = {
    focusXref: null,
    expandedNodes: new Set(),
    expandedSiblingsXrefs: new Set(),
    expandedChildrenFams: new Set(),
    visibleSpouseFams: new Set(),
    panelOpen: false,
    panelXref: null,
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

function _tokenToFamXref(token) {
    // '6GRCj0Y' → '@F380071267816@'
    return '@F' + _fromBase62(token) + '@';
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

function _childrenFamsToParam(expandedChildrenFams) {
    return _setToParam(expandedChildrenFams);
}

function _childrenFamsFromParam(search) {
    const raw = _getRawParam(search, 'c');
    if (!raw) return new Set();
    return new Set(raw.split('+').filter(Boolean).map(_tokenToFamXref));
}

function _visibleSpouseFamsToParam(visibleSpouseFams) {
    return _setToParam(visibleSpouseFams);
}

function _visibleSpouseFamsFromParam(search) {
    const raw = _getRawParam(search, 'm');
    if (!raw) return new Set();
    return new Set(raw.split('+').filter(Boolean).map(_tokenToFamXref));
}

function _xrefFromUrl(search) {
    const params = new URLSearchParams(search);
    const p = params.get('p');
    if (p) return _tokenToXref(p);
    const person = params.get('person');
    if (person) return '@' + person + '@';
    return null;
}

function _buildUrl(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams, visibleSpouseFams) {
    if (!focusXref) return '';
    const token = _xrefToToken(focusXref);
    const expandedParam = _expandedToParam(expandedNodes);
    const siblingsParam = _siblingsToParam(expandedSiblingsXrefs);
    const childrenParam = _childrenFamsToParam(expandedChildrenFams);
    const spouseParam = _visibleSpouseFamsToParam(visibleSpouseFams);
    let url = '?p=' + token;
    if (expandedParam) url += '&e=' + expandedParam;
    if (siblingsParam) url += '&s=' + siblingsParam;
    if (childrenParam) url += '&c=' + childrenParam;
    if (spouseParam) url += '&m=' + spouseParam;
    return url;
}

function _historyState(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams, visibleSpouseFams) {
    return {
        focusXref,
        expandedXrefs: _expandedToParam(expandedNodes),
        siblingsXrefs: _siblingsToParam(expandedSiblingsXrefs),
        childrenFamsXrefs: _childrenFamsToParam(expandedChildrenFams),
        visibleSpouseFamsXrefs: _visibleSpouseFamsToParam(visibleSpouseFams),
    };
}

function _pushHistory(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams, visibleSpouseFams) {
    if (typeof history === 'undefined') return;
    history.pushState(
        _historyState(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams, visibleSpouseFams),
        '',
        _buildUrl(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams, visibleSpouseFams),
    );
}

function _replaceHistory(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams, visibleSpouseFams) {
    if (typeof history === 'undefined') return;
    history.replaceState(
        _historyState(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams, visibleSpouseFams),
        '',
        _buildUrl(focusXref, expandedNodes, expandedSiblingsXrefs, expandedChildrenFams, visibleSpouseFams),
    );
}

// ── public API ────────────────────────────────────────────────────────────

function initState(rootXref) {
    const search = typeof location !== 'undefined' ? location.search : '';
    const fromUrl = _xrefFromUrl(search);

    let expandedNodes, expandedSiblingsXrefs;
    if (_isLegacyUrl(search)) {
        expandedNodes = _legacySetFromParam(search, 'expanded');
        expandedSiblingsXrefs = _legacySetFromParam(search, 'siblings');
    } else {
        expandedNodes = _expandedFromParam(search);
        expandedSiblingsXrefs = _siblingsFromParam(search);
    }
    const expandedChildrenFams = _childrenFamsFromParam(search);
    const visibleSpouseFams = _visibleSpouseFamsFromParam(search);

    _state = {
        focusXref: fromUrl || rootXref,
        expandedNodes,
        expandedSiblingsXrefs,
        expandedChildrenFams,
        visibleSpouseFams,
        panelOpen: false,
        panelXref: null,
    };

    if (typeof addEventListener !== 'undefined') {
        addEventListener('popstate', function(event) {
            let newXref = null;
            if (event.state && event.state.focusXref) {
                newXref = event.state.focusXref;
            } else if (typeof location !== 'undefined') {
                newXref = _xrefFromUrl(location.search);
            }
            const locSearch = typeof location !== 'undefined' ? location.search : '';

            let newExpanded;
            if (event.state && event.state.expandedXrefs !== undefined) {
                newExpanded = event.state.expandedXrefs ?
                    new Set(event.state.expandedXrefs.split('+').map(_tokenToXref)) :
                    new Set();
            } else if (_isLegacyUrl(locSearch)) {
                newExpanded = _legacySetFromParam(locSearch, 'expanded');
            } else {
                newExpanded = _expandedFromParam(locSearch);
            }

            let newSiblings;
            if (event.state && event.state.siblingsXrefs !== undefined) {
                newSiblings = event.state.siblingsXrefs ?
                    new Set(event.state.siblingsXrefs.split('+').map(_tokenToXref)) :
                    new Set();
            } else if (_isLegacyUrl(locSearch)) {
                newSiblings = _legacySetFromParam(locSearch, 'siblings');
            } else {
                newSiblings = _siblingsFromParam(locSearch);
            }

            let newChildrenFams;
            if (event.state && event.state.childrenFamsXrefs !== undefined) {
                newChildrenFams = event.state.childrenFamsXrefs ?
                    new Set(event.state.childrenFamsXrefs.split('+').map(_tokenToFamXref)) :
                    new Set();
            } else {
                newChildrenFams = _childrenFamsFromParam(locSearch);
            }

            let newVisibleSpouseFams;
            if (event.state && event.state.visibleSpouseFamsXrefs !== undefined) {
                newVisibleSpouseFams = event.state.visibleSpouseFamsXrefs ?
                    new Set(event.state.visibleSpouseFamsXrefs.split('+').map(_tokenToFamXref)) :
                    new Set();
            } else {
                newVisibleSpouseFams = _visibleSpouseFamsFromParam(locSearch);
            }

            if (newXref) {
                _state = Object.assign({}, _state, {
                    focusXref: newXref,
                    expandedNodes: newExpanded,
                    expandedSiblingsXrefs: newSiblings,
                    expandedChildrenFams: newChildrenFams,
                    visibleSpouseFams: newVisibleSpouseFams,
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
    const prevChildrenFams = _state.expandedChildrenFams;
    const prevSpouseFams = _state.visibleSpouseFams;
    _state = Object.assign({}, _state, updates);

    const focusChanged = 'focusXref' in updates && updates.focusXref !== prevFocusXref;
    const expandedChanged = 'expandedNodes' in updates && updates.expandedNodes !== prevExpanded;
    const siblingsChanged = 'expandedSiblingsXrefs' in updates && updates.expandedSiblingsXrefs !== prevSiblings;
    const childrenFamsChanged = 'expandedChildrenFams' in updates && updates.expandedChildrenFams !== prevChildrenFams;
    const spouseFamsChanged = 'visibleSpouseFams' in updates && updates.visibleSpouseFams !== prevSpouseFams;

    if (focusChanged) {
        _pushHistory(_state.focusXref, _state.expandedNodes, _state.expandedSiblingsXrefs, _state.expandedChildrenFams, _state.visibleSpouseFams);
    } else if (expandedChanged || siblingsChanged || childrenFamsChanged || spouseFamsChanged) {
        _replaceHistory(_state.focusXref, _state.expandedNodes, _state.expandedSiblingsXrefs, _state.expandedChildrenFams, _state.visibleSpouseFams);
    }

    _callbacks.forEach(cb => cb(_state));
}

function resetToRoot(rootXref) {
    _state = {
        focusXref: rootXref,
        expandedNodes: new Set(),
        expandedSiblingsXrefs: new Set(),
        expandedChildrenFams: new Set(),
        visibleSpouseFams: new Set(),
        panelOpen: false,
        panelXref: null,
    };
    _pushHistory(_state.focusXref, _state.expandedNodes, _state.expandedSiblingsXrefs, _state.expandedChildrenFams, _state.visibleSpouseFams);
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
    resetToRoot,
    onStateChange,
    getState,
    _toBase62,
    _fromBase62,
    _xrefToToken,
    _tokenToXref,
    _tokenToFamXref,
    _expandedToParam,
    _expandedFromParam,
    _siblingsToParam,
    _siblingsFromParam,
    _childrenFamsToParam,
    _childrenFamsFromParam,
    _visibleSpouseFamsToParam,
    _visibleSpouseFamsFromParam,
};