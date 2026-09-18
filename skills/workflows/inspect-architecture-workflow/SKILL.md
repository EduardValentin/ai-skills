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
architecture assessment. The coordinator running this skill slices the work,
dispatches read-only subagents, merges their rows, and owns two artifact sets:
the committed architecture record, which is the project's architecture
documentation, and the uncommitted refactoring ledger, which is the agents'
working memory. It never edits production code.

## Choose the mode, then follow its file

| Mode | Use when | Procedure |
|---|---|---|
| Audit | Mapping a repository or a named area for the first time, or refreshing the baseline | `references/audit.md` |
| Change review | Reviewing a diff against the committed baseline | `references/change-review.md` |
| Plan review | Reviewing a written implementation plan before it is approved | `references/plan-review.md` |

Change review and plan review require a committed baseline for their scope.
When none exists, run the audit procedure on the affected scope first, then
continue; report that the record must be committed with the PR. Never review a
diff or plan against a graph that exists only in memory.

Every mode ends with the verdict rules and return contract in
`references/verdicts.md`.

## Artifacts

**Committed record** at `docs/architecture/` in the inspected project, unless
the project's agent instructions name another path. It replaces any free-form
architecture document and is the baseline later runs compare against. Audits
write it in full; change reviews update the rows a diff changed, but never a
row that an open finding disputes. Plan reviews never write it.

| File | Holds |
|---|---|
| `README.md` | Three paragraphs on the shape (policy, how details plug in, how boundaries are enforced), how to read the folder, last audit commit and scope |
| `components.md` | Components: path, published surface, enforcement mode, ring, actors, release unit |
| `units.md` | Units: component, kind, ring, visibility, actors |
| `dependencies.md` | Edges, forbidden edges, ports, entry points, composition roots, shared data shapes |
| `metrics.md` | Per component: fan-in, fan-out, instability, abstractness, distance, volatility, previous distance |
| `decisions.md` | Deferred decisions and their ports, cohesion position and cost per component, intended exceptions, accepted findings |

**Uncommitted ledger** at `.architecture/` in the inspected project. Confirm
it is ignored before writing; if not, add it to the repository's local exclude
file, never to a tracked ignore file.

| File | Holds |
|---|---|
| `ledger.md` | Run log, change definitions, findings rows, improvement map, pending record updates |
| `change-history.md` | Per touched unit, the reason and actor of each recent change |
| `slices/` | Raw subagent returns of the latest run |

Every artifact opens with a header: date, commit, scope, mode. The ledger is derived
state: when none exists, start one; only the committed record is a required
baseline. Ledger IDs and run numbers are transitory and never appear in a
committed file; the record refers to a finding only by the target's path and
symbol and the rule.

## Shared references

- `references/rules.md`: rules R1 to R41 with a preface defining every term.
- `references/workflows.md`: evaluation workflows W1 to W8 with decision
  tables and base severities.
- `references/mapping.md`: how mapping slices fill inventory rows.
- `references/slicing.md`: subagent packets, returns, and merge rules.
- `references/metrics.md`: instability, abstractness, distance.
- `references/verdicts.md`: row verdicts, severity escalation, return contract.
- Templates: `assets/docs/README.md`, `assets/docs/components.md`,
  `assets/docs/units.md`, `assets/docs/dependencies.md`,
  `assets/docs/metrics.md`, `assets/docs/decisions.md`,
  `assets/ledger/ledger.md`, `assets/ledger/change-history.md`.

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
