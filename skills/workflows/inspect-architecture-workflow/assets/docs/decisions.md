# Decisions

Header: audit <date> at commit <hash>, scope <scope>; last update <date> at commit <hash>, <mode>.

## Deferred decisions

| Decision | Waits behind port | Current implementation | What would force it |
|---|---|---|---|

## Cohesion groups

The groups themselves are recorded in `model/boundaries.json` and kept current with `model
add-group` and `model remove-group`; read them with `query groups`. This section holds, per
group, one paragraph on why it exists: the kind of change it absorbs and why its components
belong together.

## Cohesion position per component

| Component | Position (grouped for maintenance / for reuse / split for releases) | Accepted cost |
|---|---|---|

## Intended exceptions

Allowances the architecture stands behind, stated at component or ring level: an edge from one
component or ring to another, a layer skip, or a shared data shape. Never a single symbol; a
symbol-level acceptance belongs in the ledger. Evaluators raise no finding an exception covers.

| Exception (from component or ring -> to component or ring, or shared shape) | Reason | Risk accepted | Accepted by | Date |
|---|---|---|---|---|

## Open questions

Written by an audit, which rewrites this section in full; review modes never append here.

- <question the audit could not settle from the code>
