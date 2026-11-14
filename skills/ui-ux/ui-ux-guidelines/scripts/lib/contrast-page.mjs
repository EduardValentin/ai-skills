export function collectContrastItems(config) {
  const ux = window.__uxAudit;
  const items = [];
  const excluded = { hidden: 0, disabled: 0, "aria-hidden": 0, "ignored-selector": 0 };
  const ignoredRoots = config.ignore.flatMap((selector) => [...document.querySelectorAll(selector)]);
  const SIDES = ["top", "right", "bottom", "left"];
  const BUTTONS = "button, [role=button], input[type=submit], input[type=button], input[type=reset]";
  const FIELDS =
    "input:not([type=hidden],[type=submit],[type=button],[type=reset],[type=image],[type=range]), textarea, select, [role=textbox], [role=checkbox], [role=radio], [role=combobox]";

  const exclusionOf = (element) => {
    if (ignoredRoots.some((root) => root.contains(element))) return "ignored-selector";
    if (element.closest('[aria-hidden="true"]')) return "aria-hidden";
    if (element.matches(':disabled, [aria-disabled="true"]')) return "disabled";
    const box = element.getBoundingClientRect();
    if (!ux.isRendered(element) || box.width === 0 || box.height === 0 || ux.effectiveOpacity(element) === 0) {
      return "hidden";
    }
    return null;
  };

  const active = new Set();
  for (const element of document.body.querySelectorAll("*")) {
    if (["script", "style", "noscript", "template"].includes(element.localName)) continue;
    const reason = exclusionOf(element);
    if (reason) excluded[reason] += 1;
    else active.add(element);
  }
  const activeMatches = (selector) => [...document.querySelectorAll(selector)].filter((el) => active.has(el));

  const isOverlappingSibling = (element) => {
    element.scrollIntoView({ block: "center", inline: "center" });
    const box = element.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return false;
    const stack = document.elementsFromPoint(x, y);
    const index = stack.indexOf(element);
    if (index < 0) return false;
    for (const under of stack.slice(index + 1)) {
      if (element.contains(under)) continue;
      const style = getComputedStyle(under);
      if (ux.TRANSPARENT.has(style.backgroundColor) && style.backgroundImage === "none") continue;
      return !under.contains(element);
    }
    return false;
  };

  const visibleSides = (style) =>
    SIDES.filter(
      (side) =>
        parseFloat(style[`border-${side}-width`]) > 0 && !["none", "hidden"].includes(style[`border-${side}-style`]),
    );
  const isFilled = (style) => !ux.TRANSPARENT.has(style.backgroundColor);
  const add = (kind, element, pairs, extra = {}) => items.push({ kind, selector: ux.selectorOf(element), pairs, ...extra });
  const overParent = (element, color) => ({ fg: color, opacity: 1, bg: ux.backgroundLayers(element.parentElement) });

  const boundaryPairs = (element, style) => {
    if (isFilled(style)) return [overParent(element, style.backgroundColor)];
    const sides = visibleSides(style);
    return sides.length ? [overParent(element, style[`border-${sides[0]}-color`])] : [];
  };

  const isIconFont = (style) => config.iconFonts.some((font) => style.fontFamily.toLowerCase().includes(font));

  for (const element of active) {
    if (!ux.hasDirectText(element) || element.closest("svg")) continue;
    const style = getComputedStyle(element);
    const role = element.dataset.contrastRole;
    const kind = role === "fine" || (role !== "text" && isIconFont(style)) ? "icon-outline" : "text";
    add(kind, element, [{ fg: style.color, opacity: ux.effectiveOpacity(element), bg: ux.backgroundLayers(element) }], {
      fontSizePx: parseFloat(style.fontSize),
      fontWeight: parseInt(style.fontWeight, 10),
      textSample: ux.directText(element).slice(0, 60),
      inconclusiveReason: isOverlappingSibling(element) ? "overlapping-content" : null,
    });
  }

  const TEXTLESS_INPUTS = ["checkbox", "radio", "range", "color", "file", "hidden", "image"];
  for (const element of activeMatches("input, textarea, select")) {
    if (TEXTLESS_INPUTS.includes(element.type)) continue;
    const style = getComputedStyle(element);
    const showsPlaceholder = element.value === "" && element.placeholder;
    if (element.value === "" && !showsPlaceholder) continue;
    const color = showsPlaceholder ? getComputedStyle(element, "::placeholder").color : style.color;
    add("text", element, [{ fg: color, opacity: ux.effectiveOpacity(element), bg: ux.backgroundLayers(element) }], {
      fontSizePx: parseFloat(style.fontSize),
      fontWeight: parseInt(style.fontWeight, 10),
      textSample: (showsPlaceholder ? element.placeholder : String(element.value)).slice(0, 60),
      pseudo: showsPlaceholder ? "::placeholder" : null,
    });
  }

  for (const svg of activeMatches("svg")) {
    if (svg.parentElement.closest("svg")) continue;
    const shapes = [...svg.querySelectorAll("path, circle, rect, line, polyline, polygon, ellipse, text")]
      .filter(ux.isRendered)
      .map((shape) => getComputedStyle(shape));
    if (shapes.length === 0) continue;
    const role = svg.dataset.contrastRole;
    const outlined = shapes.some((shape) => shape.fill === "none" && shape.stroke !== "none");
    const fine = role === "fine" || role === "icon-outline" || (role !== "icon-solid" && outlined);
    const paint = shapes[0].fill !== "none" ? shapes[0].fill : shapes[0].stroke;
    add(fine ? "icon-outline" : "icon-solid", svg, [{ fg: paint, opacity: ux.effectiveOpacity(svg), bg: ux.backgroundLayers(svg) }], {
      inconclusiveReason: paint.startsWith("url(") ? "background-image" : null,
    });
  }
  for (const element of activeMatches("[role=img]:not(svg):not(img)")) {
    if (element.textContent.trim() !== "") continue;
    const style = getComputedStyle(element);
    add("icon-solid", element, [{ fg: style.color, opacity: ux.effectiveOpacity(element), bg: ux.backgroundLayers(element) }]);
  }
  for (const image of activeMatches("img")) {
    const box = image.getBoundingClientRect();
    const isIcon = image.closest("a, button, [role=button]") || (box.width <= 48 && box.height <= 48);
    if (isIcon) add("icon-solid", image, [], { inconclusiveReason: "raster-icon" });
  }

  for (const field of activeMatches(FIELDS)) {
    const style = getComputedStyle(field);
    if (["checkbox", "radio"].includes(field.type) && style.appearance === "auto") {
      add("input-border", field, [], { inconclusiveReason: "native-appearance" });
      continue;
    }
    const sides = visibleSides(style);
    if (sides.length === 0) {
      add("input-border", field, [overParent(field, style.backgroundColor)], { side: "all", adjacent: "outside" });
      continue;
    }
    const colors = sides.map((side) => style[`border-${side}-color`]);
    const uniform = sides.length === 4 && colors.every((color) => color === colors[0]);
    for (const side of uniform ? ["all"] : sides) {
      const color = style[`border-${side === "all" ? "top" : side}-color`];
      add("input-border", field, [{ fg: color, opacity: 1, bg: ux.backgroundLayers(field) }], { side, adjacent: "inside" });
      add("input-border", field, [overParent(field, color)], { side, adjacent: "outside" });
    }
  }

  const looksLikeButton = (anchor) => {
    const style = getComputedStyle(anchor);
    return isFilled(style) || visibleSides(style).length === 4;
  };
  const buttons = [...activeMatches(BUTTONS), ...activeMatches("a").filter(looksLikeButton)];
  for (const button of buttons) {
    const style = getComputedStyle(button);
    if (style.backgroundImage !== "none") {
      add("button-boundary", button, [], { inconclusiveReason: "background-image" });
      continue;
    }
    const pairs = [];
    if (isFilled(style)) pairs.push(overParent(button, style.backgroundColor));
    const sides = visibleSides(style);
    if (sides.length) pairs.push(overParent(button, style[`border-${sides[0]}-color`]));
    if (pairs.length === 0 && style.textDecorationLine.includes("underline")) {
      pairs.push(overParent(button, style.textDecorationColor));
    }
    if (pairs.length) add("button-boundary", button, pairs);
  }

  const shapeOf = (style) =>
    [style.borderRadius, style.borderWidth, style.padding, style.fontSize, style.fontWeight, style.height].join("|");
  for (const [index, first] of buttons.entries()) {
    for (const second of buttons.slice(index + 1)) {
      if (first.parentElement !== second.parentElement) continue;
      const firstStyle = getComputedStyle(first);
      const secondStyle = getComputedStyle(second);
      if (shapeOf(firstStyle) !== shapeOf(secondStyle) || firstStyle.backgroundColor === secondStyle.backgroundColor) continue;
      const parentLayers = ux.backgroundLayers(first.parentElement);
      const fill = (style) => [{ color: style.backgroundColor, image: false }, ...parentLayers];
      add("button-pair", first, [{ fgLayers: fill(secondStyle), opacity: 1, bg: fill(firstStyle) }], {
        pairedSelector: ux.selectorOf(second),
      });
    }
  }

  const covered = new Set([...buttons, ...activeMatches(FIELDS)]);
  const components = activeMatches(
    "[role=switch], [role=slider], [role=tab], [role=progressbar], input[type=range], [tabindex], [data-contrast-role=ui-component]",
  );
  for (const component of components) {
    if (covered.has(component) || component.matches("a[href], summary, iframe") || component.tabIndex < 0) continue;
    const style = getComputedStyle(component);
    if (component.type === "range" && style.appearance === "auto") continue;
    const pairs = boundaryPairs(component, style);
    if (pairs.length) add("ui-component", component, pairs);
  }

  for (const divider of activeMatches("hr, [role=separator], [data-contrast-role=discernible]")) {
    const style = getComputedStyle(divider);
    const sides = visibleSides(style);
    const color = sides.length ? style[`border-${sides[0]}-color`] : style.backgroundColor;
    add("discernible", divider, [overParent(divider, color)]);
  }

  const selectionSelectors = new Set();
  for (const sheet of document.styleSheets) {
    let rules;
    try {
      rules = sheet.cssRules;
    } catch {
      continue;
    }
    for (const rule of rules) {
      if (!rule.selectorText || !rule.selectorText.includes("::selection")) continue;
      for (const part of rule.selectorText.split(",")) {
        if (part.includes("::selection")) selectionSelectors.add(part.replace("::selection", "").trim() || "*");
      }
    }
  }
  const selectable = new Set();
  for (const selector of selectionSelectors) {
    for (const element of activeMatches(selector === "*" || selector === ":root" ? "body *" : `${selector}, ${selector} *`)) {
      if (ux.hasDirectText(element)) selectable.add(element);
    }
  }
  for (const element of selectable) {
    const selection = getComputedStyle(element, "::selection");
    const layers = ux.backgroundLayers(element);
    add("selection", element, [
      { fg: selection.color, opacity: 1, bg: [{ color: selection.backgroundColor, image: false }, ...layers] },
    ]);
  }

  return { items, excluded };
}
