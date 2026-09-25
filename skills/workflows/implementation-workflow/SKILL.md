---
name: implementation-workflow
description: Use when an approved implementation plan or plan slice is ready for code changes and the work must continue through specialized independent review, manual QA, rendered visual verification, remediation, reruns, and reporting.
compatibility: >-
  Requires fresh-context dispatch of the native reviewer agents (acceptance-criteria, architecture, code-cleanliness, security, performance, and design-system when styling changes) and of `qa-verifier` and `visual-verifier`. A missing native agent may be replaced by a fresh generic subagent given that agent's mandate and preloaded skill; if fresh-context dispatch is impossible for any gate, return `IMPLEMENTATION BLOCKED`.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Implementation Workflow

## Scope

Implement an approved code unit and carry it through code quality checks, a
fan-out of specialized independent reviews, manual QA, rendered visual
verification when a rendered surface changed, remediation, reruns, and a
traceable implementation report.

This workflow starts after implementation-plan approval. It does not own
requirements intake, source-of-truth approval, design approval, plan approval,
execution-mode selection, PR readiness or publication, release, merge, or
tracker-state changes. It knows nothing about any outer workflow that may wrap
it; it returns a terminal state and the outer workflow continues.

Preserve the execution mode selected before this workflow starts. Delegation
does not transfer responsibility for repository instructions, plan
interpretation, integration, scope control, or approval-sensitive decisions
away from the main agent.

## Entry Gate

Require:

- an approved implementation plan or approved plan slice
- acceptance criteria or another clear, approved user-observable outcome, and
  explicit non-goals
- applicable source-of-truth requirements or design decisions, when the work
  has them
- repository instructions, ownership constraints, and current branch or
  worktree state
- known dependencies, sequencing constraints, risks, and expected verification
  surfaces
- the **reviewer selection** for the review gate, recorded at ticket intake;
  when absent, the review gate asks the user once with its defaults
- an **expected-demand profile**: product stage, expected users, request and
  data volumes, growth expectations, and reliability expectations. Fill it
  from repository instructions or ticket context. If neither states it, ask
  the user before proceeding; do not guess and do not leave it blank.

Check that the packet is current and internally consistent. If required
context is missing, stale, or contradictory enough to make implementation
unsafe, return `IMPLEMENTATION BLOCKED`. Name the blocker and the exact input
or approval needed; do not infer scope or edit.

## Completion States

Use only these terminal states:

- `IMPLEMENTATION COMPLETE`: the approved behavior is implemented, relevant
  automated checks pass or have a documented justified exception, the review
  gate ended with every reviewer at `CLEAN`, manual QA has passing evidence
  for every acceptance criterion, and rendered visual verification is clean or
  was not applicable because no rendered surface changed.
- `IMPLEMENTATION BLOCKED`: any required gate cannot be completed, including
  an unavailable input, an unapproved plan change, a check that cannot be
  resolved, a review gate exhausted without unanimous approval, or missing QA
  or visual evidence.

A blocked result still reports all available implementation, check, review,
QA and visual evidence plus the next required input or decision. Never
describe unfinished review or verification as optional follow-up work.

## Discovery and Delegation

Choose scanning depth from the plan's ambiguity, risk, coupling, and current
confidence. Before editing, produce a locator-backed scope map covering
affected files or surfaces, entry points, tests, risks, and verification
surfaces. Record whether the diff will touch a rendered surface (components,
styles, tokens, layout, or copy that affects layout) and whether it will touch
styles, tokens or UI primitives; the gates below key off those two facts.

Before broad searches or large reads, consider fresh, read-only subagents for
independent and compressible discovery. Keep plan interpretation and the core
code path with the main agent.

## Implementation

1. Confirm the entry gate and approved execution mode.
2. Build the scope map and inspect the relevant architecture, callers,
   contracts, and tests.
3. Implement only the approved plan, following repository patterns unless the
   plan justifies a deviation.
4. Run focused checks first, then the relevant regression checks implied by
   risk and coupling.
5. Run the review gate to unanimous `CLEAN`.
6. Run the verification gate to passing evidence.
7. Return the implementation report.

### Engineering Invariants

- Stay inside the approved boundary. If implementation reveals that the plan
  must change, return `IMPLEMENTATION BLOCKED`, explain the required change
  and why, and wait for approval.
- Use TDD for behavior changes: add or update a meaningful test, observe the
  intended failure, implement, and rerun the focused and relevant regression
  checks.
- When no meaningful automated test can exercise the change, document why
  before implementation and record the strongest available deterministic and
  manual evidence in the report. Do not claim TDD in that case.
- Prefer names that expose purpose, side effects, and domain invariants.
- Trace every change to the approved goal, criteria, or required supporting
  behavior.
- Avoid duplicated logic, hidden side effects, and abstractions that do not
  remove real complexity.
- Assess security implications where relevant, especially authentication,
  authorization, user input, data exposure, persistence, redirects, files,
  external requests, privileged actions, dependencies, and sensitive logging.

## Review Gate

One round is one fan-out against a frozen diff. Reviewers are read-only and
return findings; the main agent decides and fixes. Round one dispatches every
selected reviewer against the full frozen diff; every later round is scoped
by the delta since the previous round.

1. Freeze the diff or working tree to review.
2. Dispatch the reviewers named in the packet's reviewer selection in
   parallel, each with the task, acceptance criteria, approved plan,
   non-goals, the frozen diff, the scope map, repository instructions, and the
   expected-demand profile. The full set is `acceptance-criteria-reviewer`,
   `code-cleanliness-reviewer`, `security-reviewer`, `performance-reviewer`,
   `design-system-reviewer`, and `architecture-coordinator` in change-review
   mode over the frozen diff. Change review runs only when the structural
   precheck passes: place the diff's files in components of the committed
   record's `docs/architecture/components.md` by path, and dispatch when they
   fall in two or more components, or the diff adds a package, a port, an
   import between components, or an external dependency, or no committed
   record exists; otherwise record `architecture change review: skipped,
   single-component diff` and run the other selected reviewers. When the packet carries no selection, ask the
   user once with these defaults: `acceptance-criteria-reviewer` and
   `code-cleanliness-reviewer` selected; `design-system-reviewer` selected
   when the diff touches styles, tokens, or UI primitives in a design-system
   source the repository keeps; the others not selected. Record the answer
   and reuse it for every round of this gate.
3. Aggregate all findings. Deduplicate findings that name the same location
   and defect, keeping the highest severity and every reviewer's suggested
   fix. Security severities map as critical and high to blocker, medium to
   major, low to minor. Resolve conflicting suggestions against the approved
   plan, repository instructions, and the demand profile; when architecture
   review ran, resolve its findings first, because their fixes move code and
   can void other findings.
   Record every rejected finding with its reason; a finding is rejected only
   when it is technically wrong, outside the approved scope, or overridden by
   repository instructions.
4. Address every accepted blocker and major finding. Add or update a
   meaningful failing test first when the issue is automatable. Rerun focused
   and affected regression checks.
5. A fix invalidates only the approvals its delta can touch. Freeze the
   revised diff and compute the delta: the diff between the previous frozen
   diff and the revised one. Re-dispatch a selected reviewer when it raised
   an accepted finding in the previous round, or when the delta meets its
   predicate in the invalidation table below. Otherwise carry its prior
   `CLEAN` forward and record `carried forward: <predicate not met>`.
   A re-dispatched reviewer receives the delta as its review target, the
   full revised diff for context, its own prior findings with dispositions,
   and this instruction: confirm each accepted finding is resolved, review
   the delta and any unchanged code whose behavior the delta changes, and do
   not re-review hunks unchanged since the previous round's frozen diff.
6. The gate passes when every selected reviewer is `CLEAN` in the same
   round, re-dispatched or carried forward. A unanimous CLEAN round ends the
   gate; minor findings from that round are recorded with dispositions in
   the implementation report and do not trigger another round.
7. Budget: three rounds. If round three ends without unanimous `CLEAN`,
   return `IMPLEMENTATION BLOCKED` with the remaining findings and their
   dispositions.

If a reviewer returns a cannot-proceed or needs-more-context report, supply
the named input and re-dispatch that reviewer within the same round; if the
input requires a user decision, ask the user, then continue.

### Invalidation Table

Judge each predicate from the delta's hunks, not from the ticket's overall
shape.

| Reviewer | The delta invalidates its prior `CLEAN` when it |
|---|---|
| `acceptance-criteria-reviewer` | changes runtime behavior, user-visible output, or a test. Renames, formatting, comments, and file moves without behavior change do not. |
| `code-cleanliness-reviewer` | adds or edits source code. Changes confined to non-code assets, generated files, or lockfiles do not. |
| `security-reviewer` | touches authentication, authorization, input parsing or validation, persistence, data exposure, redirects, files, external requests, privileged actions, dependencies, logging, serialization, or raw HTML rendering. |
| `performance-reviewer` | touches data fetching, queries, caching, loops or list rendering over collections, memoization, dependencies, background work, or a hot path the demand profile names. |
| `design-system-reviewer` | touches styles, tokens, UI primitives, or component markup. |
| `architecture-coordinator` change review | passes the structural precheck on the delta's files alone: they fall in two or more components, or the delta adds a package, a port, an import between components, or an external dependency. A delta confined to one component with no new cross-component import does not. |

## Verification Gate

Run after the review gate passes.

- Always dispatch `qa-verifier` with the acceptance criteria, implemented
  surface and entry points, setup and runtime details, changed behavior,
  known risks, check evidence, and review context. Require evidence for every
  criterion. Passing automated checks never satisfy this gate.
- When the diff touched a rendered surface, dispatch `visual-verifier` in the
  same fan-out with the running app, affected routes and states, configured
  breakpoints, and the diff. Every changed rendered surface is in scope; there
  is no exception for surfaces some other process might also check.
- Wait for every dispatched verifier. A QA `BUGS FOUND`, a visual or
  accessibility finding of severity `blocker` or `major`, or a `BLOCKED`
  visual verdict, or a cannot-proceed verdict from QA sends the work to the
  remediation loop.

Fallbacks: if `qa-verifier` is unavailable, use a separate fresh agent with
the `qa-verification` skill preloaded that can exercise the runtime surface;
if `visual-verifier` is unavailable, use a separate fresh agent with the
`visual-validation` skill preloaded. If no fresh-context verifier can produce
evidence, return `IMPLEMENTATION BLOCKED`.

## Remediation Loop

For each QA failure or visual finding:

1. Decide whether the fix remains inside the approved plan. Block and request
   approval if it does not.
2. Add or update a meaningful failing test first when the issue is
   automatable, then implement the fix.
3. Rerun the focused check and all regression checks affected by the fix.
4. Re-enter the review gate with the remediation fix as the delta over the
   last unanimous `CLEAN` diff: apply the invalidation table and the
   accepted-finding rule from step 5 of the gate instead of a full fan-out.
   The three-round budget is per review gate invocation, but a total of two
   re-entries from remediation per unit is the limit; a third re-entry
   returns `IMPLEMENTATION BLOCKED`.
5. Rerun only the affected verifier: failed and affected criteria for QA;
   affected routes, states and viewports for visual. The rerun verifier
   receives the fix delta, its prior report with the failed items marked,
   and the instruction to re-verify only those items plus anything the
   delta changes, treating earlier passing evidence as still valid. Every
   criterion and every changed surface must have passing evidence against
   the final implementation.

## Implementation Report

The final report includes:

- terminal status
- approved goal and delivered behavior mapped to the criteria or outcome
- the expected-demand profile applied
- changed files or surfaces and their purpose
- test-first evidence, focused and regression check commands, and outcomes,
  or the justified no-test exception
- review gate: rounds used, per-reviewer outcome per round (`CLEAN`,
  findings, or carried forward with the unmet predicate), accepted and
  rejected findings with dispositions
- manual QA coverage, criterion-level outcomes, and final evidence
- visual verification coverage and outcome, or `not applicable: no rendered
  surface changed`
- known residual risks and limitations, explicitly stating when none are known
- for a blocked result, the exact blocker and next required input or approval

Do not claim PR readiness, publish a PR, release, merge, or update a tracker
from this workflow.

## Red Flags

- Editing before the entry gate, demand profile and scope map are complete.
- Broadening scope or changing the plan without approval.
- Dispatching fewer than the selected reviewers in round one, or skipping
  the design-system reviewer when styles, tokens or primitives changed.
- Accepting a round as passed while any reviewer is not `CLEAN`.
- Re-dispatching every reviewer after a fix, or handing a re-dispatched
  reviewer the full diff as its review target instead of the delta.
- Carrying forward a reviewer that raised an accepted finding, or one whose
  predicate the delta meets.
- Treating automated checks as review, QA, or visual verification.
- Skipping `visual-verifier` for a changed rendered surface for any reason.
- Letting the implementer perform the independent review.
- Completing while relevant findings, failed criteria, or missing evidence
  remain.
- Claiming TDD without observing a meaningful failing test.
- Reading only the target file when callers, contracts, or adjacent tests can
  affect the change.
- Returning an unstructured prose summary without changed surfaces, checks,
  review, QA, and risks.
