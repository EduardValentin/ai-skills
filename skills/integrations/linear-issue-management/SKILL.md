---
name: linear-issue-management
description: Use when managing or publishing Linear issues, epics, stories, parent/sub-issue relationships, comments, metadata, duplicate checks, or updates from approved backlog drafts.
compatibility: >-
  Live reads and writes require Linear MCP or https://api.linear.app/graphql. For GraphQL, use LINEAR_API_KEY first; otherwise LINEAR_CONFIG_PATH must name a UTF-8 plaintext file containing only the API key after surrounding ASCII whitespace is trimmed. Empty or internally whitespace-containing values are invalid. Without live access, review or format only. ticket-writing and feature-work-planning are optional; missing required collaborators block publishing.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Linear Issue Management

## Overview

Manage Linear issues without changing approved product scope. Use Linear MCP when it is configured; otherwise use direct GraphQL. Treat every mutation as gated by approved content, resolved workspace metadata, and a per-issue duplicate check.

## Access and collaborators

- For direct GraphQL, use non-empty `LINEAR_API_KEY` first and reject it if it contains whitespace. Otherwise, read the file named by `LINEAR_CONFIG_PATH` strictly as UTF-8 plaintext, strip surrounding ASCII whitespace including a final newline, and reject an empty result or any remaining whitespace. The entire result is the key; do not parse JSON, a key/value assignment, or multiple lines. Never print, log, persist, or commit the key; send it only as the authorization value to `https://api.linear.app/graphql`.
- If neither Linear MCP nor direct GraphQL is available, review or format drafts only. Stop before any write and report the pending sequence: metadata lookup, duplicate search, explicit-ID mutation, re-read, then identifier/URL reporting.
- Resolve upstream work in order. If product scope, dependencies, or sequencing are unresolved, use `feature-work-planning` first when available. Once the scope is planned, use `ticket-writing` for a missing or unapproved draft when available. If either required collaborator is unavailable, stop at that stage and request the fully planned or approved material instead of inventing it.

## Publishing gates

Create or update nothing until the user approves the exact effective fields: title, description, parent, project, team, state, labels, priority, estimate, assignee, cycle, milestone, due date, template use, and any other requested or defaultable metadata. For an update, an omitted field stays unchanged. For a creation, omission does not mean unset: Linear's `IssueCreateInput` can apply team or selected-template defaults to unspecified fields.

Before each creation, fetch the actor's team membership, the team's default state and estimate, the applicable member or non-member default template, and any explicitly selected template data. Compute the effective payload by applying explicit proposed values over current team and template defaults. Present every effective value and its source for approval. If the integration cannot expose enough current default information to guarantee the effective payload, block creation rather than treating omissions as safe.

Override a default only with an explicit approved value. Use explicit `null` only when the current Linear schema or official documentation states that it suppresses that field's creation default; never assume omission or `null` clears a default. Use documented neutral scalar values where appropriate, such as priority `0` for No priority. If Linear provides no documented representation that guarantees an approved unset value, block that creation. Missing required fields also block publication.

Resolve approved entity names for team, project, state, assignee, labels, cycle, milestone, and parent to current IDs. Priority is an integer scalar, not an entity ID: `0` = No priority, `1` = Urgent, `2` = High, `3` = Medium, and `4` = Low. A unique entity match or scalar mapping that preserves the approved display value needs no renewed approval; an ambiguous match, fallback, substitution, or changed value does. Preserve approved descriptions, acceptance criteria, and parent/sub-issue scope; ask before changing meaning.

Before each creation, search every page of the target project's issues, including closed and archived results, for overlap in title, scope, description, parent, and status. Treat a candidate as likely overlap when its title or description materially describes the same outcome, especially under the same parent; status alone never dismisses it. Surface the candidate's identifier, title, status, parent, and matching evidence, then ask the user to choose `skip`, `update`, or `create anyway`. Do not mutate either issue before that decision.

## Live workflow

1. Fetch viewer and organization context. For creation, determine team membership and read the team's current defaults plus the applicable or selected template data.
2. Discover the target teams, projects, users, workflow states, labels, cycles, and milestones. Resolve entity names to workspace IDs, map priority labels to the documented integer scalar, and ask about ambiguous matches.
3. Model epics as project issues with the `Epic` label and stories as explicit sub-issues. Set the project on every story rather than assuming inheritance.
4. Confirm the complete effective issue payload and run duplicate detection per issue.
5. Create or update with explicit resolved IDs and approved scalar values for every applicable field. Confirm the target issue before adding comments.
6. Re-read each changed issue and compare its effective metadata with the approved payload. Report its title, identifier, URL, parent/child relationship, and whether it was created, updated, skipped, mismatched, or left pending.

For direct GraphQL, send a JSON `POST` with `Content-Type: application/json`. Use the personal key loaded from `LINEAR_API_KEY` or the configured plaintext file as the raw `Authorization` header value; do not prepend `Bearer`. Treat `templateId` and `useDefaultTemplate` as approval-gated payload fields, and enable template application only after its effective values have been preflighted and approved. Keep small named operations and variables local to the request; never interpolate guessed or stale workspace IDs. Follow `pageInfo.hasNextPage` and `endCursor` until every metadata or duplicate-search connection is complete, and use `includeArchived: true` for duplicate searches.

Treat a non-success HTTP status, any GraphQL `errors`, a false or missing mutation success flag, a missing issue, a failed re-read, or effective metadata that differs from approval as a failed, mismatched, or unverified write. Do not claim success or blindly retry a creation whose outcome is unknown; verify by search and report it as pending until the result is proven. See [publishing workflow](references/publishing-workflow.md) for the readiness and reporting checklist.
