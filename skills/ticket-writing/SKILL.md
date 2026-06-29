---
name: ticket-writing
description: Use when the user asks to write, draft, refine, or clean up platform-neutral agile backlog prose from approved or sufficiently scoped context, including epics, user stories, tasks, acceptance criteria, titles, descriptions, dependencies, or ticket drafts that should not be published directly to Jira, Linear, or another tracker.
---

# Ticket Writing

## Purpose

Create clean, human-readable, platform-neutral ticket drafts from approved context. Inputs may be a PRD, prototype, planning packet, technical notes, rough brief, or existing draft.

## Rules

- Write tickets; do not plan the feature from scratch, edit PRDs, or publish to a tracker.
- If context is too thin for coherent acceptance criteria, ask for missing facts or switch back to work planning before drafting final ticket prose.
- If the required deliverables or outcomes are unclear, ask the user to clarify them before drafting the final ticket; do not guess artifacts just to fill `## Outcomes`.
- Keep titles short, specific, and outcome-based. When cleaning drafts, replace file names, parameters, mechanisms, or vague labels with the business or operator outcome.
- Use standard agile user-story shape when drafting stories: `As a [Actor], I want [capability], so that [outcome]`.
- Keep technical details concise, formatted, and human-readable. Preserve real contracts, interfaces, dependencies, and edge cases, but remove noise.
- Acceptance criteria must be concrete, coherent, pass/fail, and cover the feature's behavior, permissions, edge cases, and integration outcomes.
- Mark dependencies clearly: parent, blocked-by, blocks, related work, follow-up, and out-of-scope items when known.
- When tickets will be created in a tracker, do not leave dependencies as prose only. Preserve the relationship type so the tracker or ticket-planning app can create native issue links.
- For tickets that are not implementation-only, or implementation plus another deliverable, include an `## Outcomes` section naming the concrete artifacts or results to produce, such as a document, decision, implementation PR, rollout checklist, analytics event, or handoff.
- For user stories, prefer vertical slices that deliver user-observable value and include relevant UI, API, data, permissions, integrations, notifications, analytics, or external systems.
- Reference prototype routes/states instead of copying layout, styling, placeholders, helper text, or button copy unless the wording is business-critical or explicitly requested.
- Keep parent epics high-level and state native parent-child issue links explicitly; child tickets carry implementation specifics and should link back to the epic through the tracker's native parent/child relationship.

## Templates

Story/task:

```markdown
Title: <short outcome>

## User Story
As a [Actor], I want [capability], so that [outcome].

## Acceptance Criteria
- [ ] <observable pass/fail behavior>

## Outcomes
- <artifact or result required when the ticket is not implementation-only>

## Product And Delivery Notes
- Dependencies:
- Technical notes:
- Source context:
- Out of scope:
```

Epic:

```markdown
Title: <feature capability>

## Overview
<goal and business value>

## Scope
- <included capability>

## Outcomes
- <artifact or result required when the epic is not implementation-only>

## Notes
- Dependencies:
- Native issue links:
- Source context:
- Open questions:
```

## Cleanup Checklist

- title is concise and outcome-based
- description separates business overview from technical notes
- user stories use "As a [Actor], I want [capability], so that [outcome]"
- acceptance criteria are present and testable
- unclear deliverables trigger a clarification question before final ticket prose
- non-implementation or mixed-deliverable tickets include an Outcomes section with concrete artifacts or results
- dependencies and parent/child relationships are explicit and ready for native issue links
- stale, contradictory, or out-of-scope content is removed
- dense identifiers are reformatted into blocks; explanatory comments are marked
