---
name: inspect-architecture-workflow
description: >-
  For the architecture-coordinator agent, or another architect agent, in a
  dedicated architecture audit, a change review of a diff, or a review of an
  implementation plan before its approval. Not for implementers or planners.
compatibility: >-
  Requires dispatching read-only agents as subagents, and write access to the committed
  architecture folder and an ignored ledger folder. Change and plan review need
  a committed baseline; when none exists the coordinator produces one first.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Inspect Architecture Workflow

## Purpose

Turn a codebase, a diff, or an implementation plan into an evidenced
architecture assessment. The coordinator slices the work, dispatches read-only
subagents, merges their rows, and owns two artifact sets: the committed
architecture record, the project's architecture documentation, and the
uncommitted refactoring ledger, the agents' working memory. It never edits
production code.

## Choose the mode, then follow its file

| Mode | Use when | Procedure |
|---|---|---|
| Audit | Mapping a repository or a named area for the first time, or refreshing the baseline | `references/audit.md` |
| Change review | Reviewing a diff against the committed baseline | `references/change-review.md` |
| Plan review | Reviewing a written implementation plan before it is approved | `references/plan-review.md` |

Change review and plan review need a committed baseline for their scope. When
none exists, run the audit procedure on the affected scope first, then
continue, and report that the record must be committed with the PR. Never
review a diff or plan against a graph that exists only in memory.

Every mode ends with the verdict rules and return contract in
`references/verdicts.md`.

## Artifacts

**Committed record** at `docs/architecture/` in the inspected project, unless
the project's agent instructions name another path. It holds judged facts
only; everything derivable from the code is derived by the skill's command
and never committed.

| File | Holds |
|---|---|
| `model/components.json` | Tooling settings; components as path globs with enforcement mode, release unit, and entry-point globs |
| `model/rules.json` | Ring order, framework names, and classification rules: glob to ring, kind, actors; first match wins |
| `model/overrides.json` | Per-path exceptions to the rules |
| `model/boundaries.json` | Declared ports (path, symbol, owner, humble side) and shared data shapes |
| `decisions.md` | Only decisions the workflows consume, at component or boundary level: deferred decisions and their ports, cohesion groups, cohesion position and cost per component, intended exceptions. Never a row per finding or per ticket |
| `README.md` | Three paragraphs on the shape, how to read the folder, and a generated summary block the command fills |

Agents change the model only through `model add-override`, `model add-port`,
`model add-component`, `model add-rule`, and their removals, which write the
files canonically; never by editing JSON text.

**Derived graph** at `.architecture/graph/<commit>.json`, written by
`node <skill>/scripts/arch.mjs graph` from the project root: units with
component, ring, kind, actors, and export counts; edges with direction and
crossings; externals; component metrics; component edges; cycles; uncovered
modules. Deterministic from a commit, regenerated when missing, never
committed. The command needs the project's language tooling installed
(TypeScript and JavaScript: dependency-cruiser and typescript); a language
with no adapter stops the run with an escalation naming it.

**Uncommitted ledger** at `.architecture/` in the inspected project. Confirm
it is ignored before writing; if not, add it to the repository's local exclude
file, never to a tracked ignore file.

| File | Holds |
|---|---|
| `ledger.md` | Run log, change definitions, findings rows, acceptances, improvement map, pending record updates |
| `change-history.md` | Per touched unit, the reason and actor of each recent change |
| `slices/` | Raw subagent returns of the latest run |

Every artifact opens with one header line. In the record it names the last
full audit (date, commit, scope) and the last update (date, commit, mode); a
write replaces that line in place, never adds one. The record carries no
history of its own, since git and the ledger's run log do; nothing is ever
appended to a record file outside its tables, and no model entry names a
ticket, a PR, a plan step, a run, or a finding. A moved or renamed unit keeps
its ID and gets its new path; a unit or edge that no longer exists loses its
row; its ID is retired, never reused. The ledger is derived state: start one
when none exists; only the committed record is a required baseline. Ledger
IDs and run numbers are transitory and never appear in a committed file; the
record names a finding only by its target (a unit path, an edge as paths, a
port as path:symbol, or a component ID) and the rule number.

## Shared references

- `references/rules/preface.md`: the catalog preface and vocabulary, read
  before any rule file. `references/rules/cross-cutting.md` holds R1 to R3;
  `references/rules/w1.md` through `references/rules/w8.md` hold each
  evaluation workflow's rules.
- `references/workflows/preamble.md`: shared row columns and severity scale;
  `references/workflows/w1.md` through `references/workflows/w8.md` hold each
  workflow's inputs, procedure, and decision table.
- `references/mapping.md`: how mapping slices fill inventory rows.
- `references/slicing.md`: subagent packets, returns, and merge rules.
- `references/metrics.md`: instability, abstractness, distance.
- `references/verdicts.md`: row verdicts, severity escalation, return contract.
- Templates: `assets/docs/README.md`, `assets/docs/decisions.md`,
  `assets/docs/model/components.json`, `assets/docs/model/rules.json`,
  `assets/docs/model/overrides.json`, `assets/docs/model/boundaries.json`,
  `assets/ledger/ledger.md`, `assets/ledger/change-history.md`.

## Cost

A run's cost is agent sessions, not skill text.

- Callers run the structural precheck before dispatching a review: a plan or
  diff whose files `arch query touched` places in one component, adding no
  package, port, cross-component import, or external dependency, is not
  reviewed.
- Mapping is a command, not an agent: `arch graph`, `arch diff`, and
  `arch uncovered`. A mapping agent is dispatched only for uncovered modules.
- Packets name skill files by absolute path and carry query output, never
  pasted inventory.
- Audit fans out one evaluator per workflow; change and plan review dispatch
  one evaluator for every applicable workflow.
- Evaluators judge query output and open no project file.
- The history slice is `arch query volatility`, not an agent.
- The return contract reports agents dispatched and tokens when the harness
  shows them.

## Discipline

- No verdict without a query result and a rule number; evidence is a target
  and the rule.
- Subagents never write artifacts; the coordinator merges and writes.
- Structural findings are added to functional findings a caller also asked
  for, never substituted for them.
- Do not invent boundaries the code does not have; when it draws none, the
  record says so and W5 and W8 report it.
- Do not propose restructuring beyond the scope unless the scope's own edges
  create the problem; report wider observations in the return contract's
  out-of-scope line. Only an audit writes open questions to `decisions.md`.
