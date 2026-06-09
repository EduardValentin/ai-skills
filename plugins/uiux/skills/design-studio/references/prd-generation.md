# PRD Generation

Use only when `PRD.md` is missing and the user agrees to generate one.

## Analyze The App

Produce a product-level inventory of the React reference app:

- routes/pages and hierarchy
- visible user actions and system responses
- forms, inputs, validation, and submission outcomes
- navigation flows and conditional paths
- user roles or role-specific UI
- mock entities, fields, and relationships
- modals, drawers, filters, scheduling, messaging, alerts, empty/error/loading states
- implied business rules, constraints, and permissions

Describe product behavior only. Do not include component names, file paths, or implementation details.

## Capture Evidence

Capture primary-route screenshots with the available visual-output path. Use observations from screenshots to clarify page purpose, visible flows, and ambiguous controls.

## Write PRD.md

Create `PRD.md` with sections that fit the product, usually:

- Product Summary
- Product Goals
- Non-Goals
- Core User Types
- Feature Areas
- Business Rules
- Data Entities
- Edge Cases And States

Document only behavior evidenced by the app analysis or screenshots. Mark unclear behavior as `[TBD]` instead of inventing it.
