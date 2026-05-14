# Bitbucket Cloud Capabilities Reference

This is the supported local reference for Bitbucket Cloud endpoints and payload shapes used by the helper script. If an operation is missing, treat it as out of scope until the user approves expanding the skill.

Base URL:

```text
https://api.bitbucket.org/2.0
```

## Authentication

API tokens use Basic auth with Atlassian email as username and the API token as password. OAuth 2.0 and access-token flows use `Authorization: Bearer <token>`. App passwords are deprecated.

Use least privilege. These common operations need pull-request read scope for reads and write-capable pull-request scope for comment creation and merge.

## Script Usage

Prefer the script over ad hoc curl for supported Cloud operations. It authenticates from `BITBUCKET_TOKEN` or `BITBUCKET_EMAIL` + `BITBUCKET_API_TOKEN` and can also be used as the route/body reference for direct HTTPS calls:

```bash
scripts/bitbucket-cloud-pr.sh pr-details acme widget 42
scripts/bitbucket-cloud-pr.sh find-prs-for-branch acme widget feature/auth
scripts/bitbucket-cloud-pr.sh read-comments acme widget 42
scripts/bitbucket-cloud-pr.sh post-comment acme widget 42 "QA passed on staging"
scripts/bitbucket-cloud-pr.sh merge acme widget 42
scripts/bitbucket-cloud-pr.sh merge-status acme widget 42 task-id
```

Add `--dry-run` before the subcommand to print method, URL, and body without credentials or network calls.

## Essential Endpoints

| Need | Endpoint |
| --- | --- |
| PR details | `GET /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}` |
| Find PRs for source branch | `GET /repositories/{workspace}/{repo_slug}/pullrequests?q=source.branch.name = "{branch}" AND state = "OPEN"` |
| Read comments | `GET /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}/comments` |
| Post comment | `POST /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}/comments` |
| Merge | `POST /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}/merge` |
| Merge task status | `GET /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}/merge/task-status/{task_id}` |

Comment body shape:

```json
{
  "content": {
    "raw": "Comment text"
  }
}
```

Bitbucket paginates comments. Follow the `next` URL until the needed comments are complete. Atlassian documents filtering Bitbucket Cloud 2.0 collections with the `q` query parameter; keep the query URL-encoded in scripts and logs.
