---
name: multi-ticket-work
description: Use when the user wants an agent to work a full multi-ticket scope, such as a set of tickets, an Epic with multiple tickets, or a parent ticket with child tickets or sub-tickets. The main agent orchestrates sequencing and parallelization, dispatches one subagent per ticket or unit of work, collects each PR and completion report, and returns the PR review order. Do not use for one standalone ticket.
---

# Multi-Ticket Work

## Purpose

Use this skill when the requested unit of work is the whole multi-ticket set: several tickets, an Epic and its tickets, or a parent ticket and its child tickets/sub-tickets.

The main agent is the orchestrator. It identifies the complete ticket scope, chooses the execution order, decides what can run in parallel, dispatches the work, coordinates blockers, collects completion reports, and gives the human a final PR review order. The main agent does not implement ticket work inline.

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

3. Dispatch the work.
   - Dispatch one subagent per ticket or unit of work.
   - Each subagent request must include its ticket context, relevant parent/Epic context, dependency constraints, repository instructions, PR expectations, the PR description review-focus requirement, and the required completion report.
   - State plainly in each dispatch that the subagent must open a PR and return a completion report before the ticket or unit is complete.
   - State plainly in each dispatch that the PR description must tell the human what to review carefully.
   - A ticket or unit is not complete until its subagent has opened a PR and returned a completion report.
   - The main agent tracks status and blockers, but does not take over implementation inline.

4. Coordinate sequencing.
   - Start independent tickets in parallel when safe.
   - Hold dependent tickets until their upstream context is available.
   - When a subagent reports a blocker, decide whether to wait, resequence, split the work differently, or ask the human for a decision.
   - Keep dependency notes current so later subagents receive the correct upstream PR, branch, or implementation context.

5. Finish with a review-ready report.
   - Return the list of opened PRs.
   - Put the PRs in the order the human should review them.
   - Explain the review order using dependencies or integration risk.
   - Call out any ticket that did not produce a PR, did not produce a report, or remains blocked.

## Subagent Completion Report

Each subagent must report back with:

- ticket or unit worked
- PR link
- summary of what changed
- important decisions or deviations
- tests or checks performed
- known risks, blockers, or follow-up needed
- downstream dependency notes for later tickets

## PR Description Requirement

Every PR description must make the human review focus obvious. It should surface:

- ticket scope
- what changed
- dependency order or related PRs
- checks performed
- known risks or follow-up
- what the human should look at most carefully

This requirement belongs in the subagent dispatch request, not only in the final summary.

## Failure Signals

- The main agent starts implementing a ticket itself.
- The ticket set, Epic children, or sub-tickets were not fully gathered.
- Work begins before dependencies and parallelization are mapped.
- A ticket is marked complete without both a PR and subagent report.
- The final report lacks PR links, review order, or dependency rationale.
- A PR description does not tell the human what to review carefully.
