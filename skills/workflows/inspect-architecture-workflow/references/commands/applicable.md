# arch applicable

What `arch applicable` does, its flags, exit codes, and output. Read it when `applicable` fails or
when reading its JSON. It answers whether a change needs a reviewer and, if so, which rule groups
and which judgment conditions are in scope, so a flow dispatches a reviewer only when one has work
and names only the rule-group files it needs.

## Synopsis

```
arch applicable --base <ref>
arch applicable --files <a,b>
arch applicable --base <ref> --full
```

## Flags

| Flag | Value | Meaning |
|---|---|---|
| `--base` | a branch, tag, or commit | The change is everything that differs from that commit. |
| `--files` | comma-separated paths from the project root | The change is these files, classified by the model as they stand. Additions such as a new component edge are not detected. |
| `--full` | none | Review every judgment condition in scope even when the change is contained. |
| `--json` | none | Print the JSON output instead of the report. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

Pass exactly one of `--base` and `--files`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The answer was printed, whatever it is, including when there is no model. |
| 2 | An invalid model, an adapter failure, or a usage error, such as both or neither of `--base` and `--files`. |

## Output

A review is needed when the change touches more than one component, adds a component, a port, a
cross-component edge, or an external, or touches files the model does not cover. A change contained
in one component that adds none of these needs no reviewer; the output then counts the judgment
conditions it left unreviewed, and `--full` reviews them.

The report prints "Review needed: yes" or "no", the reasons, each rule group with judgment
conditions in scope and its rules, the uncovered files, and the count of conditions not reviewed.

The JSON output has `model`; `review`, true or false; `reasons`; `groups`, the rule-group names,
each the name of a rule-group file; `judgments`, the judgment ids in scope per group; `uncovered`,
the touched paths no pattern covers; and `notReviewed`, the count of judgment conditions a contained
change left out. Without a model it is
`{"model":false,"review":false,"reasons":["no architecture model; run a baseline audit to enable the full review"]}`
and the report is that line alone.

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

Six of the nine group lines are left out here for length. With `--files src/domain/employee.ts`
the same fixture prints "Review needed: no" and "Judgment conditions not reviewed for a contained
change: 22. Pass --full to review them."
