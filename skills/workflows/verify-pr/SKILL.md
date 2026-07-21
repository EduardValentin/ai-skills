---
name: verify-pr
description: Use when checking whether a pull request is ready for review handoff or merge, executing an explicitly approved merge after a fresh readiness check, or monitoring CI after merge. Do not use for diff review, QA, PR copy, reviewer notes, or test-plan writing.
compatibility: >-
  Requires source-control read access and authoritative CI or test evidence; Jira or Linear access when a ticket gate applies; an approved write identity for an explicitly requested merge; and a durable background process or native agent for monitoring. Missing gate evidence yields NOT_READY, missing merge access blocks mutation, and missing durable monitoring yields POST_MERGE_MONITORING_BLOCKED.
metadata:
  status: local-required
  allows_tool_references: "true"
---

# Verify PR

## Purpose

Determine whether a pull request is ready for the requested next action: review handoff, final readiness, merge, or post-merge CI monitoring. Use current source-system evidence and make no mutation beyond an explicitly approved merge.

## Select the Action

Choose one action before applying gates:

- **Review handoff**: decide whether an open PR is ready to request review.
- **Final readiness**: decide whether a reviewed PR is ready to merge, without merging it.
- **Merge**: re-check readiness, perform an explicitly approved merge, and start monitoring.
- **Post-merge monitoring**: monitor an already-merged PR's merge commit or target branch.

If the request is ambiguous, perform the least-mutating applicable readiness check. Never infer approval to merge.

## Resolve Current Evidence

Use available MCP connectors, provider APIs, CLIs, or authenticated local metadata. Treat user-provided state and earlier reports as hints whenever direct source access is available.

Resolve evidence in this order:

1. Fetch PR identity, lifecycle state, base branch, current provider-reported mergeability or conflict status, merge policy, and linked ticket IDs from source control.
2. Resolve applicable repository rules, branch protection, required checks, approval count, and code-owner requirements.
3. Fetch every applicable Jira or Linear ticket and its current project status.
4. Fetch required CI, implemented-surface test evidence, approvals, requested-changes reviews, and unresolved threads.

Attempt available reads before asking the user to transcribe metadata. If an applicable source cannot be read, identify the attempted source and mark that gate unverified. An unverified required gate blocks `READY`.

## Action Gate Matrix

| Gate | Review handoff | Final readiness | Merge | Post-merge monitoring |
|---|---|---|---|---|
| PR lifecycle | Open and reviewable; draft only if repository policy permits draft handoff | Open and non-draft | Freshly confirmed open and non-draft | Merged, with merge commit or target branch identified |
| Provider mergeability and conflicts | Not applicable | Current result confirms mergeable and conflict-free | Fresh result confirms mergeable and conflict-free | Not applicable |
| Required pre-merge CI | Passing | Passing | Freshly passing | Not applicable |
| Implemented-surface tests | Passing evidence | Passing evidence | Fresh passing evidence | Not applicable |
| Ticket review-state gate | Passing when applicable | Passing when applicable | Freshly passing when applicable | Not applicable |
| Required approvals | Not required | Repository policy satisfied | Freshly satisfied | Not applicable |
| Review blockers | No active requested-changes review or unresolved thread | None active | Freshly none active | Not applicable |
| Merge authorization and write access | Not applicable | Not applicable | Explicit user approval and approved write identity | Not applicable |
| Durable CI monitor | Not applicable | Not applicable | Start after merge | Required |

Pending, failing, cancelled, missing, or unknown required checks block readiness. Implemented-surface evidence must cover the changed user-visible or public behavior; a generic green build does not substitute for missing relevant test evidence.

### Ticket Rules

The ticket gate applies when repository or project policy requires a linked ticket, or when the PR links a Jira or Linear ticket. No linked ticket is acceptable only when no policy requires one. A required but missing ticket blocks readiness.

For multiple linked tickets, evaluate every ticket in scope for the change. If scope is ambiguous, report the ambiguity as a blocker instead of choosing one silently. Repository or project workflow configuration is authoritative for accepted review states. Names such as `In Review`, `Code Review`, `Ready for Review`, and `Ready for Merge` are fallbacks only when no configured mapping is available; an ambiguous status blocks the gate.

### PR And Approval Rules

A draft blocks final readiness and merge, and blocks review handoff unless repository policy explicitly permits draft handoff. A closed unmerged PR blocks every pre-merge action. An already-merged PR is not `READY` for a pre-merge action; use the post-merge workflow only when requested. Unknown lifecycle state blocks readiness.

For final readiness and merge, require a current provider-reported mergeability or conflict result that positively confirms the PR is mergeable and conflict-free. A conflicting, blocked, unknown, unavailable, or still-calculating result blocks readiness. Do not infer mergeability from passing checks or any other green gate.

For actions requiring approval, discover the effective policy from source-control rulesets, branch protection, code-owner requirements, or equivalent repository configuration. If the required approval policy cannot be determined, report it as missing gate evidence.

## Merge And Monitoring

Before a merge, re-fetch every applicable gate in the same verification step. A prior `READY` verdict is neither current evidence nor merge authorization. Merge only after all fresh gates pass and the user explicitly approves the merge through the repository's required write workflow and identity.

After merge, start a durable background process or native agent against the exact merge commit or target branch. Successful start evidence includes a stable owner or monitor ID, the monitored target, the checks being watched, and a continuation path for a later result. A command invocation without that evidence does not prove monitoring started.

- Return `MERGED_MONITORING` when the monitor is proven running but has no final result yet.
- The monitor owner returns `POST_MERGE_CLEAR` when the watched checks pass.
- Return `POST_MERGE_BLOCKED` when a watched check fails. Fetch source-control failure details and include the failing job, error summary, affected commit or branch, and a proposed investigation path without implementing a fix.
- Return `POST_MERGE_MONITORING_BLOCKED` when durable monitoring cannot be started, and name the missing access or collaborator.

When the final CI result is available in the same operation, return the final post-merge status directly rather than an intermediate `MERGED_MONITORING` status.

## Safety Boundaries

- Do not return `READY` with any required gate missing, stale, failing, pending, ambiguous, or unverified.
- Do not merge when the current provider mergeability or conflict result fails to positively confirm that the PR is mergeable and conflict-free.
- Do not ask for metadata before attempting available source-of-truth reads.
- Do not treat user-provided state or a prior report as authoritative when a current read is available.
- Do not merge, update tickets, dismiss reviews, resolve comments, or make other source mutations while a gate is blocked.
- Do not merge without explicit user approval, even when every readiness gate passes.
- Do not call an observed post-merge failure a monitoring failure; it is `POST_MERGE_BLOCKED`.
- Do not implement a post-merge CI fix unless the user separately requests implementation.

## Report

Return a compact report:

```markdown
# Verify PR report - <PR or ticket>

Status: READY | NOT_READY | MERGED_MONITORING | POST_MERGE_CLEAR | POST_MERGE_BLOCKED | POST_MERGE_MONITORING_BLOCKED
Action: <review handoff | final readiness | merge | post-merge monitoring>

PR:
- Source: <provider/repository/PR>
- State: <current lifecycle state and evidence source>
- Mergeability: <current provider result and evidence source or concrete blocker>
- Gate policy: <ruleset, branch protection, repository policy, or attempted but unavailable>
- CI checks: <passing or concrete blockers>
- Implemented-surface tests: <passing evidence or concrete blockers>
- Review state: <approval result and active review blockers>

Ticket:
- Requirement: <not applicable | required by policy | linked by PR>
- Linked tickets: <IDs, statuses, and gate results>

Merge and monitoring:
- Merge preconditions: <not requested | fresh gates and approval confirmed | blocker>
- Monitor evidence: <not requested | owner/ID, target, checks, and state | blocker>

Actions:
- <reads performed, merge performed, monitor started, or none>

Blockers:
- <none or concrete blockers and required next evidence>

Source-control failure details fetched/requested:
- <required only for POST_MERGE_BLOCKED>

Proposed plan:
- <required only for POST_MERGE_BLOCKED>
```
