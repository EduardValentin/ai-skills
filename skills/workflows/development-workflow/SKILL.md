---
name: development-workflow
description: Use when coordinating one piece of development work from intake or resuming at an evidenced approved-requirements, implementation-transition, or PR-readiness checkpoint.
compatibility: >-
  Needs repository, PR, and CI access, and tracker access for a ticket. Without `requirements-gathering` or `implementation-planning`, return an upstream handoff; without `implementation-workflow`, work inline only if authorized. Also uses `raising-a-pull-request`, `inspect-architecture-workflow` and its agents, `prototype-backed-workflow`, and `frontend-designer` (absent: a generic subagent given its prompt and `ui-ux-guidelines`). Other gaps block only the affected transition.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Development Workflow

## Scope

Coordinate one piece of development work, with or without a ticket, through requirements intake, implementation transition, and final PR readiness. `requirements-gathering` owns Setup through Requirements spec approval and `implementation-planning` owns Plan approval; invoke them in turn from intake and consume the approved handoff. Detailed implementation, review, QA, UI verification, and fix-loop mechanics belong to the `implementation-workflow` skill.

Do not use this workflow for a related batch of work items. If a fresh approved requirements handoff and execution mode are already established, any ticket is already In Progress, and the request is only to execute, review, verify, and open a PR, invoke `implementation-workflow` directly. This shortcut is not available for work marked prototype-backed.

Mandatory lifecycle:

Setup -> Brainstorm -> Requirements spec approval -> Visual direction -> Plan approval -> Implementation -> Parity step (prototype-backed work) -> PR readiness

Approval is artifact-specific. A user can approve only an artifact they have seen. Agreement with decisions, assumptions, recommendations, investigation progress, or "good to go" does not approve an unwritten requirements spec or implementation plan.

## Session Title

When a chat session starts with this skill, name that session after the work: use the ticket id and title when a ticket exists, for example `ABC-123 Add password reset`, otherwise a short title of the request. If the session started before the work was identified, set the title as soon as intake resolves it. If the session title cannot be set, say so and continue.

## Visual Direction

Skip this stage when the `UI appearance decision` in the requirements handoff is `none`. Otherwise dispatch `frontend-designer`, passing the approved requirements spec, the app URL and start command or page paths, and any inspiration the user supplied:

- `new app or page`: send an `Explore` brief, show the user the mockups, send their pick or mix to the same agent, and receive the visual spec. Where the harness cannot continue an agent, dispatch again with the pick and the mockup paths.
- `changes existing UI`: send a `Decide` brief.

On prototype-backed work the visual spec directs the prototype change. Picking a mockup is not approval; the visual spec is approved with the plan. A change to the visual direction invalidates only the visual spec and plan approval. Pass the visual spec to `implementation-planning`.

## Prototype-Backed Projects

Decide once, at intake, and record the decision in the requirements handoff:
if the repository contains a reference prototype app and the work implies a
user-visible UI change, load `prototype-backed-workflow` and keep it active
for the work. Otherwise do not load it. No later phase re-evaluates this
decision; work whose scope changes to include UI returns to intake.

When it is active, `prototype-backed-workflow` wraps implementation: its
prototype-first rules apply before implementation dispatch, and its parity
step runs after `implementation-workflow` returns complete and before PR
readiness. PR readiness treats the parity ledger as the UI/UX parity evidence.
The parity step is budgeted to one round; a row still not `MATCH` after its
recheck is a PR-readiness blocker for the user to decide, not a reason to
re-run the step.

## Resume Rules

Resume after the longest contiguous sequence of fresh checkpoints established by reliable conversation context, supplied records, or accessible PR evidence and, when a ticket exists, ticket evidence:

- The requirements checkpoint requires one fresh, internally consistent handoff containing the user's request, ticket and parent context when a ticket exists, the prototype-backed decision, the `UI appearance decision`, a Brainstorm completion record, the written requirements spec and its explicit approval evidence, the written implementation plan and its explicit approval evidence, accepted assumptions and open questions, and risks and required verification surfaces.
- The execution-mode checkpoint separately requires that handoff and evidence of the selected or approved mode.
- The execution-authorization checkpoint separately requires the valid handoff, selected mode, and an explicit instruction to execute the approved plan in that mode.
- The ticket-transition checkpoint applies only when a ticket exists and separately requires execution authorization and the completed transition result, including evidence when tracker mutation was excluded.
- PR readiness requires those checkpoints, the current ticket state when a ticket exists, and an implementation report or equivalent changed-scope, test, verification, and PR-or-blocker evidence.

Refresh repository and PR state, and ticket state when a ticket exists, before acting. If a requirements prerequisite is missing, stale, or contradictory, route to its earliest affected checkpoint through `requirements-gathering`, or through `implementation-planning` when only the plan is affected. If a later prerequisite is missing or stale, recover from the earliest missing local checkpoint. Do not assume approval or replay checkpoints whose evidence remains valid.

## Requirements Intake And Validation

At intake, invoke `requirements-gathering`, then `implementation-planning`. If either is unavailable, return an explicit upstream handoff naming the earliest required checkpoint and evidence; do not duplicate or reconstruct their phases.

Before implementation transition, validate the handoff. The Brainstorm record must establish that no material unknown remains unresolved and identify explicitly accepted lower-impact assumptions and open questions. Approval evidence is valid only for the written, presented requirements spec and implementation plan. The handoff must carry the reviewer selection for both gates. A selected architecture review, of the plan or of the diff, follows the `inspect-architecture-workflow` flow, in which an agent reviews the plan or the diff whenever any judgment rule applies to it. Only a diff that touches no code and changes no dependency gets no agent, and the result says so; no precheck can skip the review. An architecture review the user did not select does not run, and the handoff records it as not selected. When a selected architecture review finds no architecture model for the project, it stops at that gate and asks the user to choose: run `inspect-architecture-workflow` with `baseline` now and then continue with the review, or continue without an architecture review. That choice removes the review from its gate's selection for every later round of that gate, so the gate neither re-enters the flow nor asks again, and the handoff records `architecture review: not run, no baseline`. That gate is never passed silently, and the model is never created on the workflow's own initiative. When the reviewer selection includes architecture plan review, the handoff must also carry the plan-review evidence: the printed verdict `OK`, a `SHOULD_CHANGE` or `INCOMPLETE` verdict whose every remaining finding the user accepted through a model edit, or `architecture review: not run, no baseline` when the user chose to continue without a model; otherwise route back to `implementation-planning`. Pass the reviewer selection and the plan-review evidence into the implementation packet so the review gate runs the selected reviewers and the PR carries any model edits the user made to accept a finding.

A change to scope, behavior, or acceptance criteria invalidates the requirements spec and plan approvals and routes to `requirements-gathering`. A plan-only change invalidates plan approval and routes to `implementation-planning`. An execution-mode change stays local and returns only to mode approval.

## Implementation Transition

1. After plan approval, recommend inline, delegated, or hybrid execution based on size, coupling, risk, separability, and implementation context.
2. Ask the user to select or approve the execution mode before dispatch or edits.
3. Treat an explicit instruction to execute the approved plan in the selected mode as execution authorization. Mode approval alone is not execution authorization. When a ticket exists, that instruction also authorizes moving only the associated ticket to the process-appropriate In Progress state; announce and complete that transition before code or test edits, and ask separately if the user or tracker policy excluded tracker mutation. Without a ticket, the instruction alone is the authorization.
4. Invoke `implementation-workflow` with the approved requirements spec and approval evidence, approved plan and approval evidence, accepted assumptions and open questions, execution mode, explicit execution authorization, the request and ticket context when a ticket exists, Brainstorm record, refreshed repository state and ticket state when a ticket exists, ticket-transition outcome when a ticket exists, the visual spec and `UI appearance decision` when the handoff has them, the reviewer selection and architecture plan-review evidence from the handoff, the expected-demand profile (stage, expected users, load and data volumes, reliability expectations), taken from repository instructions or the work's context and confirmed with the user when neither states it, and required verification surfaces.
5. If that skill is unavailable, implement inline only when the user explicitly authorizes the fallback and execution mode. Otherwise return a concrete handoff or access blocker without inventing collaborator results.

Keep implementation within the approved artifacts. A change to scope, behavior, or acceptance criteria invalidates the requirements spec and plan approvals and returns to `requirements-gathering`; a plan-only change invalidates plan approval and returns to `implementation-planning`. An execution-mode change returns only to mode approval here.

## PR Readiness

Refresh the PR, CI, and review state, and ticket state when a ticket exists, after implementation. Determine required evidence from the approved plan, changed scope, repository policy, and actual user-visible risk. Mark evidence not applicable only with a reason. Missing required evidence is a blocker.

Check:

- implementation produced a PR or a concrete blocker explaining why no PR exists
- PR target, title, description, linked ticket when one exists, and changed scope match the approved plan
- implementation, automated test, review, manual QA, UI/UX parity, and blocker evidence is present when applicable
- all PR pipeline checks are green; wait for pending checks
- failed checks are investigated, fixed, and rerun or awaited before readiness
- PR comments and review threads have no unresolved or unaddressed items
- unresolved findings, blockers, assumptions, and follow-ups are explicit
- when a ticket exists, ticket state is appropriate for the user's process

Apply the `raising-a-pull-request` rules to every readiness claim, merge, and post-merge check; they are hard rules, not guidance.

Manual QA evidence applies to user-observable behavior or acceptance flows. UI/UX parity evidence applies to visual changes in a prototype-backed repository and consists of the session's parity ledger with every row at MATCH plus the final parity report; a ledger with any other row state is a blocker. Review evidence applies when the repository or implementation process requires review. Blocker evidence applies whenever a required surface could not be exercised.

Route CI or review fixes back through `implementation-workflow` under the approved scope and execution mode, handing it the fix as a delta over the last reviewed diff so its review gate re-enters at delta scope rather than as a full fan-out. Use the explicitly authorized inline fallback only when that skill is unavailable. If a fix changes scope, behavior, or acceptance criteria, invalidate the requirements spec and plan approvals and return to `requirements-gathering`; if it changes only the plan, invalidate plan approval and return to `implementation-planning`. If it changes execution mode, return only to local mode approval. Refresh evidence and repeat readiness checks after each fix.

If PR, CI, tracker, or required evidence access is unavailable, name the inaccessible surface, the exact evidence still needed, and the handoff required. Do not claim readiness from partial evidence.

Do not merge, complete or close a ticket, dismiss comments, or perform another final source-control or tracker mutation without explicit user approval.

Use this readiness shape:

- PR exists or blocker:
- target, title, description, and linked ticket when one exists:
- changed scope vs approved plan:
- implementation, review, manual QA, UI/UX parity, test, and blocker evidence:
- PR pipeline CI status and fixes:
- provider mergeability and approval policy:
- PR comments and review threads:
- unresolved findings, assumptions, and follow-ups:
- ticket state, when a ticket exists:
- prohibited mutations without approval:

## Final Report

End with the request summary, with the ticket summary when a ticket exists, approved requirements spec summary, approved plan summary, implementation status, PR link or creation blocker, PR-readiness result, the ticket state when a ticket exists, and remaining risks, blockers, assumptions, or follow-ups.

## Stop Conditions

Stop and recover when working from stale repository or PR context, or stale ticket or parent context when a ticket exists; when an approval or resume prerequisite is missing; when the plan cannot guide implementation and verification; when implementation has no PR or blocker evidence; or when a requested mutation lacks its required authorization.
