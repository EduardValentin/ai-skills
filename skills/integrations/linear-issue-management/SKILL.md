---
name: linear-issue-management
description: Use when managing or publishing Linear issues, epics, stories, parent/sub-issue relationships, comments, metadata, duplicate checks, or updates from approved backlog drafts.
compatibility: >-
  Live reads and writes require Linear MCP or macOS Keychain access to the
  generic-password service course-platform.linear-api-key for
  https://api.linear.app/graphql. Without live access, review or format only.
  ticket-writing and feature-work-planning are optional; missing required
  collaborators block publishing.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Linear Issue Management

Manage Linear issues without changing approved product scope. Use Linear MCP
when configured. Only when MCP is unavailable and direct GraphQL will be used,
read [GraphQL fallback](references/graphql-fallback.md) before any live GraphQL
call. If neither route is available, review or format drafts only and report
publication as pending.

## Publication contract

Before any live publication, read the
[publishing workflow](references/publishing-workflow.md). Create or update
nothing until the complete effective payload, including applicable defaults,
is known and approved. Resolve approved names and priority to current Linear
values; reconfirm ambiguity, substitution, fallback, or changed meaning.

Preserve approved descriptions, acceptance criteria, hierarchy, and scope.
Model epics as project issues with the `Epic` label, stories as explicit
sub-issues, and set the project on every story. Run a per-issue duplicate search
that includes closed and archived results. Do not mutate before the user chooses
`skip`, `update`, or `create anyway` for likely overlap.

## Live workflow

1. Fetch viewer and organization context, actor team membership, team defaults,
   and applicable or selected template data.
2. Resolve current teams, projects, users, states, labels, cycles, milestones,
   parents, and approved priority. Ask about ambiguous matches.
3. Present the complete effective payload and every default source for
   approval. Block when an approved result cannot be guaranteed.
4. Run duplicate detection for each proposed creation.
5. Create or update with explicit resolved values.
6. Report its title, identifier, URL, relationship, and outcome.

A missing issue or metadata mismatch is a failed, mismatched,
or unverified write. Never claim success or blindly retry an unknown creation;
verify by search and report it as pending until proven.
