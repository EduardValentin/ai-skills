# Pressure Scenarios - Design Studio

These scenarios test that the skill stays a compact project overlay: it prepares the reference app, works from a digest, protects source-of-truth docs, and requires rendered evidence.

## Scenario 1 - Large Reference App Under Time Pressure

Prompt:

> The user asks for a dashboard redesign in a React reference app. The project has a large DESIGN.md, brand-voice.md, PRD.md, theme files, routes, and 80 components. They say, "Just skim everything and start." You need project context before design work.
>
> Options:
> A) Run the setup script, produce a compact task-scoped digest, keep raw docs and broad inventories out of active context, then use targeted reads while implementing.
> B) Read DESIGN.md, brand-voice.md, PRD.md, routes, theme files, and the whole component tree directly in the main response because that is faster.
> C) Skip the digest and infer the design system from the target dashboard files only.
>
> Choose A, B, or C and write the next action.

Pass criteria:

- Chooses A.
- Runs or plans `prepare-design-studio.sh`.
- Uses the digest structure.
- Avoids loading broad raw source into active context.
- Does not treat time pressure as a reason to skip context.

## Scenario 2 - Pure Visual Change

Prompt:

> The user asks to fix mobile spacing and improve hierarchy on a reference-app page. No product capability, rule, data, permission, or flow changes.
>
> What documentation, if any, should be updated?

Pass criteria:

- Updates `DESIGN.md` only if reusable design-system rules changed.
- Does not update `PRD.md` for visual styling, layout, or responsive behavior.
- Reports visual evidence required before completion.

## Scenario 3 - Missing PRD

Prompt:

> No PRD.md exists. The user agrees to generate one from the current React reference app before adding a new feature flow.
>
> What do you do next?

Pass criteria:

- Analyzes product behavior, not implementation details.
- Captures primary-route screenshots or reports the visual-capture blocker.
- Writes PRD content from observed behavior only.
- Marks ambiguous behavior as `[TBD]`.
