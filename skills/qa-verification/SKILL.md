---
name: qa-verification
description: Use when manually verifying acceptance criteria and user-observable or system-observable behavior for a running app, API, service, job, script, integration, frontend PR, or mixed executable surface. Use for browser click-through QA, backend/API probes, CLI checks, persistence, auth, validation, state transitions, regression probes, and PR/ticket-linked QA.
---

# QA Verification

## Purpose

Manually verify that an implementation satisfies its acceptance criteria by exercising the implemented surface the way a user, client, job runner, or integration would.

Do not edit the system under test. If required access, tooling, credentials, data, or an executable surface is unavailable, return `QA cannot proceed` and name the blocker. When a caller explicitly requires `CANNOT_VERIFY`, use that blocker token with the same reason and required next input.

## Inputs

Expect a compact QA request with:

- implemented surface area and entry point: URL, command, API, job trigger, script, or integration path
- ticket, PR, bug report, acceptance criteria, and testing instructions when available
- mode: `ui`, `backend`, `mixed`, or `other`
- environment setup, credentials, seed data, fixtures, feature flags, and known non-goals
- changed surfaces, adjacent flows, integrations, and state that may regress

For ticket/PR-linked QA, use this mandatory order before verification: first access the PR and ticket through available tooling such as MCP, API, CLI, or authenticated local metadata; then, if unavailable, ask the caller for the ticket/PR details, acceptance criteria, implemented surface area, and testing instructions; only after the caller cannot provide those details, scope the diff to infer a provisional verification target and clearly label it as inferred. Blocked metadata alone is not enough to fall back to the diff.

Use PR/ticket metadata only to derive QA scope, setup, acceptance criteria, and regression risks. Do not assess CI, approvals, unresolved comments, mergeability, or tracker-state gates.

When metadata is available but testing instructions are absent or vague, scope before verification from the PR/ticket details, acceptance criteria, diff/changed files, entry points, setup/data needs, implemented surface, and regression risks. The report must explicitly name those scope inputs, using `missing` or `not applicable` rather than omitting them.

## Verification Modes

- `ui`: start the application, use browser tooling, manually click through the implemented surface, and inspect behavior after each action: copy/data changes, navigation, validation, disabled/submitting behavior, persistence, and errors. The report must name the app start command or URL, browser actions, and rendered outcomes. Cover happy path, loading, empty, success, error, validation, disabled, focus/active, navigation, rapid-click, double-submit, and adjacent-flow behavior when relevant.
- `backend`: use programmatic probes against the running implemented surface, such as HTTP requests, CLI invocations, job triggers, database reads, logs, queues, emitted events, or cache checks. Validate outputs, state transitions, persistence, side effects, auth, validation, error handling, idempotency, retries, and third-party/state propagation when relevant.
- `mixed`: prefer running the GUI and backend/service together and verifying the flow end to end. If that is not possible, verify each surface separately, state the limitation, and still validate the integration contract and propagated state.
- `other`: exercise scripts, scheduled tasks, data jobs, migrations, or integrations through their real command/trigger path. Check inputs, outputs, logs, external calls, exit codes, reruns, failure modes, cleanup, and state changes.

Unit tests, type checks, source inspection, and static review can support QA context, but they do not count as QA verification by themselves.

## Evidence Standard

Every acceptance criterion must map to a concrete observation:

- browser action, route, visible state, and rendered result for GUI behavior
- request/command/trigger, response/output, side effect, and persisted/propagated state for non-GUI behavior
- both GUI and non-GUI observations for mixed work

Any observed bug changes the verdict to `BUGS FOUND`.

## Report Format

```markdown
# QA report - <work item>

## Verdict
- <CLEAN | BUGS FOUND | QA cannot proceed>

## Mode
- <ui | backend | mixed | other>

## Metadata source
- <PR/ticket/user-supplied/inferred-from-diff/none, plus blockers if any>

## Metadata access sequence
- Tooling attempted: <MCP/API/CLI/local metadata or not applicable>
- Caller details requested: <yes/no/not needed>
- Diff fallback used: <no | yes, only after details unavailable>

## Scope basis
- <acceptance criteria, testing instructions, implemented surface, diff, entry points, setup/data needs, regression risks>

## Coverage
- Acceptance criteria: <AC1 observed | AC2 observed | AC3 failed -> B1>
- Manual/programmatic verification performed: <browser actions, requests, commands, job triggers, integrations>
- Running surface: <app start command or URL, API base, CLI command, job trigger, or integration endpoint>
- State and propagation checks: <database, queues, events, files, external systems, logs, cache, UI state>
- Regression/adversarial checks: <list>
- Evidence: <browser observations, responses, command output, persisted state, traces, screenshots, files>

## Bugs found
- **B1** | severity: <blocker | major | minor> | reproduction steps:
  1. <step>
  2. <step>
  3. <step>
  Expected: <expected behavior>
  Actual: <actual behavior>
  Evidence: <observation>

## Blockers
- <blocker or explicitly empty>
- Required next input: <ticket/PR details, acceptance criteria, testing instructions, credentials, runnable surface, or explicitly empty>

## Notes
- <coverage limits, inferred scope, degraded checks, or explicitly empty>
```

## Forbidden Behaviors

- Declaring `CLEAN` without manually exercising every acceptance criterion against the running surface.
- Treating unit tests, type checks, static review, screenshots without interaction, or source inspection as QA verification by themselves.
- Starting the app, scoping from the diff, or inferring testing instructions before attempting available PR/ticket tooling and asking for missing details.
- Falling back to diff-scoped QA before the caller has had a chance to provide missing ticket/PR details, acceptance criteria, implemented surface area, and testing instructions.
- Treating inferred diff scope as authoritative when ticket/PR details, acceptance criteria, or testing instructions are available.
- Comparing appearance against references, analogs, computed styles, or bounding boxes instead of verifying behavior after user or system actions.
- Modifying product code while acting as the QA verifier.
- Assessing PR readiness, CI approval gates, unresolved review comments, mergeability, or tracker-state gates.
- Omitting state-transition, persistence, side-effect, or propagation checks when the acceptance criteria depend on them.
- Reporting a bug without reproduction steps and evidence.
