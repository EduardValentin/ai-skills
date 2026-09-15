# Slicing and packets

The coordinator does not map or evaluate alone. It slices the scope, dispatches read-only
subagents with self-contained packets, and merges what they return. Every packet carries the
global material a slice needs so no subagent depends on having read the book, the skill, or
another slice.

## Global material in every packet

1. The "Reading this catalog" preface and the vocabulary table from `rules.md`.
2. Mode, scope, commit, and the coordinator's numbered list of named upcoming changes (`UC-n`,
   each with its source: ticket or plan, the baseline's `decisions.md`, or the caller).
3. The exact row formats from the relevant template under `assets/`.
4. The read-only instruction: inspect, never edit; return rows, never write files.

## Mapping slice

Agent: `architecture-code-auditor` (or a general-purpose agent with the same packet). One slice
per component; when no enforced components exist, one per top-level source folder; when a folder
exceeds roughly forty source files, split it by subfolder and say so in the packet.

Packet adds: the slice's paths; the list of all other slices' paths so cross-slice edges can be
named by path; the full text of `mapping.md`; the existing rows of the committed record for this
slice when a baseline exists, so IDs and prior classifications can be reused.

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

Agent: a general-purpose subagent. Exactly one per run, dispatched in parallel with the mapping
slices, covering the whole scope. It walks the version-control log once instead of once per
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

Agent: `architecture-evaluator` (or a general-purpose agent with the same packet). One slice
per workflow, W1 to W8, over the whole merged inventory. Cross-cutting rules R1 to R3 are not a
slice; the coordinator applies them during severity escalation and ordering.

Packet adds: the workflow's section from `workflows.md` (inputs, procedure, decision table with
base severities); the rule section for that workflow from `rules.md`; `metrics.md` for W6 only;
the merged inventory sections the workflow reads; `decisions.md` from the baseline; in change or
plan review, the changed or proposed rows marked `proposed` or `changed`, and the instruction to
evaluate only those targets and the edges touching them.

Audit sends every workflow the full inventory. Change and plan review are incremental: a workflow
is dispatched only when a changed or proposed row falls in a section it reads (a diff touching no
tests skips W7; one adding no component edges skips W6); skipped workflows carry their previous
ledger rows forward and the run log names them. Dispatched workflows receive the changed rows,
their direct neighbors (units one edge away), and a component-level summary of the whole graph
(components, component edges, metrics) instead of every unit row. W6 always receives the full
component graph, since cycles and stability are properties of the whole.

Returns: assessment rows in the ledger row format with `verdict`, base `severity` from the
table, `evidence` as paths and inventory IDs, `change` as a description (the coordinator assigns
`CH-` names), and `protects` when the packet's upcoming changes make it determinable. Also
returns `checked` counts per rule so `OK` coverage is visible.

## Merge rules

1. **Units and edges.** Key units by path and symbol; key edges by from, to, and kind. Reuse the
   baseline ID when the key matches; assign the next free ID otherwise; mark baseline rows with
   no match as `removed` (audit) or leave them and record the removal in `deltas.md` (change and
   plan review).
2. **Cross-slice edges.** An edge returned with a path target is resolved to the unit ID from the
   slice that owns that path; an unresolved target becomes an open question, never a silent drop.
3. **Components and metrics.** The coordinator decides component boundaries from the slices'
   published-surface and enforcement observations, then computes metrics from the merged edges.
4. **Findings.** Key by target and rule. Drop duplicates, keeping the row with the fuller
   evidence. Match to the previous ledger by key to keep IDs; a previous `SHOULD_CHANGE` with no
   current match on a target still present becomes `RESOLVED`.
5. **Changes.** Cluster `SHOULD_CHANGE` rows whose `change` descriptions name the same move
   (same port, same split, same extraction) into one `CH-<letter>`; write the description once.
6. **Severity.** Apply the escalation rules from the skill body after merging, so escalation sees
   fan-in and upcoming changes across the whole graph.

## Dispatch guidance

Dispatch all mapping slices and the history slice in parallel, then all evaluation slices in
parallel; evaluation waits for the merged inventory. Give slices enough time for real inspection. A slice that returns
prose instead of rows is re-dispatched once with the row format restated; a second failure is
recorded as an open question with the slice's paths.
