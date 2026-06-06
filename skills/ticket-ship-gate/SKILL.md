---
name: ticket-ship-gate
description: Use when Ship mutations, ticket PR readiness, marking ready, moving ticket state, merging ticket pull requests, per-work-unit readiness ledgers, required GitHub checks, explicit user merge approval, or personal-workflow bot identity are needed after delegated ticket implementation and verification.
---

# Ticket Ship Gate

## Overview

Ship gate owns readiness and release mutations after ticket implementation orchestration says the work is ready to enter Ship.

This skill does not own ticket intake, requirements/design approval, implementation planning, implementation, QA verification, UI/UX verification, or fixing findings. It only decides whether Ship may proceed and performs or withholds PR/ticket/release mutations.

## Required Inputs

Expect a compact Ship packet with:

- workflow type: personal, job, or unknown
- ticket IDs and source-of-truth links
- PR URL/number, branch, and repository
- approved requirements/design artifact
- approved implementation plan
- per-work-unit readiness ledger for every approved plan unit
- QA/UIUX status and unresolved finding status
- explicit user merge approval status when merge is requested
- current PR draft/ready state and intended Ship action

If required inputs are missing or contradictory, return `SHIP BLOCKED` and name the missing input. Do not perform partial Ship mutations.

## Readiness Ledger Gate

Before opening a PR, marking a PR ready, moving a ticket to review/done, merging, closing, or otherwise signaling ready, inspect the per-work-unit readiness ledger from actual completed reports.

Each in-scope work unit must have:

- implementation report
- implementer self-review report
- local tests/checks report or blocker
- QA verification report with clean status
- UI/UX verification report with clean status and inventory validation, or explicit backend-only/non-UI skip rationale
- unresolved QA/UI/UX findings status
- integrated/out-of-scope status for large workflows

Refuse Ship if any readiness ledger row is missing. Local tests, green CI, manual browser checks, source inspection, or the implementer's self-review do not satisfy missing QA or UI/UX verifier reports.

## GitHub Identity Gate

For personal workflow, every GitHub write must use the bot identity described in `ticket-start/bot-identity.md`.

This includes commits, branch pushes, PR creation, PR updates, PR comments, review comments, review-thread replies, labels, issue comments, merges, and direct API mutations. Ambient personal GitHub credentials are not acceptable for writes. If a bot token cannot be minted or the bot lacks permission, halt and draft the intended write instead of using the user's personal GitHub account.

Job workflow follows the repository/team hosting convention, but still records which identity and command performed each mutation.

## PR And Ticket Mutations

- Create or update the PR only after the readiness ledger gate passes.
- Prefer keeping a new personal-workflow PR in draft until required remote checks pass.
- Keep Linear/Jira transitions source-of-truth based: re-read the ticket state before transition, use only the workflow's named next state, and record the result.
- Do not move a personal-workflow Linear ticket to review until required remote checks pass.
- Do not mark any ticket done, closed, or complete before merge/post-merge rules are satisfied.

## Required Remote Checks Gate

After the PR exists and before marking it ready, moving a ticket to review/done, merging, or claiming the unit of work is complete, run:

```bash
gh pr checks <PR> --required --json name,state,bucket,workflow,link
```

Every required check whose `bucket` is not `skipping` must have `bucket == "pass"`.

`pending`, `fail`, `cancel`, missing, or unknown required checks block readiness. A green local test run, green browser check, or one passing workflow does not satisfy this gate if any other required non-skipped check is not green.

If GitHub reports no required checks, record `no-checks-configured` explicitly in the Ship gate report before continuing.

## Merge Approval Gate

User approval is required before merge. Required checks passing, a clean review, or prior approval of requirements/design/plan does not count as merge approval.

If merge is requested without explicit user approval, return `SHIP BLOCKED`, state that approval is missing, and do not merge.

## Ship Gate Report

Return a compact report:

```markdown
# Ship gate report — <ticket or PR>

## Status
- <READY | SHIP BLOCKED | MUTATION COMPLETE>

## Readiness ledger
- <work unit>: implementation report=<present/missing>, self-review=<present/missing>, QA=<clean/missing/finding>, UI/UX=<clean/skipped with rationale/missing/finding>, unresolved findings=<none/list>, integration=<integrated/out-of-scope>

## PR and checks
- PR: <url/number/state>
- Required checks command: `gh pr checks <PR> --required --json name,state,bucket,workflow,link`
- Required checks result: <pass/blocking/no-checks-configured/not run and why>

## Mutations
- PR mutations: <created/updated/marked ready/none and why>
- Ticket mutations: <Linear/Jira transition or none and why>
- Merge: <merged/not merged and why>

## Identity
- GitHub write identity: <bot/job workflow identity/not used>
- Source-of-truth ticket system: <Linear/Jira/not applicable>

## Remaining blockers
- <none or concrete blocker>
```

## Forbidden Behaviors

- Performing any Ship mutation while a readiness ledger row is missing.
- Using ambient personal GitHub credentials for personal-workflow writes.
- Marking ready, moving ticket state, merging, or claiming done before the required remote checks gate passes or records `no-checks-configured`.
- Treating local tests, local review, or CI snippets as replacements for QA/UIUX verifier reports.
- Merging before explicit user approval.
- Moving Linear/Jira tickets without re-reading the source-of-truth state and naming the transition used.
