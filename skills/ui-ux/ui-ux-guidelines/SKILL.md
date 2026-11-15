---
name: ui-ux-guidelines
description: >-
  Use when designing or building a graphical interface: pages, layout,
  spacing, typography, color, contrast, dark mode, responsive or mobile views,
  navigation, buttons, forms, validation errors, empty, loading or error
  states, motion, or accessibility, in HTML, CSS, React, native, or other GUI
  code.
compatibility: >-
  Validators need Node.js 22+ and, for rendered checks, Chrome, Chromium, Edge,
  or a Playwright Chromium; without them apply the rules by hand and report
  the checks as unverified. Defers to the `semantic-design-tokens` and
  `reusable-ui-components` skills; when absent, reuse existing tokens and
  components by inspection. Uses the `frontend-auditor` agent; when absent,
  give its prompt to a fresh generic subagent, or review inline against this
  skill and its validators.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# UI/UX Guidelines

Design rules and their validators. Tokens belong to `semantic-design-tokens`, component reuse to `reusable-ui-components`, rendered evidence to the `frontend-auditor` agent.

## Invariants

- Bespoke UI where no design system exists; no stock component-library looks.
- button acts, a[href] navigates; one h1, no skipped headings; skip link.
- Targets ≥48×48px pointer area (≥1cm); every visible control tappable.
- Text contrast ≥4.5:1 (body Lc75); control edges/icons ≥3:1.
- Never color alone (links, errors, state, hierarchy); errors need text/icon.
- Visible focus on every focusable control.
- Allow zoom; no horizontal scroll at reflow.
- img alt always (decorative empty; charts described).
- Media: no autoplay, pausable, captions/transcripts; ≤3 flashes/s.

## Precedence

Repository instructions and an existing design system override module defaults (scales, grids, palettes, type sizes). The Invariants always hold.

## Gate

1. **Route.** Establish audience, task, tone, density and platform. Before writing UI code, read only what the task touches:

   | Task touches | Read |
   | --- | --- |
   | Fonts, sizes, weights, text styling | `references/typography.md` |
   | Spacing, grouping, grids, page structure | `references/layout.md` |
   | Palettes, surfaces, themes, dark mode | `references/color.md` |
   | Breakpoints, reflow, motion, touch | `references/responsive.md` |
   | Buttons, forms, errors, feedback, navigation | `references/interaction-forms.md` |
   | Token values or names | `semantic-design-tokens` skill |
   | Reusing, extending or creating components | `reusable-ui-components` skill |

   When a visual spec exists, it is the direction; build from it.

2. **Build.** Native semantics before custom wrappers; ARIA only for what the platform cannot express. Style only from semantic tokens. Give every data view five states: Ideal, Empty, Loading, Partial, Error.

3. **Validate** browser-rendered UI. Run the scripts in this skill directory on every changed page (absolute paths); fix each violation with its `corrective` value and rerun until all exit `0`.

   ```bash
   node scripts/contrast-audit.mjs tokens --pair '<fg>:<bg>:text:<fontPx>:<weight>'   # or --input pairs.json
   node scripts/contrast-audit.mjs dom --html <page.html>                             # or --url <local-url>
   node scripts/geometry-audit.mjs <page.html or local-url>
   ```

   Add `--viewports` for the project's breakpoints. Exit `1` is a violation; `2` or `3` means the check did not run. `inconclusive` contrast results need a manual check before rerunning with `--allow-inconclusive`. `--help` lists rules and flags.

4. **Sign off.** Delegate to the `frontend-auditor` agent with the changed files, page paths or URL, and affected states. Resolve every `blocker` and `major` finding, then repeat steps 3 and 4.
