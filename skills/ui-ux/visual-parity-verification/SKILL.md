---
name: visual-parity-verification
description: Use when verifying that changed UI surfaces render identically to a runnable React reference prototype, or, when no runnable reference exists, consistently with credible production analogs, by snapshotting each root pair's rendered subtree on both sides, diffing the snapshots with the bundled scripts, and writing one verdict per row into a caller-supplied parity ledger.
compatibility: >-
  Requires a running real app, a running prototype in a React development build or named production analogs, browser tooling that can inject the bundled browser scripts and evaluate a function with serialized arguments on both sides (host browser tooling, else Playwright), Python 3 for the bundled host scripts, and a caller-supplied ledger and component map. Without any of these, return BLOCKED naming the missing input.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Visual Parity Verification

## Overview

Compare the rendered real app to its basis one root pair at a time. A root
pair is a prototype React component and the real app element that renders
the same surface. The bundled scripts resolve the prototype roots, snapshot
the rendered subtree on both sides, align and compare the two snapshots, and
write the verdict into the ledger. You reach states, supply nothing the
scripts can derive, and read the diff. Screenshots are context, never proof.
Source files, static mockups, hidden templates, Storybook-only renders and
accessibility scans cannot complete a comparison.

The real app may be built with any stack. Nothing after root resolution
inspects how its markup was produced.

## When To Use

- A changed UI surface has a prototype or other runnable reference it must
  match exactly.
- A changed UI surface has no runnable reference and must be judged against
  credible production analogs of the same role.
- The caller supplies a parity ledger and component map.

Do not use for broad rendered validation without a comparison basis; that is
ordinary visual validation.

## Inputs

- The ledger file to read and write. It records the viewport set and theme
  once at the top. Each row names a route, a state, a prototype component
  name, a real app root, and carries a `Verdict` and an `Evidence` column
  that only you write.
- The component map, which pairs each prototype component with a real app
  root selector or `data-parity-root` value and a route on each side.
- URLs of the running real app and the running prototype, or the analog
  routes and selectors when no reference exists.
- The project's breakpoints, or the default viewport set below.

If the ledger or the map is missing, return `BLOCKED` before any comparison
and request it. Do not scope the inventory yourself from screenshots or
impressions.

## Basis

The basis is chosen from one observable fact:

- A runnable reference UI exists for the row: compare against it. Local
  preference never overrides the reference.
- No runnable reference exists for the row: compare against the closest
  credible production analog by role and purpose, or a reusable component
  contract or documented design constraint. Name the analog in the row's
  evidence. If no credible analog exists, mark the row `BLOCKED`.

## Matched Conditions

Render each side at the route the component map pairs for that row. Match
viewport width and height, browser zoom, device scale factor, state, theme
and any other condition that could change the result. The snapshot records
these and the diff refuses to compare snapshots taken under different
conditions.

Take the viewport set from the project's responsive configuration, such as
Tailwind screens, CSS breakpoints or design tokens: one width just below and
one just above each breakpoint, plus the narrowest and widest widths the
project supports. Only when the project defines no breakpoints, use 320, 768,
1024, 1440 and 1920 pixels wide.

## Bundled Scripts

Paths resolve from the skill root. Inject the browser scripts unchanged and
pass every argument as a serialized evaluation argument. Never interpolate a
selector or a component name into script text.

- `scripts/find-react-roots.browser.js` exposes
  `globalThis.parityFindReactRoots(componentNames)`. Prototype side only. It
  returns each component's outermost rendered elements as selectors, or
  `no-react-fibers` when the page is not a React development build.
- `scripts/snapshot-subtree.browser.js` exposes
  `globalThis.paritySnapshot(rootSelector, options)`. Both sides. It returns
  the rendered subtree with semantics, computed style, geometry relative to
  the root, contrast and a wrapper flag. The shape is in
  `references/snapshot-schema.md`.
- `scripts/diff_snapshots.py` compares one prototype snapshot with one real
  app snapshot and writes a diff file plus a summary line. The shape and the
  verdict rules are in `references/diff-output.md`.
- `scripts/write_ledger.py` writes the worst verdict across a row's diff
  files and a compact evidence summary into that row, or appends a
  provenance-gap row.

```javascript
const roots = await page.evaluate(
  (names) => globalThis.parityFindReactRoots(names),
  ["OrderSummary"],
);
const snapshot = await page.evaluate(
  (selector) => globalThis.paritySnapshot(selector),
  roots.roots.OrderSummary[0].selector,
);
```

```bash
scripts/diff_snapshots.py --prototype <session>/snapshots/L1/prototype-1440x900.json \
  --real <session>/snapshots/L1/real-1440x900.json \
  --out <session>/diffs/L1-1440x900.json --pairings <session>/pairings.json --row L1
scripts/write_ledger.py --ledger <session>/ledger.md --row L1 \
  --diff <session>/diffs/L1-1440x900.json --diff <session>/diffs/L1-375x800.json
```

## Procedure

1. Resolve prototype roots. At each prototype route, inject the root finder
   and evaluate it with every component name the map lists for that route.
   A component with zero roots is `BLOCKED` for its rows with the component
   and route named. `no-react-fibers` blocks every row at that route.
2. For each row and viewport, set matched conditions on both sides, reach
   the row's state on both sides by interacting with the page, inject the
   snapshot script and evaluate it with the prototype root selector on the
   prototype and the map's real app root on the real app. Save both results
   unchanged under `snapshots/<row-id>/` in the session folder.
3. Run the diff for each row and viewport into `diffs/`. Read the summary
   line.
4. Review every pair matched by score below 0.7 and every suggestion in the
   diff file. Confirm or reject each by writing the pair into
   `pairings.json` under the row id, since a pairing only applies between
   nodes that are children of an already matched pair, then rerun that
   row's diffs. Add a finer root pair to the component map when a subtree
   aligns poorly rather than tuning weights.
5. Write the ledger for each row from its diff files.
6. At each real app route, look at the rendered page for a visible in-scope
   surface the map omits. Append a gap row for each with the ledger writer,
   pair it in the map, then run it like any other row.

## Evidence Standard

The snapshot is the evidence. It covers font, color, effective background,
box, layout, flex and grid placement, geometry relative to the root,
transform, role, accessible name, focusability, ARIA state and contrast.
Evidence status labels: `complete DOM evidence` when every row has diff
files for every viewport, `partial DOM evidence` when some rows do,
`degraded manual evidence` when a row's verdict rests on anything other than
a diff file, `no comparison evidence` otherwise. Degraded evidence may
support a provisional `DRIFT` for a clearly visible defect with the missing
diff stated; it can never support `MATCH` or `CLEAN`.

## Row Verdicts

The diff decides the verdict per viewport and the ledger writer records the
worst across viewports:

- `MATCH`: no style, geometry or missing finding on any viewport.
- `DRIFT`: a computed property or relative geometry differs beyond
  tolerance.
- `MISSING`: an aligned node exists on one side only.
- `BLOCKED`: conditions differ, roots are incompatible, contrast is
  unmeasurable, or a required input is unavailable.

Structure and content findings are reported and never change the verdict.
Accessibility findings are reported even when both sides share them.
Inconclusive or unavailable accessibility checks are `BLOCKED`, not
failures. Leave no row `PENDING`.

## Global Verdict

Apply in this order:

1. `FINDINGS` when any row is `DRIFT` or `MISSING`, or accessibility has a
   confirmed failure.
2. `BLOCKED` when no finding is established but a required row or check is
   blocked, only degraded evidence exists, or the status is `no comparison
   evidence`.
3. `CLEAN` only with complete DOM evidence, every row `MATCH`, every required
   accessibility check complete and passing, and no visible in-scope surface
   missing from the map.

## Rechecks

After the implementation owner fixes rows, rerun every prior `DRIFT`,
`MISSING` and `BLOCKED` row, every row whose implementation files changed,
and their affected states, under the original matched conditions. When a
shared primitive, global style, token or theme changed, rerun every row.
Pairings persist across reruns. Return a delta that distinguishes resolved,
remaining and new findings. A fix description is not proof.

## Report

Return the ledger path with the updated rows, then:

```markdown
# Visual parity verification — <surface>

## Verdict
- <CLEAN | FINDINGS | BLOCKED>

## Evidence status
- <complete DOM evidence | partial DOM evidence | degraded manual evidence | no comparison evidence>

## Basis
- <prototype URL and routes, or analog routes and why they are credible>

## Matched conditions
- viewport set: <widths x heights> | zoom: <percent> | device scale: <factor> | theme: <theme>

## Ledger rows written
- <count MATCH> MATCH | <count DRIFT> DRIFT | <count MISSING> MISSING | <count BLOCKED> BLOCKED

## Findings
- **P1** | severity: <blocker / major / minor> | ledger row <id> | <path property> | evidence: <prototype value vs real value> | diff: <relative diff path>

## Structure and content notes
- <moved nodes, collapsed-count differences, content mismatches, or None>

## Accessibility findings
- **A1** | severity: <blocker / major / minor> | ledger row <id> | <check> | WCAG criterion | suggested fix

## Pairings confirmed
- <row id: prototype path to real path, or None>

## Ledger provenance gaps
- <rows appended for visible in-scope surfaces the map omitted, or None>

## Blockers
- <None, or blocked row and minimum next input>

## Rerun delta
- <None, or resolved, remaining and new rows>
```

Write explicit `None` in every empty section.

## Forbidden Behaviors

- Declaring `CLEAN` from screenshots, source files or visual impression.
- Skipping the snapshot because the UI looks right.
- Writing a verdict without a diff file behind it.
- Editing snapshot or diff JSON by hand.
- Leaving a ledger row `PENDING` or blank.
- Interpolating selectors or component names into script text.
- Resolving components by name on the real app side.
- Matching nodes by class names or by attributes other than the parity
  hooks.
- Fixing implementation code while acting as the verifier.
