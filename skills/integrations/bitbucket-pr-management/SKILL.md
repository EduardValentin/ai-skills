---
name: bitbucket-pr-management
description: Use when a task involves Bitbucket or a Bitbucket-hosted pull request/repository, including PR URLs, pull request IDs, PR branches, metadata/comments, testing or verifying PR behavior, reviewing changes, writing summaries, comment posting, description updates, or merge requests.
compatibility: >-
  Requires Bash, curl, and Bitbucket Cloud credentials supplied through BITBUCKET_TOKEN or BITBUCKET_EMAIL with BITBUCKET_API_TOKEN. macOS Keychain and git credential fill are optional credential-source fallbacks. Use direct HTTPS when the bundled helper is unavailable; self-hosted Bitbucket requires instance-specific routes.
metadata:
  status: config-required
  allows_tool_references: "true"
---

# Bitbucket PR Management

## Supported Hosts

Use these instructions for Bitbucket Cloud PR URLs such as `https://bitbucket.org/<workspace>/<repo_slug>/pull-requests/<id>`.

For self-hosted Bitbucket URLs, do not reuse Cloud mutation routes. Confirm the instance route pattern before posting comments, updating descriptions, or merging.

## Authentication

Prefer existing approved credentials before asking how to authenticate. Never print, paste, commit, store, place credentials in URLs, or put secrets in command history.

Use this fallback order:

1. Approved local keychain or CLI credentials, including the local `codex-bitbucket-api-token` convention when present. For that keychain item, the working shape may be Basic auth: read the keychain `acct` value as `BITBUCKET_EMAIL` and the `-w` secret as `BITBUCKET_API_TOKEN`. Do not default to treating the `-w` secret as `BITBUCKET_TOKEN`; if Bearer auth returns `401`, retry with the Basic-auth shape before reporting a blocker.
2. Environment auth for the helper: `BITBUCKET_EMAIL` plus `BITBUCKET_API_TOKEN` for app-password Basic auth, or `BITBUCKET_TOKEN` only when it is explicitly available as a Bearer token.
3. Git credential helper for `bitbucket.org`: run `printf 'protocol=https\nhost=bitbucket.org\n\n' | git credential fill`, then use the returned `username` and `password` as Basic auth.

Treat each approved source as a credential candidate. A credential that can read PR metadata may still lack write scope; if a write receives `401` or `403`, try the next approved source before reporting a blocker.

When using the optional local Keychain convention, read the account and secret without printing them, expose them only to one helper invocation as `BITBUCKET_EMAIL` and `BITBUCKET_API_TOKEN`, then discard the shell values. Do not include credential retrieval command substitutions in logs or reusable snippets.

Never echo credential variables, run auth commands under shell tracing, paste token values into chat, place credentials in URLs, or preserve secrets in command output.

## Bitbucket Cloud Helper

Prefer the helper shipped with this skill for Bitbucket Cloud operations. Resolve it relative to the skill directory, not relative to the target repository:

- Preferred helper path: `<skill-dir>/scripts/bitbucket-cloud-pr.sh`.

Run `"$BITBUCKET_PR_HELPER" --help` for supported commands and auth environment variables. Do not assume every Bitbucket target repository has a root-level `scripts/bitbucket-cloud-pr.sh`. If the skill helper is unavailable in the current runtime, use the same Bitbucket Cloud routes with direct HTTPS requests.

For Cloud PR URLs, parse `workspace`, `repo_slug`, and `pull_request_id` first.
For discussion, summary, review, or verification requests, read `pr-details` before `read-comments`; follow `next` pagination until the needed comments are complete. If live calls are blocked, still report the parsed PR identity and blocked helper sequence.

For branch-only requests, derive `workspace` and `repo_slug` from the Bitbucket remote when possible, then run `find-prs-for-branch`. If there is not exactly one clear candidate, ask the user to choose before mutating.

For any write, `pr-details` is the next step before mutation; verify the exact PR, state, destination branch, requested operation, and payload before `post-comment`, `update-description`, or `merge`. For merge requests, include `merge-status` polling in the path; if merge returns a task ID, poll until success or failure.

For comments, follow `next` pagination until the needed data is complete.

## Formatting Rules

Do not nest fenced code blocks inside numbered or bulleted lists. Keep every opening and closing code fence at column 1. When a verification step needs a command block, write the step text as a normal paragraph, not as a numbered or bulleted list item, then start the fenced block on the next line with no indentation.

Prefer this flattened shape: step text paragraph, blank line, code fence at column 1, command lines, closing fence at column 1. Avoid technically valid Markdown that relies on indented fences under list items; Bitbucket can render those fenced blocks badly.

## Common Mistakes

| Mistake | Correction |
| --- | --- |
| Looking for `scripts/bitbucket-cloud-pr.sh` in the target repository | Resolve the helper relative to this skill directory first; fall back to direct HTTPS routes if unavailable. |
| Treating the local `codex-bitbucket-api-token` secret as a Bearer token after `401` | Use the keychain `acct` value plus the `-w` secret as `BITBUCKET_EMAIL` and `BITBUCKET_API_TOKEN` for Basic auth. |
