# Durable map

The adopting project commits three parity files under `.parity/`. Sessions
read and extend them; snapshots, diffs and the ledger stay in the gitignored
session folder `.parity/sessions/<session>/`. `scripts/parity_map.py` checks
the map and its states file, prints one row, turns the ledger plus the map
into the capture manifest, and converts a legacy recipe folder once.

## Files

- `.parity/parity-map.md`: one row per root pair the project has ever
  verified. Ids are stable and never reused. The implementer maintains it;
  the verifier reads it and never writes it.
- `.parity/parity-pairings.json`: confirmed manual pairings, keyed by map id,
  then prototype path to real path. The verifier writes pairings it confirms
  under the row's map id.
- `.parity/parity-states.json`: the named step lists that drive each side
  into a state, read from the directory holding the map. The map's `States`
  column names its entries. The implementer maintains it; the verifier reads
  it and never writes it. A missing file reads as empty.

## States file

One JSON object keyed by state name. A name is letters, digits, dash or
underscore. Each entry takes one of two shapes:

- A step list, used on both sides: `"open-menu": [{"click": "[data-parity=\"menu\"]"}]`.
- An object with `prototype` and `real` step lists, for apps that reach the
  state differently: `"orders-empty": {"prototype": [{"click": "#dev-empty"}], "real": []}`.
  A missing side is an empty list; any other key is a problem.

A step is an object with exactly one key:

| Step | Value |
|---|---|
| `{"click": "selector"}` | Non-empty selector string. |
| `{"hover": "selector"}` | Non-empty selector string. |
| `{"press": "Key"}` | Non-empty key name, as `page.keyboard.press` takes it. |
| `{"fill": ["selector", "text"]}` | Two strings: selector, then text. |
| `{"waitFor": "selector"}` | Non-empty selector string, for an element a step makes appear. |
| `{"wait": 250}` | Non-negative integer milliseconds. Allowed but warned. |
| `{"use": "state"}` | Name of another entry, spliced in place. |

`use` expands the named entry's steps for the same side: a `use` in a
`prototype` list takes the other entry's prototype steps, and a step list
counts as both sides. Expansion is recursive; a cycle (`use cycle: a -> b ->
a`) or a chain deeper than 64 entries is a problem, as is a `use` naming an
undefined entry. An entry no map row names is a fragment: shared steps that
other entries pull in with `use`. Write a state as the shortest list that
reaches it, extending another state with `use` rather than repeating its
steps.

Readiness belongs to the capture command, which lets the page settle
(network idle, fonts, two animation frames) before the steps and waits for
network idle, the root, finished animations, fonts and two animation frames after the last step
(`capture.md`). States never carry readiness steps: no `waitFor` on the root,
no settle sleeps.

`check` reports two warnings, which do not fail it:

- `state "<name>": step <i> is a fixed wait; prefer waitFor or the capture
  tool's readiness wait`.
- `state "<name>": <side> resolves to <n> steps; split it or shorten it`,
  when a side resolves to more than 12 steps.

### Migrating recipe files

`parity_map.py migrate-actions <map>` converts a legacy
`parity-actions/*.json` folder next to the map into `parity-states.json`
once. It exits 1 with one line on stderr when that folder is missing, when
`parity-states.json` already exists, or when a recipe is not a readable
JSON array. It:

- strips the leading readiness steps, one `waitFor` then one `wait` (either
  may be absent), and every trailing `wait` from each recipe;
- merges `proto-<x>.json` and `real-<x>.json` into one two-sided entry
  `<x>`; a bare `<x>.json` beside them supplies the side without a prefixed
  file, and a name with no prefixed file stays a plain step list;
- extracts every exact shared prefix of three or more steps between plain
  step lists into a fragment named `<longer entry>-<shared length>`
  (`-2`, `-3`, ... appended when that name is taken), and rewrites every
  list that starts with those steps to `use` it;
- rewrites the map's `(<file>.json)` references to the entry names;
- prints one line per entry and fragment, the written file and the
  rewritten reference count.

It never deletes the recipe folder; delete it after `check` passes.

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
| `States` | Comma-separated `name` or `name (state)`. Names are unique per row. Each `state` is a name defined in `parity-states.json` in the map's directory. At least one state. |
| `Viewports` | Empty for the full set, or comma-separated `WxH` integers. |
| `Ignore` | Empty, or `;`-separated `proto:<entry>` and `real:<entry>` where an entry is `hook:<data-parity value>` or `path:<snapshot path prefix>` (the diff command's ignore grammar). |
| `Confidence` | `obvious` (name match) or `confirmed` (checked by hand, or the real root carries `data-parity-root` for that component). |
| `Notes` | Free text; source locators live here. |

The table starts at the first pipe row after the title. Blank lines inside
the table are skipped, not terminators; the table ends at the first non-blank
line that is not a pipe row, and any pipe row after that is reported as
`row outside the table at line N`. A literal `|` inside a cell is written
`\|` and comes back unescaped in `row` and manifest output.

Example row:

```
| C3 | OrderSummary | [data-parity-root="OrderSummary"] | /orders → /orders | default, empty (orders-empty), hover (order-hover) | 375x667, 1440x900 | proto:hook:beta; real:path:section > div:nth-of-type(2) | confirmed | none |
```

## CLI

```
parity_map.py check <map>
parity_map.py row <map> <id>
parity_map.py manifest <map> --ledger <ledger> --prototype-url U --real-url U
  --viewports WxH,... [--only-viewports WxH,...] --out <file>
parity_map.py migrate-actions <map>
```

`check` prints one line per warning, then one per problem, on stdout, and
exits 1 only when there is a problem; with neither it exits 0 silently.
Row problems read `<map>: row <id>: <problem>`, for example
`.parity/parity-map.md: row C3: Viewports "800x" is not WxH`; states file
problems read `<map>: states: <problem>`; warnings start `warning: <map>:
states: `. A header mismatch is one line quoting the header found and the
header expected. Checked: header, cell count, id format, duplicate or
non-increasing ids, empty component or root, routes arrow, state syntax and
duplicate names, viewport syntax, ignore syntax, confidence, every state
reference, which must name an entry of `parity-states.json` (a `.json`
reference is rejected with a pointer to `migrate-actions`), and the states
file itself as States file describes. An unreadable states file, or one that
is not a JSON object, is one problem line.

`row` and `manifest` run `check` first and print its warnings on stderr.
`row` then prints the row as JSON, each state with its `reference` and its
resolved `prototype` and `real` steps:

```json
{
  "id": "C3",
  "protoComponent": "OrderSummary",
  "realRoot": "[data-parity-root=\"OrderSummary\"]",
  "protoRoute": "/orders",
  "realRoute": "/orders",
  "states": [
    {"name": "default", "reference": null, "prototype": [], "real": []},
    {"name": "empty", "reference": "orders-empty", "prototype": [{"click": "#dev-empty"}], "real": []},
    {"name": "hover", "reference": "order-hover", "prototype": [{"hover": "li"}], "real": [{"hover": "li"}]}
  ],
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

- The map row supplies the routes, roots, ignore lists and state
  references. The ledger `Route` is informational; when it differs from the
  map's real route a warning goes to stderr and the map route is used.
- The ledger `State` must be one of the map row's `States`; otherwise exit 1
  naming the ledger row. A `Map id` missing from the map, or a ledger row
  with other than nine cells, also exits 1 naming the row.
- Row viewports are the map's subset or the full `--viewports`, intersected
  with `--only-viewports` when given. A row left with no viewports is emitted
  with an empty list and a stderr warning.
- `protoSteps` and `realSteps` are the state's resolved steps for each side,
  with every `use` expanded, or empty lists when the map state names no
  entry.
- `shareProto` is the id of the first manifest row with the same
  `(protoRoute, prototype component or root, protoSteps)`, so rows whose
  resolved prototype steps are equal share one capture; the first row names
  itself. The capture command captures the prototype once per group.

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
      "protoSteps": [],
      "realSteps": [],
      "shareProto": "L1"
    }
  ]
}
```

Ignore entries are the side-stripped diff grammar strings, ready for
`--ignore-prototype` and `--ignore-real`. Rechecking only some viewports is
the caller's business through `--only-viewports`.

The capture command also reads two optional top-level objects, `prototype`
and `real`, each `{"storageState": <file>, "headers": {<name>: <value>}}`,
for authenticated captures. The agent adds them to the written manifest by
hand; `manifest` never emits them. See `capture.md`, "Manifest mode".
