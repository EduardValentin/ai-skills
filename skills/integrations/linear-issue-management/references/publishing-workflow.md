# Linear Publishing Workflow

Use this checklist when a request is ready for Linear publication.

## Readiness

1. Distinguish review/formatting from a live Linear write.
2. Confirm the source draft is approved and fully planned. Route missing draft work to `ticket-writing` and unresolved product planning to `feature-work-planning` when those collaborators are available; otherwise stop and request approved source material.
3. Confirm the target project and team. For epics, confirm the `Epic` label exists or obtain approval to create it.
4. Map epics to labeled project issues and stories to explicit sub-issues. Set the project on each story.
5. Obtain approval for the exact title, description, parent, project, team, labels, priority, estimate, assignee, cycle, milestone, due date, and any other requested metadata.

## Duplicate decision

For each proposed creation, fetch issues from the target project and compare title, parent, scope, description, and status. Include closed or archived candidates when relevant. Present every likely overlap and obtain one explicit decision: `skip`, `update`, or `create anyway`.

## Mutation and reporting

Resolve workspace names to current Linear IDs before mutation. Use explicit IDs in create/update variables, confirm the target before comments, and preserve approved content. After each write, re-read the issue and report:

- title, identifier, and URL
- parent/child relationship
- created, updated, skipped, or pending outcome
- unresolved metadata or duplicate decisions

If no live integration is available, stop before mutation and report these steps as pending rather than implying that a write occurred.
