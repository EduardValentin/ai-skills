---
name: implementation-workflow
description: Manual workflow for approved code work through implementation, review, verification, fixes, and reporting.
disable-model-invocation: true
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
---

# Implementation Workflow

## Purpose

Implement approved code work with strong engineering judgment, review, verification, and reporting.

This workflow owns implementation, code quality, code review, manual QA verification, fixes, reruns, and the implementation report.

It does not own user-facing ticket intake, requirements approval, spec/design approval, implementation-plan approval, PR readiness, release, merge, or tracker-state changes.

Once an approved implementation plan exists and the next action is coding that plan, the selected execution mode follows this workflow's review, verification, fix/rerun, and reporting contract.

## Required Inputs

Expect enough context to implement safely:

- unit goal and acceptance criteria, or a clear user-observable outcome
- approved boundary, including explicit non-goals
- approved implementation plan or approved plan slice
- known affected files/surfaces or permission to inspect and discover them
- repository instructions and ownership constraints
- current branch/worktree state
- dependencies, sequencing constraints, and known risks

If required inputs are missing, stale, or contradictory in a way that affects safe implementation, stop with `IMPLEMENTATION BLOCKED` and name the missing input or conflict.

## Delegation

For delegation requests, prefer a native available subagent when one is defined for the required task. Otherwise spawn the most capable generic subagent, with capability and scope automatically determined from the task complexity, risk, and evidence needed. If delegation is unavailable or unsafe, perform the work inline and state why.

## Implementation Workflow

1. Start from the approved spec/design and implementation plan. Resolve missing, stale, or contradictory context before editing.
2. Decide the code-scanning depth needed before editing based on the approved plan, ambiguity, risk, coupling, and current confidence. If affected surfaces are not sufficiently mapped, dispatch `code-mapper` for a read-only scope report before editing; name that dispatch explicitly instead of returning a generic mapping blocker. If code mapping or context gathering is unavailable or unsafe, stop with `IMPLEMENTATION BLOCKED` and name the missing context.
3. Implement the approved plan using the execution mode selected before this workflow starts.
4. Run the review phase.
5. Run the verification phase.
6. Return the implementation report.

## Engineering Invariants

- Stay inside the approved boundary; do not broaden scope or change the approved plan without approval.
- If implementation reveals that the approved plan should change, stop with `IMPLEMENTATION BLOCKED`, state how the plan should change and why, and do not continue until the plan change is approved.
- Adopt a TDD approach when making changes: express the intended behavior with a failing test first, implement the change, then rerun the test and relevant checks.
- Follow existing project patterns unless the approved plan requires a justified deviation.
- Do not patch narrowly when the change affects contracts, shared state, dependency flow, error handling, performance, or public behavior.
- Prefer clear names that expose purpose, domain invariants, and side effects.
- Avoid duplicating logic, hiding side effects, or adding abstractions that do not reduce real complexity.
- Keep changes traceable to the unit goal and acceptance criteria.
- Keep security implications in mind while implementing or delegating work, especially auth/session, authorization, user input, data exposure, persistence, redirects, file handling, external requests, privileged actions, dependencies, sensitive logging, and changes to what users can see or do.

## Review

Request independent review before treating implementation as complete.

Start a fresh-context review session with `code-reviewer` when available; otherwise dispatch a sufficiently capable generic read-only review subagent. Ask it to review the PR against the approved goal, acceptance criteria, approved plan, repository instructions, and relevant codebase context.

Wait for the reviewer to finish.

Filter the reviewer findings and discard any irrelevant findings given the approved goals.

## Verification

Dispatch the `qa-verifier` subagent when available; otherwise dispatch a sufficiently capable generic QA subagent to perform manual QA verification against the ACs from the ticket. Pass all relevant context to the subagent. This verification is mandatory and the flow cannot move forward until manual QA verification is performed.

## Report Format

Return a compact report:

Include every section even when the work is blocked or incomplete. If a section's evidence is unavailable, say that explicitly and name the blocker instead of omitting the section.

When the user asks whether implementation is complete and independent review or manual QA verification is missing, do not answer with only next steps. Return `IMPLEMENTATION BLOCKED` using this report format, with the Review and Manual QA verification sections naming the required dispatch, wait condition, and missing evidence.

```markdown
# Implementation report - <unit>

## Status
- <IMPLEMENTED | IMPLEMENTATION BLOCKED>

## Boundary
- In scope: <summary>
- Out of scope: <summary>

## Summary
- <what changed and why>

## Files changed
- `path` - <purpose>

## Checks and verification
- `<command or check>` - <pass/fail/not run and reason>

## Test strategy
- <test-first evidence, test update, or why another verification path was used>

## Review
- Reviewer delegation: <delegate used, inline reason, unavailable reason, or blocker>
- Reviewer completion: <finished, unavailable, blocked, or not run and why>
- Findings: <relevant findings, discarded irrelevant findings with rationale, fixed findings, or none>

## Manual QA verification
- Manual QA: <delegate used, ticket ACs verified, evidence, or blocker>

## Engineering notes
- Input freshness/conflicts: <resolved, none found, unresolved, or blocker>
- Code/repository context: <what was inspected, delegated, unnecessary, unavailable, or blocked>
- Architecture/context considered: <callers, contracts, shared surfaces, analogous code>
- Maintainability/performance notes: <notes or exceptions>

## Risks or blockers
- <risk, blocker, or explicitly empty>
```

If blocked, do not fill a success report. Return `IMPLEMENTATION BLOCKED` with the missing input, failing command, architectural conflict, dependency, approval gap, or unsafe ambiguity.

## Red Flags

Stop and recover when:

- implementing without enough goal, scope, constraints, or verification context to proceed safely
- treating a delegated unit as permission to redesign product direction
- reading only the file to edit when nearby architecture, callers, contracts, or tests could affect the change
- claiming TDD was followed without first adding or updating a meaningful failing test, or skipping tests without a reason
- treating developer checks as acceptance, visual, or PR-verdict verification
- skipping review entirely
- treating implementation as complete before the independent reviewer finishes
- moving forward before mandatory manual QA verification is performed
- answering a completion question with review or manual QA next steps but no blocked implementation report
- returning only a prose summary with no changed files, checks, review result, or risks
- broadening beyond the approved unit without approval
