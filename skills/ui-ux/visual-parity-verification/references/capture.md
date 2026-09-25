# Capture command

`scripts/capture-snapshots.mjs` drives headless Chromium through Playwright,
injects the two bundled browser scripts by file path, and writes snapshot
files itself. The agent reads one summary line per file, never the snapshot
JSON or the script text.

## Requirements

Playwright is not bundled with the skill. It is resolved at runtime, in
order:

1. `createRequire(import.meta.url)` — an ordinary `require("playwright")`
   from the command's own file, which finds a `playwright` the host project
   installed only when the skill itself is installed inside that project's
   tree; a skill installed elsewhere (a global or user-level install) never
   resolves a project's `playwright` this way.
2. Each entry of `NODE_PATH`, in order, as `<entry>/playwright`. These
   outrank `<cwd>/node_modules`, so a `NODE_PATH` entry is tried and can
   succeed even when step 3 would also have resolved.
3. `<cwd>/node_modules/playwright`.

When none resolves, the command exits 2 and prints:

```
playwright is not installed: looked in <list>; install it in the project or set NODE_PATH
```

`<list>` names every location tried. Install Playwright with Chromium in the
project, or point `NODE_PATH` at a `node_modules` directory that has it.

## Flags

Two modes, chosen by `--manifest`:

```
capture-snapshots.mjs --out <dir> --manifest <file> [--only-viewports WxH,...]
  [--timeout MS] [--color-scheme light|dark] [--wait-for SELECTOR] [--headed]

capture-snapshots.mjs --out <dir> --viewport WxH [--viewport WxH ...]
  [--prototype-url URL (--prototype-component Name | --prototype-root SELECTOR)
    [--prototype-actions FILE] [--prototype-storage-state FILE] [--prototype-header "Name: value" ...]]
  [--real-url URL --real-root SELECTOR-OR-ATTR-VALUE
    [--real-actions FILE] [--real-storage-state FILE] [--real-header "Name: value" ...]]
  [--timeout MS] [--color-scheme light|dark] [--wait-for SELECTOR] [--headed]
```

| Flag | Meaning |
|---|---|
| `--out <dir>` | Required. Output folder, created if missing. |
| `--manifest <file>` | Manifest mode (see below). Excludes `--viewport` and every `--prototype-*` / `--real-*` flag. |
| `--only-viewports WxH,...` | Manifest mode only. Keep only these viewports in every row. |
| `--viewport WxH` | Per-side mode, required, repeatable. One capture pass per viewport, e.g. `1440x900`. |
| `--prototype-url URL` | Prototype page to open. Requires exactly one of `--prototype-component` or `--prototype-root`. |
| `--prototype-component Name` | Resolve the root through `parityFindReactRoots` and use the single matching root's selector. |
| `--prototype-root SELECTOR` | Use this selector or `data-parity-root` value directly; skips root resolution. |
| `--real-url URL` | Real app page to open. Requires `--real-root`. |
| `--real-root SELECTOR-OR-ATTR-VALUE` | Selector or `data-parity-root` value passed straight to `paritySnapshot`. |
| `--prototype-actions FILE`, `--real-actions FILE` | Action recipe run on that side after load (see Recipes). |
| `--prototype-storage-state FILE`, `--real-storage-state FILE` | Playwright storage state for that side's browser context (see Authentication). |
| `--prototype-header "Name: value"`, `--real-header "Name: value"` | Repeatable. Extra HTTP header on every request of that side. The separator is `: `. |
| `--timeout MS` | Default `30000`. Applies to `goto`, `--wait-for`, every recipe step and the network-idle wait. Positive integer. |
| `--color-scheme light\|dark` | Sets the browser context's `colorScheme`. Omit to use Playwright's default. |
| `--wait-for SELECTOR` | `page.waitForSelector` after `goto`, before the recipe and root resolution. |
| `--headed` | Launch Chromium with a visible window instead of headless. |

Per-side mode needs at least one of `--prototype-url` or `--real-url`; a
side's sub-flags require that side's URL flag. Usage errors — missing
`--out`, no `--viewport`, neither side given, a malformed viewport, a header
without `: `, a bad `--timeout`, an unrecognized flag, a malformed manifest
or recipe — exit 2 with a one-line message on stderr before the browser
launches.

## What it does

One browser for the whole run. Browser contexts are created lazily and
cached per `(viewport, storage state, color scheme, headers)`; every capture
opens its own page in the matching context and closes it afterwards.

Per capture: `goto` the URL with `waitUntil: "load"`, run `--wait-for` if
given, run the side's recipe (see Recipes), resolve the root (component name
on the prototype side, or the given selector/attribute value otherwise),
inject the snapshot script and evaluate `paritySnapshot(root)`, then write
the result as compact JSON.

Root resolution errors — `no-react-fibers`, zero roots for the named
component, or more than one root (every candidate selector is printed) — a
`paritySnapshot` error result, a load timeout or a failed step are reported
as one line on stderr per failed capture; the command keeps going with the
rest and exits 1 at the end.

## Manifest mode

`--manifest <file>` consumes the JSON that `parity_map.py manifest` writes
(see `map.md`): `prototypeUrl`, `realUrl`, `viewports` and `rows`, each row
with `id`, `protoRoute`, `realRoute`, `protoComponent` or `protoRoot`,
`realRoot`, `viewports` (`"WxH"` strings), `protoActions`, `realActions`
(recipe paths or null) and `shareProto` (a row id). Routes are joined onto
the base URLs with `new URL(route, base)`. `ignore` is for the diff step and
is not read here.

Two optional top-level objects carry authentication, added by hand or copied
from the flags; `parity_map.py` does not emit them:

```json
"prototype": {"storageState": "auth/proto-state.json", "headers": {"X-Debug": "1"}},
"real": {"storageState": "auth/real-state.json", "headers": {"X-Tenant": "acme"}}
```

Rows run in manifest order; each row runs its viewports, intersected with
`--only-viewports` when given. A row left with no viewports prints
`skip <rowId>: no viewports` on stderr and does not fail the run.

Files land in `<out>/<rowId>/<side>-<WxH>.json`:

- The prototype is captured once per `shareProto` group and viewport, into
  the source row's folder (`<out>/<shareProto>/prototype-<WxH>.json`), the
  first time any row of the group needs it. Every other row of the group
  gets `<out>/<rowId>/prototype-<WxH>.json` as a hard link to that file
  (a copy when linking fails), with its own summary line marked
  `(shared from <rowId>)`.
- The real side is captured per row into `<out>/<rowId>/real-<WxH>.json`.

Recheck rule: after a round, rerun only the viewports whose last verdict was
not `MATCH`, read from the ledger's evidence cell, through
`parity_map.py manifest --only-viewports` or this command's
`--only-viewports`.

## Recipes

A recipe file is a JSON array of steps, run in order after load and
`--wait-for`, each with the `--timeout` budget:

| Step | Runs |
|---|---|
| `{"click": "selector"}` | `page.click` |
| `{"hover": "selector"}` | `page.hover` |
| `{"press": "Key"}` | `page.keyboard.press` |
| `{"fill": ["selector", "text"]}` | `page.fill` |
| `{"wait": 250}` | `page.waitForTimeout` (milliseconds) |
| `{"waitFor": "selector"}` | `page.waitForSelector` |

Each step is an object with exactly one key. A malformed file, an unknown
kind or a value of the wrong shape is a usage error naming the file and the
step index, raised before the browser launches.

After the last step — and also when the side has no recipe — the pointer is
parked at `0,0` and the page waits for `networkidle`, so hover styling from
the pointer's resting place never leaks into a capture and a hover recipe
must move the pointer onto its target itself. A failing step prints
`<side> <WxH> step <i> <kind>: <error>` and counts as a failed capture.

## Authentication

`--<side>-storage-state FILE` goes to `browser.newContext({ storageState })`;
`--<side>-header "Name: value"` goes to `context.setExtraHTTPHeaders`. In a
manifest, the `prototype` and `real` objects above carry the same two
values. Produce the storage state once with a short login script run with
the same Playwright the capture resolves:

```js
const { chromium } = require("playwright");
const browser = await chromium.launch(), page = await browser.newPage();
await page.goto("http://localhost:3000/login");
await page.fill("#email", process.env.USER_EMAIL); await page.fill("#password", process.env.USER_PASSWORD);
await page.click("button[type=submit]"); await page.waitForURL("**/home");
await page.context().storageState({ path: "auth/real-state.json" }); await browser.close();
```

Keep the state file out of Git; it holds session cookies and local storage.

## Output files and summary line

Each successful capture writes compact JSON — the same shape
`scripts/diff_snapshots.py` reads directly, no decoding needed — to
`<out>/<side>-<W>x<H>.json` in per-side mode or
`<out>/<rowId>/<side>-<W>x<H>.json` in manifest mode (`side` is `prototype`
or `real`, `<W>x<H>` is the viewport value verbatim). One line goes to
stdout per written or linked file:

```
<side> <WxH> <nodes> nodes children=<n> root=<tag> <role> "<name>" <w>x<h> -> <path>
<side> <WxH> <nodes> nodes children=<n> root=<tag> <role> "<name>" <w>x<h> (shared from <rowId>) -> <path>
```

`<nodes>` counts the root plus every descendant in the written tree.
`children=<n>` counts the root's direct children after collapsing wrapper
children: a child flagged `wrapper` contributes its own non-wrapper
descendants instead of itself, so the number matches the child signature
the diff's root preflight compares. `<tag>`, `<role>`, `<name>`, `<w>x<h>`
come from the captured root node. Error lines on stderr start with
`<side> <WxH>` and, in manifest mode, end with `(row <rowId>)`.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Every requested capture wrote its file. |
| `1` | At least one capture errored; errors were printed to stderr and the rest still ran. |
| `2` | A usage error, or Playwright could not be resolved. |

The browser and every cached context are always closed, including after a
mid-run failure.

## Prototype reuse without a manifest

Manifest mode shares prototype captures by itself. In per-side mode, capture
the prototype once per shared route and state into its own folder, then
capture only `--real-url`/`--real-root` for each row that shares it:

```bash
capture-snapshots.mjs --prototype-url http://localhost:5173/orders \
  --prototype-component OrderSummary --viewport 1440x900 --viewport 375x800 \
  --out session/snapshots/shared-orders-route

capture-snapshots.mjs --real-url http://localhost:3000/orders --real-root OrderSummary \
  --viewport 1440x900 --viewport 375x800 --out session/snapshots/L1
```

Point the diff at the shared prototype file and each row's own real file:

```bash
diff_snapshots.py --prototype session/snapshots/shared-orders-route/prototype-1440x900.json \
  --real session/snapshots/L1/real-1440x900.json --out session/diffs/L1-1440x900.json
```
