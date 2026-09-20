# Diff output

`diff_snapshots.py` writes one JSON file per row and viewport and prints one
summary line.

## Loading

`load_snapshot` normalizes each input before comparison: it rewrites the old
`geometry.relative`/`geometry.viewport` shape to the flat `geometry` box when
present, then calls `inflate_styles` to fill every node's `style` from its
parent's full style for keys the node didn't emit. See
`references/snapshot-schema.md` for the delta rule this undoes. Every
downstream step — alignment, scoring, `compare_pair` — sees full style
blocks.

## Summary line

```
<VERDICT> style=<n> geometry=<n> missing=<n> structure=<n> content=<n> accessibility=<n> lowestScore=<0.00 | n/a>
```

A blocked run prints `BLOCKED <reason>` before the counts.

## Review printout

With the `--print-review` flag, after the summary line the script prints one line per finding that needs review:

- `review blocked`, alone, when `verdict` is `BLOCKED` — no pairs or suggestions follow
- `review <prototypePath> <-> <realPath> score=<0.00> roleName=<0.0> text=<0.0>` for each pair with `needsReview` true
- `suggest <side> <path> -> <candidate> score=<0.00>` for each suggestion
- `review none` if there are no review pairs and no suggestions

Each line lets the agent decide what to do with the result without opening the JSON file.

## Top level

| Field | Meaning |
|---|---|
| `verdict` | `MATCH`, `DRIFT`, `MISSING` or `BLOCKED` |
| `conditions` | `viewport`, `devicePixelRatio`, `zoom`, `colorScheme` shared by both snapshots |
| `urls` | `prototype` and `real` page URLs |
| `rootSummaries` | Both root summaries |
| `blocked` | `null`, or `{ reason, detail }` with reason `condition-mismatch` or `roots-incompatible` |
| `pairs` | Every aligned pair: `prototype` path, `real` path, `matchedBy`, `score`, `signals`, `needsReview` |
| `findings` | Lists per category, below |
| `collapsed` | Collapsed wrapper nodes per side: `path`, `tag`, `childCount` |
| `suggestions` | For each unmatched node: `side`, `path`, best `candidate` path and its `score` |
| `lowestScore` | Lowest score among pairs matched by score, or `null` |

`matchedBy` is one of `root`, `pairing`, `hook`, `role-name`, `text`,
`score`, `moved`. `needsReview` is true for a `score` pair whose `roleName`
signal is below 1 and whose `text` signal is 0 — matched without a shared
name and without shared text identity. Review every pair with `needsReview`
true and every suggestion.

The `text` rule, and the `text` signal used when scoring, key on a node's
text identity rather than only its own text: a node's identity is its own
text when non-empty, otherwise the whitespace-joined own text of its
descendants in document order (its subtree text), otherwise empty. A
container with no own text — a list row built from label and value spans, a
card built from headings — anchors and scores by that subtree text once it
is unique on both sides, the same way a node with its own text does.

## Findings

| Category | Item fields | Verdict input |
|---|---|---|
| `style` | `path`, `realPath`, `property`, `prototype`, `real` | yes |
| `geometry` | `path`, `realPath`, `property` in `x`, `y`, `width`, `height`, `prototype`, `real` | yes |
| `missing` | `side`, `path`, `tag`, `role`, `name`, `suggestion` | yes |
| `structure` | `kind` `moved` with `prototype` and `real` paths, or `kind` `collapsed-count` with both counts | no |
| `content` | `path`, `realPath`, `prototype`, `real` own text | no |
| `accessibility` | `side`, `path`, `check` in `missing-role`, `missing-name`, `contrast`, `contrast-unmeasurable`; contrast adds `ratio` and `threshold` | findings only |

Semantic differences in `role`, `name`, `focusable`, `tabIndex` and `state`
are reported under `style` with the field name as `property`.

## Verdict rules

1. `BLOCKED` when a precondition failed.
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
When own text differs between a pair, that pair's `x`, `y`, `width` and
`height` and the `x` and `y` of every sibling of the prototype node —
preceding and following — are excluded from the geometry comparison and the
pair is listed under `content`. A sibling's own `width` and `height` stay
compared, so a sibling that resizes because of the content change is still
caught.
The diff skips the `name` comparison when both sides' `nameFrom` is
`"content"`; that difference is already covered by the `content` category.

## Pairings file

`pairings.json` in the session folder, keyed by ledger row id, then prototype
path to real path:

```json
{ "L3": { "section > button:nth-of-type(2)": "section > a:nth-of-type(1)" } }
```

Pass it with `--pairings pairings.json --row L3`. Pairings are applied before
any other rule and are final.

Pairings resolve anywhere in the two trees by full path, regardless of depth.
A paired node is taken out of ordinary alignment along with its position
among its siblings; the two nodes' children are then aligned like any other
matched pair's. Entries are applied in prototype-path order, and an entry
whose prototype or real node was already claimed by an earlier entry is
skipped silently, the same as an unknown path.
