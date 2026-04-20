// Design tokens (Obsidian theme)
// Use var (not const) so it becomes a window-level global in browser script tags
var DESIGN = {
  // Colors
  BG_BASE:        '#07070d',
  BG_SURFACE:     '#0a0a18',
  BG_NODE:        '#131330',
  BG_NODE_FOCUS:  '#1e1e42',
  BORDER:         '#343468',
  BORDER_FOCUS:   '#7878d4',
  TEXT_PRIMARY:   '#e4e4ff',
  TEXT_SECONDARY: '#b8b8e0',
  TEXT_MUTED:     '#727298',
  TEXT_DIM:       '#484860',
  ACCENT:         '#7878d4',
  ACCENT_SPOUSE:  '#3a6a3a',
  ACCENT_SOURCE:  '#78b878',

  // Layout constants (replaces viz_constants.js)
  NODE_W:       100,  // normal node width
  NODE_W_FOCUS: 116,  // focused node width
  NODE_H:       64,   // normal node height
  NODE_H_FOCUS: 70,   // focused node height
  ROW_HEIGHT:   116,  // vertical distance between generation rows (gap stays 52px)
  H_GAP:        12,   // gap between sibling nodes
  MARRIAGE_GAP: 60,   // gap between last sibling and spouse
  NODE_RADIUS:  4,    // border-radius for nodes
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
