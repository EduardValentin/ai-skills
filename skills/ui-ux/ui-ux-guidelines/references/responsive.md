# Responsive

- Build layouts that reflow on narrowing without dropping content or function; stack, wrap, or reveal instead of hiding.
- Support every orientation; never lock to portrait or landscape.
- Wrap all non-essential animation in `prefers-reduced-motion: no-preference`; under `reduce`, remove it.
- IF an animation carries meaning THEN under `reduce` keep it but slow its duration instead of removing it.
- IF the viewport is very large THEN scale touch targets up so they stay noticeable and fast to reach.
- IF the screen is tiny (watch-class) THEN never shrink targets; shift interaction to gestures or voice.
