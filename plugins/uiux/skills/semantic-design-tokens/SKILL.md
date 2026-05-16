---
name: semantic-design-tokens
description: Use when styling, auditing, or extending frontend UI that needs semantic design tokens for reusable color, spacing, typography, radii, shadows, motion, component variants, or clear boundaries between semantic roles and component-local implementation values.
---

# Semantic Design Tokens

## Overview

Use tokens as the design-system contract. Global semantic tokens should express reusable roles across the application, not component-specific implementation details.

## Token-First Workflow

1. Inventory existing tokens before styling: theme files, global CSS, component variants, and DESIGN.md or equivalent docs.
2. Use existing semantic tokens when they express the role: `surface`, `border-subtle`, `text-muted`, `space-section`, `radius-control`, `motion-enter`.
3. If no token fits, decide whether the value represents a reusable design-system role or a component-only detail.
4. Add a global token only for reusable semantic roles. Name the concept, not the current color or pixel size.
5. Keep component-only implementation details local unless they expose a reusable pattern.
6. Audit the diff for raw colors, duplicated style constants, values that bypass existing semantic roles, and unnecessary global one-off tokens before finishing.

## Global Token Boundary

Global tokens are for reusable concepts. Do not add global tokens whose only purpose is to make one component work.

## What Counts As One-Off

A local styling value is acceptable when it is a component-specific implementation detail, does not duplicate an existing semantic token or component variant, and does not need to be shared across surfaces. Normal use of the chosen styling stack's local utilities is not a token violation by itself.

A value becomes a token concern when it:

- Uses a raw color, typography style, radius, shadow, motion, spacing, or size where an existing semantic token or component variant already expresses the same role.
- Encodes a reusable visual role, repeated measurement, or cross-surface relationship that should be part of the design-system contract.
- Overrides reusable component internals instead of selecting or adding an explicit size, tone, density, emphasis, or state variant.
- Adds a global token solely to hide a component-only tweak.

### Colors

- If the color already exists through the semantic token system, use the existing semantic token.
- Do not create a component-specific alias for an existing app-wide semantic color.
- If a genuinely one-off component color does not map to a reusable semantic role, a component-scoped color token is acceptable. Keep it local to that component or component family.
- Promote a component-scoped color to the global token system only when it becomes a reusable role across surfaces.

### Sizing And Layout Values

- If spacing, dimensions, icon sizes, or layout measurements match the existing design system, use the existing tokens or component variants.
- If a sizing value is genuinely one-off for a single component, keep it local using the styling utilities of the chosen stack instead of creating a global token.
- Do not add global tokens named after component-specific pixel values, screenshot measurements, or one-off layout tweaks.
- Revisit local sizing only when the same measurement becomes a repeated pattern or component variant.

### Typography, Radius, Shadow, And Motion

- If typography, radius, shadow, or motion choices match the design-system hierarchy, use the existing token, text style, or component variant.
- Treat local values as acceptable only when they are implementation details, not a substitute for an established semantic role.
- Promote only reusable roles, such as a repeated panel elevation or interaction motion, into the global token system.

## Naming Guidance

| Good | Avoid |
|---|---|
| `--color-action-primary` | `--blue-500` |
| `--space-page-gutter` | `--spacing-24px` |
| `--radius-control` | `--radius-6` |
| `--shadow-floating-panel` | `--shadow-lg-copy` |
| `--motion-emphasized-enter` | `--fast-bounce` |

Good token names describe purpose, scope, and state. Primitive scales may exist internally, but UI code should prefer semantic aliases.

## Component Usage

- Reusable components receive size, tone, density, and emphasis through variants or props, not ad hoc overrides that bypass the component contract.
- Page layouts may control relationships between components with layout-level tokens such as grid gaps and section padding.
- A component's internal padding, icon size, border radius, typography, and state colors belong to the component variant contract.
- Component-scoped color tokens may exist for genuinely unique component color roles, but should not duplicate global semantic colors.
- Component-only sizing values should stay local unless they become reusable variants.

## Audit Script

Run the bundled scanner against changed UI files when a token audit is needed:

```bash
python3 scripts/audit_tokens.py <path> [<path> ...]
```

The scanner flags common review triggers: hex colors, `rgb()/hsl()`, and bracketed literal style values. Findings are prompts for judgment, not proof of a violation. Replace them with semantic tokens only when they duplicate an existing role or represent a reusable design-system decision.

## Done Means

- Existing semantic tokens are reused when they express the role.
- New global tokens have clear reusable semantic names and documented purpose.
- No global token is added for a one-off component sizing or layout tweak.
- One-off component color tokens are component-scoped and do not duplicate existing semantic colors.
- One-off sizing values are local to the component unless they become repeated variants.
- Reusable components expose variants instead of requiring callers to override internals.
