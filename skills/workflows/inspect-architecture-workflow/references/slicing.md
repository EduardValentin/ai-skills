# Slicing and packets

The coordinator does not map or evaluate alone. It slices the scope, dispatches read-only
subagents with self-contained packets, and merges their returns. Each packet carries the global
material its slice needs; no subagent depends on having read the book, the skill, or another
slice.

## Global material in every packet

Packets name files, never paste them. The coordinator resolves this skill's directory (the
folder holding `SKILL.md`) once and writes absolute paths into every packet; catalog text copied
into a packet is coordinator output spent for nothing.

1. The absolute path of `references/rules/preface.md` (the "Reading this catalog" preface and
   the vocabulary), to read first.
2. Mode, scope, commit, and the coordinator's numbered list of named upcoming changes (`UC-n`,
   each with its source: ticket or plan, the baseline's `decisions.md`, or the caller).
3. The absolute path of the template under `assets/` whose row formats the return must use.
4. The read-only instruction: inspect, never edit; return rows, never write files.

## Mapping slice

Agent: `architecture-code-auditor`. Dispatched only when `arch uncovered` lists modules, one
slice per component the uncovered modules fall in (or one slice when fewer than fifteen). Packet
adds: the uncovered paths; the absolute path of `references/mapping.md`; the current
`model/rules.json` and `model/overrides.json` contents; the component list. Returns: one proposed
`model add-rule`, `model add-override`, or `model add-component` invocation per module or group,
each with a one-sentence behavioral reason, and open questions for modules it could not classify.
The coordinator applies the invocations and reruns `arch uncovered`.

## History slice

`arch query volatility --since <base>`, run by the coordinator; no agent.

## Evaluation slice

Agent: `architecture-evaluator`, or a general-purpose agent with the same packet. Cross-cutting
rules R1 to R3 are not a slice; the coordinator applies them during severity escalation and
ordering.

Evaluators judge rows. The query output in the packet is the evidence; an evaluator opens only
the skill files the packet names, never a project file. A fact the graph lacks comes back as an
open question, which the coordinator settles through the fact slice below, never by letting the
evaluator read code.

Packet adds: the absolute paths of `references/workflows/preamble.md` and, per workflow to run,
its workflow file (inputs, procedure, decision table with base severities) and its rule file,
both named after the workflow (`references/workflows/w1.md` and `references/rules/w1.md` for
W1, and so on); `references/metrics.md` for W6 only; the output of the queries the workflow's
`Reads:` line names, run by the coordinator with `--json` off so the packet carries markdown
tables, each written to `.architecture/slices/packet/<nn>-<query>.md` and named in the packet by
absolute path (no query output longer than a screen is pasted inline); the `arch assess` output,
written to `.architecture/slices/packet/00-assess.md` and named in the packet as "decided rows: do
not re-derive them", so the evaluator judges only the conditions its workflow files leave
unmarked; the baseline's `decisions.md`; in change or plan review, the rows marked `proposed` or
`changed`, with the instruction to evaluate only those targets and the edges touching them.

Fan-out follows the graph size. An audit dispatches one evaluator per workflow, W1 to W8, in
parallel, each over the full graph. Change and plan review dispatch **one** evaluator that
runs every applicable workflow in order over the small changed set; eight sessions over a
handful of rows is this skill's single largest avoidable cost. A workflow is applicable when a
changed or proposed row falls in a section it reads (a diff touching no tests skips W7; one
adding no component edges skips W6, except in the base-without-model fallback of
`change-review.md`, Map step 4, where W6 always runs); skipped workflows carry their previous ledger rows forward
and the run log names them. The review packet carries the changed rows, their direct neighbors
(units one edge away, the second table of `arch query touched --base <base> --with-neighbors`), and a component-level summary of the whole graph (components, component
edges, metrics) instead of every unit row; W6, when applicable, receives the full component
graph, since cycles and stability are properties of the whole.

Returns: assessment rows in the ledger row format: `verdict`, base `severity` from the table,
`evidence` as a target (a unit path, an edge as paths, a port as path:symbol, or a component ID)
and the rule, `change` as a description (the coordinator assigns `CH-` names), `protects` when
the packet's upcoming changes make it determinable, and `checked` counts per rule so `OK`
coverage is visible.

## Fact slice

Agent: `architecture-code-auditor`. Dispatched when an evaluator returns an open question the
graph cannot answer: where a concrete detail is constructed, the types in a port's signature,
the shape of data crossing a boundary, or a power only tests use. One slice per affected
component. Packet adds: the paths in question and the exact question for each, copied from the
evaluator's return. Returns: one row per fact (path, fact, evidence line as `path:line`) and
nothing else. The coordinator appends those rows to the evaluation packet and re-runs only the
workflow rows the questions came from.

## Merge rules

Rules 1 to 3 are what `arch ledger add-run` and `arch ledger map` do (`references/command.md`,
`ledger`); the coordinator writes the merged rows to a row file and runs them instead of editing
the ledger's tables.

1. **Findings.** Run `arch ledger add-run` with the run's rows, the skipped workflows, the
   evaluated targets, and the removed targets. Rows are keyed by target and rule, a duplicate
   keeping the fuller evidence. A matched finding keeps its ID. A previous `SHOULD_CHANGE` row
   whose target this run evaluated and found compliant becomes `RESOLVED` with this run's commit.
   A row found again keeps its ID with this run's evidence. A row whose target no longer exists
   becomes `RESOLVED` with a note that the target was removed. A row this run did not evaluate,
   outside the diff or of a skipped workflow, is carried forward unchanged: not being evaluated
   never counts as being fixed. A previous `ACCEPTED` row stays `ACCEPTED` while its target and
   rule match again, and becomes `RESOLVED` once the target satisfies the rule.
2. **Changes.** Run `arch ledger map` after the last acceptance of the run. Open `SHOULD_CHANGE`
   rows whose `change` descriptions name the same move (same port, same split, same extraction)
   form one `CH-<letter>`, described once; the coordinator words such rows' descriptions
   identically, since the command clusters identical text.
3. **Decided rows.** Concatenate the `arch assess` rows and the evaluator rows into the row file
   as rows of the same run. An assessed row whose edge, component pair, or ring pair a recorded
   intended exception in `decisions.md` covers is written `OK` naming the exception.
4. **Severity.** Apply the escalation rules in `references/verdicts.md` to the merged rows before
   `arch ledger add-run`, so escalation sees fan-in and upcoming changes across the whole graph;
   mark each lift `[rule <n>]` in the row's Evidence, since the run verdict and the escalation
   counts read those marks.

## Dispatch guidance

Run `arch graph` (or `arch diff <base>` in review modes) and `arch uncovered` first; dispatch
mapping slices only for uncovered modules, in parallel, and apply their proposals before
evaluation; run `arch query volatility` and the other queries each applicable workflow reads;
then dispatch the evaluation slice or slices in parallel, and a fact slice for any open question
they return. Merge returns in memory and write
them to `slices/` once; do not re-read what was just written. Give slices enough time for real
inspection. A slice that returns prose instead of rows is re-dispatched once with the row format
restated; a second failure is recorded as an open question with the slice's paths.
