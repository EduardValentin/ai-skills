# Slicing and packets

The coordinator does not map or evaluate alone. It slices the scope, dispatches read-only
subagents with self-contained packets, and merges what they return. Every packet carries the
global material a slice needs so no subagent depends on having read the book, the skill, or
another slice.

## Global material in every packet

Packets name files, they never paste them. The coordinator resolves the absolute path of this
skill's directory (the folder holding its `SKILL.md`) once and writes paths into every packet;
catalog text copied into a packet is coordinator output spent for nothing.

1. The absolute path of `references/rules/preface.md` (the "Reading this catalog" preface and
   the vocabulary), to read first.
2. Mode, scope, commit, and the coordinator's numbered list of named upcoming changes (`UC-n`,
   each with its source: ticket or plan, the baseline's `decisions.md`, or the caller).
3. The absolute path of the template under `assets/` whose row formats the return must use.
4. The read-only instruction: inspect, never edit; return rows, never write files.

## Mapping slice

Agent: `architecture-code-auditor` (or a general-purpose agent with the same packet). One slice
per component; when no enforced components exist, one per top-level source folder; when a folder
exceeds roughly forty source files, split it by subfolder and say so in the packet.

Packet adds: the slice's paths; the list of all other slices' paths so cross-slice edges can be
named by path; the absolute path of `references/mapping.md`; the paths of the committed record
files holding this slice's existing rows when a baseline exists, so IDs and prior
classifications can be reused.

Returns, as markdown tables in the template row formats:

- Units in the slice (path and symbol, kind, ring, visibility, actors, status).
- Edges leaving the slice's units, targets named by path and symbol even when outside the
  slice; `external:` targets tagged framework, vendor, runtime, or standard library.
- Boundaries whose port is declared in the slice.
- Entry points and construction sites in the slice.
- Component candidates: the published surface and enforcement mode observed for the slice.
- Open questions: anything the slice could not classify.

Mapping slices do not read version control; that is the history slice's job.

## History slice

Agent: a general-purpose subagent on the smallest model the harness offers (in Claude Code,
`haiku`); the work is reading a log. Exactly one per run, dispatched in parallel with the
mapping slices, covering the whole scope. It walks the version-control log once instead of once per
mapping slice.

Packet adds: the scope paths; the window (default the last ten commits touching the scope, or the
commits the ticket or branch names); the ticket or brief, so commit messages can be tied to
actors; the change-history row format.

Procedure: list the commits in the window with the files each touched; for every touched file
inside the scope, write one row per commit with the reason in one phrase taken from the commit
message and diff, the actor it serves (finance, HR, platform, a vendor, unknown), and whether the
reason is a policy or a detail reason. When the scope has no history of its own, return an empty
table and say so; the coordinator records that W1, W2, and W6 ran without volatility evidence.

Returns: change-history rows keyed by file path (the coordinator maps paths to unit IDs), plus an
Open questions list for commits whose reason or actor could not be determined.

Per mode: an audit walks the full window for every file in scope. A change review limits the
slice to the files the diff touches, over the same window, and tells it which commits the ledger
already holds rows for so it returns only the missing ones; the coordinator appends those to the
existing rows. A plan review dispatches no history slice and reuses the ledger's rows unchanged,
since the plan has not changed the code.

## Evaluation slice

Agent: `architecture-evaluator` (or a general-purpose agent with the same packet). Cross-cutting
rules R1 to R3 are not a slice; the coordinator applies them during severity escalation and
ordering.

Evaluators judge rows. The merged inventory in the packet is the evidence; an evaluator opens
only the skill files the packet names and never a project file. A fact the inventory lacks comes
back as an open question, which the coordinator settles from the mapping slice's return or with
a targeted re-map of that path, never by letting the evaluator read code.

Packet adds: the absolute paths of `references/workflows/preamble.md` and, per workflow to run,
its workflow file (inputs, procedure, decision table with base severities) and its rule file,
both named after the workflow (`references/workflows/w1.md` and `references/rules/w1.md` for
W1, and so on); `references/metrics.md` for W6 only; the merged inventory sections
the workflows read; `decisions.md` from the baseline; in change or plan review, the changed or
proposed rows marked `proposed` or `changed`, and the instruction to evaluate only those targets
and the edges touching them.

Fan-out follows the inventory size. An audit dispatches one evaluator per workflow, W1 to W8, in
parallel, each over the full inventory. Change and plan review dispatch **one** evaluator that
runs every applicable workflow in order over the small changed set; eight sessions over a
handful of rows is the single largest avoidable cost of this skill. A workflow is applicable
when a changed or proposed row falls in a section it reads (a diff touching no tests skips W7;
one adding no component edges skips W6); skipped workflows carry their previous ledger rows
forward and the run log names them. The review packet carries the changed rows, their direct
neighbors (units one edge away), and a component-level summary of the whole graph (components,
component edges, metrics) instead of every unit row; W6, when applicable, receives the full
component graph, since cycles and stability are properties of the whole.

Returns: assessment rows in the ledger row format with `verdict`, base `severity` from the
table, `evidence` as paths and inventory IDs, `change` as a description (the coordinator assigns
`CH-` names), and `protects` when the packet's upcoming changes make it determinable. Also
returns `checked` counts per rule so `OK` coverage is visible.

## Merge rules

1. **Units and edges.** Key units by path and symbol; key edges by from, to, and kind. Reuse the
   baseline ID when the key matches; assign the next free ID otherwise; mark baseline rows with
   no match as `removed` (audit) or hold the removal as a candidate record update (change
   review) or leave the baseline untouched (plan review).
2. **Cross-slice edges.** An edge returned with a path target is resolved to the unit ID from the
   slice that owns that path; an unresolved target becomes an open question, never a silent drop.
3. **Components and metrics.** The coordinator decides component boundaries from the slices'
   published-surface and enforcement observations, then computes metrics from the merged edges.
4. **Findings.** Key by target and rule. Drop duplicates, keeping the row with the fuller
   evidence. Match to the previous ledger by key to keep IDs. For each previous `SHOULD_CHANGE`
   row: if this run evaluated the same target under the same rule and found it compliant, set
   `RESOLVED` with this run's commit; if it found the violation again, keep the row and its ID,
   updating run and evidence; if the target no longer exists in the code, set `RESOLVED` with a
   note that the target was removed; if this run did not evaluate that target (outside the diff,
   or its workflow was skipped), carry the row forward unchanged. Not being evaluated never
   counts as being fixed. A previous `ACCEPTED` row whose target and rule match again stays
   `ACCEPTED`; one whose target now satisfies the rule becomes `RESOLVED`.
5. **Changes.** Cluster `SHOULD_CHANGE` rows whose `change` descriptions name the same move
   (same port, same split, same extraction) into one `CH-<letter>`; write the description once.
6. **Severity.** Apply the escalation rules from the skill body after merging, so escalation sees
   fan-in and upcoming changes across the whole graph.

## Dispatch guidance

Dispatch all mapping slices and the history slice in parallel, then the evaluation slice or
slices in parallel; evaluation waits for the merged inventory. Merge returns in memory and write
them to `slices/` once; do not re-read what was just written. Give slices enough time for real inspection. A slice that returns
prose instead of rows is re-dispatched once with the row format restated; a second failure is
recorded as an open question with the slice's paths.
