# CSS Custom Properties Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all magic hex colors and layout numbers in `viz_ancestors.css` with semantic CSS custom properties defined in a `:root` block.

**Architecture:** Single `:root` block prepended to `viz_ancestors.css`. Variables use semantic names (role, not palette). Two hex values (`#334155`, `#1e293b`) serve dual roles and require ordered sed passes — border uses replaced first, remaining uses replaced second.

**Tech Stack:** CSS custom properties. No build tools, no new files.

---

### Task 1: Add the `:root` block

**Files:**
- Modify: `viz_ancestors.css` (prepend after the `*` reset, before `body`)

- [ ] **Step 1: Insert the `:root` block**

Open `viz_ancestors.css`. After the closing `}` of the `*` reset block (line 5) and before `body {`, insert:

```css
:root {
    /* Backgrounds */
    --bg-app:     #0f172a;
    --bg-surface: #1e293b;
    --bg-hover:   #334155;

    /* Borders */
    --border:        #334155;
    --border-subtle: #1e293b;
    --border-deep:   #1e3a52;

    /* Text */
    --text-primary:   #f1f5f9;
    --text-label:     #e2e8f0;
    --text-light:     #cbd5e1;
    --text-secondary: #94a3b8;
    --text-muted:     #64748b;
    --text-disabled:  #475569;

    /* Blue accent */
    --accent:       #3b82f6;
    --accent-light: #93c5fd;
    --accent-bg:    #1e3a5f;
    --accent-hover: #bfdbfe;

    /* Danger */
    --danger:       #ef4444;
    --danger-light: #f87171;

    /* Godparent (green cluster) */
    --godparent:          #4ade80;
    --godparent-light:    #86efac;
    --godparent-bg:       #1e3a2f;
    --godparent-bg-hover: #1a3d2b;

    /* Emerald (copy/paste action buttons) */
    --emerald: #6ee7b7;

    /* Layout */
    --panel-w:         480px;
    --timeline-indent: 28px;
}
```

- [ ] **Step 2: Verify the block is in place**

```bash
grep -n "panel-w\|bg-app\|text-primary" viz_ancestors.css | head -5
```

Expected output — three lines showing the variables defined near the top of the file:
```
9:    --bg-app:     #0f172a;
21:    --text-primary:   #f1f5f9;
34:    --panel-w:         480px;
```
(Line numbers may differ slightly.)

---

### Task 2: Replace unambiguous colors (safe global substitutes)

These hex values each appear in only one semantic role throughout the file — a global replace is safe for all of them.

**Files:**
- Modify: `viz_ancestors.css`

- [ ] **Step 1: Replace all unambiguous hex values**

Run these sed commands in order (each is independent):

```bash
# Backgrounds
sed -i '' 's/#0f172a/var(--bg-app)/g' viz_ancestors.css

# Borders (deep)
sed -i '' 's/#1e3a52/var(--border-deep)/g' viz_ancestors.css

# Text colors
sed -i '' 's/#f1f5f9/var(--text-primary)/g' viz_ancestors.css
sed -i '' 's/#e2e8f0/var(--text-label)/g' viz_ancestors.css
sed -i '' 's/#cbd5e1/var(--text-light)/g' viz_ancestors.css
sed -i '' 's/#94a3b8/var(--text-secondary)/g' viz_ancestors.css
sed -i '' 's/#64748b/var(--text-muted)/g' viz_ancestors.css
sed -i '' 's/#475569/var(--text-disabled)/g' viz_ancestors.css

# Blue accent
sed -i '' 's/#3b82f6/var(--accent)/g' viz_ancestors.css
sed -i '' 's/#93c5fd/var(--accent-light)/g' viz_ancestors.css
sed -i '' 's/#1e3a5f/var(--accent-bg)/g' viz_ancestors.css
sed -i '' 's/#bfdbfe/var(--accent-hover)/g' viz_ancestors.css

# Danger
sed -i '' 's/#ef4444/var(--danger)/g' viz_ancestors.css
sed -i '' 's/#f87171/var(--danger-light)/g' viz_ancestors.css

# Godparent cluster
sed -i '' 's/#4ade80/var(--godparent)/g' viz_ancestors.css
sed -i '' 's/#86efac/var(--godparent-light)/g' viz_ancestors.css
sed -i '' 's/#1e3a2f/var(--godparent-bg)/g' viz_ancestors.css
sed -i '' 's/#1a3d2b/var(--godparent-bg-hover)/g' viz_ancestors.css

# Emerald
sed -i '' 's/#6ee7b7/var(--emerald)/g' viz_ancestors.css
```

- [ ] **Step 2: Verify none of the replaced values remain as raw hex**

```bash
grep -E '#(0f172a|1e3a52|f1f5f9|e2e8f0|cbd5e1|94a3b8|64748b|475569|3b82f6|93c5fd|1e3a5f|bfdbfe|ef4444|f87171|4ade80|86efac|1e3a2f|1a3d2b|6ee7b7)' viz_ancestors.css
```

Expected: no output. If any lines appear, re-run the sed command for that hex value.

---

### Task 3: Replace `#334155` (dual role: border and hover background)

`#334155` is used as both `border` color (27 times) and hover `background` (3 times: `#home-btn:hover`, `#search-results li:hover/.active`, `.lifespan-bar-track`). Replace border uses first, then remaining uses become hover backgrounds.

**Files:**
- Modify: `viz_ancestors.css`

- [ ] **Step 1: Replace all border uses first**

```bash
sed -i '' 's/solid #334155/solid var(--border)/g' viz_ancestors.css
```

- [ ] **Step 2: Replace remaining uses (hover backgrounds and bar track) with `--bg-hover`**

```bash
sed -i '' 's/#334155/var(--bg-hover)/g' viz_ancestors.css
```

- [ ] **Step 3: Verify no raw `#334155` remains**

```bash
grep '#334155' viz_ancestors.css
```

Expected: no output.

- [ ] **Step 4: Spot-check a border and a hover use look correct**

```bash
grep -A2 'home-btn:hover' viz_ancestors.css
grep -n 'border-bottom.*border\b' viz_ancestors.css | head -3
```

Expected for first command:
```css
#home-btn:hover {
    background: var(--bg-hover);
    color: var(--text-primary);
```

Expected for second: several lines like `border-bottom: 1px solid var(--border);`

---

### Task 4: Replace `#1e293b` (dual role: surface background and subtle border)

`#1e293b` is used as panel/modal backgrounds (`--bg-surface`) and as near-invisible row dividers (`--border-subtle`). One exception: `.evt-dot { border: 2px solid #1e293b }` is an intentionally invisible ring that matches the surface — it should use `--bg-surface`, not `--border-subtle`.

**Files:**
- Modify: `viz_ancestors.css`

- [ ] **Step 1: Replace all `solid #1e293b` border uses with `--border-subtle`**

```bash
sed -i '' 's/solid #1e293b/solid var(--border-subtle)/g' viz_ancestors.css
```

- [ ] **Step 2: Replace remaining `#1e293b` uses (backgrounds) with `--bg-surface`**

```bash
sed -i '' 's/#1e293b/var(--bg-surface)/g' viz_ancestors.css
```

- [ ] **Step 3: Fix the `.evt-dot` exception**

The `evt-dot` border is an invisible ring matching the panel background — it should use `--bg-surface`, not `--border-subtle`. Find and fix it:

```bash
grep -n 'evt-dot' viz_ancestors.css
```

Find the line `border: 2px solid var(--border-subtle);` inside `.evt-dot { ... }` and change it to:

```css
.evt-dot {
    position: absolute;
    left: -24px;
    top: 5px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 2px solid var(--bg-surface);
}
```

- [ ] **Step 4: Verify no raw `#1e293b` remains**

```bash
grep '#1e293b' viz_ancestors.css
```

Expected: no output.

---

### Task 5: Replace layout magic numbers

Two layout numbers are variablized: `480px` (panel width) and `28px` (timeline indent). The `60px` header fallback inside `var(--header-h, 60px)` is left as-is — extracting it would require the awkward `var(--header-h, var(--header-h-default))` syntax with no practical benefit.

**Files:**
- Modify: `viz_ancestors.css`

- [ ] **Step 1: Replace panel width**

`480px` appears once in `#detail-panel { width: 480px; }`. Replace it:

```bash
sed -i '' 's/width: 480px/width: var(--panel-w)/' viz_ancestors.css
```

- [ ] **Step 2: Replace timeline indent (positive)**

`padding-left: 28px` appears in `#detail-timeline`, `#detail-also-lived`, and `.timeline-section-label`:

```bash
sed -i '' 's/padding-left: 28px/padding-left: var(--timeline-indent)/g' viz_ancestors.css
```

- [ ] **Step 3: Replace timeline indent (negative)**

`.timeline-section-label` uses `margin: 18px 0 10px -28px` to pull back to the left edge. Replace the `-28px`:

```bash
sed -i '' 's/-28px/calc(-1 * var(--timeline-indent))/g' viz_ancestors.css
```

- [ ] **Step 4: Verify**

```bash
grep '480px\| 28px\|-28px' viz_ancestors.css
```

Expected: no output (all replaced).

```bash
grep 'panel-w\|timeline-indent' viz_ancestors.css | head -6
```

Expected — lines showing the variables in use:
```
    width: var(--panel-w);
    padding-left: var(--timeline-indent);
    padding-left: var(--timeline-indent);
    margin: 18px 0 10px calc(-1 * var(--timeline-indent));
    padding-left: var(--timeline-indent);
```

---

### Task 6: Final verification and commit

**Files:**
- No changes — verification only, then commit.

- [ ] **Step 1: Check no targeted hex values remain**

```bash
grep -Ei '#(0f172a|1e293b|334155|475569|64748b|94a3b8|cbd5e1|e2e8f0|f1f5f9|3b82f6|93c5fd|1e3a5f|bfdbfe|ef4444|f87171|4ade80|86efac|1e3a2f|1a3d2b|6ee7b7|1e3a52)' viz_ancestors.css
```

Expected: no output. If any remain, fix using the relevant sed command from Tasks 2–4.

- [ ] **Step 2: Check all variables are actually used (catch typos)**

```bash
grep -oE 'var\(--[^)]+\)' viz_ancestors.css | sort -u
```

Expected — all 25 variables appear: `var(--accent)`, `var(--accent-bg)`, `var(--accent-hover)`, `var(--accent-light)`, `var(--bg-app)`, `var(--bg-hover)`, `var(--bg-surface)`, `var(--border)`, `var(--border-deep)`, `var(--border-subtle)`, `var(--danger)`, `var(--danger-light)`, `var(--emerald)`, `var(--godparent)`, `var(--godparent-bg)`, `var(--godparent-bg-hover)`, `var(--godparent-light)`, `var(--panel-w)`, `var(--text-disabled)`, `var(--text-label)`, `var(--text-light)`, `var(--text-muted)`, `var(--text-primary)`, `var(--text-secondary)`, `var(--timeline-indent)`.

(Note: `--header-h` also appears — that's the JS-managed variable, expected.)

- [ ] **Step 3: Commit**

```bash
git add viz_ancestors.css
git commit -m "refactor(css): replace magic hex colors and layout numbers with CSS custom properties"
```
