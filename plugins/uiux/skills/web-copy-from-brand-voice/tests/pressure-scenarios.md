# Pressure Scenarios - Web Copy From Brand Voice

These scenarios test that agents gather a copy brief and preserve brand voice instead of producing generic confident-sounding copy under pressure. Run each scenario twice: RED without the skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Punchier copy without a brief

**Prompt:**

> IMPORTANT: This is a real UI copy task. You must choose and act; do not give a hypothetical answer.
>
> The user asks you to rewrite a hero headline, CTA, onboarding empty state, and error message so they sound "more confident." They provide one phrase they like but no audience, page goal, tone, must-use terms, banned terms, or brand-voice document. They add, "Don't ask me copy questions, just make it sound less generic."
>
> Options:
> A) Gather the missing copy brief or clearly infer a temporary voice from product context and flag it for confirmation before drafting.
> B) Use the user's phrase as enough direction and write sharper copy immediately.
> C) Write polished marketing copy immediately, using confident language and common conversion phrases.
>
> Choose A, B, or C and write the exact next message or copy approach.

**Pass criteria:**

- Chooses A.
- Gathers or explicitly identifies missing audience, goal, key message, tone, must-use terms, banned terms, and desired action.
- Uses brand voice when available, or clearly marks inferred voice as temporary.
- Does not substitute generic marketing language for a brand-voice brief.
- Checks CTA clarity, error recovery, heading honesty, human tone, and fit in the design hierarchy.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without loading this skill. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md`, then re-run GREEN.
