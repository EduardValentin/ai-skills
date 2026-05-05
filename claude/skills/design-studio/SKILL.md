---
name: design-studio
description: Use when doing UI/UX work on a React reference app that mirrors a production codebase — building new pages/components/sections, auditing existing pages for clarity/decluttering/visitor fit, fixing visual bugs, or extending the design system. Only the React reference app is modified, never production code.
---

# Design Studio

Project-specific overlay for design work on a React + Tailwind reference app. General design quality (accessibility, responsive testing, animation, visual polish, latest patterns) is delegated to the `frontend-design:frontend-design` skill. Page copy is delegated to `searchfit-seo:on-page-seo`. This skill enforces the project layer: setup, semantic tokens, design-system extension rules, the two scenario flows, and PRD sync.

**Deadlines do not relax the rules.** User-imposed time pressure ("I need this in 20 minutes", "the demo is at the top of the hour") does not authorize skipping the copy gate, the `frontend-design` invocation, semantic-token discipline, or visual validation. If the timeline cannot accommodate compliance, surface the tradeoff to the user (do it right and miss the deadline / scaffold with placeholders + flag for proper pass / push the deadline) rather than silently cut corners.

## Required sub-skills

These MUST be invoked at the points specified. Do not paraphrase, summarize, or skip.

| Sub-skill | When to invoke |
|---|---|
| `frontend-design:frontend-design` | Before implementing any visual change (Flow A Phase 2; Flow B critique step) |
| `searchfit-seo:on-page-seo` | Whenever copy is created or rewritten — AFTER the copy gate (Rule 6) |
| `searchfit-seo:content-brief` | Fallback for long-form pages only (blog post, guide, deep article) |

## Prerequisites

Run in order. Do not skip.

1. **Setup script** — `<skill-dir>/scripts/prepare-design-studio.sh --project-root <abs-path>` (add `--app-root` if known). Handles Node version, package manager, install, and `.claude/launch.json`. Don't hand-create launch.json or install deps manually unless the script fails.

2. **Locate the reference app** — `<project-root>/designs/<app-name>/`. If `designs/` is missing or has no JSX/TSX, ask the user for the path. Validate the path has a `package.json` with React.

3. **Read project context** (every session):
   - `DESIGN.md` (project root) — design system. Missing? Ask the user for design direction and create it before proceeding.
   - `brand-voice.md` (project root) — copy guidelines. Missing? Note it; default to clear, direct, human language.
   - **Tailwind theme** — `@theme` blocks in CSS for v4, or `tailwind.config.{ts,js}` for v3. Map every semantic token. This is your styling vocabulary; nothing outside it without explicit approval.
   - **Component inventory** — scan `components/` for primitives, custom components, and patterns (CVA, cn(), data-slot).
   - **Router + pages** — current routes/structure.
   - `package.json` — dependency versions.
   - `PRD.md` (project root) — business rules / user flows. Missing? See `references/prd-generation.md` and offer to generate one.

4. **Visual context** — start the dev server (`preview_start`), screenshot the main pages, build a mental model of the existing aesthetic. No internal browser? See `references/browser-fallback.md`.

## The two flows

Pick one based on the user's request. If unclear, ask.

### Flow A — Build from scratch

For new pages, components, sections, or design-system extensions.

1. **Understand** — clarify scope, identify affected pages/components/tokens, ask clarifying questions before any code. **Then run the domain/business-logic gate (Rule 8) before planning.**
2. **Plan + design guardrails** — invoke `frontend-design:frontend-design`. Then describe what you'll build, list components to create/modify/reuse, identify any new tokens needed, describe responsive behavior. If Rule 8 answered *yes*, include the PRD update in the plan. Get explicit user approval before writing code.
3. **Copy gate (if any copy is involved)** — see Rule 6. Do not skip.
4. **Implement** — incrementally, one component/section at a time. Comply with all rules. Preview after each significant change.
5. **Validate** — see "Visual validation" below.
6. **Document + sync** — update DESIGN.md if the system was extended. Run PRD sync if business behavior changed.

### Flow B — Audit existing

For refining an existing page for a visitor segment, decluttering, fixing visual bugs, or improving SEO/copy on the page.

1. **Frame the audit** — ask the user: who is the audience, what is the goal (declutter / segment fit / bug fix / SEO / copy clarity), what does success look like? **Then run the domain/business-logic gate (Rule 8) before capturing state.**
2. **Capture current state** — screenshot the target page(s) at every breakpoint boundary (just-before and just-after each defined breakpoint, plus 320px and 1920px).
3. **Critique** — invoke `frontend-design:frontend-design`. Produce a written critique covering: information hierarchy, visual clutter, accessibility, responsive issues, visual bugs, copy clarity, and on-page SEO observations. Do not start changing code yet.
4. **Propose ranked fixes** — list fixes ordered by impact. Get user approval on scope before changing code.
5. **Apply fixes**:
   - Visual/structural changes — implement directly under the design rules.
   - **Copy changes** — see Rule 6. The copy gate applies here too. Never rewrite copy from your own head, even when "just fixing" a phrase.
6. **Re-validate** — re-screenshot at the same viewports and confirm fixes landed without regressions.
7. **Document + sync** — DESIGN.md if the system was extended; PRD only if business behavior changed.

## Design rules

These rules are non-negotiable. Every action must comply.

### Rule 1: Semantic tokens only

No ad-hoc hex codes, rgb values, or arbitrary Tailwind values for colors, spacing, or typography. Every style references an existing semantic token. If no token exists for what you need: STOP, propose a name to the user (`--[proposed-name]`), wait for approval, add it to the theme, update DESIGN.md, then use it.

### Rule 2: Design system consistency

Don't invent new visual patterns, colors, fonts, or component styles unless extending the design system was the explicit ask. New UI must look like it belongs. Match the vibe documented in DESIGN.md. When extending the system, update DESIGN.md.

### Rule 3: Component-first

If a UI pattern repeats (or could repeat), extract a component. If a change might affect an existing component, STOP and ask the user: "(A) Extend the existing component with a new variant/prop, or (B) Create a new separate component?" Components must have clean prop APIs and no page-specific logic.

### Rule 4: No ad-hoc spacing or sizing on reusable components

Never apply ad-hoc padding/margin/gap/width/height to a reusable component via className, wrapper divs, or inline styles. Sizing is controlled by **variants** (CVA `size`/`variant`), not external classes.

When a component needs different sizing:
- If it has a variant system → extend it with a new value covering the needed size; ensure responsive-aware values.
- If it doesn't → create one, minimum `size` variants (`sm`/`md`/`lg`), using semantic tokens, tested at all breakpoints.
- Update DESIGN.md.

The only acceptable external spacing on a reusable component is layout-level spacing applied by a parent (e.g. `gap` on a flex/grid parent, margin on a layout wrapper) — controlling relationships *between* components, not the component's own dimensions.

### Rule 5: React Router navigation only

Never use `window.location.*` or raw `<a>` tags for in-app navigation — they cause full reloads and destroy in-memory state (Dev Toggle, React context, etc.). Always use `<Link>`, `useNavigate()`, or `<Navigate>`. The only acceptable raw `<a>` is for external links (with `target="_blank" rel="noopener noreferrer"`).

### Rule 6: All page/section copy goes through searchfit-seo

Never write UI copy from your own head. Applies to: headings, subheadings, body copy, CTAs, value props, hero text, empty-state messaging, error messages, marketing microcopy. (Trivial system labels like "Save", "Cancel", "Close" don't need this.)

**Copy gate (mandatory before any copy work, in both flows):**

1. STOP. Ask the user: *"What high-level ideas do you have for the copy here? Audience, key message, tone, themes or keywords you want to land?"*
2. Wait for the user's answer. Do not proceed without it.
3. Invoke `searchfit-seo:on-page-seo` with the user's input + brand-voice.md + page context. (For long-form pages: `searchfit-seo:content-brief`.)
4. Review the output for human tone — no AI slop, no buzzwords, no generic corporate phrasing, no thesaurus filler. If it doesn't pass that bar, re-prompt the SEO skill with the specific feedback.
5. Place the reviewed copy in the design.

**Pre-supplied direction does NOT satisfy the gate.** If the user pre-supplies a suggestion or instruction (e.g. *"change X to Y"*, *"make it punchier"*, *"the headline should mention price"*), the gate question still runs verbatim. The user's suggestion is **input** to the SEO skill, not a **substitute** for the gate. Do not rationalize *"they already gave me the direction, so the gate is implicitly satisfied"* — it isn't.

Bypassing this gate (writing copy yourself, skipping the user gate, skipping the SEO skill, treating user direction as a gate substitute, or "just tweaking a word") is a violation of the skill.

### Rule 7: Scope discipline

Build only the UI/UX for the feature being designed right now. No unrelated additions. Backend integrations are mocked (static data, setTimeout for async, local state). Only the React reference app is modified — never production code, except `DESIGN.md`, `brand-voice.md`, and `PRD.md` at the project root.

### Rule 8: Domain/business-logic gate

The PRD is the source of truth for business rules and user flows. Many design changes silently encode new business assumptions ("an item can have multiple owners now", "drafts can be shared", "this filter implies a new entity field"). If the design shifts what the product *does*, the PRD must be updated as part of the same task — not patched in later, not forgotten.

**Gate (mandatory at the start of every task, before planning, in both flows):**

1. STOP. Ask the user: *"Before I plan this — is this change introducing, modifying, or extending domain or business logic? Specifically: a new product capability, a new business rule or constraint, a new data entity or field that production must model, an altered or new step in a user flow, an additional case for an existing flow, or removal/replacement of an existing flow. If yes, I'll plan the PRD update alongside the design work."*
2. Wait for the user's answer. Do not proceed without it.
3. If **yes** → treat the PRD update as in-scope from the start. Phase 6 (PRD sync) is not optional and must appear in the plan you present in Flow A Step 2 / Flow B Step 4.
4. If **no** or **not sure** → proceed without planned PRD work. But during validation, re-evaluate against the PRD-sync trigger criteria below. If the implementation surfaced a business change the user didn't anticipate at the gate, raise it explicitly before declaring done — do not silently skip it.

Bypassing this gate (making prototype changes that imply new business rules without raising them) is a violation of the skill, even if the visual outcome is correct.

---

General quality (a11y to WCAG 2.1 AA, responsive testing methodology, animation timing & `prefers-reduced-motion`, latest UI/UX patterns, clean React/TS code) is owned by `frontend-design:frontend-design`. Don't duplicate it — invoke that skill.

## Visual validation

Screenshots from Prerequisites Step 4 are exploratory — they build the agent's mental model of the existing aesthetic. They are **not boundary-precise** and do **not** count as validation. Validation (Flow A Phase 5, Flow B Steps 2 and 6) requires fresh screenshots taken at the exact breakpoint boundaries below. Do not reuse prerequisite shots to skip this step.

After every implementation:

1. Screenshot at desktop, then at every breakpoint boundary: just-before and just-after each defined Tailwind breakpoint, plus 320px and 1920px.
2. At every viewport, verify: no clipping, no overflow (no unintended horizontal scroll), proper alignment, no layout collapse (0-height sections, overlapping elements), readable typography.
3. Compare against the existing app aesthetic — same tokens, patterns, visual language.
4. Check focus states and color contrast on key text.
5. Cross-reference DESIGN.md.

If any check fails, fix before presenting.

## PRD sync

This phase **executes** the answer to the Rule 8 gate. If Rule 8 was answered *yes* at task start, the PRD update is in scope and runs here. If it was answered *no*, run through the trigger criteria once more — if validation surfaced a business change you didn't anticipate, raise it with the user and update the PRD now rather than letting it slip.

If `PRD.md` exists, update it ONLY when the change introduces or modifies a **business user flow** — a change that would result in new or altered production user stories.

**Update for:** new product capabilities, new business rules/constraints implied by the UI, new data entities or fields production must model, altered flow steps/states/branching, removal or replacement of existing flows.

**Do NOT update for:** visual/cosmetic changes, UI polish, component architecture decisions, information hierarchy that doesn't change what data is shown, responsive behavior, animations, empty/loading state styling.

**Rule of thumb:** if the sentence would still make sense in a PRD for a product built with a completely different tech stack and design system, it belongs. Otherwise it doesn't.

When triggered, spawn a **background sub-agent** (Agent tool) using the prompt in `references/prd-sync-prompt.md`, passing a clear summary of the business-level change. The sub-agent decides whether an update is warranted and makes targeted edits. Don't block on it.

When in doubt, don't update. A missing PRD line can be added later; a PRD cluttered with visual or technical detail actively harms the user stories written from it.

## Session end / PR

Treat phrases like "let's end this session", "let's create the PR", or any clear equivalent as an explicit PR request. The PR must include all React reference app changes from the session and any `PRD.md` edits. PR description: what changed in the reference app + any PRD updates (or a short note that none was needed).

## Self-check before "done"

- [ ] Rule 8 gate (domain/business-logic) was run at task start
- [ ] Visually validated at all breakpoint boundaries
- [ ] Only semantic tokens used (no ad-hoc values)
- [ ] All copy went through the user-input gate + `searchfit-seo:on-page-seo`
- [ ] `frontend-design:frontend-design` was invoked at the planning/critique step
- [ ] DESIGN.md updated if the design system changed
- [ ] PRD synced (background sub-agent) if Rule 8 was *yes*, or if validation surfaced a business change; otherwise skipped
- [ ] Only the React reference app was modified (plus DESIGN.md / brand-voice.md / PRD.md at root)
- [ ] If the user signaled session end, a PR was created including reference-app changes and any PRD edits
