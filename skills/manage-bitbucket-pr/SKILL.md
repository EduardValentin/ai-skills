---
name: manage-bitbucket-pr
description: Use when a task involves Bitbucket or a Bitbucket-hosted pull request/repository, including PR URLs, pull request IDs, PR branches, metadata/comments, testing or verifying PR behavior, reviewing changes, writing summaries, comment posting, description updates, or merge requests.
---

# Manage Bitbucket PR

## Supported Hosts

Use these instructions for Bitbucket Cloud PR URLs such as `https://bitbucket.org/<workspace>/<repo_slug>/pull-requests/<id>`.

For self-hosted Bitbucket URLs, do not reuse Cloud mutation routes. Confirm the instance route pattern before posting comments, updating descriptions, or merging.

## Authentication

Prefer existing approved credentials before asking how to authenticate. Never print, paste, commit, store, place credentials in URLs, or put secrets in command history.

Use this fallback order:

1. Approved local keychain or CLI credentials, including the local `codex-bitbucket-api-token` convention when present.
2. Environment auth for the helper: `BITBUCKET_TOKEN`, or `BITBUCKET_EMAIL` plus `BITBUCKET_API_TOKEN`.
3. Git credential helper for `bitbucket.org`: run `printf 'protocol=https\nhost=bitbucket.org\n\n' | git credential fill`.

Treat each approved source as a credential candidate. A credential that can read PR metadata may still lack write scope; if a write receives `401` or `403`, try the next approved source before reporting a blocker.

## Bitbucket Cloud Helper

Prefer `scripts/bitbucket-cloud-pr.sh` for Bitbucket Cloud operations.
Run `scripts/bitbucket-cloud-pr.sh --help` for supported commands and auth environment variables.

For Cloud PR URLs, parse `workspace`, `repo_slug`, and `pull_request_id` first.
For discussion, summary, review, or verification requests, read `pr-details` before `read-comments`; follow `next` pagination until the needed comments are complete. If live calls are blocked, still report the parsed PR identity and blocked helper sequence.

For branch-only requests, derive `workspace` and `repo_slug` from the Bitbucket remote when possible, then run `find-prs-for-branch`. If there is not exactly one clear candidate, ask the user to choose before mutating.

For any write, `pr-details` is the next step before mutation; verify the exact PR, state, destination branch, requested operation, and payload before `post-comment`, `update-description`, or `merge`. For merge requests, include `merge-status` polling in the path; if merge returns a task ID, poll until success or failure.

For comments, follow `next` pagination until the needed data is complete.

## Formatting Rules

Do not nest fenced code blocks inside numbered or bulleted lists. Keep every opening and closing code fence at column 1. When a verification step needs a command block, write the step text as a normal paragraph, not as a numbered or bulleted list item, then start the fenced block on the next line with no indentation.

Prefer this flattened shape: step text paragraph, blank line, code fence at column 1, command lines, closing fence at column 1. Avoid technically valid Markdown that relies on indented fences under list items; Bitbucket can render those fenced blocks badly.
