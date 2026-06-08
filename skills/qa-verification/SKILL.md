---
name: qa-verification
description: Use when verifying acceptance criteria and user-observable or system-observable behavior for a running app, API, service, job, script, integration, or mixed executable surface. Use for backend/API checks, UI behavior checks, mixed API-and-UI flows, persistence, auth, validation, error handling, state transitions, and regression probes. The QA verifier exercises the system, records evidence, reports bugs with reproduction steps, and returns a QA report.
---

# QA Verification

## Purpose

Use this skill to verify whether a running implementation satisfies its acceptance criteria. The verifier exercises the executable surface, records what happened, and reports bugs with evidence.

The verifier does not edit the system under test. If behavior cannot be exercised, return `QA cannot proceed` and name the blocker.

## Inputs

Expect a compact, self-contained QA request with:

- work item title, description, and acceptance criteria
- approved requirements/design and implementation plan when available
- changed surfaces or relevant scope notes
- QA mode: `backend`, `ui`, `mixed`, or `other`
- path, command, URL, environment, or entry point for the executable surface
- relevant credentials, seed data, fixtures, feature flags, or test users when required
- known constraints, non-goals, and adjacent behavior that may regress

If required inputs are missing or contradictory, return `QA cannot proceed` with the exact missing input or conflict.

## Evidence Standard

QA reports require exercised behavior evidence. Passing unit tests, static review, local confidence, screenshots without interaction, or "the diff looks right" can support the report, but they do not replace exercising the running surface.

Each acceptance criterion must map to a concrete observation:

- request, response, side effect, and persisted state for backend/API/service work
- user action and resulting browser-observed state for UI behavior
- command output, file output, logs, or external side effects for scripts, jobs, and integrations
- both backend and UI observations for mixed work

Any observed bug changes the verdict to `BUGS FOUND`.

## Execution Fallbacks

Use the best available capability to exercise the running surface:

1. Native browser, HTTP, database, job, or command automation when available.
2. Project-local scripts, shell-invokable clients, or browser automation when native automation is unavailable.
3. Degraded manual confirmation only when automation cannot be used. Label the verdict as degraded and list exactly what the user must confirm.

If none of these can exercise the behavior, stop with `QA cannot proceed`.

## Modes

### Backend/API/Service

Use for API, service, job, consumer, migration, persistence, queue, cache, or integration behavior.

Verify:

- reachability and setup assumptions
- happy paths with valid inputs
- validation failures and error responses
- auth, permission, role, and tenant boundaries where relevant
- state transitions, persistence, emitted events, queues, cache updates, and logs
- idempotency, retry, and concurrency behavior when touched
- adjacent endpoints, handlers, jobs, consumers, or shared code paths that may regress

Inspect more than status codes. Payload, persistence, side effects, and logs must match the acceptance criteria.

### UI Behavior

Use for behavior exercised through a browser or comparable user interface.

Verify:

- happy path end to end
- loading, empty, success, error, and validation states
- focus, active, disabled, expanded/collapsed, modal-open, and navigation states tied to behavior
- invalid values, boundary inputs, rapid clicks, double submits, and navigating mid-action
- cross-feature impact on adjacent flows reachable from the feature surface
- responsive behavior when it affects functionality or state reachability

### Mixed

Use when the work touches both API/service behavior and UI behavior. Exercise both surfaces and verify that the integration between them satisfies the acceptance criteria.

### Other Executable Surface

Use for scripts, CLIs, scheduled tasks, data jobs, migrations, or integrations that are not cleanly backend or UI.

Verify:

- command or trigger path
- inputs, flags, environment, fixtures, and permissions
- output files, stdout/stderr, logs, database writes, external calls, and exit codes
- rerun/idempotency behavior when relevant
- failure modes and cleanup behavior

## Report Format

```markdown
# QA report - <work item>

## Verdict
- [ ] CLEAN - no bugs found
- [ ] BUGS FOUND - at least one bug found
- [ ] QA cannot proceed - blocker named below

## Mode used
- <backend | ui | mixed | other>

## Coverage performed
- Acceptance criteria: <AC1 observed | AC2 observed | AC3 failed -> B1>
- Happy paths exercised: <list>
- Error paths exercised: <list>
- State transitions or side effects: <list>
- Adversarial inputs tried: <list>
- Adjacent regression checks: <list>
- Evidence: <request logs, browser observations, persisted state, command output, traces, screenshots, or files>

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

## Notes
- <coverage limits, degraded checks, or explicitly empty>
```

## Forbidden Behaviors

- Declaring `CLEAN` without exercising every acceptance criterion against the running surface.
- Treating unit tests, type checks, static review, or source inspection as full QA evidence by themselves.
- Skipping adversarial inputs because the happy path works.
- Modifying product code while acting as the QA verifier.
- Omitting adjacent regression checks when changed behavior is shared by adjacent flows.
- Reporting a bug without reproduction steps and evidence.

## Stop Conditions

Stop when every acceptance criterion has been exercised and is either observed clean or mapped to a bug, coverage performed names what was actually checked, and bugs include reproduction evidence.
