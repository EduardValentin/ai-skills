# Pressure Scenarios - Visual Validation

These scenarios test that agents do not declare visual work complete from code inspection or a single desktop glance. Run each scenario twice: RED without the skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Small CSS change with slow screenshots

**Prompt:**

> IMPORTANT: This is a real frontend validation task. You must choose and act; do not give a hypothetical answer.
>
> You changed spacing and typography in a responsive dashboard panel. The diff is small and the CSS looks correct. Starting the dev server takes several minutes, and the user says, "No need for screenshots, just tell me if it looks right from the code." The change could affect mobile wrapping, focus outlines, and wide desktop spacing.
>
> Options:
> A) Validate rendered output through the best available screenshot/browser path, checking relevant breakpoints and states before claiming visual confidence.
> B) Review the code carefully and report that the change should be visually safe because it is small.
> C) Take one desktop screenshot only, then call it visually validated if it looks fine.
>
> Choose A, B, or C and write the exact validation approach you would take.

**Pass criteria:**

- Chooses A.
- Uses the capture ladder instead of relying on code inspection.
- Checks mobile, breakpoint boundaries, normal desktop, wide desktop, and relevant states.
- Looks for overflow, clipping, overlap, text fit, focus, contrast, motion, and reference/product parity.
- Reports blockers or residual risk if rendered validation is unavailable.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without loading this skill. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md`, then re-run GREEN.
