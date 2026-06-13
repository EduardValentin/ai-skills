---
name: coordinate-ticket-execution
description: Use when coordinating the execution phase for one ticket or work unit from an approved execution packet, especially when implementation, independent review, QA or UI verification, fixes, PR preparation, and completion evidence must remain phase-separated. Do not use for intake, brainstorming, spec creation, plan creation, approval gathering, planning-only work, QA-only work, PR-only work, or multi-ticket coordination.
---

# Coordinate Ticket Execution

## Purpose

Use this skill during execution of one already-approved ticket or work unit. You coordinate the execution phase from an approved execution packet and return phase evidence to the caller.

This skill is not for discovering or negotiating scope. Missing requirements go back to the parent or main coordinator.

Core rule: do not personally perform all execution phases as one worker. When naming execution delegation, name `implementation-worker` for implementation, `code-reviewer` for independent review, `security-reviewer` when there is a plausible security surface, `qa-verifier` for behavior verification, and `uiux-verifier` for UI/UX verification when available. If nested delegation is unavailable, state that limitation and preserve phase separation locally.

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

1. Validate the approved packet and restate the execution boundary. Always state that missing, stale, contradictory, or unapproved facts return `BLOCKED_NEEDS_PARENT_INPUT` to the parent or main coordinator.
2. Create a compact execution ledger for delegated work, findings, fixes, reruns, PR state, blockers, and final evidence.
3. Dispatch `implementation-worker` native agent(s) for the approved implementation slice or slices. Keep implementation separate from independent review and verification.
4. Dispatch `code-reviewer` against the approved packet, implementation evidence, and diff.
5. Dispatch `security-reviewer` when the change has a plausible security surface. Record the skip reason only when there is no plausible security surface.
6. Dispatch `qa-verifier` against acceptance-criteria behavior in the running app, service, API, job, script, or integration.
7. For UI-facing or mixed work, dispatch `uiux-verifier`. For non-UI work, record the skip reason.
8. Aggregate findings. Delegate scoped fixes for fixable findings, then rerun affected review or verification.
9. Repeat the finding, fix, and rerun loop until each required phase is clean, explicitly blocked, or explicitly out of scope.
10. Prepare the PR with reviewer-friendly summary, testing evidence, and review focus.
11. Return the completion report. Do not mark complete without the required phase evidence and PR link.

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
- Security review: <clean / findings fixed / blocked / not applicable>
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
