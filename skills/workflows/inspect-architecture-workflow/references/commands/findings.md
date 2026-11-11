# arch findings

What `arch findings add` and `arch findings list` do, their flags, exit codes, and output, and the
shape of a reviewer's judged findings. Read it when either fails or refuses findings. `add` merges a
check's findings with the judged findings of one or more reviewers, applies the escalation the command owns, stores
the open findings in `.architecture/findings.json`, and prints the result with its verdict. `list`
prints that result again.

## Synopsis

```
arch findings add --flow change-review --base <ref> --check .architecture/work/check.json --judged .architecture/work/judged.json
arch findings add --flow plan-review --plan <plan> --proposal .architecture/work/proposal.json --check .architecture/work/check.json
arch findings add --flow audit --check .architecture/work/check.json --judged .architecture/work/judged-tests.json --judged .architecture/work/judged-humble-objects.json
arch findings add --flow change-review --base <ref> --check .architecture/work/check.json --upcoming "<confirmed upcoming change>"
arch findings list
arch findings list --rank
```

## Flags

`add`:

| Flag | Value | Meaning |
|---|---|---|
| `--flow` | `audit`, `change-review`, or `plan-review` | Required: which flow produced the findings. |
| `--check` | the `arch check` JSON file | Required. It must come from the same mode, base, or proposal as this run, and no source file may have changed since it ran. |
| `--judged` | a judged findings file | One reviewer's findings and questions. Repeat the flag once per reviewer; the files are read in the order given and their findings and questions joined. Leave it out when no reviewer ran. |
| `--base` | a branch, tag, or commit | Required in `change-review`: the ref the check compared with. |
| `--plan` | the plan file | Required in `plan-review`: plan evidence cites its headings. |
| `--proposal` | the proposal file | Required in `plan-review`: the file the check ran on. |
| `--upcoming` | text | A named upcoming change the user confirmed; repeat the flag for each. A finding's `liftedBy` must equal one of them or one recorded with `arch model add-upcoming`. |
| `--json` | none | Print the result as JSON. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

`list`:

| Flag | Value | Meaning |
|---|---|---|
| `--rank` | none | After an audit, order the findings by consequence within the components that changed most in the `historyWindow`, and count the rest per rule. |
| `--json` | none | Print the result as JSON. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

The check output, the judged findings, and the proposal are working files. Working files live
under `.architecture/work/`; the command refuses a working file elsewhere inside the project.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The findings were stored and the result printed, whatever its verdict. |
| 2 | A usage error, a check file that is missing, does not match this run, or is stale, or judged findings refused; nothing is stored. A missing check file's message names the `arch check` command, with `--out`, that creates it. |

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

`judgment` is an id from the conditions table of a rule group, and `rules`, `defect`, and
`severity` come from it, so a judged finding must not set them. `target` is a unit path, an edge
`<from> -> <to>`, a port `<path>#<Symbol>`, or a component, of a kind that judgment applies to. In
plan review, a judgment that applies to the plan takes the literal target `plan`, which is always in
scope there and refused in the other flows.
`evidence` holds `path:line` entries that exist in the reviewed tree; in plan review,
`<plan>#<heading>` entries naming headings of the plan. `origin` is `introduced` or `inherited`,
required in a change or plan review and absent in an audit. `"wider": true` marks a target outside
the reviewed scope, where it is required, or a finding whose only correction is larger than the
smallest change inside the scope. It is reported apart and never blocks. `liftedBy` names a confirmed upcoming change that makes the finding a
blocker: one passed with `--upcoming` or recorded with `arch model add-upcoming`.

A judged finding is dropped, not refused, when a recorded exception covers it or every rule it
names is `off` for its target's component. That is how a finding the user accepted leaves the
verdict: `arch model add-exception <target> '*' rule=<R> reason="<text>"` covers a unit, port, or
component target, and an exception with two ends covers an edge. When any judged finding breaks the
rules above, `add` stores nothing and lists every problem, each prefixed with its file and its place
in that file, such as `.architecture/work/judged.json: findings[0] (src/domain/payroll-use-case.ts)`.

The printed result has one line each for the verdict with its blocking counts by severity, the
inherited counts, the incomplete conditions and why, the checks not run, the advisory findings,
`Dropped:` with the count of findings an exception covers or whose rule is off and the reasons,
and the rules not enforced; then the corrections, grouped by correction and ordered by severity;
then the count of wider observations and each question for the user. The verdict is `OK`,
`SHOULD_CHANGE` when a blocking finding of an enforced rule is a blocker or major, or `INCOMPLETE`
when none is and a condition of an enforced rule could not be decided. With `--rank`, a ranking
follows. Without a model, the result is the verdict `OK` and the line "no architecture model; run a
baseline audit to enable the full review".

With `--json`: `flow`, `scope`, `verdict`, `blocking` and `inherited` (counts by severity),
`advisory`, `covered` (check findings an exception covered), `dropped` (each dropped judged finding
with its `target`, `judgment`, and `reason`), `wider`, `incompleteCount`, `incompleteReasons`,
`notRun`, `notEnforced`, `corrections`, `questions`, `findings`, and with `--rank` a `ranking`.

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
Dropped: 0
Rules not enforced: R6 Use cases own their boundaries (off: one delivery mechanism; controllers call use cases directly)
Corrections:
1. R30 No dependency cycles: adapters -> domain: component cycle through ... Fix: Break the cycle adapters -> domain: define the needed interface in the side that needs it and have the other implement it, or extract a cohesive leaf both depend on
5. R23 Defer unforced decisions: src/domain/payroll-use-case.ts: Swapping the clock for tests or another runtime means editing the use case. Fix: Take the Clock port in the constructor and drop the SystemClock import.
Wider observations: 0
Questions for the user: 1
- Will payroll run in a second time zone this year?
```

Corrections 2 to 4 and the cycle's full path are left out here for length.

Accepting a judged finding: on the payroll fixture after a commit that makes the payroll controller
import a new external, a reviewer judged `handler-holds-business-logic` (R20) on
`src/web/payroll-controller.ts`, and the verdict was `SHOULD_CHANGE: 0 blocker, 1 major`. The user
accepted it with an exception, and `check` and `add` ran again with the same judged file:

```
$ arch model add-exception src/web/payroll-controller.ts '*' rule=R20 reason="validation stays here until the second form arrives"
$ arch check --base main --out .architecture/work/check.json
wrote .architecture/work/check.json: 2 findings, 1 incomplete
$ arch findings add --flow change-review --base main --check .architecture/work/check.json --judged .architecture/work/judged.json
# Architecture change-review: changes since main
Verdict: INCOMPLETE: 0 blocker, 0 major, 0 minor blocking
Inherited: 2 blocker, 0 major, 0 minor (not blocking)
Incomplete: 1 conditions (1 missing facts)
Not run: distance-over-threshold (fewer than 8 components)
Advisory: 0 findings
Dropped: 1 (1 covered by an exception)
Rules not enforced: R6 Use cases own their boundaries (off: one delivery mechanism; controllers call use cases directly)
Corrections: none
Wider observations: 0
Questions for the user: 0
```

The verdict is `INCOMPLETE` because the adapter does not provide `typeChecks`, which an enforced
condition of R13 needs.

An audit of the known-defects fixture with one file per reviewer, one holding a finding and the
other only a question, stores both files' content in one result:

```
$ arch findings add --flow audit --check .architecture/work/check.json --judged .architecture/work/judged-deferral-and-boundaries.json --judged .architecture/work/judged-tests.json
# Architecture audit: all components
Verdict: SHOULD_CHANGE: 18 blocker, 10 major, 3 minor blocking
Inherited: 0 blocker, 0 major, 0 minor (not blocking)
Incomplete: 0 conditions
Not run: zone-of-pain (needs --base), no-cohesion-groups (needs --base), change-spans-groups (needs --base)
Advisory: 0 findings
Dropped: 0
Rules not enforced: none
Corrections:
21. R23 Defer unforced decisions: src/lending/loan-use-case.ts: Moving loans to another store means editing the lending rules. Fix: Take the LoanStore port in the constructor instead of the SQL store.
Wider observations: 0
Questions for the user: 1
- Will a second team own the storage component this year?
```

Thirty of the thirty-one corrections are left out here for length.
