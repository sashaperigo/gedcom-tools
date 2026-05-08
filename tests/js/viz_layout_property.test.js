// Property-based tests for the viz layout engine.
//
// Generates random GED-shaped inputs and runs computeLayoutChecked on each.
// Any invariant violation produces a reduced input via the shrinker so the
// failure is debuggable.
//
// Reproduce a single seed:    LAYOUT_PROPERTY_SEED=47 npx vitest run tests/js/viz_layout_property.test.js
// Run more seeds locally:     LAYOUT_PROPERTY_COUNT=1000 npm test

import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);

const { DESIGN } = require('../../js/viz_design.js');
global.DESIGN = DESIGN;

const { computeLayout } = require('../../js/viz_layout.js');
const { assertAllLayoutInvariants } = require('./_layout_invariants.js');
const { generateLayoutInput } = require('./_layout_generator.js');
const { shrink, formatInput } = require('./_layout_shrink.js');

const DEFAULT_COUNT = 200;
const ENV_COUNT = parseInt(process.env.LAYOUT_PROPERTY_COUNT || '', 10);
const ENV_SEED = parseInt(process.env.LAYOUT_PROPERTY_SEED || '', 10);
// Per-scenario seed budget — scenarios are pre-biased toward bug classes so
// fewer seeds suffice. Override with LAYOUT_SCENARIO_COUNT for stress runs.
const SCENARIO_COUNT = parseInt(process.env.LAYOUT_SCENARIO_COUNT || '', 10) || 50;
const SCENARIOS = [
    'focus_parent_sibling_with_kids',
    'focus_sibling_with_grandkids',
    'adjacent_siblings_both_expanded',
    'multi_gen_ancestor_siblings',
    'focus_uncle_grandkids_vs_focus_kids',
];

// Failures matching any of these patterns are pre-existing layout bugs being
// tracked elsewhere — log and skip rather than block CI. Removing an entry
// from this list when the underlying bug is fixed re-arms the property suite
// to flag regressions. Add a new entry only with a doc reference.
const KNOWN_FAILURES = [];

function classifyFailure(message) {
    for (const k of KNOWN_FAILURES) {
        if (k.pattern.test(message)) return k;
    }
    return null;
}

function applyGlobals(g) {
    global.PEOPLE = g.PEOPLE;
    global.PARENTS = g.PARENTS;
    global.CHILDREN = g.CHILDREN;
    global.RELATIVES = g.RELATIVES;
    global.FAMILIES = g.FAMILIES;
}

function runLayout(input) {
    applyGlobals(input.globals);
    return computeLayout(
        input.focusXref,
        input.expandedAncestors,
        input.expandedChildrenPersons,
        input.expandedSiblingsXrefs
    );
}

function fails(input) {
    try {
        const result = runLayout(input);
        assertAllLayoutInvariants(result);
        return false;
    } catch (_) {
        return true;
    }
}

function getFailureMessage(input) {
    try {
        const result = runLayout(input);
        assertAllLayoutInvariants(result);
        return null;
    } catch (e) {
        return e.message;
    }
}

const seeds = ENV_SEED
    ? [ENV_SEED]
    : Array.from({ length: ENV_COUNT || DEFAULT_COUNT }, (_, i) => i + 1);

describe('property tests — layout invariants', () => {
    for (const seed of seeds) {
        it(`seed=${seed}`, () => {
            const input = generateLayoutInput(seed);
            const originalMsg = getFailureMessage(input);
            if (!originalMsg) return; // pass
            const known = classifyFailure(originalMsg);
            if (known) return; // tracked separately; don't fail CI

            // Real failure — shrink and report.
            const minimal = shrink(input, fails);
            const minimalMsg = getFailureMessage(minimal) || originalMsg;
            const detail =
                `\nseed=${seed}\n\n` +
                `Minimal failing input:\n${formatInput(minimal)}\n\n` +
                `Invariant violation: ${minimalMsg}`;
            throw new Error(detail);
        });
    }
});

// Scenario-biased property tests. Each scenario forces a specific
// genealogical configuration (focus's uncle has expanded kids, etc.) and
// runs SCENARIO_COUNT seeded variants through the same invariant suite.
// Reproduce a single failure: LAYOUT_PROPERTY_SEED=N npx vitest run -t "scenario=NAME"
const scenarioSeeds = ENV_SEED
    ? [ENV_SEED]
    : Array.from({ length: SCENARIO_COUNT }, (_, i) => i + 1);

for (const scenario of SCENARIOS) {
    describe(`property tests — scenario=${scenario}`, () => {
        for (const seed of scenarioSeeds) {
            it(`scenario=${scenario} seed=${seed}`, () => {
                const input = generateLayoutInput(seed, { scenario });
                const originalMsg = getFailureMessage(input);
                if (!originalMsg) return;
                const known = classifyFailure(originalMsg);
                if (known) return;

                const minimal = shrink(input, fails);
                const minimalMsg = getFailureMessage(minimal) || originalMsg;
                const detail =
                    `\nscenario=${scenario} seed=${seed}\n\n` +
                    `Minimal failing input:\n${formatInput(minimal)}\n\n` +
                    `Invariant violation: ${minimalMsg}`;
                throw new Error(detail);
            });
        }
    });
}
