# Job Workflow

Use when the ticket comes from Jira or is pasted by the user. Loaded by `SKILL.md` during the Setup phase. Return to `SKILL.md` for phase ordering, standards, and closeout.

## Ticket Intake

1. Require the full ticket title and full description before starting. The description must include acceptance criteria and any implementation context the user has. If any of these are missing, stop and ask.
2. Do not accept a partial summary when the full title or description is required to implement safely. Stale or excerpted retellings are not current truth.
3. Extract and restate:
   - acceptance criteria
   - constraints
   - explicit context the user provided
   - non-goals, if present
   - open ambiguities that could change the implementation

## Clarifications

- Ask concise clarifying questions whenever the ticket leaves material ambiguity. Prefer a short focused set over broad brainstorming.
- If acceptance criteria are missing, vague, or not testable, stop and ask before continuing.
- If the ticket conflicts with repository instructions or existing architecture, surface the conflict before implementation.

## Architecture Research

Gather only the minimum code context needed to understand the current architecture and the implementation path. Prefer:

- the entry point or feature boot path
- the target module or component
- nearby reducers, services, fetchers, transformers, hooks, tests, or shared utilities that define the current pattern
- existing implementations of similar behavior in the repo

Reuse existing project patterns before inventing new abstractions. Aim for the smallest safe diff that satisfies the ticket cleanly.

## Hand-off To Brainstorm

When the ticket is concrete enough and the architecture findings are gathered, return to `SKILL.md` and proceed to the Brainstorm gate (`superpowers:brainstorming`).

## Verification (Required Before PR)

Loaded during the Verify phase. Run after the targeted tests and broader suite pass. Type checks and unit tests verify code correctness, not feature correctness — manual feature exercise is the evidence `superpowers:verification-before-completion` requires for a "feature works" claim on a ticket. Without it, there is no basis to declare the work done.

Pick the mode that matches the change. If the ticket touches both a service and a UI, run both modes.

### Mode A — Backend / API / Service Change

1. Start the affected service locally (or use the dev environment the repository instructions specify). If the service cannot be started, stop and surface the blocker — do not declare the feature verified.
2. Issue real requests against the changed endpoints, jobs, handlers, or message consumers. Use `curl`, the project's HTTP client, or an HTTP MCP tool. Do not substitute unit tests for live requests.
3. Cover, at minimum:
   - Happy path for every flow the ticket implements.
   - Each documented input variation, including boundary values.
   - Validation failures and error responses (4xx, 5xx, domain errors).
   - Auth and permission boundaries (authenticated vs unauthenticated, role gates, tenant isolation).
   - State transitions the change introduces or modifies.
   - Idempotency, retry, and concurrency behavior if the change touches them.
4. Inspect more than the status code — verify response payloads, persisted state (DB rows, queue messages, cache entries), emitted events, and logs match the acceptance criteria.
5. If a defect is found, fix it and re-run the affected portion. Do not skip back to declaring done.

### Mode B — User-Facing App / UI Change

1. Start the app on its dev server. Open it in the live browser session via the Playwright MCP tools. If either the app or the browser session cannot be brought up, stop and surface the blocker — do not declare the feature verified.
2. Drive the feature through every state and scenario the ticket affects:
   - Happy path end-to-end.
   - Loading, empty, success, error, and validation states.
   - Hover, focus, active, disabled, expanded/collapsed, modal-open, and any navigation states tied to the feature.
   - Adversarial input: invalid values, out-of-range values, rapid clicks, double submits, navigating mid-action.
   - Cross-feature impact: adjacent flows visible from the feature's surface area must not regress.
   - Responsive behavior at the relevant breakpoints, including widths immediately before and after each breakpoint.
3. After each meaningful action, inspect the UI to confirm it still looks correct and behaves correctly. Use the browser snapshot/screenshot tools rather than guessing from console output.
4. If a defect is found, fix it and re-run the affected portion. Do not skip back to declaring done.

### Mode C — Mixed Change

Run Mode A and Mode B both. The feature is not verified until each mode that applies is clean.

### Outcome

Only after the applicable mode(s) are clean is the Verify gate satisfied. Report what was exercised and how in the closeout, distinguishing API verification from browser verification when both ran. If any portion could not be exercised, name it explicitly as unverified — do not paper over it.
