---
name: jira-ticket-writing
description: Use when drafting, creating, or editing Jira tickets for Edi where formatting preferences matter: acceptance criteria placement, Jira task checkboxes, clean summaries, section layout, native issue relationships, Bitbucket link formatting, and sparse label usage.
---

# Jira Ticket Writing

## Overview

Apply these preferences when writing Jira ticket drafts or publishing/editing tickets through Jira tools. Use normal product/backlog judgment for scope; this skill only captures formatting and writing preferences.

## Ticket Shape

- Keep the Jira summary clean and key-free. Do not prefix summaries with the ticket id, such as `MKT-123 -`.
- Use concise, outcome-focused titles. Avoid vague titles and file-path-only titles.
- Prefer these description sections when relevant:
  - `## User Story`
  - `## Current Context`
  - `## Technical Notes`
  - `## Out Of Scope`
- Make `Technical Notes` its own top-level section.
- Make `Out Of Scope` its own top-level section.
- Do not add a `Source Context` section unless the user explicitly asks for one.
- Do not add meta-notes such as "Acceptance criteria are tracked in the Acceptance & Testing Criteria field."

## Acceptance Criteria

- Put acceptance criteria in Jira's `Acceptance & Testing Criteria` field, not in the description body.
- Use real Jira task checkboxes, not markdown `[ ]` text.
- When using Jira API fields, represent checkboxes with Atlassian Document Format `taskList` / `taskItem` nodes:

```json
{
  "type": "doc",
  "version": 1,
  "content": [
    {
      "type": "taskList",
      "attrs": { "localId": "ticket-ac" },
      "content": [
        {
          "type": "taskItem",
          "attrs": { "localId": "ticket-ac-1", "state": "TODO" },
          "content": [{ "type": "text", "text": "Criterion text." }]
        }
      ]
    }
  ]
}
```

- Write criteria as pass/fail outcomes. Avoid vague "consider" or "look into" wording unless the ticket is explicitly an investigation.
- Keep checkboxes user- or delivery-observable where possible.

## Jira Relationships

- Model parent/epic relationships with Jira's native parent field.
- Model blockers, blocked-by, related work, and follow-ups with native Jira issue links when concrete issue keys exist.
- Do not put dependency blocks in the description body.
- If the available Jira tool cannot create a native issue link, leave dependency prose out of the ticket and report the limitation in the final response.

## Links And Labels

- Format Bitbucket repository links as Markdown references with meaningful labels, for example: `[yesenergy/yes-map](https://bitbucket.org/yesenergy/yes-map/src/master/)`.
- Avoid bare Bitbucket URLs in ticket descriptions.
- Use labels sparingly. Do not add labels by default.
- If labels seem useful, propose them to the user or add them only when the user asks.

## Writing Style

- Use "the new V3 map component" for the Mapbox v3 replacement work unless the user gives a different name.
- Keep ticket prose concise and practical.
- Keep implementation details in `Technical Notes`; keep user value in `User Story` and `Current Context`.
- Separate out-of-scope work instead of mixing it into technical notes.
- Avoid redundant explanatory text about Jira fields, templates, or process mechanics inside the ticket body.
