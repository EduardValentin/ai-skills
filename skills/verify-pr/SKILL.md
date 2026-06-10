---
name: verify-pr
description: Use when checking whether a pull request is ready for human review, final approval, merge, or post-merge CI monitoring. Verifies source-control PR metadata, CI status, implemented-surface test evidence, review/comment state, and linked Jira or Linear ticket review status through available tooling.
---

# Verify PR

## Purpose

Verify PR validates whether a pull request is ready for the requested next step: review handoff, final approval, merge, or after-merge monitoring.

Read PR and ticket metadata directly through available tooling such as MCP connectors, REST APIs, CLIs, or authenticated local metadata. Treat user-provided state as a hint unless direct source-of-truth access is unavailable.

Do not return a final report with unknown PR state just because the prompt omitted current metadata. First fetch, or in a dry-run/no-tools context state the required fetch sequence: PR metadata, linked ticket IDs and status, CI checks, implemented-surface test evidence, review approval, and unresolved comments. A report with `unknown` or `not available` fields is valid only after the fetch was actually attempted and blocked. Ask the user for missing details only when the available tooling cannot fetch the required metadata; then return `NOT_READY` with the required next input.

For missing current state, spell out this fetch path: source-control PR metadata first; linked ticket IDs from the PR metadata, branch, title, or body; ticket status from Jira or Linear; then CI checks, implemented-surface tests, review approvals, and unresolved comments. Include the fallback sentence that if tooling, API, CLI, auth, or connector access is blocked, the user must provide the missing PR/ticket/check/review details.

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

Do not merge, mark ready, update tickets, dismiss comments, or perform source-control mutations while any gate is blocked.

## After-Merge Monitoring

When the user explicitly asks to merge a PR, first confirm the PR is already `READY` and that the user explicitly approved the merge. Record both preconditions in the report. Then perform the merge through the source-control system and start a background process or subagent to monitor post-merge CI on the merge commit or target branch.

If post-merge CI passes, report the merged PR, monitored checks, and final status.

If post-merge CI fails, fetch the failing check details from the source-control system and report `POST_MERGE_BLOCKED` with the failing job, error summary, affected commit or branch, and a proposed plan of action. A failing observed check means monitoring ran and found a failure; do not call that "monitoring blocked." Do not implement the fix unless the user asks for follow-up work.

If monitoring cannot be started because tooling, auth, or provider metadata is unavailable, report that monitoring is blocked and name the required access.

## Report

Return a compact report:

```markdown
# Verify PR report - <PR or ticket>

Status: READY | NOT_READY | MERGED_MONITORING | POST_MERGE_CLEAR | POST_MERGE_BLOCKED

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
```
