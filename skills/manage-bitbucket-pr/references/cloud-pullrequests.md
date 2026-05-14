# Bitbucket Cloud Pull Request REST Reference

This is the supported local reference for Bitbucket Cloud PR details, comments, and merge operations. If an operation is missing, treat it as out of scope until the user approves expanding the skill.

Base URL:

```text
https://api.bitbucket.org/2.0
```

## Authentication

API tokens use Basic auth with Atlassian email as username and the API token as password. OAuth 2.0 and access-token flows use `Authorization: Bearer <token>`. App passwords are deprecated.

Use least privilege. These common operations need pull-request read scope for reads and write-capable pull-request scope for comment creation and merge.

## Shell Helpers

Use a local helper pattern so operations are auditable and token handling stays centralized:

```bash
bb_cloud_get() {
  url="$1"
  curl --fail --silent --show-error --location \
    --header "Accept: application/json" \
    --header "Authorization: Bearer ${BITBUCKET_TOKEN}" \
    "$url"
}

bb_cloud_json() {
  method="$1"
  url="$2"
  body="$3"
  curl --fail --silent --show-error --location \
    --request "$method" \
    --header "Accept: application/json" \
    --header "Content-Type: application/json" \
    --header "Authorization: Bearer ${BITBUCKET_TOKEN}" \
    --data "$body" \
    "$url"
}
```

When using an API token instead of a bearer token, replace the authorization header with Basic auth using the Atlassian email and token from approved secret storage.

## Essential Endpoints

| Need | Endpoint |
| --- | --- |
| PR details | `GET /repositories/{workspace}/{repo_slug}/pullrequests/{pull_request_id}` |
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

Bitbucket paginates comments. Follow the `next` URL until the needed comments are complete. For writes, fetch the PR first and verify the current state, destination branch, requested side effect, and payload before mutating.
