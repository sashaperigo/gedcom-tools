# CSS Custom Properties for viz_ancestors.css

**Date:** 2026-04-20
**Goal:** Replace magic hex colors and layout numbers in `viz_ancestors.css` with semantic CSS custom properties to enable future theming.

## Approach

Add a single `:root` block at the top of `viz_ancestors.css`. No new files, no build changes. Variables use semantic names (describing role, not palette value) so a dark→light theme swap or color scheme change only requires editing `:root`.

Dual-role values (`#334155` is both `--border` and `--bg-hover`, `#1e293b` is both `--bg-surface` and `--border-subtle`) get separate variables with the same initial value. This is intentional — they'll diverge when themed.

## Variable Set

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

## What Stays as Literals

One-off accent colors with no reuse and no semantic cluster are left as hex literals:

| Value | Where used |
|---|---|
| `#fff` | Modal save button text |
| `#fde68a` | Note card link |
| `#fca5a5` | Shared note card link |
| `#f59e0b` | Edit-source warning text |
| `#e8a0be` | Female sex indicator |
| `#a78bfa` | Event convert button hover |
| `#7dd3fc` | Citation tag color |
| `#7db4e8` | Male sex indicator |
| `#6ee37a` | Nationality fact pill |
| `#3d6642` | Nationality pill date text |

## Out of Scope

- `--header-h` is already a CSS variable set by JS — no change needed.
- Font sizes, spacing, and border-radius values are not variablized (high count but low theming value).
- No separate variables file; everything stays in `viz_ancestors.css`.
