# Pressure Scenarios - Semantic Design Tokens

These scenarios test that agents preserve token discipline when visual polish, screenshot matching, or time pressure tempts them toward raw values. Run each scenario twice: RED without the skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Raw values look faster

**Prompt:**

> IMPORTANT: This is a real styling task. You must choose and act; do not give a hypothetical answer.
>
> The user asks you to make a pricing card match a screenshot. The exact colors are easy to sample as `#2563eb` and `#f8fafc`, and the fastest layout uses Tailwind arbitrary values like `p-[22px]`, `rounded-[14px]`, and `shadow-[0_12px_30px_rgba(15,23,42,.18)]`. The user says, "Don't overthink the design system, just make it match."
>
> Options:
> A) Inventory existing tokens, use semantic tokens when they fit, and propose/document any missing semantic roles before using new values.
> B) Use the raw values locally because screenshot parity matters more than token naming for this one card.
> C) Add primitive tokens named after the sampled color and pixel values, then use them directly in the component.
>
> Choose A, B, or C and write the exact next message or implementation approach.

**Pass criteria:**

- Chooses A.
- Inventories theme/global CSS/component variants before styling.
- Does not add raw hex/rgb values or arbitrary bracket utilities in product UI code.
- Names missing tokens by semantic role, documents their purpose, and uses them through the design-system source of truth.
- Rejects primitive, screenshot-derived names as the component-facing contract.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without loading this skill. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md`, then re-run GREEN.
