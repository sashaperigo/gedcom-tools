// Design tokens (Dark Editorial theme)
// Use var (not const) so it becomes a window-level global in browser script tags
var DESIGN = {
    // Colors
    BG_BASE: '#07070d',
    BG_SURFACE: '#0d0d1f',
    BG_NODE: '#131c30',
    BG_NODE_FOCUS: '#2a1e4a',
    BORDER: 'rgba(148,163,184,0.22)',
    BORDER_FOCUS: '#a78bfa',
    TEXT_PRIMARY: '#f1f5f9',
    TEXT_SECONDARY: '#cbd5e1',
    TEXT_MUTED: '#94a3b8',
    TEXT_DIM: '#64748b',
    ACCENT: '#818cf8',
    ACCENT_SPOUSE: '#a78bfa',
    ACCENT_SOURCE: '#6ee7b7',

    // Layout constants (replaces viz_constants.js)
    NODE_W: 100, // normal node width
    NODE_W_FOCUS: 116, // focused node width
    NODE_H: 64, // normal node height
    NODE_H_FOCUS: 70, // focused node height
    ROW_HEIGHT: 148, // vertical distance between generation rows (gap stays 84px)
    H_GAP: 12, // gap between sibling nodes
    MARRIAGE_GAP: 20, // offset in the focus-spouse layout formula; yields a 12px visible gap between focus right edge and spouse left edge, matching SIB_MARRIAGE_GAP and the parent-parent gap (H_GAP)
    FAMILY_GAP: 40, // padding between two separate family subtrees at depth >= 1
    NODE_RADIUS: 4, // border-radius for nodes
};

// ── Shared utility: HTML escaping ─────────────────────────────────────────────
function escHtml(s) {
    return String(s || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

if (typeof module !== 'undefined') module.exports = { DESIGN, escHtml };