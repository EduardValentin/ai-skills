// Inject unchanged into the inspected page, then evaluate
// globalThis.paritySnapshot(rootSelector, options) with the selector passed
// as a serialized argument. Never interpolate the selector into script text.

(() => {
  "use strict";

  const STYLE_KEYS = [
    "fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "textTransform", "textDecorationLine",
    "color", "backgroundColor", "opacity",
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "marginTop", "marginRight", "marginBottom", "marginLeft",
    "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
    "borderTopStyle", "borderRightStyle", "borderBottomStyle", "borderLeftStyle",
    "borderTopColor", "borderRightColor", "borderBottomColor", "borderLeftColor",
    "borderTopLeftRadius", "borderTopRightRadius", "borderBottomRightRadius", "borderBottomLeftRadius",
    "boxShadow", "outlineWidth", "outlineStyle", "outlineColor", "outlineOffset",
    "display", "flexDirection", "flexWrap", "alignItems", "justifyContent", "alignContent",
    "gridTemplateColumns", "gridTemplateRows", "gridAutoFlow", "rowGap", "columnGap",
    "position", "overflowX", "overflowY", "zIndex",
    "flexGrow", "flexShrink", "flexBasis", "alignSelf", "order",
    "gridColumnStart", "gridColumnEnd", "gridRowStart", "gridRowEnd",
    "textOverflow", "whiteSpace", "transform",
  ];
  const SKIPPED_TAGS = new Set(["script", "style", "template", "noscript"]);
  const FOCUSABLE_TAGS = new Set(["button", "input", "select", "textarea", "summary", "iframe"]);
  const NAME_FROM_CONTENT_ROLES = new Set([
    "button", "link", "heading", "cell", "columnheader", "rowheader", "menuitem",
    "option", "tab", "tooltip", "checkbox", "radio", "switch", "treeitem",
  ]);
  const STATE_ATTRIBUTES = ["aria-expanded", "aria-selected", "aria-checked", "aria-pressed", "aria-disabled", "aria-current", "aria-hidden"];
  const INPUT_ROLES = {
    button: "button", submit: "button", reset: "button", image: "button", checkbox: "checkbox", radio: "radio",
    range: "slider", number: "spinbutton", search: "searchbox", email: "textbox", tel: "textbox", text: "textbox", url: "textbox",
  };
  const DEFAULT_OPTIONS = { hookAttribute: "data-parity", rootAttribute: "data-parity-root" };

  function collapseWhitespace(text) {
    return text.replace(/\s+/g, " ").trim();
  }

  function ownText(element) {
    let text = "";
    for (const child of element.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) text += child.textContent;
    }
    return collapseWhitespace(text);
  }

  function fnv1a(text) {
    let hash = 0x811c9dc5;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193) >>> 0;
    }
    return hash.toString(16).padStart(8, "0");
  }

  function implicitRole(element) {
    const tag = element.tagName.toLowerCase();
    switch (tag) {
      case "a": return element.hasAttribute("href") ? "link" : "";
      case "button": return "button";
      case "h1": case "h2": case "h3": case "h4": case "h5": case "h6": return "heading";
      case "img": return element.getAttribute("alt") === "" ? "presentation" : "img";
      case "nav": return "navigation";
      case "main": return "main";
      case "header": return element.closest("article, aside, main, nav, section") ? "" : "banner";
      case "footer": return element.closest("article, aside, main, nav, section") ? "" : "contentinfo";
      case "aside": return "complementary";
      case "section": return element.hasAttribute("aria-label") || element.hasAttribute("aria-labelledby") ? "region" : "";
      case "article": return "article";
      case "ul": case "ol": return "list";
      case "li": return "listitem";
      case "table": return "table";
      case "tr": return "row";
      case "td": return "cell";
      case "th": return element.getAttribute("scope") === "row" ? "rowheader" : "columnheader";
      case "select": return element.multiple || element.size > 1 ? "listbox" : "combobox";
      case "textarea": return "textbox";
      case "form": return "form";
      case "dialog": return "dialog";
      case "hr": return "separator";
      case "p": return "paragraph";
      case "input": return INPUT_ROLES[(element.getAttribute("type") || "text").toLowerCase()] || "textbox";
      default: return "";
    }
  }

  function role(element) {
    const explicit = element.getAttribute("role");
    if (explicit && explicit.trim()) return explicit.trim().split(/\s+/)[0];
    return implicitRole(element);
  }

  function textOfIds(element, attribute) {
    const ids = (element.getAttribute(attribute) || "").split(/\s+/).filter(Boolean);
    const texts = ids.map((id) => {
      const target = element.ownerDocument.getElementById(id);
      return target ? collapseWhitespace(target.textContent) : "";
    }).filter(Boolean);
    return texts.join(" ");
  }

  function labelText(element) {
    if (element.labels && element.labels.length) {
      return collapseWhitespace(Array.from(element.labels).map((label) => label.textContent).join(" "));
    }
    const wrapping = element.closest("label");
    return wrapping ? collapseWhitespace(wrapping.textContent) : "";
  }

  function accessibleName(element, elementRole) {
    if (element.hasAttribute("aria-labelledby")) {
      const labelled = textOfIds(element, "aria-labelledby");
      if (labelled) return { name: labelled, nameFrom: "author" };
    }
    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel && ariaLabel.trim()) return { name: collapseWhitespace(ariaLabel), nameFrom: "author" };
    if (["input", "select", "textarea"].includes(element.tagName.toLowerCase())) {
      const label = labelText(element);
      if (label) return { name: label, nameFrom: "author" };
    }
    const alt = element.getAttribute("alt");
    if (alt && alt.trim()) return { name: collapseWhitespace(alt), nameFrom: "author" };
    const title = element.getAttribute("title");
    if (title && title.trim()) return { name: collapseWhitespace(title), nameFrom: "author" };
    if (NAME_FROM_CONTENT_ROLES.has(elementRole)) {
      const content = collapseWhitespace(element.textContent);
      return { name: content, nameFrom: content ? "content" : "" };
    }
    return { name: "", nameFrom: "" };
  }

  function isFocusable(element) {
    if (element.matches(":disabled")) return false;
    const tabindex = element.getAttribute("tabindex");
    if (tabindex !== null && Number(tabindex) >= 0) return true;
    const tag = element.tagName.toLowerCase();
    if (tag === "a" || tag === "area") return element.hasAttribute("href");
    if (FOCUSABLE_TAGS.has(tag)) return true;
    return element.isContentEditable === true;
  }

  function ariaState(element) {
    const state = {};
    for (const attribute of STATE_ATTRIBUTES) {
      if (element.hasAttribute(attribute)) state[attribute] = element.getAttribute(attribute);
    }
    if (element.disabled === true) state.disabled = "true";
    return state;
  }

  function parseColor(text) {
    const match = /^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+)\s*)?\)$/.exec(text || "");
    if (!match) return null;
    return { r: Number(match[1]), g: Number(match[2]), b: Number(match[3]), a: match[4] === undefined ? 1 : Number(match[4]) };
  }

  let canonicalColorContext;
  let canonicalColorContextResolved = false;

  function canonicalColorCanvasContext() {
    if (!canonicalColorContextResolved) {
      canonicalColorContextResolved = true;
      try {
        const canvas = document.createElement("canvas");
        canvas.width = 1;
        canvas.height = 1;
        canonicalColorContext = canvas.getContext("2d", { willReadFrequently: true, colorSpace: "srgb" }) || null;
      } catch (error) {
        canonicalColorContext = null;
      }
    }
    return canonicalColorContext;
  }

  function canonicalColor(text) {
    if (!text || text === "transparent" || parseColor(text)) return text;
    try {
      const context = canonicalColorCanvasContext();
      if (!context) return text;
      context.fillStyle = "transparent";
      context.fillStyle = text;
      if (context.fillStyle === "rgba(0, 0, 0, 0)") return text;
      context.clearRect(0, 0, 1, 1);
      context.fillRect(0, 0, 1, 1);
      const data = context.getImageData(0, 0, 1, 1).data;
      const alpha = Math.round((data[3] / 255) * 1000) / 1000;
      return `rgba(${data[0]}, ${data[1]}, ${data[2]}, ${alpha})`;
    } catch (error) {
      return text;
    }
  }

  function effectiveBackground(element) {
    let current = element;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      const style = getComputedStyle(current);
      const raw = style.backgroundColor;
      if (style.backgroundImage && style.backgroundImage !== "none") {
        return { color: canonicalColor(raw), solid: false };
      }
      const canonical = canonicalColor(raw);
      const color = parseColor(canonical);
      if (color && color.a >= 1) return { color: canonical, solid: true };
      if (color && color.a > 0) return { color: canonical, solid: false };
      if (!color && raw && raw !== "transparent") return { color: canonical, solid: false };
      current = current.parentElement;
    }
    return { color: "rgb(255, 255, 255)", solid: true };
  }

  function luminance(color) {
    const channel = (value) => {
      const scaled = value / 255;
      return scaled <= 0.03928 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(color.r) + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
  }

  function contrastRatio(foreground, background) {
    const lighter = Math.max(luminance(foreground), luminance(background));
    const darker = Math.min(luminance(foreground), luminance(background));
    return Math.round(((lighter + 0.05) / (darker + 0.05)) * 100) / 100;
  }

  function contrastOf(style, background, text) {
    if (!text) return null;
    const foreground = parseColor(style.color);
    const backgroundColor = parseColor(background.color);
    const size = parseFloat(style.fontSize) || 0;
    const weight = Number(style.fontWeight) || (style.fontWeight === "bold" ? 700 : 400);
    const largeText = size >= 24 || (size >= 18.66 && weight >= 700);
    if (!background.solid || !foreground || !backgroundColor || foreground.a < 1) {
      return { ratio: null, needsAnalyzer: true, largeText };
    }
    return { ratio: contrastRatio(foreground, backgroundColor), needsAnalyzer: false, largeText };
  }

  function isWrapper(style, text) {
    const zero = (value) => !value || parseFloat(value) === 0;
    const none = (value) => !value || value === "none";
    const rawBackground = style.backgroundColor;
    const ownBackground = parseColor(canonicalColor(rawBackground));
    const backgroundUnparseable = !ownBackground && rawBackground && rawBackground !== "transparent";
    return text === ""
      && zero(style.borderTopWidth) && zero(style.borderRightWidth) && zero(style.borderBottomWidth) && zero(style.borderLeftWidth)
      && (!ownBackground || ownBackground.a === 0)
      && !backgroundUnparseable
      && none(style.backgroundImage)
      && none(style.boxShadow)
      && zero(style.paddingTop) && zero(style.paddingRight) && zero(style.paddingBottom) && zero(style.paddingLeft)
      && none(style.transform)
      && (none(style.outlineStyle) || zero(style.outlineWidth));
  }

  function pathSegment(element) {
    const tag = element.tagName.toLowerCase();
    let index = 1;
    let sibling = element.previousElementSibling;
    while (sibling) {
      if (sibling.tagName.toLowerCase() === tag) index += 1;
      sibling = sibling.previousElementSibling;
    }
    return `${tag}:nth-of-type(${index})`;
  }

  function isHidden(element, style) {
    if (SKIPPED_TAGS.has(element.tagName.toLowerCase())) return true;
    return style.display === "none" || style.visibility === "hidden";
  }

  const COLOR_STYLE_KEYS = new Set([
    "color", "backgroundColor",
    "borderTopColor", "borderRightColor", "borderBottomColor", "borderLeftColor",
    "outlineColor",
  ]);

  function styleBlock(style, background) {
    const block = {};
    for (const key of STYLE_KEYS) block[key] = COLOR_STYLE_KEYS.has(key) ? canonicalColor(style[key]) : style[key];
    block.effectiveBackground = background.color;
    return block;
  }

  function relativeRect(rect, rootRect) {
    return {
      x: Math.round((rect.left - rootRect.left) * 100) / 100,
      y: Math.round((rect.top - rootRect.top) * 100) / 100,
      width: Math.round(rect.width * 100) / 100,
      height: Math.round(rect.height * 100) / 100,
    };
  }

  function snapshotNode(element, rootRect, path, options, isRoot) {
    const style = getComputedStyle(element);
    if (!isRoot && isHidden(element, style)) return null;
    const children = [];
    for (const child of element.children) {
      const childNode = snapshotNode(child, rootRect, `${path} > ${pathSegment(child)}`, options, false);
      if (childNode) children.push(childNode);
    }
    const rect = element.getBoundingClientRect();
    if (!isRoot && rect.width === 0 && rect.height === 0 && children.length === 0) return null;
    const text = ownText(element);
    const elementRole = role(element);
    const background = effectiveBackground(element);
    const { name, nameFrom } = accessibleName(element, elementRole);
    return {
      path,
      tag: element.tagName.toLowerCase(),
      hook: element.getAttribute(options.hookAttribute),
      ownText: text,
      textDigest: fnv1a(text),
      role: elementRole,
      name,
      nameFrom,
      focusable: isFocusable(element),
      tabIndex: element.tabIndex,
      state: ariaState(element),
      style: styleBlock(style, background),
      geometry: {
        relative: relativeRect(rect, rootRect),
        viewport: { x: rect.left, y: rect.top, width: rect.width, height: rect.height },
      },
      contrast: contrastOf(style, background, text),
      wrapper: isWrapper(style, text),
      children,
    };
  }

  function resolveRoot(rootSelector, options) {
    let matches = null;
    try {
      matches = document.querySelectorAll(rootSelector);
    } catch (error) {
      matches = null;
    }
    if (matches === null || matches.length === 0) {
      const escaped = rootSelector.replace(/["\\]/g, "\\$&");
      matches = document.querySelectorAll(`[${options.rootAttribute}="${escaped}"]`);
    }
    if (matches.length === 0) return { error: "root-not-found", rootSelector };
    if (matches.length > 1) return { error: "root-ambiguous", count: matches.length, rootSelector };
    return { element: matches[0] };
  }

  function paritySnapshot(rootSelector, options) {
    if (typeof rootSelector !== "string" || rootSelector.trim() === "") {
      return { error: "root-not-found", rootSelector };
    }
    const settings = Object.assign({}, DEFAULT_OPTIONS, options || {});
    const resolved = resolveRoot(rootSelector, settings);
    if (resolved.error) return resolved;
    const rootElement = resolved.element;
    const rootRect = rootElement.getBoundingClientRect();
    const root = snapshotNode(rootElement, rootRect, rootElement.tagName.toLowerCase(), settings, true);
    return {
      url: location.href,
      viewport: { width: innerWidth, height: innerHeight },
      devicePixelRatio,
      zoom: Math.round((outerWidth / innerWidth) * 100) / 100 || 1,
      colorScheme: typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light",
      capturedAt: new Date().toISOString(),
      rootSelector,
      rootSummary: { tag: root.tag, role: root.role, name: root.name, width: root.geometry.relative.width, height: root.geometry.relative.height },
      root,
    };
  }

  globalThis.paritySnapshot = paritySnapshot;
})();
