# Common Mistakes

**⚠️ CRITICAL - Read at session start (2 min saves 2 hours!)**

---

## Top 5 Critical Mistakes

### 1. Wrong GEDCOM file path

**Symptom**: Nationality (NATI) data missing; people show no birthplace; server works but data is sparse.
**Check**: Is the server or script using `merged.ged` or a Desktop copy of the GED?
**Fix**: ALWAYS use the canonical path:
```
/Users/sashaperigo/claude-code/smyrna-diaspora-family-tree/Smyrna-Diaspora-Family-Tree.ged
```
Never use `merged.ged` (almost no NATI data), never use a Desktop copy (stale).

---

### 2. Committing merge output files

**Symptom**: `merged.ged`, `merge-session.json`, or `merge-report.txt` show up in `git status`.
**Check**: `git status` before committing.
**Fix**: Never stage or commit these files. They are ephemeral merge outputs, not source artifacts.

---

### 3. Missing FAM event branch (event card parity)

**Symptom**: Edit/citation modal works for birth/death but silently fails for marriage/divorce events.
**Check**: Does the handler check `isFamEvt = !!(evt && evt.fam_xref)` and branch on it?
**Fix**: Any event-level lookup in `viz_modals.js` (showEditCitationModal, showEditEventModal, _buildSourcesModalContent, etc.) MUST handle both flows:
- **INDI events**: keyed by `event_idx`
- **FAM events**: keyed by `fam_xref + marr_idx` (or `div_idx`); `event_idx` is null

Tests must cover both branches. See `docs/learnings/common-pitfalls.md` → "FAM events use marr_idx/div_idx".

---

### 4. Testing data structure instead of visual output (SVG layout bugs)

**Symptom**: Test passes, but the chart still looks wrong in the browser.
**Check**: Are the tests asserting on edge objects/groupings, or on geometric invariants?
**Fix**: For layout bugs, test what the user sees — geometric properties:
- "No horizontal at umbrellaY crosses personCenter from one side to the other"
- "Cluster A x-range and cluster B x-range are disjoint"

Data-structure tests (edge objects per FAM, children grouped by FAM) can pass while the visual is still broken. See `docs/learnings/common-pitfalls.md` → "SVG edge geometry".

---

### 5. Skipping TDD / writing code before tests

**Symptom**: Bug introduced silently; regression only noticed later.
**Check**: Were tests written before implementation?
**Fix**: Always write the test first, confirm it fails, then implement. This applies to linter checks, viz features, and merge pipeline changes. See testing-patterns.md for setup patterns.

---

**Update this file when:**
- Bug took >1 hour to debug
- Error could cause production issue
- Mistake repeated across sessions
- Pattern violates framework conventions

**Last Updated**: 2026-04-24
