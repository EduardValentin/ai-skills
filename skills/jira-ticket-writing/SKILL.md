---
name: jira-ticket-writing
description: Use when drafting, creating, or editing Jira tickets
---

# Jira Ticket Writing

## Overview

Apply these preferences when writing Jira ticket drafts or publishing/editing tickets through Jira tools. This skill only captures formatting and writing preferences.

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

- Put acceptance criteria in Jira's `Acceptance & Testing Criteria` field, not in the description body. Only when there is not dedicated field, you are allowed to put it in the body.
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

- Format repository links as Markdown references with meaningful labels, for example: `[yesenergy/yes-map](https://bitbucket.org/yesenergy/yes-map/src/master/)`.
- Avoid bare URLs in ticket descriptions.
- Use labels sparingly. Do not add labels by default.
- If labels seem useful, propose them to the user or add them only when the user asks.

## Writing Style

- Keep ticket prose concise and practical.
- Keep implementation details in `Technical Notes`; keep user value in `User Story` and `Context`.
- Separate out-of-scope work instead of mixing it into technical notes.
- Avoid redundant explanatory text about Jira fields, templates, or process mechanics inside the ticket body.
