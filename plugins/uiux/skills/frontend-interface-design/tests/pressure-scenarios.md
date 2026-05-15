# Pressure Scenarios - Frontend Interface Design

These scenarios test that agents keep semantic HTML, accessibility, responsive behavior, and state coverage as first-order design constraints under delivery pressure. Run each scenario twice: RED without the skill, then GREEN with the skill loaded. Do not fabricate responses from the orchestrating agent.

## Scenario 1 - Polished page under deadline pressure

**Prompt:**

> IMPORTANT: This is a real frontend design task. You must choose and act; do not give a hypothetical answer.
>
> The user asks you to build a polished settings page quickly. They say, "Just make it look premium; we can clean up accessibility later." The design needs toggles, a destructive action, loading, empty, and error states. The existing app uses React components, but there is no provided mockup.
>
> Options:
> A) Start from semantic structure, accessible names, keyboard behavior, focus states, responsive constraints, and then style the page.
> B) Move fast with visually polished div-based markup, then add ARIA/focus fixes once the layout looks good.
> C) Build only the happy path first because loading/error/empty states can be added in a follow-up.
>
> Choose A, B, or C and write the exact next design/implementation approach you would take.

**Pass criteria:**

- Chooses A.
- Treats semantic HTML, keyboard behavior, accessible names, focus, contrast, and responsive constraints as foundational.
- Includes loading, empty, error, disabled, hover/pressed, and destructive-action states in the design scope.
- Does not defer accessibility or state coverage to a later pass.

## RED-GREEN Procedure

1. RED: run the scenario in an isolated session without loading this skill. Capture the choice and rationalization verbatim.
2. GREEN: run the same scenario with this skill loaded. Verify the pass criteria.
3. REFACTOR: if the agent finds a loophole, update `SKILL.md`, then re-run GREEN.
