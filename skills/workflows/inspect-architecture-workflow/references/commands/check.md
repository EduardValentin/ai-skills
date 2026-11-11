# arch check

What `arch check` does, its flags, exit codes, and output, including the proposal file a plan review
gives it. Read it when `check` fails, when wiring it into continuous integration or a hook, or when
reading its JSON. It decides every condition the command can decide from collected evidence, for
the whole codebase, for a change against a base commit, or for the code plus a plan's proposed
facts. Conditions that need judgment are left to a reviewer.

## Synopsis

```
arch check
arch check --base <ref>
arch check --proposal .architecture/work/proposal.json
arch check --base <ref> --out .architecture/work/check.json
arch check --strict
```

## Flags

| Flag | Value | Meaning |
|---|---|---|
| `--base` | a branch, tag, or commit | Compare with that commit: build its graph with the current model and mark each finding `introduced` or `inherited`. Only findings in the touched scope are reported. |
| `--proposal` | a proposal file | Check the current code plus a plan's proposed facts (shape below). Cannot be combined with `--base`. The proposal is a working file. |
| `--out` | a working file | Write the JSON output there and print one line. |
| `--strict` | none | Also exit 1 when a condition of an enforced rule could not be decided. |
| `--json` | none | Print the JSON output instead of the report. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

Working files live under `.architecture/work/`; the command refuses a working file elsewhere
inside the project, because it would change the reviewed state.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No enforced rule is breached, or there is no model. With `--base` or `--proposal`, no introduced breach. A breach a recorded exception covers does not count. |
| 1 | An enforced rule is breached (with `--base` or `--proposal`, by an introduced finding), or `--strict` and an enforced condition is incomplete. |
| 2 | An invalid model, an adapter failure, an invalid proposal, or a usage error. |

## Output

Without a model the report is the line "no architecture model; run a baseline audit to enable the
full review", and the JSON is `{ "model": false }`.

The report is a table with the columns Rule (number and title), Target, Severity, Status, Origin,
Evidence, and Correction; then "Covered by recorded exceptions" with a count when any finding was
covered; then three sections. Incomplete lists each condition that lacked a fact or a
classification, with what to do. Not run lists each check that needs something this run lacks,
such as `--base`. Rules not enforced lists every rule set to `advisory` or `off`, with its reason.

The JSON output has `model`; `run` (`mode` of `audit`, `base`, or `proposal`, the resolved `base`
commit, the `proposal` path, and the `state` it ran on, which `arch findings add` compares to
refuse a stale check); `rows`, one per finding (`check`, `target`, `defect`, `rules`, `severity`,
`baseSeverity`, `lifts`, `status`, `origin` of `introduced`, `inherited`, or `none`, `evidence`,
`consequence`, one sentence saying what the finding makes harder to change, and `correction`, the
smallest fix first); `incomplete` (`check`, `rules`, `target`, `reason`, and for a plan's open fact
`clarification`, `task`, and `fact`); `notRun` (`check`, `rules`, `reason`); `skipped` (`rule`,
`status`, `reason`, `component`); and `covered`, the count of findings recorded exceptions covered.
With `--out`, the one printed line is `wrote <file>: <n> findings, <n> incomplete`, or
`wrote <file>: no model`.

A proposal file states what a plan adds or removes, in the module and edge shapes of the adapter
document:

```json
{ "version": 1,
  "modules": [ { "path": "src/domain/bonus-use-case.ts" } ],
  "edges": [ { "from": "src/domain/bonus-use-case.ts", "to": "src/domain/employee.ts", "kind": "import" } ],
  "removedModules": [ "src/domain/old.ts" ],
  "removedEdges": [ { "from": "src/web/main.ts", "to": "src/domain/old.ts" } ],
  "classify": [ { "path": "src/reports/bonus.ts", "kind": "presenter", "component": "web" } ],
  "unknown": [ { "task": "Task 2: Bonus report", "fact": "which component the report reads from" } ] }
```

`version` is required and every other field is optional. `classify` places a new module no model
pattern covers. Each `unknown` entry becomes an incomplete clarification request.

## Example

From the payroll fixture, whose model sets R6 off:

```
$ arch check
| Rule | Target | Severity | Status | Origin | Evidence | Correction |
|---|---|---|---|---|---|---|
| R7 Lower-level components are plugins | src/web/payroll-controller.ts -> src/adapters/system-clock.ts | blocker | enforced | none | concrete detail constructed outside a composition root: src/web/payroll-controller.ts (adapters, controller) constructs src/adapters/system-clock.ts (adapters, adapter) | Move the construction of src/adapters/system-clock.ts from src/web/payroll-controller.ts into the composition root and pass it to src/web/payroll-controller.ts as the existing port `Clock` in `src/domain/clock.ts` |
| R38 Enforce boundaries with the build | domain | major | enforced | none | domain has enforcement "none", which the build does not check, and adapters, web depend on it | Enforce the boundary of domain with the compiler or the build, then record how in its enforcement field |

## Incomplete

- type-check-on-implementation (R13 Substitutable implementations, narrow interfaces): the adapter document does not provide typeChecks, so type-check-on-implementation could not be decided. Make the adapter provide it, or set R13 to advisory or off with arch model set-rule.

## Not run

- zone-of-pain (R31 Depend toward stability; R32 Use metrics as a screen): needs --base
- no-cohesion-groups (R28 Name your cohesion position): needs --base
- change-spans-groups (R27 One component, one published surface): needs --base
- distance-over-threshold (R32 Use metrics as a screen): fewer than 8 components

## Rules not enforced

- R6 Use cases own their boundaries: off (one delivery mechanism; controllers call use cases directly)
```

Two of the four rows are left out here for length; the command exits 1 because enforced rules are
breached.
