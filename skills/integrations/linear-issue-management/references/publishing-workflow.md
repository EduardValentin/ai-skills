# Linear Publishing Workflow

Use this checklist when a request is ready for Linear publication.

## Readiness

1. Distinguish review/formatting from a live Linear write.
2. Resolve product scope, dependencies, and sequencing before drafting. Use `feature-work-planning`, then `ticket-writing`, when those collaborators are available; otherwise stop at the unresolved stage.
3. Confirm the source draft and every effective field are approved. On create, identify the actor's team membership, fetch the team's default state and estimate plus the applicable or selected template data, and present the merged effective payload; omission can apply a default. On update, an omitted field remains unchanged.
4. Resolve the current team, project, state, user, label, cycle, milestone, and parent IDs. Map priority to Linear's integer scalar (`0` No priority, `1` Urgent, `2` High, `3` Medium, `4` Low). Reconfirm any ambiguous or substituted display value.
5. For epics, confirm the `Epic` label exists or obtain approval before creating it. Map stories to explicit sub-issues and set the project on each story.

## Duplicate decision

For each proposed creation, fetch every page from the target project with archived resources included. Compare title, parent, scope, description, and status; never discard a candidate only because it is closed or archived. A materially shared outcome, title, or description is likely overlap, especially under the same parent. Present the identifier, title, status, parent, and matching evidence for each candidate, then obtain one explicit decision: `skip`, `update`, or `create anyway`.

## Direct GraphQL fallback

1. Use non-empty `LINEAR_API_KEY` first and reject whitespace in it. Otherwise read the file named by `LINEAR_CONFIG_PATH` as UTF-8 plaintext, trim surrounding ASCII whitespace including a final newline, and reject empty or internally whitespace-containing content. Treat the entire result as the key rather than JSON, a key/value assignment, or multiple lines; do not expose it.
2. Send named operations and variables as JSON to `https://api.linear.app/graphql`. Use the key loaded in step 1 as the raw `Authorization` header value; do not prepend `Bearer`.
3. Before creation, query viewer context, actor membership, team defaults, and applicable or selected template data. Treat `templateId` and `useDefaultTemplate` as approval-gated fields. If current effective defaults cannot be determined, stop before mutation.
4. Follow `pageInfo.hasNextPage` and `endCursor` for complete entity metadata and duplicate queries. Set `includeArchived: true` for duplicate searches.
5. Stop on a non-success HTTP status, any GraphQL `errors`, a false or missing mutation success flag, or incomplete response data. Do not retry an unverified creation until a search proves whether it happened.

## Mutation and reporting

Resolve entity names to current Linear IDs and map approved priority labels to the documented integer before mutation. Use explicit approved values to override creation defaults. Use `null` as a suppressor only where the current Linear schema or official documentation expressly supports it; if an approved unset value cannot be guaranteed, stop. Confirm the target before comments and preserve approved content. After each write, re-read the issue, compare its effective metadata with approval, and report:

- title, identifier, and URL
- parent/child relationship
- created, updated, skipped, mismatched, or pending outcome
- unresolved defaults, metadata, or duplicate decisions

If no live integration is available, stop before mutation and report these steps as pending rather than implying that a write occurred.
