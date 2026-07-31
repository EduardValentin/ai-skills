---
name: self-review
description: >-
  Use when you need to dispatch an agent to review your work.
compatibility: Requires the ability to dispatch independent agents with fresh context.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Self Review

Give these guidelines to an independent agent with fresh context to review your work.

## Review Context

Give the reviewer the following packet:

- the work under review and its repository context;
- the goal, requirements, acceptance criteria, and non-goals;
- if working with a ticket or user story, its link or, if unavailable, its description;
- approved specifications, designs, plans, or handoffs;
- relevant decisions from the conversation history;
- any scope expansion approved outside the original requirements;
- applicable repository instructions, risks, and verification evidence.

Do not reveal your own findings or verdicts, expected conclusions,
suspected defects, or the coordinator's preferred outcome. Missing material
context blocks the round.

## Scope and Code Quality

Reviewers pursue the minimal implementation that satisfies the approved goal.
The most important constraint is staying within approved scope; findings must
not expand it.

When the work contains code, the reviewer must check for:

- efficient, maintainable, readable code;
- clean and simple architecture without overengineering;
- no dead code;
- compliance with the approved requirements and scope;
- simplifications that preserve correctness, scalability, performance, and
  maintainability.

## Report

Return a small, concise report with:

- rounds completed and each reviewer's final verdict;
- a high-level overview of changes caused by valid findings;
- material rejected findings or resolved conflicts.
