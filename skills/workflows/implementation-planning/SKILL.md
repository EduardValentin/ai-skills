---
name: implementation-planning
description: Use when writing and approving the implementation plan for one piece of work whose requirements spec is approved.
compatibility: >-
  Requires repository access, plus tracker access when the work has a ticket. Without `requirements-gathering`, return an upstream handoff. A selected architecture plan review requires `inspect-architecture-workflow` and its `architecture-reviewer` and `architecture-classifier`; a missing agent is replaced by a fresh generic read-only subagent given its prompt, and a missing skill blocks plan approval. `development-workflow` may consume the handoff; without it, return the handoff to the user.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Implementation Planning

## Scope

Take one requirements handoff to an approved implementation plan and return
the approved handoff. Do not edit product code or tests, change ticket state,
or select an execution mode.

## Entry

Require the approved requirements spec and its approval evidence. Without
them, return to `requirements-gathering`. When the `UI appearance decision` is
not `none` and no visual spec is supplied, block and name the missing input;
do not dispatch the designer. Refresh repository state, and the ticket when
one exists, before planning.

## Reviewer Selection

Ask the user once which reviewers run, for both the plan gate and the
implementation review gate, and record the answer as the reviewer selection.
Present the list with these defaults: selected, `code-cleanliness-reviewer`;
not selected, `acceptance-criteria-reviewer`, `design-system-reviewer`,
`security-reviewer`, `performance-reviewer`, architecture plan review, and
architecture change review (both run through the
`inspect-architecture-workflow` skill). The user may change any default. Reuse
the selection for reruns and remediations unless the user asks to change it.

## Plan And Plan Approval

Write an implementation plan grounded in the approved requirements spec, the
work and any ticket, relevant repository evidence, and the verification
surfaces. Embed the visual spec verbatim as implementation direction.

When the reviewer selection includes architecture plan review, invoke
`inspect-architecture-workflow` with `plan-review` before presenting the plan
and follow its flow yourself, passing the plan's path and the upcoming changes
it states. The plan need not use architecture vocabulary: the flow's
`architecture-reviewer` turns it into concrete files and imports, then reviews
it whenever any judgment rule applies. Only a plan that touches no code and
changes no dependency gets no agent, and the result says so. No precheck can
skip that review. Put the flow's questions to the user.

`OK` passes. `SHOULD_CHANGE` or `INCOMPLETE` blocks approval: answer the
clarifications and revise the plan within the revisions the flow allows, or
present a finding to the user, who alone may accept it with a reason through
the model edit the flow names.

When the project has no architecture model, the flow stops before any review.
Stop at that gate and ask the user to choose: run
`inspect-architecture-workflow` with `baseline` now and then continue with the
plan review, or continue without an architecture plan review. That choice
removes architecture plan review from this plan gate's selection, so plan
revisions neither re-enter the flow nor ask again. Never pass that gate
silently, and never create the model on your own initiative.

Architecture plan review judges structure only; the user approves behavior,
scope, and acceptance criteria.

Present the written plan and any plan-review return, and obtain separate
explicit approval. Agreement with decisions or recommendations does not
approve an unwritten plan.

## Approved Handoff

After plan approval, return:

- the work, with ticket and parent context when a ticket exists;
- the prototype-backed decision;
- the visual spec and the `UI appearance decision`;
- the Brainstorm completion record;
- the written requirements spec and its explicit approval evidence;
- the written implementation plan and its separate approval evidence;
- the reviewer selection for both gates;
- architecture plan-review evidence when selected: the printed verdict line,
  `.architecture/findings.json`, the clarification requests, the revisions
  made, and the model edits that accepted findings, with reasons; or
  `architecture review: not run, no baseline` when the user chose to continue
  without a model; otherwise `architecture plan review: not selected`;
- accepted assumptions, remaining open questions, material risks, and required
  verification surfaces.

If blocked, return the earliest incomplete checkpoint, exact missing evidence,
and required handoff.

## Change Recovery

A plan-only change invalidates plan approval. A change to scope, behavior, or
acceptance criteria invalidates both approvals and returns to
`requirements-gathering`.
