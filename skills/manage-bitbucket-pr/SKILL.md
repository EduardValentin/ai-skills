---
name: manage-bitbucket-pr
description: Use when reading Bitbucket PR metadata/comments, posting PR comments, or merging Bitbucket PRs through the REST API; triggers on Bitbucket PR URLs, pull request IDs, workspace/repo PR metadata, comments, or merge operations.
---

# Manage Bitbucket PR

## Overview

Manage Bitbucket PR REST operations. Built-in endpoints are limited to PR details, comments, and merge.

## Preconditions

- HTTPS request capability.
- Least-privilege Bitbucket credentials.
- A PR URL or resolvable identifiers.

Never print, paste, commit, or place credentials in URLs. Read secrets from an approved store or environment, and redact tokens in reports.

## Host Detection And Scope

- Cloud PR URL: `https://bitbucket.org/<workspace>/<repo_slug>/pull-requests/<id>`.
- Self-hosted PR URL: usually contains `/projects/<projectKey>/repos/<repoSlug>/pull-requests/<id>`.
- The local reference covers Bitbucket Cloud only. Do not apply Cloud routes to self-hosted Bitbucket. Ask for the instance-specific route pattern or approval to expand scope before mutating.

## Authentication

Prefer existing approved credentials; otherwise ask how to authenticate. For Bitbucket Cloud, API tokens use Basic auth with Atlassian email as username and token as password; OAuth/access-token flows use `Authorization: Bearer <token>`. App passwords are deprecated.

Use read scope for PR details/comments and write scope for posting comments or merging. For supported Cloud operations, prefer `scripts/bitbucket-cloud-pr.sh`; use `--dry-run` to inspect the method, URL, and body before live calls.

## Read Workflow

1. Parse or confirm `workspace`, `repo_slug`, and `pull_request_id`.
2. Run `scripts/bitbucket-cloud-pr.sh pr-details ...` before related reads.
3. For comments, run `scripts/bitbucket-cloud-pr.sh read-comments ...` and follow `next` pagination until complete.
4. Report unavailable fields or permission failures.

## Write Workflow

Use read-before-write. Before any mutation, verify:

- Exact PR target.
- Current PR state and destination branch.
- The requested operation and payload.
- Whether the user explicitly asked for that exact side effect.

If any part is vague, draft the intended action and ask for approval. Never merge or post comments based on implication alone.

For Cloud, use `post-comment`, `merge`, and `merge-status` subcommands. If merge returns a task ID, poll merge task status until success or failure.

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

## Test Prompts

Use `tests/pressure-scenarios.md` and `tests/test-bitbucket-cloud-pr.sh` when changing this skill.
