---
name: inspect-architecture-workflow
description: >-
  Use for a dedicated architecture audit, an architecture review of a diff, or an architecture
  review of an implementation plan or spec before approval, passing the flow name `audit`,
  `change-review`, or `plan-review`.
compatibility: >-
  Dispatches the architecture-reviewer and architecture-classifier agents as subagents; in a
  harness without them, dispatch a generic read-only subagent given that agent's prompt instead.
  Runs the bundled command with Node and git. The inspected project must provide an adapter
  command that prints its dependency facts, as the adapter contract reference describes.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Inspect Architecture Workflow

This skill tells a team whether a change, a plan, or a codebase makes the next reasonable change
harder, and names the smallest correction. A bundled command decides every condition it can from
the project's dependency facts, and a reviewer agent judges only the rest by reading the code or
the plan. Each project records which rules apply to it in one model file.

| Flow | Use it for | Follow |
|---|---|---|
| `audit` | A deliberate baseline of a whole codebase; builds the model | [audit](references/flows/audit.md) |
| `change-review` | A diff against a base commit; the routine path | [change review](references/flows/change-review.md) |
| `plan-review` | A plan or spec before approval, before any code exists | [plan review](references/flows/plan-review.md) |

Open only the flow you were given; it carries every command it runs. Each subcommand has its own
page, such as [the check page](references/commands/check.md), read only when a command fails or a
model edit is needed. The record path is `docs/architecture/` unless `--record` or
`ARCH_RECORD_DIR` names another.

| Artifact | Holds | Notes |
|---|---|---|
| `architecture.json` | The whole model: components and their classification, ports, rule statuses with reasons, thresholds, forbidden edges, exceptions | In the record path. Edited only through `arch model` |
| `current.md` | Counts, metrics, the component graph, threshold breaches | In the record path. Rewritten whole by `arch collect` |
| `decisions.md` | Longer explanations for people | Optional. Nothing reads it |
| `.architecture/graph/` | The graph cache | Never committed, disposable |
| `.architecture/findings.json` | Open findings | Never committed. A resolved or accepted finding is removed |
| `.architecture/work/` | A flow's working files | Never committed |

- Never propose a service split, a tier, or another deployment-topology change unless the scope asks for one.
- Never propose more than the smallest correction that removes the named consequence, or a refactor only to match a pattern.
- Never report a check that lacks a fact, or a missing classification, as passing.
- Never let a finding's severity depend on whether a check or a reviewer produced it.
- Never let the artifacts grow with the number of runs, tickets, or findings resolved.
