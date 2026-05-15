# Pressure Scenarios - Reusable UI Components

These scenarios test that agents make deliberate reuse, variant, and component-boundary decisions instead of hiding duplication behind one-off markup. Run each scenario twice: RED without the skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Duplicate cards feel faster

**Prompt:**

> IMPORTANT: This is a real component design task. You must choose and act; do not give a hypothetical answer.
>
> The user asks you to add a `MetricCard`-like block to one dashboard and a compact version to another page. There is an existing card component nearby, but it is not an exact visual match. A teammate says, "Just duplicate the JSX twice; we can componentize later if it repeats again." The second version needs different density and a slightly different footer slot.
>
> Options:
> A) Inspect nearby components, decide whether the role matches, then reuse directly, extend with variants/slots, or create a separate role-specific component.
> B) Duplicate the markup because there are only two instances and speed matters.
> C) Add a generic `CardBlock` with many boolean props so both cases can be forced through one component.
>
> Choose A, B, or C and write the exact component decision you would make next.

**Pass criteria:**

- Chooses A.
- Inventories nearby components before creating new UI.
- Uses role and interaction model to choose reuse, variant extension, or a separate component.
- Avoids generic names and boolean-prop piles.
- Keeps page-specific data fetching, routing, analytics, and business logic outside reusable UI components.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without loading this skill. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md`, then re-run GREEN.
