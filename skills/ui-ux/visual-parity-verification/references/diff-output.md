# Diff output

`diff_snapshots.py` writes one JSON file per row and viewport and prints one
summary line.

## Summary line

```
<VERDICT> style=<n> geometry=<n> missing=<n> structure=<n> content=<n> accessibility=<n> lowestScore=<0.00 | n/a>
```

A blocked run prints `BLOCKED <reason>` before the counts.

## Top level

| Field | Meaning |
|---|---|
| `verdict` | `MATCH`, `DRIFT`, `MISSING` or `BLOCKED` |
| `conditions` | `viewport`, `devicePixelRatio`, `zoom`, `colorScheme` shared by both snapshots |
| `urls` | `prototype` and `real` page URLs |
| `rootSummaries` | Both root summaries |
| `blocked` | `null`, or `{ reason, detail }` with reason `condition-mismatch`, `roots-incompatible` or `unmeasurable-contrast` |
| `pairs` | Every aligned pair: `prototype` path, `real` path, `matchedBy`, `score`, `signals` |
| `findings` | Lists per category, below |
| `collapsed` | Collapsed wrapper nodes per side: `path`, `tag`, `childCount` |
| `suggestions` | For each unmatched node: `side`, `path`, best `candidate` path and its `score` |
| `lowestScore` | Lowest score among pairs matched by score, or `null` |

`matchedBy` is one of `root`, `pairing`, `hook`, `role-name`, `text`,
`score`, `moved`. Review every `score` pair below 0.7 and every suggestion.

## Findings

| Category | Item fields | Verdict input |
|---|---|---|
| `style` | `path`, `realPath`, `property`, `prototype`, `real` | yes |
| `geometry` | `path`, `realPath`, `property` in `x`, `y`, `width`, `height`, `prototype`, `real` | yes |
| `missing` | `side`, `path`, `tag`, `role`, `name`, `suggestion` | yes |
| `structure` | `kind` `moved` with `prototype` and `real` paths, or `kind` `collapsed-count` with both counts | no |
| `content` | `path`, `realPath`, `prototype`, `real` own text | no |
| `accessibility` | `side`, `path`, `check` in `missing-role`, `missing-name`, `contrast`; contrast adds `ratio` and `threshold` | findings only |

Semantic differences in `role`, `name`, `focusable`, `tabIndex` and `state`
are reported under `style` with the field name as `property`.

## Verdict rules

1. `BLOCKED` when a precondition failed or any text node has unmeasurable
   contrast.
2. `DRIFT` when any `style` or `geometry` finding exists.
3. `MISSING` when any `missing` finding exists and no `DRIFT`.
4. `MATCH` otherwise.

## Tolerances

Defaults, overridable with `--tolerances <file.json>`:

```json
{ "lengthPx": 0.5, "normalLineHeightFactor": 1.2 }
```

Colors are normalized to `rgba(r, g, b, a)`. Font families compare as ordered
lowercase lists without quotes. `transform: none` equals the identity matrix.
When own text differs between a pair, that pair's `width` and `height` and the
`x` and `y` of the prototype node's following siblings are excluded from the
geometry comparison and the pair is listed under `content`.

## Pairings file

`pairings.json` in the session folder, keyed by ledger row id, then prototype
path to real path:

```json
{ "L3": { "section > button:nth-of-type(2)": "section > a:nth-of-type(1)" } }
```

Pass it with `--pairings pairings.json --row L3`. Pairings are applied before
any other rule and are final.

Pairings apply between nodes that are children of an already matched pair, so
two nodes at different depths cannot be paired by the file; add a finer root
pair to the component map instead.
