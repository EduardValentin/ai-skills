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

Evaluators judge rows. The merged inventory in the packet is the evidence; an evaluator opens
only the skill files the packet names, never a project file. A fact the inventory lacks comes
back as an open question, which the coordinator settles from the mapping slice's return or a
targeted re-map of that path, never by letting the evaluator read code.

Packet adds: the absolute paths of `references/workflows/preamble.md` and, per workflow to run,
its workflow file (inputs, procedure, decision table with base severities) and its rule file,
both named after the workflow (`references/workflows/w1.md` and `references/rules/w1.md` for
W1, and so on); `references/metrics.md` for W6 only; the output of the queries the workflow's
`Reads:` line names, run by the coordinator with `--json` off so the packet carries markdown
tables; the baseline's `decisions.md`; in change or plan review, the rows marked `proposed` or
`changed`, with the instruction to evaluate only those targets and the edges touching them.

Fan-out follows the inventory size. An audit dispatches one evaluator per workflow, W1 to W8, in
parallel, each over the full inventory. Change and plan review dispatch **one** evaluator that
runs every applicable workflow in order over the small changed set; eight sessions over a
handful of rows is this skill's single largest avoidable cost. A workflow is applicable when a
changed or proposed row falls in a section it reads (a diff touching no tests skips W7; one
adding no component edges skips W6); skipped workflows carry their previous ledger rows forward
and the run log names them. The review packet carries the changed rows, their direct neighbors
(units one edge away), and a component-level summary of the whole graph (components, component
edges, metrics) instead of every unit row; W6, when applicable, receives the full component
graph, since cycles and stability are properties of the whole.

Returns: assessment rows in the ledger row format: `verdict`, base `severity` from the table,
`evidence` as a target (a unit path, an edge as paths, a port as path:symbol, or a component ID)
and the rule, `change` as a description (the coordinator assigns `CH-` names), `protects` when
the packet's upcoming changes make it determinable, and `checked` counts per rule so `OK`
coverage is visible.

## Merge rules

1. **Findings.** Key by target and rule. Drop duplicates, keeping the row with the fuller
   evidence. Match to the previous ledger by key to keep IDs. For each previous `SHOULD_CHANGE`
   row: if this run evaluated the same target under the same rule and found it compliant, set
   `RESOLVED` with this run's commit; if it found the violation again, keep the row and its ID,
   updating run and evidence; if the target no longer exists in the code, set `RESOLVED` with a
   note that the target was removed; if this run did not evaluate that target (outside the diff,
   or its workflow was skipped), carry the row forward unchanged. Not being evaluated never
   counts as being fixed. A previous `ACCEPTED` row whose target and rule match again stays
   `ACCEPTED`; one whose target now satisfies the rule becomes `RESOLVED`.
2. **Changes.** Cluster `SHOULD_CHANGE` rows whose `change` descriptions name the same move
   (same port, same split, same extraction) into one `CH-<letter>`; write the description once.
3. **Severity.** Apply the escalation rules from the skill body after merging, so escalation sees
   fan-in and upcoming changes across the whole graph.

## Dispatch guidance

Run `arch graph` (or `arch diff <base>` in review modes) and `arch uncovered` first; dispatch
mapping slices only for uncovered modules, in parallel, and apply their proposals before
evaluation; run `arch query volatility` and the other queries each applicable workflow reads;
then dispatch the evaluation slice or slices in parallel. Merge returns in memory and write
them to `slices/` once; do not re-read what was just written. Give slices enough time for real
inspection. A slice that returns prose instead of rows is re-dispatched once with the row format
restated; a second failure is recorded as an open question with the slice's paths.
