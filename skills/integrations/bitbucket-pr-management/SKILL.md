---
name: bitbucket-pr-management
description: >-
  Manages and verifies Bitbucket pull requests, including metadata, discussion,
  reviews, summaries, comments, descriptions, and merges. Use for Bitbucket
  pull-request work when a task gives a PR URL or ID, or asks to resolve a PR
  from a branch in a Bitbucket-hosted repository.
compatibility: >-
  Requires Bash, Python 3, and bundled `scripts/bitbucket-cloud-pr.sh` for
  Bitbucket Cloud API calls. Live access requires an approved OAuth 2 token in
  BITBUCKET_TOKEN or an Atlassian email in BITBUCKET_EMAIL with a scoped token
  in BITBUCKET_API_TOKEN. If the helper is unavailable because it is missing,
  unreadable, or inoperable, Cloud API work is blocked. Self-hosted Bitbucket
  requires approved authentication and instance/version-specific API
  documentation or an approved local integration.
metadata:
  status: config-required
  allows_tool_references: "true"
---

# Bitbucket PR Management

## Host Boundaries

Use these instructions for Bitbucket Cloud PR URLs such as `https://bitbucket.org/<workspace>/<repo_slug>/pull-requests/<id>`.

For self-hosted Bitbucket Server or Data Center, never reuse Bitbucket Cloud API routes or the Cloud helper. Establish the route and authentication from official API documentation that matches the instance and version, or from an approved local integration. If neither is available, report the parsed PR identity and the missing evidence; do not invent a universal self-hosted route.

## Authentication

Prefer existing approved credentials before asking how to authenticate. Never print, paste, commit, store, place credentials in URLs, or put secrets in command history.

Use only one of these supported Bitbucket Cloud REST authentication shapes per attempt:

1. Set `BITBUCKET_TOKEN` only for an explicitly approved OAuth 2 access token.
2. Set `BITBUCKET_EMAIL` to the Atlassian account email and `BITBUCKET_API_TOKEN` to the API token bound to that account. This is API-token Basic authentication.

Do not reuse a generic `bitbucket.org` Git credential for REST. Git API-token authentication accepts a Bitbucket username or the static `x-bitbucket-api-token-auth` username, while REST API-token Basic authentication requires the Atlassian account email. If only Git credentials are available, request or locate a separately approved REST credential whose email-token binding is known; never infer the email from a Git username.

API tokens need `read:pullrequest:bitbucket` for PR reads, comment reads, and comment creation. Description updates and merges need both `read:pullrequest:bitbucket` and `write:pullrequest:bitbucket`; API-token scopes do not imply one another. OAuth 2 credentials need the corresponding `pullrequest` scope for reads and comments and `pullrequest:write` for updates and merges.

Treat each separately approved source as a credential candidate. A credential that can read PR metadata may still lack write scope; if a write receives `401` or `403`, try the next approved REST credential before reporting a blocker.

Expose only one credential candidate to each helper invocation. Before a Basic-auth attempt, unset `BITBUCKET_TOKEN`; before an OAuth attempt, unset `BITBUCKET_EMAIL` and `BITBUCKET_API_TOKEN`. This prevents the helper's OAuth-variable preference from silently reusing a failed candidate.

When an approved local credential provider supplies the email-token pair, capture and parse it only inside a non-traced, non-echoing shell scope. Confirm that the account field is the Atlassian account email, pass both values to one helper invocation in memory, and unset them immediately afterward. Do not run credential retrieval as a standalone command or preserve its output.

Never echo credential variables, run auth commands under shell tracing, paste token values into chat, place credentials in URLs, or preserve secrets in command output.

## Bitbucket Cloud Workflow

The helper shipped with this skill is mandatory for every Bitbucket Cloud API call. Resolve it relative to the skill directory, not relative to the target repository:

- Skill-relative helper path: `scripts/bitbucket-cloud-pr.sh`.

Run `"$BITBUCKET_PR_HELPER" --help` for supported commands and auth environment variables. Do not assume every Bitbucket target repository has a root-level `scripts/bitbucket-cloud-pr.sh`. Before exposing credentials or making an API request, require the helper to exist, be readable, and start successfully. If it is missing or unreadable, `--help` fails, or a requested command cannot operate because its bundled runtime is unavailable, stop and report the helper blocker. Do not attempt or propose an API request or mutation through `curl`, `urllib`, `http.client`, or any other ad hoc direct HTTP transport.

For Cloud PR URLs, parse `workspace`, `repo_slug`, and `pull_request_id` first.

Read fresh `pr-details` before grounding any discussion, summary, review, verification, or mutation in a PR. Read comments only when the requested result depends on discussion, review feedback, approval blockers, or comment content. Metadata-only or UI/behavior verification does not require comments unless that context is material. If live calls are blocked, report the parsed identity and blocked operation without inventing PR content.

The helper's `read-comments` command fetches every comments page and returns one JSON object whose `values` contains the combined comments. It parses each response with Python 3 and follows a top-level `next` URL only when it uses HTTPS, the exact `api.bitbucket.org` host and default port, and the same normalized workspace, repository, PR, and comments collection path. It rejects mismatched links before making another request. Use this command for pagination; never scrape `next` from prose, pass an unvalidated URL to the shell, or reproduce the request with another transport.

For branch-only requests, derive `workspace` and `repo_slug` from the Bitbucket remote when possible, then run `find-prs-for-branch`. If there is not exactly one clear candidate, ask the user to choose before mutating.

For any write, `pr-details` is the next step before mutation; verify the exact PR, state, destination branch, requested operation, and payload before `post-comment`, `update-description`, or `merge`. For merge requests, include `merge-status` polling in the path; if merge returns a task ID, treat it as an opaque string, pass the exact identifier to `merge-status`, and poll until success or failure.

Pass `post-comment` and `update-description` payload text only on stdin. Never place comment or description content in the helper's positional arguments. `--dry-run` proves the helper's method, route, and JSON body only. It does not authenticate, read current PR state, or perform a mutation.

## Formatting Rules

Do not nest fenced code blocks inside numbered or bulleted lists. Keep every opening and closing code fence at column 1. When a verification step needs a command block, write the step text as a normal paragraph, not as a numbered or bulleted list item, then start the fenced block on the next line with no indentation.

Prefer this flattened shape: step text paragraph, blank line, code fence at column 1, command lines, closing fence at column 1. Avoid technically valid Markdown that relies on indented fences under list items; Bitbucket can render those fenced blocks badly.

## Common Mistakes

| Mistake | Correction |
| --- | --- |
| Looking for `scripts/bitbucket-cloud-pr.sh` in the target repository | Resolve the helper relative to this skill directory; if it is missing, unreadable, or inoperable, stop before API work. |
| Reusing a Git credential for Cloud REST | Require a separately approved Atlassian-email and API-token binding; do not treat the Git username as the REST identity. |
| Retrying Basic auth while `BITBUCKET_TOKEN` remains set | Expose only the intended candidate and unset variables from every other auth shape. |
| Manually following an unchecked comments `next` link | Use `read-comments`; never fetch it with an alternate transport. |
| Fetching comments for every verification request | Read comments only when discussion or review context is material to the requested result. |
| Reusing Cloud routes for a self-hosted PR | Require matching official instance documentation or an approved local integration; otherwise stop with the route evidence blocker. |
