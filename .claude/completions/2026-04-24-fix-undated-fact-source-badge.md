# Task Completion: Fix undated fact source badge citation count

**Date**: 2026-04-24

---

## What was done

Source badges on undated fact rows (OCCU, RELI, TITL, FACT, NCHI) always showed `+ src` regardless of how many citations were attached. The `undatedRows` function in `viz_panel.js` had a separate `srcBadgeInline` variable hardcoded to `+ src`, which was used instead of `srcBadge` (built by `buildSourceBadgeHtml` which reads the actual citation count). Removed `srcBadgeInline` and switched all fact rows to use `srcBadge`.

## Files changed

- `js/viz_panel.js` — removed hardcoded `srcBadgeInline`; fact rows (NCHI and general) now use `srcBadge` from `buildSourceBadgeHtml`
- `tests/js/viz_panel.test.js` — added regression test: undated OCCU with one citation must render `1 src` not `+ src`

## Key decisions

RESI rows already used `srcBadge` correctly (it renders as `evt-entry`); only the `fact-row`-style rows had the bug. Rather than unifying the two badge variables into one helper, the simplest fix was to delete `srcBadgeInline` entirely since `srcBadge` was already computed on the same line and has identical click behavior.

## Tests added/modified

- `tests/js/viz_panel.test.js` — "undated OCCU with citation shows citation count in source badge" — asserts `1 src` present and `+ src` absent when event has one citation

## Follow-up / known gaps

None — all 75 pre-existing failures are unrelated; no regressions introduced.
