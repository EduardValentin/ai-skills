---
name: prototype-backed-workflow
description: Use when working on a project that maintains a React based reference prototype app alongside the production app.
compatibility: >-
  Requires writable worktree, Bash/Git, React app, active Node runtime, and app-selected package manager. Use Browser tool for screenshots if available; otherwise return a manual plan/blocker.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# Prototype Work

## Purpose

A React-based prototype reference app models user flows, designs, and user journeys in a React single-page application with mocked external dependencies and API calls. It provides an easy-to-change place to iterate on domain objects, business rules, validation, the design system, and the look of the real application. Agents use it as a guide when implementing approved production features.

## When To Use

- Use when iterating on the maintained prototype of a production application, including its design system, user flows, domain objects, domain validation, and planned or existing features.
- For implementation work, use only when the user requests a feature implementation or update that touches a production application's frontend or user-visible interface.
- Use for exploratory research that compares prototype features with implemented production features.

## Rules

- Make and approve new production features in the prototype before making them in production. Production must not contain features absent from the prototype, while the prototype may contain features absent from production.

## Requirements

- Read and write access to the working tree.
- Ability to run the reference React app with its existing JavaScript tooling.
- Native browser tooling to navigate the app, click through flows, and capture screenshots or browser evidence.

## Preparation

Bundled paths in this skill resolve from the skill root.

1. Run the helper with the absolute project root and, when known, the absolute reference app root:

```bash
scripts/prepare-prototype-work.sh --project-root <abs-project-path> --app-root <abs-app-path>
```

Omit `--app-root` only for discovery:

```bash
scripts/prepare-prototype-work.sh --project-root <abs-project-path>
```

If discovery finds zero or multiple candidates, ask for the absolute app path, make no code or documentation changes, and rerun with `--app-root <abs-app-path>`.

The helper only locates and validates the reference app.

2. Use the selected app as the working directory when installing dependencies or starting its development script.

3. Inspect two or three pages or flow states in the browser and capture screenshots. Summarize the visual vibe and provide compact product, voice, design, and app-scope reports covering the listed concerns.
   - Product: app goal, target audience, core flows, business rules, constraints.
   - Voice: audience, tone.
   - Design: design philosophy, visual direction, accessibility priorities, and design-system rules.
   - App scope: routes, mock boundaries, semantic tokens, theme configuration, component inventory, and variants.


## Prototype Rules

- Keep mocks, routing, and business rules separate from presentational components.
- Use configured router primitives and exercise flows by clicking through the app instead of manually typing URLs that lose local app state.
- Mock new or changed business rules explicitly in the prototype.
- When a flow includes a simulated fetch, API boundary, or backend-facing behavior, list and implement an explicit API-like mock for that behavior; do not rely on async states alone to imply the mock.
- Represent asynchronous prototype behavior with appropriate loading, success, empty, and error states.
