# arch applicable

What `arch applicable` does, its flags, exit codes, and output. Read it when `applicable` fails or
when reading its JSON. It reports the scope of a review: the touched units and components, the
uncovered files, what the change adds, and the judgment conditions that apply, grouped by rule
group, so a flow hands its reviewer exactly those conditions and names only the rule-group files it
needs. It never weighs whether a change is worth a review: once a review is selected, a reviewer
judges whatever this command lists, and only a scope with no judgment condition, one that touches
no code and changes no dependency, gets none. Without a model it says so, which is how every flow learns there is no model
before doing anything else.

## Synopsis

```
arch applicable --base <ref>
arch applicable --files <a,b>
arch applicable --proposal .architecture/work/proposal.json
arch applicable --all
arch applicable --all --out .architecture/work/applicable.json
```

## Flags

| Flag | Value | Meaning |
|---|---|---|
| `--base` | a branch, tag, or commit | The scope is a change: everything that differs from that commit. |
| `--files` | comma-separated paths from the project root | The scope is these files, classified by the model as they stand. Additions such as a new component edge are not detected. |
| `--proposal` | a proposal, a working file | The scope is a plan: the proposal's modules and edges, the components and component edges they add, and the plan itself, so the judgments whose target is `plan` are in scope. The file has the shape `arch check` reads with `--proposal`. |
| `--all` | none | The scope is every unit and component, as in an audit. |
| `--out` | a working file | Write the JSON output to this file and print the one-line scope summary instead. `arch findings add` reads the file with `--applicable`. |
| `--json` | none | Print the JSON output instead of the report. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

Pass exactly one of `--base`, `--files`, `--proposal`, and `--all`. Working files live under
`.architecture/work/`; the command refuses a working file elsewhere inside the project.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The scope was printed, whatever it holds, including when there is no model. |
| 2 | An invalid model, an adapter failure, an unreadable proposal, or a usage error, such as none or more than one of `--base`, `--files`, `--proposal`, and `--all`. |

## Output

A judgment condition is in scope when its rule is not `off` for the component of a target in scope.
The targets are the kinds of the touched units, `test-suite` for a touched test, `component` for each
component the scope adds or links by a new component edge, every component with `--all`, and `plan`
with `--proposal`. Whenever at least one unit is touched, covered or not, the cross-cutting conditions
that apply to every unit kind are in scope too, so a reviewer always has the conditions every change
is judged against. A scope that touches no unit can still add a component edge or an external,
which brings conditions into scope; only `inScope` 0 leaves a flow nothing to review.

The report opens with `Scope of the review: <n> units in <m> components (<names>)`, the count of
uncovered files when there are any, and the count of judgment conditions and rule groups; a scope
that touches nothing reads `Scope of the review: no unit touched`. Then come `Adds:`, one line per
component, port, component edge, or external the change adds, each rule group with judgment
conditions and its rules, and the uncovered files.

The JSON output has `model`; `mode`, the scope flag given (`base`, `files`, `proposal`, or `all`);
`run`, the record `arch findings add` binds the file to, as it binds the check file: the `mode`
(`audit` for `--all`), the resolved `base`, the `proposal` path, and the working-tree `state`;
`units`, each touched unit the model covers with its `path`, `kind`, and `component`, or with
`--all` only their count; `components`,
the touched components; `uncovered`, the paths in scope no pattern covers; `adds`, the plain facts of
what the change adds: `components`, `ports` (each `<path>#<Symbol>`), `componentEdges` (each
`<from> -> <to>`), and `externals`, all empty with `--files` and `--all`; `groups`, the rule-group
names, each the name of a rule-group file; `judgments`, the judgments in scope per group, each with
its `id`, its `targets`, and its one-sentence `condition` with the project's knob values filled in, so
a caller can hand a reviewer the conditions as they are, the cross-cutting ones listed once under
`cross-cutting`; and `inScope`, the count of judgment conditions listed. Without a model it is
`{"model":false,"reasons":["no architecture model; run a baseline audit to enable the full review"]}`
and the report is that line alone. With `--out`, the command prints `wrote <file>: ` followed by the
scope summary, or `wrote <file>: no model`.

## Example

From the payroll fixture after a commit that makes the payroll use case import the system clock
adapter:

```
$ arch applicable --base main
Scope of the review: 1 unit in 1 component (domain); 38 judgment conditions in 9 rule groups
Adds:
- component edge domain -> adapters
Rule groups with judgment conditions:
- cross-cutting: R2 Name a shape mismatch
- dependency-direction: R4 Dependencies point toward policy; R7 Lower-level components are plugins; R8 Constraints need a named reason
- humble-objects: R22 Reach storage through a gateway
Uncovered files:
- none
```

Six of the nine group lines are left out here for length. On the same fixture, a commit that only
adds a constant to `src/domain/employee.ts` adds nothing, and still has conditions for its reviewer:

```
$ arch applicable --base main --out .architecture/work/applicable.json
wrote .architecture/work/applicable.json: 1 unit in 1 component (domain); 22 judgment conditions in 8 rule groups
```

With `--all`, the known-defects fixture prints "Scope of the review: 27 units in 8 components
(lending, storage, notify, web, catalog, reports, archive, kiosk); 60 judgment conditions in 9 rule
groups" and all nine rule groups.
