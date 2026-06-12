---
name: verify-pr
description: Use when checking PR readiness, immediately after a PR is created or opened for review, before merge, or for post-merge CI verdicts. Verifies source-control PR metadata, CI status, implemented-surface test evidence, review/comment state, and linked Jira or Linear ticket review status through available tooling. Do not use for QA, diff review, PR descriptions, reviewer notes, or testing instructions.
---

# Verify PR

## Purpose

Verify PR validates whether a pull request is ready for the requested next step: review handoff after PR creation, final approval, merge, or post-merge CI monitoring.

Read PR and ticket metadata directly through available tooling such as MCP connectors, REST APIs, CLIs, or authenticated local metadata. Treat user-provided state as a hint unless direct source-of-truth access is unavailable.

## Metadata Resolution

For missing current state, fetch or state this fetch path before a readiness verdict: source-control PR metadata first; linked ticket IDs from the PR metadata, branch, title, or body; ticket status from Jira or Linear; then CI checks, implemented-surface tests, review approvals, and unresolved comments.

If source-of-truth access is blocked, label provided state as unverified. Return `READY` only when complete current source-system output covers every required gate; otherwise return `NOT_READY` with the missing PR, ticket, check, test, review, or comment fields required for the next verdict.

## Inputs

Accept any of these if provided, but fetch missing or stale values yourself when tooling is available:

- PR URL, number, repository, branch, or source-control provider.
- Linked ticket IDs, ticket descriptions, acceptance criteria, and testing instructions.
- Current PR state, CI/check status, review state, unresolved comments, or prior readiness report.
- Requested action: review handoff, final approval check, merge, or after-merge monitoring.

## Readiness Gates

Return `READY` only when all gates needed for the requested action pass.

1. PR metadata is available from the source-control system.
2. The linked Jira or Linear ticket is in a review-state column, such as In Review, Code Review, Ready for Review, or Ready for Merge. If this gate blocks readiness, name the current status and the review-state examples the ticket must move into.
3. Required CI checks are passing. Pending, failing, cancelled, missing, or unknown required checks block readiness.
4. Tests that cover the implemented surface area are passing. Prefer authoritative CI evidence; otherwise run or inspect the relevant project test command and report exactly what covered the changed behavior.
5. The PR has the required review approval for the repository's policy and has no active unresolved review comments, unresolved threads, or requested-changes reviews.

## After-Merge Monitoring

When the user explicitly asks to merge a PR, first re-fetch all readiness gates unless the `READY` verdict was produced from current source-of-truth data in this same verification step. Treat prior `READY` reports as hints, not merge authorization. Confirm the PR is `READY` and the user explicitly approved the merge, then perform the merge through the repository's required source-control write workflow and identity. If that write path or credentials are unavailable, report the blocker instead of merging. After merge, start a background process or subagent to monitor post-merge CI on the merge commit or target branch.

If post-merge CI passes, report the merged PR, monitored checks, and final status.

If post-merge CI fails, fetch the failing check details from the source-control system and report `POST_MERGE_BLOCKED` with the failing job, error summary, affected commit or branch, and a proposed plan of action. The report must include a `Source-control failure details fetched` line, or `Source-control failure details requested` when the fetch is blocked, plus a `Proposed plan` line that names the likely investigation or fix path while leaving implementation for a separate user request.

If monitoring cannot be started because tooling, auth, or provider metadata is unavailable, report `POST_MERGE_MONITORING_BLOCKED` and name the required access.

## Forbidden Behavior

- Returning a final report with `unknown` or `not available` PR state because the prompt omitted current metadata and no fetch was attempted.
- Treating user-provided PR, check, review, comment, or ticket state as authoritative while source-of-truth access is available.
- Asking the user for missing metadata before trying available MCP, API, CLI, connector, or authenticated local metadata access.
- Marking the PR `READY` when required metadata is missing, required CI checks are pending/failing/cancelled/unknown, implemented-surface test evidence is missing or failing, the linked ticket is outside a review-state column, required approval is absent, requested changes are active, or review comments/threads are unresolved.
- Relying on a prior `READY` report alone before merge instead of re-fetching current gates.
- Merging, marking ready, updating tickets, dismissing comments, or performing source-control mutations while any readiness gate is blocked.
- Calling an observed post-merge CI failure "monitoring blocked"; it is `POST_MERGE_BLOCKED`.
- Implementing post-merge CI fixes unless the user asks for follow-up implementation work.

## Report

Return a compact report:

```markdown
# Verify PR report - <PR or ticket>

Status: READY | NOT_READY | MERGED_MONITORING | POST_MERGE_CLEAR | POST_MERGE_BLOCKED | POST_MERGE_MONITORING_BLOCKED

PR:
- Source: <provider/repo/pr>
- State: <open/draft/ready/merged/unknown>
- CI checks: <passing/blocking/not available>
- Implemented-surface tests: <passing/blocking/not available>
- Review state: <approved/review missing/changes requested>
- Unresolved comments: <none/blocking/not available>
- Merge preconditions: <not requested | READY confirmed + explicit approval confirmed | blocking reason>
- Post-merge monitor: <not requested/started/running/passed/failed/blocked>

Ticket:
- System: <Jira/Linear/unknown>
- Linked ticket: <id/status>
- Review-state gate: <passing/blocking/not available>

Actions:
- <metadata fetch required, none, merged, monitoring started, or monitoring blocked>

Blockers:
- <none or concrete blockers with required next input>

Source-control failure details fetched/requested:
- <required only for POST_MERGE_BLOCKED; include fetched check/job/error details or the blocked fetch input needed>

Proposed plan:
- <required only for POST_MERGE_BLOCKED>
```
