---
name: multi-ticket-workflow
description: Use when the user asks to work a set of related tickets, an Epic, a parent ticket with children, or any multi-ticket scope that requires shared intake, dependency mapping, coordinated planning, and delegated execution. Do not use for one standalone ticket.
---

# Multi Ticket Workflow

## Purpose

Coordinate a multi-ticket scope from requirements intake through delegated execution and dependency-aware handoff.

This workflow owns full-scope intake, cross-ticket brainstorming, approved coordination planning, adaptive delegation, blocker handling, dependency order, and final handoff. It does not define the detailed implementation, review, security, QA, or UI verification mechanics for each delegated unit.

## Coordinator Role

The main agent owns:

- full scope discovery
- dependency and parallelization map
- cross-ticket requirements/design alignment
- multi-ticket spec/design approval
- multi-ticket coordination plan approval
- execution packet creation
- orchestration state
- blocker handling
- final PR review order and handoff report

The main agent should prefer delegation for ticket implementation and keep the main context focused on coordination. It may keep very small coordination-only work inline when that does not undermine orchestration.

## Gather Scope

1. Read every ticket the user named.
2. Confirm which tickets are in scope when parent structure, repository state, existing PRs, or the user request is ambiguous.
3. Understand the goal, stakeholder implications, acceptance criteria, dependencies, blockers, parent context, and ambiguity for each ticket.
4. Mark missing details as unknowns or blockers instead of smoothing them over.
5. Treat every named unit as an in-scope candidate. If exact identifiers or details are missing, list the candidate units, mark what is unknown, and confirm the scope before execution.

## Build The Coordination Map

Create a map from known facts:

- in-scope tickets or units
- dependencies and order constraints
- shared files, shared data, shared UI, shared services, migrations, feature flags, or integration risks
- tickets that can run in parallel
- tickets that should be split, merged, sequenced, or delegated together
- likely PR boundaries
- evidence needed to know when delegated work is ready for handoff

Build the best provisional dependency and parallelization map from available facts before execution. Mark uncertain edges instead of waiting for perfect inventory.

## Plan Before Implementation

Run a relentless cross-ticket brainstorming interview with the user until there is shared understanding of the full scope, ticket boundaries, dependencies, sequencing, risks, non-goals, alternatives, and any low-confidence point that could affect implementation or delegation.

Produce a concise multi-ticket spec/design that names each in-scope ticket and material dependency. Ask the user to approve the spec/design itself.

After spec/design approval, write an implementation plan for each in-scope ticket from the approved multi-ticket spec/design, gathered context, dependency map, and full-scope brainstorming discussion.

Then produce a coordination plan that decides how to delegate those ticket implementation plans in the most efficient safe fashion: parallel when independent, sequential when dependency-bound, staged when shared groundwork is needed, and consolidated when splitting would create coordination waste.

Ask the user to approve the coordination plan itself. Do not dispatch or implement before both approvals.

When the user asks to proceed from a high-level multi-ticket scope, state the gates explicitly: cross-ticket brainstorming, approved multi-ticket spec/design, one implementation plan per in-scope ticket, and approved coordination plan before delegation. Every gate summary must name all four preconditions.

## Execution Packets

Prepare one execution packet per ticket or approved unit.

Each packet should include:

- relevant ticket and parent context
- approved spec/design slice
- approved ticket implementation plan
- approved coordination-plan slice
- dependency constraints and upstream/downstream notes
- known affected files or surfaces
- expected PR or handoff expectations
- what completion evidence the coordinator needs back

Packets must be self-contained enough that a worker can execute without redoing ticket intake or user-facing planning.

When scope and plans are already approved and the user asks to proceed, create the execution packet outlines immediately and record the orchestration state. Do not offer packet creation as an optional next step.

## Keep Durable Orchestration State

Maintain an uncommitted orchestration note in an ignored or scratch location.

Record:

- ticket inventory
- parent/Epic context
- dependency map
- approved spec/design, ticket implementation plan, and coordination plan summaries
- execution packets
- dispatch assignments or inline units
- status, PR links, blockers, decisions, next actions
- re-read checkpoints after compaction or resume

Every orchestration state update should explicitly include assignment state and PR state for each ticket, even when the value is pending, unassigned, blocked, or no PR yet.

Update it after scope gathering, execution mapping, approval, dispatch, blocker reports, completion reports, and PR creation. Re-read it at the start of work, after context compaction or resume, before dependent work, and before final reporting.

## Delegate The Plan

Delegate each approved ticket or slice according to the coordination plan. Prefer the most efficient safe delegation pattern rather than one fixed structure.

For each unit, provide its approved execution packet and make clear what is in scope, what is out of scope, what dependency constraints apply, and what completion evidence must come back. Do not ask an execution worker to gather user-facing approval or redesign the ticket set.

The main agent tracks status, resolves blockers, resequences work, updates the orchestration note, and asks the user for decisions when tradeoffs affect scope, sequencing, or user-visible behavior.

## Final Report

Before reporting, re-read the durable orchestration note and reconcile ticket status, PR links, blockers, and dependency order.

Return:

- in-scope ticket inventory
- approved spec/design summary
- approved coordination plan summary
- PR list
- human review order with dependency rationale
- per-ticket status and handoff evidence summary
- blockers, risks, assumptions, and follow-ups
- tickets that did not produce a PR or completion report

## Red Flags

Stop and recover when:

- the ticket set, Epic children, or sub-tickets were not fully gathered
- work starts before multi-ticket spec/design and plan approval
- dependencies and parallelization were not mapped
- the main agent silently implements a broad ticket set without preserving coordination state
- execution packets are not self-contained
- a worker is asked to perform user-facing planning or approval gathering
- completion is accepted without the handoff evidence needed for sequencing or review order
- the durable orchestration note is missing, stale, or not re-read after compaction or resume
- final report lacks PR links, review order, or dependency rationale
