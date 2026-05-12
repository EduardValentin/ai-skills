# Verification (Personal Workflow + React Reference App)

Loaded during the Verify phase **only** when the personal project has a runnable React reference app. Required before opening the PR. Run only after all tests pass.

## Goal

Two distinct verifications. Both are required. Both are reported separately at closeout.

- **Visual parity** — the implemented feature matches the prototype, confirmed by both numeric style/layout extraction and visual inspection.
- **Behavior** — the production feature's business logic and behavior are correct across every relevant state and scenario.

## Setup

1. Start both apps locally:
   - The production app on its dev server.
   - The `designs/` React reference app on its dev server.
2. Open both apps in the live browser. Switch between tabs to compare side-by-side; do not rely on a compressed side-by-side view to spot small differences.
3. Set both browser views to the same viewport size, device scale factor, browser zoom, and route/state before each comparison, screenshot, or DOM-evaluation call.
4. If either app cannot be started, the feature cannot be exercised in both apps, or screenshots cannot be captured: stop, report the blocker explicitly, and do not claim parity was verified.

Browser-automation capability and fallback chain are defined in `agents/ui-ux.md` → `## Browser bootstrap`. The protocol below is the same regardless of which level of the fallback chain is in use.

## Pass 1 — Visual Parity

Vision alone misses small differences in spacing, font-weight, color, border-radius, line-height, and shadow. Pass 1 must combine **programmatic style and layout extraction** with element-level visual inspection. Numbers catch what vision misses — a 4px gap difference, a `font-weight: 500` vs `400`, a `#0f172a` vs `#111827`. Treat any numeric divergence as a mismatch.

### Important UI states

Cover every state the feature surfaces:

- Default
- Loading
- Empty
- Hover, focus, active, disabled
- Error and validation
- Success
- Expanded / collapsed
- Modal-open
- Navigation states tied to the feature

### Matched-element inventory (do this first)

**REQUIRED + EXHAUSTIVE.** Every visible element in the feature's surface gets a row. Selectivity is forbidden — "I checked the important ones" is parity drift.

In **parity mode**, the inventory is **supplied by main agent at Verify dispatch** (see `SKILL.md` → Verify step 4a). Your job is to verify each supplied row by running DOM evaluation against the live browsers and filling in the verdict + computed-style cells per row. If during verification you observe a visible element on either side that wasn't in the supplied inventory, add it to `### Rows added beyond the supplied inventory` in your report — it represents a Scoping/Plan enumeration gap, not a row to silently drop.

In **consistency mode**, you build the sibling/analog inventory yourself per `agents/ui-ux.md` → `## Determining completeness — consistency mode`.

The four completeness checks (diff-driven coverage, production-DOM coverage, prototype-DOM coverage, sibling/parent geometry) detailed in `agents/ui-ux.md` apply in both modes — they're built into the supplied inventory in parity mode and built by you in consistency mode.

Before any comparison, ensure the inventory is in hand (parity mode: supplied; consistency mode: built). For every visible region — header, button, input, label, card, list item, icon, badge, link, divider, container — identify the matching element in both apps (parity mode: per the supplied row; consistency mode: by inspection). Match by role, accessible name, text content, or `data-testid`. Record:

- the selector you will use in each app
- which prototype element maps to which production element
- any element that exists in one app but not the other (an unmatched element is a parity miss; flag it explicitly)

If you cannot match all visible elements, the inventory is incomplete and Pass 1 cannot start.

### Per-state procedure

For each important UI state, at every relevant breakpoint plus the widths immediately before and after each breakpoint switch:

1. **Drive both apps into the same state.** Same route, same data, same interaction depth, same viewport, same device scale, same zoom.

2. **Element-level screenshots per matched pair.** Capture an element-level screenshot for each pair in each app. Do not rely on full-page screenshots for parity judgments — they compress detail.

3. **Programmatic style and layout extraction (REQUIRED).** For each matched pair (parity mode: each supplied row; consistency mode: each row of the sibling/analog inventory you built), evaluate the extraction snippet at `scripts/extract-element-style.browser.js` against the DOM in both apps. The snippet returns a single JSON-serialisable object per element containing the computed-style and bounding-rect fields the matched-element inventory needs:

   - `font.*` — `family`, `size`, `weight`, `style`, `lineHeight`, `letterSpacing`, `textTransform`, `textDecoration`.
   - `color.*` — `fg`, `bg`, `opacity`.
   - `box.*` — `padding`, `margin`, `border`, `borderRadius`, `boxShadow`, `outline`.
   - `layout.*` — `display`, `flexDirection`, `alignItems`, `justifyContent`, `gap`, `position`.
   - `size.*` — `width`, `height` (from `getBoundingClientRect()`).
   - `transform`.

   Compare property-by-property, prototype against production. Any divergence is a mismatch unless it is a deliberate, documented divergence raised during planning (rare).

4. **Layout-position check.** For matched elements that share a parent, compare `getBoundingClientRect()` `x`, `y`, `width`, `height`. Position drift inside the same parent reveals alignment, gap, padding, or sizing mismatches that style values alone may not surface.

5. **Visual cross-check.** Inspect the element-level screenshots. Vision is the redundant check on top of numbers, not the primary one. If a screenshot looks wrong but styles match, dig deeper — a parent layout, a sibling, or a pseudo-element may be the cause.

6. **Fix-and-rerun.** If any mismatch is found — visual, computed-style, or layout-position — fix the implementation and re-run Pass 1 for every state where the changed property could surface. Do not narrow the re-run to only the state that reported the bug.

### What "clean" means

Pass 1 is clean only when **all** of the following hold for every matched element pair, at every important state, at every relevant breakpoint:

- `font-family`, `font-size`, `font-weight`, `font-style`, `line-height`, `letter-spacing`, `text-transform`, `text-decoration` match.
- `color`, `background-color`, `opacity` match.
- `padding`, `margin`, `border`, `border-radius`, `box-shadow`, `outline` match.
- `display`, `flex-direction`, `align-items`, `justify-content`, `gap`, `position` match.
- `width` and `height` agree within sub-pixel rounding.
- `transform` matches (relevant for animation rest states).
- The matched-element inventory is complete: no unmatched elements in either app.
- Element-level screenshots agree under visual inspection.

If any one of these is not true, parity is **not** clean. Do not declare visual parity. Do not advance to Pass 2.

### Forbidden shortcuts

- Declaring parity off full-page screenshots alone.
- Skipping DOM evaluation because the screenshots "look the same."
- Restricting the matched-element inventory to elements named in the ticket — the inventory covers every visible region of the feature.
- Tolerating "small" numeric differences. There is no tolerance budget — different numbers mean different rendering.
- Re-running only the state that surfaced the bug instead of every state where the changed property could affect rendering.

Reference `react-parity.md` for the parity rules being applied.

## Pass 2 — Behavior

After visual parity is clean, exhaustively exercise the production app's implementation in the browser. Be thorough — go through every state and scenario of the implemented feature, not just the obvious ones.

Cover:

- **Happy path:** every implemented flow end-to-end.
- **State transitions:** every transition the feature owns.
- **Error paths:** validation errors, permission denials, network failures, conflict states, retry/cancel paths — every error this feature is responsible for.
- **Empty, loading, success, boundary conditions:** at every place the feature surfaces them.
- **Adversarial inputs:** invalid input, out-of-range values, unexpected sequences (rapid clicks, navigating mid-action, double submits) the feature should defend against.
- **Cross-feature impact:** the new feature must not regress adjacent flows visible from its surface area.
- **Responsive behavior:** interactive elements at the same breakpoints used in Pass 1.

After each meaningful action, inspect the UI to confirm the feature still looks correct and behaves correctly.

If a behavior issue is found, fix it and re-run the affected portion. Do not skip back to declaring done.

## Outcome

Only after both passes are clean:

- Open the PR with `gh`.
- Move the Linear ticket to `In Review`.
- Wait for the user's explicit approval before merging.
- After merge, move the Linear ticket to its completed state.

In the closeout report, distinguish visual parity coverage from behavior coverage explicitly. If either pass surfaced issues, name them and confirm they were fixed and re-verified.
