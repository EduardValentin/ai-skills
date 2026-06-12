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
- Treat "start working", "coding part only", "code it", branch instructions, branch clarification, and investigation permission as permission to begin this workflow, not permission to code.
- In every pre-approval response or workflow summary, explicitly state that branch choice, worktree setup, draft diff knowledge, investigation progress, internal status plans, checklists, update plans, and working notes are not approval of the spec/design or implementation plan.
- Before spec and plan approval, limit code-adjacent work to fact gathering, freshness/setup, and delegated scoping. Do not validate draft changes, run implementation tests, recommend repairs, edit product/test files, or treat an existing draft worktree as approval.
- Keep the main session focused on orchestration and user decisions. Do not quietly turn it into the implementer, QA verifier, UI/UX verifier, or PR/ticket mutator.
- The user's ticket-start request is sufficient authorization for mandatory delegated codebase scoping. Do not wait for a separate explicit user ask, and do not treat main-session local scoping as a substitute.
- Branch choice, investigation progress, internal checklists, status plans, working notes, and update plans never replace explicit user approval of the written spec/design and implementation plan.
- Keep delegated requests self-contained: ticket facts, acceptance criteria, approved decisions, relevant repo instructions, scope locators, constraints, expected checks, PR expectations, and output expectations.
- Treat subagent reports as compact evidence, not transcripts. Carry forward locators and summaries so later agents can read surgically.

## Step 1 - Gather Facts

1. Identify the ticket source and workflow type: job/Jira ticket or personal/Linear ticket.
2. Read the current ticket from the ticket-system MCP, or from the ticket system's REST API when MCP is unavailable. Capture title, description, acceptance criteria, links, status, dependencies, and ambiguity.
3. If the ticket is a child issue, subtask, story under an Epic, or otherwise linked into a parent hierarchy, read the parent tickets or Epic descriptions too. Carry forward the parent problem statement, goals, constraints, and acceptance context that explain why the child ticket exists.
4. Read nearby repo instructions and workflow references. For personal projects, check `PRD.md` when the ticket or unit of work adds or changes business rules. Check `designs/` or reference apps only when the ticket adds or modifies UI components that have a corresponding reference surface or component. Read only the relevant slices.
5. Inspect current git state, branches, existing PRs, and recent commits relevant to the ticket.
6. Create or verify the ticket worktree from freshly fetched `origin/main`; halt if freshness cannot be established.
7. After ticket, parent, artifact, and repo intake, the immediate next workflow step is delegated codebase scoping, before brainstorming or planning. The next-step response must state:
   - the ticket-start request itself authorizes the scoping dispatch; no separate user ask is needed
   - local scoping does not satisfy or replace the delegated scoping report
   - brainstorming will ask only about unknowns the returned codebase sweep could not resolve
   - the sweep must ambitiously cover affected files/surfaces, schemas, secret conventions, event models, configs, tests, prior implementation history, risks, and verification surfaces
   Include the ticket title, description, acceptance criteria, dependencies, repo instructions, and known constraints in the scoping request.

## Step 2 - Align Requirements And Design

Open with a short briefing grounded in the ticket, delegated scoping report, and current repo: what is known, what code evidence resolved, what remains ambiguous, likely affected surfaces, relevant designs or product docs, and any conflicts. In that briefing, explicitly state that brainstorming questions are based on returned scoping evidence and limited to unknowns the codebase sweep could not resolve.

Run a user-facing brainstorming session until the agent and user share a concrete understanding of the work, boundaries, and success criteria. This is mandatory and non-negotiable. Keep the discussion grounded in the ticket, parent context, approved artifacts, PRD/design slices, and current codebase facts.

Maintain and show a complete open-questions ledger before writing the spec/design. Use explicit headings for `Blocking decisions`, `Risky assumptions`, and `Non-blocking assumptions`. Do not surface only the loudest blocker while silently carrying other unknowns into the spec or plan. After the user answers one question, update the ledger, rescan for remaining unknowns, and show the remaining questions before proceeding.

A single question, generic "any concerns?", or brief summary is not enough. When material unknowns exist, ask the concrete follow-up questions in the user-facing response. Continue until every material unknown that could affect scope, data contracts, integration behavior, fallback behavior, schedules, acceptance criteria, or verification is resolved or explicitly approved as an assumption. Do not write the spec/design until the user confirms the shared understanding and the remaining assumptions.

After brainstorming, write a concise spec/design covering scope, non-goals, decisions, acceptance criteria, risks, and open questions. Ask the user to approve it. Do not route plan writing before that approval. Every brainstorming handoff must state that plan writing waits for spec/design approval, and execution, draft validation, product edits, and test edits wait for both spec/design approval and implementation-plan approval.

## Step 3 - Create And Approve The Spec And Plan

1. After the spec/design is approved, route implementation-plan writing from the approved spec and ticket context.
2. Present the implementation plan to the user and get explicit approval before coding starts. The plan must be concrete enough to route implementation and verification work.

Branch choice, investigation progress, internal status plans, checklists, and working notes do not count as approval.
Spec approval and implementation-plan approval are mandatory, non-negotiable gates. Do not implement, scaffold, mutate product code, edit tests, validate draft work, recommend implementation repairs, or route execution before both approvals.

## Step 4 - Execute The Approved Packet

After the user approves the spec and implementation plan, enter the execution phase using the approved execution packet and the execution-phase contract. Restate the packet details in the phase contract; do not merely refer to "the approved packet." Before modifying product or test code, select and apply the execution capability from that packet; if it is unavailable, stop and report the blocker. Remain the main orchestrator in the current session. Coordinate implementation, independent review, QA, UI/UX verification when applicable, scoped fixes, reruns, PR preparation, and final reporting through delegated work as needed. Do not hand off main-ticket orchestration to another agent.

The approved execution packet must include the ticket facts, parent context, acceptance criteria, approved spec/design, approved implementation plan, relevant artifact slices, scope locators, branch/worktree state, constraints, expected checks, PR expectations, and completion-report requirements.

Respect this execution order:

1. Validate the approved execution packet.
2. Coordinate implementation for the approved plan.
3. Coordinate independent review against the ticket, acceptance criteria, approved plan, implementation evidence, and diff.
4. Coordinate QA verification against acceptance-criteria behavior in the running app, service, API, job, script, or integration.
5. For UI-facing or mixed work, coordinate UI/UX verification. For backend-only/non-UI work, record the skip reason.
6. Aggregate findings from independent review, QA, and UI/UX verification.
7. Coordinate scoped fixes for fixable findings.
8. Rerun the affected verification after fixes.
9. Repeat the finding, fix, and rerun loop until all required reports are clean, explicitly blocked, or explicitly out of scope.
10. Close execution with a gate note that states whether PR verification is allowed, blocked, or still waiting, and why.

When routing verifier work, include this fallback instruction: if a verifier lacks required tooling or access, it must immediately report `CANNOT_VERIFY` with the reason and missing capability. Record that result, then perform the needed verification in the main session when the main session has the required tooling; otherwise report the blocker.

Include the `CANNOT_VERIFY` fallback in delegated QA and UI/UX verification requests so verifier agents fail fast instead of inventing evidence.

Track returned reports compactly enough to know what is implemented, reviewed, verified, fixed, rerun, clean, blocked, or explicitly out of scope. Do not route the ticket to PR verification until implementation, independent review, QA, UI/UX or skip, scoped fixes, and necessary reruns are resolved or explicitly blocked/out of scope.

Execution routing is incomplete unless it states that PR verification waits for those resolved, blocked, or out-of-scope reports and is not allowed while any required report is missing.

## Step 5 - PR Creation, Verification, And Handoff

When implementation, review, QA, UI/UX or skip, scoped fixes, and reruns are resolved, ensure a reviewable PR exists for the completed branch before the final ticket report. If no PR exists, coordinate reviewer-facing PR preparation and source-control PR creation through the appropriate project workflow and identity. If PR creation is blocked, report that concrete blocker instead of presenting the ticket as complete.

After the PR exists or is identified, delegate a self-contained PR readiness verification request. Include the ticket, PR or branch, current known tracker/PR state, intended action, execution and verification summary, stale or missing PR metadata, and merge-approval status. PR creation alone is not ticket-start completion.

Relay the readiness result to the user. Do not merge, mark ready, update tickets, dismiss comments, or perform other source-control/tracker mutations inline while readiness is blocked or merge approval is absent.

## Final Report

End with a concise report:

- ticket, approved spec, and approved plan summary
- what was implemented
- what worked, what did not, and unresolved blockers
- implementation reports, self-review/review results, QA results, UI/UX results, and skipped rows with reasons
- plan-match or deviation findings from self-review/review, plus follow-up verification
- tests/checks/run evidence and remote check state
- PR link or PR-creation blocker, PR readiness result, ticket state, and recommended next step

## Red Flags

Stop and recover when:

- ticket, repo, branch, PR, or requirement facts are stale or unavailable but would affect the decision
- spec approval or implementation-plan approval is skipped
- subagent work is silently replaced by inline implementation, QA, UI/UX verification, or PR/ticket mutation
- PR verification is requested while required implementation, review, QA, UI/UX, finding, fix, or rerun reports are missing
- the final ticket report is prepared while no reviewable PR exists and no concrete PR-creation blocker is recorded
- merge or ticket completion is attempted without required checks and explicit user approval
