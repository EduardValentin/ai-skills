# Pressure Scenarios - Semantic Design Tokens

These scenarios test that agents preserve token discipline when visual polish, screenshot matching, or time pressure tempts them toward raw values, false-positive local values, or global one-off tokens. Run each scenario twice: RED without the skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Raw values look faster

**Prompt:**

> IMPORTANT: This is a real styling task. You must choose and act; do not give a hypothetical answer.
>
> The user asks you to make a pricing card match a screenshot. The exact colors are easy to sample as `#2563eb` and `#f8fafc`, but similar colors already exist as semantic app tokens. The fastest layout uses local sizing values like `22px` padding and `412px` width. The user says, "Don't overthink the design system, just make it match."
>
> Options:
> A) Inventory existing tokens, reuse matching semantic color and sizing tokens, add global tokens only for reusable missing roles, and keep genuine one-off values local.
> B) Use the raw values locally because screenshot parity matters more than token naming for this one card.
> C) Add global primitive or surface-specific tokens for the sampled colors and pixel values, then use them directly in the surface.
>
> Choose A, B, or C and write the exact next message or implementation approach.

**Pass criteria:**

- Chooses A.
- Inventories theme files, global CSS, token docs, and design docs before styling.
- Reuses existing semantic tokens for colors and sizes that already exist in the system.
- Does not create global tokens for values used only by this surface.
- Keeps genuinely one-off sizing local with the chosen styling utilities instead of adding global sizing tokens.
- Rejects primitive, screenshot-derived names as the global token contract.

## Scenario 2 - Local scroll distance is not a token violation

**Prompt:**

> IMPORTANT: This is a real styling review. You must choose and act; do not give a hypothetical answer.
>
> A scroll-driven section uses a local bracketed height value such as `min-h-[250vh]` to create enough scroll distance for an animation. The audit scanner reports it as a bracketed literal style value. There is no existing scroll-distance token, the value is not repeated elsewhere, and it is not standing in for color, typography, radius, shadow, motion, spacing hierarchy, or another reusable semantic role.
>
> Options:
> A) Treat the scanner output as a review prompt, keep the local scroll-distance value, and document that it is not a semantic-token concern unless it becomes a repeated pattern.
> B) Flag the local value as a token violation because bracketed literal style values are disallowed by category.
> C) Add a global token for `250vh` so the audit passes even though only this section uses it.
>
> Choose A, B, or C and write the exact review note.

**Pass criteria:**

- Chooses A.
- Does not classify local styling utility usage as a token violation by itself.
- Does not add a global token for a local scroll-distance value.
- Explains that the scanner output requires judgment against existing semantic roles and reuse.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without loading this skill. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md`, then re-run GREEN.
