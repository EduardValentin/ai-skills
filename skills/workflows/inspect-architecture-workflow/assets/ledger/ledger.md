# Refactoring ledger

## Run log

| Run | Date | Commit | Mode | Scope | Verdict | Blocker | Major | Minor | OK |
|---|---|---|---|---|---|---|---|---|---|

## Changes

| Change | Description | Resolves |
|---|---|---|

## Findings

`Target` is one inventory row ID: a unit `U<n>`, an edge `E<n>`, a boundary `B<n>`, or a component
`C<n>`. One finding per target and rule; IDs are stable across runs.

| ID | Workflow | Target | Rule | Verdict | Severity | Evidence | Change | Protects | Run |
|---|---|---|---|---|---|---|---|---|---|

## Acceptances

One line per `ACCEPTED` finding. A one-off stays here; a standing rule is also written to
`decisions.md` as a generalized intended exception, cohesion group, deferred decision, or
cohesion position, and the Promoted column names that row.

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
