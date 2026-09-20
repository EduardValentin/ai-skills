# Snapshot schema

`snapshot-subtree.browser.js` returns one object per root per viewport. The
agent saves it as compact JSON — `JSON.stringify(data)`, no indentation — under
the session folder as `snapshots/<row-id>/<side>-<width>x<height>.json`. The
diff's loader accepts indented JSON too; compact only shrinks the file the
agent's context would otherwise see.

## Document

| Field | Type | Meaning |
|---|---|---|
| `url` | string | Page URL at capture time |
| `viewport` | `{ width, height }` | `innerWidth` and `innerHeight` in CSS pixels |
| `devicePixelRatio` | number | `window.devicePixelRatio` |
| `zoom` | number | `outerWidth / innerWidth`, rounded to two decimals |
| `colorScheme` | `"light"` or `"dark"` | From `prefers-color-scheme` |
| `capturedAt` | string | ISO 8601 timestamp |
| `rootSelector` | string | The selector or `data-parity-root` value that resolved the root |
| `rootSummary` | `{ tag, role, name, width, height }` | Plausibility check input for the diff |
| `root` | node | The root node; descendants are under `children` |

## Node

| Field | Type | Meaning |
|---|---|---|
| `path` | string | `tag:nth-of-type(n)` segments joined by ` > `, from the root; the root's path is its tag |
| `tag` | string | Lowercase tag name |
| `hook` | string or null | Value of the `data-parity` attribute |
| `ownText` | string | Whitespace-collapsed concatenation of the node's own text children |
| `role` | string | Explicit `role` attribute or implicit role for the tag, empty when none |
| `name` | string | Accessible name in order: `aria-labelledby`, `aria-label`, associated label, `alt`, `title`, own text when the role allows name from content |
| `nameFrom` | string | `"author"` when `name` came from `aria-labelledby`, `aria-label`, an associated label, `alt`, or `title`; `"content"` when it came from the node's text content; `""` when there is no name |
| `focusable` | boolean | Focusable by tag or by non-negative `tabindex` |
| `tabIndex` | number | `element.tabIndex` |
| `state` | object | Present ARIA and native state: `aria-expanded`, `aria-selected`, `aria-checked`, `aria-pressed`, `aria-disabled`, `disabled`, `aria-current`, `aria-hidden` |
| `style` | object | Computed values, see below; the root carries every key, every other node only the keys that differ from its parent |
| `geometry` | `{ x, y, width, height }` | Measured from the root's top-left corner |
| `contrast` | `{ ratio, needsAnalyzer, largeText }` or null | Only for nodes with non-empty `ownText` |
| `wrapper` | boolean | No own text, no border, transparent own background, no shadow, zero padding, no transform, no outline |
| `children` | node[] | Included descendants in document order |

## Style keys

All values are computed-style strings.

- `fontFamily`, `fontSize`, `fontWeight`, `fontStyle`, `lineHeight`, `letterSpacing`, `textTransform`, `textDecorationLine`
- `color`, `backgroundColor`, `effectiveBackground`, `opacity`
- `paddingTop`, `paddingRight`, `paddingBottom`, `paddingLeft`
- `marginTop`, `marginRight`, `marginBottom`, `marginLeft`
- `borderTopWidth`, `borderRightWidth`, `borderBottomWidth`, `borderLeftWidth`, `borderTopStyle`, `borderRightStyle`, `borderBottomStyle`, `borderLeftStyle`, `borderTopColor`, `borderRightColor`, `borderBottomColor`, `borderLeftColor`
- `borderTopLeftRadius`, `borderTopRightRadius`, `borderBottomRightRadius`, `borderBottomLeftRadius`
- `boxShadow`, `outlineWidth`, `outlineStyle`, `outlineColor`, `outlineOffset`
- `display`, `flexDirection`, `flexWrap`, `alignItems`, `justifyContent`, `alignContent`, `gridTemplateColumns`, `gridTemplateRows`, `gridAutoFlow`, `rowGap`, `columnGap`, `position`, `overflowX`, `overflowY`, `zIndex`
- `flexGrow`, `flexShrink`, `flexBasis`, `alignSelf`, `order`, `gridColumnStart`, `gridColumnEnd`, `gridRowStart`, `gridRowEnd`
- `textOverflow`, `whiteSpace`, `transform`

Together with `effectiveBackground` this is 68 keys. The root node's `style`
holds all 68. Every other node's `style` holds only the keys whose
canonicalized value differs from its parent's full 68-key block — the parent
block used for the comparison, not the parent's own (possibly delta) emitted
`style`. A node whose computed style matches its parent everywhere emits an
empty `style` object. Internal computations (contrast, the wrapper flag,
alignment fingerprinting) always use the full 68-key block, never the
emitted delta.

## Removed fields

Two fields from the 2026-09-19 schema are gone: `textDigest` (redundant with
`ownText`, which the diff already reads) and `geometry.viewport` (the
diff and every reader use `geometry` directly; nothing consumed the
viewport-relative box).

## Style inflation

`diff_snapshots.py` calls `inflate_styles(root)` in `load_snapshot` before
any comparison, filling each node's `style` from its parent's already-
inflated full block for every key the node didn't emit. A snapshot whose
nodes already carry full styles inflates to itself. Everything downstream —
alignment, scoring, comparison — sees full style blocks and never has to
know about the delta encoding on disk.

## Old geometry shape

A snapshot from before this schema change nests each node's box under
`geometry.relative` alongside a `geometry.viewport` sibling. `load_snapshot`
detects that shape (`"relative"` present) and replaces `geometry` with the
`relative` box before inflation, so older files on disk still load.

## Color canonicalization

`color`, `backgroundColor`, the four border colors, `outlineColor`, and
`effectiveBackground` are canonicalized before they are stored. A value
`parseColor` can already read (`rgb()`/`rgba()`) is kept as-is. A value it
cannot read — `oklch()`, `lab()`, `color()`, and similar modern syntax that
survives unchanged through a computed style read — is painted onto a cached
1×1 canvas (`{ willReadFrequently: true, colorSpace: "srgb" }`) and read back
with `getImageData`, producing `rgba(r, g, b, a)` with `a` rounded to three
decimals. When the browser has no canvas 2D context (for example, jsdom), or
the value fails a `fillStyle` validity check, the raw string is kept
unchanged. A background that is non-empty, not `transparent`, and still
unparseable after this step makes `effectiveBackground` return
`{ solid: false }` for that node instead of walking past it to an ancestor,
and makes `wrapper` false for that node's own background. Readbacks of
semi-transparent colors carry premultiplication rounding of up to a few units
per channel; this is acceptable because both sides of a comparison
canonicalize the same way in the same browser. `contrast` reads the
canonical `color` and `effectiveBackground`, so a modern-syntax text color is
measurable whenever the canvas readback succeeds.

## Inclusion rules

A descendant is skipped, with its subtree, when computed `display` is `none`,
computed `visibility` is `hidden`, or it is inside `script`, `style`,
`template` or `noscript`. A descendant with a zero-area box is skipped only
when none of its descendants is included.

## Errors

The function returns `{ "error": "root-not-found", "rootSelector" }` or
`{ "error": "root-ambiguous", "count", "rootSelector" }` instead of a
snapshot. An invalid selector is treated as a `data-parity-root` value.
