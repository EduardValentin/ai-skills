---
name: execute-ticket-work
description: Use when an agent receives an approved execution packet for one ticket or work unit and needs to execute that approved unit. Do not use for intake, brainstorming, spec creation, plan creation, approval gathering, planning-only work, QA-only work, PR-only work, or multi-ticket coordination.
---

# Execute Ticket Work

## Purpose

Use this skill during execution of one already-approved ticket or work unit. You coordinate the execution phase from an approved execution packet and return phase evidence to the caller.

This skill is not for discovering or negotiating scope. Missing requirements go back to the parent or main coordinator.

Core rule: do not personally perform all execution phases as one worker. Use nested delegated subagents for implementation, independent review, QA, UI/UX verification, scoped fixes, and PR preparation when available. If nested delegation is unavailable, state that limitation and preserve phase separation locally.

## Required Input

Require an approved execution packet before starting. It should include:

- ticket or unit context and acceptance criteria
- approved spec/design direction
- approved implementation plan
- approval state
- scope locators or affected files/surfaces
- repository instructions, branch/worktree state, constraints, dependencies, and non-goals
- expected checks, PR expectations, UI/UX applicability, and completion-report requirements

If required packet details are missing, stale, contradictory, or unapproved, stop with `BLOCKED_NEEDS_PARENT_INPUT`. Name the missing input or conflict. Do not brainstorm, infer missing scope, negotiate changes, or proceed on a best guess.

## Execution Workflow

1. Validate the approved packet and restate the execution boundary. If validation finds missing, stale, contradictory, or unapproved facts, return `BLOCKED_NEEDS_PARENT_INPUT` to the parent or main coordinator.
2. Create a compact execution ledger for delegated work, findings, fixes, reruns, PR state, blockers, and final evidence.
3. Dispatch focused implementation subagents when nested delegation is available. Keep implementation separate from independent review and verification.
4. Dispatch independent review against the approved packet, implementation evidence, and diff.
5. Dispatch QA verification against acceptance-criteria behavior in the running app, service, API, job, script, or integration.
6. For UI-facing or mixed work, dispatch UI/UX verification. For non-UI work, record the skip reason.
7. Aggregate findings. Delegate scoped fixes for fixable findings, then rerun affected review or verification.
8. Repeat the finding, fix, and rerun loop until each required phase is clean, explicitly blocked, or explicitly out of scope.
9. Prepare the PR with reviewer-friendly summary, testing evidence, and review focus.
10. Return the completion report. Do not mark complete without the required phase evidence and PR link.

If nested delegation is unavailable, perform the coordination locally and make that limitation explicit in the report.

## Completion Report

Return a compact report:

```markdown
# Execution report - <ticket or unit>

## Status
- <READY | BLOCKED_NEEDS_PARENT_INPUT | BLOCKED_EXECUTION | BLOCKED_VERIFICATION>

## Packet
- Approved scope: <summary>
- Approval state: <confirmed / missing / stale>

## PR
- <PR link or why unavailable>

## Delegation
- <nested subagents used, or limitation if unavailable>

## Phase evidence
- Implementation: <report summary>
- Independent review: <clean / findings fixed / blocked>
- QA: <clean / bugs found / cannot verify / not applicable>
- UI/UX: <clean / findings / cannot verify / not applicable>
- Fixes and reruns: <summary>

## Checks and risks
- Checks run: <commands or evidence>
- Risks/blockers: <items or none>
- Parent input needed: <questions or none>
```

## Forbidden Behaviors

- Starting without an approved execution packet.
- Brainstorming with the human, inventing requirements, negotiating scope, or changing the approved plan.
- Combining implementation, independent review, QA, and UI/UX verification into one undifferentiated worker task.
- Treating implementer self-checks or parent-side inspection as independent review or verification.
- Marking complete without PR evidence and required phase reports.
- Hiding missing tooling, access, tests, acceptance criteria, or approval state.
