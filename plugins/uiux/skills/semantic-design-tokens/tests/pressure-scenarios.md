# Pressure Scenarios - Semantic Design Tokens

These scenarios test that agents preserve token discipline when visual polish, screenshot matching, or time pressure tempts them toward raw values or global one-off tokens. Run each scenario twice: RED without the skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Raw values look faster

**Prompt:**

> IMPORTANT: This is a real styling task. You must choose and act; do not give a hypothetical answer.
>
> The user asks you to make a pricing card match a screenshot. The exact colors are easy to sample as `#2563eb` and `#f8fafc`, but similar colors already exist as semantic app tokens. The fastest layout uses one-off Tailwind sizing values like `p-[22px]` and `w-[412px]`. The user says, "Don't overthink the design system, just make it match."
>
> Options:
> A) Inventory existing tokens, reuse matching semantic color and sizing tokens, add global tokens only for reusable missing roles, keep genuine one-off sizing local, and use component-scoped color tokens only for genuinely unique component colors.
> B) Use the raw values locally because screenshot parity matters more than token naming for this one card.
> C) Add global primitive or component-specific tokens for the sampled colors and pixel values, then use them directly in the component.
>
> Choose A, B, or C and write the exact next message or implementation approach.

**Pass criteria:**

- Chooses A.
- Inventories theme/global CSS/component variants before styling.
- Reuses existing semantic tokens for colors and sizes that already exist in the system.
- Does not create global component-specific tokens for values used only by this component.
- Allows component-scoped color tokens only for genuinely unique one-off component colors.
- Keeps genuinely one-off sizing local with the chosen styling utilities instead of adding global sizing tokens.
- Rejects primitive, screenshot-derived names as the global token contract.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without loading this skill. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md`, then re-run GREEN.
