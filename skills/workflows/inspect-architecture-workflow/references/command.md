# The arch command

Run `node <skill>/scripts/arch.mjs <subcommand>` from the inspected project's root, where
`<skill>` is this skill's directory, the folder holding `SKILL.md`. The coordinator resolves that
folder once per run and writes its absolute path into every packet, so no subagent has to find it
itself.

## Exit codes

0 when the subcommand succeeds. 1 on a usage error (a missing subcommand or required argument),
a hard model problem, or a tooling error (a language with no adapter, tooling that cannot run).
`arch uncovered` returns 1 whenever it lists at least one module; that is its normal job, not a
failure. `arch assess` returns 0 whenever it succeeds, rows or not.

`--json`, `--force`, `--with-neighbors`, `--one-off`, and `--standing` are switches: they never
take a value, so an argument after them stays positional. Every other flag takes the next argument as its value.

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
| `tsConfig` | The TypeScript config that resolves path aliases, passed to the cruiser with `--ts-config` only when the bundled default config runs; a project's own config carries its own. When unset, `tsconfig.json` at the root is passed if it exists. The same file supplies the compiler options of the program the adapter builds for its facts; with neither, the program uses default options |

The TypeScript adapter provides all four facts (see Adapter facts). It builds one TypeScript
program over the module set so the checker resolves imported types, and tests each exported value
of a module for assignability to every port declared in `boundaries.json` whose module is in the
set; a match adds the port's symbol to `implements` next to the nominal `implements` clauses, once.
When the program cannot be built, it falls back to parsing each file alone, provides `exports` and
nominal `implements` only, sets `constructs` and `signatures` to false, and warns
`cannot build a TypeScript program (<reason>); constructs and signatures are not provided`. The
skill's own tests exercise the program-built facts only where `typescript` is installed; otherwise
they cover only the fallback to per-file parsing.

An import the cruiser cannot resolve is never an edge: it is reported as the warning
`unresolved import <specifier> in <module>`. A module or dependency resolved outside the project
root (a path starting with `../`) is an external tagged `vendor`, named after its first path
segment, with the warning `module outside the root: <path>`.

## Adapter facts

Beside the edges, the adapter supplies up to four optional facts per module and declares which it
provides; the graph records them as `capabilities`, each true or false.

| Fact | In the graph | Absent means |
|---|---|---|
| `exports` | `units[].exports`: abstract and concrete exported declarations | `exports` is `null`; A and D are `undefined` and no zone is assigned |
| `implements` | `units[].implements`: the port symbols a unit implements, nominally or by assignability to a declared port | `implements` is `null`; the `ports` Implementers cell reads `not provided by the adapter` |
| `constructs` | edges of kind `constructs`: from a unit to the unit whose type it instantiates | no `constructs` edges |
| `signatures` | `units[].signatures`: for each exported symbol, the types from other units named in its public interface, as `{ symbol, types: [{ symbol, path }] }` | `signatures` is `null`; `query signatures` prints `not provided by the adapter` |

A query that needs an absent fact prints `not provided by the adapter` and exits 0; with `--json`
it prints `{"notProvided": "<fact>", "message": "not provided by the adapter"}`. Nothing that
depends on an absent fact is left silently empty; the workflow settles it through a fact slice
(`slicing.md`).

A `constructs` edge gets its crossings and ring direction like an import edge and counts toward
fan-in, fan-out, component edges, and cycles like one. It usually runs parallel to an import edge
between the same two units, so it adds an edge but never a new importer.

`--facts-json <file>` feeds saved facts instead of asking the adapter:

```json
{ "capabilities": { "exports": true, "implements": true, "constructs": true, "signatures": true },
  "modules": { "<path>": { "exports": { "abstract": 0, "concrete": 1 }, "implements": [],
                           "constructs": [{ "symbol": "<Symbol>", "path": "<path>" }],
                           "signatures": [{ "symbol": "<Symbol>", "types": [{ "symbol": "<Symbol>", "path": "<path>" }] }] } } }
```

A capability left out is false, and a fact whose capability is false is ignored. A module with no
entry gets empty facts and the warning `no facts entry for <path>`. `--exports-json <file>` is an
alias of `--facts-json`; it also reads the older per-module `{ exports, implements }` map, which
provides `exports` and `implements` only.

## Known limits

The derived graph covers only what the project's cruiser configuration includes. When that
configuration excludes test files, `arch query units --kind test` returns only the test units the
configuration does include, W7 evaluates that narrower set, and the run log records that the
scope was narrowed.

Export counts come from a statement-level scan, so three shapes are counted coarsely: an
`export type { ... }` re-export counts its names as concrete, each overload signature of an
exported function counts as one export, and a barrel's `export * from` counts once, at the
barrel.

The `ports` query lists the implementers the `implements` fact names. Assignability is tested only
against declared ports and only for a module's own exported values, so a re-export, a value of an
unchecked type, or a port with no members never counts as a structural implementer; a port that is
not yet declared has only nominal implementers. A port whose members are all optional matches
structurally in any module that exports an object. An implementer the fact misses is settled through a fact
slice (`slicing.md`).

## `graph`

Builds `.architecture/graph/<commit>.json`: the adapter's `capabilities`; units with component,
ring, kind, actors, and the adapter facts; edges of kind `import`, `type-import`, `dynamic`, and
`constructs`, with direction and crossings; externals; component metrics; component edges;
cycles; uncovered modules. Deterministic from a commit; rebuilt when the cache is missing, when
the cached file's `version` differs from the command's graph format version, when `--force` is
given, or when either saved-output flag is given. A commit with no
`docs/architecture/model/components.json` stops the run with `no architecture model at <ref>`.

| Flag or argument | Meaning |
|---|---|
| `--commit <ref>` | Build the graph for `<ref>` instead of the working tree |
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--facts-json <file>` | Read the adapter facts from `<file>` instead of running the tooling; `--exports-json` is an alias |
| `--force` | Rebuild even when a cached graph file already exists |
| `--json` | Print the full graph as JSON instead of the summary line |

On success it prints `graph: <n> units, <n> edges, <n> components, <n> component cycles, <n>
uncovered -> <path>`. Warnings, such as an unresolved import, an unused rule, or a stale override,
go to stderr whether or not `--json` is set. A hard model problem, meaning overlapping component
globs, an unknown ring or kind, a duplicate component ID, a port or shape owner that is not a
component, or fewer than two distinct rings in `rules.json`, stops the run and exits 1 before any
graph is written.

`--cruise-json` and `--facts-json` feed saved adapter output instead of running the project's
tooling. They exist for tests and for projects whose tooling cannot run in the current
environment; passing either always rebuilds, bypassing the cache.

## `diff`

| Flag or argument | Meaning |
|---|---|
| `<base>` | The commit or ref to diff the working tree against (required) |
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` for both sides instead of running it |
| `--facts-json <file>` | Read the adapter facts from `<file>` for both sides instead of running the tooling; `--exports-json` is an alias |
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

## `assess`

| Flag or argument | Meaning |
|---|---|
| `--base <ref>` | Compare against `<ref>`: set Origin from `arch diff <ref>`, read the touched units and components from `arch query touched --base <ref>`, and emit only the rows inside the change |
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--facts-json <file>` | Read the adapter facts from `<file>` instead of running the tooling; `--exports-json` is an alias |
| `--json` | Print `{ "rows": [...], "notProvided": [...] }` instead of a markdown table; each row is `{ workflow, target, rule, origin, verdict, severity, evidence, change, escalation }` |

Decides every decision-table condition that is a function of edges, rings, unit kinds,
components, metrics, cycles, cohesion groups, and, with `--base`, the change. It prints one
`SHOULD_CHANGE` row per finding, as the ledger's findings table without the ID, Protects, and
Run columns:

| Workflow | Target | Rule | Origin | Verdict | Severity | Evidence | Change | Escalation |
|---|---|---|---|---|---|---|---|---|

It exits 0 whether or not it prints rows: an assessment is not a verdict.

| Condition | Workflow | Rule | Base severity | Target |
|---|---|---|---|---|
| Edge from a policy unit (entity, use-case, port, boundary-data) to a detail unit (controller, presenter, gateway, adapter, composition-root, entry-point, test, config, ui) or to an external of any tag | W1 | R4 | blocker | the edge; `external:<name>` for an external |
| Edge crossing rings outward, for any other unit | W1 | R4 | blocker | the edge |
| `constructs` edge from a unit whose kind is not `composition-root` to a unit whose kind is not a policy kind (entity, use-case, port, boundary-data); needs the `constructs` fact | W1 | R7 | blocker | the edge |
| Cycle in the component graph | W6 | R30 | blocker | the cycle's component IDs, sorted numerically |
| Cycle among modules | W6 | R30 | blocker | the cycle's paths, sorted numerically |
| Component edge whose source has a lower I than its target (from more stable to less stable) | W6 | R31 | major | the component edge `C<a> -> C<b>` |
| Component in the zone of pain (`metrics.md`) that the change touches; with `--base` only; needs the `exports` fact | W6 | R31, R32 | major | the component |
| Component with abstract exports and a fan-in of 0 (no consumer outside at all); needs the `exports` fact | W6 | R31, R32 | minor | the component |
| Change touches two or more components and the model records no groups; with `--base` only | W6 | R28 | minor | `docs/architecture/model/boundaries.json` |
| Change touches a component that shares no recorded group with at least one other touched component; with `--base` only | W6 | R27 | major | each such touched component |

Every other decision-table condition, including any that mentions behavior, intent, naming, or a
document, stays with the evaluator, as does the rest of a condition only partly listed here
(abstract types with no implementor, consumers that use none of a component's abstract types).
An edge that both R4 rows match is one row: the first matching condition decides, as in every
decision table.

R27 reads overlapping groups this way: a touched component is a row when at least one other
touched component shares no recorded group with it. With groups {C1, C2} and {C2, C3} and C1,
C2, and C3 touched, C1 and C3 are rows and C2 is not. The row's Evidence has a fixed form that
`ledger accept --standing` parses: `<X> shares no recorded group with <Y[, Z]>; groups holding
<X>: <G1[, G2]>`, with `none` in place of the group list when no group holds X.

With `--base`, rows outside the change are not emitted. A row is inside the change when its
target is a touched unit, an edge or external import from or to a touched unit, a module cycle
containing a touched unit, a component cycle, component edge, or component touching a touched
component, or a cohesion row (R27, R28).

A row that needs an adapter fact the adapter does not provide is never silently missing: for
each absent fact one line goes to stderr and its name to `notProvided`, and the workflow settles
those conditions through a fact slice (`slicing.md`):

| Absent fact | `notProvided` | stderr line |
|---|---|---|
| `exports` | `abstractness` | `abstractness rows not provided by the adapter; evaluate R31 and R32 from a fact slice` |
| `constructs` | `constructs` | `construction rows not provided by the adapter; evaluate R7 from a fact slice` |

Origin without `--base` is `introduced` on every row (audit). With `--base`, a row is
`introduced` when its target is an edge whose `from -> to` pair is absent at the base (a pair
that only gained another kind is `left`), an external import absent at the base, a module cycle
with an edge between its members whose pair is absent at the base, a component cycle with a
component edge between its members absent at the base, a component edge or component absent at
the base, or a cohesion row (R27, R28), which describes the change itself; every other row is
`left`, so a cycle the change only shrinks stays `left`. When `<ref>` has no
`docs/architecture/model/components.json`, every row is `left` and stderr reads `no architecture
model at <ref>; every assessed row is marked left; set Origin from "arch query touched --base
<ref>" (verdicts.md)`.

Escalation rule 3 of `verdicts.md` is applied here: when the target's component (for an edge,
the component of its `to` unit; for a component edge, its target component) has a fan-in of 3 or
more and the base severity is below `major`, the severity is lifted to `major` and Escalation
reads `rule 3`; a row rule 3 does not lift has an empty Escalation cell. Cycle rows are
`blocker` by their table and rule 4. The coordinator applies the other escalation rules after
merging.

## `query`

| Flag or argument | Meaning |
|---|---|
| `<name>` | The query to run; see the table below |
| `[args]` | The named query's own positional arguments and flags |
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--facts-json <file>` | Read the adapter facts from `<file>` instead of running the tooling; `--exports-json` is an alias |
| `--json` | Print the result as a JSON object of columns and rows instead of a markdown table; `touched --with-neighbors` prints `{ "touched": ..., "neighbors": ... }`, each a columns-and-rows object |

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
| `edges` | `<path>`, `--kind <kind>`, or both (one is required) | Direction, Other, Kind, Ring direction; with `--kind` and no path: From, To, Kind, Ring direction | W1, plan review step 1 |
| `units` | `[--component <id>] [--kind <k>] [--ring <r>]` | Path, Kind, Ring, Actors, Abstract, Concrete | W2, W3, W4, W7 |
| `components` | none | Component, Name, Enforcement, Release unit, Entry points, Units | W8 |
| `groups` | none | Group, Components, Absorbs | W6 |
| `touched` | `--base <ref>` (required), `[--with-neighbors]` | Path, Component, Kind, Ring, Change, Neighbors; with `--with-neighbors` a second table: Path, Component, Kind, Ring, Actors, Abstract, Concrete | change review |
| `ports` | none | Port, Owner, Humble side, Implementers, Consumers (by component) | W1, W3, W4, W5, W7 |
| `entry-points` | none | Path, Component, Constructs | W1, W7 |
| `signatures` | `<path>` (required) | Symbol, Type, From | W1, W3 |
| `externals` | `[--tag vendor\|framework\|runtime]` | Name, Tag, Importing components, Importing modules | W5, W8 |
| `volatility` | `--since <ref>` (required) | Component, Commits, Modules touched | W1, W2, W5, W6 |

`edges --kind <kind>` with no path lists every edge of that kind in the graph; with a path,
`--kind` keeps only that kind. `edges <path>` lists the module's outgoing internal edges (`out`)
and then its incoming ones (`in`), with the kind and ring direction of each edge; a `constructs` edge is listed next to the import
edge it parallels. `fan-in` lists every edge into the module, so an importer that also constructs
the module's type appears once per kind. `signatures` prints one row per type from another unit
that an exported symbol of the module names in its public interface; a symbol whose interface
names none has no row. `ring-crossings` filters every internal edge whose two
rings are known by its direction: `outward` and `inward` list edges that cross rings, `same` lists
edges whose two ends sit in the same ring. `components` prints the component record from
`docs/architecture/model/components.json` with each component's unit count in the graph.
`groups` prints the cohesion groups from `docs/architecture/model/boundaries.json`.
`entry-points` expands each component's entry-point globs
against the graph's units and prints one row per matching unit, its Constructs cell listing every
unit the entry point has an edge to, once. `touched` reads `git diff
--name-status` against the base plus untracked files: a copy or an untracked unit is `added`, a
type change is `modified`, and a deleted path is listed only when it was a unit in the base
graph. With `--with-neighbors`, a second table follows the first: the full unit row of every
unit one edge away from a touched unit that is not itself touched, sorted by path.

`touched`, `volatility`, `edges` (given neither a path nor `--kind`), and `signatures` exit with
a usage message when their required argument is missing. In a markdown table a missing value renders as an empty cell, except the I, A, and D
columns of `metrics`, which render `undefined`; with `--json` it is `null`. A query over an empty
graph section renders no rows.

## `uncovered`

| Flag or argument | Meaning |
|---|---|
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--facts-json <file>` | Read the adapter facts from `<file>` instead of running the tooling; `--exports-json` is an alias |
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
| `add-group <name> components=<C,...> absorbs=<text>` | Add or replace the cohesion group named `<name>` |
| `remove-group <name>` | Remove the cohesion group named `<name>` |

`validate` also accepts `--cruise-json <file>` and `--facts-json <file>` to feed saved adapter
output instead of running the tooling.

`arch model` with no subcommand prints `usage: arch model <validate|add-override|remove-override|add-port|remove-port|add-component|remove-component|add-rule|remove-rule|add-group|remove-group>`
and exits 1. `add-override` without a path, `add-rule` without `match=`, `add-component`
without an ID, a name, and `paths=`, and `add-group` without a name, `components=`, and
`absorbs=` print that subcommand's usage line and exit 1. A kind must
be one of the `kinds` listed in `rules.json`, or of the default kinds in `mapping.md` when the
list is absent. `add-component` also refuses globs that share a git-tracked path with an
existing component. `add-group` also refuses a group whose `components` name an unknown
component.

## `ledger`

Keeps `.architecture/ledger.md`, the uncommitted ledger, so the coordinator never edits its
tables by hand. A missing ledger starts from `assets/ledger/ledger.md`. Every table keeps the
template's columns and every line of prose is kept as written. The run's commit is the short head
commit, or `working-tree` when the tree has uncommitted changes, as `graph` keys it. A finding
resolved `at working-tree` was judged on uncommitted code; the next run on a clean tree confirms
it, and a finding found again there reopens with its ID.

| Subcommand | Meaning |
|---|---|
| `add-run --mode <audit\|change-review\|plan-review> --scope <text> --rows <file> [--base <ref>] [--plan <path>] [--skipped W1,W6] [--evaluated <file>] [--removed <file>]` | Merge this run's rows into the findings and append the run log row |
| `accept <F-id> --one-off\|--standing --by <who> --reason <text>` | Accept a finding and write its Acceptances row |
| `map [--agents "<n> mapping, <n> fact, <n> evaluation"]` | Rewrite the Changes and Improvement map tables and print the return contract lines |

### Row file

`--rows` names a markdown file holding one or more tables in the `assess` column set, `Workflow |
Target | Rule | Origin | Verdict | Severity | Evidence | Change | Escalation`, optionally with a
`Protects` column; columns are read by header, so the `assess` output and the evaluator rows can
be concatenated as separate tables. A literal `|` inside a cell is written `\|`. Verdict is `OK`,
`SHOULD_CHANGE`, or `UNDERSPECIFIED`. Origin is required in a change review and defaults to
`introduced` in the other modes. An Escalation cell naming rules (`rule 3`) is kept as `[rule 3]`
markers at the end of the Evidence cell; the coordinator writes `[rule 1]`, `[rule 2]`, or
`[rule 4]` the same way when it lifts a row, since the escalation counts and the run verdict read
those markers. The Severity cell is `<severity>`, or `<severity> (base <severity>)` for a lifted
row (`verdicts.md`, Severity); a row carrying only `[rule 1]` or `[rule 3]` marks at `major` with
no base written is stored as `major (base minor)`, since those rules lift to `major` and only
from below it. Every count and ordering reads the first word. Two rows with the same target and
rule merge into one: the highest severity with its base (at equal severity, the cell that
carries a base), the union of the `[rule <n>]` marks, and
the longer evidence.

`--evaluated` and `--removed` name files listing targets one per line; blank lines and lines
starting with `#` are ignored. A listed unit path covers the edges, ports, and cycles that name
it; a line `*` in `--evaluated` covers every target, for an audit of the whole repository. Every
target of an incoming row counts as evaluated.

### `add-run`

Matches each incoming row to the existing finding with the same target and rule, keeping its ID;
an unmatched row gets the next free `F<n>`. A matched `ACCEPTED` finding stays `ACCEPTED`; an
incoming `OK` row resolves a matched open finding. Each previous `SHOULD_CHANGE`, `ACCEPTED`, or
`UNDERSPECIFIED` finding absent from the incoming rows is settled in this order: a target listed
in `--removed` becomes `RESOLVED` with `resolved at <commit>: target removed` appended to its
Evidence; a finding of a workflow named in `--skipped` is carried forward unchanged; a target
evaluated this run becomes `RESOLVED` with `resolved at <commit>` appended; any other finding is
carried forward unchanged. A carried-forward finding keeps its Run.

`--scope` is free text for people. The run's identity for the fix loop is its Key: the short
commit `--base <ref>` resolves to in a change review, the `--plan <path>` as given in a plan
review, and `audit` in an audit. `--base` is required in a change review and `--plan` in a plan
review; without it the command prints its usage and exits 1.

The run log row records the mode, the scope (with `; skipped W1, W6` when workflows were
skipped), the Key, the commit, and the run verdict and counts described under `map`, computed
after the run is recorded, so they equal what `map` prints for the same ledger. Prints the run
log row:

```markdown
| 2 | 2026-10-14 | 1a2b3c4d | change-review | diff main | 9f8e7d6c | SHOULD_CHANGE | 0 | 1 | 0 | 3 |
```

### `accept`

Sets the finding to `ACCEPTED` and writes its Acceptances row (Finding, One-off or standing,
Reason, Accepted by, today's date, Promoted to; `none` for a one-off). Accepting a finding again
replaces its row. Prints `<F-id> ACCEPTED (<kind>)`. With
`--standing` it also prints the record edit for the coordinator to make, and Promoted to names it:

| Finding | Printed record edit |
|---|---|
| R27 | Read from the Evidence and the current `docs/architecture/model/boundaries.json`: for each group the Evidence names as holding the target, `arch model add-group <group> components=<its current members plus the partners the Evidence names> absorbs="<its absorbs>"`, so successive acceptances accumulate once each printed command runs; when the Evidence says `none`, `arch model add-group <name> components=<the target and the partners> absorbs="<to be stated>"`. Then the group's paragraph in `decisions.md` |
| R28 | `arch model add-group <name> components=<the Evidence's components> absorbs="<reason>"`, then the group's paragraph in `decisions.md` |
| An edge `from -> to` | An Intended exceptions row for `decisions.md`, with each path replaced by its component when the graph of the current commit is saved under `.architecture/graph/` |
| Anything else | A deferred decision or cohesion position to record in `decisions.md` |

Fails with `no finding <F-id>` for an unknown ID and refuses a `RESOLVED` or `OK` finding.

### `map`

Clusters the open `SHOULD_CHANGE` findings by identical Change text into `CH-A`, `CH-B`, and so
on, ordered by the highest severity each change resolves, then by the number of rows, then by
description. It writes the Changes table (Change, Description, Resolves as finding IDs), the
Improvement map (Order, Change, Severity, Rows as a count, Protects as the rows' upcoming changes),
and the `CH-` name into each clustered finding's Change cell; a later `map` reads the names back
through the Changes table. It refreshes the last run log row, since an acceptance changes the
counts, and prints, for the last run, the return contract lines of `verdicts.md` in its
wording: Verdict, Pre-existing, Carried, Escalation, Direction (one numbered line per change, naming the
`CH-` name, the rules, the change, and `protects <upcoming changes>` or `protects none`), and
Agents.

The run's rows are the findings whose Run is the last run, plus the open `SHOULD_CHANGE`
findings whose Run is an earlier run of the same mode and Key: a fix loop keeps counting what it
has not yet re-evaluated. Carried counts the open `SHOULD_CHANGE` findings of every other mode or
Key. A run log row with an empty Key matches no other run. Verdict counts the run's open
`SHOULD_CHANGE` rows that are `introduced` or carry `[rule 2]`, and is `SHOULD_CHANGE` when one of
them is `blocker` or `major`; Pre-existing counts its other open rows; targets OK counts its `OK`
rows; Escalation counts its `SHOULD_CHANGE` and `ACCEPTED` rows per `[rule <n>]` marker;
Direction lists the first three changes of the map. Agents totals the `--agents` counts, or reads
`Agents: <n> dispatched (<n> mapping, <n> fact, <n> evaluation)` without the flag. Fails when the ledger has no run.

## `readme-summary`

| Flag or argument | Meaning |
|---|---|
| `--cruise-json <file>` | Read dependency-cruiser output from `<file>` instead of running it |
| `--facts-json <file>` | Read the adapter facts from `<file>` instead of running the tooling; `--exports-json` is an alias |

Rewrites the block between the `<!-- arch:summary -->` and `<!-- /arch:summary -->` markers in
`docs/architecture/README.md` with the components, units, edges, component cycles, and uncovered
counts, the metrics table, and the component graph table. Fails when the markers are missing.
