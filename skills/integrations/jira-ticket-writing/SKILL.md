---
name: jira-ticket-writing
description: Drafts and revises Jira ticket fields with outcome-focused summaries, structured descriptions, native acceptance tasks, and issue relationships. Use when preparing, creating, or editing Jira tickets.
compatibility: >-
  Drafting works without Jira access. Publishing or editing requires an approved Jira integration or API configured through JIRA_CONFIG_PATH, permission for the target project, and support for the required fields. Field IDs, ADF support, parent fields, and issue-link types vary by instance. When a required capability is unavailable, return a draft, name unapplied fields or links, and do not claim or perform a partial write.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Jira Ticket Writing

## Overview

Write practical Jira tickets whose field structure matches the target Jira instance. Preserve user value and delivery outcomes while keeping implementation detail, acceptance evidence, and issue relationships in their proper fields.

## Operating Boundary

- Draft by default. Requests to prepare, draft, rewrite, or clean a ticket do not authorize a Jira mutation.
- Create or update an issue only when the user explicitly requests the write and an approved Jira integration is available. Use a dry run when the integration provides one.
- Before a write, inspect the target project's field and issue-link metadata. For an edit, also read the current issue. Verify the exact project or issue, complete field payload, parent, and requested links immediately before mutation.
- If the target, field mapping, representation, or relationship direction cannot be verified, return the usable draft and identify the blocker. Do not silently publish a partial ticket; require explicit approval for any reduced write.

## Field Representation

- For a human-readable draft, Markdown headings and labeled links are acceptable.
- For Jira API fields or a payload, return field-keyed data and serialize every rich-text value in the exact format accepted by the configured Jira instance. Use ADF nodes and marks when the field requires ADF; do not present Markdown as an API-ready ADF value.
- Discover instance-specific custom field IDs instead of inventing them. If field metadata is unavailable, use semantic field names in the draft and report that ID mapping is still required.

## Ticket Shape

- Keep the Jira summary clean and key-free. Do not prefix titles with the ticket id.
- Use concise, outcome-focused titles. Avoid vague titles and file-path-only titles.
- Prefer these description sections when relevant:
  - `## User Story`
  - `## Context`
  - `## Out Of Scope`
  - `## Outcomes`
  - `## Technical Notes`

- Do not add meta-notes such as "Acceptance criteria are tracked in the Acceptance & Testing Criteria field."

## Acceptance Criteria

- Discover whether the project has a dedicated `Acceptance & Testing Criteria` field and whether that field supports native task nodes.
- When the dedicated field supports them, put acceptance criteria there as real Jira task checkboxes, not Markdown `[ ]` text. For Jira API fields, follow `references/adf-task-list.md` and use ADF `taskList` and `taskItem` nodes.
- When the dedicated field exists but cannot represent native tasks, keep the criteria assigned to that field in the draft, report the capability gap, and stop before publication. Do not move them into the description or degrade them to Markdown checkboxes without an explicitly approved exception.
- Only when no dedicated field exists may criteria fall back to the description. Use native ADF task nodes there when supported; otherwise return the draft, report the limitation, and stop before publication.

- Write criteria as pass/fail outcomes. Avoid vague "consider" or "look into" wording unless the ticket is explicitly an investigation.
- Keep checkboxes user- or delivery-observable where possible.

## Jira Relationships

- Model parent/epic relationships with Jira's native parent field.
- Model blockers, blocked-by, related work, and follow-ups with native Jira issue links when concrete issue keys exist.
- Resolve the target instance's available link types and inward/outward directions. Use only an unambiguous semantically matching type and direction; do not guess from a display label.
- Do not put dependency blocks in the description body.
- If no matching link type exists or the integration cannot create it, leave dependency prose out of the ticket, identify each unapplied relationship, and do not claim it was created. Require explicit approval before publishing without requested links.

## Links And Labels

- Give repository links meaningful labels in the target field's representation, for example `[yesenergy/yes-map](https://bitbucket.org/yesenergy/yes-map/src/master/)` in Markdown or linked text in ADF.
- Avoid bare URLs in ticket descriptions.
- Use labels sparingly. Do not add labels by default.
- If labels seem useful, propose them to the user or add them only when the user asks.

## Writing Style

- Keep ticket prose concise and practical.
- Keep implementation details in `Technical Notes`; keep user value in `User Story` and `Context`.
- Separate out-of-scope work instead of mixing it into technical notes.
- Avoid redundant explanatory text about Jira fields, templates, or process mechanics inside the ticket body.
