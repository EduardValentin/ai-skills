# Ticket Planner Evaluations

Run these scenarios with a fresh agent before changing this skill. The observed baselines that motivated this revision: ticket drafts over-included prototype-owned UI copy and treated issue creation as part of planning instead of a separate publishing concern.

## Scenario 1: Prototype Copy Boundary

Prompt:

```text
Use ticket-planner to create a story for the onboarding screen. The React prototype shows the button text, helper text, and placeholders.
```

Expected behavior:

- References the prototype route/screen/state.
- Does not repeat button text, helper text, or placeholders.
- Includes exact copy only if the user asks or the copy is business-critical.

## Scenario 2: Tracker Unavailable

Prompt:

```text
Turn the PRD dashboard section into user stories. The issue tracker is not connected.
```

Expected behavior:

- Produces platform-neutral story drafts.
- Does not treat tracker access as required for planning.
- Does not include tracker-specific metadata or creation steps.

## Scenario 3: PRD Update Approval

Prompt:

```text
Clarification: archived plans stay visible to coaches forever but clients cannot see them.
```

Expected behavior:

- Identifies this as a business rule.
- Proposes a concise PRD update.
- Asks before editing `PRD.md`.

## Scenario 4: Implementation Leakage

Prompt:

```text
Draft a ticket from this React component file.
```

Expected behavior:

- Converts component details into product behavior.
- Avoids component names, CSS classes, file paths, and framework-specific implementation details.
- Includes prototype references where useful.

## Scenario 5: Vertical Slice Pressure

Prompt:

```text
Split this feature into tickets: database schema, API, frontend, and notifications.
```

Expected behavior:

- Pushes back on layer-sliced tickets.
- Proposes vertical stories organized around user outcomes.
- Each story names the relevant UI, API, data, permissions, and notification integration points.

## Scenario 6: Publish To Tracker

Prompt:

```text
These approved story drafts look good. Publish them to our issue tracker.
```

Expected behavior:

- Stops using ticket-planner as the publishing workflow.
- Checks `README.md`, `AGENTS.md`, and project docs for issue-tracker conventions.
- Asks the user which tracker to use if the project docs do not make it clear.
- Switches to the relevant tracker-specific issue writing skill if available.
- Treats the approved drafts as source material instead of inventing new product scope.

## Scenario 7: No PRD Or Prototype

Prompt:

```text
Create user stories for a new team invitation feature. There is no PRD or prototype yet.
```

Expected behavior:

- Does not draft stories immediately.
- Runs a requirements interview covering users, flow, data, permissions, integrations, edge cases, and out of scope.
- Produces a shared-understanding brief.
- Waits for user approval of the brief before drafting stories.
