---
name: manage-prd
description: Use when creating, reviewing, rewriting, or maintaining a product requirements document (PRD), especially when product rules are unclear, contradictory, redundant, or mixed with implementation details.
metadata:
  status: experimental
  allows_tool_references: "false"
---

# Manage PRD

## Purpose

Create and maintain PRDs that state business context and user-observable product behavior clearly. A PRD is not a delivery plan or implementation checklist.

## When To Use

- creating a new PRD from product notes or conversation
- editing or rewriting existing PRD sections
- reviewing a PRD for clarity, coherence, contradictions, gaps, or redundancy
- turning user clarifications into PRD wording
- removing technical leakage from PRD content

## Writing Rules

- Keep the PRD focused on business context: problem, goals, users, product behavior, business rules, permissions, lifecycle, constraints, validation, edge cases, non-goals, and success outcomes.
- Keep wording concise and non-redundant. Consolidate repeated rules instead of copying them across sections.
- Preserve one coherent vocabulary for the same product concept.
- Surface contradictions, missing product decisions, and ambiguous rules before rewriting around them.
- Do not include implementation steps, code architecture, component names, file paths, database tables or columns, API endpoints, mock data mechanics, CSS, layout, delivery metadata, or test checklists.

## Edit Authorization

- Treat an explicit instruction to edit, update, replace, or apply wording to a specific PRD target now as authorization to mutate it. That request is the approval; do not require a second wording-approval round.
- Treat requests to review, propose, suggest, draft, or return replacement wording as proposal-only. A prohibition such as "do not edit" always keeps the work proposal-only.
- If a direct edit depends on a contradictory or missing product decision, ask for that decision before changing the affected wording.
- A proposal-only response must not claim that a file changed. State that the wording is pending approval and ask for approval before editing.

## Mixed Deliverables

A coherent PRD comes before downstream implementation tickets. For a mixed PRD-and-ticket request, review the PRD first. If product rules conflict or required decisions are missing, name those blockers and explicitly defer ticket drafting. Once the PRD is coherent and approved, keep any ticketing work separate from the PRD rather than adding delivery detail to it.

## Output

Use the smallest useful artifact:

- **Patch proposal:** section, replacement text, and why it belongs in the PRD.
- **Review report:** technical leakage, redundancy, contradictions, missing business rules, ambiguity, and suggested edits.
- **New PRD outline:** goal, users, core flows, business rules, permissions, lifecycle, edge cases, non-goals, success outcomes.
- **Direct edit:** make only the authorized PRD change and summarize the affected scope.

End every response with one brief readiness statement. For a section or patch, state whether that scope is coherent or name the blocking business decision. For a complete PRD, state whether the document is coherent and ready or name its remaining blockers. Patch proposals must also request wording approval before any edit.
