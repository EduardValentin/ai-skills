// Browser-context extraction snippet for the UI/UX matched-element inventory.
//
// This is in-page JavaScript. Evaluate it against the live DOM through the
// host agent's DOM-evaluation capability (a native browser-automation tool's
// `evaluate()`-equivalent, or Playwright's `page.evaluate()` if running via
// the shell fallback in `agents/ui-ux.md` → `## Browser bootstrap`).
//
// Input: a CSS selector for the element being inspected.
// Output: a JSON-serialisable object with computed-style and bounding-rect
// fields. Returns `{ missing: true, selector }` if the selector doesn't match.
//
// Property set is chosen so the matched-element inventory's `font-* | color/bg
// | box | layout | size` columns can be filled directly from one call per
// element. Keep this list aligned with the inventory header in
// `agents/ui-ux.md` → `## Output format`.

((selector) => {
  const el = document.querySelector(selector);
  if (!el) return { missing: true, selector };
  const cs = getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return {
    font: {
      family: cs.fontFamily,
      size: cs.fontSize,
      weight: cs.fontWeight,
      style: cs.fontStyle,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      textTransform: cs.textTransform,
      textDecoration: cs.textDecorationLine,
    },
    color: { fg: cs.color, bg: cs.backgroundColor, opacity: cs.opacity },
    box: {
      padding: cs.padding,
      margin: cs.margin,
      border: cs.border,
      borderRadius: cs.borderRadius,
      boxShadow: cs.boxShadow,
      outline: cs.outline,
    },
    layout: {
      display: cs.display,
      flexDirection: cs.flexDirection,
      alignItems: cs.alignItems,
      justifyContent: cs.justifyContent,
      gap: cs.gap,
      position: cs.position,
    },
    size: { width: rect.width, height: rect.height },
    transform: cs.transform,
  };
})('YOUR_SELECTOR');
