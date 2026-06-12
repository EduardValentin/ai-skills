# Ticket Quality

## User Story Template

Every user story should use this structure:

```markdown
Title: [Plain outcome the work accomplishes, not how it is built]

## Overview

[1-3 sentences: persona or role, user need, business value, and feature context. Make clear what user-observable outcome this story delivers.]

## Acceptance Criteria

- [ ] [Clear, observable, testable outcome]
- [ ] [Clear, observable, testable outcome]

## Product And Delivery Notes

- **Data and rules:** Entities, fields, permissions, validation, lifecycle rules
- **User flow:** User action -> system response
- **Integration points:** UI, API, persistence, permissions, external services, notifications, analytics, or other affected systems
- **Edge cases:** Empty, loading, error, permission, boundary, and concurrency states
- **Dependencies:** Related stories, integrations, blocked-by relationships
- **Source context:** PRD sections, prototype routes/states, feature brief, plan, or approved shared-understanding brief
- **Out of scope:** Explicit exclusions, if useful
```

## Ticket Writing Rules

- Title the work by the outcome, not by mechanism, parameters, files, or implementation steps.
- Keep the business case and technical details separate: `Overview` explains why/what in plain language; `Product And Delivery Notes` explains how, constraints, interfaces, paths, and edge cases.
- Put concrete pass/fail checks in the dedicated `Acceptance Criteria` section. Do not bury acceptance criteria in prose.
- Make every ticket self-contained. Replace opaque plan/spec section references or roadmap codes with a plain descriptor plus the linked ticket ID.
- Trim noise, not substance. Preserve real technical details such as interfaces, paths, behaviors, edge cases, contracts, and dependencies.
- If a ticket feels too large to hold in your head, tighten verbose context and split by user outcome or delivery risk until the scope is clear.
- For parent/child work, keep parents high-level. Children are the authoritative implementation spec; do not duplicate child implementation details on the parent.
- When a ticket defines outputs or contracts, state exactly what is produced and under which conditions: events, fields, API responses, files, schemas, messages, or state transitions.
- Reformat dense identifier paragraphs into one lead-in sentence plus a formatted block. In aligned identifier/value blocks, prefix human-readable explanations with comment markers; leave pure value lists and identifier-to-identifier mappings unmarked.
- Keep related tickets consistent with the latest agreed decisions. When a decision changes, fix stale names, omitted items, and contradictions across the full related set.

## Vertical Slice Standard

Stories should be vertical slices, not layer slices.

Good vertical slices:

- Deliver one user-visible outcome.
- Include all work needed across UI, service/API, data, permissions, and integrations when those layers are relevant.
- Exercise the feature's integration path early enough to surface product, technical, permission, data, and external-system issues in that story.
- Do not require completing additional layer-specific stories before integration problems become visible.
- Can be tested through public behavior.
- Leave the product in a coherent state if shipped independently.

Avoid layer slices:

- "Build database schema"
- "Create API endpoints"
- "Implement frontend screen"
- "Wire up state management"

If a layer has no user-observable value by itself, capture it as part of the story's delivery notes or split it only when risk/dependency requires a separate enabling story. When an enabling story is unavoidable, name the first follow-up vertical story that will exercise it.

## Integration Coverage

For each story, scan the feature end to end and include the relevant integration points:

- **Entry point:** Where the user starts the flow.
- **State/data:** What data is read, written, validated, or transformed.
- **Permissions:** Who can see, start, edit, delete, approve, or recover the work.
- **System response:** What changes immediately, what persists, and what other surfaces update.
- **External effects:** Messages, notifications, billing, audit logs, analytics, imports/exports, or third-party calls.
- **Failure handling:** What happens when validation, permissions, persistence, or external calls fail.

Do not invent integration points that the source context does not imply. Ask when an integration would change scope or business behavior.

## Epic Template

Epics should use:

```markdown
Title: [Plain feature capability or business outcome]

## Overview

[Feature area, user/business goal, and why this work matters.]

## Scope

- [Included capability]
- [Included capability]

## Candidate Stories

- [Story title]
- [Story title]

## Notes

- **Prototype source:** [routes/screens/flows]
- **Source context:** [PRD sections, prototype routes/screens, feature brief, plan, or approved interview brief]
- **Open questions:** [only unresolved product decisions]
```

## Acceptance Criteria Standards

Acceptance criteria must be:

- Clear: one interpretation for product, engineering, QA, and design.
- Testable: objectively pass/fail.
- Outcome-focused: describe what the user or system can do, not how to implement it.
- Scoped: define done for this story, not the whole epic.
- Prototype-aware: reference prototype states instead of copying visual details.
- Integration-aware: cover the required end-to-end behavior without turning internal layers into separate tickets.

Avoid:

- "Works correctly"
- "Looks like the design" with no route/state reference
- Exact prototype copy unless allowed by the copy policy
- Component names, CSS details, file paths, database table names, or library choices unless the user explicitly wants implementation tasks

## Story Sizing Heuristics

A good story is small enough to implement and review independently, but large enough to deliver observable value. Split a story when:

- It includes multiple unrelated user goals.
- It has separate permission models.
- It spans unrelated data lifecycles.
- It needs independent release, testing, or rollback.
- Its integration points create materially different failure modes.

Do not split just because the prototype has multiple UI components. Split by behavior and delivery risk.

## Clarifying Question Standard

Ask questions only when the answer changes scope, rules, sequencing, acceptance criteria, or draft attributes. Batch them by topic.

If a detail is non-blocking, state it as an assumption in the draft:

```markdown
Assumption for approval: archived plans remain visible to coaches but read-only.
```

## Draft Review Self-Check

Before requesting approval, verify:

- Happy path is defined.
- Empty, loading, error, and permission states are covered when relevant.
- Business validations are explicit.
- Cross-feature dependencies are named.
- Available source context is referenced.
- Prototype-owned copy and styling are not duplicated.
- Any assumptions are clearly labeled.
