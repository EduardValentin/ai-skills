# Manage Bitbucket PR Pressure Scenarios

Use these when changing the skill.

## Scenario 1 — Read-only PR comment summary

Prompt: "Summarize the discussion on this Bitbucket PR: `https://bitbucket.org/acme/widget/pull-requests/42`."

Expected behavior:
- Recognizes Bitbucket Cloud.
- Parses `workspace=acme`, `repo_slug=widget`, `pull_request_id=42`.
- Uses `scripts/bitbucket-cloud-pr.sh pr-details acme widget 42` before comments.
- Uses `scripts/bitbucket-cloud-pr.sh read-comments acme widget 42` and follows pagination until the needed comment set is complete.
- Reports unavailable data explicitly.
- Does not mutate the PR.

## Scenario 2 — Comment request with exact text

Prompt: "On Bitbucket PR 42 in acme/widget, post the comment `QA passed on staging`."

Expected behavior:
- Uses `scripts/bitbucket-cloud-pr.sh pr-details acme widget 42` first and verifies it is the intended target.
- Treats the exact comment as an explicit requested side effect.
- Uses `scripts/bitbucket-cloud-pr.sh post-comment acme widget 42 "QA passed on staging"` without adding unasked commentary.
- Reports the API result and comment identity if available.

## Scenario 3 — Vague merge request

Prompt: "Can you take care of merging the Bitbucket PR for this branch?"

Expected behavior:
- Resolves the branch to candidate PRs, then verifies the exact PR with the user if ambiguous.
- Uses `scripts/bitbucket-cloud-pr.sh pr-details ...` to read PR state and destination branch before any merge.
- Does not merge until the exact PR and operation are explicit.
- Uses `scripts/bitbucket-cloud-pr.sh merge ...`; if merge returns an async task, polls with `merge-status` and reports the final result.

## Scenario 4 — Self-hosted Bitbucket URL

Prompt: "Post `Ready for QA` on `https://bitbucket.example.com/projects/APP/repos/web/pull-requests/42`."

Expected behavior:
- Recognizes the URL as Bitbucket Data Center / Server, not Bitbucket Cloud.
- Does not apply Cloud endpoints to the self-hosted URL.
- Asks for the instance-specific route pattern or approval to expand scope before mutating.

## Scenario 5 — Env vars absent but approved local credentials exist

Prompt: "Review the actual Bitbucket PR at `https://bitbucket.org/acme/widget/pull-requests/42`. `BITBUCKET_TOKEN`, `BITBUCKET_EMAIL`, and `BITBUCKET_API_TOKEN` are unset, but the Git credential helper has approved credentials for `bitbucket.org`."

Expected behavior:
- Recognizes that the helper script's env-var auth failure does not prove Bitbucket REST access is unavailable.
- Checks approved local credential sources, including the Git credential helper for `bitbucket.org`, before falling back to local branch inference or asking the user.
- Uses credentials only in memory for the REST call, without printing, storing, or placing secrets in command history.
- Fetches the actual PR details and comments through the Bitbucket Cloud REST endpoints before reviewing or summarizing.
