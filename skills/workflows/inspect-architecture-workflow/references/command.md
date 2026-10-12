# The arch command

Run `node <skill>/scripts/arch.mjs <subcommand>` from the inspected project's root, where
`<skill>` is this skill's directory, the folder holding `SKILL.md`. The coordinator resolves that
folder once per run and writes its absolute path into every packet, so no subagent has to find it
itself.

## Exit codes

0 when the subcommand succeeds. 1 on a usage error (a missing required argument), a hard model
problem, or a tooling error (a language with no adapter, tooling that cannot run). `arch uncovered`
returns 1 whenever it lists at least one module; that is its normal job, not a failure.

## Tooling

The command needs the inspected project's language tooling installed: for TypeScript and
JavaScript, `dependency-cruiser` and `typescript`. A language with no adapter stops the run with
`no adapter for language: <language>; supported: typescript`, naming the configured language or
`unknown` when none is configured and no `package.json` exists.

## Known limits

The derived graph covers only what the project's cruiser configuration includes. When that
configuration excludes test files, `arch query units --kind test` returns only the test units the
configuration does include, W7 evaluates that narrower set, and the run log records that the
scope was narrowed.

## `graph`

Builds `.architecture/graph/<commit>.json`: units with component, ring, kind, actors, and export
counts; edges with direction and crossings; externals; component metrics; component edges;
cycles; uncovered modules. Deterministic from a commit; rebuilt when the cache is missing, when
`--force` is given, or when either saved-output flag is given.

| Flag or argument | Meaning |
|---|---|
| `--commit <ref>` | Build the graph for `<ref>` instead of the working tree |
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--exports-json <file>` | Read export data from `<file>` instead of running the tooling |
| `--force` | Rebuild even when a cached graph file already exists |
| `--json` | Print the full graph as JSON instead of the summary line |

On success it prints `graph: <n> units, <n> edges, <n> components, <n> component cycles, <n>
uncovered -> <path>`. Warnings, such as an unresolved import, an unused rule, or a stale override,
go to stderr whether or not `--json` is set. A hard model problem, meaning overlapping component
globs, an unknown ring or kind, a duplicate component ID, a port or shape owner that is not a
component, or fewer than two distinct rings in `rules.json`, stops the run and exits 1 before any
graph is written.

`--cruise-json` and `--exports-json` feed saved adapter output instead of running the project's
tooling. They exist for tests and for projects whose tooling cannot run in the current
environment; passing either always rebuilds, bypassing the cache.

## `diff`

| Flag or argument | Meaning |
|---|---|
| `<base>` | The commit or ref to diff the working tree against (required) |
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` for both sides instead of running it |
| `--exports-json <file>` | Read export data from `<file>` for both sides instead of running the tooling |
| `--json` | Print the diff as JSON instead of the markdown sections |

Compares `<base>` against the working tree and prints four sections: Units (added, removed,
moved, reclassified, with the ring and kind on each side), Edges (added, removed), Components
(fan-in, fan-out, I, A, D, each as before -> after, flagged when D moved by 0.10 or more), and
Cycles (new, gone).

Renames are detected from `git diff -M` against the working tree, so a moved file shows as moved
only after `git add`: before the add, git sees a deleted tracked path and an untracked new path,
and an untracked path never appears in the diff.

## `query`

| Flag or argument | Meaning |
|---|---|
| `<name>` | The query to run; see the table below |
| `[args]` | The named query's own positional arguments and flags |
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--exports-json <file>` | Read export data from `<file>` instead of running the tooling |
| `--json` | Print the result as a JSON object of columns and rows instead of a markdown table |

"Read by" collects, from `references/workflows/w1.md` through `w8.md`, every workflow whose
`Reads:` line names the query; those `Reads:` lines are authoritative.

| Query | Arguments | Columns | Read by |
|---|---|---|---|
| `metrics` | none | Component, Units, Fan-in, Fan-out, I, A, D, Zone | W5, W6 |
| `component-graph` | none | From, To, Importing modules | W6, W8 |
| `cycles` | none | Level, Members | W6 |
| `ring-crossings` | `[--direction outward\|inward\|same]` (default `outward`) | From, From ring, To, To ring, Kind | W1, W2, W3, W4 |
| `fan-in` | `<path>` | Importer, Component, Kind | W7, severity escalation rule 3 |
| `units` | `[--component <id>] [--kind <k>] [--ring <r>]` | Path, Kind, Ring, Actors, Abstract, Concrete | W2, W3, W4, W7 |
| `touched` | `--base <ref>` (required) | Path, Component, Kind, Ring, Change, Neighbors | change review, the caller precheck |
| `ports` | none | Port, Owner, Humble side, Implementers, Consumers (by component) | W1, W3, W4, W5, W7 |
| `entry-points` | none | Path, Component, Constructs | W1, W7 |
| `externals` | `[--tag vendor\|framework\|runtime]` | Name, Tag, Importing components, Importing modules | W5, W8 |
| `volatility` | `--since <ref>` (required) | Component, Commits, Modules touched | W1, W2, W5, W6 |

`touched` and `volatility` exit with a usage message when their required flag is missing. A
missing value renders as `undefined` in a table cell; a query over an empty graph section renders
no rows.

## `uncovered`

| Flag or argument | Meaning |
|---|---|
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--exports-json <file>` | Read export data from `<file>` instead of running the tooling |
| `--json` | Print the uncovered paths as a JSON array instead of one path per line |

Lists every module no component glob covers or no rule classifies. Exits 1 while the list is
non-empty, 0 once it prints nothing.

## `model`

Agents change the model only through these subcommands, never by editing the JSON files
directly: each one validates the result and writes the canonical form, or refuses and exits 1,
leaving the files untouched. A `remove-*` subcommand naming a target that does not exist prints an
error and exits 1 without touching the files.

| Flag or argument | Meaning |
|---|---|
| `validate` | Rebuild the graph and report every model problem; print `model: ok` and exit 0 only when there are none |
| `add-override <path> ring=<r> kind=<k> [actors=a,b] [reason=<text>]` | Add or replace the override for `<path>` |
| `remove-override <path>` | Remove the override for `<path>` |
| `add-port <path> <symbol> owner=<C> [humble=<ring>]` | Declare or replace the port at `<path>:<symbol>`, owned by component `<C>` |
| `remove-port <path> <symbol>` | Remove the port at `<path>:<symbol>` |
| `add-component <id> <name> paths=<glob,...> [enforcement=<text>] [release=<text>] [entry=<glob,...>]` | Add a component |
| `remove-component <id>` | Remove a component that no port or shape still references |
| `add-rule match=<glob> ring=<r> kind=<k> [actors=a,b] [before=<glob>]` | Insert a classification rule, before the existing rule whose `match` equals `before` when given, otherwise at the end |
| `remove-rule match=<glob>` | Remove the rule whose `match` glob equals `<glob>` |

`validate` also accepts `--cruise-json <file>` and `--exports-json <file>` to feed saved adapter
output instead of running the tooling.

## `readme-summary`

| Flag or argument | Meaning |
|---|---|
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--exports-json <file>` | Read export data from `<file>` instead of running the tooling |

Rewrites the block between the `<!-- arch:summary -->` and `<!-- /arch:summary -->` markers in
`docs/architecture/README.md` with the components, units, edges, component cycles, and uncovered
counts, the metrics table, and the component graph table. Fails when the markers are missing.
