# arch collect

What `arch collect` does, its flags, exit codes, and output. Read it when `collect` fails, or when
wiring it into continuous integration, a hook, or a schedule. It runs the project's adapter, builds
the dependency graph, stores it in the graph cache under `.architecture/graph/`, and rewrites
`current.md` in the record path. It decides no condition; `arch check` does that.

## Synopsis

```
arch collect
arch collect --ref <ref>
arch collect --json
```

## Flags

| Flag | Value | Meaning |
|---|---|---|
| `--ref` | a branch, tag, or commit | Build the graph of that commit's tree with the current model, and leave `current.md` alone. |
| `--json` | none | Print the whole graph as JSON instead of the summary line. |
| `--record` | a directory | Read the model from, and write `current.md` to, this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The graph was built. |
| 2 | No model, in which case the message names the baseline flow to run first, an invalid model, an adapter that failed or printed an invalid document, or a usage error. |

## Output

One summary line on standard output: units, edges, components, cycles (module and component
together), and uncovered units. Adapter warnings go to standard error.

`current.md` holds four sections, with no dates and no previous values: counts; a metrics table per
component (units, fan-in, fan-out, instability, abstractness, distance, zone); the component graph
with the number of importing modules per edge; and threshold breaches.

With `--json`, the graph object: `version`, `capabilities`, `rings`, `units` (path, component,
kind, ring, actors, valueType, and the adapter facts), `edges` (from, to, kind, symbols,
crossesComponent, direction), `externals` (name, tag, importers), `components` (name, units, fanIn,
fanOut, instability, abstractness, distance, zone), `componentEdges` (from, to, modules), `cycles`
(`modules` and `components`), `uncovered`, and `warnings`.

## Example

From the payroll fixture:

```
$ arch collect
collect: 11 units, 20 edges, 3 components, 0 cycles, 0 uncovered
```
