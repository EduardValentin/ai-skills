# Context Digest — Subagent Prompt

Use this template when dispatching a subagent for project-context gathering at the start of a design-studio session (Prerequisites Step 2). The subagent reads the project artifacts and returns a single structured digest so the main agent's context stays clean. If subagent dispatch is unavailable in the current agent, the main agent runs the same prompt itself inline — the prompt body below is identical either way.

**Inputs to fill in before dispatching (or before running inline):**

- `<project-root>` — absolute path to the project root.
- `<app-root>` — absolute path to the located React reference app.
- `<task-summary>` — one-line description of what the user is asking for in *this* task. Used to scope which PRD sections come back.

---

> **Task: Produce a structured context digest for a design-studio session**
>
> You are gathering project context so the main agent can do design work without reading raw files. Return ONE markdown document in the exact structure below. Do not include code snippets, file paths, or implementation chatter — only the structured fields. If a field has no data, return the literal string `None` for that field.
>
> **Inputs:**
>
> - Project root: `<project-root>`
> - Reference app root: `<app-root>`
> - Current task summary: `<task-summary>`
>
> **Files / sources to read:**
>
> - `<project-root>/DESIGN.md`
> - `<project-root>/brand-voice.md`
> - `<project-root>/PRD.md`
> - Tailwind theme: `@theme` block(s) in `<app-root>/src/**/*.css` (Tailwind v4) OR `<app-root>/tailwind.config.{ts,js,cjs,mjs}` (Tailwind v3).
> - Component inventory: `<app-root>/src/components/` and any sibling component directories.
> - Router: the top-level `<Routes>` / route registry under `<app-root>/src/`.
> - `<app-root>/package.json`
>
> If any of these is absent, do not error — record it under the `Missing` section at the end.
>
> **Required output structure (use these exact headings, in this order):**
>
> ## Design tokens
>
> List every semantic token, grouped by category. One token per line: `--token-name: value — one-line purpose`. Categories in this order:
>
> - Colors
> - Spacing
> - Typography (font families, sizes with line heights, weights)
> - Radii
> - Shadows
> - Motion / transitions
> - Other (any custom category that actually exists)
>
> For Tailwind v3, treat extended `theme.extend.*` keys as tokens. Skip default Tailwind values that haven't been customized — those aren't part of the project's vocabulary.
>
> ## Components
>
> One row per component. Format:
>
> `**ComponentName** — one-line purpose. Variants: <CVA variant axes with their values, comma-separated, or "none">. Key props: <non-style props only, comma-separated, or "none">.`
>
> Cover every component file under the component directories. Skip purely internal helpers that are single-use sub-components inside another file.
>
> ## Routes
>
> One line per route: `<path> → <PageComponent> (<audience-or-role-if-implied>)`. Omit the parenthetical when no role distinction exists.
>
> ## Brand voice highlights
>
> 3 to 5 bullets capturing the most actionable rules from `brand-voice.md`:
>
> - Voice/tone in one phrase (e.g. "direct, second-person, no jargon").
> - Specific word bans or word preferences.
> - Structural rules (sentence length, headline pattern, CTA style).
> - Anything else load-bearing for copy decisions.
>
> If `brand-voice.md` is missing, return `None` here and add it to the Missing section.
>
> ## PRD slice relevant to current task
>
> Read `PRD.md` in full. Return ONLY the sections that touch the pages, flows, entities, or features mentioned in `<task-summary>`. Use the PRD's own headings/labels — quote or tightly summarize rather than paraphrasing freely. Include cross-referenced flows that the task implicates.
>
> If the task summary is vague (e.g. "general design refresh"), return only the Product Summary and Core User Types sections, and add a note that a tighter task description would yield a tighter slice.
>
> If `PRD.md` is missing, return `None` here and add it to the Missing section.
>
> ## Visual aesthetic signals (file-based only)
>
> 3 to 5 bullets inferred from tokens, the global stylesheet, and component defaults:
>
> - Color rhythm (palette breadth, contrast level, accent usage).
> - Spacing rhythm (base unit, typical gaps).
> - Type hierarchy (display vs body weighting).
> - Density / whitespace tendency (from default paddings, container widths).
> - Motion (defined transitions, `prefers-reduced-motion` handling).
>
> These are file-derived signals. The main agent validates them against screenshots in the next prerequisites step.
>
> ## Notable dependencies
>
> Bullet list of versions that affect design work: Tailwind (state v3 vs v4 explicitly), React Router (v6 vs v7), CVA presence, framer-motion or other animation library, shadcn/ui or radix-ui families if present, and anything else that materially shapes design choices. Do not list every dependency.
>
> ## Mismatches
>
> Cases where two sources disagree. Examples:
>
> - DESIGN.md references `--accent` but the theme defines `--highlight`.
> - The components directory has a `Banner` component but DESIGN.md is silent on it.
> - PRD references a flow that has no corresponding route.
>
> Return `None` if there are no mismatches.
>
> ## Missing
>
> List artifacts that were expected but absent: `DESIGN.md` missing, `brand-voice.md` missing, `PRD.md` missing, no Tailwind theme found, no components directory found, etc. The main agent will handle user prompts for each. Return `None` if everything was present.
>
> ---
>
> **Output rules:**
>
> - Use the exact headings above, in the exact order.
> - No file paths, no React/TS code, no implementation detail.
> - Tight bullets — one line each where possible.
> - Do not invent content. If a section has no data, return `None`.
> - Aim for under 1500 tokens of output total.

---

## After the digest is produced

The main agent should:

1. **Handle Missing first.** If `Missing` is non-empty, address each item before proceeding:
   - `DESIGN.md` missing → ask the user for design direction and create DESIGN.md before any design work begins.
   - `brand-voice.md` missing → note it; default to clear, direct, human language for any copy gate.
   - `PRD.md` missing → see `prd-generation.md` and offer to generate one.
   - Tailwind theme missing or components directory missing → ask the user where they live, then re-run the digest.
2. **Surface Mismatches.** Raise each one with the user and apply the conflict rule: the Tailwind theme is authoritative; offer to update DESIGN.md as part of the current task.
3. **Use the digest as the working reference** for the rest of the session. Do not re-read the underlying files in the main agent.
4. **Re-run the digest** (via subagent dispatch when available, otherwise inline) when (a) any of the source artifacts has been edited since the last digest, or (b) the active task shifts enough that the PRD slice no longer covers it. Pass a refreshed `<task-summary>` in case (b).
