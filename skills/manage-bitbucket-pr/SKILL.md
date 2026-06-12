---
name: manage-bitbucket-pr
description: Use when a task involves Bitbucket or a Bitbucket-hosted pull request/repository, including PR URLs, pull request IDs, PR branches, metadata/comments, testing or verifying PR behavior, reviewing changes, writing summaries, comment posting, or merge requests.
---

# Manage Bitbucket PR

## Overview

Manage Bitbucket PR operations for PR details, source-branch lookup, comments, and merge.

Use this skill whenever the PR or repository is hosted on Bitbucket, even if the immediate task is testing, verification, review, summary, or implementation context-gathering.

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

Prefer existing approved credentials before asking how to authenticate. Check environment variables, the Git credential helper for `bitbucket.org`, and approved company CLI/keychain flows before concluding Bitbucket auth is unavailable.

For supported Cloud operations, prefer `scripts/bitbucket-cloud-pr.sh` when its env-var auth path is available. If credentials exist through another approved source, use the documented endpoints through a direct HTTPS request instead of abandoning the PR lookup. See `references/cloud-capabilities-reference.md` for auth mechanics, scopes, endpoints, and payload shapes.

## Read Workflow

1. Parse or confirm `workspace`, `repo_slug`, and `pull_request_id`.
2. If the user gives a branch instead of a PR ID, derive `workspace` and `repo_slug` from the Bitbucket remote when possible, then run `scripts/bitbucket-cloud-pr.sh find-prs-for-branch ...`. If there is not exactly one clear candidate, show the candidates and ask the user to choose.
3. Run `scripts/bitbucket-cloud-pr.sh pr-details ...` before related reads or writes.
4. For comments, run `scripts/bitbucket-cloud-pr.sh read-comments ...` and follow `next` pagination until complete.
5. Report unavailable fields or permission failures.

## Write Workflow

Use read-before-write. Before any mutation, verify:

- Exact PR target.
- Current PR state and destination branch.
- The requested operation and payload.
- Whether the user explicitly asked for that exact side effect.

If any part is vague, draft the intended action and ask for approval. Never merge or post comments based on implication alone.

For Cloud, use `find-prs-for-branch`, `post-comment`, `merge`, and `merge-status` subcommands. If merge returns a task ID, poll merge task status until success or failure.

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
| Treating "this branch" as a PR ID | Look up PR candidates for the source branch, then verify the exact PR before reading or mutating. |
| Skipping PR metadata because Bitbucket integration seems unavailable | Exhaust approved auth/local credential paths before reporting the metadata gap. |
| Posting a guessed comment or merging by implication | Mutate only after the user requested the exact side effect. |
| Applying Cloud routes to self-hosted Bitbucket | Detect host type first; ask before expanding beyond the Cloud mini-reference. |

## Test Coverage

Use the repo-level `tests/manage-bitbucket-pr/manage_bitbucket_pr_behavioral_pressure.py`
for behavioral pressure coverage and `tests/test-bitbucket-cloud-pr.sh` for helper-script contracts.
