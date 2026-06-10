---
name: ticket-start
description: Use when the user asks to start, work on, build, or implement one standalone Jira or Linear ticket, not an Epic, parent-with-children scope, or ticket set. Also use for progress/status on a ticket already being handled by this workflow. Covers job and personal-project tickets through MCP or REST API fallback. Do not use for multi-ticket workflow intake, code review, planning-only, QA-only, PR verification, PR summary, debugging-only, or ticket lookup tasks.
---

# Ticket Start

## Purpose

Use this skill as the main-agent workflow for working one implementation ticket from intake to final report. The main agent stays the user-facing orchestrator: it gathers ticket facts, brainstorms requirements/design with the user, gets approval, routes execution and verification work, reconciles returned reports, and keeps the user informed.

Prefer delegated work for implementation, independent review, QA verification, UI/UX verification, focused fixes, and PR verification. If required delegated capability is unavailable, tell the user before replacing it with inline work.

A personal project is a project that uses GitHub for code versioning and Linear for ticket tracking.
A job project is a project that uses Bitbucket for code versioning and Jira for ticket tracking.

For UI-facing or mixed tickets, UI/UX verification depends on project type:

- Personal projects / Linear tickets: verify the production app matches the runnable reference app for the changed user-visible surfaces and every visually meaningful changed state.
- Job projects / Jira tickets: verify visual consistency with the rest of the application and similar existing elements, especially sizing, spacing, component usage, typography, state styling, and interaction patterns.

## When To Use

- The user asks to start, work on, build, or implement one standalone ticket.
- The user gives one standalone Jira ticket or Linear issue ID as part of an implementation-work request.
- The user asks for progress or status on a ticket already being handled here.

Do not use for Epics, parent tickets with children requested as one scope, multi-ticket workflow intake, pure planning, debugging-only tasks, standalone code review, or refactors with no ticket.

## Core Rules

- Memory and prior chat are hints, not source of truth. Re-read the ticket, repo, branch, PR, and relevant docs before making substantive decisions.
- Use the ticket-system MCP first. If MCP is unavailable, use the ticket system's REST API.
- Start work in a fresh worktree based on fetched `origin/main`. Fetch first; do not base ticket work on local `main`, the current branch, or a stale ref.
- Keep the main session focused on orchestration and user decisions. Do not quietly turn it into the implementer, QA verifier, UI/UX verifier, or PR/ticket mutator.
- Keep delegated requests self-contained: ticket facts, acceptance criteria, approved decisions, relevant repo instructions, scope locators, constraints, expected checks, and output expectations.
- Treat subagent reports as compact evidence, not transcripts. Carry forward locators and summaries so later agents can read surgically.

## Step 1 - Gather Facts

1. Identify the ticket source and workflow type: job/Jira ticket or personal/Linear ticket.
2. Read the current ticket from the ticket-system MCP, or from the ticket system's REST API when MCP is unavailable. Capture title, description, acceptance criteria, links, status, dependencies, and ambiguity.
3. If the ticket is a child issue, subtask, story under an Epic, or otherwise linked into a parent hierarchy, read the parent tickets or Epic descriptions too. Carry forward the parent problem statement, goals, constraints, and acceptance context that explain why the child ticket exists.
4. Read nearby repo instructions and workflow references. For personal projects, check `PRD.md` when the ticket or unit of work adds or changes business rules. Check `designs/` or reference apps only when the ticket adds or modifies UI components that have a corresponding reference surface or component. Read only the relevant slices.
5. Inspect current git state, branches, existing PRs, and recent commits relevant to the ticket.
6. Create or verify the ticket worktree from freshly fetched `origin/main`; halt if freshness cannot be established.
7. Delegate codebase scoping before planning for implementation tickets. If the scope is clearly trivial, record the skip reason before doing local scoping. Include the ticket title, description, acceptance criteria, dependencies, repo instructions, and known constraints in the scoping request.

## Step 2 - Align Requirements And Design

Open with a short briefing grounded in the ticket and current repo: what is known, what is ambiguous, likely affected surfaces, relevant designs or product docs, and any conflicts.

Run a user-facing brainstorming session until the agent and user share a concrete understanding of the work, boundaries, and success criteria. Keep the discussion grounded in the ticket, parent context, approved artifacts, PRD/design slices, and current codebase facts.

When the user confirms the shared requirements/design understanding, trigger implementation-plan writing from that confirmed ticket context.

## Step 3 - Approve The Implementation Plan

Get user approval for the implementation plan before coding starts. The plan must be concrete enough to route implementation and verification work.

Do not implement, scaffold, or mutate product code before plan approval.

## Step 4 - Route Execution And Verification

After plan approval, implementation begins by delegating work to implementer subagents in the most optimal way to minimize dependencies and maximize throughput and quality of work.

Respect this ticket sequence:

1. Delegate implementation for the approved plan.
2. Delegate independent review against the ticket, acceptance criteria, approved plan, implementation evidence, and diff.
3. Delegate QA verification against acceptance-criteria behavior in the running app, service, API, job, script, or integration.
4. For UI-facing or mixed work, delegate UI/UX verification. For backend-only/non-UI work, record the skip reason.
5. Aggregate findings from independent review, QA, and UI/UX verification.
6. Delegate scoped fixes for fixable findings.
7. Rerun the affected verification after fixes.
8. Repeat the finding, fix, and rerun loop until all required reports are clean, explicitly blocked, or explicitly out of scope.
9. Close execution with a gate note that states whether PR verification is allowed, blocked, or still waiting, and why.

When routing verifier work, include this fallback instruction: if a verifier lacks required tooling or access, it must immediately report `CANNOT_VERIFY` with the reason and missing capability. Record that result, then perform the needed verification in the main session when the main session has the required tooling; otherwise report the blocker.

Include the `CANNOT_VERIFY` fallback in delegated QA and UI/UX verification requests so verifier agents fail fast instead of inventing evidence.

Track returned reports compactly enough to know what is implemented, reviewed, verified, fixed, rerun, clean, blocked, or explicitly out of scope. Do not route the ticket to PR verification until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved or explicitly blocked/out of scope.

Execution routing is incomplete unless it states that PR verification waits for those resolved, blocked, or out-of-scope reports and is not allowed while any required report is missing.

## Step 5 - PR Verification Or Handoff

When implementation, review, QA, UI/UX or skip, scoped fixes, and reruns are resolved, delegate a self-contained PR verification request. Include the ticket, PR or branch, current known tracker/PR state, intended action, execution and verification summary, and merge-approval status.

Relay the readiness result to the user. Do not perform PR, branch, tracker, or merge mutations inline.

## Final Report

End with a concise report:

- ticket and approved plan summary
- what was implemented
- what worked, what did not, and unresolved blockers
- implementation reports, self-review/review results, QA results, UI/UX results, and skipped rows with reasons
- plan-match or deviation findings from self-review/review, plus follow-up verification
- tests/checks/run evidence and remote check state
- PR/ticket state and recommended next step

## Red Flags

Stop and recover when:

- ticket, repo, branch, PR, or requirement facts are stale or unavailable but would affect the decision
- confirmed requirements/design understanding or implementation-plan approval is skipped
- subagent work is silently replaced by inline implementation, QA, UI/UX verification, or PR/ticket mutation
- PR verification is requested while required implementation, review, QA, UI/UX, finding, fix, or rerun reports are missing
- merge or ticket completion is attempted without required checks and explicit user approval
