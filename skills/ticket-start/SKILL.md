---
name: ticket-start
description: Use when the user wants to start implementation work from one ticket - phrases like "start ticket", a Jira ticket, or a Linear issue ID. Also use for status/progress questions about a ticket already in this workflow. Covers job tickets and personal-project tickets through the ticket-system MCP or REST API fallback. Do not use for multi-ticket workflow intake, code review, planning-only, or debugging-only tasks.
---

# Ticket Start

## Purpose

Use this skill as the main-agent workflow for working one implementation ticket from intake to final report. It defines ticket-specific source-of-truth, approval, routing, and reporting gates. It does not define the detailed method for brainstorming, plan writing, implementation, review, QA, UI verification, or PR readiness.

The main agent stays the user-facing orchestrator: it gathers ticket facts, aligns requirements/design with the user, gets approval, routes execution and verification work to appropriate capabilities, reconciles returned reports, and keeps the user informed.

Prefer delegated work for implementation, independent review, QA verification, UI/UX verification, focused fixes, and release checks. If required delegated capability is unavailable, tell the user before replacing it with inline work.

A personal project is a project that uses GitHub for code versioning and Linear for ticket tracking.
A job project is a project that uses Bitbucket for code versioning and Jira for ticket tracking.

For UI-facing or mixed tickets, UI/UX verification depends on project type:

- Personal projects / Linear tickets: verify the production app matches the runnable reference app for the changed user-visible surfaces and every visually meaningful changed state.
- Job projects / Jira tickets: verify visual consistency with the rest of the application and similar existing elements, especially sizing, spacing, component usage, typography, state styling, and interaction patterns.

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
- For personal workflows, use the repository's required GitHub write identity before commits, pushes, PR updates, comments, labels, transitions, or merges. Read `bot-identity.md` when setup or activation details are needed. Do not rely on ambient personal credentials for writes.

## Step 1 - Gather Facts

1. Identify the ticket source and workflow type: job/Jira ticket or personal/Linear ticket.
2. Read the current ticket from the ticket-system MCP, or from the ticket system's REST API when MCP is unavailable. Capture title, description, acceptance criteria, links, status, dependencies, and ambiguity.
3. If the ticket is a child issue, subtask, story under an Epic, or otherwise linked into a parent hierarchy, read the parent tickets or Epic descriptions too. Carry forward the parent problem statement, goals, constraints, and acceptance context that explain why the child ticket exists.
4. Read nearby repo instructions and workflow references. For personal projects, check `PRD.md` when the ticket or unit of work adds or changes business rules. Check `designs/` or reference apps only when the ticket adds or modifies UI components that have a corresponding reference surface or component. Read only the relevant slices.
5. Inspect current git state, branches, existing PRs, and recent commits relevant to the ticket.
6. Create or verify the ticket worktree from freshly fetched `origin/main`; halt if freshness cannot be established.
7. Map the relevant code surface before planning. Prefer delegated codebase scoping when the affected surface is non-trivial, unfamiliar, shared, or UI/reference-backed. Include the ticket title, description, acceptance criteria, dependencies, repo instructions, and known constraints in the scoping request.

## Step 2 - Align Requirements And Design

Open with a short briefing grounded in the ticket and current repo: what is known, what is ambiguous, likely affected surfaces, relevant designs or product docs, and any conflicts.

Run a user-facing alignment phase until the agent and user share a concrete understanding of the work, boundaries, and success criteria. Keep the discussion grounded in the ticket, parent context, approved artifacts, PRD/design slices, and current codebase facts.

Ask for explicit approval of the requirements/design direction. This approval is separate from implementation-plan approval.

## Step 3 - Approve The Implementation Plan

Produce an implementation plan from the approved requirements/design direction and ask the user to approve it before coding starts. The plan must be concrete enough to route implementation and verification work, but ticket-start does not prescribe the plan format or task mechanics.

Do not implement, scaffold, or mutate product code before plan approval.

## Step 4 - Route Execution And Verification

After plan approval, route the ticket work through delegated capabilities. Let the agent harness and active methodology skills decide the exact subagent strategy, task granularity, review mechanics, and execution sequence.

Route these work categories when applicable:

- implementation for the approved plan
- independent review against the ticket, acceptance criteria, approved plan, implementation evidence, and diff
- QA verification against acceptance-criteria behavior in the running app, service, API, job, script, or integration
- UI/UX verification for UI-facing or mixed work; for backend-only/non-UI work, record the skip reason
- scoped fixes for verifier findings
- reruns of affected verification after fixes

If a verifier lacks required tooling or access, it must immediately report `CANNOT_VERIFY` with the reason and missing capability. Record that result, then perform the needed verification in the main session when the main session has the required tooling; otherwise report the blocker.

Include the `CANNOT_VERIFY` fallback in delegated QA and UI/UX verification requests so verifier agents fail fast instead of inventing evidence.

Track returned reports compactly enough to know what is implemented, reviewed, verified, fixed, rerun, clean, blocked, or explicitly out of scope. Do not route the ticket to PR readiness until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved or explicitly blocked/out of scope.

## Step 5 - PR Readiness Or Handoff

When the work is ready for PR, tracker, release, or merge action, delegate a self-contained PR readiness request instead of performing state changes inline. Include the current PR or branch, current tracker and PR state, intended PR or tracker action, execution and verification summary, and explicit merge-approval state.

When returning action lists, use a capability phrase like `ticket-linked PR readiness check` and explicitly copy any known current tracker state, intended tracker state, and whether merge approval is present or missing. Put known state values in the request itself, for example `current tracker state is In Review; intended tracker state is Done`. Do not leave known state values for the readiness handoff to rediscover.

Relay the readiness result to the user. If readiness cannot be confirmed, report the blocker without partially changing PR, branch, tracker, release, or merge state.

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
