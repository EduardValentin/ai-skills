---
name: ticket-requirements-gathering
description: Use when gathering, clarifying, documenting, and approving requirements and an implementation plan for one standalone implementation ticket.
compatibility: >-
  Requires tracker and repository access and, for a selected architecture plan review, the `inspect-architecture-workflow` skill's `architecture-reviewer` and `architecture-classifier`; a missing agent is replaced by a fresh generic read-only subagent given its prompt, and a missing skill blocks plan approval. Discovery agents are optional. `ticket-workflow` may consume the handoff. Stop only when missing access could materially change scope, behavior, acceptance criteria, or the plan.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Ticket Requirements Gathering

## Scope

Take one standalone implementation ticket through:

`Setup -> Brainstorm -> Spec/design approval -> Plan approval`

Stop after returning the approved requirements handoff. Do not implement,
change ticket state, select an execution mode, or verify PR readiness. Do not
use this skill for related-ticket batches, broad future-work planning, PRD
management, backlog writing, implementation-only work, or PR verification.

Approval is artifact-specific. Agreement with decisions, assumptions, or
recommendations does not approve an unwritten spec/design or plan.

## Resume Rules

Resume after the longest contiguous sequence of fresh checkpoints:

- Setup requires current ticket and repository evidence for every material
  requirements decision.
- Brainstorm requires a record showing that material unknowns are resolved and
  identifying explicitly accepted lower-impact assumptions and open questions.
- Spec/design approval requires the written, presented artifact and its
  explicit approval evidence.
- Plan approval requires the written, presented plan and its separate explicit
  approval evidence.

The Brainstorm record is checkpoint evidence, not approval evidence. Record
approval evidence only for the spec/design and plan.

Refresh ticket and repository state before resuming. Missing, stale, or
contradictory evidence invalidates that checkpoint and every later checkpoint.
Recover from the earliest affected checkpoint without replaying earlier fresh
work.

## Discovery

Keep ownership of repository instructions, the core analysis, user questions,
and approval artifacts. Delegate only broad, independent, read-only discovery
that can return concise locator-backed findings. Inspect inline when agents are
unavailable.

## Setup

1. Confirm the ticket is standalone and intended for implementation. Ask when
   either point is unclear.
2. Read the ticket and any parent Epic/story/ticket for goals, stakeholder
   implications, acceptance criteria, dependencies, constraints, and
   ambiguities.
3. Read repository instructions and the relevant product, design, reference,
   code, and test slices.
4. Inspect repository state, related PRs, and draft work needed to avoid stale
   assumptions.
5. Gather the repository context needed for requirements decisions and
   planning, such as affected files or surfaces, entry points, tests, risks,
   and verification surfaces. Inspect additional areas only when their
   findings could materially change scope, behavior, acceptance criteria,
   dependencies, risks, or verification.
6. Ask the user once which reviewers this ticket runs, covering both the plan
   gate and the implementation review gate, and record the answer as the
   reviewer selection. Present the list with these defaults: selected,
   `code-cleanliness-reviewer`; not selected, `acceptance-criteria-reviewer`,
   `design-system-reviewer`, `security-reviewer`, `performance-reviewer`,
   architecture plan review, and architecture change review (both run
   through the `inspect-architecture-workflow` skill). The user may change any
   default. The selection travels in the handoff and is reused for reruns and
   remediation rounds; it is asked again only when the user asks to change
   it.

If missing access or contradictory evidence could materially change scope,
behavior, acceptance criteria, or the plan, stop at Setup and return the
blocker and required evidence. Otherwise continue and surface lower-impact
gaps during Brainstorm.

## Brainstorm And Spec/Design Approval

Interview the user one question at a time, grounded in the ticket, parent
context, and relevant repository evidence. Resolve unknowns, assumptions,
constraints, edge cases, risks, non-goals, and alternatives that could
materially change implementation.

An unknown is material when it could change user-visible behavior, scope,
acceptance criteria, data or security handling, integrations, rollout or
recovery, or verification. Continue until none remains unresolved. Proceed
with lower-impact unknowns only after the user explicitly accepts them as
assumptions or open questions.

Record resolved material unknowns, agreed decisions, and accepted residual
unknowns. Then write and present a concise spec/design containing scope,
decisions, acceptance criteria, risks, alternatives, assumptions, and open
questions. Obtain explicit approval of that artifact before planning.

## Plan Approval

Write an implementation plan grounded in the approved spec/design, ticket
context, relevant repository evidence, and verification surfaces. Do not edit
product code or tests.

When the reviewer selection includes architecture plan review, invoke the
`inspect-architecture-workflow` skill with `plan-review` before presenting the
plan and follow its flow yourself, with the written plan's path and the
upcoming changes the plan states. The plan need not use architecture
vocabulary: the flow's `architecture-reviewer` turns it into concrete files
and imports, then reviews the plan whenever any judgment rule applies to it,
however small the plan; only a plan that touches no code and changes no
dependency gets no agent, and the result says so. No precheck can skip that
review. The flow prints a verdict, findings with corrections phrased
for the plan, clarification requests where the plan is not concrete enough,
and questions for the user; put the questions to the user.

`OK` passes. When the project has no architecture model, the flow stops
before any review and asks for the baseline flow. Stop at that gate and ask
the user to choose: run `inspect-architecture-workflow` with `baseline` now
and then continue with the plan review, or continue without an architecture
plan review, recorded in the handoff as `architecture review: not run, no
baseline`. Never pass that gate silently, and never create the model on your
own initiative. `SHOULD_CHANGE` or `INCOMPLETE` blocks approval: answer the
clarifications and revise the plan within the revisions the flow allows, or
present a finding to the user, who may accept it with a reason through the
model edit the flow names. Only the user accepts a finding. When the
selection excludes plan review, no architecture plan review runs: record
`architecture plan review: not selected` in the handoff and present the plan
without it.

Present the plan, together with the plan-review return when one exists, and
obtain separate explicit approval of the plan.

Architecture plan review judges structure only. Behavior, scope, and
acceptance criteria remain the user's approval.

## Approved Handoff

After plan approval, return:

- ticket and parent context;
- the prototype-backed decision: whether the repository contains a reference
  prototype app and the ticket implies a user-visible UI change;
- Brainstorm completion record;
- written spec/design and its explicit approval evidence;
- written implementation plan and its separate approval evidence;
- the reviewer selection for both gates;
- architecture plan-review evidence when selected: the printed verdict line,
  `.architecture/findings.json`, the clarification requests, the revisions
  made, and the model edits by which the user accepted findings, with their
  reasons; or `architecture review: not run, no baseline` when the user chose
  to continue without a model; otherwise `architecture plan review: not
  selected`;
- accepted assumptions, remaining open questions, and material risks;
- required verification surfaces.

If blocked, return the fresh completed checkpoints, earliest incomplete
checkpoint, exact missing evidence, and required handoff. Do not attach
approval evidence to Setup, Brainstorm, assumptions, or open questions.

## Change Recovery

A change to scope, behavior, design, or acceptance criteria invalidates the
spec/design and plan approvals. A plan-only change invalidates plan approval.
Return to the earliest affected checkpoint and preserve earlier fresh evidence.
