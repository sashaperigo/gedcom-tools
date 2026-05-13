// Node-only compatibility shim. The browser loads the 4 split files
// directly via <script> tags in viz_ancestors.html; this file only runs
// under vitest/node, where it loads each split module and re-exports
// their public bindings as one object so existing tests can keep doing
// `require('../../js/viz_modals.js')`.
if (typeof module !== 'undefined' && module.exports) {
    const shared = require('./viz_modal_shared.js');
    // Cross-module references in events/sources/people resolve at call
    // time via global lookup (browser <script> tags share scope). Mirror
    // shared bindings onto global so node tests behave the same way.
    Object.assign(global, shared);
    module.exports = {
        ...shared,
        ...require('./viz_modal_events.js'),
        ...require('./viz_modal_sources.js'),
        ...require('./viz_modal_people.js'),
    };
}
