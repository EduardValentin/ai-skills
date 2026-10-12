# The arch command

Run `node <skill>/scripts/arch.mjs <subcommand>` from the inspected project's root, where
`<skill>` is this skill's directory, the folder holding `SKILL.md`. The coordinator resolves that
folder once per run and writes its absolute path into every packet, so no subagent has to find it
itself.

## Exit codes

0 when the subcommand succeeds. 1 on a usage error (a missing subcommand or required argument),
a hard model problem, or a tooling error (a language with no adapter, tooling that cannot run).
`arch uncovered` returns 1 whenever it lists at least one module; that is its normal job, not a
failure.

`--json` and `--force` are switches: they never take a value, so an argument after them stays
positional. Every other flag takes the next argument as its value.

## Tooling

The command needs the inspected project's language tooling installed: for TypeScript and
JavaScript, `dependency-cruiser` and `typescript`. A language with no adapter stops the run with
`no adapter for language: <language>; supported: typescript`, naming the configured language or
`unknown` when none is configured and no `package.json` exists.

The TypeScript adapter reads these `tooling` settings from `components.json`:

| Setting | Meaning |
|---|---|
| `language` | The adapter to use; `typescript` covers JavaScript too |
| `roots` | The source roots dependency-cruiser walks; missing or empty means the project root |
| `dependencyCruiserConfig` | The project's own cruiser config; otherwise a `.dependency-cruiser.*` file at the root, otherwise the bundled default |
| `tsConfig` | The TypeScript config that resolves path aliases, passed to the cruiser with `--ts-config` only when the bundled default config runs; a project's own config carries its own. When unset, `tsconfig.json` at the root is passed if it exists |

An import the cruiser cannot resolve is never an edge: it is reported as the warning
`unresolved import <specifier> in <module>`. A module or dependency resolved outside the project
root (a path starting with `../`) is an external tagged `vendor`, named after its first path
segment, with the warning `module outside the root: <path>`.

## Known limits

The derived graph covers only what the project's cruiser configuration includes. When that
configuration excludes test files, `arch query units --kind test` returns only the test units the
configuration does include, W7 evaluates that narrower set, and the run log records that the
scope was narrowed.

Export counts come from a statement-level scan, so three shapes are counted coarsely: an
`export type { ... }` re-export counts its names as concrete, each overload signature of an
exported function counts as one export, and a barrel's `export * from` counts once, at the
barrel. The skill's own tests exercise this scan only where `typescript` is installed; it is
otherwise untested.

## `graph`

Builds `.architecture/graph/<commit>.json`: units with component, ring, kind, actors, and export
counts; edges with direction and crossings; externals; component metrics; component edges;
cycles; uncovered modules. Deterministic from a commit; rebuilt when the cache is missing, when
the cached file's `version` differs from the command's graph format version, when `--force` is
given, or when either saved-output flag is given. A commit with no
`docs/architecture/model/components.json` stops the run with `no architecture model at <ref>`.

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
Cycles (component and module cycles, new and gone). Missing values render as in `query`: an
empty side for fan-in and fan-out, `undefined` for I, A, and D.

When `<base>` has no `docs/architecture/model/components.json`, it exits 1 with
`no architecture model at <base>; evaluate the working tree with "arch query touched --base
<base>" (change-review.md, Map step 4)`.

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
`Reads:` line names the query; those `Reads:` lines are authoritative. A mode step that runs a
query outside a workflow is named after its mode file (`change-review.md`, `plan-review.md`).

Callers have no command: the structural precheck a caller runs before dispatching a review is a
hand match of the plan's or diff's file list against the globs in
`docs/architecture/model/components.json`. `touched` belongs to change review.

| Query | Arguments | Columns | Read by |
|---|---|---|---|
| `metrics` | none | Component, Units, Fan-in, Fan-out, I, A, D, Zone | W5, W6 |
| `component-graph` | none | From, To, Importing modules | W6, W8 |
| `cycles` | none | Level, Members | W6 |
| `ring-crossings` | `[--direction outward\|inward\|same]` (default `outward`) | From, From ring, To, To ring, Kind | W1, W2, W3, W4 |
| `fan-in` | `<path>` | Importer, Component, Kind | W7, severity escalation rule 3 |
| `edges` | `<path>` (required) | Direction, Other, Kind, Ring direction | plan review step 1 |
| `units` | `[--component <id>] [--kind <k>] [--ring <r>]` | Path, Kind, Ring, Actors, Abstract, Concrete | W2, W3, W4, W7 |
| `touched` | `--base <ref>` (required) | Path, Component, Kind, Ring, Change, Neighbors | change review |
| `ports` | none | Port, Owner, Humble side, Implementers, Consumers (by component) | W1, W3, W4, W5, W7 |
| `entry-points` | none | Path, Component, Constructs | W1, W7 |
| `externals` | `[--tag vendor\|framework\|runtime]` | Name, Tag, Importing components, Importing modules | W5, W8 |
| `volatility` | `--since <ref>` (required) | Component, Commits, Modules touched | W1, W2, W5, W6 |

`edges` lists the module's outgoing internal edges (`out`) and then its incoming ones (`in`),
with the ring direction of each edge. `entry-points` expands each component's entry-point globs
against the graph's units and prints one row per matching unit. `touched` reads `git diff
--name-status` against the base plus untracked files: a copy or an untracked unit is `added`, a
type change is `modified`, and a deleted path is listed only when it was a unit in the base
graph.

`touched`, `volatility`, and `edges` exit with a usage message when their required argument is
missing. In a markdown table a missing value renders as an empty cell, except the I, A, and D
columns of `metrics`, which render `undefined`; with `--json` it is `null`. A query over an empty
graph section renders no rows.

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
| `validate` | Rebuild the graph, print its warnings to stderr, and report every model problem (a hard problem, an unused rule, a stale override); print `model: ok` and exit 0 when there are none, even when the adapter warned |
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

`arch model` with no subcommand prints `usage: arch model <validate|add-override|remove-override|add-port|remove-port|add-component|remove-component|add-rule|remove-rule>`
and exits 1. `add-override` without a path, `add-rule` without `match=`, and `add-component`
without an ID, a name, and `paths=` print that subcommand's usage line and exit 1. A kind must
be one of the `kinds` listed in `rules.json`, or of the default kinds in `mapping.md` when the
list is absent. `add-component` also refuses globs that share a git-tracked path with an
existing component.

## `readme-summary`

| Flag or argument | Meaning |
|---|---|
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--exports-json <file>` | Read export data from `<file>` instead of running the tooling |

Rewrites the block between the `<!-- arch:summary -->` and `<!-- /arch:summary -->` markers in
`docs/architecture/README.md` with the components, units, edges, component cycles, and uncovered
counts, the metrics table, and the component graph table. Fails when the markers are missing.
