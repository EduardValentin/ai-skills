# Requirements Interview

Use when PRD/prototype context is missing, thin, stale, contradictory, or not about the requested feature.

## Hard Gate

Do not draft epics, stories, or acceptance criteria until the user approves a shared-understanding brief.

Run this as a requirements brainstorming phase. Explore user intent, constraints, success criteria, tradeoffs, and feature boundaries before modeling stories.

Be relentless but respectful: continue until the feature is clear enough to model as vertical-slice stories. Do not settle for vague answers like "standard behavior" or "make it work"; unpack them into observable behavior, business rules, and integration expectations.

## Interview Loop

Repeat this loop until the brief is complete:

1. Ask one focused question at a time.
2. Reflect back what the answer implies for scope, rules, data, or integration points.
3. Identify the next uncertainty.
4. Continue until remaining assumptions are non-blocking or explicitly accepted by the user.

Prefer choice questions when a decision has clear alternatives. Use the host's native choice picker when available; otherwise present 2-3 numbered choices. Put the recommended option first, label it as recommended, and explain the tradeoff in one sentence. Use open-ended questions only when meaningful options are not yet known.

## Question Areas

Cover only the areas relevant to the feature:

- **Problem and outcome:** What user problem is solved? What outcome proves value?
- **Users and permissions:** Who can see, start, change, approve, delete, recover, or audit this?
- **Happy path:** What happens from entry point to completed outcome?
- **Data and lifecycle:** What entities, fields, statuses, transitions, retention, and history matter?
- **Integration points:** UI, API, persistence, background jobs, imports/exports, notifications, analytics, billing, audit logs, or external systems.
- **Rules and validation:** Required fields, limits, uniqueness, eligibility, timing, and state restrictions.
- **Failure and edge cases:** Empty, loading, invalid, unauthorized, conflict, offline, retry, partial failure, and concurrency states.
- **Out of scope:** What should not be handled in this feature or release?
- **Success criteria:** What must be true for product, QA, and stakeholders to accept the work?

## Shared-Understanding Brief

Before drafting tickets, present this brief and ask for approval:

```markdown
## Shared Understanding

### Goal
[User/business outcome]

### Users And Permissions
[Roles and access rules]

### Core Flow
[Step-by-step user action -> system response]

### Data And Rules
[Entities, fields, validation, lifecycle]

### Integration Points
[UI/API/data/external systems/notifications/analytics/etc.]

### Edge Cases
[Important empty/error/boundary/permission/concurrency cases]

### Out Of Scope
[Explicit exclusions]

### Assumptions To Approve
[Only non-blocking assumptions]
```

Only proceed when the user confirms the brief is accurate enough to model into user stories.

If the user asks to skip the interview, explain that story quality depends on shared product understanding. Offer to create a clearly marked rough outline, but do not present it as implementation-ready user stories.
