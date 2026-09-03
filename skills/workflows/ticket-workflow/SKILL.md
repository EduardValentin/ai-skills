---
name: ticket-workflow
description: Use when coordinating one standalone implementation ticket from intake or resuming at an evidenced approved-requirements, implementation-transition, or PR-readiness checkpoint.
compatibility: >-
  Requires repository, ticket-tracker, PR, and CI access plus the `ticket-requirements-gathering` and `implementation-workflow` skills, and `prototype-backed-workflow` for visual tickets in prototype-backed repositories. If requirements gathering is unavailable, return an explicit upstream handoff. If implementation is unavailable, implement inline only with explicit fallback authorization. Missing tracker, PR, CI, or evidence access blocks only the affected transition or readiness claim.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Ticket Workflow

## Scope

Coordinate one standalone ticket through requirements intake, implementation transition, and final PR readiness. `ticket-requirements-gathering` owns Setup through Plan approval; invoke it from intake and consume its approved handoff. Detailed implementation, review, QA, UI verification, and fix-loop mechanics belong to the `implementation-workflow` skill.

Do not use this workflow for a related batch of tickets. If a fresh approved requirements handoff and execution mode are already established, the ticket is already In Progress, and the request is only to execute, review, verify, and open a PR, invoke `implementation-workflow` directly. This shortcut is not available for a ticket marked prototype-backed.

Mandatory lifecycle:

Setup -> Brainstorm -> Spec/design approval -> Plan approval -> Implementation -> Parity step (prototype-backed tickets) -> PR readiness

Approval is artifact-specific. A user can approve only an artifact they have seen. Agreement with decisions, assumptions, recommendations, investigation progress, or "good to go" does not approve an unwritten spec/design or implementation plan.

## Session Title

When a chat session starts with this skill, name that session after the ticket: use the user story id and title, for example `ABC-123 Add password reset`. If the session started before the ticket was identified, set the title as soon as intake resolves the id and title. If the session title cannot be set, say so and continue.

## Prototype-Backed Projects

Decide once, at intake, and record the decision in the requirements handoff:
if the repository contains a reference prototype app and the ticket implies a
user-visible UI change, load `prototype-backed-workflow` and keep it active
for the ticket. Otherwise do not load it. No later phase re-evaluates this
decision; a ticket whose scope changes to include UI returns to intake.

When it is active, `prototype-backed-workflow` wraps implementation: its
prototype-first rules apply before implementation dispatch, and its parity
step runs after `implementation-workflow` returns complete and before PR
readiness. PR readiness treats the parity ledger as the UI/UX parity evidence.

## Resume Rules

Resume after the longest contiguous sequence of fresh checkpoints established by reliable conversation context, supplied records, or accessible ticket and PR evidence:

- The requirements checkpoint requires one fresh, internally consistent handoff containing ticket and parent context, the prototype-backed decision, a Brainstorm completion record, the written spec/design and its explicit approval evidence, the written implementation plan and its explicit approval evidence, accepted assumptions and open questions, and risks and required verification surfaces.
- The execution-mode checkpoint separately requires that handoff and evidence of the selected or approved mode.
- The execution-authorization checkpoint separately requires the valid handoff, selected mode, and an explicit instruction to execute the approved plan in that mode.
- The ticket-transition checkpoint separately requires execution authorization and the completed transition result, including evidence when tracker mutation was excluded.
- PR readiness requires those checkpoints, the current ticket state, and an implementation report or equivalent changed-scope, test, verification, and PR-or-blocker evidence.

Refresh repository, ticket, and PR state before acting. If a requirements prerequisite is missing, stale, or contradictory, route to its earliest affected checkpoint through `ticket-requirements-gathering`. If a later prerequisite is missing or stale, recover from the earliest missing local checkpoint. Do not assume approval or replay checkpoints whose evidence remains valid.

## Requirements Intake And Validation

At intake, invoke `ticket-requirements-gathering`. If it is unavailable, return an explicit upstream handoff naming the earliest required checkpoint and evidence; do not duplicate or reconstruct its phases.

Before implementation transition, validate the handoff. The Brainstorm record must establish that no material unknown remains unresolved and identify explicitly accepted lower-impact assumptions and open questions. Approval evidence is valid only for the written, presented spec/design and implementation plan.

A change to scope, behavior, design, or acceptance criteria invalidates the spec/design and plan approvals. A plan-only change invalidates plan approval. Route to the earliest affected checkpoint in `ticket-requirements-gathering`. An execution-mode change stays local and returns only to mode approval.

## Implementation Transition

1. After plan approval, recommend inline, delegated, or hybrid execution based on size, coupling, risk, separability, and implementation context.
2. Ask the user to select or approve the execution mode before dispatch or edits.
3. Treat an explicit instruction to execute the approved plan in the selected mode as authorization to move only the associated ticket to the process-appropriate In Progress state. Mode approval alone is not execution authorization. Announce and complete that transition before code or test edits; ask separately if the user or tracker policy excluded tracker mutation.
4. Invoke `implementation-workflow` with the approved spec/design and approval evidence, approved plan and approval evidence, accepted assumptions and open questions, execution mode, explicit execution authorization, ticket context, Brainstorm record, refreshed repository and ticket state, ticket-transition outcome, the expected-demand profile (stage, expected users, load and data volumes, reliability expectations), taken from repository instructions or ticket context and confirmed with the user when neither states it, and required verification surfaces.
5. If that skill is unavailable, implement inline only when the user explicitly authorizes the fallback and execution mode. Otherwise return a concrete handoff or access blocker without inventing collaborator results.

Keep implementation within the approved artifacts. A change to scope, behavior, design, or acceptance criteria invalidates the spec/design and plan approvals; a plan-only change invalidates plan approval. Return to the earliest affected checkpoint in `ticket-requirements-gathering`. An execution-mode change returns only to mode approval here.

## PR Readiness

Refresh the PR, CI, review, and ticket state after implementation. Determine required evidence from the approved plan, changed scope, repository policy, and actual user-visible risk. Mark evidence not applicable only with a reason. Missing required evidence is a blocker.

Check:

- implementation produced a PR or a concrete blocker explaining why no PR exists
- PR target, title, description, linked ticket, and changed scope match the approved plan
- implementation, automated test, review, manual QA, UI/UX parity, and blocker evidence is present when applicable
- all PR pipeline checks are green; wait for pending checks
- failed checks are investigated, fixed, and rerun or awaited before readiness
- PR comments and review threads have no unresolved or unaddressed items
- unresolved findings, blockers, assumptions, and follow-ups are explicit
- ticket state is appropriate for the user's process

Manual QA evidence applies to user-observable behavior or acceptance flows. UI/UX parity evidence applies to visual changes in a prototype-backed repository and consists of the session's parity ledger with every row at MATCH plus the final parity report; a ledger with any other row state is a blocker. Review evidence applies when the repository or implementation process requires review. Blocker evidence applies whenever a required surface could not be exercised.

Route CI or review fixes back through `implementation-workflow` under the approved scope and execution mode. Use the explicitly authorized inline fallback only when that skill is unavailable. If a fix changes scope, behavior, design, or acceptance criteria, invalidate the spec/design and plan approvals and return to `ticket-requirements-gathering`; if it changes only the plan, invalidate plan approval and return there. If it changes execution mode, return only to local mode approval. Refresh evidence and repeat readiness checks after each fix.

If PR, CI, tracker, or required evidence access is unavailable, name the inaccessible surface, the exact evidence still needed, and the handoff required. Do not claim readiness from partial evidence.

Do not merge, complete or close the ticket, dismiss comments, or perform another final source-control or tracker mutation without explicit user approval.

Use this readiness shape:

- PR exists or blocker:
- target, title, description, and linked ticket:
- changed scope vs approved plan:
- implementation, review, manual QA, UI/UX parity, test, and blocker evidence:
- PR pipeline CI status and fixes:
- PR comments and review threads:
- unresolved findings, assumptions, and follow-ups:
- ticket state:
- prohibited mutations without approval:

## Final Report

End with the ticket summary, approved spec/design summary, approved plan summary, implementation status, PR link or creation blocker, PR-readiness result, ticket state, and remaining risks, blockers, assumptions, or follow-ups.

## Stop Conditions

Stop and recover when working from stale ticket, parent, repository, or PR context; when an approval or resume prerequisite is missing; when the plan cannot guide implementation and verification; when implementation has no PR or blocker evidence; or when a requested mutation lacks its required authorization.
