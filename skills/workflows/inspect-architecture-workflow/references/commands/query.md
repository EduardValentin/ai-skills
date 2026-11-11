# arch query

What `arch query` does, its queries, flags, exit codes, and output. Read it when a reviewer or a
classifier needs one view of the collected evidence, or when a query fails. Every query reads the
graph the adapter produced and the model, and prints one table; none decides a condition or writes
anything outside the graph cache.

## Synopsis

```
arch query <name>
arch query <name> <path>
arch query touched --base <ref> --with-neighbors
arch query units --component <component> --json
```

| Query | Takes | Prints |
|---|---|---|
| `units` | `--component`, `--kind`, `--ring` to filter | Path, kind, ring, actors, abstract and concrete export counts |
| `edges` | a path, or `--kind <kind>` | The edges of that path in and out, or every edge of that kind, with ring direction |
| `fan-in` | a path | Every importer of that path, its component, and the edge kind |
| `ring-crossings` | `--direction`, `--include-barrels` | Edges in one ring direction: `outward` by default, `inward`, `same`, `through-barrel`, or `unknown`; `--include-barrels` gives an edge through a barrel the direction of its ends |
| `externals` | `--tag <tag>` to filter | Each external, its tag, and the components and modules importing it |
| `components` | nothing | Each component's enforcement, release, entry points, published globs, and unit count |
| `component-graph` | nothing | Edges between components with the number of importing modules |
| `metrics` | nothing | Units, fan-in, fan-out, instability, abstractness, distance, and zone per component |
| `cycles` | nothing | Module and component cycles |
| `groups` | nothing | The model's cohesion groups |
| `ports` | nothing | Each port, its owner, humble side, implementers, and consumers by component |
| `entry-points` | nothing | Each entry point and what it constructs |
| `signatures` | a path | The types from other modules in that path's exported signatures |
| `touched` | `--base <ref>`, required; `--with-neighbors` | The files changed since the ref with their classification and neighbors; with `--with-neighbors`, also the untouched units next to them |
| `volatility` | `--since <ref>` | Commits and touched modules per component since the ref, or within the `historyWindow` knob |

## Flags

| Flag | Value | Meaning |
|---|---|---|
| `--component` | a component name | `units` only: keep units of that component. |
| `--kind` | a kind, or an edge kind | `units`: keep units of that kind. `edges`: keep edges of that kind (`import`, `type-import`, `dynamic`, `constructs`). |
| `--ring` | a ring name | `units` only: keep units in that ring. |
| `--direction` | a ring direction | `ring-crossings` only: which direction to list. |
| `--include-barrels` | none | `ring-crossings` only: see through barrels. |
| `--tag` | `vendor`, `framework`, or `runtime` | `externals` only: keep externals with that tag. |
| `--base` | a branch, tag, or commit | `touched` only, and required there. |
| `--with-neighbors` | none | `touched` only: add the neighbor table. |
| `--since` | a branch, tag, or commit | `volatility` only: count commits since that ref instead of the history window. |
| `--json` | none | Print JSON instead of a table. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

A query refuses a flag it does not take and lists the flags it accepts.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The table was printed. |
| 2 | An unknown query, a missing path or `--base`, no model, an invalid model, an adapter failure, or no git history for `volatility`. |

## Output

A markdown table, or two tables for `touched --with-neighbors`. A query that needs an adapter fact
the adapter does not provide prints "not provided by the adapter". With `--json`, one line:
`{"columns": [...], "rows": [[...], ...]}`; for `touched --with-neighbors`, an object with
`touched` and `neighbors`, each in that shape; for a missing fact, `{"notProvided": "<fact>"}`.

## Example

From the payroll fixture:

```
$ arch query units --component domain
| Path | Kind | Ring | Actors | Abstract | Concrete |
|---|---|---|---|---|---|
| src/domain/clock.ts | port | entities |  | 1 | 0 |
| src/domain/employee.ts | entity | entities |  | 0 | 1 |
| src/domain/index.ts | barrel | entities |  | 0 | 4 |
| src/domain/payroll-repository.ts | port | entities |  | 1 | 0 |
| src/domain/payroll-use-case.ts | use-case | use-cases |  | 0 | 1 |
```
