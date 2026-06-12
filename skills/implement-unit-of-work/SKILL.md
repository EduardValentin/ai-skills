---
name: implement-unit-of-work
description: Use when acting as the implementer for an already approved standalone code unit or delegated implementation slice, including feature slices, ad hoc code requests, scripts, migrations, focused fixes, and scoped programming tasks after requirements, acceptance criteria, implementation plan, and codebase scope are approved.
---

# Implement Unit Of Work

## Purpose

Use this skill to implement one approved unit of code. The unit may be a delegated ticket slice, plan slice, focused fix, ad hoc user request, script, migration, service change, UI change, integration, or any other scoped programming task.

The agent using this skill is the implementer. It uses TDD for behavior changes where the project test harness supports it, writes the code, runs relevant local checks, delegates self-review of the produced diff to a separate subagent, applies necessary fixes, and returns an implementation report.

This skill does not own user-facing ticket intake, requirements approval, design approval, implementation-plan approval, product acceptance, PR review, release, merge, or tracker-state changes.

## Required Inputs

Expect a self-contained implementation request with:

- unit goal and acceptance criteria
- approved requirements/design direction
- approved implementation plan
- approved codebase scope, either as a scope map or explicit affected files/surfaces, architecture notes, and known unknowns
- repository instructions and ownership constraints
- expected local checks or test areas
- current branch/worktree state
- dependencies, sequencing constraints, and explicit non-goals

If required inputs are missing, stale, or contradictory, stop with `IMPLEMENTATION BLOCKED` and name the missing input or conflict.

## Implementation Workflow

1. Re-read the approved inputs and restate the implementation boundary.
2. Inspect the relevant code ambitiously before editing. Read the files directly in scope, nearby callers/callees, shared types/contracts, analogous implementations, tests, configuration, and any architecture surfaces that could be affected.
3. Use TDD for required features and bug fixes when the project test harness supports it: write or update a focused failing test first, run it to confirm the expected failure, implement the smallest change that turns it green, then refactor while keeping tests green. If TDD is not feasible, record the concrete reason and the alternate verification before coding.
4. Implement within the approved boundary using existing project patterns and the smallest safe design that still fits the architecture. When describing the approach or report, explicitly name the clean-code checks: clear names, focused responsibilities, three-or-fewer parameters, maintainability, and performance.
5. Run relevant developer checks, such as tests, type/lint/build, and targeted smoke commands. Start narrow, then broaden when the change touches shared behavior, contracts, performance-sensitive paths, or integration points.
6. Delegate self-review of the produced work to a separate subagent. Include the approved inputs, diff summary, changed files, local checks, TDD evidence or skip rationale, architecture concerns, and any areas where you want extra scrutiny.
7. Fix valid self-review findings, rerun affected local checks, and repeat delegated self-review if the fix materially changes the implementation.
8. Return the implementation report.

## Engineering Standards

- Preserve the surrounding application architecture. Do not patch narrowly when the change affects contracts, shared state, dependency flow, error handling, performance, or public behavior.
- Prefer clear names that expose purpose, domain invariants, and side effects. Avoid vague names such as `data`, `item`, `result`, `handler`, or `manager` unless the local domain makes them precise.
- Keep methods and functions focused on one responsibility. Orchestrator methods may coordinate steps, but should delegate meaningful work to named helpers.
- Keep new or changed methods/functions to three parameters or fewer. If preserving an existing external API, framework hook, callback signature, or generated interface requires more, call out the exception in the report.
- Favor maintainable code over clever code. Avoid duplicating logic, hiding side effects, or adding abstractions that do not reduce real complexity.
- Consider performance before finalizing. Avoid unnecessary repeated I/O, broad scans, avoidable network calls, quadratic loops on unbounded data, expensive renders, and needless recomputation.
- Keep changes traceable to the approved scope and acceptance criteria.

## Delegated Self-Review

Self-review is required and must be delegated to a separate subagent. The implementer should not mark its own work reviewed without that independent pass.

Ask the self-review subagent to check:

- match with approved requirements, acceptance criteria, and implementation plan
- architecture fit and affected callers/callees
- clean naming, responsibilities, and parameter count
- maintainability and unnecessary complexity
- performance risks
- edge cases, errors, permissions, data/state effects, and regressions
- local checks and obvious missing tests
- accidental scope broadening

Record the self-review result in the implementation report, including any findings fixed and any findings intentionally left blocked or out of scope.

## Report Format

Return a compact report:

```markdown
# Implementation report - <unit>

## Status
- <IMPLEMENTED | IMPLEMENTATION BLOCKED>

## Summary
- <what changed and why>

## Files changed
- `path` - <purpose>

## Local checks
- `<command or check>` - <pass/fail/not run and reason>

## TDD evidence
- <failing test observed, green rerun, or why TDD was not feasible>

## Delegated self-review
- Reviewer: <subagent/session label>
- Result: <clean | findings fixed | blocked>
- Notes: <what was checked and any important findings>

## Engineering notes
- Architecture/context considered: <callers, contracts, shared surfaces, analogous code>
- Naming/responsibility/parameter-count notes: <notes or exceptions>
- Performance/maintainability notes: <notes>

## Risks or blockers
- <risk, blocker, or explicitly empty>
```

If blocked, do not fill a success report. Return `IMPLEMENTATION BLOCKED` with the missing input, failing command, architectural conflict, dependency, or approval gap.

## Forbidden Behaviors

- Implementing without approved requirements/design direction, acceptance criteria, implementation plan, and scope.
- Reading only the file to edit when nearby architecture, callers, contracts, or tests could affect the change.
- Skipping delegated self-review or treating the implementer's own pass as the required review.
- Returning only a prose summary with no changed files, checks, self-review result, or engineering notes.
- Treating developer checks as acceptance, visual, or PR-verdict verification.
- Adding poorly named, over-broad, hard-to-maintain, or needlessly slow code when a cleaner option is available.
- Broadening beyond the approved unit without approval.
