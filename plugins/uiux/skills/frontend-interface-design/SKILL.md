---
name: frontend-interface-design
description: Use when execution work creates or modifies visual interfaces in frontend or GUI applications, including pages, components, layouts, dashboards, forms, app surfaces, accessible interaction, adaptive layout, motion, stateful behavior, or production-grade UI/UX.
---

# Frontend Interface Design

## Overview

Build visual interfaces from structure outward: platform-native semantics and accessible interaction first, then visual hierarchy, composition, motion, and polish. The result should feel intentionally designed for the product, not assembled from generic defaults.

## When To Use

- Creating or modifying visual interfaces in a frontend, mobile, desktop, canvas, game, or other GUI technology.
- The work depends on accessible interaction, adaptive layout, stateful UI behavior, motion, or production-grade visual polish.
- The UI direction is already clear enough to implement.

This is an execution skill, not a standalone review skill. Use it for review only when the review directly guides code changes being made in the same task.

## Workflow

1. Establish context: audience, task, product tone, density needs, existing design system, target platform, and technical constraints.
2. Start with the target platform's native UI primitives and semantic structure before styling.
3. Implement accessible behavior in code: labels, names, input paths, focus or selection management, control relationships, and status updates.
4. Compose layout and styling from the existing design system: hierarchy, spacing rhythm, type scale, color roles, and motion purpose.
5. Keep behavioral states explicit in code, such as loading, empty, error, disabled, selected, and expanded rendering paths.

## HTML Interfaces

When the target is HTML or web UI:

- Use native landmarks, headings, forms, buttons, links, lists, tables, dialogs, and status elements before adding custom wrappers.
- Every interactive element needs an accessible name, expected keyboard behavior, and correct focus management.
- ARIA only fills semantic gaps that native HTML cannot express.

## Quality Bar

- Platform semantics and accessible interaction are not polish; they are the foundation.
- Every interactive element has a clear name, expected input behavior, and correct focus, selection, or activation management for the target platform.
- Layouts use stable semantic structure and adaptive constraints instead of brittle visual-only wrappers.
- Typography matches the container: compact panels use compact headings; hero-scale type is reserved for true hero contexts.
- Color use supports hierarchy, contrast, and state. Avoid one-note palettes and decorative gradients that do not serve the product.
- Motion clarifies cause and effect. Respect reduced-motion preferences and avoid animation that delays core tasks.
- Design choices match the domain: operational apps should be dense, scannable, and restrained; editorial or expressive surfaces can take more visual risk.

## Done Means

- Platform-appropriate structure and accessible interactions are implemented.
- Behavioral states have explicit rendering paths.
- Layout, typography, color, and motion use the product's design system intentionally.
