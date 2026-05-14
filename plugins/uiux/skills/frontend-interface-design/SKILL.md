---
name: frontend-interface-design
description: Use when designing, implementing, or reviewing frontend pages, components, layouts, dashboards, forms, states, or app surfaces that need coherent aesthetics, semantic HTML, accessibility, responsive behavior, motion, visual polish, or production-grade UI/UX.
---

# Frontend Interface Design

## Overview

Design from structure outward: correct semantics and accessible interaction first, then visual hierarchy, composition, motion, and polish. The result should feel intentionally designed for the product, not assembled from generic defaults.

## Workflow

1. Establish context: audience, task, product tone, density needs, existing design system, and technical constraints.
2. Start with native HTML semantics: landmarks, headings, forms, buttons, links, lists, tables, dialogs, and status messages should use the correct elements before adding styling.
3. Define the visual direction in concrete terms: information hierarchy, spacing rhythm, type scale, color roles, states, and motion purpose.
4. Implement the smallest coherent surface, then refine the details: alignment, empty/loading/error states, focus states, hover/pressed states, disabled states, and responsive behavior.
5. Validate with the running UI whenever possible. If visual validation is unavailable, ask for screenshots before claiming the design is complete.

## Quality Bar

- Semantic HTML and keyboard behavior are not polish; they are the foundation.
- Every interactive element has an accessible name, visible focus state, and expected keyboard behavior.
- ARIA only fills semantic gaps that native HTML cannot express.
- Layouts use stable dimensions and responsive constraints so content, labels, and controls do not overlap or shift unexpectedly.
- Typography matches the container: compact panels use compact headings; hero-scale type is reserved for true hero contexts.
- Color use supports hierarchy, contrast, and state. Avoid one-note palettes and decorative gradients that do not serve the product.
- Motion clarifies cause and effect. Respect reduced-motion preferences and avoid animation that delays core tasks.
- Design choices match the domain: operational apps should be dense, scannable, and restrained; editorial or expressive surfaces can take more visual risk.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Styling divs before choosing the right elements | Build the native document structure first, then style it. |
| Treating accessibility as a final audit | Include accessible names, focus, keyboard paths, and contrast in the first implementation. |
| Copying generic card-heavy layouts | Choose density, hierarchy, and rhythm based on the user's actual workflow. |
| Adding decorative effects to compensate for weak structure | Fix hierarchy and spacing before adding atmosphere. |
| Designing only the happy path | Include loading, empty, error, disabled, and long-content states. |

## Done Means

- The UI is usable by keyboard and understandable to screen readers.
- The visual hierarchy is clear at mobile, tablet, desktop, narrow, and wide widths.
- Text does not clip, overlap, or outgrow controls.
- States and motion are purposeful.
- The design feels coherent with the surrounding product.
