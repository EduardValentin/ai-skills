---
name: frontend-interface-design
description: "Use when working on applications with a graphical user interface. Examples: React web and native apps, HTML based websites, SwiftUI mobile apps."
metadata:
  status: experimental
  allows_tool_references: "false"
---

# Frontend Interface Design

## When To Use

- Creating or modifying visual interfaces in a frontend, mobile, desktop, canvas, game, or other GUI technology.
- The work depends on accessible interaction, adaptive layout, stateful UI behavior, and motion.

## Workflow

1. Establish context: audience, task, product tone, density needs, existing design system, target platform, and technical constraints.
2. Implement accessible behavior in code: labels, names, input paths, focus or selection management, control relationships, and status updates.
3. Compose layout and styling from the existing design system: hierarchy, spacing rhythm, type scale, color roles, and motion purpose.
4. Keep every state relevant to the requested surface explicit in code. Examples include loading, empty, error, disabled, selected, expanded, success, and destructive-action progress or failure.

## HTML Interfaces

When the target is HTML or web UI:

- Use native landmarks, headings, forms, buttons, links, lists, tables, dialogs, and status elements before adding custom wrappers.
- Every interactive element needs an accessible name, expected keyboard behavior, and correct focus management.
- ARIA only fills semantic gaps that native HTML cannot express.

## Quality Bar

- Platform semantics and accessible interaction are not polish; they are the foundation.
- Every interactive element has a clear name, expected input behavior, and correct focus, selection, or activation management for the target platform.
- Layouts use stable semantic structure and adaptive constraints instead of brittle visual-only wrappers.
- Relevant loading, empty, error, progress, success, disabled, selection, and destructive-action paths remain understandable and operable.
- Typography matches the container: compact panels use compact headings; hero-scale type is reserved for true hero contexts.
- Color use supports hierarchy, contrast, and state.
- Motion clarifies cause and effect. Respect reduced-motion preferences and avoid animation that delays core tasks.
