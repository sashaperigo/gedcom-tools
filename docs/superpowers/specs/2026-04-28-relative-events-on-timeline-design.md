# Relative life events on the person timeline — design

**Date**: 2026-04-28
**Status**: Spec — pending implementation plan

---

## Problem

The detail panel's timeline currently shows only the focused person's own events. A person's life is shaped by what happens to those around them — a parent's death in childhood, the births of children, losing a spouse. Surfacing those events on the timeline gives the focused person's life its social context without forcing the user to navigate to each relative.

## Goal

Render life events of close relatives — parents, spouse(s), children — on the focused person's timeline, visually distinct from the person's own events, bounded to events that occurred during the person's lifetime.

## Scope

**In scope (relative events to display):**

- **Birth of children** — for each child of the focused person.
- **Death of children** — for each child who died during the focused person's lifetime.
- **Death of spouse(s)** — for each spouse who died during the focused person's lifetime.
- **Death of parents** — for each parent who died during the focused person's lifetime.

**Out of scope:**

- Sibling events
- Marriages of children, parents, or siblings
- Births of parents or spouses (always before the focused person's death; not informative)
- Any event without a year

## Display

Compact one-liner rendered between the focused person's own event cards, in muted italic text, no card chrome, no tag column, no edit/delete/source actions.

```
1895 · Death of father Dimitrios Konstantinidis
1904 · Birth of daughter Eleni Papadopoulos
```

Visual treatment matches the **Option B** mockup in `mockups/relative-events-options.html`:

- Year (`var(--text-secondary)`, weight 600, tabular-nums) in a 36px column
- Phrase in italic, `var(--text-muted)`, font-size 12px
- 4px vertical padding, no border, no background

CSS class: `.evt-rel-row` (with `.yr` and `.label` children).

### Phrasing

Relationship-led, neutral form:

| Event | Phrase |
|---|---|
| Child birth (sex known) | `Birth of son <name>` / `Birth of daughter <name>` |
| Child birth (sex unknown) | `Birth of child <name>` |
| Child death | `Death of son <name>` / `Death of daughter <name>` / `Death of child <name>` |
| Spouse death (sex known) | `Death of husband <name>` / `Death of wife <name>` |
| Spouse death (sex unknown) | `Death of spouse <name>` |
| Parent death (sex known) | `Death of father <name>` / `Death of mother <name>` |
| Parent death (sex unknown) | `Death of parent <name>` |

If `<name>` is missing, drop it: `Birth of daughter`, `Death of spouse`, etc.

## Filtering rules

A relative event is **included** if and only if:

1. The event has a year (year-only is sufficient; full date not required).
2. The relative is a parent, child, or spouse of the focused person.
3. The event year falls within the focused person's lifetime, computed as:
    - **Lower bound**: focused person's `birth_year`.
        - If unknown: skip all relative events for this person.
    - **Upper bound**:
        - focused person's `death_year` if known;
        - else `birth_year + 100`.
    - Inclusive on both ends.

For child births, the lower bound is also bounded by the parent's birth year (a child can't be born before its parent), but in practice this is identical to using the focused person's `birth_year`.

## Section assignment

Relative events follow the same temporal rule as the focused person's own events:

- `Early Life` — year ≤ focused person's `birth_year + 18`
- `Life` — otherwise

`Later Life` is reserved for the focused person's own death-related events; relative events never go there.

## Sort order

All events (own + relative) are sorted ascending by year. **Within a single year, the focused person's own events render before relative events.** Within either group, existing tie-breaking rules apply (own events: GEDCOM order; relative events: parent-death, child-birth, child-death, spouse-death, then alphabetical by relative name).

## Data source

Use the `ALL_PEOPLE` global only — every individual is indexed there with `birth_year` and `death_year`. The `PEOPLE` global (full event records) is not consulted, because:

- The display only requires year + name + sex.
- `PEOPLE` is partial — depends on which subtree is expanded — so using it would make relative events appear/disappear as the user navigates the tree.
- `ALL_PEOPLE` is constant for the session.

### Required Python change

`viz_ancestors.py:1048` builds the `all_people` list. Add `sex` to each entry:

```python
all_people = sorted(
    [{"id": xref, "name": info["name"] or "",
      "birth_year": info.get("birth_year") or "",
      "death_year": info.get("death_year") or "",
      "sex": info.get("sex") or ""}
     for xref, info in indis.items()],
    key=lambda p: p["name"].lower()
)
```

(`indis[xref]['sex']` is already populated by the GEDCOM parser; no parser changes needed. Verify during implementation.)

### JS index

On panel load, build a one-shot lookup once and cache on `window`:

```js
const ALL_PEOPLE_BY_ID = Object.fromEntries(ALL_PEOPLE.map(p => [p.id, p]));
```

## Components

### `js/viz_relative_events.js` (new module)

Single responsibility: given a focused-person xref, return the list of relative-event rows to render.

**Public function:**

```js
// Returns: [{ year, section, kind, role, name, sortKey }]
//   - year:    number
//   - section: 'Early Life' | 'Life'
//   - kind:    'birth' | 'death'
//   - role:    'son'|'daughter'|'child'|'husband'|'wife'|'spouse'|'father'|'mother'|'parent'
//   - name:    string (possibly empty)
//   - sortKey: number used for intra-year ordering (parents-death < child-birth < child-death < spouse-death)
function buildRelativeEvents(xref) { ... }
```

The function does the filtering, the role/sex resolution, and the year-window check. It does NOT render HTML — that's `viz_panel.js`'s job.

**Helpers (private to the module):**

- `_collectChildren(xref)` — uses `CHILDREN[xref]`
- `_collectSpouses(xref)` — uses `FAMILIES` to find spouses across all FAM records the person belongs to
- `_collectParents(xref)` — uses `PARENTS[xref]`
- `_role(relativeXref, relation)` — maps sex + relation to display role (son/daughter/etc.)
- `_lifetimeBounds(xref)` — returns `{ lo, hi }` or `null` if birth year unknown

### `js/viz_panel.js` (modified)

In the timeline render block (around `viz_panel.js:610-781`):

1. After computing `sorted` (the focused person's own events), call `buildRelativeEvents(xref)` to get relative rows.
2. Merge the two streams into a single year-sorted sequence with the rule: at equal year, own event first.
3. While walking the merged sequence, emit either an existing `.evt-entry` (own event) or a new `.evt-rel-row` (relative event).
4. Section header logic uses the same `Early Life | Life | Later Life` rule, applied to the row's year (relative events never produce `Later Life`).

### `viz_ancestors.css` (modified)

Append a small block defining `.evt-rel-row`, `.evt-rel-row .yr`, `.evt-rel-row .label`. Lifted directly from the mockup (`mockups/relative-events-options.html`).

## Testing

Add `tests/js/viz_relative_events.test.js` covering `buildRelativeEvents`:

1. Returns empty array when focused person has no birth year.
2. Returns empty array when focused person has no relatives.
3. Includes child birth when child has birth year within lifetime.
4. Excludes child birth when child has no birth year.
5. Excludes child birth when child's birth year is after focused person's death year.
6. Includes child death when within lifetime; excludes when after.
7. Includes spouse death when within lifetime.
8. Includes parent death when within lifetime.
9. Returns role `daughter` when child sex is `F`, `son` when `M`, `child` when missing.
10. Returns role `husband`/`wife`/`spouse` based on sex.
11. Returns role `father`/`mother`/`parent` based on sex.
12. Falls back to `birth_year + 100` upper bound when death year unknown; excludes events past that.
13. Section assignment: event at `birth_year + 18` → `Early Life`; at `birth_year + 19` → `Life`.
14. Sort: at equal year, parent-death sorts before child-birth before child-death before spouse-death.

Inject `ALL_PEOPLE`, `PARENTS`, `CHILDREN`, `FAMILIES` as globals in `beforeEach` per existing pattern (`tests/js/README.md`).

No Python tests required — only `viz_ancestors.py` change is appending `sex` to a dict literal; covered by visual verification.

## Edge cases

- **Multiple spouses**: each spouse's death is shown independently, ordered by year.
- **Adopted/step relationships**: `PARENTS` and `CHILDREN` are derived from FAMC/FAMS only; if the GEDCOM has no PEDI tag distinguishing biological vs adoptive, both render the same. Out of scope to differentiate.
- **Same-sex couples**: spouse role uses the *spouse's* sex to pick `husband`/`wife`. If both are male, the focused person sees `Death of husband`. Acceptable.
- **Person predeceases own parent**: parent's death year falls outside the focused person's lifetime; correctly filtered out.
- **Stillborn child with same birth/death year**: both events render; same year, child-birth before child-death per intra-year sort key.
- **Self-loop / data error** (person is their own parent): the lifetime bound clip handles this naturally — the event year either falls inside or outside the window.

## Non-goals

- Editing relative events from the timeline (they're not the focused person's events; navigate to the relative).
- Showing places, full dates, or sources for relative events.
- Showing siblings' events (decided B over C in scope discussion).
- Showing marriages of children (decided B over D in scope discussion).
- Surfacing this on print/export views.

## Open questions

None at spec time.

## Implementation order

1. Add `sex` to `ALL_PEOPLE` payload in `viz_ancestors.py`. Smoke-test via dev server.
2. Write `tests/js/viz_relative_events.test.js` (TDD — tests come first).
3. Implement `js/viz_relative_events.js` to pass tests.
4. Add `.evt-rel-row` CSS to `viz_ancestors.css`.
5. Wire into `viz_panel.js` timeline render block.
6. Add `<script src="/js/viz_relative_events.js">` to `viz_ancestors.html`.
7. Manually verify in browser: focus a person with children, parents, and a deceased spouse; verify ordering, section split, lifetime bound, italics + muted color.
