# Durable map

The adopting project commits three parity files at its root. Sessions read
and extend them; snapshots, diffs and the ledger stay in the gitignored
session folder. `scripts/parity_map.py` checks the map, prints one row, and
turns the ledger plus the map into the capture manifest.

## Files

- `parity-map.md`: one row per root pair the project has ever verified. Ids
  are stable and never reused. The implementer maintains it; the verifier
  reads it and never writes it.
- `parity-pairings.json`: confirmed manual pairings, keyed by map id, then
  prototype path to real path. The verifier writes pairings it confirms
  under the row's map id.
- `parity-actions/<name>.json`: optional action recipes, named from the
  map's `States` column. One recipe serves both sides of a row.

## Map contract

Header, exactly:

```
| Id | Prototype component | Real app root | Routes (real → prototype) | States | Viewports | Ignore | Confidence | Notes |
```

| Column | Value |
|---|---|
| `Id` | `C<n>`, unique, strictly increasing down the table. |
| `Prototype component` | React component name, or `root:<selector>` to address the prototype side by selector. |
| `Real app root` | CSS selector or `data-parity-root` value, passed through to the capture command. |
| `Routes (real → prototype)` | `<real route> → <prototype route>`; `->` is also accepted. Exactly one arrow, with a space on both sides; both sides non-empty. |
| `States` | Comma-separated `name` or `name (file.json)`. Names are unique per row. With `--project-root`, each file must exist under `<root>/parity-actions/`. At least one state. |
| `Viewports` | Empty for the full set, or comma-separated `WxH` integers. |
| `Ignore` | Empty, or `;`-separated `proto:<entry>` and `real:<entry>` where an entry is `hook:<data-parity value>` or `path:<snapshot path prefix>` (the diff command's ignore grammar). |
| `Confidence` | `obvious` (name match) or `confirmed` (checked by hand). |
| `Notes` | Free text; source locators live here. |

The table starts at the first pipe row after the title. Blank lines inside
the table are skipped, not terminators; the table ends at the first non-blank
line that is not a pipe row, and any pipe row after that is reported as
`row outside the table at line N`. A literal `|` inside a cell is written
`\|` and comes back unescaped in `row` and manifest output.

Example row:

```
| C3 | OrderSummary | [data-parity-root="OrderSummary"] | /orders → /orders | default, empty, hover (order-hover.json) | 375x667, 1440x900 | proto:hook:beta; real:path:section > div:nth-of-type(2) | confirmed | none |
```

## CLI

```
parity_map.py check <map> [--project-root DIR]
parity_map.py row <map> <id>
parity_map.py manifest <map> --ledger <ledger> --prototype-url U --real-url U
  --viewports WxH,... [--only-viewports WxH,...] [--project-root DIR] --out <file>
```

`check` exits 0 silently or exits 1 with one line per problem on stdout,
each `<map>: row <id>: <problem>`, for example
`parity-map.md: row C3: Viewports "800x" is not WxH`. A header mismatch is
one line quoting the header found and the header expected. Checked: header,
cell count, id format, duplicate or non-increasing ids, empty component or
root, routes arrow, state syntax and duplicate names, viewport syntax,
ignore syntax, confidence, and referenced action files when `--project-root`
is given.

`row` runs `check` first, then prints the row as JSON:

```json
{
  "id": "C3",
  "protoComponent": "OrderSummary",
  "realRoot": "[data-parity-root=\"OrderSummary\"]",
  "protoRoute": "/orders",
  "realRoute": "/orders",
  "states": [{"name": "default", "actions": null}, {"name": "hover", "actions": "order-hover.json"}],
  "viewports": ["375x667", "1440x900"],
  "ignore": {"prototype": ["hook:beta"], "real": ["path:section > div:nth-of-type(2)"]},
  "confidence": "confirmed",
  "notes": "none"
}
```

A `root:<selector>` component emits `protoRoot` instead of `protoComponent`.
An unknown id exits 1 with a message on stderr.

## Manifest

`manifest` runs `check` first, then reads every row of the ledger's
`## Elements` table in order, whatever its verdict, and joins it with the map
row named in `Map id`:

- The map row supplies the routes, roots, ignore lists and action files. The
  ledger `Route` is informational; when it differs from the map's real route
  a warning goes to stderr and the map route is used.
- The ledger `State` must be one of the map row's `States`; otherwise exit 1
  naming the ledger row. A `Map id` missing from the map, or a ledger row
  with other than nine cells, also exits 1 naming the row.
- Row viewports are the map's subset or the full `--viewports`, intersected
  with `--only-viewports` when given. A row left with no viewports is emitted
  with an empty list and a stderr warning.
- `protoActions` and `realActions` are the same path,
  `<project-root or map directory>/parity-actions/<file>`, or null when the
  state names no file.
- `shareProto` is the id of the first manifest row with the same
  `(protoRoute, prototype component or root, protoActions)`; the first row
  names itself. The capture command captures the prototype once per group.

```json
{
  "prototypeUrl": "http://localhost:5173",
  "realUrl": "http://localhost:8000",
  "viewports": ["375x667", "1024x768", "1440x900"],
  "rows": [
    {
      "id": "L1",
      "mapId": "C3",
      "protoRoute": "/orders",
      "realRoute": "/orders",
      "protoComponent": "OrderSummary",
      "realRoot": "[data-parity-root=\"OrderSummary\"]",
      "viewports": ["375x667", "1440x900"],
      "ignore": {"prototype": ["hook:beta"], "real": ["path:section > div:nth-of-type(2)"]},
      "protoActions": null,
      "realActions": null,
      "shareProto": "L1"
    }
  ]
}
```

Ignore entries are the side-stripped diff grammar strings, ready for
`--ignore-prototype` and `--ignore-real`. Rechecking only some viewports is
the caller's business through `--only-viewports`.
