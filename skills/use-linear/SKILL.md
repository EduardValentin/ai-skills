---
name: use-linear
description: Use when managing Linear teams, projects, issues, statuses, assignees, labels, duplicate detection, or comments through the Linear GraphQL API when MCP is unavailable or disabled, especially with the saved macOS Keychain API key.
---

# Use Linear

## Overview

Manage Linear directly through GraphQL when the Linear MCP path is unavailable. Read metadata first, preserve the user's approved ticket scope, and make mutations only with explicit IDs discovered from the target workspace.

## Safety

- Retrieve the API key from macOS Keychain without printing it:
  `security find-generic-password -s course-platform.linear-api-key -a trocaneduard -w`
- When reporting the retrieval plan, name only the Keychain service/account, never the token value.
- Never echo, log, store, or commit the token. Use it only as `Authorization: <token>` for `https://api.linear.app/graphql`.
- Query before mutating. Discover project-specific teams, projects, users, statuses, labels, and priorities instead of hardcoding IDs.
- For mutations, convert resolved names to Linear GraphQL IDs and state the payload uses `teamId`, `projectId`, `stateId`, `assigneeId`, `labelIds`, and priority.
- Run duplicate detection before creating issues. Search existing issues in the target project by title, scope, parent, and status.
- Preserve approved title, description, acceptance criteria, metadata, and parent/sub-issue scope unless the user approves changes.
- After writes, report identifiers, issue URLs, and any skipped duplicates or unresolved metadata.
- If live access is unavailable, stop before mutation but still name the pending sequence: metadata lookup, duplicate search, explicit-ID mutation, re-read, then identifier/URL report.

## Minimal Workflow

1. Load the token into an ephemeral variable, then call Linear GraphQL with `Authorization: <token>`.
2. Fetch `viewer` and organization context, then list relevant teams, projects, users, workflow states/statuses, labels, and priority values.
3. Select target metadata by name/key from the discovered results; ask if there are ambiguous matches.
4. Search existing issues in the target project before creation, including closed or archived candidates when relevant.
5. Create or update issues with explicit `teamId`, `projectId`, `stateId`, `assigneeId`, `labelIds`, and priority. Add comments through GraphQL only after confirming the target issue.
6. Re-read the changed issue or project after mutation and summarize the final Linear identifier and URL.

Keep GraphQL documents local to the current request. Prefer small, named operations and variables over pasted IDs or ad hoc string interpolation.
