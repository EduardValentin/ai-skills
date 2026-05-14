---
name: linear-issue-writing
description: Use when the user wants to publish approved epics, user stories, backlog drafts, or ticket descriptions into Linear, or needs Linear issue structure, metadata, duplicate detection, parent/sub-issue modeling, or creation/update guidance.
compatibility: Requires a working Linear-capable integration for creation or updates. Can review and format Linear issue drafts without integration access.
---

# Linear Issue Writing

## Overview

Convert approved, platform-neutral backlog drafts into well-structured Linear issues. This skill owns Linear modeling, metadata, duplicate checks, and publishing gates. It does not invent product scope; use `ticket-planner` first for PRD-to-story planning.

## Required Rules

- Do not create or update Linear issues unless the Linear integration is available.
- Create or update nothing until the user approves the exact title, description, parent, project, team, labels, priority, estimate, and other metadata.
- Treat approved drafts as source material. Preserve scope and ask before changing product meaning.
- Run duplicate detection before every issue creation.
- Report created or updated issue identifiers and URLs.

## Start Checklist

- [ ] Confirm review/formatting vs. Linear publishing.
- [ ] Confirm source drafts are approved; otherwise ask whether to refine them first.
- [ ] Confirm target Linear project and team.
- [ ] Ensure the `Epic` label exists if publishing epics.
- [ ] Map drafts to Linear parent/sub-issue structure.
- [ ] Confirm metadata.
- [ ] Run duplicate detection per issue.
- [ ] Create/update only approved issues.

## Linear Model

Epics are normal Linear issues with:

- `Epic` label
- Target project
- High-level description
- User stories as sub-issues

User stories are normal Linear issues with:

- Parent epic when applicable
- Target project
- Approved story description
- Appropriate metadata

Set project explicitly on stories; do not rely on inherited properties.

## Duplicate Detection

Before creating each issue:

1. Fetch existing issues in the target project.
2. Compare title, parent, scope, description, and status.
3. If an issue overlaps, show the likely duplicate and ask whether to skip, update, or create anyway.
4. Proceed only after the user chooses.

This check is per issue, not once per session.

## Metadata Guidance

- Epic titles: descriptive noun phrases, such as `Workout Plan Creation`.
- Story titles: imperative capability phrases, such as `Create workout plan from template`.
- Priority: use dependency and product value; ask if uncertain.
- Estimate: ask for the workspace scale before setting estimates.
- Labels: use `Epic` only for epics; use feature labels only when they already exist or the user approves creation.
- Assignee, cycle, milestone, due date: set only when provided or approved.

## Description Handling

Keep the approved draft's core sections intact. Platform-specific adjustments should be formatting-only unless the user approves a scope change.

If a draft lacks a title, parent, acceptance criteria, or material metadata, ask before publishing. Do not silently fill important gaps.

## Reporting

After publishing, report:

- Issue title
- Issue identifier
- URL
- Parent/child relationship
- Any issue skipped, updated, or left pending
