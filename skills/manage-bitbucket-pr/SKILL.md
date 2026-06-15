---
name: manage-bitbucket-pr
description: Use when a task involves Bitbucket or a Bitbucket-hosted pull request/repository, including PR URLs, pull request IDs, PR branches, metadata/comments, testing or verifying PR behavior, reviewing changes, writing summaries, comment posting, description updates, or merge requests.
---

# Manage Bitbucket PR

## Overview

Manage Bitbucket Cloud PR operations for PR details, source-branch lookup, comments, description updates, and merge.

Use this skill whenever the PR or repository is hosted on Bitbucket, even if the immediate task is testing, verification, review, summary, or implementation context-gathering.

## Preconditions

- HTTPS request capability.
- Least-privilege Bitbucket credentials.
- A PR URL or resolvable identifiers.

Never print, paste, commit, store, place credentials in URLs, or put secrets in command history. Keep credentials in memory only and redact tokens in reports.

## Host Detection And Scope

- Cloud PR URL: `https://bitbucket.org/<workspace>/<repo_slug>/pull-requests/<id>`.
- Self-hosted PR URL: usually contains `/projects/<projectKey>/repos/<repoSlug>/pull-requests/<id>`.
- The concrete routes below are Bitbucket Cloud only. Do not apply Cloud routes to self-hosted Bitbucket. Ask for the instance-specific route pattern or approval to expand scope before mutating.

## Authentication

Prefer existing approved credentials before asking how to authenticate. Use this fallback order:

1. Environment auth for the helper: `BITBUCKET_TOKEN` as Bearer auth, or `BITBUCKET_EMAIL` plus `BITBUCKET_API_TOKEN` as Basic auth.
2. Git credential helper for `bitbucket.org`:

   ```bash
   printf 'protocol=https\nhost=bitbucket.org\n\n' | git credential fill
   ```

   Use the returned `username` and `password` as Basic auth for direct HTTPS requests.
3. Approved local keychain or CLI credentials, including the local `codex-bitbucket-api-token` convention when present.

Treat each approved source as a credential candidate. A credential that can read PR metadata may still lack write scope; if a write receives `401` or `403`, try the next approved source before reporting a blocker.

## Bitbucket Cloud Routes

Base URL: `https://api.bitbucket.org/2.0`.

Prefer `scripts/bitbucket-cloud-pr.sh` for supported Cloud operations when its env-var auth path is available. If credentials come from another approved source, use the same routes with direct HTTPS requests.

| Need | Helper command | Route |
| --- | --- | --- |
| PR details | `pr-details` | `GET /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}` |
| Find PRs for source branch | `find-prs-for-branch` | `GET /repositories/{workspace}/{repo_slug}/pullrequests?q=source.branch.name = "{branch}" AND state = "OPEN"` |
| Read comments | `read-comments` | `GET /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}/comments` |
| Post comment | `post-comment` | `POST /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}/comments` with `{"content":{"raw":"..."}}` |
| Update description | `update-description` | `PUT /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}` with `{"description":"..."}` |
| Merge | `merge` | `POST /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}/merge` |
| Merge task status | `merge-status` | `GET /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}/merge/task-status/{task_id}` |

For paginated responses such as comments, follow `next` until the needed data is complete.

## Read Workflow

1. Parse or confirm `workspace`, `repo_slug`, and `pull_request_id`.
2. If the user gives a branch instead of a PR ID, derive `workspace` and `repo_slug` from the Bitbucket remote when possible, then run `scripts/bitbucket-cloud-pr.sh find-prs-for-branch ...`. If there is not exactly one clear candidate, show the candidates and ask the user to choose.
3. Run `scripts/bitbucket-cloud-pr.sh pr-details ...` before related reads or writes.
4. For comments, run `scripts/bitbucket-cloud-pr.sh read-comments ...` and follow `next` pagination until complete.
5. Report unavailable fields or permission failures.

For vague requests such as "this branch" or "the current PR", do not ask for a PR URL as the first response unless local repo/remote context is unavailable. First state that the workflow derives workspace/repo from the Bitbucket remote, looks up PR candidates for the source branch, and asks the user to choose if multiple candidates are found.

For PR testing or verification requests, missing credentials, authentication failure, permission denial, or ambiguous PR lookup must be reported as exact blockers or metadata gaps. Do not silently skip PR metadata gathering.

## Write Workflow

Use read-before-write. Before any mutation, verify:

- Exact PR target.
- Current PR state and destination branch.
- The requested operation and payload.
- Whether the user explicitly asked for that exact side effect.

For branch-only write requests, look up PR candidates first. If there is not exactly one clear candidate, show the candidates and ask the user to choose before mutating.

If any part is vague, draft the intended action and ask for approval. Never merge or post comments based on implication alone.

For Cloud writes, use `post-comment`, `update-description`, `merge`, and `merge-status` when available. If merge returns a task ID, poll merge task status until success or failure.

## Output

For reads, report PR URL/ID, state, author, branches, requested comments, and unavailable fields or permission failures.

For writes, report:

- Operation performed.
- PR URL and ID.
- Payload summary, with sensitive values redacted.
- API result status.
- Any merge-task polling, unresolved checks, or permission gaps.

When a write is requested but blocked before mutation, still state the write-result report contract that will be required after the mutation: operation, PR identity, redacted payload summary, API result, and comment, update, or task identity if available.

For merge requests, include whether Bitbucket returns a merge task and the polled final task state, or the blocker preventing that polling.

## Common Mistakes

| Mistake | Correction |
| --- | --- |
| Treating "this branch" as a PR ID | Look up PR candidates for the source branch, then verify the exact PR before reading or mutating. |
| Skipping PR metadata because Bitbucket integration seems unavailable | Exhaust approved auth/local credential paths before reporting the metadata gap. |
| Posting a guessed comment or merging by implication | Mutate only after the user requested the exact side effect. |
| Applying Cloud routes to self-hosted Bitbucket | Detect host type first; ask before expanding beyond the Cloud route set. |
