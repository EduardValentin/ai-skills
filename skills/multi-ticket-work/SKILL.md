---
name: multi-ticket-work
description: Use when the user asks to work a set of Jira or Linear tickets, an Epic, or a parent ticket with children as one multi-ticket scope. Do not use for one standalone ticket.
---

# Multi-Ticket Work

## Purpose

Use this skill when the requested unit of work is a full multi-ticket scope: several Jira or Linear tickets, an Epic with multiple tickets, or a parent ticket with child tickets or sub-tickets.

The main agent is the multi-ticket coordinator. It identifies the complete ticket scope, aligns the cross-ticket plan with the user, gets approval, dispatches one `ticket-execution-coordinator` native agent per approved ticket or unit, coordinates blockers, collects completion reports, and gives the human a final PR review order. The main agent does not implement ticket work inline.

## Workflow

1. Gather the full scope.
   - Read every ticket the user named.
   - If the user names an Epic, parent ticket, or ticket with child tickets/sub-tickets, read the parent context and every child ticket that belongs to the requested scope.
   - Confirm which tickets are in scope when the ticket system, branch state, or user request is ambiguous.

2. Build the execution map.
   - List each ticket or unit of work.
   - Identify dependencies, shared files, integration risks, and order constraints.
   - Decide which tickets can be worked in parallel and which must happen consecutively.
   - Keep one `ticket-execution-coordinator` per ticket by default. Split into units of work only when one ticket is too large or has separable sequencing constraints.

3. Align and approve the work.
   - Run the user-facing cross-ticket requirements and brainstorming session needed to reach shared understanding for each ticket, including dependencies, boundaries, risks, and success criteria.
   - Do not dispatch before cross-ticket requirements gathering, user-facing brainstorming, spec creation, implementation planning, and user approval are all complete.
   - Name each in-scope ticket and material dependency in that session instead of summarizing only the Epic or parent ticket.
   - Produce or route the multi-ticket spec and implementation plan from that understanding.
   - Get user approval before dispatching execution.
   - Prepare one approved execution packet per ticket or unit. Each packet carries the ticket context, relevant parent/Epic context, approved spec/design, approved plan, dependency constraints, repository instructions, PR expectations, reviewer-friendly PR body expectation, and completion-report requirements.

4. Keep durable orchestration notes.
   - Save an uncommitted orchestration note in the repo's scratch or ignored work area. Use an existing ignored scratch path when available; otherwise create a clearly named untracked note outside source docs, report its path, and do not add it to commits unless the user explicitly asks.
   - Include ticket inventory, parent context, dependency map, approved spec/plan summary, approved execution packets, dispatch assignments, status, PR links, blockers, decisions, and next actions.
   - Update it after scope gathering, execution mapping, approval, every dispatch, every subagent report, every blocker, and every PR.
   - Re-read it at the start of work, after any context compaction or resume, before dispatching dependent work, and before the final report.
   - When returning workflow actions, make note creation/update and the required re-read checkpoints explicit instead of hiding them inside generic status tracking.

5. Dispatch ticket coordinators.
   - Dispatch one `ticket-execution-coordinator` native agent per approved ticket or unit of work.
   - Each dispatch must include the approved execution packet facts, dependency context, and completion-report requirements. Do not merely say that a packet exists.
   - Do not ask ticket coordinators to perform ticket intake, user-facing brainstorming, spec creation, plan creation, or approval gathering. State this exclusion plainly when rejecting a worker-collapse plan.
   - State plainly in each dispatch that the ticket coordinator coordinates execution for that ticket and must use `implementation-worker` plus deeper focused independent review, security review when applicable, QA, UI/UX, fix, and PR-preparation subagents when nested delegation is available. If nested delegation is unavailable, the ticket coordinator must report that limitation.
   - Do not phrase the handoff as if the ticket coordinator should personally implement, review, QA-check, UI-check, fix, prepare the PR, and report in one worker task.
   - A ticket or unit is not complete until its ticket coordinator has returned PR evidence plus distinct implementation, independent review, security-review-or-not-applicable, manual/runtime QA, UI/UX-or-not-applicable, scoped fixes/reruns, risk, dependency, and completion-report evidence.
   - The main agent tracks status and blockers, but does not take over implementation inline.

6. Coordinate sequencing.
   - Start independent tickets in parallel when safe.
   - Hold dependent tickets until their upstream context is available.
   - When a subagent reports a blocker, decide whether to wait, resequence, split the work differently, or ask the human for a decision.
   - Keep dependency notes current so later subagents receive the correct upstream PR, branch, or implementation context.

7. Finish with a review-ready report.
   - Re-read the durable orchestration note before reporting, then reconcile ticket status, PR links, blockers, and dependency order.
   - Return the list of opened PRs.
   - Put the PRs in the order the human should review them.
   - Explain the review order using dependencies or integration risk.
   - Call out any ticket that did not produce a PR, did not produce a report, or remains blocked.

## Subagent Completion Report

Each `ticket-execution-coordinator` must report back with:

- ticket or unit worked
- PR link
- summary of what changed
- implementation report
- independent review report
- security review report, or not-applicable reason
- QA report with manual/runtime evidence
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
- Ticket coordinator dispatch starts before user approval of the multi-ticket spec and plan.
- A ticket coordinator is asked to perform intake, user-facing brainstorming, spec creation, plan creation, or approval gathering.
- A first-level prompt assigns implementation, review, QA, UI/UX checks, PR creation, and completion reporting to one worker.
- A ticket coordinator handoff says to own all execution directly instead of coordinating deeper delegated phases.
- Parent-side review is treated as a replacement for independent per-ticket review.
- Completion is summarized as a generic report instead of the required phase evidence.
- A combined worker report is accepted instead of distinct implementation, review, security-review-or-skip, manual/runtime QA, and UI/UX-or-skip evidence.
- The ticket set, Epic children, or sub-tickets were not fully gathered.
- Work begins before dependencies and parallelization are mapped.
- The durable orchestration note is missing, stale, or not re-read after compaction or resume.
- A ticket is marked complete without both a PR and subagent report.
- The final report lacks PR links, review order, or dependency rationale.
- A PR body does not give the human enough review focus.

When rejecting a rushed worker-collapse plan, the response must explicitly state:
- Ticket coordinators must not perform user-facing brainstorming, spec creation, plan creation, or approval gathering.
- Each ticket remains incomplete until distinct returned evidence includes implementation, independent review, security-review-or-not-applicable, manual/runtime QA, UI/UX-or-not-applicable, fixes/reruns, PR link, completion report, risks, and blockers or downstream notes.
