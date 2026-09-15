---
name: inspect-architecture-workflow
description: >-
  For the architecture-coordinator agent, or another architect agent, in a
  dedicated architecture audit, a change review of a diff, or a review of an
  implementation plan before its approval. Produces a committed architecture
  record and an uncommitted refactoring ledger by fanning out mapping and
  evaluation slices to subagents. Not for implementers, planners, or general
  chat sessions: those apply the software-architecture-principles skill.
compatibility: >-
  Requires dispatching read-only subagents (`architecture-code-auditor` and
  `architecture-evaluator`, or general-purpose agents given the slice packets),
  read access to the source tree, and write access to the committed
  architecture folder and an ignored ledger folder. Change and plan review need
  a committed baseline; when none exists the coordinator produces one first.
  `software-architecture-principles` is not required here.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Inspect Architecture Workflow

## Purpose

Turn a codebase, a diff, or an implementation plan into an evidenced
architecture assessment. The coordinator running this skill slices the work,
dispatches read-only subagents, merges their rows, and owns two sets of
artifacts: the committed architecture record, which is the project's
architecture documentation, and the uncommitted refactoring ledger, which is
the agents' working memory. It never edits production code.

Bundled material, paths relative to the skill root:

- `references/rules.md`: rule catalog R1 to R41, with a preface that defines
  behavior, structure, importance, urgency, the dependency graph, rings, and
  policy versus detail. Every finding cites one rule.
- `references/metrics.md`: instability, abstractness, distance: definitions,
  formulas, counting rules, thresholds, and how to read them.
- `references/mapping.md`: how a mapping slice fills inventory rows.
- `references/workflows.md`: evaluation workflows W1 to W8 with decision
  tables; every row carries a base severity.
- `references/slicing.md`: the packet each subagent receives and the rows it
  returns; the merge rules.
- `references/plan-review.md`: how a written plan is turned into proposed
  inventory rows and evaluated.
- Templates for the committed record: `assets/docs/README.md`,
  `assets/docs/components.md`, `assets/docs/units.md`,
  `assets/docs/dependencies.md`, `assets/docs/metrics.md`,
  `assets/docs/decisions.md`. Templates for the ledger:
  `assets/ledger/ledger.md`, `assets/ledger/change-history.md`,
  `assets/ledger/deltas.md`.

## Artifacts

**Committed record**, at `docs/architecture/` in the inspected project unless
the project's agent instructions name another path. It replaces any
free-form architecture document and is the baseline every later run compares
against.

| File | Holds |
|---|---|
| `README.md` | Three paragraphs on the shape (what the policy is, how details plug in, how boundaries are enforced), how to read the folder, and the commit and scope of the last audit |
| `components.md` | Components with path, published surface, enforcement mode, ring, actors, release unit |
| `units.md` | Units with component, kind, ring, visibility, actors |
| `dependencies.md` | Edges, forbidden edges, boundaries (ports), entry points, composition roots, shared data shapes |
| `metrics.md` | Per-component fan-in, fan-out, instability, abstractness, distance, volatility, previous distance |
| `decisions.md` | Deferred decisions and the port each waits behind, accepted cohesion position and cost per component, intended layer skips, accepted findings with who accepted them and when |

**Uncommitted ledger**, at `.architecture/` in the inspected project. Confirm
it is ignored before writing; if not, add it to the repository's local exclude
file, never to a tracked ignore file.

| File | Holds |
|---|---|
| `ledger.md` | Findings rows, change definitions, improvement map, run log |
| `change-history.md` | Per touched unit, the reason and actor of each recent change, derived from version control each run |
| `deltas.md` | Change-review and plan-review only: the rows of the committed record the change adds, removes, or alters, for the implementer to apply in the same PR |
| `slices/` | The raw returns of the latest run's subagents, overwritten each run |

Every artifact opens with a header: date, commit, scope, mode.

## Modes and baseline

| Mode | Scope | Baseline requirement | Writes |
|---|---|---|---|
| Audit | Whole repository or a named area | None; this run creates or refreshes the baseline | Committed record, ledger |
| Change review | A diff | Committed record must exist for the scope | Ledger, deltas |
| Plan review | A written implementation plan | Committed record must exist for the scope | Ledger, deltas |

When change review or plan review finds no committed record, run an audit of
the affected scope first, write the record, and report that the record must be
committed with the PR. Never review a diff or plan against a graph that exists
only in memory.

## Procedure

**Preflight.** Read the project's agent instructions for artifact paths and
named boundaries. Determine mode and scope. Check the baseline. Confirm the
ledger root is ignored. Load the existing ledger so finding IDs can be matched.
Build the list of named upcoming changes, numbered `UC-1`, `UC-2`, and so on,
each with its source: the ticket, brief, or plan handed to you; the deferred
decisions and open questions in the baseline's `decisions.md`; and any roadmap
or backlog items the caller supplied. This list goes into every packet, fills
the `protects` column, and drives escalation rule 2. When no source names an
upcoming change, the list is empty and rule 2 never fires.

**Map, one slice per component.** Slice the scope by component, or by
top-level source folder when the code declares no enforced components. A scope
of fifteen source files or fewer is one mapping slice.
Dispatch one `architecture-code-auditor` per slice with the mapping packet from
`references/slicing.md`. Each returns inventory rows for its slice: units,
edges leaving its units, boundaries it owns, and entry points. Alongside them,
dispatch one history slice for the whole scope, a general-purpose subagent
with the history packet, which walks version control once and returns change
history rows: per touched unit, the reason and actor of each recent change.
Change review limits it to the files the diff touches and to commits the
ledger lacks; plan review skips it and reuses the ledger's rows.
Merge: resolve edges whose target lies in another slice, assign IDs matching
the existing record where the same path and symbol exist, attach history rows
to units by path, and compute component-level data and metrics yourself
following `references/metrics.md`.
In plan-review mode also convert the plan into proposed rows following
`references/plan-review.md`. Write the merged inventory to the committed record
(audit) or to `deltas.md` (change and plan review).

**Evaluate, one slice per workflow.** Dispatch one `architecture-evaluator`
per workflow W1 to W8 with the evaluation packet: the catalog preface and
vocabulary, that workflow's rule section and decision table, the merged
inventory sections it reads, `decisions.md`, the named upcoming changes, and
in plan or change review the proposed or changed rows marked as such. In
those two modes, dispatch a workflow only when at least one changed or
proposed row falls in the sections it reads; carry the other workflows'
previous rows forward unchanged and say so in the run log. Their packets carry
the changed rows, their direct neighbors, and a component-level summary of the
graph rather than every unit row; W6 always receives the full component graph
because cycles and stability are whole-graph properties. Each
returns assessment rows with a base severity from its table. Merge: drop
duplicate target-and-rule pairs, match rows to existing ledger IDs by target
and rule, apply the escalation rules below, name each distinct change once as
`CH-<letter>`, and build the improvement map.

**Record.** Write `ledger.md`, `change-history.md`, and `deltas.md`. In audit
mode write every committed file from the templates and refresh `README.md`.
Never write to the committed record in change or plan review; the implementer
applies `deltas.md`.

**Return.** Reply to the caller with the return contract below. There is no
separate report file; the ledger is for agents and the committed record is for
people.

## Verdicts and severity

Per row: `OK`, `SHOULD_CHANGE`, `RESOLVED` (a later run found the target
compliant; keep the row, add the commit), or `ACCEPTED` (the user explicitly
accepted the finding; record who and when in `decisions.md`).

Base severity comes from the decision-table row that matched. Escalation, in
order, applied by the coordinator:

1. The target is a policy unit (entity, use case, port, boundary data) or the
   edge starts in one: at least `major`.
2. A named upcoming change would cost less if this violation were already
   fixed: with the violation in place, that change must edit a unit it would
   otherwise leave alone, thread a flag through layers, or copy code.
   `blocker`. Ask "would fixing this first make the upcoming change smaller?";
   a yes escalates. Touching the same file as the upcoming change does not
   count on its own: if the change does the same work whether or not the
   violation is fixed, the row keeps its severity.
3. The target is depended on by three or more other units (its fan-in, the
   count of units that import, implement, construct, or use its types), so a
   defect in it reaches all of them: at least `major`. Likewise when the
   target is a boundary the design reasons on but nothing enforces (no
   visibility rule, export list, build unit, or build-failing import rule
   stops a crossing): at least `major`, even if it has not been crossed yet.
4. A cycle: `blocker` regardless of table.

No rule lowers a severity. Keep the base severity beside the escalated one in
the ledger, and state in the return contract how many rows each escalation
rule lifted, so a distribution dominated by one rule is visible. Run verdict: `OK` when no open `SHOULD_CHANGE` row
is `blocker` or `major`; otherwise `SHOULD_CHANGE`. In plan review a
`SHOULD_CHANGE` verdict blocks plan approval until each blocker and major row
is resolved in the plan or `ACCEPTED` by the user.

## Return contract

```markdown
# Architecture <audit | change review | plan review> — <scope>
Verdict: <OK | SHOULD_CHANGE> — <n> blocker, <n> major, <n> minor open; <n> targets OK; <n> changes named
Escalation: <n> rows lifted by rule 1, <n> by rule 2, <n> by rule 3, <n> by rule 4
Baseline: <docs/architecture at commit, or "created this run, commit with the PR">
Direction:
1. <CH-x> — <rule> — <change> — protects <upcoming change>
2. ...
3. ...
Deltas for the implementer: <deltas.md path, or none>
Ledger: <path> | Slices: <n> mapping, 1 history, <n> evaluation
Out of scope: <one line of non-structural observations for other reviewers, or None>
```

## Discipline

- No verdict without an inventory row and a rule number behind it; evidence is
  a path and an inventory ID.
- Subagents never write artifacts; the coordinator merges and writes.
- Structural findings are added to functional findings a caller also asked
  for, never substituted for them.
- Do not invent boundaries the code does not have; when it draws none, the
  record says so and W5 and W8 report it.
- Do not propose restructuring beyond the scope unless the scope's own edges
  create the problem; record wider observations in `decisions.md` under open
  questions.
