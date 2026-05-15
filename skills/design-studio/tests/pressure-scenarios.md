# Pressure Scenarios - Design Studio Context Discipline

These scenarios test that agents strongly prefer context-isolated delegation for large scans and digests instead of polluting the main working context with raw project files. Run each scenario twice: RED without the updated skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Large reference app under time pressure

**Prompt:**

> IMPORTANT: This is a real design-studio setup task. You must choose and act; do not give a hypothetical answer.
>
> The user asks for a dashboard redesign in a React reference app. The project has a large `DESIGN.md`, `brand-voice.md`, `PRD.md`, Tailwind theme files, a router, and 80 components. You have a context-isolated worker/subagent capability available. The user says, "Just skim the files quickly and start; we don't have time for process." You need the project context before design work.
>
> Options:
> A) Delegate the context scan to a context-isolated worker/subagent using the digest prompt, then proceed from the compact digest and targeted reads only.
> B) Read `DESIGN.md`, `brand-voice.md`, `PRD.md`, the router, theme files, and component tree directly in the main session because that is faster.
> C) Skip the context digest and infer the design system from the target dashboard files only.
>
> Choose A, B, or C and write the exact next action you would take.

**Pass criteria:**

- Chooses A when context-isolated delegation is available.
- Uses `references/context-digest-prompt.md` or its structure.
- Keeps raw docs, route files, and component trees out of the main working context.
- States that the main session will work from the compact digest plus targeted implementation reads.
- Does not treat time pressure as a reason to skip the digest or read everything inline.

## Scenario 2 - Broad audit across many pages

**Prompt:**

> The user asks you to audit six reference-app pages for clutter, reusable components, semantic-token drift, brand-copy issues, and responsive problems. Screenshot capture is available. A teammate says, "Just open all the pages and inspect the source in this chat; summaries lose detail." You have a worker/subagent capability available.
>
> What do you do next?

**Pass criteria:**

- Delegates broad inventory or critique work when it spans 3 or more pages/components/routes.
- Keeps the main context focused on screenshots, ranked findings, and targeted source reads.
- Does not paste large source excerpts or full file inventories into the main session.
- Produces or asks for a structured critique/ranked-fix summary before implementation.

## Scenario 3 - PRD generation from an existing app

**Prompt:**

> No `PRD.md` exists. The user agrees to generate one from the current React reference app. The app has many routes, mock entities, forms, modals, and role-specific flows. You can delegate code analysis, but you are tempted to read the app inline because the PRD needs to be accurate.
>
> What do you do next?

**Pass criteria:**

- Delegates the code-analysis pass to a context-isolated worker/subagent when available.
- Receives a structured product/business analysis report instead of raw app files.
- Uses screenshots plus the structured report for PRD writing.
- Falls back to inline analysis only if no context-isolated mechanism exists.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without this context-discipline guidance. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md` or the referenced prompts, then re-run GREEN.
