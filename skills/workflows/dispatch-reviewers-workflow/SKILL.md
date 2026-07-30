---
name: dispatch-reviewers-workflow
description: >-
  Use when completed work needs coordinated independent review by both Codex
  and Claude agents before final approval.
compatibility: >-
  Requires fresh-context agent dispatch for Codex 5.6 Sol at Extra High effort
  and Claude Fable 5 at xHigh effort, with access to the complete review target
  and approved requirements. If either exact reviewer, configuration, or
  required evidence is unavailable, block; do not substitute.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Dispatch Reviewers Workflow

Coordinate independent review. Reviewers report findings; the coordinator
evaluates and addresses them.

## Required Reviewers

Each round, dispatch two new, independent, read-only reviewers:

- A Codex reviewer using Codex 5.6 Sol at Extra High effort.
- A Claude reviewer using Fable 5 at xHigh effort.

Never reuse or substitute reviewers. If either cannot return evidence, report
`REVIEW BLOCKED`.

## Review Context

Give both reviewers the same neutral packet:

- the work under review and its repository context;
- the goal, requirements, acceptance criteria, and non-goals;
- the ticket or user-story link or, if unavailable, its description;
- approved specifications, designs, plans, or handoffs;
- relevant decisions from the conversation history;
- any scope expansion approved outside the original requirements;
- applicable repository instructions, risks, and verification evidence.

Do not reveal any same-round or prior-round reviewer findings or verdicts,
expected conclusions, suspected defects, or the coordinator's preferred
outcome. Missing material context blocks the round.

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
6. If same-target dual approval is absent, dispatch two new independent
   reviewers against the current complete work. Any change invalidates both
   prior approvals.
7. Stop with `REVIEW APPROVED` only when both reviewers approve the same exact
   target in the same round.

Do not exceed ten rounds. If round ten does not produce both approvals, stop
with `REVIEW BLOCKED` and report the remaining findings or capability blockers.

## Scope and Code Quality

Reviewers pursue the minimal implementation that satisfies the approved goal.
The most important constraint is staying within approved scope; findings must
not expand it.

When the work contains code, both reviewers must check for:

- efficient, maintainable, readable code;
- clean and simple architecture without overengineering;
- no dead code;
- compliance with the approved requirements and scope;
- simplifications that preserve correctness, scalability, performance, and
  maintainability.

## Report

Return a small, concise report with:

- rounds completed and each final reviewer verdict;
- a high-level overview of changes caused by valid findings;
- material rejected findings or resolved conflicts;
- unresolved findings or blockers when approval was not achieved.
