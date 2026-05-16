# Codebase Scope Map Pressure Scenarios

Run these with a fresh agent after changing `codebase-scope-map`. They target rationalizations that make scoping too vague, too verbose, or too solution-oriented. Do not leak the expected behavior into the test prompt.

## Scenario 1 - Ticket Scoping Without Explicit Skill Name

Prompt:

```text
Before we implement this ticket, map the relevant code surface so the main agent and implementers know exactly which files, tests, patterns, and risks matter without loading the whole repo into context.
```

Expected behavior:
- Picks up the reusable scope-map protocol from the wording.
- Produces a structured scope map with file:line locators.
- Includes entry points, target modules, analogous implementations, tests, types/contracts, dependencies, touched areas, conflict points, and downstream slices.
- Does not propose a solution or write code.

Failure signals:
- Gives a prose summary without locators.
- Loads broad files or dumps source into the report.
- Skips tests/types/analogous implementations because the entry point seems obvious.

## Scenario 2 - Token Pressure

Prompt:

```text
The codebase is huge and context is tight. Scope this bug fix for downstream agents, but keep the result compact enough that the main agent can carry it.
```

Expected behavior:
- Treats the output as a navigable index, not a transcript.
- Uses one-line entries with precise locators.
- Groups representative items if a section would get too large.
- Adds high-risk omitted areas under potential conflict points.

Failure signals:
- Pastes full functions or long source excerpts.
- Lists every search hit without relevance.
- Omits risk areas instead of grouping them.

## Scenario 3 - Prototype UI Scoping

Prompt:

```text
Scope this UI ticket in a repo with a runnable designs/ React reference app. The later visual reviewer will need prototype element locators for parity against production.
```

Expected behavior:
- Includes prototype/reference elements as a mandatory section.
- Lists one row per visible relevant declaration in the scoped prototype slices.
- Adds a touched-areas map that pairs downstream consumers with production locators, routes/states/selectors, and prototype counterparts where relevant.
- Surfaces a conflict or input gap if prototype enumeration cannot be done.

Failure signals:
- Emits `_None._` for prototype elements on a parity-mode UI task.
- Says visual review can discover everything later without prototype locators.
- Leaves the UI/UX reviewer without a touched-areas map.
- Provides prototype prose without file:line locators.

## Scenario 4 - Missing Context

Prompt:

```text
Map the scope for this ticket, but the acceptance criteria are vague and I am not sure which route owns the feature.
```

Expected behavior:
- Maps what can be mapped from available terms.
- Uses `## Needs clarification or input` for missing AC/route questions.
- Explains why each missing input matters.
- Does not invent feature ownership or implementation direction.

Failure signals:
- Pretends the scope is complete.
- Asks only a broad clarification question without returning useful scoped evidence.
- Chooses an approach to compensate for missing requirements.
