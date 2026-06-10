---
name: ui-verification
description: Use when a request asks for UI verification, UI/UX verification, frontend UI review, visual parity, or visual consistency of implemented UI and needs a structured CLEAN/FINDINGS/BLOCKED verdict, matched-element inventory, DOM computed-style or bounding-rect evidence, accessibility states, or scoped reruns after visual findings.
---

# UI Verification

## Overview

Visual review is evidence work, not taste work. Verify rendered UI by pairing visible elements, extracting DOM computed styles and bounding boxes, checking screenshots only as secondary evidence, and reporting a compact inventory with findings. Visual verification checks the rendered user-visible outcome and every visually meaningful state, not hidden templates or implementation proxies.

## When To Use

- A frontend change needs to match a runnable prototype, reference app, design implementation, or `designs/` React app.
- A frontend change has no runnable reference but should match existing production sibling or analog elements.
- A visual review needs matched-element inventory coverage, computed-style comparison, bounding-rect comparison, accessibility checks, or a scoped rerun after fixes.

## Required Capabilities

- Ability to execute shell commands for app startup or browser automation fallback.
- Ability to inspect a live browser page by navigating, changing viewport, evaluating JavaScript in the page, capturing element screenshots, and exercising keyboard/focus states.
- Read access to the production UI. Parity mode also requires read access to the runnable reference UI.

If a capability is unavailable, follow the fallback chain below. Do not replace DOM evidence with visual impressions.

## Inputs

Expect as many of these as the caller can provide:

- Task context: title, description, requirements, acceptance criteria, non-goals, and approved design or implementation notes.
- Review mode if known: `parity` or `consistency`.
- Full diff or changed UI file list.
- Production route/URL and important states to exercise.
- For parity mode: reference route/URL, prototype/reference element rows, and any approved divergences.
- For consistency mode: expected production siblings, analog routes, reusable component patterns, or design-system constraints if known.
- Caller-supplied affected surface map if available, production locators or changed UI files, relevant routes/states, and prior local evidence such as screenshots, a11y scans, or manual notes.

Treat prior evidence as context, not as gate completion.

Important states means every visually meaningful user-visible state named by the task, approved artifacts, runnable reference, changed UI, or adjacent feature surface. Hidden templates, implementation-only component variants, and proxy render targets do not count as state coverage.

## Inventory Scoping

UI verification requires an affected-element inventory before normal verification starts.

If the caller did not provide an affected-element or matched-element inventory, produce or obtain one before normal verification. Prefer delegated scoping when available; otherwise return `BLOCKED` unless the caller explicitly requests best-effort in-session scoping from the ticket description, acceptance criteria, approved artifacts, diff or changed UI files, routes and states, and the reference or production comparison basis. The verifier may refine the scoped inventory during live DOM inspection, but must not skip the scoping step or invent an inventory from visual impressions alone.

## Mode Selection

- **Parity mode**: use when a runnable prototype, reference app, design implementation, or `designs/` React app is available. The reference is the visual source of truth.
- **Consistency mode**: use when no runnable reference is available. Existing production siblings, analog elements, reusable components, and documented design constraints are the comparison basis.

If the caller does not name a mode, choose parity when a runnable reference URL/path is supplied; otherwise choose consistency. If neither a reference nor credible production analogs can be identified, return `BLOCKED` or a clearly degraded evidence status instead of inventing a visual basis.

## Browser Bootstrap

Prefer the host's native browser automation if it can navigate, set viewport, capture element screenshots, and evaluate JavaScript in the page. If that is unavailable, drive Playwright through the shell and inject `scripts/extract-element-style.browser.js` via page evaluation. If neither is available, save the renderable page or screenshots to disk and ask the user for visual confirmation; mark the evidence status **degraded manual evidence**. CLEAN requires complete DOM evidence; degraded evidence returns BLOCKED unless the caller explicitly requested best-effort. If even that fallback cannot run, return `UI verification cannot proceed` with the blocker and required input.

## Output Format

Return Markdown:

```markdown
# UI verification — <task or surface>

## Verdict
- [ ] CLEAN — no visual or accessibility findings
- [ ] FINDINGS — at least one visual or accessibility finding
- [ ] BLOCKED — review could not proceed

## Review mode
- <parity | consistency>

## Evidence status
- <complete DOM evidence | degraded manual evidence | blocked>

## Comparison basis
- <reference URL/route and source-of-truth notes, or production analog routes/elements and why they are credible>

## States covered
- <state> | viewport widths: <list, including pre/post-breakpoint widths> | evidence: <DOM extraction / screenshot / keyboard path>

## Matched-element inventory
| Pair | Basis selector | Production selector | font-* | color/bg | box | layout | size | verdict |
|---|---|---|---|---|---|---|---|---|
| <basis locator> <-> <production locator> | <reference or analog selector> | <implemented selector> | <actual extracted values> | <actual extracted values> | <actual extracted values> | <actual extracted values> | <actual extracted values> | <MATCH / DRIFT / MISSING> |

### Inventory provenance gaps
_(list visible in-scope elements observed during verification that were missing from caller-supplied affected surfaces or approved artifacts)_
- `<locator>` | <element type> | <one-line description> | suggested provenance gap: <scope map / plan / rendered conditional state>

## Visual findings
- **V1** | severity: <blocker / major / minor> | `<production selector>` <-> `<basis selector>` | <property or measurement diff> | evidence: <computed-style snippet or bounding-rect numbers> | suggested fix

## Accessibility findings
- **A1** | severity: <blocker / major / minor> | `<selector>` | <semantic structure / ARIA / focus order / keyboard reach / contrast / alt text> | WCAG criterion | suggested fix

## Out-of-scope flags
- **O1** | `<path:line>` | <suspected behavior or implementation-quality issue> | flagged for: <caller follow-up / behavior verification / implementation review>

## Patterns to codify next time
- <one-line declarative candidate rule> | rationale: <one sentence>
```

Any visual finding flips the verdict to FINDINGS. Do not create a "recommendations only" bucket for visual drift.

## Parity Mode

Use when a runnable prototype/reference app exists.

1. Start or open both production and reference apps. Match route, state, viewport, device scale, and browser zoom before each comparison.
2. Use the supplied inventory, or the scoped inventory produced from the ticket description and diff, as the starting matched-element inventory. Refine it with prototype/reference rows, changed UI files, approved artifacts, and live DOM inspection. Do not ask the caller to prebuild it.
3. For each inventory row and state, locate the rendered DOM atoms in both apps, capture element-level screenshots, evaluate `scripts/extract-element-style.browser.js`, fill every computed-style cell, and set verdict to MATCH, DRIFT, or MISSING.
4. Compare font, color/background, padding/margin/border/radius/shadow/outline, display/flex/gap/position, width/height, and transform. Different numbers mean rendered drift unless an approved artifact explicitly accepted the divergence.
5. Compare parent and sibling geometry with bounding rects, especially for rows sharing a parent declaration.
6. While verifying, cross-check both DOMs for visible elements absent from the caller-supplied affected surface map or approved artifacts. Add those to `Inventory provenance gaps`; never silently drop them.
7. Use screenshots as a redundant visual check after numeric extraction, not as primary evidence.

Parity mode is clean only when the inventory covers caller-supplied affected surfaces if any and observed changed elements, every row has non-blank computed values, no unexplained observed rows are missing from the report, all drift has findings, and accessibility checks are complete.

## Consistency Mode

Use when there is no runnable reference and the implemented UI should fit existing production patterns.

1. Start or open the production app and any relevant analog routes/states. Match viewport, device scale, and browser zoom before comparing.
2. Use the supplied inventory, or the scoped inventory produced from the ticket description and diff, as the starting matched-element inventory. Refine it with changed UI files, live DOM inspection, reusable component usage, and credible production sibling or analog elements.
3. For each implemented element, pair it with the closest production analog by role and purpose: same component family, same route region, same interaction pattern, or same documented token/component contract.
4. Extract DOM computed styles and bounding rects for both the implemented element and its analog. Fill every inventory cell; do not rely on "looks consistent" prose.
5. Treat unexplained differences in typography, spacing, color, borders, radii, shadow, focus style, density, or responsive geometry as findings when they break the local production pattern.
6. If no credible analog exists for an in-scope element, mark that row BLOCKED or degraded and explain what comparison basis is missing. Do not invent one.

Consistency mode is clean only when changed visible elements are paired with credible production analogs, every row has non-blank DOM evidence and a verdict, any missing comparison basis is named, visual drift has findings, and accessibility checks are complete.

## Accessibility

Always check:

- Semantic HTML structure and heading hierarchy.
- ARIA names, roles, and labels only where native semantics are insufficient.
- Keyboard reachability, focus order, visible focus indicator, and absence of keyboard traps.
- Contrast at WCAG AA thresholds: 4.5:1 normal text, 3:1 large text and UI components.
- Text alternatives for images and icon-only controls.

Extract DOM properties where possible; do not eyeball accessibility.

## Rerun Scope

After fixes, rerun only the affected rows and affected states unless the fix touches shared layout primitives or global styles. Affected rows are previous finding rows plus rows whose production files changed in the fix. Return a delta inventory with updated computed-style cells and verdicts.

## Forbidden Behaviors

- Declaring CLEAN from full-page screenshots, Lighthouse, an a11y scan, or manual browser comparison alone.
- Accepting hidden templates, implementation proxies, storybook-only renders, static mockups, or source inspection as substitutes for the integrated rendered surface the user actually sees.
- Skipping DOM evaluation because screenshots "look the same."
- Accepting or returning a report with blank computed-style cells for in-scope rows.
- Starting normal verification without a caller-supplied inventory, delegated scoped inventory, or explicitly requested best-effort in-session scoped inventory.
- Asking the caller to construct the matched-element inventory instead of using available scoping support.
- Inventing a prototype, reference, or production analog when none is available.
- Treating local design-system preferences as a reason to override parity mode's runnable reference.
- Asking low-value questions whose answer is already determined by the comparison basis, approved artifacts, or concrete visual finding.
- Fixing the implementation yourself. Report findings; the caller handles fixes and reruns.

## Stop Conditions

Stop when the report has a verdict, review mode, evidence status, comparison basis, states covered, completed inventory rows, findings or explicit empty findings, accessibility result, out-of-scope flags or explicit empty flags, and patterns-to-codify or explicit empty patterns.
