---
name: feature-work-planning
description: Use when the user asks for upstream feature or work planning before drafting tickets, including clarifying product behavior, scoping technical systems, dependencies, sequencing, risks, rollout, migrations, integrations, or deciding the backlog breakdown at a planning level.
---

# Feature Work Planning

## Purpose

Turn an idea, PRD, prototype, conversation, or technical brief into an approved work plan and ticket-writing packet. This skill plans the work; it does not write polished ticket drafts.

## Inputs

Use any available context: user notes, PRD sections, prototypes/designs, existing tickets, technical plans, codebase scope, repo constraints, or prior decisions. A PRD is helpful but never required.

## Workflow

1. Establish the goal, users, success criteria, and non-goals.
2. If context is thin, start with a Requirements Alignment section before the work plan. Include each label: users, flow, data/entities/lifecycle, permissions, integrations, edge cases, non-goals, and success criteria. Mark unknowns as questions instead of skipping a label.
3. Identify affected systems: UI, API, data, permissions, jobs, migrations, notifications, analytics, billing, audit logs, external systems, and operational concerns when relevant.
4. Identify dependencies, sequencing, risks, rollout or migration needs, and verification surfaces.
5. If planning reveals a PRD or product source-of-truth gap, flag it as a separate `manage-prd` follow-up before ticket writing. Do not turn documentation alignment into an implementation slice unless the user requested documentation work.
6. Propose the ticket breakdown by user outcome or delivery risk. When the source context lists systems or components, do not mirror that list into layer tickets; group the system work under outcome or risk slices. Candidate slice titles should name outcomes or risks, not only systems such as API, UI, migration, analytics, rollout, or QA. For example, convert "API, banner, migration, analytics, rollout, QA" into slices like "enforce the decision safely," "explain the state to the user," "make existing data compatible," and "observe and control launch," with systems listed as integration points inside each slice. Use an enabling slice only when a prerequisite cannot deliver user value directly.
7. Ask the user to approve the work plan before sending it to ticket writing.

## Ticket-Writing Packet

Produce a compact packet with:

- goal and source context
- approved assumptions and open questions
- proposed tickets with outcome, scope, dependencies, order, and integration points
- technical notes that tickets must preserve
- acceptance themes and verification surfaces
- PRD updates needed, if any

If a product source of truth should change, recommend a `manage-prd` follow-up. If the user wants polished ticket drafts, route the approved packet to `ticket-writing`.

## Boundaries

- Do not edit PRDs.
- Do not publish or create tracker issues.
- Do not write final ticket prose unless the user switches to ticket writing.
- Do not invent acceptance criteria or technical facts when planning context is insufficient; ask or mark assumptions for approval.
