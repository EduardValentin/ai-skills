---
name: qa-verification
description: Use when manually verifying acceptance criteria and user-observable or system-observable behavior for a running app, API, service, job, script, integration, frontend PR, or mixed executable surface. Use when the user asks for QA, browser behavior evidence, acceptance-criteria verification, PR-note verification, backend/API probes, CLI checks, persistence, auth, validation, state transitions, regression probes, and PR/ticket-linked QA.
compatibility: >-
  Requires access to the running surface, mode-appropriate interaction and probe tools, and any credentials, fixtures, seed data, feature flags, or real dependencies required by the acceptance criteria. Try available PR or ticket tooling, ask the caller for missing metadata, and only then use explicitly provisional diff scope. If runtime evidence is unavailable, return the documented blocker verdict.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# QA Verification

## Purpose

Manually verify that an implementation satisfies its acceptance criteria by exercising the implemented surface the way a user, client, job runner, or integration would.

Do not change implementation code or alter configuration to repair a defect while acting as the verifier. Normal verification may use documented setup, feature flags, or test controls and may mutate designated test data or trigger expected side effects when the acceptance criteria require it; record those mutations and any cleanup.

When an acceptance criterion depends on a real third-party contract or propagated state, gather evidence from that dependency. A controlled substitute is acceptable only when the criterion and requested scope explicitly concern behavior independent of the dependency; report the limitation and do not claim integration coverage. If required access, tooling, credentials, data, dependencies, or an executable surface is unavailable, return `QA cannot proceed` and name the blocker plus required next input. Passing tests, mocks, and source inspection cannot replace missing runtime evidence. When a caller explicitly requires `CANNOT_VERIFY`, use that blocker token with the same reason and required next input.

## Inputs

Expect a compact QA request with:

- implemented surface area and entry point: URL, command, API, job trigger, script, or integration path
- ticket, PR, bug report, acceptance criteria, and testing instructions when available
- mode: `ui`, `backend`, `mixed`, or `other`
- environment setup, credentials, seed data, fixtures, feature flags, and known non-goals
- changed surfaces, adjacent flows, integrations, and state that may regress

For ticket/PR-linked QA, use this mandatory order before verification: first access the PR and ticket through available tooling such as MCP, API, CLI, or authenticated local metadata; then, if unavailable, ask the caller for the ticket/PR details, acceptance criteria, implemented surface area, and testing instructions; only after the caller cannot provide those details, scope the diff to infer a provisional verification target and clearly label it as inferred. Blocked metadata alone is not enough to fall back to the diff.

Use PR/ticket metadata only to derive QA scope, setup, acceptance criteria, and regression risks. Do not assess CI, approvals, unresolved comments, mergeability, or tracker-state gates.

When caller-supplied PR/ticket notes are available and the local diff is available, use the notes as QA scope and the diff to identify affected routes, setup, implemented surfaces, and regression risks.

When metadata is available but testing instructions are absent or vague, scope before verification from the PR/ticket details, acceptance criteria, diff/changed files, entry points, setup/data needs, implemented surface, and regression risks. The response must explicitly name those scope inputs, using `missing` or `not applicable` rather than omitting them.

## Verification Modes

- `ui`: start the application, use browser tooling, manually click through the implemented surface, and inspect behavior after each action: copy/data changes, navigation, validation, disabled/submitting behavior, persistence, and errors. Name the app start command or URL, browser actions, and rendered outcomes. Cover happy path, loading, empty, success, error, validation, disabled, focus/active, navigation, rapid-click, double-submit, and adjacent-flow behavior when relevant.
- `backend`: use programmatic probes against the running implemented surface, such as HTTP requests, CLI invocations, job triggers, database reads, logs, queues, emitted events, or cache checks. Validate outputs, state transitions, persistence, side effects, auth, validation, error handling, idempotency, retries, and third-party/state propagation when relevant. Keep state-transition checks explicit in the approach and report; do not collapse them into persistence or side effects.
- `mixed`: prefer running the GUI and backend/service together and verifying the flow end to end. The approach and report must explicitly name browser-observed behavior and programmatic backend/API/service probes, then tie them through the integration contract and propagated state. If running them together is not possible, verify each surface separately, state the limitation, and still validate the integration contract and propagated state.
- `other`: exercise scripts, scheduled tasks, data jobs, migrations, or integrations through their real command/trigger path. Check inputs, outputs, logs, external calls, exit codes, reruns, failure modes, cleanup, and state changes.

Automated checks, mocks, fake imports, stubs, simulations, unit tests, type checks, source inspection, and static review can support QA context, but they are not manual QA and do not count as QA verification by themselves.

## Verdicts and Report

- `CLEAN`: every acceptance criterion was exercised against the required running surface and passed.
- `BUGS FOUND`: at least one exercised behavior failed. Include reproduction steps, expected behavior, actual behavior, and evidence for every defect.
- `QA cannot proceed`: required runtime, access, data, or dependency evidence is unavailable. Name each blocker and the next input needed. Use `CANNOT_VERIFY` instead only when the caller requires that token.
- `NOT RUN`: verification is feasible but has not been executed, including scope-only or plan-only requests. Describe the intended probes without implying observed results.

The final report must include the verdict, mode and environment, scope inputs, and a result for every acceptance criterion. For each criterion, record the action, request, command, or trigger; expected behavior; observed UI, response, state, side effect, or propagation result; evidence; and pass, fail, or blocked status. Also list defects, blockers and unverified areas, limitations, test-data mutations and cleanup, and relevant regression notes. Mark unavailable fields as `missing` or `not applicable` rather than silently omitting them.

## Evidence Standard

Every acceptance criterion must map to a concrete observation:

- browser action, route, visible state, and rendered result for GUI behavior
- request/command/trigger, response/output, side effect, and persisted/propagated state for non-GUI behavior
- both GUI and non-GUI observations for mixed work

Any observed bug changes the verdict to `BUGS FOUND`.

When provided runtime facts show QA can proceed but verification has not yet been run, use `NOT RUN`, state the manual/runtime probes, and explain the evidence each probe must produce. Any failed behavior becomes `BUGS FOUND`.

## Forbidden Behaviors

- Declaring `CLEAN` without manually exercising every acceptance criterion against the running surface.
- Treating mocks, fake imports, stubs, simulations, unit tests, type checks, static review, screenshots without interaction, or source inspection as QA verification by themselves.
- Providing a hypothetical QA plan instead of a `QA cannot proceed` verdict when required runtime, credentials, seeded data, or real third-party dependencies are unavailable.
- Starting the app, scoping from the diff, or inferring testing instructions before attempting available PR/ticket tooling and asking for missing details.
- Falling back to diff-scoped QA before the caller has had a chance to provide missing ticket/PR details, acceptance criteria, implemented surface area, and testing instructions.
- Treating inferred diff scope as authoritative when ticket/PR details, acceptance criteria, or testing instructions are available.
- Comparing appearance against references, analogs, computed styles, or bounding boxes instead of verifying behavior after user or system actions.
- Modifying product code or changing configuration to repair a finding while acting as the QA verifier.
- Assessing PR readiness, CI approval gates, unresolved review comments, mergeability, or tracker-state gates.
- Omitting state-transition, persistence, side-effect, or propagation checks when the acceptance criteria depend on them.
- Reporting a bug without reproduction steps and evidence.
