---
name: visual-parity-verification
description: Use when verifying that changed UI surfaces render identically to a runnable React reference prototype, or, when no runnable reference exists, consistently with credible production analogs, by snapshotting each root pair's rendered subtree on both sides, diffing the snapshots with the bundled scripts, and writing one verdict per row into a caller-supplied parity ledger.
compatibility: >-
  Requires a running real app, a running prototype in a React development build or named production analogs, browser tooling that can inject the bundled browser scripts and evaluate a function with serialized arguments on both sides, Python 3 for the bundled host scripts, and a caller-supplied ledger and component map. Playwright is optional, for scripts/capture-snapshots.mjs; without it, drive browser tooling directly. Without any of these, return BLOCKED naming the missing input.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Visual Parity Verification

## Overview

Compare the rendered real app to its basis one root pair at a time: a
prototype React component and the real app element rendering the same
surface. The bundled scripts capture, align and compare the two snapshots
and write the verdict into the ledger. You reach states, supply nothing the
scripts can derive, and read only the diff's and ledger writer's printed
output, never the snapshot JSON. Screenshots, source files, static
mockups, hidden templates, Storybook-only renders and accessibility scans
are context, never proof, and cannot complete a comparison.

The real app may be built with any stack; nothing after root resolution
inspects how its markup was produced.

## When To Use

- A changed UI surface has a prototype or other runnable reference it must
  match exactly, or has none and must be judged against credible
  production analogs of the same role.
- The caller supplies a parity ledger and component map.

Do not use for broad rendered validation without a comparison basis; that's
ordinary visual validation.

## Inputs

- The ledger to read and write, recording the viewport set and theme once
  at the top; each row names a route, a state, a prototype component name
  and a real app root, and carries a `Verdict` and an `Evidence` column
  only you write.
- The component map, pairing each prototype component with a real app root
  selector or `data-parity-root` value and a route per side.
- URLs of the running real app and prototype, or analog routes and
  selectors when no reference exists, and the project's breakpoints or the
  default viewport set below.

If the ledger or map is missing, return `BLOCKED` before any comparison and
request it; do not scope the inventory yourself from screenshots or
impressions.

## Basis

The basis follows one fact:

- A runnable reference exists for the row: compare against it; local
  preference never overrides the reference.
- No runnable reference exists: compare against the closest credible
  production analog by role and purpose, or a reusable component contract
  or documented design constraint; name the analog in the row's evidence,
  or mark the row `BLOCKED` if none exists.

## Matched Conditions

Render each side at the route the component map pairs for that row,
matching viewport width and height, browser zoom, device scale factor,
state, theme and any other condition that could change the result. The
snapshot records these; the diff refuses to compare snapshots taken under
different conditions.

Take the viewport set from the project's responsive configuration — Tailwind
screens, CSS breakpoints or design tokens — one width below and one above
each breakpoint, plus the narrowest and widest widths supported. Without
project breakpoints, use 320, 768, 1024, 1440 and 1920 pixels wide.

## Bundled Scripts

Paths resolve from the skill root.

- `scripts/capture-snapshots.mjs`: drives headless Chromium through
  Playwright, writing snapshot files itself. `references/capture.md`.
- `scripts/find-react-roots.browser.js` and
  `scripts/snapshot-subtree.browser.js`: resolve prototype roots and
  capture a subtree when driving the browser directly.
  `references/snapshot-schema.md`.
- `scripts/diff_snapshots.py`: compares a prototype and a real app
  snapshot, writes a diff file, and prints a summary line, adding review
  lines with `--print-review`. `references/diff-output.md`.
- `scripts/write_ledger.py`: writes a row's worst verdict and an evidence
  summary, or appends a provenance-gap row with `--append-gap`.

## Procedure

1. Capture. For each row and viewport set, run
   `scripts/capture-snapshots.mjs` with that row's URLs and roots. Rows
   sharing a prototype route and state capture it once, then capture only
   `--real-url`/`--real-root` per row, pointing the diff at the shared
   file. Read only the printed summary line.
2. Interactive states. For a state the capture command cannot drive, reach
   it by hand on both sides, inject the snapshot script by file path, and
   evaluate `paritySnapshot(root, { encoding: "gzip-base64" })`, saving the
   returned string verbatim as the snapshot file.
3. Diff. For each row and viewport, run `scripts/diff_snapshots.py` with
   `--print-review` and read only its printed summary and review lines.
4. Review. Confirm or reject each printed `review` pair and accept or
   ignore each `suggest` line. Write confirmed pairs into `pairings.json`
   under the row id, then rerun that row's diffs. Add a finer root pair to
   the component map when a subtree aligns poorly rather than tuning
   weights.
5. Ledger. Write the ledger for each row from its diff files with
   `scripts/write_ledger.py`.
6. Gap check. At each real app route, look for a visible in-scope surface
   the map omits. Append a gap row with `write_ledger.py --append-gap`,
   pair it in the map, and run it like any other row.

## Evidence Standard

See `references/report-format.md` for evidence status labels and what the
snapshot covers.

## Row Verdicts

The diff decides each viewport's verdict; the ledger writer records the
worst across viewports:

- `MATCH`: no style, geometry or missing finding on any viewport.
- `DRIFT`: a computed property or relative geometry differs beyond
  tolerance.
- `MISSING`: an aligned node exists on one side only.
- `BLOCKED`: conditions differ, roots are incompatible, or a required input
  is unavailable.

Structure and content findings are reported and never change the verdict;
accessibility findings are reported even when both sides share them.
Unmeasurable contrast is an accessibility finding, not a row verdict,
counting as a blocked check in Global Verdict step 2. Leave no row
`PENDING`.

## Global Verdict

Apply in this order:

1. `FINDINGS` when any row is `DRIFT` or `MISSING`, or accessibility has a
   confirmed failure.
2. `BLOCKED` when no finding is established but a required row or check is
   blocked, evidence is degraded, or status is `no comparison evidence`.
3. `CLEAN` only with complete DOM evidence, every row `MATCH`, every required
   accessibility check complete and passing, and no visible in-scope surface
   missing from the map.

## Rechecks

After fixes, rerun every prior `DRIFT`, `MISSING` and `BLOCKED` row, every
row whose implementation files changed, and their affected states, under
the original matched conditions; a shared primitive, global style, token or
theme change reruns every row. Pairings persist across reruns. Return a
delta distinguishing resolved, remaining and new findings — a fix
description is not proof.

## Report

Return the ledger path with the updated rows, then the report template in
`references/report-format.md`.

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
