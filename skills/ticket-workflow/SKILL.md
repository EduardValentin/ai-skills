---
name: ticket-workflow
description: Manual workflow for one standalone ticket from intake through approved plan, implementation, and PR readiness.
disable-model-invocation: true
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
---

# Ticket Workflow

## Purpose

Coordinate one standalone ticket from intake to approved implementation plan, then confirm PR readiness after implementation completes.

This workflow owns requirements intake, context gathering, shared understanding, spec/design approval, implementation-plan approval, implementation transition, and final PR readiness. It does not define detailed implementation, review, QA, UI verification, or fix-loop mechanics.

Mandatory lifecycle:

Setup -> Brainstorm -> Spec/design approval -> Plan approval -> Implementation -> PR readiness

Approval is artifact-specific. The user can only approve an artifact they have actually seen. Approval of decisions, assumptions, recommendations, authorization, branch/worktree setup, investigation progress, or "good to go" is not approval of an unwritten spec/design or implementation plan.

## Setup

1. Confirm the ticket is standalone and intended for implementation. If unclear, ask before continuing.
2. Read the ticket to understand the goal, stakeholder implications, acceptance criteria, dependencies, and ambiguity. If the ticket has a parent Epic, parent story, or parent ticket, read that parent too.
3. Read repo instructions and only the relevant product, design, reference, and code slices needed to understand the ticket and prepare the implementation plan.
4. Inspect relevant repository state, existing PRs, and draft work only as needed to understand current status and avoid planning against stale assumptions.
5. Map the relevant codebase surface before brainstorming. Delegate the read-only scoping pass to `code-mapper`. If `code-mapper` is unavailable, use a generic read-only subagent. If delegation is unavailable or unsafe, map inline and state why. Include affected files/surfaces, entry points, analogous implementations, tests, risks, and verification surfaces with locators.

## Brainstorm

Run a relentless brainstorming interview with the user, grounded in the ticket, parent context, repo facts, relevant docs, and codebase scope.

Identify and resolve unknowns, low-confidence assumptions, stakeholder implications, constraints, edge cases, risks, non-goals, alternatives, and any detail that could even slightly affect implementation.

Treat brainstorming as an active interview loop, not a one-time question list. Ask one question at a time until you and the user reach a common understanding of the problem.

After a shared common understanding has been achieved, write a concise spec/design that captures the agreed scope, decisions, acceptance criteria, risks, alternatives considered, and open questions. Ask the user to approve the spec/design itself.

Do not write the implementation plan before spec/design approval.

## Plan

After spec/design approval, write an implementation plan that takes into consideration all gathered context and everything discussed in the brainstorming step. Present the plan and wait for explicit approval of the plan itself. Do not edit product code or tests until both spec/design and implementation plan are approved.

## Implementation

After plan approval, invoke `/implementation-workflow` for the approved implementation unit before editing. State the recommended execution approach: inline, subagent-driven delegated execution, or hybrid. Base it on the approved plan's size, coupling, risk, separability, and implementation context.

Prefer quality code over time to complete the task. Make sure the solution is well tested. If implementation reveals that the approved spec/design or plan should change, return to the relevant approval gate before continuing.

## PR Readiness

After implementation completes, confirm the ticket is ready for human review and handoff.

Do not declare the ticket ready only because implementation is complete or a PR exists. First check the readiness items below and report any missing PR metadata or evidence as a blocker.

Check:

- implementation produced a PR or a concrete blocker explaining why no PR exists
- PR target, title, description, linked ticket, and changed scope match the approved plan
- implementation, review, manual QA verification report, UI/UX prototype parity report, test, and blocker evidence is present when applicable
- PR pipeline CI checks are green; if anything fails, deliver the appropriate fix and include it in the final report
- unresolved findings, blockers, assumptions, and follow-ups are clearly reported
- ticket state is appropriate for the user's process
- no merge, completion, ticket closure, comment dismissal, or final source-control/tracker mutation happens without explicit user approval

If readiness is blocked, report the exact blocker and what needs to happen next.

Use this compact readiness shape:

- PR exists or blocker:
- target, title, description, and linked ticket:
- changed scope vs approved plan:
- implementation, review, manual QA verification report, UI/UX prototype parity report, test, and blocker evidence:
- PR pipeline CI status and fixes:
- unresolved findings, assumptions, follow-ups:
- ticket state:
- prohibited mutations without approval:

## Final Report

End with:

- ticket summary
- approved spec/design summary
- approved plan summary
- implementation status
- PR link or PR creation blocker
- PR readiness result
- ticket state
- remaining risks, blockers, assumptions, or follow-ups

## Red Flags

Stop and recover when:

- planning from stale ticket, parent, repository, or PR context
- writing product code or tests before both approval gates
- skipping codebase scoping because the ticket looks clear
- writing a vague plan that cannot guide implementation or verification
- defining detailed review, QA, UI verification, or fix-loop mechanics inside this workflow
- accepting implementation completion without PR or blocker evidence
- merging or completing the ticket without explicit user approval
