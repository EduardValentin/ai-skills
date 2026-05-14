---
name: manage-bitbucket-pr
description: Use when reading Bitbucket pull request metadata, reading or posting PR comments, or merging Bitbucket pull requests through the REST API; triggers on Bitbucket PR URLs, pull request IDs, workspace/repo PR metadata, comments, or merge operations.
---

# Manage Bitbucket PR

## Overview

Manage Bitbucket pull request REST operations with read-before-write discipline. Built-in endpoint support is limited to PR details, comments, and merge operations.

## Preconditions

- HTTPS request capability.
- Least-privilege Bitbucket credentials.
- A PR URL or enough identifiers to resolve one.

Never print, paste, commit, or place credentials in URLs. Read secrets from the user's approved secret store or environment, and redact tokens in every report.

## Host Detection And Scope

- Cloud PR URL: `https://bitbucket.org/<workspace>/<repo_slug>/pull-requests/<id>`.
- Self-hosted PR URL: usually contains `/projects/<projectKey>/repos/<repoSlug>/pull-requests/<id>`.
- The local reference covers Bitbucket Cloud only. Do not apply Cloud routes to self-hosted Bitbucket. Ask for the instance-specific route pattern or approval to expand scope before mutating.

## Authentication

Prefer existing project or user-approved credentials; otherwise ask how to authenticate. For Bitbucket Cloud, API tokens use Basic auth with Atlassian email as username and token as password; OAuth/access-token flows use `Authorization: Bearer <token>`. App passwords are deprecated.

Use read scope for PR details/comments and write scope for posting comments or merging. Use `references/cloud-pullrequests.md` for all supported Cloud requests.

## Read Workflow

1. Parse or confirm `workspace`, `repo_slug`, and `pull_request_id`.
2. Fetch PR details first.
3. Fetch only requested comments, following `next` pagination until complete.
4. Report unavailable fields or permission failures.

## Write Workflow

Use read-before-write. Before any mutation, verify:

- Exact PR target.
- Current PR state and destination branch.
- The requested operation and payload.
- Whether the user explicitly asked for that exact side effect.

If any part is vague, draft the intended action and ask for approval. Never merge or post comments based on implication alone.

Use `references/cloud-pullrequests.md` for Cloud comments and merge. If merge returns a task ID, poll merge task status until success or failure.

## Output

For reads, report PR URL/ID, state, author, branches, requested comments, and unavailable fields or permission failures.

For writes, report:

- Operation performed.
- PR URL and ID.
- Payload summary, with sensitive values redacted.
- API result status.
- Any merge-task polling, unresolved checks, or permission gaps.

## Common Mistakes

| Mistake | Correction |
| --- | --- |
| Treating a Bitbucket web URL as enough to mutate | Parse identifiers, fetch the PR, and verify state first. |
| Skipping pagination | Follow `next` until the needed set is complete. |
| Posting a guessed comment or merging by implication | Mutate only after the user requested the exact side effect. |
| Applying Cloud routes to self-hosted Bitbucket | Detect host type first; ask before expanding beyond the Cloud mini-reference. |
| Exposing tokens in shell history or output | Use approved secret storage or environment variables and redact reports. |

## Test Prompts

Use `tests/pressure-scenarios.md` when changing this skill.
