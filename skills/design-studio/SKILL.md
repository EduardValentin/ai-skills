---
name: design-studio
description: "Use when doing UI/UX work on a React reference app that mirrors a production codebase: building or auditing pages, components, sections, visual bugs, design-system tokens, reusable component patterns, visual validation, brand-aligned copy, or PRD/DESIGN.md sync."
---

# Design Studio

## Overview

Design Studio is the project overlay for a React reference app. It keeps the session grounded in the local product context: the reference app, `DESIGN.md`, `brand-voice.md`, `PRD.md`, semantic tokens, reusable components, visual validation, and documentation sync.

Let any available companion UI/UX, accessibility, copy, token, component, or visual-validation skills trigger naturally from the user's request. This skill does not require a named external skill or a specific agent harness; if no companion skill is available, follow the acceptance criteria here.

## Core Priorities

1. Prototype/reference-app parity when the reference app is the design source of truth.
2. Semantic HTML and accessibility before styling.
3. Semantic design tokens before ad-hoc values.
4. Reusable components before duplicated UI.
5. Coherent, aesthetically intentional design that fits the audience and product.
6. Rendered visual validation before claiming the work is done.

Deadlines do not relax these priorities. If the requested timeline conflicts with them, surface the tradeoff and ask how the user wants to proceed.

## Requirements

- Ability to read and write files in the working tree.
- Ability to run the reference app with its existing JavaScript tooling.
- Ability to inspect rendered output through screenshots, browser automation, or user-provided screenshots.
- Read access to the project root for `DESIGN.md`, `brand-voice.md`, and `PRD.md` when they exist.

## Prerequisites

1. **Prepare the reference app.** Run `<skill-dir>/scripts/prepare-design-studio.sh --project-root <abs-path>`. The script detects the app under `designs/`, installs dependencies only when needed, and prints the dev command. If detection fails, ask the user for the app path.

2. **Create a project-context digest with context isolation.** Before design work, summarize only the context needed for the task:
   - semantic tokens from the theme and global CSS
   - reusable components and variants
   - relevant routes/pages
   - brand voice highlights
   - PRD slice relevant to the task
   - rendered aesthetic signals if screenshots already exist
   - mismatches and missing artifacts

   Prefer delegating this scan to a context-isolated worker/subagent when the environment supports it. The main session should receive only the compact digest, not raw docs, full component trees, or large source excerpts. If no delegation or context-saving mechanism exists, produce the digest inline and keep it compact. `references/context-digest-prompt.md` contains a reusable prompt.

3. **Handle missing or conflicting sources.**
   - `DESIGN.md` missing: ask for design direction and create it before extending the system.
   - `brand-voice.md` missing: note it and ask for tone/audience before writing meaningful copy.
   - `PRD.md` missing: offer to generate one using `references/prd-generation.md`.
   - Token docs and theme disagree: treat the implemented theme as the current source of truth, flag the mismatch, and offer to update `DESIGN.md`.

4. **Capture visual context.** Start the app, inspect the target page and nearby pages, and write a 3-to-5 bullet aesthetic summary: color rhythm, spacing rhythm, type hierarchy, density, component shape, and motion. If the environment cannot capture screenshots, use the fallback ladder in `references/browser-fallback.md`.

## Context Discipline

Design work often tempts agents to load everything: `DESIGN.md`, `brand-voice.md`, `PRD.md`, theme files, router files, component trees, screenshots, and page code. Do not pull all of that into the main working context when a compact digest or delegated scan can answer the task.

Prefer context-isolated delegation for:

- project-context digest creation
- PRD generation app analysis
- PRD sync checks
- audits across 3 or more pages/components/routes
- broad component inventory or token inventory

The main session should work from structured summaries, screenshots, and targeted file reads. Read raw source in the main context only when implementing, verifying a cited detail, resolving a mismatch, or when delegation is unavailable.

## Choose The Flow

| User request | Flow |
|---|---|
| New page, section, component, or design-system extension | Build from scratch |
| Declutter, visual bug, mobile issue, copy polish, or audience fit | Audit existing |
| Ambiguous request such as "make this better" | Ask whether the user wants new UI, refinement, or both |

## Flow A: Build From Scratch

1. Clarify scope, affected pages/components/tokens, audience, and success criteria.
2. If multiple design directions are plausible, run a persistent design-direction brainstorm: audience, goal, desired impression, constraints, tradeoffs, options, recommendation, and shared understanding.
3. Run the business-logic gate from Rule 8.
4. Plan the implementation: reused components, new or extended variants, token needs, responsive behavior, accessibility considerations, visual validation, and documentation sync.
5. Get user approval on the plan before editing code.
6. Implement incrementally, previewing after significant changes.
7. Validate rendered output.
8. Update `DESIGN.md` when the design system changes and sync `PRD.md` when business behavior changes.

## Flow B: Audit Existing

1. Frame the audit with the user: audience, goal, target page/state, and what success looks like.
2. Run the business-logic gate from Rule 8.
3. Capture the current rendered state at relevant breakpoints and states.
4. Critique information hierarchy, clutter, accessibility, responsive behavior, token use, component reuse, copy clarity, and visual fit. For audits spanning 3 or more pages/components/routes, prefer delegating the broad critique or inventory to a context-isolated worker/subagent, then rank fixes in the main session from the structured summary.
5. Propose ranked fixes and get user approval on scope.
6. Apply approved fixes.
7. Re-validate the same viewports and states.
8. Update `DESIGN.md` or `PRD.md` only when their source-of-truth content changed.

## Design Rules

### Rule 1: Semantic Tokens First

Use existing semantic tokens when they express the role. Add global tokens only for reusable design-system concepts, not for one-off component implementation details.

For colors, prefer existing semantic color tokens. If a color is genuinely unique to one component and does not map to a reusable role, keep it as a component-scoped token. For sizing and layout values, use existing tokens or variants when they match the system; if a value is genuinely one-off for a single component, keep it local with the chosen styling utilities instead of adding a global token. Document `DESIGN.md` only when the global token system changes.

### Rule 2: Semantic HTML And Accessibility First

Start with the correct native elements, document structure, headings, landmarks, labels, buttons, links, forms, tables, dialogs, and status messages. Add ARIA only when native HTML cannot express the interaction. Keyboard behavior, accessible names, focus visibility, contrast, reduced motion, and screen-reader meaning are acceptance criteria.

### Rule 3: Design-System Consistency

New UI should look like it belongs in the existing product. Match documented tokens, component shapes, density, spacing rhythm, typography, and motion. Extend the system only when the existing system lacks a needed semantic role.

### Rule 4: Component Reuse

Before creating UI, inspect nearby reusable components. Reuse when the role matches, extend with variants when the role is the same but presentation differs, and create a new component when the role or interaction model is genuinely different. Keep page-specific logic outside reusable components.

Ask the user only when the choice changes the design-system contract or has multiple reasonable API directions.

### Rule 5: Brand-Voice Copy

Do not invent meaningful page or section copy without a copy brief. For headings, hero text, value props, CTAs, empty states, error text, and marketing microcopy, gather audience, key message, tone, themes, and must-use or banned terms. Use `brand-voice.md` when available. Trivial system labels such as "Save" or "Cancel" do not need a copy gate.

Keep copy focused on brand voice and user clarity.

### Rule 6: React Router Navigation

For in-app navigation, use the project's router primitives rather than full-page reloads. Raw anchors are appropriate for external links and must include safe external-link attributes when opening a new tab.

### Rule 7: Scope Discipline

Modify only the React reference app and project source-of-truth docs needed for the task: `DESIGN.md`, `brand-voice.md`, and `PRD.md`. Mock backend behavior in the reference app unless the user explicitly asks for production integration.

### Rule 8: Business-Logic Gate

Before planning, ask:

> Is this change introducing, modifying, or extending domain or business logic: a new product capability, business rule, data entity or field, user-flow step, branch, case, removal, or replacement? If yes, I will plan the PRD update alongside the design work.

If yes, include PRD sync in the plan. If no or uncertain, proceed but re-check during validation. If the implementation reveals a business change, raise it before declaring done.

## Visual Validation

Use the product's breakpoint system. At minimum, validate 320px, just below and above each configured breakpoint, a normal desktop width, and a wide desktop width around 1920px.

Check:

- no unintended horizontal scroll, clipping, overlap, or collapsed sections
- readable text and stable control sizes
- correct alignment and spacing rhythm
- keyboard order, focus states, accessible names, and contrast
- default, loading, empty, error, disabled, selected, expanded, and long-content states when relevant
- consistency with the reference app and token system

Fix failures before presenting the work as complete.

## PRD Sync

Update `PRD.md` only when the change affects business-level product behavior: capabilities, rules, data model, flow steps, branching, permissions, or removal/replacement of a flow. Do not update it for visual styling, component architecture, responsive behavior, animation, or copy tone unless those changes alter what the product does.

Use `references/prd-sync-prompt.md` as the sync checklist. If uncertain, prefer a concise user question over adding visual or technical detail to the PRD.

## Self-Check Before Done

- [ ] Project-context digest created and missing/mismatched sources handled.
- [ ] Context-isolated delegation used for large scans/digests when available; main context kept to compact summaries and targeted reads.
- [ ] Design direction aligned when multiple directions were plausible.
- [ ] Business-logic gate answered and PRD sync handled if needed.
- [ ] Semantic HTML, keyboard behavior, focus, contrast, and accessible names checked.
- [ ] Existing semantic tokens reused; new global tokens documented only for reusable roles; one-off component sizing kept local.
- [ ] Reusable component opportunities handled.
- [ ] Meaningful copy follows the copy brief and brand voice.
- [ ] Rendered output validated across required viewports/states.
- [ ] `DESIGN.md` updated if the design system changed.
- [ ] Scope stayed within the reference app and source-of-truth docs.
