# arch findings

What `arch findings add` and `arch findings list` do, their flags, exit codes, and output, and the
shape of a reviewer's judged findings. Read it when either fails or refuses findings. `add` merges a
check's findings with the judged findings of one or more reviewers, applies the escalation the command owns, stores
the open findings in `.architecture/findings.json`, and prints the result with its verdict. `list`
prints that result again.

## Synopsis

```
arch findings add --flow change-review --base <ref> --check .architecture/work/check.json --applicable .architecture/work/applicable.json --judged .architecture/work/judged.json
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
| `--applicable` | the `arch applicable` JSON file | Made with `--out` for the same scope: `--all` in an audit, `--base` in a change review, `--proposal` in a plan review. Its counts give the line `Judgment conditions: <n> in scope, <m> not reviewed`. |
| `--upcoming` | text | A named upcoming change the user confirmed; repeat the flag for each. A finding's `liftedBy` must equal one of them or one recorded with `arch model add-upcoming`. |
| `--json` | none | Print the result as JSON. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

`list`:

| Flag | Value | Meaning |
|---|---|---|
| `--rank` | none | After an audit, order the findings by consequence within the components that changed most in the `historyWindow`, and count the rest per rule. |
| `--json` | none | Print the result as JSON. |
| `--record` | a directory | Read the model from this record path instead of `docs/architecture/`. `ARCH_RECORD_DIR` does the same. |

The check output, the applicable output, the judged findings, and the proposal are working files. Working files live
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
      "evidence": ["src/domain/payroll-use-case.ts:1"], "origin": "introduced" } ],
  "questions": ["Will payroll run in a second time zone this year?"],
  "disputes": [ { "path": "src/domain/payroll-use-case.ts",
                  "reason": "It formats the payslip text, which is presenter work, not a use case's." } ] }
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
blocker: one passed with `--upcoming` or recorded with `arch model add-upcoming`. `disputes` lists
the units whose code contradicts their classification, each with the reviewer's reason; every
`path` must be a unit of the graph, or `add` refuses the file.

A judged finding is dropped, not refused, when recorded exceptions cover every rule it names or
every rule it names is `off` for its target's component. An exception with `rule=` removes only
that rule, so a finding of a judgment with several rules stays with the rules left. That is how a finding the user accepted leaves the
verdict: `arch model add-exception <target> '*' rule=<R> reason="<text>"` covers a unit, port, or
component target, and an exception with two ends covers an edge. When any judged finding breaks the
rules above, `add` stores nothing and lists every problem, each prefixed with its file and its place
in that file, such as `.architecture/work/judged.json: findings[0] (src/domain/payroll-use-case.ts)`.

The printed result has one line each for the verdict with its blocking counts by severity, the
inherited counts, and the count of incomplete conditions by kind, followed by one line per incomplete
condition, `- <check> (<rule numbers and titles>): <target>: <reason and what to do>`, where a
condition missing a fact for every target names `all targets` and a clarification request is
`- clarification: <task>: <reason>`; then one line each for the checks not run,
`Judgment conditions: <n> in scope, <m> not reviewed`, the advisory findings,
`Dropped:` with the count of findings an exception covers or whose rule is off and the reasons,
and the rules not enforced. The judgment line counts the conditions `arch applicable` put in scope,
and those no reviewer judged: the ones a contained change left out, or all of them when no
`--judged` file was given. Without `--applicable` it reads `Judgment conditions: not reported`.
Then come the corrections, grouped by correction and ordered by severity.
A finding keeps every distinct correction of the check rows and judged findings merged into it, a
check row's first, printed as `Fix: <a> | <b>`.
Then come three sections, each left out when it is empty: `Inherited findings:` and `Wider
observations:`, one line per finding in the form `<rule numbers and titles>: <target>:
<consequence> Fix: <correction>`, and `Overlapping findings:`, one group per unit that judged
findings from two or more `--judged` files name as their target or as an edge end with different
corrections, each followed by the file it came from. The command reads the judged findings before
merging them, so two reviewers giving the same judgment on the same target with different
corrections are listed too. These are parallel reviewers proposing two fixes for one unit, to be
reconciled into one. A check finding never overlaps, since its correction is fixed, and a single
judged file never overlaps with itself. Then come the questions for the user, and last
`Classification disputes: <n>`, one line per dispute: `- <path>: <reason>`. The verdict is `OK`,
`SHOULD_CHANGE` when a blocking finding of an enforced rule is a blocker or major, or `INCOMPLETE`
when none is and a condition of an enforced rule could not be decided. With `--rank`, a ranking
follows; wider observations stay in their own section and are not ranked. Without a model, the result is the verdict `OK` and the line "no architecture model; run a
baseline audit to enable the full review".

With `--json`: `flow`, `scope`, `verdict`, `blocking` and `inherited` (counts by severity),
`advisory`, `covered` (check findings an exception covered), `incomplete` (each incomplete entry
with its `check`, `rules`, `target`, `reason`, and `enforced`), `judgmentConditions` (`inScope` and
`notReviewed`, or `null` without `--applicable`), `dropped` (each dropped judged finding
with its `target`, `judgment`, and `reason`), `wider`, `incompleteCount`, `incompleteReasons`,
`notRun`, `notEnforced`, `corrections` (each group's `severity`, `rules`, `targets`,
`consequence`, `corrections`, and `findings` count), `questions`, `disputes` (each `path` and
`reason`), `overlaps` (each overlapping `unit` with its `findings`, each with `target`, `defect`,
`rules`, `corrections`, and `files`, the judged files it came from), `findings` (each with its
`corrections`), and with `--rank` a `ranking`.

## Example

From the payroll fixture after a commit that makes the payroll use case import the system clock
adapter, with the judged file above:

```
$ arch applicable --base main --out .architecture/work/applicable.json
wrote .architecture/work/applicable.json: review yes, 38 judgment conditions in scope, 0 not reviewed
$ arch findings add --flow change-review --base main --check .architecture/work/check.json --applicable .architecture/work/applicable.json --judged .architecture/work/judged.json
# Architecture change-review: changes since main
Verdict: SHOULD_CHANGE: 3 blocker, 2 major, 0 minor blocking
Inherited: 0 blocker, 0 major, 0 minor (not blocking)
Incomplete: 1 conditions (1 missing facts)
- type-check-on-implementation (R13 Substitutable implementations, narrow interfaces): all targets: the adapter document does not provide typeChecks, so type-check-on-implementation could not be decided. Make the adapter provide it, or set R13 to advisory or off with arch model set-rule.
Not run: distance-over-threshold (fewer than 8 components)
Judgment conditions: 38 in scope, 0 not reviewed
Advisory: 0 findings
Dropped: 0
Rules not enforced: R6 Use cases own their boundaries (off: one delivery mechanism; controllers call use cases directly)
Corrections:
1. R30 No dependency cycles: adapters -> domain: A change to any component in adapters -> domain can force a change to all of them, so none can be released or tested alone. Fix: Break the cycle adapters -> domain by removing one of its edges: move what that edge uses into the depending side, or merge the members if they always change together; only if the dependency must stay, have the side that needs it declare an interface the other side implements
3. R4 Dependencies point toward policy; R5 The consumer owns the port: src/domain/payroll-use-case.ts -> src/adapters/system-clock.ts: A change to src/adapters/system-clock.ts can force a change to the business rule in src/domain/payroll-use-case.ts, which cannot be tested without it. Fix: Depend on the existing port `Clock` in `src/domain/clock.ts` instead of src/adapters/system-clock.ts, and have the composition root pass src/adapters/system-clock.ts to src/domain/payroll-use-case.ts
5. R23 Defer unforced decisions: src/domain/payroll-use-case.ts: Swapping the clock for tests or another runtime means editing the use case. Fix: Take the Clock port in the constructor and drop the SystemClock import.
Questions for the user: 1
- Will payroll run in a second time zone this year?
Classification disputes: 1
- src/domain/payroll-use-case.ts: It formats the payslip text, which is presenter work, not a use case's.
```

Corrections 2 and 4 are left out here for length. Correction 5 repeats what correction 3, from the
check, already says; a reviewer should not have raised it.

Accepting a judged finding: on the payroll fixture after a commit that makes the payroll controller
import a new external, a reviewer judged `handler-holds-business-logic` (R20) on
`src/web/payroll-controller.ts`, and the verdict was `SHOULD_CHANGE: 0 blocker, 1 major`. The user
accepted it with an exception, and `check` and `add` ran again with the same judged file:

```
$ arch model add-exception src/web/payroll-controller.ts '*' rule=R20 reason="validation stays here until the second form arrives"
$ arch check --base main --out .architecture/work/check.json
wrote .architecture/work/check.json: 2 findings, 1 incomplete
$ arch findings add --flow change-review --base main --check .architecture/work/check.json --applicable .architecture/work/applicable.json --judged .architecture/work/judged.json
# Architecture change-review: changes since main
Verdict: INCOMPLETE: 0 blocker, 0 major, 0 minor blocking
Inherited: 2 blocker, 0 major, 0 minor (not blocking)
Incomplete: 1 conditions (1 missing facts)
- type-check-on-implementation (R13 Substitutable implementations, narrow interfaces): all targets: the adapter document does not provide typeChecks, so type-check-on-implementation could not be decided. Make the adapter provide it, or set R13 to advisory or off with arch model set-rule.
Not run: distance-over-threshold (fewer than 8 components)
Judgment conditions: 18 in scope, 0 not reviewed
Advisory: 0 findings
Dropped: 1 (1 covered by an exception)
Rules not enforced: R6 Use cases own their boundaries (off: one delivery mechanism; controllers call use cases directly)
Corrections: none
Inherited findings:
- R7 Lower-level components are plugins: src/web/payroll-controller.ts -> src/adapters/pg-payroll-repository.ts: Replacing or reconfiguring src/adapters/pg-payroll-repository.ts means editing src/web/payroll-controller.ts, which cannot be tested with a stand-in. Fix: Move the construction of src/adapters/pg-payroll-repository.ts from src/web/payroll-controller.ts into the composition root and pass it to src/web/payroll-controller.ts as the existing port `PayrollRepository` in `src/domain/payroll-repository.ts`
- R7 Lower-level components are plugins: src/web/payroll-controller.ts -> src/adapters/system-clock.ts: Replacing or reconfiguring src/adapters/system-clock.ts means editing src/web/payroll-controller.ts, which cannot be tested with a stand-in. Fix: Move the construction of src/adapters/system-clock.ts from src/web/payroll-controller.ts into the composition root and pass it to src/web/payroll-controller.ts as the existing port `Clock` in `src/domain/clock.ts`
Questions for the user: 0
Classification disputes: 0
```

The verdict is `INCOMPLETE` because the adapter does not provide `typeChecks`, which an enforced
condition of R13 needs.

An audit of the known-defects fixture with one file per reviewer, where two reviewers judged the
same use case and proposed two fixes:

```
$ arch findings add --flow audit --check .architecture/work/check.json --applicable .architecture/work/applicable.json --judged .architecture/work/judged-dependency-direction.json --judged .architecture/work/judged-deferral-and-boundaries.json
# Architecture audit: all components
Verdict: SHOULD_CHANGE: 20 blocker, 10 major, 3 minor blocking
Inherited: 0 blocker, 0 major, 0 minor (not blocking)
Incomplete: 0 conditions
Not run: zone-of-pain (needs --base), no-cohesion-groups (needs --base), change-spans-groups (needs --base)
Judgment conditions: 60 in scope, 0 not reviewed
Advisory: 0 findings
Dropped: 0
Rules not enforced: none
Corrections:
7. R6 Use cases own their boundaries: src/lending/loan-use-case.ts: Moving loans to another store means editing the lending rules. Fix: Depend on the existing LoanStore port instead of the SQL store.
21. R26 Demonstrate the model without I/O: src/lending/loan-use-case.ts: The lending rules cannot run in a test without a database pool. Fix: Have the composition root create the pool and pass the store in.
Overlapping findings:
- src/lending/loan-use-case.ts:
  - R6 Use cases own their boundaries: src/lending/loan-use-case.ts: Fix: Depend on the existing LoanStore port instead of the SQL store. (from .architecture/work/judged-dependency-direction.json)
  - R26 Demonstrate the model without I/O: src/lending/loan-use-case.ts: Fix: Have the composition root create the pool and pass the store in. (from .architecture/work/judged-deferral-and-boundaries.json)
Questions for the user: 0
Classification disputes: 0
```

Twenty-nine of the thirty-one corrections are left out here for length. The two findings on the use
case are one fix: the audit flow sends them, with both judged files, to one reviewer for a single
reconciled file.
