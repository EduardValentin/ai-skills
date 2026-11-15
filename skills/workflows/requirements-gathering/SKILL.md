---
name: requirements-gathering
description: Use when gathering, clarifying, documenting, and approving the requirements spec for one piece of work, whether or not it comes with a ticket.
compatibility: >-
  Requires repository access, and tracker access only when the work has a ticket. Discovery agents are optional; without them, inspect inline. `development-workflow` and `implementation-planning` may consume the handoff; without them, return it to the user. Stop only when missing access could materially change scope, behavior, or acceptance criteria.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Requirements Gathering

## Scope

Take one piece of work, not a batch, through:

`Setup -> Brainstorm -> Requirements spec approval`

The work is the user's request, and a ticket is optional. Stop after returning
the requirements handoff. Do not plan, implement, change ticket state, select
an execution mode, or verify PR readiness. Do not use this skill for broad future-work planning,
PRD management, backlog writing, implementation-only work, or PR verification.

Approval is artifact-specific. Agreement with decisions, assumptions, or
recommendations does not approve an unwritten requirements spec.

## Resume Rules

Resume after the longest contiguous sequence of fresh checkpoints:

- Setup requires current request, ticket, and repository evidence for every
  material requirements decision.
- Brainstorm requires a record showing that material unknowns are resolved and
  naming the lower-impact assumptions and open questions the user explicitly
  accepted.
- Requirements spec approval requires the written, presented spec and its
  explicit approval evidence.

The Brainstorm record is checkpoint evidence, not approval evidence. Refresh
ticket and repository state before resuming. Missing, stale, or contradictory
evidence invalidates that checkpoint and every later one. Recover from the
earliest affected checkpoint without replaying earlier fresh work.

## Discovery

Keep ownership of repository instructions, the core analysis, user questions,
and approval artifacts. Delegate only broad, independent, read-only discovery
that can return concise locator-backed findings.

## Setup

1. Confirm the work is one standalone piece intended for implementation. Ask
   when either point is unclear.
2. Read the request, and the ticket and any parent Epic, story, or ticket when
   one exists, for goals, stakeholder implications, acceptance criteria,
   dependencies, constraints, and ambiguities.
3. Read repository instructions and the relevant product, design, reference,
   code, and test slices.
4. Inspect repository state, related PRs, and draft work needed to avoid stale
   assumptions.
5. Gather the repository context needed for requirements decisions and later
   planning, such as affected files or surfaces, entry points, tests, risks,
   and verification surfaces. Inspect additional areas only when their
   findings could materially change scope, behavior, acceptance criteria,
   dependencies, risks, or verification.

If missing access or contradictory evidence could materially change scope,
behavior, or acceptance criteria, stop at Setup and return the blocker and
required evidence. Otherwise continue and surface lower-impact gaps during
Brainstorm.

## Brainstorm And Requirements Spec Approval

Interview the user one question at a time, grounded in the request, any ticket
context, and relevant repository evidence. Resolve unknowns, assumptions, constraints, edge cases, risks, non-goals, and
alternatives that could materially change implementation.

An unknown is material when it could change user-visible behavior, scope,
acceptance criteria, data or security handling, integrations, rollout or
recovery, or verification. Continue until none remains unresolved. Proceed
with lower-impact unknowns only after the user explicitly accepts them as
assumptions or open questions.

Record resolved material unknowns, agreed decisions, and accepted residual
unknowns. Then write and present a concise requirements spec containing scope,
decisions, acceptance criteria, risks, alternatives, assumptions, and open
questions. Obtain explicit approval of that artifact.

## Requirements Handoff

After requirements spec approval, return:

- the work, with ticket and parent context when a ticket exists;
- the prototype-backed decision: whether the repository contains a reference
  prototype app and the work implies a user-visible UI change;
- the Brainstorm completion record;
- the written requirements spec and its explicit approval evidence;
- accepted assumptions, remaining open questions, and material risks;
- required verification surfaces.

If blocked, return the fresh completed checkpoints, earliest incomplete
checkpoint, exact missing evidence, and required handoff. Do not attach
approval evidence to Setup, Brainstorm, assumptions, or open questions.

## Change Recovery

A change to scope, behavior, or acceptance criteria invalidates the
requirements spec approval. Return to the earliest affected checkpoint and
preserve earlier fresh evidence.
