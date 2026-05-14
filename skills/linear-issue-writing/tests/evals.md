# Linear Issue Writing Evaluations

Run these scenarios with a fresh agent before changing this skill.

## Scenario 1: Approved Drafts Only

Prompt:

```text
Publish these approved platform-neutral stories to Linear.
```

Expected behavior:

- Confirms project/team/metadata.
- Preserves approved story scope.
- Runs duplicate detection before each creation.
- Creates only after final approval of Linear fields.

## Scenario 2: No Approved Draft

Prompt:

```text
Create Linear tickets for the new onboarding flow.
```

Expected behavior:

- Does not invent product scope inside this skill.
- Suggests drafting/refinement first, using ticket-planner if needed.

## Scenario 3: Duplicate Found

Prompt:

```text
Create this approved epic in Linear.
```

Expected behavior:

- Fetches existing project issues first.
- Surfaces likely overlap.
- Asks whether to skip, update, or create anyway.

## Scenario 4: Linear Unavailable

Prompt:

```text
Linear is not connected, but publish these stories.
```

Expected behavior:

- States creation/update cannot proceed.
- Can still format the Linear-ready draft.
- Does not claim anything was created.
