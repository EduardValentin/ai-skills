---
name: visual-parity-verification
description: Use when verifying that changed UI surfaces render identically to a runnable React reference prototype, by reading the project's committed .parity/parity-map.md and .parity/parity-pairings.json, snapshotting each root pair's rendered subtree on both sides, diffing the snapshots with the bundled scripts, and writing one verdict per row into the session's parity ledger. Not for surfaces without a runnable prototype.
compatibility: >-
  Requires a running real app, a running prototype in a React development build, browser tooling that injects the bundled browser scripts and evaluates a function with serialized arguments on both sides, Python 3 for the bundled host scripts, a caller-supplied ledger and committed parity map. Playwright is optional, for scripts/capture-snapshots.mjs; without it, drive browser tooling directly. Without any of these, return BLOCKED naming the missing input; there is no fallback basis.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Visual Parity Verification

## Overview

Compare the rendered real app to its basis one root pair at a time: a
prototype React component and the real app element, whatever its stack,
rendering the same surface. The prototype is the only basis; local
preference never overrides it. The committed `.parity/parity-map.md` declares
the pairs; the bundled scripts build the manifest, capture, align, compare and
write the verdict into the ledger. You reach the states no recipe covers,
supply nothing the scripts can derive, and read only the printed output of
the diff and ledger writer, never the snapshot JSON. Screenshots, source
files, mockups and accessibility scans are context, never proof.

## When To Use

- A changed UI surface has a runnable React prototype it must match
  exactly.
- The project commits a parity map and the caller supplies a session
  ledger.

## Inputs

- The committed `.parity/parity-map.md`: one durable row per root pair the
  project has ever verified, with routes, `States`, `Viewports` and `Ignore`
  entries (`references/map.md`).
- The committed `.parity/parity-pairings.json`, keyed by map id, and the
  optional `.parity/parity-actions/` recipes.
- The session ledger, `.parity/sessions/<session>/ledger.md`, with the
  viewport set and theme at the top; each row's `Map id` names a map row,
  and you write only its `Verdict` and `Evidence` cells.
- Both app URLs and the project's breakpoints. For authentication, add
  `prototype` or `real` objects with `storageState` and `headers` to the
  manifest by hand (`references/capture.md`).

Return `BLOCKED` before any comparison when the map or ledger is missing or
`parity_map.py check` fails; never scope the inventory yourself.

## Matched Conditions

Render each side at the row's mapped route, matching viewport, zoom, device
scale factor, state and theme; the snapshot records these and the diff
refuses mismatched conditions.

Take the viewport set from the project's breakpoints: one width below and
one above each, plus the narrowest and widest supported; without them, 320,
768, 1024, 1440 and 1920 pixels wide. Default states use the full set;
hover, focus, pressed and similar interaction states use one width per
breakpoint class, the smallest in each.

Rows with the same prototype route, component and recipe share one
prototype capture; a state that renders differently on the prototype needs
a recipe or its own map row.

## Bundled Scripts

Paths resolve from the skill root.

- `scripts/parity_map.py`: `check` validates the map, `row` prints one row,
  `manifest` joins ledger and map into the capture manifest with each row's
  viewports, recipes and ignore entries. `references/map.md`.
- `scripts/capture-snapshots.mjs`: drives headless Chromium through
  Playwright from a manifest (`--manifest`, `--only-viewports`) or per side
  (`--viewport`, `--prototype-*`, `--real-*`), with recipe, storage-state
  and header flags. `references/capture.md`.
- `scripts/find-react-roots.browser.js` and
  `scripts/snapshot-subtree.browser.js`: resolve prototype roots and
  capture a subtree when driving the browser directly.
  `references/snapshot-schema.md`.
- `scripts/diff_snapshots.py`: compares one snapshot pair, pruning declared
  subtrees with `--ignore-prototype` and `--ignore-real`, writes a diff
  file and prints a summary line, plus review lines with `--print-review`.
  `references/diff-output.md`.
- `scripts/write_ledger.py`: writes a row's worst verdict and evidence from
  `--row --diff`, `BLOCKED` from `--row --blocked REASON` or `EXPECTED`
  from `--row --expected REASON`, and appends a provenance-gap row with
  `--append-gap`.

## Procedure

1. Capture. Run `parity_map.py check`, then `parity_map.py manifest` with
   both URLs and the viewport set (`--only-viewports` on a recheck, see
   Rechecks). Run `capture-snapshots.mjs --manifest` once per round and
   read the summary lines once. A capture error line makes its row
   `BLOCKED` (`write_ledger.py --row <id> --blocked "<side> <root>
   <route>: <error>"`); `no-react-fibers` blocks every row at that
   prototype route.
2. Hand-driven states. When no recipe reaches a state, drive both sides by
   hand, inject the snapshot script by file path, evaluate
   `paritySnapshot(root, { encoding: "gzip-base64" })` and save the
   returned string verbatim as the snapshot file.
3. Diff. Per row and viewport, run `scripts/diff_snapshots.py
   --print-review --pairings .parity/parity-pairings.json --row <map id>`
   with the row's manifest `ignore` entries as `--ignore-prototype` and
   `--ignore-real`; read only the printed summary and review lines.
4. Review. Confirm or reject each `review` pair and each `suggest` line.
   Write confirmed pairs into `.parity/parity-pairings.json` under the map
   id, drop or correct the entry behind each `pairing unapplied` line, then
   rerun that row's diffs; copy each `hook suggest` line into the report's
   Hook suggestions section. Propose, never write, an `Ignore` entry for a
   legitimate one-sided subtree and a finer map row for a subtree that
   aligns poorly. `Ignore` prunes the node, not its layout effect, so it
   fits only out-of-flow or zero-footprint subtrees.
5. Ledger. Write each row from its diff files with
   `scripts/write_ledger.py`. For a row listed by a design-changes row
   whose `What changed` starts with `accepted:`, write `--expected` with
   that row's reason.
6. Gap check. At each real app route, look for a visible in-scope surface
   the map omits; append a gap row with `write_ledger.py --append-gap`
   under the next free map id, capture it per side, and propose the map
   row (`Id`, roots, routes) in the report.

## Row Verdicts

The diff decides each viewport; the ledger writer records the worst, in
this order:

- `BLOCKED`: conditions differ, roots are incompatible, or a required input
  is unavailable.
- `DRIFT`: a computed property or relative geometry differs beyond
  tolerance.
- `MISSING`: an aligned node exists on one side only.
- `EXPECTED`: an accepted difference with a recorded reason; passes.
- `MATCH`: no style, geometry or missing finding on any viewport.

Structure, content and `ignored` findings are reported and never change the
verdict; the root's own box and margins are context, not evidence.
Accessibility findings are reported even when both sides share them.
Unmeasurable contrast is an accessibility finding that counts as a blocked
check in Global Verdict step 2.

## Global Verdict

Apply in this order:

1. `FINDINGS` when any row is `DRIFT` or `MISSING`, or accessibility has a
   confirmed failure.
2. `BLOCKED` when no finding is established but a required row or check is
   blocked, evidence is degraded, or status is `no comparison evidence`.
3. `CLEAN` only with complete DOM evidence, every row `MATCH` or `EXPECTED`,
   every required accessibility check complete and passing, and no visible
   in-scope surface missing from the map.

## Rechecks

After fixes, rerun every prior `DRIFT`, `MISSING` and `BLOCKED` row and
every row whose implementation files changed, under the original
conditions, at only the viewports whose evidence cell was not `MATCH`; a
shared primitive, token, global style or theme change reruns every row at
every viewport. Pairings persist. Return a delta of resolved, remaining and
new findings; a fix description is not proof.

## Report

Return the ledger path with the updated rows, then the report template in
`references/report-format.md`, which also defines evidence status labels.

## Forbidden Behaviors

- Declaring `CLEAN` from screenshots, source files or visual impression.
- Skipping the snapshot because the UI looks right.
- Writing a verdict without a diff file behind it.
- Editing snapshot or diff JSON by hand.
- Leaving a ledger row `PENDING` or blank.
- Writing `Ignore` entries or any other cell of `.parity/parity-map.md`
  yourself.
- Narrating between captures, or running one capture per row when a
  manifest exists.
- Writing `EXPECTED` without a reason.
- Interpolating selectors or component names into script text.
- Resolving components by name on the real app side.
- Matching nodes by class names or by attributes other than the parity
  hooks.
- Fixing implementation code while acting as the verifier.
