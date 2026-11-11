# arch findings

What `arch findings add` and `arch findings list` do, their flags, exit codes, and output, and the
shape of a reviewer's judged findings. Read it when either fails or refuses findings. `add` merges a
check's findings with a reviewer's judged findings, applies the escalation the command owns, stores
the open findings in `.architecture/findings.json`, and prints the result with its verdict. `list`
prints that result again.

## Synopsis

```
arch findings add --flow change-review --base <ref> --check .architecture/work/check.json --judged .architecture/work/judged.json
arch findings add --flow plan-review --plan <plan> --proposal .architecture/work/proposal.json --check .architecture/work/check.json
arch findings add --flow audit --check .architecture/work/check.json --upcoming "<confirmed upcoming change>"
arch findings list
arch findings list --rank
```

## Flags

`add`:

| Flag | Value | Meaning |
|---|---|---|
| `--flow` | `audit`, `change-review`, or `plan-review` | Required: which flow produced the findings. |
| `--check` | the `arch check` JSON file | Required. It must come from the same mode, base, or proposal as this run, and no source file may have changed since it ran. |
| `--judged` | the judged findings file | The reviewer's findings and questions. Leave it out when no reviewer ran. |
| `--base` | a branch, tag, or commit | Required in `change-review`: the ref the check compared with. |
| `--plan` | the plan file | Required in `plan-review`: plan evidence cites its headings. |
| `--proposal` | the proposal file | Required in `plan-review`: the file the check ran on. |
| `--upcoming` | text | A named upcoming change the owner confirmed; repeat the flag for each. A finding's `liftedBy` must equal one of them or one recorded in the model. |
| `--json` | none | Print the result as JSON. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

`list`:

| Flag | Value | Meaning |
|---|---|---|
| `--rank` | none | After an audit, order the findings by consequence within the components that changed most in the `historyWindow`, and count the rest per rule. |
| `--json` | none | Print the result as JSON. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

The check, judged, and proposal files must be under `.architecture/` or outside the project; a flow
keeps them under `.architecture/work/`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The findings were stored and the result printed, whatever its verdict. |
| 2 | A usage error, a check file that does not match this run or is stale, or judged findings refused; nothing is stored. |

## Output

The judged findings file is one object:

```json
{ "findings": [
    { "judgment": "detail-reached-without-port", "target": "src/domain/payroll-use-case.ts",
      "consequence": "Swapping the clock for tests or another runtime means editing the use case.",
      "correction": "Take the Clock port in the constructor and drop the SystemClock import.",
      "evidence": ["src/domain/payroll-use-case.ts:2"], "origin": "introduced" } ],
  "questions": ["Will payroll run in a second time zone this year?"] }
```

`judgment` is an id from a rule-group file's conditions table, and `rules`, `defect`, and `severity`
come from it, so a finding must not set them. `target` is a unit path, an edge `<from> -> <to>`, a
port `<path>#<Symbol>`, or a component, of a kind that judgment applies to. `evidence` holds
`path:line` entries that exist in the reviewed tree; in plan review, `<plan>#<heading>` entries
naming headings of the plan. `origin` is `introduced` or `inherited`, required in a change or plan
review and absent in an audit. `"wider": true` marks a target outside the reviewed scope and is
refused inside it. `liftedBy` names the confirmed upcoming change that makes the finding a blocker.
`add` refuses the whole file, listing every problem, when any finding breaks these rules or names
a rule whose status is `off`.

The printed result has one line each for the verdict with its blocking counts by severity, the
inherited counts, the incomplete conditions and why, the checks not run, the advisory findings, and
the rules not enforced; then the corrections, grouped by correction and ordered by severity; then
the count of wider observations and each question for the owner. The verdict is `OK`,
`SHOULD_CHANGE` when a blocking finding of an enforced rule is a blocker or major, or `INCOMPLETE`
when none is and an enforced condition could not be decided. With `--rank`, a ranking follows.
Without a model, the result is the verdict `OK` and the line "no architecture model; run a baseline
audit to enable the full review".

With `--json`: `flow`, `scope`, `verdict`, `blocking` and `inherited` (counts by severity),
`advisory`, `wider`, `incompleteCount`, `incompleteReasons`, `notRun`, `notEnforced`,
`corrections`, `questions`, `findings`, and with `--rank` a `ranking`.

## Example

From the payroll fixture after a commit that makes the payroll use case import the system clock
adapter, with the judged file above:

```
$ arch findings add --flow change-review --base main --check .architecture/work/check.json --judged .architecture/work/judged.json
# Architecture change-review: changes since main
Verdict: SHOULD_CHANGE: 3 blocker, 2 major, 0 minor blocking
Inherited: 0 blocker, 1 major, 0 minor (not blocking)
Incomplete: 1 conditions (1 missing facts)
Not run: distance-over-threshold (fewer than 8 components)
Advisory: 0 findings
Rules not enforced: R6 Use cases own their boundaries (off: one delivery mechanism; controllers call use cases directly)
Corrections:
1. R30 No dependency cycles: adapters -> domain: component cycle through ... Fix: Break the cycle adapters -> domain: define the needed interface in the side that needs it and have the other implement it, or extract a cohesive leaf both depend on
5. R23 Defer unforced decisions: src/domain/payroll-use-case.ts: Swapping the clock for tests or another runtime means editing the use case. Fix: Take the Clock port in the constructor and drop the SystemClock import.
Wider observations: 0
Questions for the owner: 1
- Will payroll run in a second time zone this year?
```

Corrections 2 to 4 and the cycle's full path are left out here for length.
