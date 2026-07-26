---
name: ticket-writing
description: >-
  Drafts and refines platform-neutral tickets, user stories, and epics from approved briefs or existing drafts. Use when backlog prose, testable acceptance criteria, outcomes, scope, or dependency relationships must be written or cleaned up before tracker publication.
compatibility: >-
  Uses the `feature-work-planning` skill when available if source decisions are incomplete; otherwise asks for the missing facts and defers final ticket prose. Tracker publishing tools are optional because this skill produces drafts only.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Ticket Writing

## Scope

Produce human-readable, platform-neutral ticket drafts from settled source context. A brief is approved for drafting when the user labels it approved or directly supplies it as the basis for a draft. Do not infer approval from discovered documents, unresolved alternatives, brainstorming, or a request to explore a feature. If approval is unclear, ask whether the decisions are settled before writing final ticket prose.

Draft or refine tickets only. Do not plan an undefined feature, edit its source-of-truth documents, publish to a tracker, or claim that tracker relationships were created.

## Workflow

1. Confirm that the source establishes the actor or owner, desired outcome, scope, permissions, important behaviors, edge cases, integrations, and known dependencies.
2. If material decisions are missing, use the `feature-work-planning` skill before drafting when the current runtime exposes it. Return its planning result or next decision and wait for approval. If it is unavailable, ask for the missing facts and defer final ticket prose. Do not infer availability merely because this skill names the collaborator.
3. Choose the ticket type and write a concise, outcome-based title. For a user story, use `As a [actor], I want [capability], so that [outcome].`
4. Write concrete pass/fail acceptance criteria for observable behavior, permissions, edge cases, and integration outcomes. Preserve approved contracts and constraints; surface unknowns instead of inventing them.
5. Record dependencies, delivery outcomes, technical notes, source context, and exclusions only when relevant.

## Drafting Rules

- Prefer vertical slices that deliver user-observable value across relevant UI, API, data, permissions, integrations, notifications, analytics, or external systems.
- Keep technical identifiers in concise technical notes rather than titles or business descriptions.
- Reference prototype routes and states instead of copying layout, placeholder, helper, or button text unless wording is an approved requirement.
- For non-implementation work or implementation with additional deliverables, add `## Outcomes` and name each required artifact or result. Omit that section for implementation-only work.
- Express every known relationship as its type plus a target key or outcome title, for example `Blocked by: MAIL-12 - Configure email delivery`. Use `Parent`, `Blocked by`, `Blocks`, `Related`, or `Follow-up` as appropriate.
- Keep parent epics at capability level. State that child tickets use the tracker's native parent-child relationship. Do not invent candidate child stories when their scope is unapproved; preserve approved child outlines without adding implementation detail.

## Templates

Story or task:

```markdown
Title: <short outcome>

## User Story
As a [actor], I want [capability], so that [outcome].

## Acceptance Criteria
- [ ] <observable pass/fail behavior>

## Product And Delivery Notes
- Dependencies: <relationship type and target key or title>
- Technical notes:
- Source context:
- Out of scope:
```

Use `## Overview` instead of `## User Story` for a task that does not fit the user-story form.

For non-implementation or mixed-deliverable work, add:

```markdown
## Outcomes
- <required artifact or result>
```

Epic:

```markdown
Title: <feature capability or outcome>

## Overview
<goal and business value>

## Acceptance Criteria
- [ ] <capability-level observable pass/fail behavior>

## Scope
- <included capability>

## Notes
- Dependencies: <relationship type and target key or title>
- Native parent-child relationship:
- Source context:
- Open questions:
```

## Final Check

- The title names the outcome, and the description separates business value from technical notes.
- Acceptance criteria are coherent, testable, and traceable to approved context.
- Required outcomes are explicit without turning possibilities into commitments.
- Dependencies and parent-child relationships are typed and ready for native tracker links.
- Stale, contradictory, and out-of-scope content is removed.
