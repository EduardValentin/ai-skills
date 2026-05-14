# Prototype Boundaries

## Core Rule

When a React prototype exists, it is the source of truth for visible UI copy, labels, placeholders, helper text, empty-state wording, layout, spacing, styling, and screen-level interaction details.

Tickets should describe user-observable behavior and reference the relevant prototype route, screen state, or flow. They should not duplicate prototype-owned details.

## Source Ownership

| Source | Owns |
| --- | --- |
| PRD | Business rules, roles, permissions, domain concepts, lifecycle states, constraints |
| Prototype | UI copy, visual structure, layout, interaction patterns, screen states |
| Ticket | User goal, scope, acceptance criteria, data/rules, dependencies, edge cases |

If sources disagree, ask which source wins for that decision.

## Exact Copy Policy

Do not include exact copy from the prototype just to make the ticket feel complete.

Exact wording belongs in a ticket only when:

- It is legal, compliance, billing, medical, policy, or other regulated text.
- It is a domain contract, such as canonical status names or role names.
- The wording is not present in the prototype and must be decided for delivery.
- The user explicitly asks to preserve exact wording in the final backlog artifact.

## Preferred References

Use references like:

- `Prototype: /coach/plans -> Create Plan flow -> empty exercise list state`
- `Prototype: client portal dashboard -> unread messages state`
- `Prototype: onboarding route -> account type selection`

Avoid references like:

- `Button text must say "Start your plan"`
- `Use a modal with a blue primary button`
- `The placeholder should say "Search exercises"`

## Acceptance Criteria Examples

Bad:

```markdown
- [ ] The CTA says "Start your plan".
- [ ] The card uses the same blue gradient as the prototype.
```

Good:

```markdown
- [ ] The user can start a plan from the plan detail screen, and the visible UI matches the approved prototype for that state.
- [ ] First-time users see the empty plan state shown in the prototype.
```

## Ticket Draft Self-Check

Before showing a draft, remove any line that:

- Repeats visible copy already present in the prototype.
- Specifies styling or layout without a business reason.
- Names React components, CSS classes, internal files, or implementation primitives.
- Turns a prototype detail into a separate business rule without user confirmation.
