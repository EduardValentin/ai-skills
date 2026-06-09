---
name: design-studio
description: Use when doing UI/UX work in a React reference app that mirrors production, including building or auditing pages, components, sections, visual bugs, design-system changes, brand-copy changes, or DESIGN.md/PRD.md sync.
---

# Design Studio

## Purpose

Use this as the project overlay for a React reference app. Keep work grounded in the runnable app, `DESIGN.md`, `brand-voice.md`, `PRD.md`, existing tokens/components, and rendered evidence.

## Requirements

- Read and write access to the working tree.
- Ability to run the reference app with its existing JavaScript tooling.
- A way to inspect rendered output: native screenshots, browser automation, or user-provided screenshots.

## Setup

1. Prepare the reference app:

```bash
<skill-dir>/scripts/prepare-design-studio.sh --project-root <abs-path>
```

Use `--app-root <abs-path>` if app detection under `designs/` fails. The script prints the app root and dev command.

2. Produce a compact project digest before design work. Use `references/context-digest-prompt.md`; keep only task-relevant tokens, components, routes, brand voice, PRD slice, missing artifacts, and mismatches in active context.

3. Capture visual context for the target page and nearby shared surfaces. Record 3 to 5 bullets covering color rhythm, spacing, type hierarchy, density, component shape, and motion. If capture is blocked, follow `references/browser-fallback.md`.

## Source Rules

- `DESIGN.md` missing: ask for design direction and create it before extending the design system.
- `brand-voice.md` missing: ask for audience/tone before writing meaningful copy.
- `PRD.md` missing: offer to generate it with `references/prd-generation.md`.
- Theme and docs disagree: treat the implemented theme as current truth, flag the mismatch, and offer to update `DESIGN.md`.
- Only update `DESIGN.md` when the reusable design system changes.
- Only update `PRD.md` when product behavior changes: capabilities, rules, data, permissions, flow steps, branching, removal, or replacement.

## Flow

Choose one path:

- Build: new page, section, component, state, or design-system extension.
- Audit: visual bug, clutter, mobile issue, copy polish, consistency issue, or audience fit.
- Clarify: ambiguous requests like "make this better" when build vs refinement is unclear.

Before planning, ask whether the change introduces or alters domain/business logic. If yes, include PRD sync in the plan.

Plan only the task-relevant scope: affected files, reused or new components, token/documentation impact, accessibility checks, responsive states, and rendered validation. Ask for user approval only when the direction, product behavior, or design-system contract is materially changing.

## Work Rules

- Start from semantic native structure and accessible behavior, then style.
- Reuse existing semantic tokens and components when their role matches.
- Add global tokens or reusable component variants only for reusable roles.
- Keep one-off styling local when it is not replacing a semantic role.
- Keep page-specific data, routing, analytics, and business rules out of reusable UI components.
- Use project router primitives for internal navigation.
- Mock backend behavior in the reference app unless production integration is explicitly requested.

## Done

- Rendered output was checked at 320px, normal desktop, wide desktop around 1920px, and configured breakpoint boundaries when relevant.
- Relevant default, loading, empty, error, disabled, focused, selected, expanded, and long-content states were checked.
- No unintended horizontal scroll, clipping, overlap, unreadable text, broken focus, or obvious contrast issue remains.
- `DESIGN.md` and `PRD.md` were updated only when their source-of-truth content changed.
- The final note names visual evidence, docs changed, and any residual verification gap.
