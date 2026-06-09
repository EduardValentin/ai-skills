---
name: qa-verification
description: Use when verifying acceptance criteria and user-observable or system-observable behavior for a running app, API, service, job, script, integration, frontend PR, or mixed executable surface. Use for browser behavior, backend/API checks, persistence, auth, validation, error handling, state transitions, regression probes, and blocked PR/ticket metadata during QA.
---

# QA Verification

## Purpose

Verify whether a running implementation satisfies its acceptance criteria. Exercise the executable surface, record what happened, and report bugs with evidence.

Do not edit the system under test. If required inputs, metadata, access, tooling, or executable behavior are unavailable, return `QA cannot proceed` and name the blocker.

## Inputs

Expect a compact, self-contained QA request with:

- work item title, description, and acceptance criteria
- path, command, URL, environment, or entry point for the executable surface
- mode: `backend`, `ui`, `mixed`, or `other`
- changed surfaces, scope notes, non-goals, and adjacent behavior that may regress
- credentials, seed data, fixtures, feature flags, or test users when required
- PR/ticket metadata, PR notes, or bug report details when QA is PR-linked

If required inputs are missing or contradictory, return `QA cannot proceed` with the exact missing input or conflict.

## PR-Linked QA

For PR-linked QA, verify the branch being reviewed:

1. Fetch or confirm the latest PR branch and base branch before setup.
2. Read PR metadata and ticket/bug details before diff-derived scoping or browser testing.
3. If PR metadata is blocked by auth, network, missing connector, unavailable CLI, or login wall, stop with `QA cannot proceed`. Ask for restored access, pasted PR notes, or another authenticated source. The report must name that required next input. Do not start the app, scope from the diff, or infer PR testing instructions. A ticket ID, local diff, or user permission to proceed without PR notes does not replace blocked PR metadata.
4. Run PR testing notes first and map them to acceptance criteria.
5. If metadata was read but testing notes are absent or vague, scope from the PR, ticket, diff, changed files, entry points, setup/data needs, focused tests, and regression risks before exercising behavior.

## Evidence Standard

QA reports require exercised behavior evidence. Unit tests, static review, source inspection, screenshots without interaction, or "the diff looks right" can support the report, but they do not replace exercising the running surface.

Each acceptance criterion must map to a concrete observation:

- request, response, side effect, and persisted state for backend/API/service work
- user action, route, active state, and browser-observed result for UI behavior
- command output, file output, logs, or external side effects for scripts, jobs, and integrations
- both backend and UI observations for mixed work

Any observed bug changes the verdict to `BUGS FOUND`.

## Modes

- `backend`: verify request/response payloads, auth, validation, errors, persistence, side effects, events, queues, logs, idempotency, retries, and adjacent shared paths.
- `ui`: start the app as specified and use browser-capable evidence for happy path, loading, empty, success, error, validation, disabled, focus/active, navigation, rapid-click, double-submit, and adjacent-flow behavior.
- `mixed`: exercise both backend and UI surfaces, then verify their integration satisfies the acceptance criteria.
- `other`: exercise scripts, CLIs, scheduled tasks, data jobs, migrations, or integrations through their command/trigger path, outputs, logs, external calls, exit codes, reruns, and failure modes.

Use focused tests as supporting evidence, never as a replacement for the relevant running behavior.

## Report Format

```markdown
# QA report - <work item>

## Verdict
- <CLEAN | BUGS FOUND | QA cannot proceed>

## Mode
- <backend | ui | mixed | other>

## Metadata source
- <PR/ticket/user-supplied notes/none, plus blockers if any>

## Scope basis
- <PR, ticket, diff, changed files, entry points, setup/data needs, focused tests, regression risks>

## Coverage
- Acceptance criteria: <AC1 observed | AC2 observed | AC3 failed -> B1>
- Behavior exercised: <routes, requests, commands, states, side effects>
- Focused tests: <supporting output or explicitly none>
- Regression/adversarial checks: <list>
- Evidence: <logs, responses, browser observations, persisted state, command output, traces, screenshots, files>

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
- Required next input: <restored access, pasted PR notes, authenticated metadata source, or explicitly empty>

## Notes
- <coverage limits, degraded checks, or explicitly empty>
```

## Forbidden Behaviors

- Declaring `CLEAN` without exercising every acceptance criterion against the running surface.
- Treating unit tests, type checks, static review, or source inspection as full QA evidence by themselves.
- Inferring blocked PR testing instructions from the diff.
- Skipping adversarial inputs because the happy path works.
- Modifying product code while acting as the QA verifier.
- Omitting adjacent regression checks when changed behavior is shared by adjacent flows.
- Reporting a bug without reproduction steps and evidence.
