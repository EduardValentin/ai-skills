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

## Ignore lists

`--ignore-prototype ENTRY` and `--ignore-real ENTRY`, each repeatable, prune
subtrees from one side before comparison. An entry is:

- `hook:<value>`: every node whose `hook` equals the value;
- `path:<prefix>`: the node whose `path` equals the prefix and every node
  whose path starts with the prefix followed by ` > ` (whole segments only,
  so `div:nth-of-type(1)` never matches `div:nth-of-type(10)`).

Any other shape exits 2 naming the entry, as does an entry that matches the
root. Pruning runs on the raw tree after style inflation and before the root
preflight and wrapper collapse, so an ignored child no longer counts in the
child signature. Each pruned node is listed under `findings.ignored` as
`{ side, path, entry }` in document order; an entry that matches nothing adds
no item. The category never affects the verdict.

Pruning removes the node from the comparison, not its layout effect: an
in-flow prototype-only element still shifts its siblings, which then show as
geometry drift. Use `Ignore` for out-of-flow or zero-footprint elements;
otherwise record the row `EXPECTED` with a reason or change the prototype.

## Summary line

```
<VERDICT> style=<n> geometry=<n> missing=<n> structure=<n> content=<n> accessibility=<n> ignored=<n> lowestScore=<0.00 | n/a>
```

A blocked run prints `BLOCKED <reason>` before the counts.

## Review printout

With the `--print-review` flag, after the summary line the script prints one line per finding that needs review:

- `review blocked`, alone, when `verdict` is `BLOCKED` — no pairs or suggestions follow
- `review <prototypePath> <-> <realPath> score=<0.00> roleName=<0.0> text=<0.0>` for each pair with `needsReview` true
- `pairing unapplied <prototypePath> -> <realPath> (<reason>)` for each entry in `unappliedPairings`
- `suggest <side> <path> -> <candidate> score=<0.00>` for each suggestion
- `review none` if there are no review pairs, no unapplied pairings and no suggestions
- `hook suggest <prototypePath> <-> <realPath> (<matchedBy>)` for each entry in `hookSuggestions`, after every line above

Each line lets the agent decide what to do with the result without opening the JSON file. A run whose only lines are hook suggestions prints `review none` followed by the hook lines.

## Top level

| Field | Meaning |
|---|---|
| `verdict` | `MATCH`, `DRIFT`, `MISSING` or `BLOCKED` |
| `conditions` | `viewport`, `devicePixelRatio`, `zoom`, `colorScheme` shared by both snapshots |
| `urls` | `prototype` and `real` page URLs |
| `rootSummaries` | Both root summaries |
| `blocked` | `null`, or `{ reason, detail }` with reason `condition-mismatch` or `roots-incompatible`, below |
| `pairs` | Every aligned pair: `prototype` path, `real` path, `matchedBy`, `score`, `signals`, `needsReview`, `hooks` (`prototype` and `real` `data-parity` values, each a string or `null`) |
| `findings` | Lists per category, below |
| `collapsed` | Collapsed wrapper nodes per side: `path`, `tag`, `childCount` |
| `suggestions` | For each unmatched node: `side`, `path`, best `candidate` path and its `score` |
| `unappliedPairings` | Pairings entries that were skipped: `prototype` path, `real` path, `reason` |
| `hookSuggestions` | Pairs that would anchor with a `data-parity` hook: `prototype` path, `real` path, `matchedBy`; empty on a blocked run |
| `lowestScore` | Lowest score among pairs matched by score, or `null` |

`matchedBy` is one of `root`, `pairing`, `hook`, `role-name`, `text`,
`position`, `score`, `moved`. `needsReview` is true for a `score` pair whose
`roleName` signal is below 1 and whose `text` signal is 0 — matched without a
shared name and without shared text identity. Review every pair with
`needsReview` true and every suggestion.

A pair whose two nodes carry the same `data-parity` value anchors
deterministically by the `hook` rule and never needs a pairings entry.
`hookSuggestions` lists, in `pairs` order, every non-root pair matched by
`score`, `position` or `moved`, and every non-root pair whose `hooks` differ
(one side hooked, or two values); giving both nodes one matching hook removes
the entry on the next run.

`position` pairs same-shaped sibling runs by order: when, between two
anchors, the unmatched prototype children and the unmatched real children
have the same `role`-or-`tag` sequence, they pair by index without scoring.
Such a pair has `score` and `signals` `null` and is never `needsReview`; a
text difference between the two lands under `content`.

### Roots-incompatible detail

The preflight compares the two roots before any alignment and blocks when
any rule fails:

1. both roots have a `role` and the roles differ;
2. the `tag`s differ;
3. `width` or `height` differ by more than a factor of 2;
4. the child signatures share a longest common subsequence shorter than half
   the longer signature (two empty signatures agree).

A child signature is the `role`-or-`tag` of each direct child of the raw
root, read through wrapper children at depth 1 (a wrapper contributes its
own non-wrapper descendants in order). The `detail` is
`{ prototype, real }`, each the root summary (`tag`, `role`, `name`, `width`,
`height`) plus `childSignature`.

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
| `ignored` | `side`, `path`, `entry` for each subtree pruned by an ignore list | no |

Semantic differences in `role`, `name`, `focusable`, `tabIndex` and `state`
are reported under `style` with the field name as `property`.

## Verdict rules

1. `BLOCKED` when a precondition failed.
2. `DRIFT` when any `style` or `geometry` finding exists.
3. `MISSING` when any `missing` finding exists and no `DRIFT`.
4. `MATCH` otherwise.

The root pair's own `x`, `y`, `width`, `height` and `marginTop`,
`marginRight`, `marginBottom`, `marginLeft` never produce findings: the root's
placement belongs to its parent and is not evidence about the surface. Its
other styles and every child's full geometry stay compared. The root summary
keeps `width` and `height` for the preflight.

## Tolerances

Defaults, overridable with `--tolerances <file.json>`:

```json
{ "lengthPx": 0.5, "normalLineHeightFactor": 1.2 }
```

Colors, whether the snapshot wrote `rgb()` or `rgba()`, are normalized to
`rgba(r, g, b, a)`. Font families compare as ordered
lowercase lists without quotes. `transform: none` equals the identity matrix.
When own text differs between a pair, that pair's `x`, `y`, `width` and
`height` and the `x` and `y` of every sibling of the prototype node —
preceding and following — are excluded from the geometry comparison and the
pair is listed under `content`. A sibling's own `width` and `height` stay
compared, so a sibling that resizes because of the content change is still
caught. Siblings are the node's original siblings in document order, so a
node taken out by a pairing still shields and is shielded by them.
The diff skips the `name` comparison when both sides' `nameFrom` is
`"content"`; that difference is already covered by the `content` category.

## Pairings file

`.parity/parity-pairings.json`, committed next to the map, keyed by map id,
then prototype path to real path:

```json
{ "C3": { "section > button:nth-of-type(2)": "section > a:nth-of-type(1)" } }
```

Pass it with `--pairings .parity/parity-pairings.json --row C3`; `--row`
names the key to read, which is the ledger row's `Map id`, not the ledger
row id. Pairings are applied before any other rule and are final.

Pairings resolve anywhere in the two trees by full path, regardless of depth.
A paired node is taken out of ordinary alignment along with its position
among its siblings; the two nodes' children are then aligned like any other
matched pair's. Entries are applied in prototype-path order. A skipped entry
is listed under `unappliedPairings` with one reason, checked in this order:
`unknown-prototype-path`, `unknown-real-path`, `root` (either path is a
root), `already-claimed` (either node was taken by an earlier entry).
