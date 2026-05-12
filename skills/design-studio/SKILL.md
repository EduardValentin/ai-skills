---
name: design-studio
description: Use when doing UI/UX work on a React reference app that mirrors a production codebase — building new pages/components/sections, auditing existing pages for clarity/decluttering/visitor fit, fixing visual bugs, or extending the design system.
---

# Design Studio

Project-specific overlay for design work on a React + Tailwind reference app. General design quality (accessibility, responsive testing, animation, visual polish, latest patterns) is delegated to the `frontend-design` skill. Page copy is delegated to the `on-page-seo` skill. This skill enforces the project layer: setup, semantic tokens, design-system extension rules, the two scenario flows, and PRD sync.

**Deadlines do not relax the rules.** User-imposed time pressure ("I need this in 20 minutes", "the demo is at the top of the hour") does not authorize skipping the copy gate, the `frontend-design` invocation, semantic-token discipline, or visual validation. If the timeline cannot accommodate compliance, surface the tradeoff to the user (do it right and miss the deadline / scaffold with placeholders + flag for proper pass / push the deadline) rather than silently cut corners.

**Violating the letter of the rules is violating the spirit of the rules.** "I followed the intent" is not a defense for skipping a named step (the copy gate, Rule 8, the `frontend-design` invocation, visual validation, the user-approval beat in either flow). If a rule names a step, the step runs.

## Requires

- Ability to execute shell commands and read/write files in the working tree.
- A Node.js runtime on `PATH` (the reference app is a JS/TS project).
- Ability to start a local HTTP dev server and observe its output.
- Visual-output capture for the running app — see `references/browser-fallback.md` for the capability ladder (native screenshot → browser-automation via shell → user-provided screenshots).
- Subagent dispatch — used for the context digest, PRD generation, and PRD sync. If your agent cannot dispatch subagents, the affected steps note an inline fallback (the main agent runs the same prompt itself, accepting the context cost).
- Read access to the project root for `DESIGN.md`, `brand-voice.md`, `PRD.md`.
- Two referenced skills, with fallbacks if either is unavailable in the current agent:
  - `frontend-design` — high-quality design code. Fallback: apply WCAG 2.1 AA accessibility, responsive testing methodology, animation timing with `prefers-reduced-motion`, and current UI/UX patterns inline.
  - `on-page-seo` (with `content-brief` as a long-form fallback) — copy generation aligned with brand voice and SEO. Fallback: write the copy yourself per `brand-voice.md` and the user's gate answer, then surface for explicit user approval before placement.

## Required sub-skills

These MUST be invoked at the points specified. Do not paraphrase, summarize, or skip. If your agent does not expose a named skill, apply its fallback from the Requires block.

| Sub-skill | When to invoke |
|---|---|
| `frontend-design` | Before implementing any visual change (Flow A Step 3 "Plan + design guardrails"; Flow B Step 4 "Critique") |
| `on-page-seo` | Whenever copy is created or rewritten — AFTER the copy gate (Rule 6) |
| `content-brief` | Fallback for long-form pages only (blog post, guide, deep article) |

## Prerequisites

Run in order. Do not skip.

1. **Setup + locate the reference app** — run `<skill-dir>/scripts/prepare-design-studio.sh --project-root <abs-path>`. The script auto-detects the React app under `<project-root>/designs/`; pass `--app-root` only if you already know the path or auto-detection picks the wrong one. The script handles Node version, package manager, install, and writes a `.claude/launch.json` for agents that consume that format. If it fails to find a React `package.json`, ask the user for the path. Don't hand-create launch config or install deps manually unless the script fails. Agents without `launch.json` semantics can ignore that output and start the dev server directly with `<package-manager> run dev` in the app root.

2. **Project-context digest** — dispatch a subagent using the prompt in `references/context-digest-prompt.md`. Pass the project root, the located reference app root, and a one-line summary of the current task (used to scope which PRD sections come back). The subagent returns ONE structured markdown digest with these sections: **Design tokens**, **Components**, **Routes**, **Brand voice highlights**, **PRD slice relevant to current task**, **Visual aesthetic signals**, **Notable dependencies**, **Mismatches**, **Missing**.

   This subagent replaces inline reads of `DESIGN.md`, `brand-voice.md`, `PRD.md`, the Tailwind theme, the component inventory, the router, and `package.json`. Do not read those files directly in the main agent — the digest is your working reference for the session.

   **Fallback (no subagent dispatch available):** run the same prompt as the main agent and produce the digest inline, accepting the context cost. Treat the inline-produced digest as the working reference for the rest of the session.

   **On return, before proceeding:**
   - If `Missing` is non-empty, handle each item:
     - `DESIGN.md` missing → ask the user for design direction and create DESIGN.md before any design work.
     - `brand-voice.md` missing → note it; default to clear, direct, human language for any copy gate.
     - `PRD.md` missing → see `references/prd-generation.md` and offer to generate one.
     - Tailwind theme or components directory missing → ask the user where they live, then re-dispatch the digest.
   - If `Mismatches` is non-empty, raise each one with the user. **Conflict rule:** the Tailwind theme is authoritative — flag the mismatch and offer to update DESIGN.md as part of the current task.

   **Re-dispatch (or re-run inline) when** (a) any source artifact has been edited since the last digest, or (b) the active task shifts enough that the PRD slice no longer covers it (use a refreshed task summary).

3. **Visual context** — start the dev server, navigate to the main pages, and capture screenshots. Then write down (in the working response) a 3-to-5-bullet aesthetic summary covering: color rhythm (palette breadth, accent usage), spacing rhythm (base unit, typical gaps), type hierarchy (display vs body weighting), density / whitespace tendency, dominant motion/interaction patterns. This is the rendered counterpart to the digest's *Visual aesthetic signals* — confirm the signals or flag where the rendered app diverges from what the tokens implied. If no visual-output capture is available natively, see `references/browser-fallback.md`.

## The two flows

Pick one based on the user's request. Use the triage table; if still unclear, ask.

| User says... | Flow |
|---|---|
| "Build a new pricing page" / "Add a comparison section" / "Extend the design system with a callout component" | **A — Build from scratch** |
| "Make the dashboard less cluttered" / "Fix the mobile layout on /clients" / "Improve the empty-state copy on /onboarding" | **B — Audit existing** |
| Ambiguous (e.g. "improve the dashboard", "make the pricing page better") | **Ask first:** "Are you adding new sections, or refining what's already there?" |

### Flow A — Build from scratch

For new pages, components, sections, or design-system extensions.

1. **Understand** — clarify scope, identify affected pages/components/tokens, ask clarifying questions before any code.
2. **Domain/business-logic gate** — run the Rule 8 gate verbatim. Wait for the user's answer before continuing. Do not merge this into Step 1's clarifying questions.
3. **Plan + design guardrails** — invoke the `frontend-design` skill (or its inline fallback per the Requires block). Then describe what you'll build, list components to create/modify/reuse, identify any new tokens needed, describe responsive behavior. If Rule 8 answered *yes*, include the PRD update in the plan. Get explicit user approval before writing code.
4. **Copy gate (if any copy is involved)** — see Rule 6. Do not skip.
5. **Implement** — incrementally, one component/section at a time. Comply with all rules. Preview after each significant change.
6. **Validate** — see "Visual validation" below.
7. **Document + sync** — update DESIGN.md if the system was extended. Run PRD sync if business behavior changed.

### Flow B — Audit existing

For refining an existing page for a visitor segment, decluttering, fixing visual bugs, or improving SEO/copy on the page.

1. **Frame the audit** — ask the user: who is the audience, what is the goal (declutter / segment fit / bug fix / SEO / copy clarity), what does success look like?
2. **Domain/business-logic gate** — run the Rule 8 gate verbatim. Wait for the user's answer before continuing. Do not merge this into Step 1's framing questions.
3. **Capture current state** — screenshot the target page(s) at the breakpoint boundaries defined in "Visual validation" below.
4. **Critique** — invoke the `frontend-design` skill (or its inline fallback). Produce a written critique covering: information hierarchy, visual clutter, accessibility, responsive issues, visual bugs, copy clarity, and on-page SEO observations. Do not start changing code yet.

   **Delegate when:** the audit spans 3+ pages or covers all categories in depth. Dispatch a subagent with the screenshots, the digest from Prerequisites Step 2, and the user's audit goals; have it return the written critique. The main agent then ranks fixes in Step 5. For single-page or focused audits, run inline. If subagent dispatch is unavailable, always run inline.
5. **Propose ranked fixes** — list fixes ordered by impact. Get user approval on scope before changing code. If Rule 8 answered *yes*, include the PRD update in this plan.
6. **Apply fixes**:
   - Visual/structural changes — implement directly under the design rules.
   - **Copy changes** — see Rule 6. The copy gate applies here too. Never rewrite copy from your own head, even when "just fixing" a phrase.
7. **Re-validate** — re-screenshot at the same viewports and confirm fixes landed without regressions.
8. **Document + sync** — DESIGN.md if the system was extended; PRD only if business behavior changed.

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

### Rule 6: All page/section copy goes through the on-page-seo skill

Never write UI copy from your own head. Applies to: headings, subheadings, body copy, CTAs, value props, hero text, empty-state messaging, error messages, marketing microcopy. (Trivial system labels like "Save", "Cancel", "Close" don't need this.)

**Copy gate (mandatory before any copy work, in both flows):**

1. STOP. Ask the user: *"What high-level ideas do you have for the copy here? Audience, key message, tone, themes or keywords you want to land?"*
2. Wait for the user's answer. Do not proceed without it.
3. Invoke the `on-page-seo` skill with the user's input + `brand-voice.md` + page context. (For long-form pages: invoke `content-brief` instead.)
4. Review the output for human tone — no AI slop, no buzzwords, no generic corporate phrasing, no thesaurus filler. If it doesn't pass that bar, re-prompt the skill with the specific feedback.
5. Place the reviewed copy in the design.

**Fallback if the `on-page-seo` skill is unavailable in the current agent:** after the user's gate answer, write the copy yourself anchored on `brand-voice.md`, the user's stated audience/message/tone, and the page context. Apply the same human-tone review in step 4. Surface the draft for explicit user approval before placing — the user approval substitutes for the named-skill gate, not the user-input gate above.

**Pre-supplied direction does NOT satisfy the gate.** If the user pre-supplies a suggestion or instruction (e.g. *"change X to Y"*, *"make it punchier"*, *"the headline should mention price"*), the gate question still runs verbatim. The user's suggestion is **input** to the SEO skill, not a **substitute** for the gate. Do not rationalize *"they already gave me the direction, so the gate is implicitly satisfied"* — it isn't.

Bypassing this gate (writing copy yourself, skipping the user gate, skipping the SEO skill, treating user direction as a gate substitute, or "just tweaking a word") is a violation of the skill.

### Rule 7: Scope discipline

Build only the UI/UX for the feature being designed right now. No unrelated additions. Backend integrations are mocked (static data, setTimeout for async, local state). Only the React reference app is modified — never production code, except `DESIGN.md`, `brand-voice.md`, and `PRD.md` at the project root.

### Rule 8: Domain/business-logic gate

The PRD is the source of truth for business rules and user flows. Many design changes silently encode new business assumptions ("an item can have multiple owners now", "drafts can be shared", "this filter implies a new entity field"). If the design shifts what the product *does*, the PRD must be updated as part of the same task — not patched in later, not forgotten.

**Gate (mandatory at the start of every task, before planning, in both flows):**

1. STOP. Ask the user: *"Before I plan this — is this change introducing, modifying, or extending domain or business logic? Specifically: a new product capability, a new business rule or constraint, a new data entity or field that production must model, an altered or new step in a user flow, an additional case for an existing flow, or removal/replacement of an existing flow. If yes, I'll plan the PRD update alongside the design work."*
2. Wait for the user's answer. Do not proceed without it.
3. If **yes** → treat the PRD update as in-scope from the start. The PRD sync phase is not optional and must appear in the plan you present in Flow A Step 3 / Flow B Step 5.
4. If **no** or **not sure** → proceed without planned PRD work. But during validation, re-evaluate against the PRD-sync trigger criteria below. If the implementation surfaced a business change the user didn't anticipate at the gate, raise it explicitly before declaring done — do not silently skip it.

Bypassing this gate (making prototype changes that imply new business rules without raising them) is a violation of the skill, even if the visual outcome is correct.

---

General quality (a11y to WCAG 2.1 AA, responsive testing methodology, animation timing & `prefers-reduced-motion`, latest UI/UX patterns, clean React/TS code) is owned by the `frontend-design` skill. Don't duplicate it — invoke that skill (or apply the inline fallback declared in the Requires block).

## Visual validation

**Breakpoint set (canonical):** desktop, every breakpoint boundary — just-before and just-after each defined Tailwind breakpoint — plus 320px and 1920px. Every other section that says "the breakpoint boundaries defined in Visual validation" means this list.

Screenshots from Prerequisites Step 3 are exploratory — they build the agent's mental model of the existing aesthetic. They are **not boundary-precise** and do **not** count as validation. Validation (Flow A Step 6, Flow B Steps 3 and 7) requires fresh screenshots taken at the canonical breakpoint set above. Do not reuse prerequisite shots to skip this step.

After every implementation:

1. Screenshot at the canonical breakpoint set.
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

When triggered, spawn a **background subagent** using the prompt in `references/prd-sync-prompt.md`, passing a clear summary of the business-level change. The subagent decides whether an update is warranted and makes targeted edits. Don't block on it.

**Fallback (no subagent dispatch available):** run the same prompt yourself synchronously after the main design work is complete — read `PRD.md` in full, decide whether an update is warranted per the criteria below, and apply targeted edits inline. Surface the result to the user (PRD updated / no update needed).

When in doubt, don't update. A missing PRD line can be added later; a PRD cluttered with visual or technical detail actively harms the user stories written from it.

## Session end / PR

Treat phrases like "let's end this session", "let's create the PR", or any clear equivalent as an explicit PR request. The PR must include all React reference app changes from the session and any `PRD.md` edits. PR description: what changed in the reference app + any PRD updates (or a short note that none was needed).

## Self-check before "done"

- [ ] Rule 8 gate (domain/business-logic) was run at task start
- [ ] Visually validated at all breakpoint boundaries
- [ ] Only semantic tokens used (no ad-hoc values)
- [ ] All copy went through the user-input gate + the `on-page-seo` skill (or its inline fallback with explicit user approval)
- [ ] The `frontend-design` skill was invoked at the planning/critique step (or its inline fallback applied)
- [ ] DESIGN.md updated if the design system changed
- [ ] PRD synced (background subagent, or the inline fallback) if Rule 8 was *yes*, or if validation surfaced a business change; otherwise skipped
- [ ] Only the React reference app was modified (plus DESIGN.md / brand-voice.md / PRD.md at root)
- [ ] If the user signaled session end, a PR was created including reference-app changes and any PRD edits
