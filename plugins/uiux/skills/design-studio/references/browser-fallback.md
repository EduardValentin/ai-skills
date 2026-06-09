# Visual Capture Fallback

Rendered evidence is required for design-studio work. Use the first available option:

1. Native browser or screenshot capability in the current environment.
2. Project-local browser automation or an installed browser automation package.
3. A small temporary screenshot script run from the project.
4. User-provided screenshots.

Capture the target page and nearby shared surfaces at the required viewports. If automation is unavailable, start the dev server and ask the user for screenshots before implementation and again after changes.

Do not claim visual confidence when no rendered evidence was available. Report the exact blocker and the residual risk instead.
