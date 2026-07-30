# Linear Publishing Workflow

Use this checklist when a request is ready for Linear publication.

## Readiness

1. Distinguish review or formatting from a live Linear write.
2. Resolve product scope, dependencies, and sequencing before drafting. Use
   `feature-work-planning`, then `ticket-writing`, when those collaborators are
   available; otherwise stop at the unresolved stage.
3. Confirm the source draft and every effective field are approved. On create,
   identify the actor's team membership, fetch the team's default state and
   estimate plus the applicable or selected template data, and present the
   merged effective payload; omission can apply a default. On update, an omitted
   field remains unchanged.
4. Resolve the current team, project, state, user, label, cycle, milestone,
   parent, and priority values. Reconfirm any ambiguous or substituted display
   value.
5. For epics, confirm the `Epic` label exists or obtain approval before creating
   it. Map stories to explicit sub-issues and set the project on each story.

If Linear MCP is unavailable and direct GraphQL is the chosen live route, read
[GraphQL fallback](references/graphql-fallback.md) before any live GraphQL
call. Do not read it for a working MCP route.

## Duplicate decision

For each proposed creation, fetch every page from the target project with
archived resources included. Compare title, parent, scope, description, and
status; never discard a candidate only because it is closed or archived. A
materially shared outcome, title, or description is likely overlap, especially
under the same parent. Present the identifier, title, status, parent, and
matching evidence for each candidate, then obtain one explicit decision:
`skip`, `update`, or `create anyway`.

## Mutation and reporting

Resolve entity names and approved priority to current Linear values before
mutation. Use explicit approved values to override creation defaults. Use
`null` as a suppressor only where the current Linear schema or official
documentation expressly supports it; if an approved unset value cannot be
guaranteed, stop. Confirm the target before comments and preserve approved
content. After each write, re-read the issue, compare its effective metadata
with approval, and report:

- title, identifier, and URL
- parent/child relationship
- created, updated, skipped, mismatched, or pending outcome
- unresolved defaults, metadata, or duplicate decisions

If no live integration is available, stop before mutation and report these
steps as pending rather than implying that a write occurred.
