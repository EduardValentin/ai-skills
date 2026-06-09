---
name: verify-pr-readiness
description: Use when checking whether a ticket-linked PR is ready for mark-ready, merge, or tracker-state sync after review is complete. Covers required PR checks, review-state gating, explicit merge approval, Jira/Linear transitions, and parent ticket readiness. Not for code review.
---

# Verify PR Readiness

## Purpose

Verify PR Readiness decides whether a ticket-linked PR is ready for PR or ticket state changes and performs only explicitly requested, allowed updates.

Use it when the user or an orchestrator asks to check readiness, mark a PR ready, merge an approved PR, or synchronize Jira/Linear ticket state after review.

It receives implementation, review, and verification details as inputs. It does not judge how that work was produced, fix failing work, or delegate fixes.

## Required Inputs

If any required input is missing, return `NOT_READY` and name the missing information.

- PR URL or number, repository, and branch.
- Linked Jira or Linear ticket IDs.
- Current ticket status and intended target status.
- Current PR state, required PR/CI checks, and intended PR action.
- Explicit user approval when merge is requested.
- Parent ticket and sibling/child ticket statuses when the ticket belongs to a hierarchy.

## Readiness Gates

Re-read the PR, checks, and ticket state from their source of truth before any mutation.

The linked ticket must already be in a review state, such as Review, In Review, Code Review, or Ready for Merge. Do not move a ticket directly from In Progress to Done or Closed. If the ticket is still In Progress, return `NOT_READY` and report that the ticket must enter a review state before readiness actions.

Required PR/CI checks must be passing before merge or final tracker movement. Pending, failing, cancelled, missing, or unknown required checks block readiness. If checks block readiness, return `NOT_READY`, list the blocking checks, and do not change the PR or ticket.

Merging requires explicit user approval. Passing checks or prior plan approval is not merge approval.

When blocked, perform no partial PR, branch, tracker, release, or merge mutations.

## Ticket Sync

After the PR action successfully completes, move the linked Jira or Linear ticket to the correct final state using the ticket system's available transition.

If the linked ticket has a parent or Epic, re-read the parent and all child or sibling ticket statuses immediately before any parent transition. Do not update a parent from cached or supplied hierarchy data alone. If no child remains in a non-final state, move the parent to the corresponding final state as well. If any child remains open, in progress, or under review, leave the parent unchanged and report the remaining non-final children.

Record every PR and ticket mutation that was performed.

When asked not to perform external mutations, return `READY` only if the gates pass and list the exact PR, ticket, and parent-ticket mutations that would be performed.

## Report

Return a compact report:

```markdown
# PR readiness report - <ticket or PR>

Status: UPDATED | READY | NOT_READY

PR:
- <url/number/state>
- Required checks: <passing/blocking/not configured/not checked and why>
- Merge: <merged/not merged and why>

Ticket:
- System: <Jira/Linear>
- Ticket: <id/status -> target or unchanged>
- Parent sync: <updated/unchanged/not applicable and why>

Actions:
- <PR and ticket mutations performed, or none>

Blockers:
- <none or concrete blockers>
```
