// Shared HTML-escaping utilities.
// Used by viz_advanced_search.js and viz_advanced_results.js.

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

if (typeof module !== 'undefined') {
    module.exports = { escapeHtml };
}
