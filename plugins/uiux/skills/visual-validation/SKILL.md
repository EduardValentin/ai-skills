---
name: visual-validation
description: Use when validating frontend UI changes, screenshots, responsive layouts, visual regressions, accessibility states, browser-rendered pages, canvas/3D output, breakpoint behavior, overflow, clipping, contrast, focus states, or broad visual quality against screenshots, design notes, tokens, or surrounding product aesthetics.
---

# Visual Validation

## Overview

Do not declare visual work complete from code inspection alone. Validate the rendered interface through screenshots or live browser inspection, then fix what the evidence shows.

## When To Use

- Validating frontend UI changes, screenshots, responsive layouts, visual regressions, or breakpoint behavior.
- Checking overflow, clipping, focus states, contrast, visual parity, canvas/3D output, or browser-rendered states.
- A task is ready to be judged by rendered evidence rather than source inspection alone.

## Minimum Checklist

For responsive grid or card changes, every validation plan, blocker report, or completion report must name the minimum visual smell checklist: grid/card axis alignment, overflow, clipping, hidden or non-wrapping text, overlap, inconsistent sibling sizing, sibling color consistency, focus states, contrast, motion, and spacing.

## Capture Ladder

Use the highest available capability:

1. Native browser/screenshot capability in the current environment.
2. Browser automation through the shell using the project's existing tooling.
3. A small temporary script that opens the local app and captures screenshots.
4. User-provided screenshots when automation is unavailable.

If none of these is possible, report the blocker instead of claiming visual confidence.

If validation is delayed or cannot be completed in the current turn, say what is blocked, record the residual risk, and still list the concrete viewport/state matrix and visual smell families that must be checked next. Waiting for a slow server is acceptable; claiming visual confidence before rendered evidence is not.

## Viewport Matrix

Use the product's configured breakpoints when available. At minimum cover:

- 320px wide mobile.
- Just below and just above each configured breakpoint.
- A common desktop width.
- A wide desktop width around 1920px.

For stateful UI, capture the relevant states: default, loading, empty, error, disabled, focused, expanded, selected, and long-content cases.

## What To Check

In a validation plan or report, name the relevant visual smell families instead of summarizing them as "layout issues." Do not limit the checklist to risks named by the caller. For responsive grids and cards, explicitly include alignment, overflow, clipping, hidden or non-wrapping text, overlap, inconsistent sibling sizing or colors, focus states, contrast, motion, and spacing.

- No unintended horizontal scroll, clipping, overlap, 0-height sections, or broken alignment.
- Repeated items align on shared axes. In grids, card titles, media, controls, and baselines should not drift up, down, left, or right unless the layout intentionally varies them.
- Text remains readable and visible. Watch for labels, headings, buttons, cards, and long strings that overflow, are cut off by hidden overflow, cannot wrap, wrap awkwardly, or disappear behind adjacent UI.
- Related sibling elements use consistent sizing, spacing, color roles, icon sizes, border radii, and visual weight unless a visible state or hierarchy explains the difference.
- Interactive controls have visible focus, hover, active, selected, and disabled states.
- Color contrast works for key text and controls.
- Keyboard order matches visual order.
- Motion does not block use and respects reduced-motion preferences.
- New surfaces visually fit nearby product surfaces: same density logic, alignment rhythm, type scale, color roles, and component proportions.

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

When evidence is still pending, do not write only `pending`. Fill the same fields with the planned matrix and the minimum unverified smell list: grid/card axis alignment, overflow, clipping, hidden or non-wrapping text, overlap, sibling sizing, sibling colors, focus states, contrast, motion, and spacing.

## Done Means

Every visual finding has either been fixed and rechecked, or explicitly handed back with the reason it cannot be verified in the current environment.
