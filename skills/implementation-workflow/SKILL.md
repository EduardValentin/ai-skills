---
name: implementation-workflow
description: Use only when the context already includes an approved implementation plan, approved plan slice, or approved implementation packet and the user asks to implement that approved code unit, including focused fixes, scripts, migrations, service changes, UI changes, or integrations. Do not use for ticket or issue start, coding-scope setup, feature-branch ticket setup, ticket intake, user-facing requirements approval, spec/design approval, implementation-plan approval, PR readiness only, or ticket-set coordination.
---

# Implementation Workflow

## Purpose

Implement approved code work with strong engineering judgment, review, verification, and reporting.

This workflow owns implementation, code quality, code review, security review when relevant, QA/runtime verification, UI verification when relevant, fixes, reruns, and the implementation report.

It does not own user-facing ticket intake, requirements approval, spec/design approval, implementation-plan approval, PR readiness, release, merge, or tracker-state changes.

## Required Inputs

Expect enough context to implement safely:

- unit goal and acceptance criteria, or a clear user-observable outcome
- approved boundary, including explicit non-goals
- approved implementation plan or approved plan slice
- known affected files/surfaces or permission to inspect and discover them
- repository instructions and ownership constraints
- current branch/worktree state
- dependencies, sequencing constraints, and known risks

Require the approved spec/design when applicable and an approved implementation plan or approved plan slice for every implementation unit. Do not infer missing boundaries or proceed without the required approval.

If required inputs are missing, stale, or contradictory in a way that affects safe implementation, stop with `IMPLEMENTATION BLOCKED` and name the missing input or conflict.

## Implementation Workflow

1. Start from the approved spec/design and implementation plan. Resolve missing, stale, or contradictory context before editing.
2. Inspect enough code to avoid blind edits, including nearby callers/callees, shared types/contracts, analogous implementations, tests, configuration, and affected architecture surfaces when they could affect the change.
3. Implement the approved plan using the most appropriate execution shape for the approved unit. Prefer delegated execution for separate plan slices when it materially improves quality, focus, parallelism, or context management.
4. Run the review phase.
5. Run the security phase, or record why there is no plausible security surface.
6. Run the verification phase.
7. Return the implementation report.

## Engineering Invariants

- Stay inside the approved boundary; do not broaden scope or change the approved plan without approval.
- If implementation reveals that the approved plan should change, return to the relevant approval gate before continuing.
- Adopt a TDD approach when making changes: express the intended behavior with a failing test first, implement the change, then rerun the test and relevant checks.
- Follow existing project patterns unless the approved plan requires a justified deviation.
- Do not patch narrowly when the change affects contracts, shared state, dependency flow, error handling, performance, or public behavior.
- Prefer clear names that expose purpose, domain invariants, and side effects.
- Avoid duplicating logic, hiding side effects, or adding abstractions that do not reduce real complexity.
- Prefer quality, readability, maintainability, and performance over speed.
- Keep changes traceable to the unit goal and acceptance criteria.

When summarizing the implementation loop before or during edits, name the chosen execution shape, the existing-patterns check, and the quality, readability, maintainability, and performance preference explicitly.

## Review

Request independent review before treating implementation as complete.

Use every configured review channel available for the repository:

- start a fresh-context review session with another capable agent and ask it to review the PR against the approved goal, acceptance criteria, approved plan, repository instructions, and relevant codebase context
- request an external frontier-model review when a separate model/runtime is available
- request automated PR review when the repository has an automated review service configured

Have reviewers post findings on the PR whenever the review channel supports PR comments. The implementing agent owns the review loop: address valid findings, rerun affected checks, reply with the fix evidence, and mark the addressed comments resolved.

After each batch of fixes, request a fresh review from every configured review channel again. Do not stop the implementation workflow until every available required reviewer has approved the PR, or until a reviewer is unavailable or blocked and the blocker is reported explicitly.

When implementation exists but review evidence is missing, state the exact review requests to make next for every configured review channel, including the review focus, PR-comment expectation when supported, fix ownership, comment resolution, and fresh-review loop after each fix batch until every required reviewer approves or an explicit blocker is reported.

When asked whether implementation is complete, treat missing review-loop evidence as incomplete unless the report covers every configured review channel, PR comments when supported, valid findings addressed, comments resolved, affected checks rerun, and fresh approval or explicit blocker from each required reviewer.

## Security

When the change has a plausible security surface, request a security-focused pass through the same configured review channels. Ask reviewers to focus on auth/session, authorization, user input, data exposure, persistence, redirects, file handling, external requests, privileged actions, dependencies, sensitive logging, and changes to what users can see or do.

Address valid security findings through the normal review loop. If security review is skipped, record why there is no plausible security surface.

When a plausible security surface exists and security evidence is missing, state the exact security-focused review request to make next through the configured review channels.

## Verification

Run QA manual verification against the running application and confirm the acceptance criteria received as input are met. Do not mock third-party dependencies such as services and databases unless starting the real app and testing against real dependencies is not feasible.

Running automated tests does not count as manual QA verification.

For UI-facing or mixed work, verify visual consistency, accessibility, relevant states, and responsive behavior. Use DOM/computed-style/bounding-rect evidence where possible; screenshots alone are not enough for visual parity claims.

Record anything not run and why. A missing check is acceptable only when the reason is explicit and the residual risk is reported.

When executable behavior changed and manual QA evidence is missing, state the exact manual QA verification to run against the running application and acceptance criteria. Keep automated tests separate from manual QA evidence.

## Report Format

Return a compact report:

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
- <review channels requested, approval status, findings addressed, unresolved blockers>

## Security
- <security result or skip rationale>

## Runtime or manual verification
- <verification performed, evidence, or blocker>

## Engineering notes
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
- skipping runtime/manual verification when executable behavior changed
- skipping UI verification for UI-facing work
- skipping security review when there is a plausible security surface
- stopping before required review channels approve, unless an unavailable or blocked reviewer is reported explicitly
- returning only a prose summary with no changed files, checks, review result, or risks
- broadening beyond the approved unit without approval
