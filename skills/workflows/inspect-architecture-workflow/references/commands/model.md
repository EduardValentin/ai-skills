# arch model

What `arch model` does: create, check, explain, and edit `architecture.json`, the one model file in
the record path. Read it before any model edit, when a flow names an edit, or when a model command
fails. The model is edited only through these subcommands, which validate the result against the
published schema and write one entry per line in a canonical order.

## Synopsis

```
arch model explain <path>
arch model set-rule <R> <enforced|advisory|off> reason=<text>
arch model add-exception <from> <to> rule=<R> reason=<text>
```

Each subcommand and its usage line are listed below. Arguments are positional; details are
`key=value` pairs, and the usage line marks the optional ones with brackets. Quote a value with
spaces, and quote any pattern with `*` so the shell does not expand it, as in
`arch model classify domain "**/*-use-case.ts" use-case "before=**"`.

Create and check the model:

- `arch model init --start <greenfield|legacy> --adapter "<command>" [--record-mode committed|local]`: write a new model holding the adapter command and the starting point's default rule statuses, with no components yet; `add-component` adds the first. `local` also adds the record path to the repository's local exclude file. Refuses to overwrite a model.
- `arch model migrate`: convert the four model files of the earlier format into `architecture.json`, leaving them in place. The adapter is left empty; set it with `set-adapter`.
- `arch model status`: say whether a model file exists, without reading the code or running the adapter. A flow runs it first to learn whether there is a model.
- `arch model validate`: check the model file against the schema, then the model against the code. It fails on a model with no components, a classification pattern or a port that matches no module, a module two components claim, and a forbidden edge or exception whose end is not exact: a component, a ring, an external the adapter reports, `*` as a destination, or the path of a module with or without `#<Symbol>`. A glob end is refused.
- `arch model explain <path>`: print the path's component, kind, ring, actors, and the classification pair that matched.
- `arch model explain-thresholds`: print every knob with its default, the project's value, and its meaning.

Components and classification:

- `arch model add-component <name> paths=<globs>`: add a component owning the comma-separated globs.
- `arch model remove-component <name>`
- `arch model classify <component> <pattern> <kind> [ring=<ring>] [actors=<a,b>] [reason=<text>] [value-type=true] [before=<pattern>]`: add or replace a pair; the pattern is relative to the component's paths, and the first matching pair wins. `before=` inserts the pair ahead of an existing pattern; `ring=`, `actors=`, `reason=`, and `value-type=true` record what differs from the kind's default.
- `arch model unclassify <component> <pattern>`
- `arch model add-port <path>#<Symbol> owner=<component> [humble=<ring>] [defers=<text>]`: record a port, the component that owns it, the ring of its humble side, and the decision it defers.
- `arch model remove-port <path>#<Symbol>`
- `arch model add-group <name> members=<a,b> absorbs=<text>`: record a cohesion group and the kind of change it absorbs.
- `arch model remove-group <name>`

Rule statuses, thresholds, and accepted findings:

- `arch model set-rule <R>[@<component>] <enforced|advisory|off> reason=<text>`: set a rule's status for the project, or for one component with `@<component>`. `advisory` findings are reported and never count toward the verdict; `off` conditions are not checked.
- `arch model unset-rule <R>[@<component>]`: return the rule to its default status.
- `arch model set-threshold <knob> <value>`: override a knob; `explain-thresholds` lists them.
- `arch model unset-threshold <knob>`: return the knob to its default.
- `arch model add-forbidden-edge <from> <to> reason=<text>`: record a dependency that must not exist, so a check reports it. Each end is matched exactly, as for an exception: a component name, `ring:<ring>`, or a unit path.
- `arch model remove-forbidden-edge <from> <to>`
- `arch model add-exception <from> <to> [rule=<R>] reason=<text>`: accept a finding by recording an intended dependency, for one target or generalized to a component or ring pair. Ends are matched exactly, never as globs: a unit path, `<path>#<Symbol>` (a port), a component name, or `ring:<name>`; `to` may also be `external:<name>`, or the literal `*` to accept a finding about one target instead of an edge. With `*`, `from` names that target: a unit path covers the unit and its ports, a `<path>#<Symbol>` covers only that port, a component name covers the component, and `ring:<name>` covers every unit of the ring. A `*` exception never covers a dependency cycle. Without `rule=` it covers every rule. `arch findings add` drops a judged finding that an exception covers, and `arch check` counts a covered row in `covered`.
- `arch model remove-exception <from> <to> [rule=<R>]`
- `arch model add-upcoming <text>`: remember an upcoming change the user confirmed, so every later review counts it as a named upcoming change, as `--upcoming` does for one run of `arch findings add`. Refused when the same text is already recorded.
- `arch model remove-upcoming <text>`: forget a recorded upcoming change once it has shipped or been dropped.
- `arch model set-adapter <command>`: set the command that prints the adapter document.

## Flags

| Flag | Value | Meaning |
|---|---|---|
| `--start` | `greenfield` or `legacy` | `init` only: the starting point, which sets the default rule statuses. |
| `--adapter` | a shell command | `init` only, and required there: the project's adapter command. |
| `--record-mode` | `committed` or `local` | `init` only: whether the record is committed. `committed` by default. |
| `--json` | none | `validate`, `status`, `explain`, and `explain-thresholds`: print JSON. Edits ignore it. |
| `--record` | a directory | Use this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

A flag given to a subcommand it does not apply to is a usage error.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The model was written, or the answer was printed. `status` exits 0 whether or not a model exists. |
| 2 | A usage error, no model, a model that does not fit the code or an adapter that cannot run (`validate`), or an edit that would make the model invalid, in which case the file is left unchanged. |

## Output

An edit prints `updated <model file>`; `init` and `migrate` print `wrote <model file>` and the next
step. `status` prints `model: present at <model file>` or `model: absent; run a baseline audit`;
with `--json`, an object with `model`, true or false, and `path`, the model file. `validate` prints `model: ok` only when
the model file and the code both pass. A model that does not fit the code exits 2 with
`model does not fit the code:` and one line per problem on standard error. When the adapter cannot
run, `validate` prints `model file: ok` and then exits 2 with the tooling error. A refused edit prints
`edit refused, <model file> left unchanged:` and each schema problem. With `--json`, `explain`
prints `path`, `component`, `kind`, `ring`, `actors`, `valueType`, and `matched` (`component`,
`index`, `pattern`), each `null` when unknown; `explain-thresholds` prints one object per knob with
`knob`, `default`, `project`, and `description`.

## Example

In a project with no model, then on the payroll fixture: explaining a path, recording the same
upcoming change twice, and validating after an exception was recorded for a file that does not
exist:

```
$ arch model status
model: absent; run a baseline audit
$ arch model status --json
{
  "model": false,
  "path": "/project/docs/architecture/architecture.json"
}
$ arch model explain src/domain/payroll-use-case.ts
path: src/domain/payroll-use-case.ts
component: domain
kind: use-case
ring: use-cases
actors: unknown
matched: domain, pair 1: **/*-use-case.ts -> use-case
$ arch model add-upcoming "a second delivery mechanism"
updated docs/architecture/architecture.json
$ arch model add-upcoming "a second delivery mechanism"
the upcoming change "a second delivery mechanism" is already recorded. Nothing was changed.
$ arch model validate
model does not fit the code:
- exceptions src/web/gone.ts -> *: "src/web/gone.ts" is not a component, a ring, or the exact path of a module. Ends are matched exactly, never as globs. Run arch model remove-exception src/web/gone.ts *, then add it again with a component name, ring:<ring>, or the exact path of a module.
Fix these entries and run arch model validate again.
```

The command prints the model file's absolute path; it is shortened here, and `/project` stands for
the project root.
