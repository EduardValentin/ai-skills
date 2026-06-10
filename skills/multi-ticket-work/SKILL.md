---
name: multi-ticket-work
description: Use when the user asks to work a set of Jira or Linear tickets, an Epic, or a parent ticket with children as one multi-ticket scope. Do not use for one standalone ticket.
---

# Multi-Ticket Work

## Purpose

Use this skill when the requested unit of work is a full multi-ticket scope: several Jira or Linear tickets, an Epic with multiple tickets, or a parent ticket with child tickets or sub-tickets.

The main agent is the portfolio orchestrator. It identifies the complete ticket scope, chooses the execution order, decides what can run in parallel, dispatches one ticket orchestrator per ticket or unit, coordinates blockers, collects completion reports, and gives the human a final PR review order. The main agent does not implement ticket work inline.

## Workflow

1. Gather the full scope.
   - Read every ticket the user named.
   - If the user names an Epic, parent ticket, or ticket with child tickets/sub-tickets, read the parent context and every child ticket that belongs to the requested scope.
   - Confirm which tickets are in scope when the ticket system, branch state, or user request is ambiguous.

2. Build the execution map.
   - List each ticket or unit of work.
   - Identify dependencies, shared files, integration risks, and order constraints.
   - Decide which tickets can be worked in parallel and which must happen consecutively.
   - Keep one subagent per ticket by default. Split into units of work only when one ticket is too large or has separable sequencing constraints.

3. Keep durable orchestration notes.
   - Save an uncommitted orchestration note in the repo's scratch or ignored work area. Use an existing ignored scratch path when available; otherwise create a clearly named untracked note outside source docs, report its path, and do not add it to commits unless the user explicitly asks.
   - Include ticket inventory, parent context, dependency map, dispatch assignments, status, PR links, blockers, decisions, and next actions.
   - Update it after scope gathering, execution mapping, every dispatch, every subagent report, every blocker, and every PR.
   - Re-read it at the start of work, after any context compaction or resume, before dispatching dependent work, and before the final report.
   - When returning workflow actions, make note creation/update and the required re-read checkpoints explicit instead of hiding them inside generic status tracking.

4. Dispatch ticket orchestrators.
   - Dispatch one ticket orchestrator per ticket or unit of work.
   - The first-level subagent prompt must call the agent a ticket orchestrator, not an implementation worker.
   - Each ticket-orchestrator request must be self-contained. Include ticket context, relevant parent/Epic context, dependency constraints, repository instructions, PR expectations, reviewer-friendly PR body expectation, and the required completion report.
   - A ticket orchestrator owns coordination of the one-ticket workflow for its ticket or unit. It dispatches internal subagents or delegated requests for scoping, implementation, independent review, QA, UI/UX checks when applicable, scoped fixes, reruns, PR creation, and PR verification or handoff.
   - The ticket orchestrator coordinates those internal agents and aggregates their reports; it does not implement or verify the ticket directly.
   - Do not assign implementation, review, QA, UI/UX checks, PR creation, and completion reporting to one worker prompt.
   - State plainly in each dispatch that the ticket orchestrator must open a PR and return the required phase reports before the ticket or unit is complete.
   - A ticket or unit is not complete until its ticket orchestrator has opened a PR and returned the required implementation, review, QA, UI/UX-or-skip, fixes/reruns, risk, and dependency evidence.
   - The main agent tracks status and blockers, but does not take over implementation inline.

5. Coordinate sequencing.
   - Start independent tickets in parallel when safe.
   - Hold dependent tickets until their upstream context is available.
   - When a subagent reports a blocker, decide whether to wait, resequence, split the work differently, or ask the human for a decision.
   - Keep dependency notes current so later subagents receive the correct upstream PR, branch, or implementation context.

6. Finish with a review-ready report.
   - Re-read the durable orchestration note before reporting, then reconcile ticket status, PR links, blockers, and dependency order.
   - Return the list of opened PRs.
   - Put the PRs in the order the human should review them.
   - Explain the review order using dependencies or integration risk.
   - Call out any ticket that did not produce a PR, did not produce a report, or remains blocked.

## Subagent Completion Report

Each ticket orchestrator must report back with:

- ticket or unit worked
- PR link
- summary of what changed
- implementation report
- independent review report
- QA report
- UI/UX report, or not-applicable/cannot-verify reason
- scoped fixes and reruns after verifier findings
- important decisions or deviations
- tests or checks performed
- known risks, blockers, or follow-up needed
- downstream dependency notes for later tickets

## PR Description Requirement

In each dispatch, ask for a reviewer-friendly PR body with summary, manual testing, and review focus. Phrase it as a PR-description or reviewer-summary request so the appropriate PR-summary capability can handle the wording.

## Failure Signals

- The main agent starts implementing a ticket itself.
- The first-level subagent is framed as an implementation worker instead of a ticket orchestrator.
- A ticket orchestrator implements, reviews, QA-checks, or UI-checks directly instead of delegating those phases.
- A first-level prompt assigns implementation, review, QA, UI/UX checks, PR creation, and completion reporting to one worker.
- Parent-side review is treated as a replacement for independent per-ticket review.
- Completion is summarized as a generic report instead of the required phase evidence.
- A combined worker report is accepted instead of distinct implementation, review, QA, and UI/UX-or-skip evidence.
- The ticket set, Epic children, or sub-tickets were not fully gathered.
- Work begins before dependencies and parallelization are mapped.
- The durable orchestration note is missing, stale, or not re-read after compaction or resume.
- A ticket is marked complete without both a PR and subagent report.
- The final report lacks PR links, review order, or dependency rationale.
- A PR body does not give the human enough review focus.
