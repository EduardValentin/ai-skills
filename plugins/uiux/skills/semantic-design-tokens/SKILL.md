---
name: semantic-design-tokens
description: Use when styling, auditing, or extending frontend UI that needs semantic design tokens for reusable color, spacing, typography, radii, shadows, motion, or clear boundaries between semantic roles and local styling values.
---

# Semantic Design Tokens

## Overview

Use tokens as the design-system contract. Global semantic tokens should express reusable roles across the application, not surface-specific implementation details.

## When To Use

- Styling, auditing, or extending UI where semantic color, spacing, typography, radii, shadows, or motion roles matter.
- Reviewing raw values, duplicated style constants, or local values that may bypass the design system.
- Deciding whether a value belongs in global tokens, scoped tokens, or local styling.

## Token-First Workflow

1. Inventory existing token sources before styling: theme files, global CSS, token docs, and DESIGN.md or equivalent docs.
2. Use existing semantic tokens when they express the role: `surface`, `border-subtle`, `text-muted`, `space-section`, `radius-control`, `motion-enter`.
3. If no token fits, decide whether the value represents a reusable design-system role or a local implementation detail.
4. Add a global token only for reusable semantic roles. Name the concept, not the current color or pixel size.
5. Keep implementation-only details local unless they expose a reusable semantic role.
6. Audit the diff for raw colors, duplicated style constants, values that bypass existing semantic roles, and unnecessary global one-off tokens before finishing.

## Token Boundary Rules

- Add global tokens only for reusable cross-surface roles.
- Keep local styling values when they are not repeated, do not duplicate an existing token, and do not define a reusable contract.
- Use scoped tokens only for named roles inside a local surface or family; promote them only when the role becomes reusable across surfaces.
- Do not add global tokens for sampled screenshot values, surface-specific sizes, one-off layout tweaks, or literal pixel/color names.
- Primitive scales may exist internally, but UI code should prefer semantic aliases.

A value becomes a token concern when it uses raw color, spacing, typography, radius, shadow, motion, or size where an existing token already expresses the same role; or when it creates a repeated visual relationship that should stay consistent across the product.

## Naming Guidance

| Good | Avoid |
|---|---|
| `--color-action-primary` | `--blue-500` |
| `--space-page-gutter` | `--spacing-24px` |
| `--radius-control` | `--radius-6` |
| `--shadow-floating-panel` | `--shadow-lg-copy` |
| `--motion-emphasized-enter` | `--fast-bounce` |

Good token names describe purpose, scope, and state. Primitive scales may exist internally, but UI code should prefer semantic aliases.

## Audit Script

Run the bundled scanner against changed UI files when a token audit is needed:

```bash
python3 scripts/audit_tokens.py <path> [<path> ...]
```

The scanner flags common review triggers: hex colors, `rgb()/hsl()`, and bracketed literal style values. Findings are prompts for judgment, not proof of a violation. Replace them with semantic tokens only when they duplicate an existing role or represent a reusable design-system decision.

## Done Means

- Existing semantic tokens are reused when they express the role.
- New global tokens have reusable semantic names and documented purpose.
- Local styling values remain local when they do not define reusable roles.
- No global token is added for sampled colors, literal measurements, or one-off layout tweaks.
