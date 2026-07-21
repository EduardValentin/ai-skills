---
name: ui-verification
description: Verifies implemented frontend UI for visual parity or consistency with DOM-backed style, geometry, state, and accessibility evidence. Use when a request asks for UI/UX verification, frontend visual review, prototype parity, production-pattern consistency, or a scoped visual rerun. Do not use for general functional QA unless visual evidence is explicitly required.
compatibility: >-
  Requires shell execution and browser automation that supports navigation, viewport control, JavaScript injection and evaluation, screenshots, and keyboard and focus exercise. Prefer host browser tools, with Playwright as fallback. Parity also requires readable runnable implementation and reference UIs. The optional `uiux-verifier` native agent may supply delegated scoping; if unavailable, continue only with caller-authorized in-session scoping or return BLOCKED.
metadata:
  status: local-required
  allows_tool_references: "true"
---

# UI Verification

## Purpose

Verify the integrated, user-visible UI with rendered evidence. Pair affected elements with a runnable reference or a credible production analog, compare DOM styles and geometry, exercise meaningful states and accessibility, and report findings without modifying the implementation.

Use this skill for visual evidence. Use functional QA for roles, persistence, redirects, API behavior, and other acceptance criteria unless the request also requires visual verification.

## Inputs And Scope

Collect the available task requirements, approved design notes and divergences, changed UI files or diff, implementation URL and routes, meaningful states, viewport conditions, and comparison basis. Parity also needs a runnable reference URL. Consistency needs credible production siblings, analog routes, reusable component contracts, or documented design constraints.

An affected-element inventory is required before normal verification:

1. Start with a caller-supplied affected surface map when available.
2. When delegated to the `uiux-verifier` native agent, treat its implementation and reference URLs, approved requirements and design, changed files, affected surface map, reference rows, and implementation locators as starting inputs.
3. If no inventory exists, use delegated scoping when available. Without it, continue only when the caller explicitly authorizes best-effort in-session scoping from the task, approved artifacts, changed files, routes, states, comparison basis, and live DOM.
4. Otherwise return `BLOCKED` and name the minimum missing scope input or authorization. Never invent scope from screenshots or visual impressions alone.

Refine the inventory during live inspection. Record visible in-scope elements omitted from supplied artifacts as inventory provenance gaps and add them to the inventory.

## Modes

- **Parity**: a runnable prototype, reference app, design implementation, or `designs/` app is the visual source of truth.
- **Consistency**: no runnable reference exists; compare with the closest credible production analog by component family, route region, interaction pattern, or documented component or token contract.

Choose parity when a runnable reference is supplied. In consistency mode, a row with no credible analog is `BLOCKED`; never invent a comparison basis.

## Browser And Evidence Setup

Use the host's browser automation when it can navigate, set viewport, capture element screenshots, evaluate JavaScript, and exercise keyboard and focus states. Otherwise use Playwright through the shell. Match route, state, viewport, device scale factor, and browser zoom before each comparison.

For Playwright, inject `scripts/extract-element-style.browser.js` unchanged, then pass the selector as a serialized evaluation argument:

```js
await page.addScriptTag({ path: extractorPath });
const evidence = await page.evaluate(
  (selector) => globalThis.uiVerificationExtractElementStyle(selector),
  selector,
);
```

Do not interpolate selectors into script text. The helper returns rendered font, color, box, layout, transform, and geometry evidence. Its geometry contract is `x`, `y`, `top`, `right`, `bottom`, `left`, `width`, and `height`. Gather parent and sibling geometry with separate helper calls when relative placement matters.

Screenshots are secondary evidence for context and visual cross-checking. Source files, hidden templates, static mockups, Storybook-only renders, Lighthouse, accessibility scans, and screenshots alone do not establish complete visual verification of the integrated surface.

## Inventory Contract

Create one row per affected element and meaningful state. Every row must contain:

| Field | Required evidence |
| --- | --- |
| Row | Stable ID, element name, route, viewport, and state |
| Pair | Implementation locator and reference locator or named consistency basis |
| Font | Family, size, weight, style, line height, letter spacing, transform, and decoration |
| Color | Foreground, effective background, and opacity |
| Box | Padding, margin, border, radius, shadow, and outline |
| Layout | Display, flex or grid properties, gap, position, and relevant overflow |
| Geometry | `x`, `y`, `top`, `right`, `bottom`, `left`, `width`, and `height` for the element and relevant relatives |
| Transform | Rendered transform value |
| Accessibility | Semantics, accessible name, keyboard and focus result, contrast result, and relevant state |
| Verdict | `MATCH`, `DRIFT`, `MISSING`, or `BLOCKED`, with an explanation when not `MATCH` |

Use explicit `not applicable` plus a reason where a field truly does not apply; never leave required cells blank. An approved divergence is documented in the row and does not become `DRIFT` when every non-approved property matches.

Row verdicts mean:

- `MATCH`: complete evidence matches the comparison basis, allowing only documented approved divergences.
- `DRIFT`: an unapproved rendered difference exists.
- `MISSING`: a required rendered element exists on only one side or is absent from the implementation.
- `BLOCKED`: evidence or a credible comparison basis is unavailable, so the row cannot be decided.

## Verification Procedure

### Parity

1. Open the integrated implementation and runnable reference under matched conditions.
2. Exercise every meaningful state named by the task, approved artifacts, changed surface, or adjacent affected interaction.
3. Extract both sides of every inventory row with the bundled helper and gather separate accessibility evidence.
4. Compare numeric and computed values. Treat unexplained differences as `DRIFT`; do not override the runnable reference with local preferences.
5. Cross-check both live DOMs for inventory provenance gaps.
6. Capture element screenshots after DOM extraction as redundant evidence.

### Consistency

1. Open the integrated implementation and relevant production analog routes under matched conditions.
2. Pair each row with the closest credible analog by role and purpose.
3. Extract both sides and compare typography, spacing, color, borders, radii, shadow, focus treatment, density, and responsive geometry.
4. Mark a row `BLOCKED` when no credible analog or documented contract exists.

## Accessibility Evidence

Always verify semantic structure and heading hierarchy, accessible names and roles, keyboard reachability and order, visible focus, keyboard traps, image alternatives, icon-only control names, and relevant ARIA state only where native semantics are insufficient.

Record every confirmed accessibility failure as a finding, even when the implementation matches the reference or production analog. Keep inconclusive or unavailable accessibility checks `BLOCKED` instead of treating them as failures.

Check WCAG AA contrast at 4.5:1 for normal text and 3:1 for large text and UI components. Resolve inherited and transparent solid backgrounds through ancestors and alpha-composite them before computing a ratio. For gradients, images, blend modes, backdrop filters, or other non-solid backgrounds, use a browser contrast analyzer that can evaluate the rendered background. If no reliable ratio is available, mark that accessibility cell `BLOCKED`, lower the evidence status, and do not return `CLEAN`. Never estimate contrast by eye.

## Evidence Status And Global Verdict

Report evidence status independently from verdict:

- **complete DOM evidence**: every required row, state, geometry field, and accessibility check is complete.
- **partial DOM evidence**: some DOM evidence exists, but one or more required rows or checks are blocked.
- **degraded manual evidence**: only screenshots or manual observation are available.

Aggregate the global verdict in this order:

1. `FINDINGS` when any row is `DRIFT` or `MISSING`, or any accessibility check confirms a failure. This takes precedence over blocked rows; list those rows or checks as remaining evidence gaps. With caller-authorized best-effort degraded evidence, a clearly visible defect may produce `FINDINGS`, but label it provisional and identify missing DOM confirmation.
2. `BLOCKED` when no finding is established and any required row or check is `BLOCKED`, or when only degraded manual evidence exists.
3. `CLEAN` only with complete DOM evidence, all rows `MATCH`, every required accessibility check complete and passing, zero accessibility findings, and no unresolved provenance gap.

Degraded manual evidence can never produce `CLEAN`.

## Reruns

After fixes, rerun prior finding rows, rows whose implementation files changed, and their affected states. Expand to the full inventory only when shared layout primitives, global styles, or shared components changed. Recollect DOM evidence under the same comparison conditions and return a delta inventory; do not accept the fix description as proof.

## Report Contract

Return:

- Global verdict, mode, and evidence status.
- Comparison basis and matched route, viewport, device scale, zoom, and states.
- Completed inventory rows.
- Findings with stable IDs such as `UV-1`, affected row and state, expected basis, observed result, evidence, and user impact. Severity is optional and must be justified by impact.
- Accessibility result and any blocked checks.
- Inventory provenance gaps, including explicit `None`.
- Out-of-scope flags: nearby surfaces or states intentionally excluded, with reason and residual risk, or explicit `None`.
- Patterns to codify: repeated drift that suggests a reusable component, token, or regression check, or explicit `None`. Do not promote one-off differences as patterns.
- Blockers and the minimum next input, or explicit `None`.

Do not create a recommendations-only bucket for visual drift. Do not fix the implementation during verification; report findings for a separate implementation step.
