---
name: implementation-workflow
description: Use when an approved implementation plan or plan slice is ready for code changes and the work must continue through independent review, manual QA, remediation, reruns, and reporting.
compatibility: >-
  Requires the public `dispatch-reviewers-workflow` skill and fresh-context
  agent dispatch for independent review, plus `qa-verifier` or a separate
  generic QA agent with the public `qa-verification` skill preloaded and able
  to exercise the runtime surface. If
  `dispatch-reviewers-workflow` is unavailable, return `IMPLEMENTATION
  BLOCKED`; block if no QA role can produce evidence.
metadata:
  ai-skills-category: procedural
  ai-skills-invocation: manual
  status: experimental
  allows_tool_references: "true"
---

# Implementation Workflow

## Scope

Implement an approved code unit and carry it through code quality checks, independent review, manual QA, remediation, reruns, and a traceable implementation report.

This workflow starts after implementation-plan approval. It does not own requirements intake, source-of-truth approval, design approval, plan approval, execution-mode selection, PR readiness or publication, release, merge, or tracker-state changes.

Preserve the execution mode selected before this workflow starts. Delegation does not transfer responsibility for repository instructions, plan interpretation, integration, scope control, or approval-sensitive decisions away from the main agent.

## Entry Gate

Require:

- an approved implementation plan or approved plan slice
- acceptance criteria or another clear, approved user-observable outcome
- the approved boundary and explicit non-goals
- applicable source-of-truth requirements or design decisions, when the work has them
- repository instructions, ownership constraints, and current branch or worktree state
- known dependencies, sequencing constraints, risks, and expected verification surfaces

Check that the packet is current and internally consistent. A separate spec or design artifact is not required when the approved work does not need one.

If required context is missing, stale, or contradictory enough to make implementation unsafe, return `IMPLEMENTATION BLOCKED`. Name the blocker and the exact input or approval needed; do not infer scope or edit.

## Completion States

Use only these terminal states:

- `IMPLEMENTATION COMPLETE`: the approved behavior is implemented, relevant automated checks pass or have a documented justified exception, independent review has no unresolved relevant findings, and manual QA has passing evidence for every acceptance criterion or approved outcome.
- `IMPLEMENTATION BLOCKED`: any required gate cannot be completed, including an unavailable input, an unapproved plan change, a check that cannot be resolved, missing independent review evidence, or missing manual QA evidence.

A blocked result still reports all available implementation, check, review, and QA evidence plus the next required input or decision. Never describe unfinished review or QA as optional follow-up work.

## Discovery and Delegation

Choose scanning depth from the plan's ambiguity, risk, coupling, and current confidence. Before editing, produce a locator-backed scope map covering affected files or surfaces, entry points, tests, risks, and verification surfaces.

Before broad searches or large reads, consider fresh, read-only subagents for independent and compressible discovery such as reference inventories, external API research, test mapping, or environment and deployment sweeps. Ask for concise, categorized, locator-backed results. Keep plan interpretation and the core code path with the main agent. If a plausible broad discovery slice remains inline, briefly state why.

## Implementation

1. Confirm the entry gate and approved execution mode.
2. Build the scope map and inspect the relevant architecture, callers, contracts, and tests.
3. Implement only the approved plan, following repository patterns unless the plan justifies a deviation.
4. Run focused checks first, then the relevant regression checks implied by risk and coupling.
5. Submit the resulting implementation diff or working tree to independent review. A PR may be supplied when one already exists, but a PR is not required.
6. Resolve relevant review findings and obtain a clean fresh review before QA.
7. Manually verify the reviewed executable behavior against every acceptance criterion or approved outcome.
8. Resolve QA failures through the remediation loop, including fresh review and affected QA reruns.
9. Return the implementation report when all gates pass or a blocker requires approval or new context.

### Engineering Invariants

- Stay inside the approved boundary. If implementation reveals that the plan must change, return `IMPLEMENTATION BLOCKED`, explain the required change and why, and wait for approval.
- Use TDD for behavior changes: add or update a meaningful test, observe the intended failure, implement, and rerun the focused and relevant regression checks.
- When no meaningful automated test can exercise the change, document why before implementation and record the strongest available deterministic and manual evidence in the report. Do not claim TDD in that case.
- Prefer names that expose purpose, side effects, and domain invariants.
- Avoid duplicated logic, hidden side effects, and abstractions that do not remove real complexity.
- Trace every change to the approved goal, criteria, or required supporting behavior.
- Assess security implications where relevant, especially authentication, authorization, user input, data exposure, persistence, redirects, files, external requests, privileged actions, dependencies, and sensitive logging.

## Independent Review


WIP

## Manual QA

Use `qa-verifier` when available. Otherwise use a separate generic QA agent with the `qa-verification` skill preloaded that can exercise the actual runtime surface and capture user-observable or system-observable evidence. It must not substitute source inspection, mocks, or automated tests for manual execution.

Provide the criteria or approved outcome, implemented surface and entry points, setup and runtime details, affected files or surfaces, changed behavior, known risks, check evidence, and review or fix context. Require evidence for every criterion. Wait for the QA result; passing automated checks alone never satisfies this gate.

## Remediation Loop

For each relevant review finding or QA failure:

1. Decide whether the fix remains inside the approved plan. Block and request approval if it does not.
2. Add or update a meaningful failing test first when the issue is automatable, then implement the fix.
3. Rerun the focused check and all regression checks affected by the fix.
4. Obtain fresh independent review of the revised diff.
5. If QA has started, rerun failed and affected criteria plus relevant regression surfaces so every criterion has passing evidence against the final implementation.

Clear review findings before the first QA pass. If fresh review finds another relevant issue, repeat the loop before QA or QA reruns. Continue until no relevant review finding remains and all criteria pass. If a finding, failure, environment problem, or missing capability cannot be resolved, return `IMPLEMENTATION BLOCKED` with the evidence gathered so far.

## Implementation Report

The final report includes:

- terminal status
- approved goal and delivered behavior mapped to the criteria or outcome
- changed files or surfaces and their purpose
- test-first evidence, focused and regression check commands, and outcomes, or the justified no-test exception
- independent review findings, dispositions, fixes, reruns, and final review outcome
- manual QA coverage, criterion-level outcomes, and final evidence
- known residual risks and limitations, explicitly stating when none are known
- for a blocked result, the exact blocker and next required input or approval

Do not claim PR readiness, publish a PR, release, merge, or update a tracker from this workflow.

## Red Flags

- Editing before the entry gate and scope map are complete.
- Broadening scope or changing the plan without approval.
- Reading only the target file when callers, contracts, or adjacent tests can affect the change.
- Claiming TDD without observing a meaningful failing test.
- Treating automated checks as independent review or manual QA.
- Letting the implementer perform the independent review.
- Completing while relevant findings, failed criteria, or missing evidence remain.
- Returning an unstructured prose summary without changed surfaces, checks, review, QA, and risks.
