---
name: visual-validation
description: Use when validating frontend UI changes by rendered evidence, including screenshots, responsive layouts, breakpoint behavior, visual regressions, overflow, clipping, hidden or non-wrapping text, contrast, focus states, accessibility states, motion, canvas or 3D output, and broad visual quality of a browser-rendered page without a comparison basis.
compatibility: >-
  Requires native browser or screenshot tooling, project browser automation, an approved temporary capture script, or user screenshots; otherwise report a blocker and residual risk. Measurable checks use the `ui-ux-guidelines` validators; when they are unavailable, measure computed values by hand or mark those checks unverified. Comparison against a reference belongs to `visual-parity-verification`.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Visual Validation

Judge visual work from rendered evidence, never from code inspection alone. This skill is the procedure; the rules and thresholds it checks belong to `ui-ux-guidelines`.

Comparison against a prototype or reference is `visual-parity-verification`.

## Viewports And States

Use the product's configured breakpoints. Cover at least 320px, a width just below and just above each breakpoint, a common desktop width, and about 1920px.

Enumerate the supported states the change affects, such as default, loading, empty, error, disabled, focused, expanded, selected and long content. Check each or mark it unverified; record unsupported states as not applicable with a reason.

## Measure

Run the `ui-ux-guidelines` validators on every affected page, passing the viewport widths with `--viewports`. They decide contrast, target size and gap, reflow, line length, body font size, labels, names and image alternatives. Every violation is a finding. A validator that did not run leaves its checks unverified.

## Capture Ladder

Use the highest available capability:

1. Native browser or screenshot capability in the current environment.
2. Browser automation through the shell using the project's existing tooling.
3. A small temporary script that opens the local app and captures screenshots.
4. User-provided screenshots.

If none is possible, report the blocker, the residual risk, and the viewport, state and check coverage still required.

## Evidence Boundaries

- Screenshots establish layout, wrapping, clipping, overlap, spacing, color consistency and the look of a captured state.
- Live interaction or automation is required for keyboard order, focus transitions, hover or active behavior and state changes.
- Contrast claims require the validator or computed colors; on a non-solid background use a browser contrast analyzer. Never estimate visually.
- Motion claims require live observation with the reduced-motion preference emulated.
- Canvas or 3D claims require visible-pixel evidence and resize checks.

Name the evidence source for each check. Anything outside that evidence is unverified.

## Inspect

Check what the validators cannot measure, and name each family checked instead of summarizing as "layout issues". Do not limit the list to risks the caller named.

- Clipping, overlap, zero-height sections and broken alignment.
- Repeated items share axes: titles, media, controls and baselines do not drift.
- Text stays visible: nothing cut off, unable to wrap, awkwardly wrapped or hidden behind adjacent UI.
- Siblings match in size, spacing, color role, icon size, radius and weight unless state or hierarchy explains the difference.
- Controls show focus, hover, active, selected and disabled states.
- Keyboard order matches visual order; no traps.
- Heading structure, roles and relevant ARIA state are correct.
- Motion does not block use.
- New surfaces match nearby ones in density, rhythm, type scale, color roles and proportions.

Give accessibility findings a WCAG criterion. Record inconclusive checks as unverified, not as failures.

## Fixes And Rechecks

Fix findings and recheck when implementation changes are in scope. A report-only verifier returns findings to the implementation owner. After a fix, rerun the validators, recapture the affected viewports and states, and report the delta.

## Report Format

```markdown
Visual validation:
- Validators: <contrast exit code, geometry exit code, or unverified with reason>
- Evidence: <browser, automation, measurements, and artifacts used>
- Viewports checked: <list>
- States checked: <list>
- Planned or unverified viewports: <list or none>
- Planned or unverified states: <list or none; include justified not-applicable states>
- Findings: <none, or bullets with viewport, state, evidence, rule and severity blocker / major / minor>
- Fixes and rechecks: <summary or none>
- Residual risk: <anything not observable>
```

## Done Means

Every finding is fixed and rechecked, or handed back with the reason it cannot be verified here. Every affected viewport and state is checked or named as residual risk.
