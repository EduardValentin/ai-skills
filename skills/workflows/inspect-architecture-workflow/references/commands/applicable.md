# arch applicable

What `arch applicable` does, its flags, exit codes, and output. Read it when `applicable` fails or
when reading its JSON. It answers whether a scope needs a reviewer and, if so, which rule groups and
which judgment conditions are in scope, so a flow dispatches a reviewer only when one has work and
names only the rule-group files it needs. Without a model it says so, which is how every flow
learns there is no model before doing anything else.

## Synopsis

```
arch applicable --base <ref>
arch applicable --base <ref> --full
arch applicable --files <a,b>
arch applicable --proposal .architecture/work/proposal.json --full
arch applicable --all
arch applicable --all --out .architecture/work/applicable.json
```

## Flags

| Flag | Value | Meaning |
|---|---|---|
| `--base` | a branch, tag, or commit | The scope is a change: everything that differs from that commit. |
| `--files` | comma-separated paths from the project root | The scope is these files, classified by the model as they stand. Additions such as a new component edge are not detected. |
| `--proposal` | a proposal, a working file | The scope is a plan: the proposal's modules and edges, the components and component edges they add, and the plan itself, so the judgments whose target is `plan` are in scope. The file has the shape `arch check` reads with `--proposal`. |
| `--all` | none | The scope is every unit and component, as in an audit. A review is needed whenever any judgment condition is in scope. |
| `--full` | none | With `--base`, `--files`, or `--proposal`: list every judgment condition in scope even when the scope is contained in one component. `--all` already lists them all. |
| `--out` | a working file | Write the JSON output to this file and print one line with its counts instead. `arch findings add` reads the file with `--applicable`. |
| `--json` | none | Print the JSON output instead of the report. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

Pass exactly one of `--base`, `--files`, `--proposal`, and `--all`. Working files live under
`.architecture/work/`; the command refuses a working file elsewhere inside the project.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The answer was printed, whatever it is, including when there is no model. |
| 2 | An invalid model, an adapter failure, an unreadable proposal, or a usage error, such as none or more than one of `--base`, `--files`, `--proposal`, and `--all`. |

## Output

For `--base`, `--files`, and `--proposal`, a review is needed when the scope touches more than one
component, adds a component, a port, a cross-component edge, or an external, or touches files the
model does not cover. A scope contained in one component that adds none of these needs no
reviewer; the output then counts the judgment conditions it left out, and `--full` lists them. For
`--all`, a review is needed when any judgment condition of a rule that is not `off` has a target.

The report prints "Review needed: yes" or "no", the reasons, each rule group with judgment
conditions in scope and its rules, the uncovered files, and the count of conditions not reviewed.

The JSON output has `model`; `mode`, the scope flag given (`base`, `files`, `proposal`, or `all`);
`review`, true or false; `reasons`; `groups`, the rule-group names,
each the name of a rule-group file; `judgments`, the judgments in scope per group, each with its
`id`, its `targets`, and its one-sentence `condition` with the project's knob values filled in,
so a caller can hand a reviewer the conditions as they are; with `--all`, the cross-cutting
judgments are listed once under `cross-cutting`; `uncovered`,
the paths in scope no pattern covers; `inScope`, the count of judgment conditions in scope, listed
or left out; and `notReviewed`, the count of judgment conditions a contained scope left out. Without a model it is
`{"model":false,"review":false,"reasons":["no architecture model; run a baseline audit to enable the full review"]}`
and the report is that line alone. With `--out`, the command prints
`wrote <file>: review <yes|no>, <n> judgment conditions in scope, <m> not reviewed`, or
`wrote <file>: no model`.

## Example

From the payroll fixture after a commit that makes the payroll use case import the system clock
adapter:

```
$ arch applicable --base main
Review needed: yes
Reasons:
- the change adds the component edge domain -> adapters
Rule groups with judgment conditions:
- cross-cutting: R2 Name a shape mismatch
- dependency-direction: R4 Dependencies point toward policy; R7 Lower-level components are plugins; R8 Constraints need a named reason
- humble-objects: R22 Reach storage through a gateway
Uncovered files:
- none
```

Six of the nine group lines are left out here for length. On the same fixture before that commit, a
proposal that only adds `src/domain/bonus-use-case.ts` importing `src/domain/employee.ts` stays in
one component:

```
$ arch applicable --proposal .architecture/work/proposal.json
Review needed: no
Reasons:
- contained in one component; adds no component, port, cross-component edge, or external
Rule groups with judgment conditions:
- none
Uncovered files:
- none
Judgment conditions not reviewed for a contained change: 27. Pass --full to review them.
```

With `--all`, the known-defects fixture prints "Review needed: yes" with the reason "audit: every
unit and component is in scope and 60 judgment conditions apply" and all nine rule groups.
