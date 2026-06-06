---
name: ticket-start
description: Use when the user wants to start implementation work from a ticket — phrases like "start ticket", a pasted Jira ticket, or a Linear issue ID. Also use for large workflows spanning multiple tickets or substantial implementation work that needs delegated orchestration, or follow-up status/progress questions about a ticket already in this workflow. Covers both job tickets (Jira/pasted; uses acli when available) and personal-project tickets (Linear, optionally with PRD.md and a designs/ React reference app). Do not use for code review, planning-only, or debugging-only tasks.
---

# Ticket Start

## Overview

`ticket-start` is the thin intake and routing orchestrator for implementation work driven by a ticket. It owns user dialogue, source-of-truth freshness, requirements/design approval, implementation-plan approval, routing to execution orchestration, and routing to Ship.

Phase order is a hard gate:

**Setup -> Requirements/Design -> Plan -> Execute -> Ship**

Implementation, review, testing, QA, UI/UX verification, focused fixes, readiness ledger tracking, and Ship mutations are delegated to dedicated skills. The main session coordinates returned reports and user decisions; it does not implement, review, test, verify, or mutate release state inline.

**Scoping dispatch wording:** `ticket-start` dispatches the Scoping subagent and consumes its returned map. The Scoping prompt must be a self-contained codebase mapping request: implementation/ticket codebase mapping, token-efficient navigable scope map, file:line locators, entry points, target modules/components, domain logic, shared utilities, analogous implementations, project patterns, types/contracts, tests, imports/dependencies, prototype/reference elements when applicable, affected surfaces, conflict points, and suggested downstream slices.

**Implementation dispatch wording:** `ticket-start` invokes `ticket-work-unit-orchestration` after plan approval. That skill chooses the implementation delegation strategy and may use `ticket-implementation-unit`.

**UI/UX dispatch wording:** UI/UX verification remains delegated through execution orchestration, preferably to `frontend-ui-review` for UI-facing or mixed work. Visual verification checks the rendered user-visible outcome and every visually meaningful state, not hidden templates or implementation proxies.

**GitHub write identity guard (personal workflow):** every GitHub write action must use the dedicated bot identity from `bot-identity.md`. This includes commits, branch pushes, PR creation, PR updates, PR comments, PR review comments, review-thread replies, labels, issue comments, merges, and any `gh api` mutation. Ambient `gh` authentication is not proof of the correct actor and must not be used for writes.

**Context-economy contract:** every subagent report is a navigable index, not a transcript. Downstream readers consume the surgical slices upstream locators point at; never reload full files when a Scoping locator suffices.

**Subagent authorization contract:** a user who invokes `ticket-start` has authorized the mandatory dispatches still owned here: Scoping, `ticket-work-unit-orchestration`, and `ticket-ship-gate`. If the host cannot dispatch required subagents or skills, halt and surface that blocker.

## When to use

- The user asks to start, work on, build, or implement a ticket.
- The user pastes a Jira/job ticket and asks for implementation.
- The user gives a Linear ticket identifier in a personal project.
- The user asks about a ticket already in this workflow.
- The work is a large workflow spanning multiple tickets or substantial implementation areas that needs delegated orchestration.

Do not use for code review, pure planning, debugging-only tasks, or refactors with no ticket.

## Workflow selection

- **Job workflow** — Jira ticket or pasted by the user. Load `job-workflow.md`.
- **Personal workflow** — Linear ticket. Load `personal-workflow.md`. `PRD.md` and a `designs/` React reference app are optional; see that file's `## Partial Setups` for what changes when either is absent.

If ambiguous, ask the user before loading anything else.

## Setup

1. **Worktree.** Start feature work in an isolated worktree based on the latest `origin/main`. Hard rule: fetch `origin main` first, then create or verify the worktree from fetched `origin/main`, never from local `main`, the current branch, or a stale remote-tracking ref. Halt on fetch failure.

2. **Bot identity (personal workflow only).** Run the two activation checks in `bot-identity.md` -> `## Setup activation`: mint and verify a fresh GitHub installation token, then apply the bot's git name/email as per-worktree git config. Fail closed; never fall back to personal GitHub credentials. Job workflow skips this step.

3. **Freshness.** Memory and prior chat are hints, not facts. Before substantive answers about scope, status, blockers, related tickets, progress, or git state, re-read the source of truth:
   - Linear tickets through Linear MCP, including related tickets when relevant.
   - Job/Jira tickets through `acli jira workitem view <KEY> --json` when available, otherwise the user paste.
   - Repo branch, working tree, diffs, recent commits, PR metadata, docs, and code from disk.
   - If a source is unavailable, say what could not be verified.

4. **Workflow-specific reading.** Read the selected workflow file and gather only the relevant facts it points at.

5. **Dispatch Scoping subagent.** Forward ticket title/description/AC, relevant repo instructions, workflow facts, and scoped PRD/design slices when applicable. The returned scope map is the definitive relevant code surface for downstream routing.

6. **Clarify if needed.** If acceptance criteria are missing/vague/not testable, or Scoping surfaces a conflict, brief the user with Scoping evidence and ask before continuing.

## Requirements/Design

1. Open with a Scoping-grounded briefing: entry points, target modules, prototype/reference elements if any, affected surfaces, and conflicts.

2. Explore project context, user intent, requirements, constraints, design, alternatives, edge cases, failure modes, accessibility, and non-goals before implementation.

3. Surface at least one credible alternative when meaningful, and record the chosen direction plus dismissed alternatives in the requirements/design artifact.

4. Ask the user to approve the requirements/design direction explicitly. Approval here is not implementation-plan approval.

5. Write the approved requirements/design artifact in the workflow's planning location. Keep agent-local planning artifacts out of product commits unless the repo explicitly asks to version them.

## Plan

1. Produce a written implementation plan from the approved requirements/design artifact before touching code.

2. Keep UI-visible tasks traceable to Scoping's affected surface map and reference/prototype rows when present.

3. If the plan spans multiple tickets or substantial implementation areas, describe the intended delegation shape at a high level. For workflows spanning multiple tickets, each ticket implementation should be delegated to a different implementation agent where practical, while review, testing, and verification remain delegated to subagents. The exact strategy belongs to `ticket-work-unit-orchestration`.

4. Wait for explicit user approval of the implementation plan before execution. No code or scaffolding happens between requirements/design approval and plan approval.

## Execution routing

Invoke `ticket-work-unit-orchestration` after the implementation plan is approved.

Forward a compact execution packet:

- ticket source, ticket IDs, and acceptance criteria
- approved requirements/design artifact
- approved implementation plan
- Scoping map with affected surfaces, entry points, tests, and constraints
- workflow type and branch/worktree state
- relevant repo instructions and non-goals
- UI/prototype/reference context when applicable
- expected handoff shape: per-work-unit readiness ledger for implementation report, implementer self-review report, QA verification report, UI/UX verification report or explicit backend-only/non-UI skip rationale, unresolved findings status, and integration/out-of-scope status

Do not dispatch implementation, QA, UI/UX, review, testing, or fix-loop work directly from `ticket-start`. `ticket-work-unit-orchestration` owns those details and returns the per-work-unit readiness ledger before Ship.

## Ship routing

Use `ticket-ship-gate` for Ship. Do not perform Ship mutations inline.

Forward a compact Ship packet:

- approved requirements/design artifact and approved implementation plan
- per-work-unit readiness ledger from `ticket-work-unit-orchestration`
- PR/ticket context, workflow type, branch, and repository
- bot identity guard context for personal workflow
- required checks gate expectations
- explicit user merge approval status
- current PR draft/ready state
- intended Ship action

`ticket-ship-gate` owns readiness preflight, PR creation/update, Remote checks gate, ticket transitions, merge approval, merge, and closeout mutation report.

## Briefing rule

When a routed skill or subagent returns a finding, blocker, or decision point that needs user input, brief the user with the same relevant context before asking. Include severity, locator or ticket reference, one-line description, and the material choice or blocker.

## Closeout report

When done, report:

- what changed
- what was validated and how, including delegated QA/UIUX status or backend-only skip
- readiness ledger status from `ticket-work-unit-orchestration`
- Ship gate status from `ticket-ship-gate`
- rules proposed or promoted in this session, if any
- remaining risks, assumptions, blockers, or manual follow-up

## Red flags

Stop and recover if any of these happen:

- worktree was not based on freshly fetched `origin/main`
- source-of-truth ticket, repo, or PR state is stale or unavailable but treated as fact
- requirements/design or implementation-plan approval is skipped or collapsed
- implementation, review, testing, QA, UI/UX, fixes, or Ship mutations are done inline by `ticket-start`
- visual verification is accepted without the rendered user-visible outcome and every visually meaningful state
- personal-workflow GitHub writes would use ambient credentials
- Ship starts without a complete per-work-unit readiness ledger
