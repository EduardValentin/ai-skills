---
name: visual-parity-verification
description: Use when verifying that changed UI surfaces render identically to a runnable reference such as a prototype app, or, when no runnable reference exists, consistently with credible production analogs, using browser computed style, geometry, and accessibility evidence recorded row by row in a caller-supplied parity ledger.
compatibility: >-
  Requires a running implementation UI, a running reference UI or named production analogs, browser automation able to evaluate scripts in both (host browser tooling, else Playwright), and a caller-supplied ledger or inventory. Without any of these, return BLOCKED naming the missing input.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Visual Parity Verification

## Overview

Compare the rendered implementation to its basis element by element, from
computed style and geometry extracted in a real browser, and record one
verdict per ledger row. Screenshots are context, never proof. Source files,
static mockups, hidden templates, Storybook-only renders and accessibility
scans cannot complete a comparison.

## When To Use

- A changed UI surface has a prototype or other runnable reference it must
  match exactly.
- A changed UI surface has no runnable reference and must be judged against
  credible production analogs of the same role.
- The caller supplies a parity ledger or an equivalent element inventory.

Do not use for broad rendered validation without a comparison basis; that is
ordinary visual validation.

## Inputs

- The ledger file to read and write. It records the viewport set and theme
  once at the top; each row names a route, a state, a production selector and
  a basis selector (the ledger's prototype selector column), and carries a
  `Verdict` and an `Evidence` column.
- URLs of the running implementation and the running reference, or the
  analog routes and selectors when no reference exists.
- The project's breakpoints, or the default viewport set below.

If the ledger is missing, return `BLOCKED` before any comparison and request
it. Do not scope the inventory yourself from screenshots or impressions.

## Basis

The basis is chosen from one observable fact:

- A runnable reference UI exists for the row: compare against it. Local
  preference never overrides the reference.
- No runnable reference exists for the row: compare against the closest
  credible production analog by role and purpose, or a reusable component
  contract or documented design constraint. Name the analog in the row's
  evidence. If no credible analog exists, mark the row `BLOCKED`.

## Matched Conditions

Render both sides with the same route, viewport width and height, browser
zoom, device scale factor, state, content, theme and any other condition that
could change the result. Record the exact values in the report. Default
viewport set when the project defines none: 320, 768, 1024, 1440 and 1920
pixels wide, plus one width just below and one just above each project
breakpoint.

## Evidence Standard

For every row and state, extract on both sides:

- Font family, size, weight, style, line height, letter spacing, text
  transform and decoration.
- Foreground color, effective background and opacity.
- Padding, margin, border, radius, shadow and outline.
- Display, flex and grid properties, alignment, gap, position and relevant
  overflow.
- Full geometry: x, y, top, right, bottom, left, width and height. Collect
  parent or sibling geometry separately when relative placement matters.
- Rendered transform.
- Semantic structure, accessible name and role, keyboard and focus behavior,
  relevant state, image alternatives and measured contrast.

The bundled `scripts/extract-element-style.browser.js` helper exposes
`globalThis.visualValidationExtractElementStyle`. Inject it unchanged into each
page and pass selectors as serialized evaluation arguments. Never interpolate
a selector into executable script text:

```javascript
const evidence = await page.evaluate(
  (selector) => globalThis.visualValidationExtractElementStyle(selector),
  selector,
);
```

Evidence status labels: `complete DOM evidence`, `partial DOM evidence`,
`degraded manual evidence`, `no comparison evidence`. Degraded evidence may
support a provisional `DRIFT` for a clearly visible defect with the missing DOM
confirmation stated; it can never support `MATCH` or `CLEAN`.

## Row Verdicts

Assign one verdict to each row and meaningful state and write it into the
ledger's `Verdict` column:

- `MATCH`: complete comparison evidence matches the basis on every collected
  property.
- `DRIFT`: a rendered difference exists.
- `MISSING`: a required rendered element exists on only one side.
- `BLOCKED`: required evidence or a credible basis is unavailable.

Write the extracted values that decided the verdict into the `Evidence`
column: the property, the basis value and the implementation value for a
`DRIFT`; the matched conditions for a `MATCH`; the missing input for a
`BLOCKED`. Leave no row `PENDING`.

Accessibility failures are findings even when the basis shares them; record
them in the report and keep the row's comparison verdict separate.
Inconclusive or unavailable accessibility checks are `BLOCKED`, not failures.
Check heading and semantic structure, names and roles, keyboard reachability
and order, visible focus, traps, image alternatives, icon-only control names,
relevant ARIA state and WCAG AA contrast (4.5:1 normal text, 3:1 large text
and UI components). For a non-solid background use a browser contrast
analyzer; never estimate contrast visually.

## Global Verdict

Apply in this order:

1. `FINDINGS` when any row is `DRIFT` or `MISSING`, or accessibility has a
   confirmed failure.
2. `BLOCKED` when no finding is established but a required row or check is
   blocked, only degraded evidence exists, or the status is `no comparison
   evidence`.
3. `CLEAN` only with complete DOM evidence, every row `MATCH`, every required
   accessibility check complete and passing, and no visible in-scope element
   missing from the ledger.

Cross-check the live DOM for visible in-scope elements the ledger omits. Add
each as a new row marked with its provenance gap, assess it, and report it.

## Rechecks

After the implementation owner fixes rows, rerun every prior `DRIFT`,
`MISSING` and `BLOCKED` row, every row whose implementation files changed, and
their affected states, under the original matched conditions. When a shared
primitive, global style, token or theme changed, rerun every row. Return a
delta that distinguishes resolved, remaining and new findings. A fix
description is not proof.

## Report

Return the ledger path with the updated rows, then:

```markdown
# Visual parity verification — <surface>

## Verdict
- <CLEAN | FINDINGS | BLOCKED>

## Evidence status
- <complete DOM evidence | partial DOM evidence | degraded manual evidence | no comparison evidence>

## Basis
- <reference URL and routes, or analog routes and why they are credible>

## Matched conditions
- viewport: <width x height> | zoom: <percent> | device scale: <factor> | theme: <theme>

## Ledger rows written
- <count MATCH> MATCH | <count DRIFT> DRIFT | <count MISSING> MISSING | <count BLOCKED> BLOCKED

## Findings
- **P1** | severity: <blocker / major / minor> | ledger row <id> | <property or measurement diff> | evidence: <basis value vs implementation value>

## Accessibility findings
- **A1** | severity: <blocker / major / minor> | ledger row <id> | <check> | WCAG criterion | suggested fix

## Ledger provenance gaps
- <rows added for visible in-scope elements the ledger omitted, or None>

## Blockers
- <None, or blocked row and minimum next input>

## Rerun delta
- <None, or resolved, remaining and new rows>
```

Write explicit `None` in every empty section.

## Forbidden Behaviors

- Declaring `CLEAN` from screenshots, source files or visual impression.
- Skipping DOM evaluation because the UI looks right.
- Leaving a ledger row `PENDING` or blank.
- Interpolating selectors into script text.
- Fixing implementation code while acting as the verifier.
