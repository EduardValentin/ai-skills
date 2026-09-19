# Snapshot schema

`snapshot-subtree.browser.js` returns one object per root per viewport. The
agent saves it unchanged under the session folder as
`snapshots/<row-id>/<side>-<width>x<height>.json`.

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
| `textDigest` | string | Eight hex characters, FNV-1a of `ownText` |
| `role` | string | Explicit `role` attribute or implicit role for the tag, empty when none |
| `name` | string | Accessible name in order: `aria-labelledby`, `aria-label`, associated label, `alt`, `title`, own text when the role allows name from content |
| `focusable` | boolean | Focusable by tag or by non-negative `tabindex` |
| `tabIndex` | number | `element.tabIndex` |
| `state` | object | Present ARIA and native state: `aria-expanded`, `aria-selected`, `aria-checked`, `aria-pressed`, `aria-disabled`, `disabled`, `aria-current`, `aria-hidden` |
| `style` | object | Longhand computed values, see below |
| `geometry` | `{ relative: { x, y, width, height }, viewport: { x, y, width, height } }` | Relative is measured from the root's top-left corner |
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

## Inclusion rules

A descendant is skipped, with its subtree, when computed `display` is `none`,
computed `visibility` is `hidden`, or it is inside `script`, `style`,
`template` or `noscript`. A descendant with a zero-area box is skipped only
when none of its descendants is included.

## Errors

The function returns `{ "error": "root-not-found", "rootSelector" }` or
`{ "error": "root-ambiguous", "count", "rootSelector" }` instead of a
snapshot. An invalid selector is treated as a `data-parity-root` value.
