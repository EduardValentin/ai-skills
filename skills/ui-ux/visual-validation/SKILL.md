---
name: visual-validation
description: Use when validating frontend UI changes, screenshots, responsive layouts, visual regressions, accessibility states, browser-rendered pages, canvas/3D output, breakpoint behavior, overflow, clipping, contrast, focus states, broad visual quality, or parity and consistency against runnable references, design notes, tokens, or credible production analogs.
compatibility: >-
  Rendered validation requires native browser/screenshots, project browser automation, an approved temporary capture script, or user screenshots; otherwise report a blocker and residual risk. For DOM comparison, prefer host browser automation and fall back to Playwright. Parity requires runnable implementation and reference UIs. The optional `uiux-verifier` may scope the inventory; without it, use a supplied inventory or caller-authorized in-session scoping, otherwise return BLOCKED.
metadata:
  status: experimental
  allows_tool_references: "true"
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

If validation is delayed or cannot be completed in the current turn, say what is blocked, record the residual risk, and list the concrete viewport, state, and visual-smell coverage still required. Waiting for a slow server is acceptable; claiming visual confidence before rendered evidence is not.

## Evidence Boundaries

Match each claim to evidence that can establish it:

- Screenshots can establish visible layout, wrapping, clipping, overlap, spacing, color consistency, and the appearance of a captured state.
- Live interaction or browser automation is required to establish keyboard order, focus transitions, hover or active behavior, and state changes.
- Contrast claims require computed colors or a contrast measurement, not visual estimation from a screenshot alone.
- Motion claims require live observation or automation with the relevant reduced-motion preference emulated.
- Canvas or 3D claims require visible-pixel evidence and resize checks; a present canvas element is not proof of rendered output.

Name the evidence source for each completed check. Treat anything outside that evidence as unverified.

## Viewport Matrix

Use the product's configured breakpoints when available. At minimum cover:

- 320px wide mobile.
- Just below and just above each configured breakpoint.
- A common desktop width.
- A wide desktop width around 1920px.

For stateful UI, enumerate the supported states affected by the change, such as default, loading, empty, error, disabled, focused, expanded, selected, and long-content cases. Check each affected state or mark it unverified. Record unsupported states as not applicable with a brief reason instead of implying they passed or making every example mandatory.

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

## Structured Comparison Mode

Use this mode only when the request asks for either:

- **Parity** against a readable runnable reference UI.
- **Consistency** against credible production analogs when no runnable reference exists.

For ordinary visual validation, keep the workflow lighter: use the capture
ladder, viewport and state coverage, visual-smell checks, fixes, and the
standard report. Do not require a matched-element inventory or comparison
verdict matrix when neither parity nor consistency applies.

### Scope and provenance

Before comparison, create an affected-element inventory with one row for every
affected element and meaningful state. Start from supplied task details,
acceptance criteria, approved artifacts, changed UI files, routes, state maps,
reference locators, implementation locators, and live DOM inspection. Record
the provenance for every row.

Use a caller-supplied inventory when available. The optional `uiux-verifier`
native agent may provide delegated scoping. If neither exists, perform
best-effort in-session scoping only when the caller authorizes it. Without an
inventory or authorized scoping basis, return `BLOCKED` before normal
comparison and request the minimum missing input.

Do not derive scope solely from screenshots or visual impressions. Cross-check
the live DOM for visible in-scope elements omitted from supplied artifacts.
Add each omission to the inventory, assess it, and report it as an inventory
provenance gap. Document approved divergences with their source; approval for
one property does not exempt the rest of the row.

### Basis and matched conditions

In parity mode, compare the rendered implementation to the runnable reference;
local preference does not override that basis. In consistency mode, identify
the closest credible production analog by role and purpose, or use a reusable
component contract or documented design constraint. If no credible basis
exists for a required row, mark that row `BLOCKED` rather than inventing one.

Render both sides with matched route, viewport width and height, browser zoom,
device scale factor, state, content, theme, and other conditions that could
change the result. Record the exact viewport, zoom, device scale factor, and
state in the report.

### Evidence standard

DOM extraction is primary comparison evidence. Accessibility evidence is
separately required. Screenshots are secondary context and visual
cross-checking; screenshots, source files, hidden templates, static mockups,
Storybook-only renders, Lighthouse, or accessibility scans alone cannot
complete comparison mode.

For each row and state, collect:

- Font family, size, weight, style, line height, letter spacing, text
  transform, and decoration.
- Foreground color, effective background, and opacity.
- Padding, margin, border, radius, shadow, and outline.
- Display, flex/grid properties, alignment, gap, position, and relevant
  overflow.
- Full geometry: `x`, `y`, `top`, `right`, `bottom`, `left`, `width`, and
  `height`; collect parent or sibling geometry separately when relative
  placement matters.
- Rendered transform.
- Semantic structure, accessible name and role, keyboard and focus behavior,
  relevant state, image alternatives, and measured contrast.

The bundled `scripts/extract-element-style.browser.js` helper exposes
`globalThis.visualValidationExtractElementStyle`. Inject the helper unchanged
and pass selectors as serialized evaluation arguments. Never interpolate a
selector into executable script text:

```javascript
const evidence = await page.evaluate(
  (selector) => globalThis.visualValidationExtractElementStyle(selector),
  selector,
);
```

Use the evidence-status labels `complete DOM evidence`, `partial DOM evidence`,
`degraded manual evidence`, or `no comparison evidence`. Use
`no comparison evidence` when comparison cannot start or zero comparison
evidence was collected. Caller-authorized degraded evidence may support a
provisional finding for a clearly visible defect, with the missing DOM
confirmation stated, but it can never support `CLEAN`.

### Row and global verdicts

Required cells cannot be blank; use `not applicable` with a reason. Assign one
verdict to each row and meaningful state:

- `MATCH`: complete comparison evidence matches the basis, except for a
  documented approved divergence whose other properties match.
- `DRIFT`: an unapproved rendered difference exists.
- `MISSING`: a required rendered element exists on only one side or is absent
  from the implementation.
- `BLOCKED`: required evidence or a credible comparison basis is unavailable.

The row verdict answers the comparison question. A shared accessibility defect
can leave a row as `MATCH` while still producing an accessibility finding and
a global `FINDINGS` verdict.

Apply global verdict precedence in this order:

1. `FINDINGS` when any row is `DRIFT` or `MISSING`, or accessibility has a
   confirmed failure. Report any blocked checks as evidence gaps too.
2. `BLOCKED` when no finding is established but a required row or check is
   blocked, only degraded manual evidence exists, or the status is
   `no comparison evidence`.
3. `CLEAN` only with complete DOM evidence, all rows `MATCH`, every required
   accessibility check complete and passing, no accessibility findings, and
   no unresolved provenance gap.

Confirmed accessibility failures are findings even when the reference has the
same defect. Inconclusive or unavailable accessibility checks are `BLOCKED`,
not failures. Check heading and semantic structure, names and roles, keyboard
reachability and order, visible focus, traps, image alternatives, icon-only
control names, relevant ARIA state, and WCAG AA contrast. Use `4.5:1` for
normal text and `3:1` for large text and UI components. For a non-solid
rendered background, use a browser contrast analyzer; never estimate contrast
visually.

### Fixes and targeted rechecks

This skill may fix findings and recheck them when implementation changes are in
scope. A report-only delegated verifier may instead return findings for the
implementation owner; that local boundary does not make this skill globally
report-only.

After a fix, rerun prior finding rows, rows affected by changed implementation
files, and their affected states. Recollect computed styles, full geometry,
screenshots, and accessibility evidence under the original matched conditions,
then return a delta inventory that distinguishes resolved, remaining, and new
findings. A fix description is not proof.

Expand the rerun to every affected inventory row, state, and viewport when a
shared layout primitive, shared component, global style, theme token, or other
broad dependency changed.

### Comparison report

Alongside the standard visual-validation fields, include:

- Global verdict: `CLEAN`, `FINDINGS`, or `BLOCKED`.
- Mode, evidence status, comparison basis, and matched route, viewport, browser
  zoom, device scale factor, and states.
- The completed affected-element inventory and its provenance.
- One row per element and state with `Pair`, `Font`, `Color`, `Box`, `Layout`,
  `Geometry`, `Transform`, `Accessibility`, and `Verdict`.
- Stable finding IDs such as `VV-1`, affected row and state, expected basis,
  observed result, evidence, and user impact.
- Accessibility findings and blocked accessibility checks.
- Inventory provenance gaps, out-of-scope flags, patterns to codify, blockers
  and minimum next input, fixes and rechecks, and residual risk.

Write explicit `None` for empty comparison sections. Do not move visual drift
into a recommendations-only bucket.

## Report Format

Return concise evidence:

```markdown
Visual validation:
- Evidence: <browser, automation, measurements, and artifacts used>
- Viewports checked: <list>
- States checked: <list>
- Planned or unverified viewports: <list or none>
- Planned or unverified states: <list or none; include justified not-applicable states when useful>
- Findings: <none or bullets with screenshot/viewport/state>
- Fixes and rechecks: <summary or none>
- Residual risk: <anything not observable>
```

When evidence is still pending, do not write only `pending` and do not put planned coverage under checked fields. Report `none` for checks that did not occur, then fill the planned or unverified fields with the required matrix and minimum smell list: grid/card axis alignment, overflow, clipping, hidden or non-wrapping text, overlap, sibling sizing, sibling colors, focus states, contrast, motion, and spacing.

## Done Means

Every visual finding has either been fixed and rechecked with appropriate evidence, or explicitly handed back with the reason it cannot be verified in the current environment. Every affected supported viewport and state is checked or remains clearly identified as residual risk.
