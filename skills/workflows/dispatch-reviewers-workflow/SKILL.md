---
name: dispatch-reviewers-workflow
description: >-
  Use when the user requests coordinated independent review by both Codex
  and Claude agents before final approval.
compatibility: >-
  Requires fresh-context agent dispatch for Codex and Claude Code agents, with
  access to the complete review target
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

Depending on the review mode:

- Single reviewer : ask the user if it's Claude or Codex.
- Dual reviewers: One Claude Code reviewer and one Codex reviewer.

Each round, dispatch two new, independent, read-only reviewers.
You determine the appropriate model and effort level based on the complexity of 
the work being reviewed.

Never reuse or substitute reviewers. If either cannot return evidence, report
`REVIEW BLOCKED`.

Either Claude or Codex reviewers are dispatched via the installed CLI from the other harness:
- Claude is dispatched via Claude Code CLI from the Codex harness.
- Codex is dispatched via Codex CLI from the Claude Code harness.
- Claude Code dispatching Claude reviewers will use native subagent dispatches.
- Codex dispatching Codex reviewers will use native subagent dispatches.


## Workflow

0. Ask the user what review mode we should use: single or dual reviewers. 
If single review is chosen, ask which agent we should use Codex or Claude Code.
1. Freeze the exact review target and dispatch reviewers based on the review mode independently.
2. Collect complete reviews, including findings and an explicit
   `APPROVED` or `CHANGES REQUESTED` verdict.
3. If more than one reviewer is used, deduplicate findings and resolve conflicts against the work, evidence,
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
