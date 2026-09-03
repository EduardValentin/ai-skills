---
name: visual-validation
description: Use when validating frontend UI changes by rendered evidence, including screenshots, responsive layouts, breakpoint behavior, visual regressions, overflow, clipping, hidden or non-wrapping text, contrast, focus states, accessibility states, motion, canvas or 3D output, and broad visual quality of a browser-rendered page without a comparison basis.
compatibility: >-
  Rendered validation requires native browser or screenshot tooling, project browser automation, an approved temporary capture script, or user screenshots; otherwise report a blocker and residual risk instead of claiming visual confidence. Comparison against a reference belongs to the separate `visual-parity-verification` skill.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Visual Validation

## Overview

Do not declare visual work complete from code inspection alone. Validate the
rendered interface through screenshots or live browser inspection, then fix
what the evidence shows.

## When To Use

- Validating frontend UI changes, screenshots, responsive layouts, visual
  regressions or breakpoint behavior.
- Checking overflow, clipping, focus states, contrast, motion, canvas or 3D
  output, or browser-rendered states.
- A task is ready to be judged by rendered evidence rather than source
  inspection alone.

Do not use for comparing a surface against a prototype or reference; that is
`visual-parity-verification`.

## Minimum Checklist

For responsive grid or card changes, every validation plan, blocker report or
completion report must name the minimum visual smell checklist: grid and card
axis alignment, overflow, clipping, hidden or non-wrapping text, overlap,
inconsistent sibling sizing, sibling color consistency, focus states,
contrast, motion and spacing.

## Capture Ladder

Use the highest available capability:

1. Native browser or screenshot capability in the current environment.
2. Browser automation through the shell using the project's existing tooling.
3. A small temporary script that opens the local app and captures
   screenshots.
4. User-provided screenshots when automation is unavailable.

If none is possible, report the blocker instead of claiming visual confidence.
If validation cannot complete in the current turn, say what is blocked, record
the residual risk, and list the viewport, state and visual-smell coverage still
required.

## Evidence Boundaries

- Screenshots establish visible layout, wrapping, clipping, overlap, spacing,
  color consistency and the appearance of a captured state.
- Live interaction or browser automation is required for keyboard order, focus
  transitions, hover or active behavior and state changes.
- Contrast claims require computed colors or a contrast measurement.
- Motion claims require live observation with the reduced-motion preference
  emulated.
- Canvas or 3D claims require visible-pixel evidence and resize checks; a
  present canvas element is not proof of rendered output.

Name the evidence source for each completed check. Treat anything outside that
evidence as unverified.

## Viewport Matrix

Use the product's configured breakpoints when available. At minimum cover a
320px-wide mobile viewport, a width just below and just above each configured
breakpoint, a common desktop width, and a wide desktop width around 1920px.

For stateful UI, enumerate the supported states affected by the change, such
as default, loading, empty, error, disabled, focused, expanded, selected and
long-content cases. Check each affected state or mark it unverified. Record
unsupported states as not applicable with a brief reason.

## What To Check

Name the relevant visual smell families instead of summarizing them as
"layout issues", and do not limit the checklist to risks named by the caller.

- No unintended horizontal scroll, clipping, overlap, zero-height sections or
  broken alignment.
- Repeated items align on shared axes; card titles, media, controls and
  baselines do not drift unless the layout intentionally varies them.
- Text remains readable and visible: no labels, headings, buttons or long
  strings that overflow, are cut off, cannot wrap, wrap awkwardly or disappear
  behind adjacent UI.
- Related siblings use consistent sizing, spacing, color roles, icon sizes,
  radii and visual weight unless a visible state or hierarchy explains the
  difference.
- Interactive controls have visible focus, hover, active, selected and
  disabled states.
- Color contrast works for key text and controls.
- Keyboard order matches visual order.
- Motion does not block use and respects reduced-motion preferences.
- New surfaces fit nearby product surfaces: density, alignment rhythm, type
  scale, color roles and component proportions.

## Accessibility

Check heading and semantic structure, names and roles, keyboard reachability
and order, visible focus, traps, image alternatives, icon-only control names,
relevant ARIA state and WCAG AA contrast: 4.5:1 for normal text, 3:1 for large
text and UI components. For a non-solid rendered background use a browser
contrast analyzer; never estimate contrast visually. Record confirmed
failures as findings with a WCAG criterion; record inconclusive or
unavailable checks as unverified, not as failures.

## Fixes and Rechecks

This skill may fix findings and recheck them when implementation changes are
in scope. A report-only delegated verifier returns findings for the
implementation owner instead. After a fix, recapture the affected viewports
and states and report the delta.

## Report Format

```markdown
Visual validation:
- Evidence: <browser, automation, measurements, and artifacts used>
- Viewports checked: <list>
- States checked: <list>
- Planned or unverified viewports: <list or none>
- Planned or unverified states: <list or none; include justified not-applicable states>
- Findings: <none or bullets with screenshot/viewport/state>
- Accessibility findings: <none or bullets with severity, WCAG criterion and evidence>
- Fixes and rechecks: <summary or none>
- Residual risk: <anything not observable>
```

When evidence is still pending, report `none` for checks that did not occur
and fill the planned fields with the required matrix and minimum smell list.

## Done Means

Every visual finding has been fixed and rechecked with appropriate evidence,
or explicitly handed back with the reason it cannot be verified in the current
environment. Every affected supported viewport and state is checked or remains
clearly identified as residual risk.
