---
name: ui-ux-guidelines
description: >-
  Use when creating, styling, refactoring, or auditing a frontend interface:
  pages, components, design tokens, layouts, spacing, typography, color,
  contrast, dark mode, responsive or mobile views, navigation, buttons, forms,
  validation errors, empty or loading states, or accessibility of HTML, CSS,
  React, or other UI code.
compatibility: >-
  Validators need Node.js 22+; rendered checks also need Chrome, Chromium, Edge,
  or a Playwright Chromium install. Without them, apply the rules by hand and
  report the checks as unverified. Uses the `ux-auditor` native agent when
  available; otherwise perform its review inline.
metadata:
  status: experimental
  allows_tool_references: "true"
---

# UI/UX Guidelines

## Invariants

- Bespoke UI; no stock component-library looks.
- button acts, a[href] navigates; one h1, no skipped headings; skip link.
- Targets ≥48×48px (≥1cm); every visible control tappable.
- Text contrast ≥4.5:1 (body Lc75); control edges/icons ≥3:1.
- Never color alone (links, errors, state, hierarchy); errors need text/icon.
- Visible focus on every keyboard-reachable control.
- Allow zoom; no horizontal scroll at reflow.
- img alt always (decorative empty; charts described).
- Media: no autoplay, pausable, captions/transcripts; ≤3 flashes/s.

## Gate

Complete every step before finishing a frontend task.

1. **Route.** Before writing UI code, read only the modules the task touches:

   | Task touches | Read |
   | --- | --- |
   | Fonts, sizes, weights, text styling | `references/typography.md` |
   | Spacing, grouping, grids, page structure | `references/layout.md` |
   | Palettes, surfaces, themes, dark mode | `references/color.md` |
   | Breakpoints, reflow, motion, touch | `references/responsive.md` |
   | Buttons, forms, errors, feedback, navigation | `references/interaction-forms.md` |

2. **Tokens first.** Define semantic typography, spacing, color (light and dark), and state tokens, then style components only from them. Cover five states for every data view: Ideal, Empty, Loading, Partial, Error.

3. **Validate.** Run the scripts in this skill directory against every changed page (absolute page paths); fix each violation with its `corrective` value and rerun until all exit `0`.

   ```bash
   node scripts/contrast-audit.mjs tokens --pair '<fg>:<bg>:text:<fontPx>:<weight>'   # or --input pairs.json
   node scripts/contrast-audit.mjs dom --html <page.html>                             # or --url <local-url>
   node scripts/geometry-audit.mjs <page.html or local-url>
   ```

   Exit `1` is a violation; `2` or `3` is a usage or browser error, not a pass. `inconclusive` contrast results (background images, native controls) need a manual check before rerunning with `--allow-inconclusive`. `--help` lists rules and flags.

4. **Sign off.** Delegate to the `ux-auditor` agent with the changed files, the page path or URL, and the states to review. Resolve every Blocking Defect, then rerun steps 3 and 4. Without subagents, review hierarchy, cognitive load, form ergonomics, keyboard path, and the five states yourself and report the same two lists.
