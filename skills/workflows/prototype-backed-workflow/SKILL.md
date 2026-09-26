---
name: prototype-backed-workflow
description: Use when implementing, changing, or verifying user-visible UI in a project that maintains a React reference prototype app alongside the production app, including sessions that iterate on the prototype itself and sessions that must prove production matches the prototype before a PR.
compatibility: >-
  Requires a writable worktree, Bash and Git, the reference React app with its own package manager, native browser tooling, and the `parity-verifier` agent with `visual-parity-verification` preloaded. Without the agent, run `visual-parity-verification` inline from a fresh context; without browser tooling, return a parity blocker instead of a completion claim.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Prototype-Backed Workflow

## Purpose

A React reference prototype models user flows, designs, domain objects,
business rules and the design system in a single-page app with mocked
external dependencies. It is the source of truth for how production looks and
behaves. This workflow wraps ordinary implementation: it sets the rules that
apply before production code changes, and it adds the parity step that proves
production matches the prototype before a PR is raised.

## When To Use

- The repository contains a reference prototype app and the work adds or
  changes any user-visible element in production.
- The work iterates on the prototype itself: design system, flows, domain
  objects, validation, planned or existing features.
- Exploratory comparison of prototype features with production features.

Do not load this workflow for work that touches no user-visible surface.

## Hard Rules

- Prototype first. New production features and design changes are made and
  approved in the prototype before they are made in production. Production
  must not contain features or design absent from the prototype; the
  prototype may contain features absent from production.
- A design change made in production during a session is mirrored into the
  prototype in the same session and recorded in the ledger's design-changes
  table. A session ends with both sides in sync, never with a recorded
  divergence.
- Parity is proven, not asserted. The parity step below is mandatory for
  every prototype-backed application and is the last gate before the PR.
  Screenshots, unit tests, type checks and code inspection do not substitute.
- Parity has three committed files at the project root, `parity-map.md`,
  `parity-pairings.json` and `parity-actions/`, and per-session records under
  the gitignored parity root that are never committed or copied into design
  documentation.

## Preparation

Bundled paths resolve from the skill root.

1. Locate and validate the reference app:

```bash
scripts/prepare-prototype-work.sh --project-root <abs-project-path> --app-root <abs-app-path>
```

Omit `--app-root` only for discovery. If discovery finds zero or multiple
candidates, ask for the absolute app path and rerun. The helper only locates
and validates the app.

2. Use the selected app as the working directory when installing its
   dependencies or starting its development script.

3. Confirm the prototype development script serves an unminified React build.
   The parity root finder reads React's development-only fiber references;
   a production build blocks every parity row.

4. Inspect two or three pages or flow states in the browser and capture
   screenshots. Summarize the visual direction and provide compact product,
   voice, design and app-scope reports: goal, audience, core flows, business
   rules, tone, design philosophy, accessibility priorities, routes, mock
   boundaries, semantic tokens, theme configuration, component inventory and
   variants.

## Prototype Rules

- Keep mocks, routing and business rules separate from presentational
  components.
- Use configured router primitives and exercise flows by clicking through the
  app instead of typing URLs that lose local app state.
- Mock new or changed business rules explicitly.
- When a flow includes a simulated fetch, API boundary or backend-facing
  behavior, implement an explicit API-like mock for it; async states alone
  do not imply the mock.
- Represent asynchronous behavior with loading, success, empty and error
  states.

## Implementation Rules

When building or changing a surface from the prototype, write its parity
hooks with it:

- Put `data-parity-root="<ComponentName>"` on the real app element that
  renders the prototype component, and use that value as the map row's
  `Real app root` with `Confidence` `confirmed`.
- Give matching `data-parity="<name>"` to elements on both apps that have
  no role with an accessible name and no stable unique text: value cells,
  counters, icons, repeated items, wrappers that carry style. The diff
  anchors siblings by hook first, then by role and name, then by text;
  everything else is scored or paired by position and lands in the review
  lines and the manual pairings.
- Names are unique within a root and identical across apps. Never hook one
  side only; a one-sided hook anchors nothing and comes back as a hook
  suggestion.

## Parity Artifacts

Three files at the project root are committed with the code and shared by
every session:

- `parity-map.md`, created from `assets/parity-map.md`: one row per root
  pair the project has ever verified. A root pair is a prototype React
  component name and the real app element that renders the same surface,
  given as a CSS selector or as the value of a `data-parity-root`
  attribute. Each row carries a stable `C<n>` id, a route per side, its
  `States` (each optionally naming a recipe), a `Viewports` subset,
  `Ignore` entries and a `Confidence`. Ids are never reused; a new pair
  takes the next free id.
- `parity-pairings.json`: manual pairings the verifier confirmed, keyed by
  map id.
- `parity-actions/<name>.json`: optional action recipes that reach a state
  on both sides, named from the map's `States` column.

The parity root is `.parity/` at the project root unless the project's
agent instructions name another path. Confirm it is gitignored before writing
into it; if it is not, add it to the ignore file as part of the session.

Each session owns one folder under that root, named after the ticket id when
one exists (for example `GEN-123`) or, for ad hoc work, a short kebab-case
name the agent chooses that describes the change. Never write into another
session's folder and never reuse one; a leftover folder from an earlier
session is not evidence for this one. The folder holds only `ledger.md`,
created from `assets/ledger.md`, and the `snapshots/` and `diffs/` the
verifier writes.

`ledger.md` has one row per touched map row, per meaningful state; its
`Map id` column points at a `parity-map.md` row, and the verifier writes its
`Verdict` and `Evidence` columns. A second table records design changes made
in the session and whether both sides were updated.

`data-parity-root` and `data-parity` are the only markup the parity scripts
read beyond native semantics; Implementation Rules say where to write them.

The implementer maintains the map and the ledger as the work progresses:
add a map row for a new root pair, derived from the two apps and confirmed
when it is not an obvious name match; edit `States`, `Viewports` or `Ignore`
for touched rows; add a ledger row when an element is added or modified and
a design-change row when a design decision is made; commit the map with the
code. Run the parity skill's `parity_map.py check parity-map.md
--project-root .` before the parity step. Do not wait for the parity step to
reconstruct any of it. The verifier writes only `parity-pairings.json` and
the ledger; it never edits `parity-map.md` and reports the `Ignore` entries
it proposes for the implementer to add.

## Parity Step

Runs once the inner implementation workflow has returned
`IMPLEMENTATION COMPLETE` for the unit, and before any PR is raised.

Budget: one round. A round is one full dispatch of `parity-verifier` over
every row (step 3), the fixes for its findings (steps 4 and 5), and one
recheck of the affected rows (step 6). The step never loops beyond that
without the user's explicit decision.

1. Bring the map and ledger current: every new root pair has a map row and
   every touched row's `States`, `Viewports` and `Ignore` are right; every
   element added or modified in the unit has a ledger row per meaningful
   state naming its map id; every design change has a row with both updated
   columns reading yes. A difference the user accepted is a design-changes
   row whose `What changed` starts with `accepted:` followed by the reason
   and whose `Ledger rows` lists the rows it covers, so the verifier can
   write those rows as `EXPECTED` with that reason. Run `parity_map.py
   check`.
2. Start both apps. Record the viewport set from the project's responsive
   configuration: one width just below and one just above each breakpoint,
   plus the narrowest and widest widths the project supports. Use the parity
   skill's defaults only when the project defines no breakpoints.
3. Dispatch `parity-verifier` with the map, pairings and ledger paths, both
   app URLs, the viewport set, the theme, and the diff. It builds the
   capture manifest and captures with the bundled capture command when
   Playwright is available, otherwise drives the browser directly, then
   runs the bundled diff, writes a verdict and evidence into every row and
   returns its report.
4. Read the ledger. For every row that is not `MATCH` or `EXPECTED`, the
   implementer fixes the production side, or the prototype side when the
   design change was made there and production is the source of the row's
   basis. In the same step, act on the report's `Hook suggestions`: add the
   named `data-parity` hooks to both apps before the recheck. A fix to a
   shared primitive, token or global style widens the recheck to every row.
5. A confirmed accessibility failure the prototype shares is a design defect:
   fix it in the prototype first, mirror it in production, record a
   design-change row, and re-verify. Only the user may waive it; a waiver is
   recorded in the ledger's design-changes table and named in the PR, and it
   is the sole case where a FINDINGS report may proceed.
6. Re-dispatch `parity-verifier` once, for the affected rows only, under
   the same conditions and with the prior report, so it returns a delta of
   resolved, remaining and new findings. A row that is not `MATCH` or
   `EXPECTED` after this recheck is a parity blocker: stop, report the
   ledger path and the remaining rows to the user, and raise no PR. The user
   may authorize one further fix-and-recheck cycle or record a waiver in the
   ledger's design-changes table; record either decision in the parity
   report.
7. Hand the ledger path and the final parity report to PR readiness as the
   parity evidence. PR readiness accepts `EXPECTED` rows with their reasons
   and names them in the PR; the changed `parity-map.md`,
   `parity-pairings.json` and `parity-actions/` files are part of the PR.

If `parity-verifier` is unavailable, run `visual-parity-verification` from a
fresh context that did not implement the change. If no browser tooling can
evaluate scripts in both apps, stop with a parity blocker naming the missing
capability. Never claim parity from a blocked or partial ledger.

This workflow dispatches exactly one verifier, `parity-verifier`. Other
verification belongs to the inner implementation workflow.

## Red Flags

- Implementing a production feature or design change the prototype does not
  have.
- Ending a session with a design-change row whose two updated columns differ.
- Raising or preparing a PR while any ledger row is `PENDING`, `DRIFT`,
  `MISSING` or `BLOCKED`.
- Treating screenshots or a passing test suite as parity evidence.
- Adding parity hooks to one app only.
- Writing into, reusing, or reading verdicts from another session's parity
  folder.
- Committing anything under the parity root, or copying its state into
  design documentation; only `parity-map.md`, `parity-pairings.json` and
  `parity-actions/` at the project root are committed.
- Editing `parity-map.md` from the verifier role.
- Rebuilding the ledger from memory at the end instead of maintaining it
  during the work.
- Landing any fix after the parity step without re-running it; a later fix
  invalidates the ledger.
- Dispatching a second full parity round, or a second recheck, without the
  user's explicit decision.
