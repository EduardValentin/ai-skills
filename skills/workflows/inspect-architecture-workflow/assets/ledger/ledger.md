# Refactoring ledger

## Run log

| Run | Date | Commit | Mode | Scope | Key | Verdict | Blocker | Major | Minor | OK |
|---|---|---|---|---|---|---|---|---|---|---|

## Changes

| Change | Description | Resolves |
|---|---|---|

## Findings

`Target` is a unit path, an edge written `from -> to` as paths, a port written `path:symbol`, or a
component ID `C<n>`, or a cycle as its sorted members joined by ` -> `. `Origin` is `introduced`
or `left` (left in place by the diff); see "Introduced or left in place" in the skill's
`references/verdicts.md`. One finding per target and rule; a target keeps its finding ID while the
same path and rule match.

| ID | Workflow | Target | Rule | Origin | Verdict | Severity | Evidence | Change | Protects | Run |
|---|---|---|---|---|---|---|---|---|---|---|

## Acceptances

One line per `ACCEPTED` finding. A one-off stays here; a standing rule is also written: a
generalized intended exception, deferred decision, or cohesion position to `decisions.md`, or a
cohesion group to `model/boundaries.json` with its explaining paragraph added to `decisions.md`.
The Promoted column names that row.

| Finding | One-off or standing | Reason | Accepted by | Date | Promoted to |
|---|---|---|---|---|---|

## Pending record updates

Record rows held back because a finding disputes their target; written when that finding is
`RESOLVED` or `ACCEPTED`.

| Finding | File | Row | Operation |
|---|---|---|---|

## Improvement map

Ordered by the highest severity a change resolves, then by rows resolved.

| Order | Change | Severity | Rows | Protects |
|---|---|---|---|---|
