# Report format

## Evidence standard

The snapshot is the evidence. It covers font, color, effective background,
box, layout, flex and grid placement, geometry relative to the root,
transform, role, accessible name, focusability, ARIA state and contrast.
Evidence status labels: `complete DOM evidence` when every row has diff
files for every viewport, `partial DOM evidence` when some rows do,
`degraded manual evidence` when a row's verdict rests on anything other than
a diff file, `no comparison evidence` otherwise. Degraded evidence may
support a provisional `DRIFT` for a clearly visible defect with the missing
diff stated; it can never support `MATCH` or `CLEAN`. `EXPECTED` rows pass
on their own and always carry the reason the difference is intended.

## Report template

Return the ledger path with the updated rows, then this report:

```markdown
# Visual parity verification — <surface>

## Verdict
- <CLEAN | FINDINGS | BLOCKED>

## Evidence status
- <complete DOM evidence | partial DOM evidence | degraded manual evidence | no comparison evidence>

## Basis
- <prototype URL and routes>

## Matched conditions
- viewport set: <widths x heights> | zoom: <percent> | device scale: <factor> | theme: <theme>

## Ledger rows written
- <count MATCH> MATCH | <count EXPECTED> EXPECTED | <count DRIFT> DRIFT | <count MISSING> MISSING | <count BLOCKED> BLOCKED

## Findings
- **P1** | severity: <blocker / major / minor> | ledger row <id> | <path property> | evidence: <prototype value vs real value> | diff: <relative diff path>

## Structure and content notes
- <moved nodes, collapsed-count differences, content mismatches, or None>

## Accessibility findings
- **A1** | severity: <blocker / major / minor> | ledger row <id> | <check> | WCAG criterion | suggested fix

## Pairings confirmed
- <row id: prototype path to real path, or None>

## Expected
- <row id — reason, one per EXPECTED row, or None>

## Ledger provenance gaps
- <rows appended for visible in-scope surfaces the map omitted, or None>

## Blockers
- <None, or blocked row and minimum next input>

## Rerun delta
- <None, or resolved, remaining and new rows>
```

Write explicit `None` in every empty section.
