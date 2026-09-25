# Parity ledger

Session: <ticket id or branch>
Parity map: parity-map.md (committed at the project root)
Viewport set: <widths used, including one below and one above each breakpoint>
Theme: <theme or light>

## Elements

One row per touched `parity-map.md` row, per meaningful state; `Map id` is
that row's id and `State` is one of its `States` names. The implementer
fills every column except `Verdict` and `Evidence`, which the parity
verifier writes from diff files. A row starts as `PENDING`. An `EXPECTED`
row carries the reason for its accepted difference in `Evidence`. The
session cannot raise a PR while any row is not `MATCH` or `EXPECTED`.

| Id | Map id | Route | State | Prototype root | Real app root | Change | Verdict | Evidence |
|---|---|---|---|---|---|---|---|---|
| L1 | C1 | <route> | <state> | <ComponentName> | <selector or data-parity-root value> | <added / modified / design-change / provenance gap> | PENDING | |

## Design changes

One row per design decision made in this session. The prototype changes
first. A production-first change is a rule violation that is remediated in
the same session by updating the prototype; both columns must read yes before
the parity step runs. A difference the user accepted is a row whose `What
changed` starts with `accepted:` followed by the reason; the verifier writes
that reason as `EXPECTED` into every ledger row the `Ledger rows` cell lists.

| Id | What changed | Changed first in | Prototype updated | Production updated | Ledger rows |
|---|---|---|---|---|---|
| D1 | <token, primitive, layout or copy change> | <prototype / production> | <yes / no> | <yes / no> | <L ids> |
