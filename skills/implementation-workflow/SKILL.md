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
- affected files/surfaces, if already known
- repository instructions and ownership constraints
- current branch/worktree state
- dependencies, sequencing constraints, and known risks

If required inputs are missing, stale, or contradictory in a way that affects safe implementation, stop with `IMPLEMENTATION BLOCKED` and name the missing input or conflict.

## Delegation checkpoint

Before broad searches or large file reads, consider dispatching read-only subagents for independent, compressible discovery such as repo-wide reference inventories, external API research, test-surface mapping, docs/env/deploy sweeps, or PR/status checks.
Keep the main agent responsible for the approved plan, repo instructions, workflow interpretation, core code path, implementation decisions, and approval-sensitive artifacts. Subagent outputs must be concise, locator-backed, and categorized; avoid raw dumps.
Delegated and inline discovery together must still populate the implementation scope map: affected files/surfaces, entry points, tests, risks, and verification surfaces with locators. If choosing not to delegate a plausible broad discovery task, briefly state why.

## Implementation Workflow

1. Start from the approved spec/design and implementation plan. Resolve missing, stale, or contradictory context before editing.
2. Decide the code-scanning depth needed before editing based on the approved plan, ambiguity, risk, coupling, and current confidence. Map the relevant codebase surface before editing, using the delegation checkpoint for broad independent discovery when it preserves output quality and saves main-context load. Capture affected files/surfaces, entry points, tests, risks, and verification surfaces with locators.
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
Include those same items in the review handoff, plus the changed files or diff when available.

Wait for the reviewer to finish.

Filter the reviewer findings and discard any irrelevant findings given the approved goals.

## Verification

Dispatch the `qa-verifier` subagent when available; otherwise dispatch a sufficiently capable generic QA subagent to perform manual QA verification against the ACs from the ticket. Pass all relevant context to the subagent. This verification is mandatory and the flow cannot move forward until manual QA verification is performed.
Include the acceptance criteria, implemented surface, setup/runtime details, affected files or surfaces, changed behavior, known risks, and any review/fix context in the QA handoff.

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
