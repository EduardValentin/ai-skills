---
name: linear-issue-management
description: Use when managing or publishing Linear issues, epics, stories, parent/sub-issue relationships, comments, metadata, duplicate checks, or updates from approved backlog drafts.
compatibility: Live searches and writes require a configured Linear MCP connection or access to https://api.linear.app/graphql with a key supplied through LINEAR_API_KEY or LINEAR_CONFIG_PATH. Without live access, only review and formatting are available. ticket-writing and feature-work-planning are optional collaborators; when either is unavailable, publishing waits for an approved, fully planned draft.
metadata:
  status: config-required
  allows_tool_references: "true"
---

# Linear Issue Management

## Overview

Manage Linear issues without changing approved product scope. Use Linear MCP when it is configured; otherwise use direct GraphQL. Treat every mutation as gated by approved content, resolved workspace metadata, and a per-issue duplicate check.

## Access and collaborators

- For direct GraphQL, read the API key from `LINEAR_API_KEY` or from the config file named by `LINEAR_CONFIG_PATH`. Never print, log, persist, or commit the key; send it only as the authorization value to `https://api.linear.app/graphql`.
- If neither Linear MCP nor direct GraphQL is available, review or format drafts only. Stop before any write and report the pending sequence: metadata lookup, duplicate search, explicit-ID mutation, re-read, then identifier/URL reporting.
- If a draft is missing or unapproved, use `ticket-writing` for refinement when available. Otherwise block publishing and ask for an approved draft.
- If product scope or sequencing is unresolved, use `feature-work-planning` when available. Otherwise refuse to invent scope and ask for a fully planned draft.

## Publishing gates

Create or update nothing until the user approves the exact title, description, parent, project, team, labels, priority, estimate, and any other requested metadata. Preserve approved descriptions, acceptance criteria, and parent/sub-issue scope; ask before changing meaning.

Before each creation, search the target project for overlap in title, scope, description, parent, and status. For every likely duplicate, ask the user to choose `skip`, `update`, or `create anyway`.

## Live workflow

1. Fetch viewer and organization context, then discover the target teams, projects, users, workflow states, labels, and priority values. Resolve names to workspace IDs and ask about ambiguous matches.
2. Model epics as project issues with the `Epic` label and stories as explicit sub-issues. Set the project on every story rather than assuming inheritance.
3. Confirm the complete issue payload and run duplicate detection per issue.
4. Create or update with explicit `teamId`, `projectId`, `stateId`, `assigneeId`, `labelIds`, priority, and parent ID where applicable. Confirm the target issue before adding comments.
5. Re-read each changed issue. Report its title, identifier, URL, parent/child relationship, and whether it was created, updated, skipped, or left pending.

For direct GraphQL, keep small named operations and variables local to the request; never interpolate guessed or pasted workspace IDs. See [publishing workflow](references/publishing-workflow.md) for the detailed readiness and reporting checklist.
