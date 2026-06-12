---
name: visual-validation
description: Use when validating frontend UI changes, screenshots, responsive layouts, visual regressions, accessibility states, browser-rendered pages, canvas/3D output, breakpoint behavior, overflow, clipping, contrast, focus states, or broad visual quality against screenshots, design notes, tokens, or surrounding product aesthetics.
---

# Visual Validation

## Overview

Do not declare visual work complete from code inspection alone. Validate the rendered interface through screenshots or live browser inspection, then fix what the evidence shows.

## Capture Ladder

Use the highest available capability:

1. Native browser/screenshot capability in the current environment.
2. Browser automation through the shell using the project's existing tooling.
3. A small temporary script that opens the local app and captures screenshots.
4. User-provided screenshots when automation is unavailable.

If none of these is possible, report the blocker instead of claiming visual confidence.

## Viewport Matrix

Use the product's configured breakpoints when available. At minimum cover:

- 320px wide mobile.
- Just below and just above each configured breakpoint.
- A common desktop width.
- A wide desktop width around 1920px.

For stateful UI, capture the relevant states: default, loading, empty, error, disabled, focused, expanded, selected, and long-content cases.

## What To Check

- No unintended horizontal scroll, clipping, overlap, 0-height sections, or broken alignment.
- Text remains readable and fits its container.
- Interactive controls have visible focus, hover, active, selected, and disabled states.
- Color contrast works for key text and controls.
- Keyboard order matches visual order.
- Motion does not block use and respects reduced-motion preferences.
- The UI matches the intended screenshots, design notes, token system, or surrounding product aesthetic.

## Report Format

Return concise evidence:

```markdown
Visual validation:
- Viewports checked: <list>
- States checked: <list>
- Findings: <none or bullets with screenshot/viewport/state>
- Fixes applied: <summary or none>
- Residual risk: <anything not observable>
```

## Done Means

Every visual finding has either been fixed and rechecked, or explicitly handed back with the reason it cannot be verified in the current environment.
