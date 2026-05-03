# React Reference App Parity

Loaded when the personal project's `designs/` is a runnable React reference app. Use during planning and during verification. Pair with `verification.md` at the Verify phase.

## Parity Rules

1. Mirror the prototype for the ticketed feature: exact copy, information hierarchy, layout, spacing, colors, typography, sizing, radii, shadows, responsive behavior, UI interactions, interaction states, transitions, and animations.
2. Maintain the production app's design system. Prefer existing production components, variants, CSS variables, and semantic tokens over copying raw prototype values or one-off classes.
3. Inspect both apps' styling systems before implementing visual work. Compare Tailwind versions, theme configuration, CSS variables, semantic tokens, breakpoints, base styles, and any component-library defaults that affect the feature.
4. Identical class names do not guarantee identical CSS across apps. Verify scale-sensitive utilities (`size-*`, spacing, typography, radius, shadow, color, breakpoints) and translate to exact production-equivalent values or semantic tokens when scales differ.
5. Carry over every relevant interaction and animation: trigger conditions, hover/focus/active/disabled behavior, duration, delay, easing, transform/opacity/property changes, mount/unmount behavior, and reduced-motion handling when present.
6. If the production design system lacks a needed semantic token, component variant, styling primitive, or animation primitive, surface that during brainstorming and planning before coding. Prefer adding or reusing production-system primitives over hard-coded local styling.
7. If the production app uses a different technology stack or lacks the prototype's primitives, surface that during planning and discuss the direction with the user before coding or finalizing approximations. Prefer existing production libraries and out-of-the-box styling/animation primitives when they can reproduce the reference faithfully.

## Plan Documentation

Document in the implementation plan so the user can approve the parity approach before code changes begin:

- Reference route and matching production route.
- Important UI states for this feature.
- Styling-scale findings and any divergences between the two apps.
- Semantic token / component / styling primitive / animation primitive mapping (prototype → production).
- Interaction findings and animation findings.
