---
name: reusable-ui-components
description: Use when creating, refactoring, or reviewing frontend UI patterns that repeat or may repeat, when deciding between extending an existing component and creating a new one, or when component APIs, variants, slots, composition, duplication, page-specific logic, or design-system consistency are at stake.
---

# Reusable UI Components

## Overview

Prefer reusable components when they preserve meaning and reduce real duplication. A good component models a stable role in the product, exposes a small intentional API, and keeps page-specific behavior at the page boundary.

## When To Use

- Creating, refactoring, or reviewing UI patterns that repeat or are likely to repeat.
- Deciding whether to reuse a component, extend variants, add slots/composition, or create a new component.
- Component APIs, duplication, variants, page-specific logic, or design-system boundaries are part of the work.

## Workflow

1. Inventory nearby components before creating new UI. Look for matching role, structure, states, variants, and usage frequency.
2. Reuse directly when the existing component already fits the semantic role.
3. Extend with variants when the role is the same but presentation, density, tone, or state differs.
4. Create a separate component when the role, interaction model, or invariant is different enough that a variant would make the original API vague.
5. Extract repeated markup when it appears twice, is likely to appear again, or carries interaction/accessibility complexity worth centralizing.
6. Keep page-specific data fetching, routing, analytics, and business logic outside reusable UI components.

## API Rules

- Name components after their role: `MetricTile`, `FilterPanel`, `EmptyState`, `PricingTier`, not `BlueCard` or `SectionBlock`.
- Use explicit props for meaningful behavior and content. Avoid boolean piles that create unclear combinations.
- Prefer variant axes for design-system choices: `size`, `tone`, `density`, `emphasis`, `state`.
- Prefer composition or slots when callers need to provide rich content.
- Keep class overrides rare. If callers repeatedly need the same override, promote it to a variant.
- Preserve accessibility responsibilities inside the component when the component owns interaction.
- Component internals own their spacing, typography, icon sizing, radius, state styling, and interaction details.
- Page layouts may arrange components and pass content, but should not reach into component internals.

## When To Ask The User

Ask before implementation when the component decision changes product meaning or creates a design-system fork:

- Extending the existing component would alter its default behavior or visual contract.
- A new variant would introduce a naming/API choice with multiple reasonable meanings.
- The new pattern may become a reusable design-system primitive.

For ordinary reuse decisions, make the conservative choice and document it briefly.

## Done Means

- Repeated UI is consolidated or intentionally left local with a clear reason.
- Reusable components have clean names, prop APIs, variants, and state coverage.
- No page-specific logic leaks into design-system components.
- The implementation reduces future maintenance instead of hiding one-off complexity behind a generic name.
