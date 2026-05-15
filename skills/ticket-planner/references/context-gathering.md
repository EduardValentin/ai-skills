# Context Gathering

## PRD

Look for `PRD.md` at the project root. Treat it as the source of truth for:

- Business logic
- Roles and permissions
- Domain concepts
- Data lifecycle rules
- Constraints and validation
- Business-impacting edge cases

If there is no PRD, note the gap. Do not assume the prototype or implementation files fully describe the product rules.

## Project Instructions

Read project-level instruction files such as `README.md`, `AGENTS.md`, and nearby contributor docs when present. Use them to learn:

- Product/repo conventions that affect story boundaries
- Expected implementation surfaces or integration points
- Whether the project documents an issue tracker or publishing workflow

If the issue tracker is not clear from the user request or project docs, ask the user before preparing any tracker-specific handoff.

## React Prototype

Look for a React reference app under `designs/`.

Discovery order:

1. Check for a `designs/` child with a `package.json` that lists React.
2. If unclear, search under `designs/` for `.jsx` and `.tsx` files.
3. Use the nearest parent package as the prototype root.
4. If no prototype is found, ask the user for its path.

Treat the prototype as the source of truth for:

- Routes and screen hierarchy
- UI flow and navigation
- Visible copy
- Layout and styling
- Screen states
- Interaction details

If there is no prototype, note the gap. Do not ask for a prototype path unless the user implied one exists.

## Prototype Analysis

Inventory product behavior, not implementation details:

- Routes, pages, and user flows
- Forms, inputs, validation, and submission behavior
- Roles and role-specific surfaces
- Mock data entities, fields, and relationships
- Navigation, modals, drawers, filters, scheduling, messaging
- Shared state in product terms
- Notifications, alerts, loading, empty, success, and error states

Avoid component names, file paths, CSS classes, framework internals, and implementation architecture in the final tickets.

## Context Sufficiency Gate

After reading available sources, decide whether there is enough shared product context to draft clean vertical-slice stories.

Context is insufficient when:

- There is no PRD, feature brief, accepted plan, or prototype.
- The user asks for tickets for a feature that is not described in available docs.
- User roles, goals, business rules, data, or integration points are unclear.
- The available context only describes implementation layers, not user outcomes.
- The agent would need to invent acceptance criteria or edge cases.

When context is insufficient, run [requirements-interview.md](requirements-interview.md). Do not draft stories until the user approves the shared-understanding brief.

## Conflict Handling

If PRD and prototype disagree:

- PRD usually wins for business rules.
- Prototype usually wins for UI, copy, layout, and interaction details.
- Ask the user when the conflict changes behavior, permission, lifecycle, or scope.
