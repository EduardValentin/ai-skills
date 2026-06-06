---
name: ticket-qa-verification
description: Use when verifying ticket acceptance criteria, backend/API/service behavior, user-facing UI behavior, mixed API-and-UI behavior, or QA reports for a running app or service before Ship; not for visual parity, code style, implementation, or fixing bugs.
---

# Ticket QA Verification

## Overview

Own acceptance-criteria behavior verification against the running implementation. QA verifies what the app or service actually does in its real form: dev server, deployed environment, local service, job runner, API endpoint, or other executable surface.

QA is distinct from implementation, self-review, code review, and UI/UX visual verification. QA findings are reported, not fixed by the QA agent. Any bug flips the verdict to `BUGS FOUND`.

## Inputs

Expect a compact, self-contained QA request with:

- ticket title, description, and acceptance criteria
- approved requirements/design and implementation plan when available
- full diff or changed surfaces
- QA mode: `backend`, `ui`, or `mixed`
- path, command, or URL for the running app/service
- relevant credentials, seed data, feature flags, or test users when required
- known constraints, out-of-scope areas, and adjacent flows that may regress

If the implementation cannot be run or a required dependency is unavailable, do not infer behavior from code. Return `QA cannot proceed` with the exact blocker.

## Evidence Standard

QA reports require live behavior evidence. Passing unit tests, static review, local confidence, screenshots without interaction, or "the diff looks right" are useful supporting evidence, but they do not replace exercising the running app or service.

Each acceptance criterion must map to a concrete observation:

- a request/response and persisted state observation for backend/API/service work
- a browser-observed user action and resulting rendered state for UI work
- both backend and UI observations for mixed work

QA should flag suspected visual or accessibility issues as out-of-scope for UI/UX verification rather than deciding visual parity.

## Browser And Service Fallbacks

Use the best available capability to exercise the running surface:

1. Native browser or HTTP automation when available.
2. Project-local scripts, shell-invokable HTTP clients, or Playwright-style browser automation when native automation is unavailable.
3. Degraded manual confirmation only when automation cannot be used. Label the verdict as degraded and list exactly what the user must confirm.

If none of these can exercise the behavior, stop with `QA cannot proceed`.

## Modes

### Backend/API/Service Mode

Use for backend-only, API, service, job, consumer, migration, or persistence behavior.

Verify:

- service reachability
- happy paths with valid inputs
- validation failures and error responses
- auth, permission, role, and tenant boundaries where relevant
- state transitions, persistence, emitted events, queues, cache updates, and logs
- idempotency, retry, and concurrency behavior when touched
- adjacent endpoints, handlers, jobs, or consumers that share changed code paths

Inspect more than status codes. Payload, persistence, side effects, and logs must match the acceptance criteria.

### UI Mode

Use for user-facing behavior. QA is about functionality and user-observable states, not visual parity.

Verify through the live UI:

- happy path end to end
- loading, empty, success, error, and validation states
- hover, focus, active, disabled, expanded/collapsed, modal-open, and navigation states tied to behavior
- invalid values, boundary inputs, rapid clicks, double submits, and navigating mid-action
- cross-feature impact on adjacent flows visible from the feature surface
- responsive behavior when it affects functionality or state reachability

For visual parity, styling, layout polish, and detailed accessibility/contrast review, flag out-of-scope items for UI/UX verification.

### Mixed Mode

Use when the diff touches both backend/API/service behavior and user-facing behavior.

Run backend/API/service mode and UI mode. The work is not QA clean until both are clean.

## Report Format

```markdown
# QA report — <ticket title>

## Verdict
- [ ] CLEAN — no bugs found
- [ ] BUGS FOUND — at least one bug found
- [ ] QA cannot proceed — blocker named below

## Mode used
- <backend | ui | mixed>

## Coverage performed
- AC line by line: <AC1 observed | AC2 observed | AC3 failed -> B1>
- Happy paths exercised: <list>
- Error paths exercised: <list>
- State transitions: <list>
- Adversarial inputs tried: <list>
- Cross-feature regression checks: <list>
- Responsive/functionality breakpoints tested: <list or N/A>
- Evidence: <request logs, browser observations, persisted state, screenshots, traces, or command output>

## Bugs found
- **B1** | severity: <blocker | major | minor> | reproduction steps:
  1. <step>
  2. <step>
  3. <step>
  Expected: <expected behavior>
  Actual: <actual behavior>
  Suspected location: `path:line` or `path:start-end` if determinable
  Evidence: <observation>

## Out-of-scope flags
- **O1** | <surface> | <suspected visual/accessibility/code-style issue> | flagged for: <UI/UX | code review | product>

## Patterns to codify next time
- <candidate lesson or explicitly empty>
```

## Forbidden Behaviors

- Declaring `CLEAN` without exercising every acceptance criterion against the running app/service.
- Treating unit tests, type checks, static review, or implementation self-review as QA completion.
- Skipping adversarial input because the happy path works.
- Fixing bugs found during QA.
- Deciding visual parity, layout polish, or code style.
- Omitting cross-feature regression checks when changed code is shared by adjacent behavior.

## Stop Conditions

Stop when every acceptance criterion has been exercised and is either observed clean or mapped to a bug, coverage performed names what was actually checked, bugs include reproduction evidence, and out-of-scope flags are clearly routed.
