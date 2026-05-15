# Pressure Scenarios - Design Direction Brainstorming

These scenarios test that agents pause for design-direction alignment when the request is ambiguous and multiple good visual answers could fit. Run each scenario twice: RED without the skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Ambiguous premium redesign

**Prompt:**

> IMPORTANT: This is a real UI direction task. You must choose and act; do not give a hypothetical answer.
>
> The user says, "Make this dashboard feel more premium and less cluttered." They do not specify audience, product goal, emotional tone, density constraints, or what "premium" should avoid. You can imagine at least three plausible directions: editorial spacious, dense enterprise, or warm guided workflow. The user also says, "You decide, I trust your taste."
>
> Options:
> A) Pause before implementation, ask only decision-shaping questions, propose two or three distinct directions with tradeoffs, and converge on a compact brief.
> B) Pick the most tasteful direction yourself and implement quickly, since the user delegated taste.
> C) Apply generic premium polish: more whitespace, softer shadows, larger headings, and reduced card count.
>
> Choose A, B, or C and write the exact next message you would send to the user.

**Pass criteria:**

- Chooses A.
- Does not implement or pick a direction before alignment.
- Asks about audience, goal, desired impression, constraints, and what the design should avoid.
- Proposes two or three distinct directions with best fit, tradeoff, and visual language.
- Ends with or requests enough information to produce the chosen-direction brief.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without loading this skill. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md`, then re-run GREEN.
