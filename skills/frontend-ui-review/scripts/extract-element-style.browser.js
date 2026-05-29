// Browser-context extraction snippet for matched-element visual review.
//
// Evaluate this in the page against a CSS selector for the element being
// inspected. It returns the computed-style and bounding-rect fields needed to
// fill the frontend-ui-review matched-element inventory.

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
