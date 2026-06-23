---
name: multi-ticket-workflow
description: Manual workflow for coordinating related tickets through shared planning, per-ticket plans, delegated execution, and handoff.
disable-model-invocation: true
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
---

# Multi Ticket Workflow

## Purpose

Coordinate a multi-ticket scope from requirements intake through delegated execution and dependency-aware handoff.

This workflow owns full-scope intake, cross-ticket brainstorming, approved coordination planning, adaptive delegation, blocker handling, dependency order, and final handoff. It does not define the detailed implementation, review, QA, or UI verification mechanics for each delegated unit.

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

Create and return a provisional map from known facts before mapping results are complete, with one entry per unit covering known dependencies, unknown dependencies, likely parallel/sequential status, and next mapping action; mark unknown or uncertain edges instead of saying the map is missing or offering it later:

- in-scope tickets or units
- dependencies and order constraints
- shared files, shared data, shared UI, shared services, migrations, feature flags, or integration risks
- tickets that can run in parallel
- tickets that should be split, merged, sequenced, or delegated together
- likely PR boundaries
- evidence needed to know when delegated work is ready for handoff

Before brainstorming, dispatch one read-only code mapping pass per affected ticket to `code-mapper` and use the literal name `code-mapper` in planning responses, not generic labels. This mapping is a planning action and is not gated by spec/design or coordination-plan approval. If `code-mapper` is unavailable, use a generic read-only subagent. Only map inline if delegation is unavailable or unsafe. Do not postpone this scoping until after brainstorming or approval.

Ask each mapper to return affected files/surfaces, entry points, shared contracts, dependencies, analogous implementations, tests, risks, and verification surfaces with locators. Use those reports and known ticket facts to build a provisional dependency and parallelization map.

## Plan Before Implementation

Run a relentless cross-ticket brainstorming interview with the user until there is shared understanding of the full scope, ticket boundaries, dependencies, sequencing, risks, non-goals, alternatives, and any low-confidence point that could affect implementation or delegation.

Produce a concise multi-ticket spec/design that names each in-scope ticket and material dependency. Ask the user to approve the spec/design itself.

After spec/design approval, write an implementation plan for each in-scope ticket from the approved multi-ticket spec/design, gathered context, dependency map, and full-scope brainstorming discussion.

Then produce a coordination plan that decides the execution shape for each ticket or unit: inline, delegated, hybrid, parallel when independent, sequential when dependency-bound, staged when shared groundwork is needed, and consolidated when splitting would create coordination waste.

Ask the user to approve the coordination plan itself. Do not dispatch or implement before both approvals.

When the user asks to work, proceed from, or get started on an unapproved multi-ticket scope, state the gates explicitly before any delegation or implementation: cross-ticket brainstorming, approved multi-ticket spec/design, one implementation plan per in-scope ticket, and approved coordination plan with an execution-shape decision for each ticket or unit. Every gate summary must name all four preconditions.

## Execution Packets

Prepare one execution packet per ticket or approved unit for `implementation-coordinator`; each packet and dispatch line must name that delegate.

When the multi-ticket spec/design, per-ticket implementation plans, and coordination plan are already approved, do not stop at describing the sequence. Return the execution packet outlines and orchestration-state update immediately before dispatch or handoff. Include required fields even when evidence is unavailable; mark the gap instead of omitting the field. Do not collapse packets into a short sequence summary or offer packet formatting as an optional next step.

For approved scopes, respond in this order:

1. Orchestration state: inventory, approvals, dependencies, assignments, PR state, blockers, and review order.
2. One execution packet per unit: delegate `implementation-coordinator`, ticket/parent context, approved spec/design slice, approved ticket plan, dependency constraints, affected surfaces or explicit gap, PR/handoff expectations, and completion evidence.
3. Dispatch or handoff action.

Each packet should include:

- relevant ticket and parent context
- approved spec/design slice
- approved ticket implementation plan
- approved coordination-plan slice
- dependency constraints and upstream/downstream notes
- known affected files or surfaces, including mapping evidence or unresolved mapping gaps
- expected PR or handoff expectations
- what completion evidence the coordinator needs back

Use a compact packet outline per unit with those fields. For unavailable facts, write `unknown` or `not provided`; do not omit the field.

Packets must be self-contained enough that a worker can execute without redoing ticket intake or user-facing planning.

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

Every orchestration state update should explicitly include assignment state and PR state for each ticket, even when the value is pending, unassigned, blocked, or no PR yet. Post-approval coordination updates must include current inventory, approvals, dependency status, assignment or dispatch status, PR or handoff status, blockers, packet lifecycle, and final review order when known.

Update it after scope gathering, execution mapping, approval, dispatch, blocker reports, completion reports, and PR creation. Re-read it at the start of work, after context compaction or resume, before dependent work, and before final reporting.

## Delegate The Plan

Delegate each approved ticket or slice to `implementation-coordinator` according to the coordination plan. Prefer the most efficient safe delegation pattern rather than one fixed structure.

When dependency facts leave no safe parallel work, say that explicitly and use sequential or staged delegation instead of implying parallelism is always required.

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
- approved execution packets are offered as an optional follow-up instead of returned immediately
- a worker is asked to perform user-facing planning or approval gathering
- completion is accepted without the handoff evidence needed for sequencing or review order
- the durable orchestration note is missing, stale, or not re-read after compaction or resume
- final report lacks PR links, review order, or dependency rationale
