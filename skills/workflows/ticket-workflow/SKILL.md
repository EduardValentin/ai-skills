---
name: ticket-workflow
description: Use when coordinating one standalone implementation ticket from intake or resuming its lifecycle at an evidenced implementation transition or PR-readiness checkpoint.
compatibility: >-
  Full operation requires repository, ticket-tracker, PR, and CI access plus the `implementation-workflow` skill. If native read-only agents are unavailable, perform discovery inline. If `implementation-workflow` is unavailable, implement inline only with explicit fallback authorization or return an explicit handoff. Missing tracker, PR, CI, or evidence access blocks only the affected transition or readiness claim.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Ticket Workflow

## Scope

Coordinate one standalone ticket through requirements intake, shared understanding, artifact-specific approvals, implementation transition, and final PR readiness. Detailed implementation, review, QA, UI verification, and fix-loop mechanics belong to the `implementation-workflow` skill.

Do not use this workflow for a related batch of tickets. If the approved plan and execution mode are already established, the ticket is already In Progress, and the request is only to execute, review, verify, and open a PR, invoke `implementation-workflow` directly.

Mandatory lifecycle:

Setup -> Brainstorm -> Spec/design approval -> Plan approval -> Implementation -> PR readiness

Approval is artifact-specific. A user can approve only an artifact they have seen. Agreement with decisions, assumptions, recommendations, investigation progress, or "good to go" does not approve an unwritten spec/design or implementation plan.

## Resume Rules

Resume at a later checkpoint only when reliable conversation context, supplied records, or accessible ticket and PR evidence establish its prerequisites:

- Implementation transition requires the written spec/design and implementation plan plus explicit approval of each. Resuming work already in progress also requires evidence of the approved execution mode and the current ticket state.
- PR readiness requires those approvals, the execution-mode authorization, the current ticket state, and an implementation report or equivalent changed-scope, test, verification, and PR-or-blocker evidence.

Refresh repository, ticket, and PR state before acting. If a prerequisite is missing or stale, recover from the earliest missing checkpoint; do not assume approval or replay checkpoints whose evidence remains valid.

## Discovery Delegation

Keep ownership of the ticket, repository instructions, workflow decisions, core code path, user questions, and approval artifacts. Delegate broad, independent, read-only discovery when agents are available and the work can be compressed without fragmenting the core analysis. Suitable work includes cross-ticket history, repo-wide reference inventories, test-surface mapping, external API research, and docs, environment, deployment, or PR-status sweeps.

Require concise, categorized, locator-backed results rather than raw dumps. Perform discovery inline when delegation would not preserve quality or save meaningful context, and briefly state that choice when a broad delegation opportunity existed.

Delegated and inline discovery must produce one setup map covering affected files or surfaces, entry points, tests, risks, and verification surfaces with locators.

## Setup

1. Confirm the ticket is standalone and intended for implementation. Ask if either point is unclear.
2. Read the ticket for its goal, stakeholder implications, acceptance criteria, dependencies, and ambiguity. Read any parent Epic, story, or ticket that supplies goals or constraints.
3. Read repository instructions and the relevant product, design, reference, code, and test slices.
4. Inspect repository state, related PRs, and draft work only as needed to avoid stale assumptions.
5. Build the setup map before brainstorming, using the discovery-delegation rule above.

## Brainstorm

Interview the user one question at a time, grounded in the ticket, parent context, repository facts, and setup map. Resolve unknowns, low-confidence assumptions, stakeholder implications, constraints, edge cases, risks, non-goals, and alternatives that could materially change implementation.

An unknown is material when it could change user-visible behavior, scope, acceptance criteria, data or security handling, integration contracts, rollout or recovery, or verification. Continue until no material unknown remains unresolved. Record lower-impact residual unknowns as assumptions or open questions and proceed only when the user explicitly accepts them.

Then write a concise spec/design containing the agreed scope, decisions, acceptance criteria, risks, alternatives considered, accepted assumptions, and open questions. Present that artifact and ask for its explicit approval.

Do not write the implementation plan before spec/design approval.

## Plan

After spec/design approval, write an implementation plan grounded in all approved decisions and gathered context. Present the plan and wait for explicit approval of that artifact. Do not edit product code or tests until both approval gates have passed.

## Implementation Transition

1. After plan approval, recommend inline, delegated, or hybrid execution based on size, coupling, risk, separability, and implementation context.
2. Ask the user to select or approve the execution mode before dispatch or edits.
3. Treat an explicit instruction to execute the approved plan in the selected mode as authorization to move only the associated ticket to the process-appropriate In Progress state. Mode approval alone is not execution authorization. Announce and complete that transition before code or test edits; ask separately if the user or tracker policy excluded tracker mutation.
4. Invoke `implementation-workflow` with the approved spec/design, plan, execution mode, ticket context, setup map, and required verification surfaces.
5. If that skill is unavailable, implement inline only when the user explicitly authorizes the fallback and execution mode. Otherwise return a concrete handoff or access blocker without inventing collaborator results.

Keep implementation within the approved artifacts. A change to product scope, design, or execution mode returns to the relevant approval gate.

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

Manual QA evidence applies to user-observable behavior or acceptance flows. UI/UX parity evidence applies to visual changes with an approved design or prototype. Review evidence applies when the repository or implementation process requires review. Blocker evidence applies whenever a required surface could not be exercised.

Route CI or review fixes back through `implementation-workflow` under the approved scope and execution mode. Use the explicitly authorized inline fallback only when that skill is unavailable. If a fix changes approved scope, design, or mode, return to the relevant approval gate. Refresh evidence and repeat readiness checks after each fix.

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
