# Parity ledger

Session: <ticket id or branch>
Component map: component-map.md
Viewport set: <widths used, including one below and one above each breakpoint>
Theme: <theme or light>

## Elements

One row per user-visible element added or modified in this session, per
meaningful state. The implementer fills every column except `Verdict` and
`Evidence`, which the parity verifier writes. A row starts as `PENDING`. The
session cannot raise a PR while any row is not `MATCH`.

| Id | Map id | Route | State | Production selector | Prototype selector | Change | Verdict | Evidence |
|---|---|---|---|---|---|---|---|---|
| L1 | C1 | <route> | <state> | <stable selector> | <stable selector> | <added / modified / design-change> | PENDING | |

## Design changes

One row per design decision made in this session. The prototype changes
first. A production-first change is a rule violation that is remediated in
the same session by updating the prototype; both columns must read yes before
the parity step runs.

| Id | What changed | Changed first in | Prototype updated | Production updated | Ledger rows |
|---|---|---|---|---|---|
| D1 | <token, primitive, layout or copy change> | <prototype / production> | <yes / no> | <yes / no> | <L ids> |
