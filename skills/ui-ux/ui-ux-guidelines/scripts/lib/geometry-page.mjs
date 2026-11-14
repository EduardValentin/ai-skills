const NATIVE_FOCUSABLE =
  "a[href], area[href], button, input:not([type=hidden]), select, textarea, summary, iframe, [contenteditable]:not([contenteditable=false])";
const INTERACTIVE_ROLES = [
  "button", "link", "checkbox", "radio", "switch", "tab", "menuitem", "menuitemcheckbox", "menuitemradio",
  "option", "slider", "spinbutton", "combobox", "textbox",
].map((role) => `[role=${role}]`).join(", ");

export const PAGE_CONSTANTS = { NATIVE_FOCUSABLE, INTERACTIVE_ROLES };

export function collectNamedElements(constants) {
  const ux = window.__uxAudit;
  const candidates = `${constants.NATIVE_FOCUSABLE}, ${constants.INTERACTIVE_ROLES}, [tabindex]:not([tabindex="-1"])`;
  ux.named = [...document.querySelectorAll(candidates)].filter((el) => ux.isRendered(el) && !el.matches(":disabled"));
  return ux.named.length;
}

export function auditGeometry(config) {
  const ux = window.__uxAudit;
  const { NATIVE_FOCUSABLE, INTERACTIVE_ROLES } = config.constants;
  const BUTTONS = "button, input[type=button], input[type=submit], input[type=reset], input[type=image], [role=button]";
  const viewportWidth = document.documentElement.clientWidth;
  const round = (value) => Math.round(value * 100) / 100;
  const results = [];
  const ran = [];
  const excludedRoots = config.exclude ? [...document.querySelectorAll(config.exclude)] : [];
  const isExcluded = (element) => excludedRoots.some((root) => root.contains(element));
  const nameOf = (element) => config.names[ux.named.indexOf(element)] ?? "";

  const fail = (ruleId, target, measured, expected, corrective, details) =>
    results.push({
      ruleId,
      status: "fail",
      selector: typeof target === "string" ? target : ux.selectorOf(target),
      measured,
      expected,
      corrective,
      ...(details ? { details } : {}),
    });
  const indeterminate = (ruleId, selector, reason) =>
    results.push({ ruleId, status: "indeterminate", selector, measured: null, expected: "measurable", reason });
  const rule = (ruleId, isApplicable, check) => {
    if (!config.rules.includes(ruleId) || !isApplicable) return;
    ran.push(ruleId);
    check();
  };

  const undiscoverableReason = (element) => {
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.display === "none") return "display";
      if (parseFloat(style.opacity) === 0) return "opacity";
      if (node.getAttribute("aria-hidden") === "true") return "aria-hidden";
      if (node.localName === "dialog" && !node.open) return "closed-dialog";
    }
    if (getComputedStyle(element).visibility !== "visible") return "visibility";
    if (element.getClientRects().length === 0) return "display";
    const box = element.getBoundingClientRect();
    if (box.width === 0 || box.height === 0) return "zero-size";
    const scroller = document.scrollingElement;
    const left = box.left + scrollX;
    const top = box.top + scrollY;
    if (left + box.width <= 0 || top + box.height <= 0 || left >= scroller.scrollWidth || top >= scroller.scrollHeight) {
      return "offscreen";
    }
    for (let node = element.parentElement; node && node !== document.documentElement; node = node.parentElement) {
      const style = getComputedStyle(node);
      if (style.overflowX === "visible" && style.overflowY === "visible") continue;
      const clip = node.getBoundingClientRect();
      const width = Math.min(box.right, clip.right) - Math.max(box.left, clip.left);
      const height = Math.min(box.bottom, clip.bottom) - Math.max(box.top, clip.top);
      if (width <= 0 || height <= 0) return "clipped";
    }
    return null;
  };

  const whileFocused = (element, read) => {
    const previous = document.activeElement;
    element.focus({ preventScroll: true });
    const value = read();
    element.blur();
    previous?.focus?.({ preventScroll: true });
    return value;
  };
  const revealedReason = (element) => {
    const atRest = undiscoverableReason(element);
    return atRest && whileFocused(element, () => undiscoverableReason(element)) ? atRest : null;
  };

  const isInlineTextLink = (element) =>
    element.localName === "a" && getComputedStyle(element).display === "inline" && ux.hasDirectText(element.parentElement);

  const unionBox = (boxes) => ({
    left: Math.min(...boxes.map((box) => box.left)),
    top: Math.min(...boxes.map((box) => box.top)),
    right: Math.max(...boxes.map((box) => box.right)),
    bottom: Math.max(...boxes.map((box) => box.bottom)),
  });
  const targetBox = (element) => {
    const isTiny = (box) => box.width < 2 || box.height < 2;
    let box = element.getBoundingClientRect();
    if (isTiny(box) || undiscoverableReason(element)) box = whileFocused(element, () => element.getBoundingClientRect());
    const labels = ["checkbox", "radio"].includes(element.type) ? [...(element.labels ?? [])].filter(ux.isRendered) : [];
    const merged = unionBox([box, ...labels.map((label) => label.getBoundingClientRect())]);
    return { ...merged, width: merged.right - merged.left, height: merged.bottom - merged.top };
  };

  const interactive = [
    ...document.querySelectorAll(`${NATIVE_FOCUSABLE}, ${INTERACTIVE_ROLES}, [tabindex]:not([tabindex="-1"])`),
  ].filter((el) => ux.isRendered(el) && !el.matches(":disabled") && !isExcluded(el));

  if (config.documentChecks) {
    rule("DOC-LANG", true, () => {
      const lang = document.documentElement.getAttribute("lang");
      let wellFormed = Boolean(lang && lang.trim());
      try {
        Intl.getCanonicalLocales(lang);
      } catch {
        wellFormed = false;
      }
      if (!wellFormed) fail("DOC-LANG", "html", lang, "well-formed BCP 47 tag", "set html lang to the page language, e.g. en");
    });

    rule("DOC-TITLE", true, () => {
      const title = document.querySelector("head > title")?.textContent.trim();
      if (!title) fail("DOC-TITLE", "head > title", title ?? null, "unique, non-empty title", "add unique <title>");
    });

    rule("VIEWPORT-ZOOM", true, () => {
      const meta = document.querySelector("meta[name=viewport]");
      if (!meta) {
        fail("VIEWPORT-ZOOM", "head", null, "meta viewport with width=device-width", "add <meta name=viewport content=\"width=device-width, initial-scale=1\">");
        return;
      }
      const pairs = Object.fromEntries(
        (meta.getAttribute("content") ?? "").split(/[,;]/).map((pair) => pair.split("=").map((part) => part.trim().toLowerCase())),
      );
      if (["no", "0"].includes(pairs["user-scalable"])) {
        fail("VIEWPORT-ZOOM", "meta[name=viewport]", `user-scalable=${pairs["user-scalable"]}`, "user-scalable absent or yes", "remove user-scalable=no");
      }
      if (parseFloat(pairs["maximum-scale"]) < 5) {
        fail("VIEWPORT-ZOOM", "meta[name=viewport]", `maximum-scale=${pairs["maximum-scale"]}`, "maximum-scale absent or >= 5", "maximum-scale=5 or remove");
      }
    });

    rule("LANDMARKS", true, () => {
      const count = (selector) => [...document.querySelectorAll(selector)].filter(ux.isRendered).length;
      if (count("main, [role=main]") === 0) fail("LANDMARKS", "body", { main: 0 }, ">= 1 main", "wrap primary content in <main>");
      if (count("nav, [role=navigation]") === 0) fail("LANDMARKS", "body", { nav: 0 }, ">= 1 nav", "wrap primary navigation in <nav>");
    });

    rule("TABINDEX-VALUE", true, () => {
      for (const element of document.querySelectorAll("[tabindex]")) {
        const value = Number(element.getAttribute("tabindex").trim());
        if (value !== 0 && value !== -1) fail("TABINDEX-VALUE", element, element.getAttribute("tabindex"), "0 or -1", value > 0 ? "0" : "-1");
      }
    });

    rule("TABINDEX-NATIVE", true, () => {
      for (const element of document.querySelectorAll(NATIVE_FOCUSABLE)) {
        if (!element.hasAttribute("tabindex")) continue;
        const value = element.getAttribute("tabindex").trim();
        if (value === "-1" && undiscoverableReason(element)) continue;
        fail("TABINDEX-NATIVE", element, value, "absent", "remove tabindex");
      }
    });

    rule("AUTOFOCUS", true, () => {
      for (const element of document.querySelectorAll("[autofocus]")) fail("AUTOFOCUS", element, "present", "absent", "remove autofocus");
    });

    rule("MEDIA-MUTE-PRESSED", true, () => {
      const media = document.querySelectorAll("audio, video");
      for (const button of interactive.filter((el) => el.matches(BUTTONS) && /\b(un)?mute\b/i.test(nameOf(el)))) {
        const before = button.getAttribute("aria-pressed");
        const inSync = () => media.length !== 1 || button.getAttribute("aria-pressed") === String(media[0].muted);
        const syncedBefore = inSync();
        button.click();
        const after = button.getAttribute("aria-pressed");
        const syncedAfter = inSync();
        button.click();
        const valid = ["true", "false"].includes(before) && ["true", "false"].includes(after) && before !== after;
        if (!valid || !syncedBefore || !syncedAfter) {
          fail("MEDIA-MUTE-PRESSED", button, { before, after, muted: media.length === 1 ? media[0].muted : null },
            "aria-pressed in {true,false}, toggles, matches muted", "set aria-pressed to reflect muted state");
        }
      }
    });

    rule("MEDIA-VOLUME-RANGE", true, () => {
      for (const element of interactive.filter((el) => /\bvolume\b/i.test(nameOf(el)))) {
        if (element.matches("input[type=range]")) continue;
        fail("MEDIA-VOLUME-RANGE", element, { tag: element.localName, role: element.getAttribute("role") }, "input[type=range]", "use <input type=range>");
      }
    });

    rule("CONTROL-NAME", true, () => {
      for (const element of interactive) {
        if (element.localName === "iframe" || nameOf(element).trim() !== "") continue;
        fail("CONTROL-NAME", element, "", "non-empty accessible name", "add visible text, a <label>, or aria-label");
      }
    });

    rule("LABEL-ASSOC", true, () => {
      const fields = "input:not([type=hidden],[type=submit],[type=button],[type=reset],[type=image]), select, textarea";
      for (const field of [...document.querySelectorAll(fields)].filter((el) => ux.isRendered(el) && !isExcluded(el))) {
        const labelled =
          field.labels.length > 0 ||
          (field.getAttribute("aria-label") ?? "").trim() !== "" ||
          (field.getAttribute("aria-labelledby") ?? "").split(/\s+/).some((id) => id && document.getElementById(id));
        if (!labelled) {
          fail("LABEL-ASSOC", field, field.placeholder ? "placeholder only" : "no label", "<label for> or aria-labelledby", "add <label for=\"id\"> above the field");
        }
      }
    });

    rule("ARIA-REFS", true, () => {
      for (const attribute of ["aria-labelledby", "aria-describedby", "aria-controls", "aria-errormessage", "for"]) {
        for (const element of document.querySelectorAll(`[${attribute}]`)) {
          if (attribute === "for" && !["label", "output"].includes(element.localName)) continue;
          const missing = element.getAttribute(attribute).split(/\s+/).filter((id) => id && !document.getElementById(id));
          if (missing.length) fail("ARIA-REFS", element, { attribute, missing }, "every referenced id exists", "point the attribute at an existing id");
        }
      }
    });

    rule("IMG-ALT", true, () => {
      for (const image of document.querySelectorAll("img:not([alt])")) {
        if (!isExcluded(image)) fail("IMG-ALT", image, "alt missing", "alt attribute present", "add alt text, or alt=\"\" if decorative");
      }
    });
  }

  rule("FOCUS-HIDDEN", true, () => {
    const focusOrder = [...document.querySelectorAll(`${NATIVE_FOCUSABLE}, [tabindex]`)].filter(
      (el) => el.tabIndex >= 0 && !el.matches(":disabled") && !el.closest("[inert]") && !isExcluded(el),
    );
    for (const element of focusOrder) {
      const reason = revealedReason(element);
      if (reason) fail("FOCUS-HIDDEN", element, reason, "not in focus order", "add inert or tabindex=-1 to the hidden container, or display:none");
    }
  });

  const targets = interactive.filter((el) => !isInlineTextLink(el) && !revealedReason(el)).map((el) => ({ el, box: targetBox(el) }));
  const minimum = round(48 * config.ptScale);

  rule("TARGET-SIZE", true, () => {
    for (const { el, box } of targets) {
      const width = round(box.width);
      const height = round(box.height);
      if (width >= minimum && height >= minimum) continue;
      fail("TARGET-SIZE", el, { width, height }, `>= ${minimum}px x ${minimum}px`, { width: Math.max(width, minimum), height: Math.max(height, minimum) });
    }
  });

  const gapBetween = (first, second) => {
    const dx = Math.max(0, second.left - first.right, first.left - second.right);
    const dy = Math.max(0, second.top - first.bottom, first.top - second.bottom);
    return round(Math.hypot(dx, dy));
  };
  const checkGaps = (ruleId, threshold, wantsButtonPair) => {
    for (const [index, first] of targets.entries()) {
      for (const second of targets.slice(index + 1)) {
        if (first.el.contains(second.el) || second.el.contains(first.el)) continue;
        if ((first.el.matches(BUTTONS) && second.el.matches(BUTTONS)) !== wantsButtonPair) continue;
        const gap = gapBetween(first.box, second.box);
        if (gap >= threshold) continue;
        fail(ruleId, `${ux.selectorOf(first.el)} <-> ${ux.selectorOf(second.el)}`, gap, `>= ${threshold}px`, `increase spacing by ${round(threshold - gap)} px`);
      }
    }
  };
  rule("TARGET-GAP-BUTTON", true, () => checkGaps("TARGET-GAP-BUTTON", round(16 * config.ptScale), true));
  rule("TARGET-GAP", true, () => checkGaps("TARGET-GAP", round(8 * config.ptScale), false));

  rule("REFLOW-OVERFLOW", true, () => {
    const scrollWidth = document.scrollingElement.scrollWidth;
    if (scrollWidth <= viewportWidth) return;
    const offenders = [...document.body.querySelectorAll("*")]
      .filter((el) => ux.isRendered(el) && el.getBoundingClientRect().right + scrollX > viewportWidth + 0.5)
      .filter((el, _, all) => !all.some((other) => other !== el && el.contains(other)))
      .slice(0, 5)
      .map((el) => ({ selector: ux.selectorOf(el), right: round(el.getBoundingClientRect().right + scrollX) }));
    fail("REFLOW-OVERFLOW", "html", { scrollWidth }, `scrollWidth <= ${viewportWidth}px`, "let content wrap or stack: max-width:100%, min-width:0, flex-wrap, no fixed widths", { offenders });
  });

  rule("FORM-OPTIONS-VISIBLE", config.isMobileViewport, () => {
    const options = [...document.querySelectorAll("input[type=radio], input[type=checkbox], [role=radio], [role=option], [role=checkbox], select")]
      .flatMap((el) => [el, ...(el.labels ?? [])])
      .filter((el) => ux.isRendered(el) && !isExcluded(el));
    for (const option of new Set(options)) {
      const box = option.getBoundingClientRect();
      const left = round(box.left + scrollX);
      const right = round(box.right + scrollX);
      if (left >= 0 && right <= viewportWidth) continue;
      fail("FORM-OPTIONS-VISIBLE", option, { left, right }, `0 <= left, right <= ${viewportWidth}`, `stack options vertically / allow wrapping within ${viewportWidth} px`);
    }
  });

  const bodyText = [...document.querySelectorAll(config.bodyTextSelector)].filter((el) => ux.isRendered(el) && !isExcluded(el));

  rule("BODY-FONT-SIZE", true, () => {
    for (const element of bodyText) {
      const size = round(parseFloat(getComputedStyle(element).fontSize));
      if (size < config.minBodyFontPx) fail("BODY-FONT-SIZE", element, { fontSizePx: size }, `>= ${config.minBodyFontPx}px`, { fontSizePx: config.minBodyFontPx });
    }
  });

  rule("LINE-LENGTH", true, () => {
    const lineLengths = (element) => {
      const lines = new Map();
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      const range = document.createRange();
      let budget = 6000;
      for (let node = walker.nextNode(); node && budget > 0; node = walker.nextNode()) {
        for (let offset = 0; offset < node.length && budget > 0; offset += 1, budget -= 1) {
          range.setStart(node, offset);
          range.setEnd(node, offset + 1);
          const box = range.getClientRects()[0];
          if (!box || box.width === 0) continue;
          const key = Math.round(box.top);
          lines.set(key, (lines.get(key) ?? 0) + 1);
        }
      }
      return [...lines.entries()].sort((x, y) => x[0] - y[0]).map(([, count]) => count).slice(0, -1);
    };
    const perElement = bodyText
      .slice(0, 80)
      .map((element) => ({ element, lines: lineLengths(element) }))
      .filter(({ lines }) => lines.length >= 1);
    const counted = perElement.flatMap(({ lines }) => lines);
    if (counted.length === 0) {
      indeterminate("LINE-LENGTH", config.bodyTextSelector, "no multi-line body text");
      return;
    }
    const mean = (values) => round(values.reduce((sum, value) => sum + value, 0) / values.length);
    const average = mean(counted);
    const widest = Math.max(...perElement.map(({ element }) => element.getBoundingClientRect().width));
    const tooLong = average > config.measureMax;
    const tooShort = average < config.measureMin && widest < viewportWidth * 0.8;
    if (!tooLong && !tooShort) return;
    const details = {
      elements: perElement.slice(0, 10).map(({ element, lines }) => ({ selector: ux.selectorOf(element), avg: mean(lines) })),
    };
    fail("LINE-LENGTH", config.bodyTextSelector, { avgCharsPerLine: average }, `${config.measureMin}..${config.measureMax} chars`,
      { maxWidthCh: tooLong ? config.measureMax : config.measureMin }, details);
  });

  rule("SPACING-RATIO", true, () => {
    const stackedChildren = (parent) => [...parent.children].filter((child) => ux.isRendered(child) && getComputedStyle(child).position !== "absolute" && getComputedStyle(child).position !== "fixed");
    const isHeading = (element) => /^h[1-6]$/.test(element.localName);

    for (const heading of document.querySelectorAll("h1, h2, h3, h4, h5, h6")) {
      if (!ux.isRendered(heading) || isExcluded(heading)) continue;
      const siblings = stackedChildren(heading.parentElement);
      const index = siblings.indexOf(heading);
      const previous = siblings[index - 1];
      const next = siblings[index + 1];
      if (!previous || !next || isHeading(previous)) continue;
      const box = heading.getBoundingClientRect();
      const above = round(box.top - previous.getBoundingClientRect().bottom);
      const below = round(next.getBoundingClientRect().top - box.bottom);
      if (above < 0 || below < 0 || (above === 0 && below === 0) || below < above) continue;
      fail("SPACING-RATIO", heading, { aboveHeadingPx: above, belowHeadingPx: below }, "heading-to-content gap < gap above heading",
        { aboveHeadingPx: Math.max(above, round(below * 1.5)) });
    }

    const GROUPS = "section, article, fieldset, li, [role=group]";
    const edge = (style, side) => parseFloat(style[`padding-${side}`]) + parseFloat(style[`border-${side}-width`]);
    const parents = new Set([...document.querySelectorAll(GROUPS)].map((group) => group.parentElement));
    for (const parent of parents) {
      const groups = stackedChildren(parent).filter((child) => child.matches(GROUPS) && !isExcluded(child));
      if (groups.length < 2) continue;
      const separations = [];
      for (const [index, group] of groups.slice(1).entries()) {
        const upper = groups[index];
        const gap = group.getBoundingClientRect().top - upper.getBoundingClientRect().bottom;
        if (gap < 0) continue;
        separations.push(gap + edge(getComputedStyle(upper), "bottom") + edge(getComputedStyle(group), "top"));
      }
      if (separations.length === 0) continue;
      const between = round(Math.min(...separations));
      for (const group of groups) {
        const children = stackedChildren(group);
        const gaps = children.slice(1).map((child, index) => child.getBoundingClientRect().top - children[index].getBoundingClientRect().bottom).filter((gap) => gap >= 0);
        const within = gaps.length ? round(Math.max(...gaps)) : 0;
        if (within <= between) continue;
        fail("SPACING-RATIO", group, { withinGroupPx: within, betweenGroupsPx: between }, "largest gap inside a group <= gap between groups",
          { betweenGroupsPx: round(within * 1.5) });
      }
    }
  });

  const apca = [];
  const declaredTarget = (element) => {
    const declared = [Number(element.dataset.apcaTarget)];
    for (const [selector, target] of Object.entries(config.apcaTargets)) if (element.matches(selector)) declared.push(target);
    return Math.max(...declared.filter((value) => !Number.isNaN(value)), -Infinity);
  };
  const paintOf = (element, style) => {
    const borders = ["top", "right", "bottom", "left"].filter((side) => parseFloat(style[`border-${side}-width`]) > 0);
    const candidates = [style.backgroundColor, ...borders.map((side) => style[`border-${side}-color`]), style.fill, style.stroke];
    return candidates.find((color) => color && color !== "none" && !ux.TRANSPARENT.has(color)) ?? style.color;
  };
  const smallestSolidDimension = (element, style) => {
    const box = element.getBoundingClientRect();
    if (element instanceof SVGGeometryElement && style.fill === "none" && parseFloat(style.strokeWidth) > 0) {
      const matrix = element.getCTM();
      return parseFloat(style.strokeWidth) * Math.sqrt(Math.abs(matrix.a * matrix.d - matrix.b * matrix.c));
    }
    const borders = ["top", "right", "bottom", "left"].map((side) => parseFloat(style[`border-${side}-width`])).filter((width) => width > 0);
    if (ux.TRANSPARENT.has(style.backgroundColor) && borders.length && !ux.hasDirectText(element) && !(element instanceof SVGElement)) {
      return Math.min(...borders);
    }
    return Math.min(box.width, box.height);
  };
  const ICONS = "svg, [role=img], img, i, [data-icon]";
  const declaredSelectors = ["[data-apca-target]", ...Object.keys(config.apcaTargets)].join(", ");
  const DECLARED_RULES = [
    { ruleId: "APCA-NONTEXT-15", target: 15, minDimension: 5, applies: (element) => !ux.hasDirectText(element) },
    { ruleId: "APCA-ICON-30", target: 30, minDimension: 5.5, applies: (element) => element.matches(ICONS) },
  ];
  for (const { ruleId, target, minDimension, applies } of DECLARED_RULES) {
    rule(ruleId, true, () => {
      for (const element of document.querySelectorAll(declaredSelectors)) {
        if (!ux.isRendered(element) || isExcluded(element) || declaredTarget(element) !== target || !applies(element)) continue;
        const firstShape = element.localName === "svg" && element.querySelector("path, circle, rect, line, polyline, polygon, ellipse");
        const painted = firstShape || element;
        const style = getComputedStyle(painted);
        const paintsOwnFill = painted === element && !ux.TRANSPARENT.has(style.backgroundColor);
        apca.push({
          ruleId,
          target,
          minDimension,
          selector: ux.selectorOf(element),
          fg: paintOf(painted, style),
          opacity: ux.effectiveOpacity(element),
          bg: ux.backgroundLayers(paintsOwnFill ? element.parentElement : element),
          dimension: round(smallestSolidDimension(painted, style)),
        });
      }
    });
  }
  rule("APCA-TEXT-SIZE", true, () => {
    for (const element of document.body.querySelectorAll("*")) {
      if (!ux.hasDirectText(element) || !ux.isRendered(element) || isExcluded(element) || element.closest("svg, script, style, noscript")) continue;
      const style = getComputedStyle(element);
      apca.push({
        ruleId: "APCA-TEXT-SIZE", selector: ux.selectorOf(element), fg: style.color, opacity: ux.effectiveOpacity(element),
        bg: ux.backgroundLayers(element), fontSizePx: round(parseFloat(style.fontSize)), fontWeight: parseInt(style.fontWeight, 10),
      });
    }
  });

  return {
    results,
    ran,
    apca,
    title: document.querySelector("head > title")?.textContent.trim() || null,
    excluded: excludedRoots.map(ux.selectorOf),
  };
}

export async function auditTextResize() {
  const ux = window.__uxAudit;
  const round = (value) => Math.round(value * 100) / 100;
  const results = [];
  const fail = (selector, measured) =>
    results.push({
      ruleId: "TEXT-RESIZE-200", status: "fail", selector, measured, expected: "0 overlaps, 0 clipped",
      corrective: "allow wrapping/auto height; remove fixed height or overflow:hidden",
    });

  const elements = [...document.querySelectorAll("body, body *")];
  const sizes = elements.map((element) => parseFloat(getComputedStyle(element).fontSize));
  elements.forEach((element, index) => element.style?.setProperty("font-size", `${sizes[index] * 2}px`, "important"));
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

  const textOwners = elements.filter((el) => ux.hasDirectText(el) && ux.isRendered(el) && !el.closest("svg, script, style, noscript"));
  const range = document.createRange();
  const lineBoxes = textOwners.slice(0, 1500).map((owner) => ({
    owner,
    boxes: [...owner.childNodes]
      .filter((node) => node.nodeType === 3 && node.nodeValue.trim() !== "")
      .flatMap((node) => {
        range.selectNodeContents(node);
        return [...range.getClientRects()];
      }),
  }));
  const isVisuallyHidden = (element) => element.clientWidth <= 1 || element.clientHeight <= 1;
  const reported = new Set();
  for (const [index, first] of lineBoxes.entries()) {
    for (const second of lineBoxes.slice(index + 1)) {
      if (first.owner.contains(second.owner) || second.owner.contains(first.owner)) continue;
      const overlap = first.boxes
        .flatMap((x) => second.boxes.map((y) => [Math.min(x.right, y.right) - Math.max(x.left, y.left), Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top)]))
        .find(([width, height]) => width > 1 && height > 1);
      if (!overlap) continue;
      const key = `${ux.selectorOf(first.owner)} <-> ${ux.selectorOf(second.owner)}`;
      if (reported.has(key)) continue;
      reported.add(key);
      fail(key, { overlapPx: { width: round(overlap[0]), height: round(overlap[1]) } });
    }
  }
  for (const owner of textOwners) {
    if (isVisuallyHidden(owner)) continue;
    const style = getComputedStyle(owner);
    const clipsX = ["hidden", "clip"].includes(style.overflowX) || style.textOverflow === "ellipsis";
    const clipsY = ["hidden", "clip"].includes(style.overflowY);
    const overflowX = clipsX ? owner.scrollWidth - owner.clientWidth : 0;
    const overflowY = clipsY ? owner.scrollHeight - owner.clientHeight : 0;
    if (overflowX > 1 || overflowY > 1) fail(ux.selectorOf(owner), { clippedPx: { x: Math.max(0, overflowX), y: Math.max(0, overflowY) } });
  }
  return results;
}
