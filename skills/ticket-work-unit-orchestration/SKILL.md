---
name: ticket-work-unit-orchestration
description: Use when coordinating approved ticket implementation, multi-ticket delivery, delegated implementation and verification, per-unit readiness ledger tracking, or large work where each work unit needs independent implementation, self-review, QA, UI/UX, and Ship readiness.
---

# Ticket Work Unit Orchestration

## Overview

Coordinate approved implementation work after intake, requirements/design, and implementation-plan approval are complete. The main agent is the orchestrator: it keeps the user dialogue, branch or ticket state, integration status, and Ship gate coherent while delegating implementation, implementer self-review, QA verification, UI/UX verification, review, testing, and focused fixes through self-contained capability requests.

The hard contract is the **per-work-unit readiness ledger**. The skill enforces independent completion evidence for each work unit, not a rigid root/child/grandchild topology. Do not prescribe a rigid topology. Let the orchestrator choose the delegation strategy that fits the ticket, repository, sequencing, and shared write surfaces.

Use this skill for a single ticket with one work unit and for large workflows spanning multiple tickets/work units.

## Preconditions

- The work has an approved requirements/design direction.
- The work has an approved implementation plan or an approved unit of implementation work.
- The relevant codebase scope, affected surfaces, constraints, and test expectations are known. When they are not known, dispatch a compact codebase mapping request first.

If these preconditions are not met, return to the intake/planning workflow instead of improvising implementation.

## First Actions

1. Identify each work unit from the approved plan. A work unit may be a ticket, feature slice, backend surface, UI surface, migration, background job, or integration slice.
2. Classify each work unit as backend-only/non-UI, UI-facing, or mixed. If uncertain, do not assume backend-only.
3. Build the ledger before delegating implementation. Each work unit starts with empty rows for implementation, implementer self-review, QA, UI/UX or skip rationale, unresolved findings, and integration/out-of-scope status.
4. Delegate implementation through an implementation work-unit request using the smallest sensible unit boundaries. Multiple work units may use multiple implementers where practical, but sequencing, shared ownership, and repository constraints may justify another strategy.
5. Require returned reports to update the ledger. Local checks, green tests, screenshots, or manual notes can be evidence inside a report; they do not replace missing report rows.

## Per-Work-Unit Readiness Ledger

Track every work unit independently with these rows:

| Row | Required evidence |
|---|---|
| Work unit | Name, scope, related ticket if any, and backend-only/UI-facing/mixed classification. |
| Implementation | Completed implementation report from an implementation work-unit request, with changed surfaces, decisions, and any follow-up risk. |
| Self-review | Completed implementer self-review report covering local diff review, edge cases, and obvious regressions. |
| QA | Completed QA verification report from an acceptance-criteria QA behavior verification request, with the scenario, checks performed, result, and findings status. |
| UI/UX | Completed UI/UX verification report from a frontend UI/UX visual review request for UI-facing or mixed units; otherwise an explicit backend-only/non-UI skip rationale. |
| Findings | Unresolved findings status, fix-loop status, and owner if not clean. |
| Integration | Integrated, blocked, or explicitly out-of-scope status. |

Required exact row labels for downstream checks are: `implementation report`, `implementer self-review report`, `QA verification report`, `UI/UX verification report`, `explicit backend-only/non-UI skip rationale`, `unresolved findings status`, and `integration/out-of-scope status`.

## Completion Gate

A work unit is not complete until its ledger has all applicable rows filled:

- implementation report
- implementer self-review report
- QA verification report
- UI/UX verification report, or explicit backend-only/non-UI skip rationale
- unresolved findings status marked clean, fixed, blocked, or explicitly out of scope
- integration/out-of-scope status

Self-review is distinct from QA verification and UI/UX verification. Do not collapse them into a single "looks good" statement. A clean report for one work unit does not make another work unit complete.

UI/UX skip is allowed only when the work unit is explicitly backend-only/non-UI. The skip rationale must say why no user-visible rendered outcome is affected. If the answer is uncertain, run UI/UX verification.

## Delegation Guidance

Choose the delegation strategy that fits the work:

- For independent tickets or slices, delegate each work unit separately where practical.
- For tightly coupled slices, delegate implementation in the sequence that reduces conflicts, then still require per-unit ledger rows.
- For UI-facing or mixed work, include affected surfaces, important states, running URLs when available, and any reference/prototype context in the UI/UX verification request.
- For backend-only work, include APIs, jobs, migrations, persistence behavior, and relevant test/probe expectations in the acceptance-criteria QA behavior verification request.
- For findings, delegate focused fixes with the finding packet and rerun only the affected verification rows unless the fix changes broader behavior.

The orchestrator may combine reports when the same agent legitimately owns multiple units, but the ledger must still show every work unit separately.

## Carry-Forward Report

Before Ship or handoff, summarize the ledger compactly:

```text
WORK UNIT | TYPE | IMPLEMENTATION | SELF-REVIEW | QA | UI/UX | FINDINGS | INTEGRATION
```

Use short statuses such as `complete`, `clean`, `skipped: backend-only`, `blocked`, `fixing`, or `out of scope`. Include links or file/path locators only where useful. Do not mark the overall workflow complete while any row is missing, blocked without user decision, or waiting on verification.
