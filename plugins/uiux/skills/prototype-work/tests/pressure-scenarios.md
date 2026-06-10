# Pressure Scenarios - Prototype Work

These scenarios test that the skill stays focused on prototype reference apps: setup under `designs/`, browser evidence, compact context reports, design-system discipline, mock separation, and concise PRD consolidation.

## Scenario 1 - Reference App Not Found

Prompt:

> The user asks for a prototype flow change, but the worktree has no `designs/` directory and no app path was provided.
>
> Options:
> A) Stop and ask the user for the reference app path before doing anything else.
> B) Search the entire repo for any React app and pick the first package.json.
> C) Continue by editing docs first while waiting for an app path.
>
> Choose A, B, or C and write the next action.

Pass criteria:

- Chooses A.
- Does not edit files before an app path is provided.
- Plans to rerun the preparation script with `--app-root`.

## Scenario 2 - New User Flow

Prompt:

> The user asks to add a new onboarding flow to the prototype, with mocked eligibility rules and a simulated API fetch.
>
> What must accompany the prototype change?

Pass criteria:

- Updates `PRD.md` because product behavior changed.
- Keeps PRD edits limited to business rules and product behavior.
- Adds explicit mocks for the eligibility rule and API-like fetch.
- Adds loading states for the async behavior.
- Validates the flow through browser navigation.

## Scenario 3 - Token And Component Discipline

Prompt:

> The user asks for a new dashboard panel. Existing tokens and card components cover most of the role, but not the exact density. A sampled screenshot color and one-off pixel value would make matching faster.
>
> What implementation approach should the agent take?

Pass criteria:

- Reuses existing semantic tokens when roles match.
- Adds only generic reusable semantic tokens if a role is missing.
- Avoids one-off colors, sizes, and typography.
- Extends component variants when the role matches.
- Adds a new component only if variant extension would blur the component's purpose.
