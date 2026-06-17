---
name: feature-work-planning
description: Use when the user asks to plan future product, feature, technical, or operational work, with or without an existing ticket, PRD, prototype, or backlog item. Use for clarifying behavior, scope, systems, dependencies, sequencing, risks, rollout, migrations, integrations, or delivery slices before implementation or backlog writing.
---

# Feature Work Planning

## Purpose

Turn an idea, conversation, PRD, prototype, existing ticket, technical brief, or rough problem statement into an approved future-work plan. This skill plans the work implied by the request; it does not implement it, edit source-of-truth documents, or write polished backlog items.

## When To Use

- The user wants to plan future work before implementation.
- The user wants to turn rough context into a coherent work plan, delivery sequence, or backlog-ready planning packet.
- The request may or may not involve tickets, PRDs, prototypes, or existing artifacts.

Do not use for writing final ticket prose, editing PRDs, publishing tracker issues, or executing an approved implementation plan.

## Inputs

Use any available context: user notes, PRD sections, prototypes/designs, existing tickets, technical plans, codebase scope, repo constraints, or prior decisions. No single artifact is required.

## Workflow

1. Establish the goal, users, success criteria, and non-goals.
2. If context is thin, start with a Requirements Alignment section before the work plan. Include each label: users, flow, data/entities/lifecycle, permissions, integrations, edge cases, non-goals, and success criteria. Mark unknowns as questions instead of skipping a label.
3. Identify affected systems: UI, API, data, permissions, jobs, migrations, notifications, analytics, billing, audit logs, external systems, and operational concerns when relevant.
4. Identify dependencies, sequencing, risks, rollout or migration needs, and verification surfaces.
5. If planning reveals a product source-of-truth gap, flag it as a separate documentation decision or follow-up. Do not turn documentation alignment into an implementation slice unless the user requested documentation work.
6. Propose delivery slices by user outcome or delivery risk. When the source context lists systems or components, do not mirror that list into layer slices; group the system work under outcome or risk slices. Candidate slice titles should name outcomes or risks, not only systems such as API, UI, migration, analytics, rollout, or QA. For example, convert "API, banner, migration, analytics, rollout, QA" into slices like "enforce the decision safely," "explain the state to the user," "make existing data compatible," and "observe and control launch," with systems listed as integration points inside each slice. Use an enabling slice only when a prerequisite cannot deliver user value directly.
7. Ask the user to approve the work plan before treating it as ready for implementation, backlog drafting, or other downstream use.

## Planning Packet

Produce a compact packet with:

- goal and source context
- approved assumptions and open questions
- proposed work slices with outcome, scope, dependencies, order, and integration points
- technical notes that downstream work must preserve
- acceptance themes and verification surfaces
- documentation/source-of-truth updates needed, if any

If a product source of truth should change, recommend a separate documentation follow-up. If the user wants backlog items afterward, use the approved planning packet as the source context.

## Boundaries

- Do not edit PRDs.
- Do not publish or create tracker issues.
- Do not write final ticket prose unless the user explicitly switches from planning to backlog drafting.
- Do not invent acceptance criteria or technical facts when planning context is insufficient; ask or mark assumptions for approval.
