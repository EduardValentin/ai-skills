---
name: prototype-work
description: Use when working in a prototype reference application, usually a React app under designs/, to add or change prototype pages, components, user flows, mocked business rules, mocked integrations, backend-facing behavior, or related PRD/DESIGN/brand-voice alignment.
---

# Prototype Work

## Purpose

Prototype reference applications define product UX before production work: user flows, mocked business rules, mocked integrations, and backend-facing behavior. They are usually React apps under `designs/` and are usually accompanied by root-level `PRD.md`, `DESIGN.md`, and `brandvoice.md` (or `brand-voice.md` in repos that already use that name).

## Requirements

- Read and write access to the working tree.
- Ability to run the reference React app with its existing JavaScript tooling.
- Native browser tooling to navigate the app, click through flows, take screenshots, inspect states, and validate changes.

## Preparation

1. Prepare the prototype app:

```bash
<skill-dir>/scripts/prepare-prototype-work.sh --project-root <abs-path>
```

The script only auto-detects React apps under `designs/`. If it cannot find one, stop and ask the user for the reference app path before doing anything else. Then rerun with `--app-root <abs-path>`.

2. Start the dev server from the command printed by the script.

3. Use the browser to click through the app and take 2-3 screenshots from different pages or flow states. Summarize the app's visual vibe: color, density, typography, component shape, spacing, and motion.

4. Gather compact reports in parallel when the environment supports isolated workers; otherwise produce the same reports inline without dumping raw files into the main context:
   - `PRD.md`: app goal, target audience, core user flows, key business rules, constraints, and product directions relevant to the task.
   - `brandvoice.md` / `brand-voice.md`: tone, audience details, preferred language, banned language, and copy principles.
   - `DESIGN.md`: design philosophy, colors, visual vibe, layout direction, accessibility priorities, and design-system rules.
   - Reference app scope: semantic tokens, theme properties, theming decisions, component list, component variants, design-system configuration, routes, and mock data boundaries.

If any root document is missing, note the gap and ask before making changes that depend on it.

## PRD Consolidation

If the change adds or alters a user flow, page, component, business rule, data field, permission, branch, mocked integration, or backend-facing behavior even slightly, update `PRD.md` with the prototype change.

Keep PRD edits concise and non-redundant. The PRD contains business rules and product behavior only: no code, component names, design decisions, token names, layout details, or implementation mechanics.

## Work Rules

- Use the implemented semantic token system for every UI change. Reuse existing tokens when their semantic role fits.
- Add a token only for a reusable semantic role. Name the role generically, such as `color-primary` or `size-large`, never by a specific color, component, pixel value, or one-off need.
- Do not add one-off colors, sizes, typography, shadows, or spacing outside the design system.
- Keep mocks clearly separated from presentational components.
- Keep routing separate from presentational components.
- Keep business rules separate from presentational components.
- Use configured router primitives for internal navigation, and validate flows by clicking through the app instead of manually typing URLs that lose app state.
- When a new or changed flow introduces a business rule, mock that rule explicitly in the prototype.
- Respect the app's existing breakpoints and validate changed surfaces across the relevant viewport range.
- Add proper loading states for async behavior: API-like fetches, file reads, delayed computations, mocked integrations, and any operation that takes time.
- Prefer reusing existing components. Extend variants when the role matches but the current variants do not cover the need. Add a new component only when reuse or extension would blur the component's purpose.

## Validation

Before calling the work done:

- Click through the changed flow in the running prototype.
- Validate relevant default, loading, empty, error, disabled, focused, selected, expanded, long-content, and mocked-integration states.
- Capture screenshots at mobile, normal desktop, wide desktop, and any configured breakpoint boundaries affected by the change.
- Check for unintended horizontal scroll, clipping, overlap, unreadable text, broken focus, contrast issues, and visual artifacts.
- Confirm PRD consolidation was completed when product behavior changed.

The final response should name the browser evidence, states checked, screenshots taken, PRD/DESIGN/brand-voice updates, and any residual validation gap.
