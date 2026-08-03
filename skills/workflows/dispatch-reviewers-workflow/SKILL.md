---
name: dispatch-reviewers-workflow
description: >-
  Use when the user requests coordinated independent review by both Codex
  and Claude agents before final approval.
compatibility: >-
  Requires fresh-context agent dispatch for Codex 5.6 Sol at High effort
  and Claude Fable 5 at High effort, with access to the complete review target
  and approved requirements. If either exact reviewer, configuration, or
  required evidence is unavailable, block; do not substitute.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Dispatch Reviewers Workflow

Coordinate independent review. Reviewers report findings; the coordinator
evaluates and addresses them.

## When to use

Only use this skill if the user explicitly asks for independent Claude and Codex reviewers.

## Required Reviewers

Each round, dispatch two new, independent, read-only reviewers:

- A Codex reviewer using Codex 5.6 Sol at High effort.
- A Claude reviewer using Opus 5 at High effort.

Never reuse or substitute reviewers. If either cannot return evidence, report
`REVIEW BLOCKED`.

## Workflow

1. Freeze the exact review target and dispatch both reviewers independently.
2. Collect both complete reviews, including findings and an explicit
   `APPROVED` or `CHANGES REQUESTED` verdict.
3. Deduplicate findings and resolve conflicts against the work, evidence,
   approved requirements, and conversation decisions.
4. Accept only technically valid, evidence-supported findings within approved
   scope. Reject invalid, unsupported, duplicate, or scope-expanding findings
   and record the reason.
5. Address every accepted finding and run the relevant verification. If a
   valid fix requires unapproved scope expansion, stop and request approval.
6. After the accepted findings have been addressed, notify both reviewers to
   re-review the latest changes and determine whether their findings have been
   properly addressed.
7. Addressing any findings invalidates any approval received previously.
8. A reviewer who previously gave approval that was invalidated due to
   addressing the findings of the other reviewer needs to re-review the latest
   state of the work and determine whether to keep the initial approval or
   return new findings.
9. Stop with `REVIEW APPROVED` only when both reviewers approve the final state of the work.

Do not exceed 5 rounds. If round five does not produce both approvals, stop
with `REVIEW BLOCKED` and report the remaining findings or capability blockers.
