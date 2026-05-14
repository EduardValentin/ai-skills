---
name: manage-bitbucket-pr
description: Use when reading Bitbucket pull request metadata, reading or posting PR comments, or merging Bitbucket pull requests through the REST API; triggers on Bitbucket PR URLs, pull request IDs, workspace/repo PR metadata, comments, or merge operations.
---

# Manage Bitbucket PR

## Overview

Manage essential Bitbucket pull request operations through the REST API with read-before-write discipline. Keep repository-specific workflow decisions outside this skill; this skill owns the Bitbucket PR API mechanics for PR details, comments, and merge operations.

## Preconditions

- Ability to make HTTPS requests from the working environment.
- Bitbucket credentials with the least scopes needed for the requested operation.
- The pull request host type: Bitbucket Cloud or Bitbucket Data Center / Server.
- A PR URL or enough identifiers to resolve one.

Never print, paste, commit, or place credentials in URLs. Read secrets from the user's approved secret store or environment, and redact tokens in every report.

## Host Detection

| Input | Product | API shape |
| --- | --- | --- |
| `https://bitbucket.org/<workspace>/<repo_slug>/pull-requests/<id>` | Bitbucket Cloud | `https://api.bitbucket.org/2.0/repositories/<workspace>/<repo_slug>/pullrequests/<id>` |
| Self-hosted URL with `/projects/<projectKey>/repos/<repoSlug>/pull-requests/<id>` | Bitbucket Data Center / Server | `<baseUrl>/rest/api/latest/projects/<projectKey>/repos/<repoSlug>/pull-requests/<id>` |

For Data Center / Server, verify the instance version and API path from the instance or Atlassian docs before mutating. Cloud and Data Center endpoints are similar concepts but not interchangeable.

## Authentication

Prefer existing project or user-approved credentials. If none are configured, ask the user how they want to authenticate.

For Bitbucket Cloud, API tokens use Basic auth with Atlassian email as username and the API token as password. OAuth 2.0 and access-token flows use `Authorization: Bearer <token>`. App passwords are deprecated; do not recommend creating new ones.

Use endpoint-specific least privilege. Read operations usually need pull-request read scope; posting comments and merging usually need write scope as well. See `references/cloud-pullrequests.md` for the curated endpoint set.

For shell helper templates and the curated Cloud endpoint set, use `references/cloud-pullrequests.md`.

## Read Workflow

1. Parse or confirm `workspace`, `repo_slug`, and `pull_request_id`.
2. Fetch the PR object first.
3. Follow pagination using each response's `next` URL until the required result set is complete.
4. Fetch only the related resources needed for the user's question.
5. Summarize from the API response, naming any unavailable fields or permission failures.

For the curated Bitbucket Cloud PR details and comment endpoints, use `references/cloud-pullrequests.md`.

## Write Workflow

Use read-before-write. Before any mutation, verify:

- Exact PR target.
- Current PR state and destination branch.
- The requested operation and payload.
- Whether the user explicitly asked for that exact side effect.

If any part is vague, draft the intended action and ask for approval. Never merge or post comments based on implication alone.

For the curated Bitbucket Cloud comment and merge endpoints, use `references/cloud-pullrequests.md`. For long-running merges, a `202` response can return a task ID. Poll the merge task status until it reaches success or failure, then report the final state.

## Output

For reads, report the source PR, state, author, source/destination branches, comments requested by the user, and any unavailable fields or permission failures.

For writes, report:

- Operation performed.
- PR URL and ID.
- Payload summary, with sensitive values redacted.
- API result status.
- Any follow-up task, including merge-task polling, unresolved checks, or permission gaps.

## Common Mistakes

| Mistake | Correction |
| --- | --- |
| Treating a Bitbucket web URL as enough to mutate | Parse identifiers, fetch the PR, and verify state first. |
| Using GitHub/GitLab PR commands by habit | Use Bitbucket's REST API shapes and Bitbucket review states. |
| Skipping pagination | Follow `next` until the needed set is complete. |
| Posting a guessed comment or merging by implication | Mutate only after the user requested the exact side effect. |
| Mixing Cloud and Data Center routes | Detect the host type first; verify Data Center paths before writes. |
| Exposing tokens in shell history or output | Use approved secret storage or environment variables and redact reports. |

## Test Prompts

Keep scenarios in `tests/pressure-scenarios.md` and update `tests/test-log.md` whenever the skill changes materially.
