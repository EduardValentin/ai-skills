# UIUX Skill Evaluations

These scenarios are the regression set for the UIUX plugin. Run them in fresh sessions when changing these skills.

## Evaluation 1: Token-First Styling

Prompt: "Using the design-studio workflow, add a stats section to the React reference app. Keep it visually polished."

Expected behavior:
- Inspects existing design tokens before styling.
- Reuses existing semantic tokens when they express the role.
- Avoids global one-off tokens for component-only values.
- Keeps genuine one-off sizing local to the component.
- Uses component-scoped color tokens only for genuine one-off component colors.
- Proposes global tokens only for missing reusable semantic roles.
- Updates design-system documentation if the token system changes.

## Evaluation 2: Reusable Components

Prompt: "Add a testimonials row and a compact testimonials card on another page."

Expected behavior:
- Identifies the repeated card pattern.
- Reuses or extracts a component with a clear role and variant API.
- Keeps page-specific data outside the reusable component.
- Avoids generic component names.

## Evaluation 3: Accessibility-First Frontend

Prompt: "Build a settings drawer with toggles and a destructive action."

Expected behavior:
- Starts from semantic structure and keyboard behavior.
- Provides accessible names, focus handling, and recoverable destructive-action copy.
- Checks contrast, reduced motion, and responsive behavior.

## Evaluation 4: Ambiguous Design Direction

Prompt: "Make the dashboard feel more premium and less cluttered."

Expected behavior:
- Runs a persistent brainstorm interview until audience, goal, desired impression, constraints, and things to avoid are clear.
- Presents distinct design directions with tradeoffs plus a recommended option.
- Waits for shared understanding before implementation.

## Evaluation 5: Brand-Voice Copy

Prompt: "Rewrite this hero and CTA so it sounds more confident."

Expected behavior:
- Uses brand-voice guidance or asks for the missing copy brief.
- Produces human, specific page copy without drifting into generic marketing language.
- Verifies CTA clarity and fit in the UI.
