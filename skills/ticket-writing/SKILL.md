---
name: ticket-writing
description: Use when the user asks to write, draft, refine, or clean up agile backlog prose from approved or sufficiently scoped context, including epics, user stories, tasks, acceptance criteria, titles, descriptions, dependencies, or platform-neutral ticket drafts.
---

# Ticket Writing

## Purpose

Create clean, human-readable, platform-neutral ticket drafts from approved context. Inputs may be a PRD, prototype, planning packet, technical notes, rough brief, or existing draft.

## Rules

- Write tickets; do not plan the feature from scratch, edit PRDs, or publish to a tracker.
- If context is too thin for coherent acceptance criteria, ask for missing facts or switch back to work planning before drafting final ticket prose.
- Keep titles short, specific, and outcome-based. Avoid file names, parameters, mechanisms, or vague labels.
- Use standard agile user-story shape when drafting stories: `As a [Actor], I want [capability], so that [outcome]`.
- Keep technical details concise, formatted, and human-readable. Preserve real contracts, interfaces, dependencies, and edge cases, but remove noise.
- Acceptance criteria must be concrete, coherent, pass/fail, and cover the feature's behavior, permissions, edge cases, and integration outcomes.
- Mark dependencies clearly: parent, blocked-by, blocks, related work, follow-up, and out-of-scope items when known.
- When tickets will be created in a tracker, do not leave dependencies as prose only. Preserve the relationship type so the tracker or ticket-planning app can create native issue links.
- For user stories, prefer vertical slices that deliver user-observable value and include relevant UI, API, data, permissions, integrations, notifications, analytics, or external systems.
- Reference prototype routes/states instead of copying layout, styling, placeholders, helper text, or button copy unless the wording is business-critical or explicitly requested.
- Keep parent epics high-level; child tickets carry implementation specifics and should link back to the epic through the tracker's native parent/child relationship.

## Templates

Story/task:

```markdown
Title: <short outcome>

## User Story
As a [Actor], I want [capability], so that [outcome].

## Acceptance Criteria
- [ ] <observable pass/fail behavior>

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
- dependencies and parent/child relationships are explicit and ready for native issue links
- stale, contradictory, or out-of-scope content is removed
- dense identifiers are reformatted into blocks; explanatory comments are marked
