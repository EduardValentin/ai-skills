---
name: frontend-interface-design
description: Use when designing, implementing, or reviewing frontend pages, components, layouts, dashboards, forms, or app surfaces that need coherent aesthetics, semantic HTML, accessible interaction, responsive layout code, motion, or production-grade UI/UX.
---

# Frontend Interface Design

## Overview

Design from structure outward: correct semantics and accessible interaction first, then visual hierarchy, composition, motion, and polish. The result should feel intentionally designed for the product, not assembled from generic defaults.

## When To Use

- Designing, implementing, or reviewing frontend pages, components, layouts, forms, dashboards, or app surfaces.
- The work depends on semantic HTML, accessible interaction, responsive layout code, motion, or production-grade visual polish.
- The UI direction is already clear enough to implement or critique.

## Workflow

1. Establish context: audience, task, product tone, density needs, existing design system, and technical constraints.
2. Start with native HTML semantics: landmarks, headings, forms, buttons, links, lists, tables, dialogs, and status messages should use the correct elements before adding styling.
3. Implement accessible behavior in code: labels, names, keyboard paths, focus management, form relationships, and status updates.
4. Compose layout and styling from the existing design system: hierarchy, spacing rhythm, type scale, color roles, and motion purpose.
5. Keep behavioral states explicit in code, such as loading, empty, error, disabled, selected, and expanded rendering paths.

## Quality Bar

- Semantic HTML and keyboard behavior are not polish; they are the foundation.
- Every interactive element has an accessible name, expected keyboard behavior, and correct focus management.
- ARIA only fills semantic gaps that native HTML cannot express.
- Layouts use stable semantic structure and responsive constraints instead of brittle visual-only wrappers.
- Typography matches the container: compact panels use compact headings; hero-scale type is reserved for true hero contexts.
- Color use supports hierarchy, contrast, and state. Avoid one-note palettes and decorative gradients that do not serve the product.
- Motion clarifies cause and effect. Respect reduced-motion preferences and avoid animation that delays core tasks.
- Design choices match the domain: operational apps should be dense, scannable, and restrained; editorial or expressive surfaces can take more visual risk.

## Done Means

- Semantic structure and accessible interactions are implemented.
- Behavioral states have explicit rendering paths.
- Layout, typography, color, and motion use the product's design system intentionally.
