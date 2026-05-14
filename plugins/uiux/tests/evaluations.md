# UIUX Skill Evaluations

These scenarios are the regression set for the UIUX plugin and the `design-studio` refactor. Run them in fresh sessions when changing these skills.

## Evaluation 1: Token-First Styling

Prompt: "Using the design-studio workflow, add a stats section to the React reference app. Keep it visually polished."

Expected behavior:
- Inspects existing design tokens before styling.
- Avoids raw hex/rgb values and arbitrary utility classes in product UI.
- Proposes any missing token by semantic role before use.
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
- Pauses to align on audience, goal, desired impression, and constraints.
- Presents distinct design directions with tradeoffs.
- Waits for direction before implementation.

## Evaluation 5: Brand-Voice Copy

Prompt: "Rewrite this hero and CTA so it sounds more confident."

Expected behavior:
- Uses brand-voice guidance or asks for the missing copy brief.
- Produces human, specific page copy without treating the task as SEO unless search ranking is requested.
- Verifies CTA clarity and fit in the UI.
