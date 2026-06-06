---
name: ticket-implementation-unit
description: Use when implementing an approved ticket work unit, plan slice, feature slice, or delegated implementation task that must return an implementation report, local checks, concrete implementer self-review, risks, and handoff notes before QA/UIUX verification.
---

# Ticket Implementation Unit

## Overview

Implement one approved work unit. A work unit may be a ticket, backend/API slice, UI slice, migration, background job, integration slice, or focused fix packet.

This skill belongs to the implementer. It does not own ticket intake, requirements/design approval, implementation-plan approval, QA verification, UI/UX verification, PR review, Ship, or global readiness. The implementer returns evidence that the work unit is **ready for verification**, not globally complete.

## Required Inputs

Expect a self-contained implementation request with:

- work-unit goal and acceptance criteria
- approved requirements/design direction
- approved implementation plan slice
- codebase scope locators and affected surfaces
- repository instructions and ownership constraints
- expected local checks or test areas
- current branch/worktree state
- dependencies, sequencing constraints, and explicit non-goals

If required inputs are missing or contradictory, stop with `IMPLEMENTATION BLOCKED` and name the missing input or conflict.

## Implementation Rules

- Stay inside the approved plan slice and explicit non-goals.
- Use existing project patterns and smallest safe changes.
- Keep changed files traceable to the work-unit goal and scope locators.
- Run the narrowest relevant local tests/checks first, then broaden only when risk or shared behavior requires it.
- Do not claim QA passed, UI/UX passed, PR review passed, Ship readiness, or global completion. Those are separate verifier/orchestrator responsibilities.
- If a finding packet asks for a focused fix, fix that finding and rerun the narrowest relevant local check; do not broaden into unrelated cleanup.

## Implementer Self-Review

Self-review is required before returning the report. It is not QA, UI/UX verification, or PR review.

Inspect the local diff against:

- approved plan slice and acceptance criteria
- obvious regressions and edge cases
- naming, ownership boundaries, and side effects
- tests/check coverage appropriate to the change
- accidental broadening beyond the approved work unit
- handoff risks for QA/UIUX verifiers

Record concrete notes. Do not write "self-review passed" without naming what was checked.

## Report Format

Return a compact report the orchestrator can paste into a readiness ledger:

```markdown
# Implementation unit report — <work unit>

## Status
- <READY FOR VERIFICATION | IMPLEMENTATION BLOCKED>

## Summary
- <what changed and why>

## Files changed
- `path` — <purpose>

## Local tests/checks run
- `<command or check>` — <pass/fail/not run and reason>

## Implementer self-review report
- Plan/AC match: <notes>
- Diff/regression review: <notes>
- Naming/ownership/side effects: <notes>
- Test/check adequacy: <notes>
- Scope control: <notes>

## Known risks or blockers
- <risk, blocker, or explicitly empty>

## Handoff notes for QA/UIUX
- QA focus: <behavior, API, service, or user-flow notes>
- UI/UX focus or skip rationale: <visible states affected, or backend-only/non-UI rationale>
```

## Stop Conditions

Stop when the implementation is applied, relevant local checks have been run or explicitly blocked, the implementer self-review report is complete, and the handoff notes are specific enough for QA/UIUX verification.

If blocked, do not partially fill a success report. Return `IMPLEMENTATION BLOCKED` with the missing input, failing command, conflict, or dependency.

## Forbidden Behaviors

- Returning only a prose summary with no files changed, tests/checks, or self-review.
- Claiming QA/UIUX passed without separate verifier reports.
- Saying the work unit is complete, shippable, or ready to merge.
- Treating self-review as a substitute for QA, UI/UX verification, or PR review.
- Broadening beyond the provided plan slice without orchestrator approval.
