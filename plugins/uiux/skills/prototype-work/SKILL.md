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

When stopping for a missing reference app path, the response must include both parts: ask for the path and state that preparation will be rerun with `--app-root <abs-path>` after the user provides it. Do not edit code or docs while this path is unknown.

2. Start the dev server from the command printed by the script.

3. Use the browser to click through the app and take 2-3 screenshots from different pages or flow states. Summarize the app's visual vibe in a few bullets.

4. Gather compact reports in parallel when possible; otherwise produce the same reports inline:
   - Product: app goal, target audience, core flows, business rules, constraints, and task-relevant PRD direction.
   - Voice: audience, tone, preferred language, banned language, and copy principles.
   - Design: design philosophy, visual direction, accessibility priorities, and design-system rules.
   - App scope: routes, mock boundaries, semantic tokens, theme configuration, component inventory, variants, and design-system configuration.

Preparation is incomplete until those outputs are framed as compact reports: product report, voice report, design report, and app-scope report. Do not replace them with raw doc dumps or a vague note that the docs were read.

## Prototype Rules

- Keep mocks, routing, and business rules separate from presentational components.
- Use configured router primitives and exercise flows by clicking through the app instead of manually typing URLs that lose app state.
- Mock new or changed business rules explicitly in the prototype.
- When a flow includes a simulated fetch, API boundary, or backend-facing behavior, list and implement an explicit API-like mock for that behavior; do not rely on async states alone to imply the mock.
- Represent async prototype behavior with appropriate loading, success, empty, and error states.

## Code Mapping

When prototype work will feed production planning, implementation, visual parity, or review, prepare a prototype-side mapping handoff before asking the native `code-mapper` agent to map production code.

The handoff should include:

- Prototype app root, relevant routes, and stateful flow branches.
- Prototype component or element locators for visible relevant declarations.
- Accessible names, roles, visible copy, and interaction states that production must preserve.
- Mocked business rules, mocked integration boundaries, API-like mocks, and data shapes.
- PRD/DESIGN/brand-voice facts that are load-bearing for production parity.
- Known or suspected production route, state, selector, test, or component counterparts, labeled as known or uncertain.

Ask `code-mapper` to return a read-only production map that pairs production locators with the relevant prototype route, state, selector, and element counterparts. If the prototype uses dynamic composition or third-party code that hides useful declaration locators, say so in the handoff instead of inventing locators.

Do not use this code mapping handoff as permission to edit production code. It is preparation for downstream planning, implementation, verification, or visual parity work.

## PRD Consolidation

If the change adds or alters a user flow, page, component, business rule, data field, permission, branch, mocked integration, or backend-facing behavior even slightly, update `PRD.md`.

Keep PRD edits concise and non-redundant. The PRD contains business rules and product behavior only: no code, component names, design decisions, token names, layout details, or implementation mechanics.

Whenever listing obligations for a prototype behavior change, state both halves: `PRD.md` must be updated, and the PRD content must stay limited to business rules and product behavior rather than mocks, simulated API mechanics, component details, or implementation notes.

## Completion

- Click through the changed flow in the running prototype.
- Capture browser evidence for the changed surfaces.
- Confirm PRD consolidation was completed when product behavior changed.
- In the final response, name browser evidence, docs changed, and any remaining blocker.
