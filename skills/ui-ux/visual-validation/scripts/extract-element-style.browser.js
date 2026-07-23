// Inject this file into the inspected page, then call
// globalThis.visualValidationExtractElementStyle(selector).

(() => {
  "use strict";

  function extractElementStyle(selector) {
    if (typeof selector !== "string" || selector.trim() === "") {
      return {
        error: "Selector must be a non-empty string.",
        selector,
      };
    }

    let element;
    try {
      element = document.querySelector(selector);
    } catch (error) {
      return {
        error: `Invalid selector: ${error.message}`,
        selector,
      };
    }

    if (!element) return { missing: true, selector };

    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();

    return {
      selector,
      font: {
        family: style.fontFamily,
        size: style.fontSize,
        weight: style.fontWeight,
        style: style.fontStyle,
        lineHeight: style.lineHeight,
        letterSpacing: style.letterSpacing,
        textTransform: style.textTransform,
        textDecoration: style.textDecorationLine,
      },
      color: {
        foreground: style.color,
        background: style.backgroundColor,
        opacity: style.opacity,
      },
      box: {
        padding: style.padding,
        margin: style.margin,
        border: style.border,
        borderRadius: style.borderRadius,
        boxShadow: style.boxShadow,
        outline: style.outline,
      },
      layout: {
        display: style.display,
        flexDirection: style.flexDirection,
        alignItems: style.alignItems,
        justifyContent: style.justifyContent,
        gridTemplateColumns: style.gridTemplateColumns,
        gridTemplateRows: style.gridTemplateRows,
        gap: style.gap,
        position: style.position,
        overflow: style.overflow,
      },
      geometry: {
        x: rect.x,
        y: rect.y,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        left: rect.left,
        width: rect.width,
        height: rect.height,
      },
      transform: style.transform,
    };
  }

  globalThis.visualValidationExtractElementStyle = extractElementStyle;
})();
