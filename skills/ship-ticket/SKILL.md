---
name: ship-ticket
description: Use when a Jira or Linear ticket-linked pull request is ready to ship, merge, mark ready, or sync ticket state after review.
---

# Ship Ticket

## Purpose

Ship Ticket decides whether a ticket-linked PR may be shipped and performs only the allowed PR and ticket state updates.

It receives implementation, review, and verification details as inputs. It does not judge how that work was produced, fix failing work, or delegate fixes.

## Required Inputs

If any required input is missing, return `CANNOT SHIP` and name the missing information.

- PR URL or number, repository, and branch.
- Linked Jira or Linear ticket IDs.
- Current ticket status and intended target status.
- Current PR state, required PR/CI checks, and intended PR action.
- Explicit user approval when merge is requested.
- Parent ticket and sibling/child ticket statuses when the ticket belongs to a hierarchy.

## Shipping Gates

Re-read the PR, checks, and ticket state from their source of truth before any mutation.

The ticket being shipped must already be in a review state, such as Review, In Review, Code Review, or Ready for Merge. Do not move a ticket directly from In Progress to Done or Closed. If the ticket is still In Progress, return `CANNOT SHIP` and report that the ticket must enter a review state before shipping.

Required PR/CI checks must be passing before merge or final shipping. Pending, failing, cancelled, missing, or unknown required checks block shipping. If checks block shipping, return `CANNOT SHIP`, list the blocking checks, and do not change the PR or ticket.

Merging requires explicit user approval. Passing checks or prior plan approval is not merge approval.

When blocked, perform no partial shipping mutations.

## Ticket Sync

After the PR successfully ships or merges, move the linked Jira or Linear ticket to the correct final state using the ticket system's available transition.

If the shipped ticket has a parent or Epic, re-read the parent and all child or sibling ticket statuses immediately before any parent transition. Do not update a parent from cached or supplied hierarchy data alone. If no child remains in a non-final state, move the parent to the corresponding final state as well. If any child remains open, in progress, or under review, leave the parent unchanged and report the remaining non-final children.

Record every PR and ticket mutation that was performed.

When asked not to perform external mutations, return `READY TO SHIP` only if the gates pass and list the exact PR, ticket, and parent-ticket mutations that would be performed.

## Report

Return a compact report:

```markdown
# Ship ticket report - <ticket or PR>

Status: SHIPPED | READY TO SHIP | CANNOT SHIP

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
