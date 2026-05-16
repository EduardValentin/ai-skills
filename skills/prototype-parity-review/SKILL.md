---
name: prototype-parity-review
description: Use when reviewing implemented frontend UI against a runnable prototype or reference app for visual parity, building or verifying matched-element inventories, comparing DOM computed styles/bounding rects, or auditing UI consistency and accessibility when no prototype exists.
---

# Prototype Parity Review

## Overview

Visual review is evidence work, not taste work. Verify rendered UI by pairing visible elements, extracting DOM computed styles and bounding boxes, checking screenshots only as secondary evidence, and reporting a compact inventory with findings.

## When To Use

- A frontend change needs to match a runnable prototype, reference app, design implementation, or `designs/` React app.
- A ticket workflow delegates a UI/UX verification gate and supplies a mode: `parity` or `consistency`.
- A visual review needs matched-element inventory coverage, computed style comparison, bounding-rect comparison, accessibility checks, or a scoped visual rerun after fixes.
- No prototype exists, but new or changed UI must be checked for consistency against sibling or analog elements in the production app.

## Required Capabilities

- Ability to execute shell commands for app startup or browser automation fallback.
- Ability to inspect a live browser page by navigating, changing viewport, evaluating JavaScript in the page, capturing element screenshots, and exercising keyboard/focus states.
- Read access to the production UI and, in parity mode, the reference UI.

If a capability is unavailable, follow the fallback chain below. Do not replace DOM evidence with visual impressions.

## Inputs

Expect as many of these as the caller can provide:

- Ticket title, description, acceptance criteria, and approved plan.
- Full diff or changed UI file list.
- Mode: `parity` when a runnable reference/prototype exists; `consistency` otherwise.
- Production route/URL and, in parity mode, reference route/URL.
- Important states to exercise: default, loading, empty, hover, focus, active, disabled, error, validation, success, expanded/collapsed, modal-open, and navigation states.
- Parity mode: Scoping touched-areas map with prototype/reference element rows, production locators or changed UI files, relevant routes/states, approved requirements/design artifact, and approved plan.
- Prior local evidence such as screenshots, Lighthouse output, a11y scans, or manual notes. Treat these as context, not as gate completion.

## Browser Bootstrap

Prefer the host's native browser automation if it can navigate, set viewport, capture element screenshots, and evaluate JavaScript in the page. If that is unavailable, drive Playwright through the shell and inject `scripts/extract-element-style.browser.js` via page evaluation. If neither is available, save the renderable page or screenshots to disk and ask the user for visual confirmation; mark the verdict **degraded**. If even that fallback cannot run, return `Prototype parity review cannot proceed` with the blocker and required input.

## Output Format

Return Markdown:

```markdown
# Prototype parity review — <ticket title>

## Verdict
- [ ] CLEAN — no visual or accessibility findings
- [ ] FINDINGS — at least one visual or accessibility finding
- [ ] BLOCKED — review could not proceed

## Mode used
- <parity | consistency | degraded>

## States covered
- <state> | viewport widths: <list, including pre/post-breakpoint widths> | evidence: <DOM extraction / screenshot / keyboard path>

## Matched-element inventory
| Pair | Prototype selector | Production selector | font-* | color/bg | box | layout | size | verdict |
|---|---|---|---|---|---|---|---|---|
| <prototype locator or analog> ↔ <production locator> | <selector> | <selector> | <actual extracted values> | <actual extracted values> | <actual extracted values> | <actual extracted values> | <actual extracted values> | <MATCH / DRIFT / MISSING> |

### Inventory provenance gaps
_(parity mode only; list visible production or prototype elements observed during verification that were missing from Scoping touched areas or approved artifacts)_
- `<locator>` | <element type> | <one-line description> | suggested provenance gap: <scoping / plan / rendered conditional state>

## Visual findings
- **V1** | severity: <blocker / major / minor> | `<production selector>` ↔ `<reference selector or analog>` | <property or measurement diff> | evidence: <computed-style snippet or bounding-rect numbers> | suggested fix

## Accessibility findings
- **A1** | severity: <blocker / major / minor> | `<selector>` | <semantic structure / ARIA / focus order / keyboard reach / contrast / alt text> | WCAG criterion | suggested fix

## Out-of-scope flags
- **O1** | `<path:line>` | <suspected behavior or code-quality issue> | flagged for: <QA / code review>

## Patterns to codify next time
- <one-line declarative candidate rule> | rationale: <one sentence>
```

Any visual finding flips the verdict to FINDINGS. Do not create a "recommendations only" bucket for visual drift.

## Parity Mode

Use when a runnable prototype/reference app exists. The prototype is the source of truth for the ticketed visual surface.

1. Start or open both apps. Match route, state, viewport, device scale, and browser zoom before each comparison.
2. Build the matched-element inventory from Scoping touched areas, prototype/reference rows, changed UI files, approved artifacts, and live DOM inspection. Do not ask the main agent to prebuild it.
3. For each inventory row and state, locate the rendered DOM atoms in both apps, capture element-level screenshots, evaluate `scripts/extract-element-style.browser.js`, fill every computed-style cell, and set verdict to MATCH, DRIFT, or MISSING.
4. Compare font, color/background, padding/margin/border/radius/shadow/outline, display/flex/gap/position, width/height, and transform. Different numbers mean rendered drift unless the approved plan explicitly accepted the divergence.
5. Compare parent and sibling geometry with bounding rects, especially for rows sharing a parent declaration.
6. While verifying, cross-check both DOMs for visible elements absent from Scoping touched areas or approved artifacts. Add those to `Inventory provenance gaps`; never silently drop them.
7. Use screenshots as a redundant visual check after numeric extraction, not as primary evidence.

Parity mode is clean only when the inventory covers Scoping touched areas and observed changed elements, every row has non-blank computed values, no unexplained observed rows are missing from the report, all drift has findings, and accessibility checks are complete.

## Consistency Mode

Use when no runnable prototype/reference app exists. The goal is consistency with existing production analogs, not personal preference.

1. Walk the diff and enumerate every new or changed visible element on the feature surface.
2. For each element, identify sibling or analog elements in the same view: same typography hierarchy, icon role, button class, spacing rhythm, border radius, color token, or elevation.
3. Build the same matched-element inventory using analogs instead of prototype selectors.
4. Extract computed styles and bounding rects for the new/changed element and its analogs.
5. Any deviation without an approved rationale is a finding.

Consistency mode is clean only when every changed visible element has an analog row, every row has DOM evidence, and accessibility checks are complete.

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
- Skipping DOM evaluation because screenshots "look the same."
- In parity mode, accepting or returning a report with blank computed-style cells for in-scope rows.
- In parity mode, asking the main agent to construct the matched-element inventory for you.
- In consistency mode, reviewing only "important" elements instead of every changed visible element and analog.
- Treating local design-system preferences as a reason to override prototype parity.
- Asking low-value questions whose answer is already determined by the prototype, approved plan, or concrete visual finding.
- Fixing the implementation yourself. Report findings; the caller handles fixes and reruns.

## Stop Conditions

Stop when the report has a verdict, mode, states covered, completed inventory rows, findings or explicit empty findings, accessibility result, out-of-scope flags or explicit empty flags, and patterns-to-codify or explicit empty patterns.
