---
name: ticket-planner
description: Use when the user asks to turn PRDs, feature briefs, designs, or prototypes into clean epics, vertical-slice user stories, acceptance criteria, or implementation-ready backlog drafts for any issue tracker.
compatibility: Requires filesystem access for project context. No issue-tracker integration is required unless the user separately asks to publish drafts.
---

# Ticket Planner

## Overview

Turn product context into clean, platform-neutral epics and user stories. A good story is a vertical slice: one user-observable outcome plus the integration points needed end to end.

PRD owns business rules; prototype owns UI, interaction details, and visible copy.

## Required Rules

- Stay issue-tracker neutral while planning; publishing belongs to a separate tracker-specific skill.
- PRD and prototype are optional inputs. If product context is missing or thin, run a requirements interview before drafting.
- Draft no stories from guesses; first get user approval on a shared-understanding brief.
- Slice stories by user outcome and integration path, not by UI component, layer, or technical task.
- Cover relevant integration points: UI/API/data/permissions/external systems/notifications/analytics.
- Edit no `PRD.md` content until the user approves the proposed business-rule additions.
- Reference prototype routes/screens/states instead of repeating prototype copy, layout, or styling.
- Include exact UI copy only when business-critical, absent from prototype, or explicitly requested.

## Start Checklist

- [ ] Read `PRD.md` and prototype context, if present.
- [ ] If context is missing or insufficient, run [references/requirements-interview.md](references/requirements-interview.md).
- [ ] Get approval on the shared-understanding brief before drafting.
- [ ] Select workflow and identify vertical slices.
- [ ] Draft, refine, and get approval for platform-neutral stories.
- [ ] Propose user-approved PRD updates for newly clarified business rules.
- [ ] If publishing is requested, infer the issue tracker from project docs or ask the user.

## Context Sources

Read all available product context before drafting. For discovery, including issue-tracker convention discovery from project docs, read [references/context-gathering.md](references/context-gathering.md).

If PRD and prototype conflict, ask which source wins before drafting.

## Reference Files

Read only what the selected path needs:

- Context: [references/context-gathering.md](references/context-gathering.md)
- Requirements interview: [references/requirements-interview.md](references/requirements-interview.md)
- Prototype boundaries: [references/prototype-boundaries.md](references/prototype-boundaries.md)
- Quality bar: [references/ticket-quality.md](references/ticket-quality.md)
- Workflows: [workflows/single-epic.md](workflows/single-epic.md), [workflows/bulk-planning.md](workflows/bulk-planning.md), [workflows/user-story.md](workflows/user-story.md), [workflows/epic-with-stories.md](workflows/epic-with-stories.md)
- Regression evals: [tests/evals.md](tests/evals.md)

## Scenario Selection

| User intent | Workflow |
| --- | --- |
| Create one epic for a feature area | [workflows/single-epic.md](workflows/single-epic.md) |
| Plan all major epics | [workflows/bulk-planning.md](workflows/bulk-planning.md) |
| Create one story under an existing epic | [workflows/user-story.md](workflows/user-story.md) |
| Create an epic and all stories together | [workflows/epic-with-stories.md](workflows/epic-with-stories.md) |

If unclear, ask: one epic, all epics, one story, or an epic with stories?

## Clarifying Questions

Ask questions only when the answer changes business meaning, acceptance criteria, scope, sequencing, or draft attributes.

Do not ask about details already settled by the PRD or prototype. Put non-blocking assumptions in the draft for approval.

## PRD Sync

When clarifications add new business details not in `PRD.md`, propose a concise PRD patch summary and ask before editing.

Only add business rules, domain concepts, data models, user flows, permissions, lifecycle rules, or business-impacting edge cases. Never add implementation details, component architecture, layout, styling, or UI-widget choices.

## Definition Of Done

A planning session is complete when approved epics/stories are clean issue-tracker-neutral drafts, each story represents a coherent vertical slice with integration points covered, and any approved PRD updates are applied. Publishing to an issue tracker is a separate follow-up step.
