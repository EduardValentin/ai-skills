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
- Parity artifacts are session records. They live in the project's gitignored
  parity folder and are never committed or copied into design documentation.

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

3. Inspect two or three pages or flow states in the browser and capture
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

## Parity Artifacts

The parity folder is `.parity/` at the project root unless the project's
agent instructions name another path. Confirm it is gitignored before writing
into it; if it is not, add it to the ignore file as part of the session. It
holds two files, created from the templates under `assets/` and rebuilt each
session for the surfaces the session touches:

- `component-map.md`: one row per production component, section or page
  touched, paired with its prototype counterpart, routes, states and pairing
  confidence. Derive it from the two trees; confirm every pairing that is not
  an obvious name match.
- `ledger.md`: one row per user-visible element added or modified, per
  meaningful state, with stable selectors on both sides, a `Verdict` column
  the verifier writes, and an `Evidence` column the verifier writes. A second
  table records design changes made in the session and whether both sides
  were updated.

The implementer maintains both files as the work progresses: add a ledger row
when an element is added or modified, and a design-change row when a design
decision is made. Do not wait for the parity step to reconstruct them.

## Parity Step

Runs once the inner implementation workflow has returned
`IMPLEMENTATION COMPLETE` for the unit, and before any PR is raised.

1. Bring the ledger current: every element added or modified in the unit has
   a row per meaningful state; every design change has a row with both
   updated columns reading yes. Confirm the component map pairings.
2. Start both apps. Record the viewport set from the project's breakpoints,
   with one width just below and one just above each, plus 320 and 1920.
3. Dispatch `parity-verifier` with the ledger and map paths, both app URLs,
   the viewport set, the theme, and the diff. It writes a verdict and
   evidence into every row and returns its report.
4. Read the ledger. For every row that is not `MATCH`, the implementer fixes
   the production side, or the prototype side when the design change was
   made there and production is the source of the row's basis. A fix to a
   shared primitive, token or global style widens the recheck to every row.
5. A confirmed accessibility failure the prototype shares is a design defect:
   fix it in the prototype first, mirror it in production, record a
   design-change row, and re-verify. Only the user may waive it; a waiver is
   recorded in the ledger's design-changes table and named in the PR, and it
   is the sole case where a FINDINGS report may proceed.
6. Re-dispatch `parity-verifier` for the affected rows with the same
   conditions. Repeat until every row reads `MATCH` and the report verdict is
   `CLEAN`.
7. Hand the ledger path and the final parity report to PR readiness as the
   parity evidence.

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
- Committing anything under the parity folder or copying its state into
  design documentation.
- Rebuilding the ledger from memory at the end instead of maintaining it
  during the work.
- Landing any fix after the parity step without re-running it; a later fix
  invalidates the ledger.
