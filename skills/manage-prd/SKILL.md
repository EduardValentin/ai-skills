---
name: manage-prd
description: Use when the user asks to create, write, edit, update, review, or clean up a PRD or product requirements document, especially to keep it business-focused, coherent, concise, non-redundant, and free of technical implementation details.
---

# Manage PRD

## Purpose

Create and maintain PRDs that explain the business context and product behavior clearly. A PRD is not a delivery plan or implementation checklist.

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
- Ask before editing a PRD unless the user explicitly requested direct file mutation. Patch proposals must state that the PRD will not be edited until the wording is approved.

## Output

Use the smallest useful artifact:

- **Patch proposal:** section, replacement text, and why it belongs in the PRD.
- **Review report:** technical leakage, redundancy, contradictions, missing business rules, ambiguity, and suggested edits.
- **New PRD outline:** goal, users, core flows, business rules, permissions, lifecycle, edge cases, non-goals, success outcomes.

Every patch proposal must end by asking the user to approve the wording before the PRD is edited, or by stating that no file edit will happen until the wording is approved.

End by stating whether the PRD section is coherent or what business decision is still blocking it.
