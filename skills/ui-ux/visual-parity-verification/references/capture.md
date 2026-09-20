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
   installed.
2. Each entry of `NODE_PATH`, in order, as `<entry>/playwright`.
3. `<cwd>/node_modules/playwright`.

When none resolves, the command exits 2 and prints:

```
playwright is not installed: looked in <list>; install it in the project or set NODE_PATH
```

`<list>` names every location tried. Install Playwright with Chromium in the
project, or point `NODE_PATH` at a `node_modules` directory that has it.

## Flags

```
capture-snapshots.mjs --out <dir> --viewport WxH [--viewport WxH ...]
  [--prototype-url URL (--prototype-component Name | --prototype-root SELECTOR)]
  [--real-url URL --real-root SELECTOR-OR-ATTR-VALUE]
  [--color-scheme light|dark] [--wait-for SELECTOR] [--headed]
```

| Flag | Meaning |
|---|---|
| `--out <dir>` | Required. Output folder, created if missing. |
| `--viewport WxH` | Required, repeatable. One capture pass per viewport, e.g. `1440x900`. |
| `--prototype-url URL` | Prototype page to open. Requires exactly one of `--prototype-component` or `--prototype-root`. |
| `--prototype-component Name` | Resolve the root through `parityFindReactRoots` and use the single matching root's selector. |
| `--prototype-root SELECTOR` | Use this selector or `data-parity-root` value directly; skips root resolution. |
| `--real-url URL` | Real app page to open. Requires `--real-root`. |
| `--real-root SELECTOR-OR-ATTR-VALUE` | Selector or `data-parity-root` value passed straight to `paritySnapshot`. |
| `--color-scheme light\|dark` | Sets the browser context's `colorScheme`. Omit to use Playwright's default. |
| `--wait-for SELECTOR` | `page.waitForSelector` after `goto`, before root resolution. |
| `--headed` | Launch Chromium with a visible window instead of headless. |

At least one of `--prototype-url` or `--real-url` must be given. Usage
errors — missing `--out`, no `--viewport`, neither side given, a malformed
`--viewport`, an unrecognized flag — exit 2 with a one-line message on
stderr.

## What it does

For each `--viewport`, for each side given: open a new browser context with
that viewport and the color scheme, `goto` the side's URL with
`waitUntil: "load"`, run `--wait-for` if given, resolve the root (component
name on the prototype side, or the given selector/attribute value otherwise),
inject the snapshot script and evaluate `paritySnapshot(root)`, then write
the result as compact JSON.

Root resolution errors — `no-react-fibers`, zero roots for the named
component, or more than one root (every candidate selector is printed) — and
a `paritySnapshot` error result are reported as one line on stderr per
failed capture; the command keeps going with the rest.

## Output files and summary line

Each successful capture writes `<out>/<side>-<W>x<H>.json` (`side` is
`prototype` or `real`, `<W>x<H>` is the `--viewport` value verbatim) as
compact JSON — the same shape `scripts/diff_snapshots.py` reads directly, no
decoding needed. One line goes to stdout per successful capture:

```
<side> <WxH> <nodes> nodes root=<tag> <role> "<name>" <w>x<h> -> <path>
```

`<nodes>` counts the root plus every descendant in the written tree.
`<tag>`, `<role>`, `<name>`, `<w>x<h>` come from the captured root node.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Every requested capture wrote its file. |
| `1` | At least one capture errored; errors were printed to stderr and the rest still ran. |
| `2` | A usage error, or Playwright could not be resolved. |

The browser is always closed, including after a mid-run failure.

## Prototype reuse across rows (L4)

When several ledger rows share the same prototype route and state, capture
the prototype side once for that route and state, into its own folder, then
capture only `--real-url`/`--real-root` for each row that shares it, each
into its own row folder:

```bash
capture-snapshots.mjs --prototype-url http://localhost:5173/orders \
  --prototype-component OrderSummary --viewport 1440x900 --viewport 375x800 \
  --out session/snapshots/shared-orders-route

capture-snapshots.mjs --real-url http://localhost:3000/orders --real-root OrderSummary \
  --viewport 1440x900 --viewport 375x800 --out session/snapshots/L1

capture-snapshots.mjs --real-url http://localhost:3000/orders?variant=empty --real-root OrderSummary \
  --viewport 1440x900 --viewport 375x800 --out session/snapshots/L2
```

Point the diff at the shared prototype file and each row's own real file:

```bash
diff_snapshots.py --prototype session/snapshots/shared-orders-route/prototype-1440x900.json \
  --real session/snapshots/L1/real-1440x900.json --out session/diffs/L1-1440x900.json
```

Copying the prototype file into each row's folder instead of referencing it
across folders is also fine; either way the prototype page is opened once
per shared route and state, not once per row.
