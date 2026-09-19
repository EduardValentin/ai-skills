# Decisions

Header: date <date>, commit <hash>, scope <scope>.

## Deferred decisions

| Decision | Waits behind port | Current implementation | What would force it |
|---|---|---|---|

## Cohesion groups

Sets of components expected to change together for one kind of reason. A change whose touched
components all sit in one group is expected; one that spreads across groups is a finding unless
accepted below. A component may belong to more than one group. Proposed by an audit from change
history; confirmed by a person.

| Group | Components | Kind of change it absorbs |
|---|---|---|

## Cohesion position per component

| Component | Position (grouped for maintenance / for reuse / split for releases) | Accepted cost |
|---|---|---|

## Intended exceptions

| Exception (layer skip, direct edge, shared shape) | Reason | Risk accepted | Accepted by | Date |
|---|---|---|---|---|

## Accepted findings

Keyed by the target's path and symbol and the rule, never by a ledger ID; ledger IDs are
transitory and must not appear in any committed file.

| Target (path and symbol, or edge as from -> to) | Rule | Reason accepted | Accepted by | Date |
|---|---|---|---|---|

## Open questions

- <question the inspection could not settle from the code>
