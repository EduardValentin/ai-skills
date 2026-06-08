---
name: ticket-start
description: Use when the user wants to start implementation work from one ticket - phrases like "start ticket", a Jira ticket, or a Linear issue ID. Also use for status/progress questions about a ticket already in this workflow. Covers job tickets and personal-project tickets through the ticket-system MCP or REST API fallback. Do not use for multi-ticket workflow intake, code review, planning-only, or debugging-only tasks.
---

# Ticket Start

## Purpose

Use this skill as the main-agent workflow for working one implementation ticket from intake to final report. The main agent stays the user-facing orchestrator: it gathers facts, runs the requirements/design conversation, gets approval, delegates execution and verification work to subagents where available, reconciles reports, and keeps the user informed.

Prefer subagent orchestration for implementation, self-review/review, QA verification, UI/UX verification, focused fixes, and release checks. If required subagent capability is unavailable, tell the user before replacing it with inline work.

A personal project is a project that uses GitHub for code versioning and Linear for ticket tracking.
A job project is a project that uses Bitbucket for code versioning and Jira for ticket tracking.

## When To Use

- The user asks to start, work on, build, or implement one ticket.
- The user gives a Jira ticket or Linear issue ID.
- The user asks for progress or status on a ticket already being handled here.

Do not use for multi-ticket workflow intake, pure planning, debugging-only tasks, standalone code review, or refactors with no ticket.

## Core Rules

- Memory and prior chat are hints, not source of truth. Re-read the ticket, repo, branch, PR, and relevant docs before making substantive decisions.
- Use the ticket-system MCP first. If MCP is unavailable, use the ticket system's REST API.
- Start work in a fresh worktree based on fetched `origin/main`. Fetch first; do not base ticket work on local `main`, the current branch, or a stale ref.
- Keep the main session focused on orchestration and user decisions. Do not quietly turn it into the implementer, QA verifier, UI/UX verifier, or release mutator.
- Keep delegated requests self-contained: ticket facts, acceptance criteria, approved decisions, relevant repo instructions, scope locators, constraints, expected checks, and output expectations.
- Treat subagent reports as compact evidence, not transcripts. Carry forward locators and summaries so later agents can read surgically.
- For personal workflows, use the repository's required GitHub write identity before commits, pushes, PR updates, comments, labels, transitions, or merges. Do not rely on ambient personal credentials for writes.

## Step 1 - Gather Facts

1. Identify the ticket source and workflow type: job/Jira ticket or personal/Linear ticket.
2. Read the current ticket from the ticket-system MCP, or from the ticket system's REST API when MCP is unavailable. Capture title, description, acceptance criteria, links, status, dependencies, and ambiguity.
3. If the ticket is a child issue, subtask, story under an Epic, or otherwise linked into a parent hierarchy, read the parent tickets or Epic descriptions too. Carry forward the parent problem statement, goals, constraints, and acceptance context that explain why the child ticket exists.
4. Read nearby repo instructions and workflow references. For personal projects, inspect `PRD.md`, `designs/`, or reference apps only when they exist and are relevant.
5. Inspect current git state, branches, existing PRs, and recent commits relevant to the ticket.
6. Create or verify the ticket worktree from freshly fetched `origin/main`; halt if freshness cannot be established.
7. Map the relevant code surface before planning. Prefer delegating codebase scoping when the affected surface is non-trivial, unfamiliar, shared, or UI/reference-backed. Include the ticket title, description, acceptance criteria, dependencies, repo instructions, and known constraints in the scoping request. Ask for a compact navigable scope map with file-line locators, entry points, affected surfaces, relevant tests, contracts/types, conflicts, and suggested implementation or verification slices.

## Step 2 - Brainstorm Requirements

Open with a short briefing grounded in the ticket and current repo: what is known, what is ambiguous, likely affected surfaces, relevant designs or product docs, and any conflicts.

Then brainstorm relentlessly with the user before planning. Do not stop at vague agreement or first-pass assumptions; continue until the agent and user share a concrete understanding of the work to do, the boundaries, and what success means. Cover:

- intended user or system behavior
- constraints, non-goals, dependencies, and rollout concerns
- edge cases, failure modes, permissions, accessibility, and data/state effects
- meaningful alternatives and tradeoffs
- how success will be verified

Ask for explicit approval of the requirements/design direction. This approval is separate from implementation-plan approval.

## Step 3 - Build And Approve The Plan

Write a concrete implementation plan from the approved requirements/design direction. Include:

- work units and sequencing
- affected files, services, UI surfaces, data stores, jobs, or integrations
- work areas that may benefit from delegated implementation or verification
- self-review/review, QA, and UI/UX verification expectations
- tests, commands, manual probes, and running-app checks
- risks, assumptions, non-goals, and likely fix-loop points

Ask the user to approve the plan before coding starts. Do not implement, scaffold, or mutate product code before plan approval.

## Step 4 - Execute Through Subagents

After plan approval, execute the ticket as an orchestration loop. Let the agent harness decide the exact subagent strategy, but preserve this sequence of work. When starting or summarizing execution, explicitly carry the status table, implementation, self-review/review, QA, UI/UX or skip, findings aggregation, scoped fixes, verification reruns, and integration phases. Scoped fixes and reruns are conditional when no findings exist yet, but they still need to be named as part of the loop. Do not collapse them into a generic integration step.

When returning an execution action list, make the status table its own first action and include an explicit repeat-until-clean action for the verifier/fix loop.

1. Initialize a compact work-unit status table with columns: `work unit`, `implementation`, `self-review/review`, `QA`, `UI/UX or skip reason`, `findings/fixes`, and `integration`.
2. Delegate implementation for the approved work units. Implementation results must report changed surfaces, checks run, risks, and handoff notes.
3. Delegate self-review or review against the ticket description, acceptance criteria, approved implementation plan, implementation evidence, and diff.
4. Collect any self-review/review findings in the status table.
5. Delegate QA verification against acceptance-criteria behavior in the running app, service, API, job, or integration.
6. Collect any QA findings in the status table. If the verifier lacks required tooling or access, it must immediately report `CANNOT_VERIFY` with the reason and missing capability. Record that result, then perform the needed verification in the main session when the main session has the required tooling; otherwise report the blocker.
7. For UI-facing or mixed work, delegate UI/UX verification. For backend-only/non-UI work, record the skip reason.
8. Collect any UI/UX findings in the status table. If the verifier lacks required tooling such as browser access, it must immediately report `CANNOT_VERIFY` with the reason and missing capability. Record that result, then perform the needed verification in the main session when the main session has the required tooling; otherwise report the blocker.
9. Aggregate all verifier findings from self-review/review, QA, and UI/UX. Decide which findings are blockers, which are out of scope, and which need scoped fixes. Brief the user when a finding changes scope, plan, timeline, or acceptance criteria.
10. Delegate scoped fixes for fixable findings. Each fix request should include the original ticket context, approved plan, finding evidence, affected surfaces, and the verification rows that must be rerun.
11. Rerun the affected verification loops after fixes. If a fix touches broader behavior or UI surfaces, rerun every verifier that could be affected, not only the verifier that reported the finding.
12. Reconcile integration status for the work units and repeat until no verifier reports findings, or until the remaining findings are explicitly blocked or out of scope.

Do not mark a work unit clean because local tests passed. It is clean only when the applicable implementation, review, QA, UI/UX or backend-only skip, findings, and integration rows are resolved.

## Step 5 - Ship Or Handoff

When the work is ready for PR, tracker, release, or merge action, delegate a self-contained shipping request instead of performing state changes inline. Include the current PR or branch, current tracker and PR state, intended shipping action, completed status table, verifier summary, and explicit merge-approval state.

When returning action lists, use a capability phrase like `ticket-linked PR shipping handoff` and explicitly copy any known current tracker state, intended tracker state, and whether merge approval is present or missing. Put known state values in the request itself, for example `current tracker state is In Review; intended tracker state is Done`. Do not leave known state values for the shipping handoff to rediscover.

Relay the shipping result to the user. If shipping cannot proceed, report the blocker without partially changing PR, branch, tracker, release, or merge state.

## Final Report

End with a concise report:

- ticket and approved plan summary
- what was implemented
- what worked, what did not, and unresolved blockers
- implementation reports, self-review/review results, QA results, UI/UX results, and skipped rows with reasons
- plan-match or deviation findings from self-review/review, plus follow-up verification
- tests/checks/run evidence and remote check state
- PR/ticket/release state and recommended next step

## Red Flags

Stop and recover when:

- ticket, repo, branch, PR, or requirement facts are stale or unavailable but would affect the decision
- requirements/design approval or implementation-plan approval is skipped
- subagent work is silently replaced by inline implementation, QA, UI/UX verification, or release mutation
- a work unit is called clean while required review, QA, UI/UX, finding, or integration rows are missing
- merge or ticket completion is attempted without required checks and explicit user approval
