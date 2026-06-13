---
name: prototype-work
description: Use when working in a prototype reference application, usually a React app under designs/, to add or change prototype pages, user flows, mocked business rules, mocked integrations, backend-facing behavior, or PRD/DESIGN/brand-voice alignment.
---

# Prototype Work

## Purpose

Prototype reference applications define product UX before production work: user flows, mocked business rules, mocked integrations, and backend-facing behavior. They are usually React apps under `designs/` with root-level `PRD.md`, `DESIGN.md`, and `brandvoice.md` or `brand-voice.md`.

## When To Use

- Adding or changing prototype reference app pages, routes, flows, states, mocks, mocked integrations, or backend-facing behavior.
- Updating companion product/design/voice docs because prototype behavior or direction changed.

## Forbidden Behavior

- Do not treat production app implementation as prototype work. Only use this skill for production code when the user explicitly asks to port prototype behavior into production.

## Requirements

- Read and write access to the working tree.
- Ability to run the reference React app with its existing JavaScript tooling.
- Native browser tooling to navigate the app, click through flows, and capture screenshots or browser evidence.

## Preparation

1. Prepare the prototype app:

```bash
<skill-dir>/scripts/prepare-prototype-work.sh --project-root <abs-path>
```

The script only auto-detects React apps under `designs/`. If it cannot find one, stop and ask the user for the reference app path. Then rerun with `--app-root <abs-path>`.

2. Start the dev server from the command printed by the script.

3. Use the browser to click through the app and take 2-3 screenshots from different pages or flow states. Summarize the app's visual vibe in a few bullets.

4. Gather compact reports in parallel when possible; otherwise produce the same reports inline:
   - Product: app goal, target audience, core flows, business rules, constraints, and task-relevant PRD direction.
   - Voice: audience, tone, preferred language, banned language, and copy principles.
   - Design: design philosophy, visual direction, accessibility priorities, and design-system rules.
   - App scope: routes, mock boundaries, semantic tokens, theme configuration, component inventory, variants, and design-system configuration.

## Prototype Rules

- Keep mocks, routing, and business rules separate from presentational components.
- Use configured router primitives and exercise flows by clicking through the app instead of manually typing URLs that lose app state.
- Mock new or changed business rules explicitly in the prototype.
- Represent async prototype behavior with appropriate loading, success, empty, and error states.

## PRD Consolidation

If the change adds or alters a user flow, page, component, business rule, data field, permission, branch, mocked integration, or backend-facing behavior even slightly, update `PRD.md`.

Keep PRD edits concise and non-redundant. The PRD contains business rules and product behavior only: no code, component names, design decisions, token names, layout details, or implementation mechanics.

## Completion

- Click through the changed flow in the running prototype.
- Capture browser evidence for the changed surfaces.
- Confirm PRD consolidation was completed when product behavior changed.
- In the final response, name browser evidence, docs changed, and any remaining blocker.
