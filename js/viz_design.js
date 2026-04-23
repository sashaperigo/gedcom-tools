// Design tokens (Dark Editorial theme)
// Use var (not const) so it becomes a window-level global in browser script tags
var DESIGN = {
    // Colors — Dark Editorial palette (matches CSS variables in viz_ancestors.css)
    BG_BASE: '#0a0f1c',      // --bg-app
    BG_SURFACE: '#0d1526',   // --bg-surface
    BG_NODE: '#0d1526',      // --bg-surface (node cards)
    BG_NODE_FOCUS: '#2a1e4a', // --accent-bg
    BORDER: 'rgba(148,163,184,0.18)',
    BORDER_FOCUS: '#818cf8', // --accent
    TEXT_PRIMARY: '#e4e4ff', // --text-primary
    TEXT_SECONDARY: '#b8b8e0', // --text-secondary
    TEXT_MUTED: '#727298',   // --text-muted
    TEXT_DIM: '#424260',     // --text-disabled
    ACCENT: '#818cf8',       // --accent
    ACCENT_SPOUSE: '#a78bfa', // violet variant
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