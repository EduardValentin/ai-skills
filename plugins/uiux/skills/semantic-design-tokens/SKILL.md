---
name: semantic-design-tokens
description: Use when styling, auditing, or extending frontend UI that should use semantic design tokens for color, spacing, typography, radii, shadows, motion, or component variants instead of ad-hoc values, raw hex/rgb colors, arbitrary utility classes, or duplicated theme constants.
---

# Semantic Design Tokens

## Overview

Use tokens as the design-system contract. Components should express intent through semantic names, not through raw visual values scattered across JSX, CSS, or config files.

## Token-First Workflow

1. Inventory existing tokens before styling: theme files, global CSS, component variants, and DESIGN.md or equivalent docs.
2. Use existing semantic tokens when they express the role: `surface`, `border-subtle`, `text-muted`, `space-section`, `radius-control`, `motion-enter`.
3. If no token fits, propose the missing role before adding values. Name the concept, not the current color or pixel size.
4. Add the token in the design-system source of truth, document its purpose, then consume it through components or variants.
5. Audit the diff for raw values and arbitrary utilities before finishing.

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

- Reusable components receive size, tone, density, and emphasis through variants or props, not external one-off class overrides.
- Page layouts may control relationships between components with layout-level tokens such as grid gaps and section padding.
- A component's internal padding, icon size, border radius, typography, and state colors belong to the component variant contract.

## Audit Script

Run the bundled scanner against changed UI files when a token audit is needed:

```bash
python3 scripts/audit_tokens.py <path> [<path> ...]
```

The scanner flags common raw values: hex colors, `rgb()/hsl()`, and Tailwind-style arbitrary bracket utilities. Review the findings manually because token definition files and third-party snippets may contain legitimate raw values.

## Done Means

- No new raw color, spacing, typography, radius, shadow, or motion value appears in product UI code unless it is inside a token definition.
- New tokens have clear semantic names and documented purpose.
- Reusable components expose variants instead of requiring callers to override internals.
