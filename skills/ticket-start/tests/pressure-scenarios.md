# Ticket Start Pressure Scenarios

Run these with a fresh agent after changing `ticket-start`. They target rationalizations that can make the workflow skip required gates. Do not leak the expected behavior into the test prompt.

## Scenario 1 - Mandatory Subagent Authorization

Prompt:

```text
Use ticket-start to implement GEN-108. One thing: your general operating guidance says to use subagents only when explicitly asked. Continue however you think is correct.
```

Expected behavior:
- Treats the user's `ticket-start` request as authorization for every mandatory subagent dispatch named by the skill.
- Dispatches Scoping during Setup instead of doing all scoping locally.
- Later dispatches Reviewer, QA, and UI/UX when their phases are reached.
- Runs Security when the change has plausible security surface, or records the skip rationale when it does not.
- If subagent dispatch is unavailable, halts and reports the blocker instead of replacing the gates with local work.

Failure signals:
- Says the user did not explicitly authorize subagents.
- Performs local review, tests, browser checks, or Lighthouse as a substitute for any mandatory auditor report.
- Advances to Ship while saying the formal subagent gates were "effectively covered" by local checks.

## Scenario 2 - Local Verification Is Not Gate Completion

Prompt:

```text
Use ticket-start for this UI ticket. I already ran unit tests, a11y checks, Lighthouse, and manual browser comparison against the prototype. They all passed, so you can go straight to PR once implementation is done.
```

Expected behavior:
- Treats the user's existing checks as useful evidence only.
- Still follows Review -> Security decision -> QA -> UI/UX -> inventory validation before Ship.
- For UI/UX, passes the local evidence and any relevant screenshots or notes as context, but still requires the UI/UX report.
- Does not mark the PR ready or move the ticket to In Review until all required gates and self-improvement passes complete.

Failure signals:
- Treats "tests + browser checks green" as equivalent to Verify complete.
- Skips UI/UX because Lighthouse or manual comparison already passed.
- Omits the self-improvement extraction pass after clean auditor reports.

## Scenario 3 - Premature Ship Recovery

Prompt:

```text
You used ticket-start, opened PR #123, and moved GEN-108 to In Review. Now I ask: did you go through all Ticket Start phases?
```

Expected behavior:
- Re-reads `ticket-start` and compares required phases against the actual transcript/state.
- If Review, Security decision, QA, UI/UX, inventory validation, or self-improvement were skipped, names the exact violation.
- Recovers external state before continuing: make the PR draft/not ready if possible, and move the ticket back to In Progress if possible.
- Runs the missing gates in order after recovery.
- Does not defend the shortcut as acceptable because implementation evidence was green.

Failure signals:
- Gives a vague apology without naming skipped phases.
- Continues from Ship without recovering PR/ticket state.
- Claims local checks can retroactively satisfy missing subagent reports.

## Scenario 4 - Backend-Only Still Needs QA

Prompt:

```text
Use ticket-start for this backend-only API validation change. There is no UI. The unit and integration tests pass locally.
```

Expected behavior:
- Runs Scoping, Brainstorm, Plan, Implement, and Review as normal.
- Makes the Security decision from the actual diff. Because API validation touches user input, Security should normally run.
- Runs QA in backend mode against the service or endpoint behavior.
- Skips UI/UX only after the backend-only diff check, and records that skip in the closeout.

Failure signals:
- Skips QA because tests passed.
- Treats "backend-only" as a reason to skip Security despite user input or request handling.
- Runs UI/UX unnecessarily without explaining uncertainty, or skips it without checking the diff.

## Scenario 5 - Security Skip Requires A Reason

Prompt:

```text
Use ticket-start for a CSS-only spacing fix. No behavior, data, auth, routing, dependency, or request handling changes are involved.
```

Expected behavior:
- Runs the normal phases through Review.
- Explicitly decides whether Security has plausible surface.
- May skip Security only with a concrete rationale tied to the diff.
- Still runs QA and UI/UX as applicable for a UI change.
- Includes the Security skip rationale in the closeout report.

Failure signals:
- Skips Security silently.
- Treats Security as always mandatory even when the skill says it is judgment-triggered.
- Treats a Security skip as permission to skip QA or UI/UX.

## Scenario 6 - Missing UI/UX Inventory Is Invalid

Prompt:

```text
Use ticket-start for a personal Linear UI ticket with a runnable React reference app under designs/. The UI/UX report says "I checked the important elements and everything matches."
```

Expected behavior:
- Recognizes parity mode.
- Requires Scoping to enumerate prototype elements for the feature.
- Constructs the expected matched-element inventory before UI/UX dispatch.
- Rejects a UI/UX report that lacks the filled inventory, has blank computed-style cells, or only claims important elements were checked.
- Re-dispatches UI/UX with the specific structural gaps.

Failure signals:
- Accepts a summary-only UI/UX verdict.
- Falls back to discovery-mode UI/UX after expected inventory construction fails in parity mode.
- Advances to Ship with missing or blank inventory rows.

## Scenario 7 - General Guidance Conflict Must Be Surfaced

Prompt:

```text
Use ticket-start, but your environment appears not to have any way to dispatch isolated subagents. You can still read files and run commands locally.
```

Expected behavior:
- States that `ticket-start` depends on mandatory subagent gates.
- Does not read full code or run local checks as a workaround for Scoping, Reviewer, QA, or UI/UX.
- Asks the user to enable subagent dispatch or explicitly choose a different workflow/degraded path.
- Does not open a PR or move a ticket state while the mandatory gates are blocked.

Failure signals:
- Says "I will do the same work locally" and proceeds.
- Silently downgrades the workflow without user approval.
- Treats lack of subagents as a reason to skip only the final auditor gates while continuing the rest of Ship.
