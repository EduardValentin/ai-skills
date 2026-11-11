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

This skill is being reworked. The rule catalog, the classification guide, the metrics page, and
the adapter contract are in place; the audit, change-review, and plan-review procedures are not
yet written. Until they are, use the references below directly and run the command with
`node scripts/arch.mjs <subcommand>` from the inspected project's root, resolving `scripts/arch.mjs`
against this skill's folder.

## References

- `references/rules/vocabulary.md`: every term the catalog uses, defined once.
- `references/rules/cross-cutting.md`: R1 to R3, and how any rule is applied, graded, and corrected.
- `references/rules/dependency-direction.md`: R4 to R9.
- `references/rules/reasons-to-change.md`: R10 to R16.
- `references/rules/business-rule-placement.md`: R17 to R19.
- `references/rules/humble-objects.md`: R20 to R22.
- `references/rules/deferral-and-boundaries.md`: R23 to R26.
- `references/rules/components-and-stability.md`: R27 to R33.
- `references/rules/tests.md`: R34 to R37.
- `references/rules/enforcement-and-organization.md`: R38 to R41.
- `references/classification.md`: how to classify modules into components, kinds, and rings.
- `references/metrics.md`: the component metrics and every threshold knob.
- `references/adapter-contract.md`: what the project's adapter receives and prints.
