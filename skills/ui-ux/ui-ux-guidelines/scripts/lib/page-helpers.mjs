export function installPageHelpers() {
  const TRANSPARENT = new Set(["rgba(0, 0, 0, 0)", "transparent"]);

  const isRendered = (element) => {
    if (element.getClientRects().length === 0) return false;
    const style = getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && style.visibility !== "collapse";
  };

  const segment = (element) => {
    const tag = element.localName;
    const classes = [...element.classList].slice(0, 2).map((name) => `.${CSS.escape(name)}`).join("");
    const twins = element.parentElement
      ? [...element.parentElement.children].filter((sibling) => sibling.localName === tag)
      : [];
    const position = twins.length > 1 ? `:nth-of-type(${twins.indexOf(element) + 1})` : "";
    return `${tag}${classes}${position}`;
  };

  const selectorOf = (element) => {
    const parts = [];
    for (let node = element; node && node.nodeType === 1; node = node.parentElement) {
      if (node.id && document.querySelectorAll(`#${CSS.escape(node.id)}`).length === 1) {
        parts.unshift(`#${CSS.escape(node.id)}`);
        break;
      }
      if (node === document.documentElement) {
        parts.unshift("html");
        break;
      }
      parts.unshift(segment(node));
      if (node === document.body) break;
    }
    return parts.join(" > ");
  };

  const backgroundLayers = (element) => {
    const layers = [];
    for (let node = element; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      const image =
        style.backgroundImage !== "none" ||
        (node !== element && style.filter !== "none") ||
        style.mixBlendMode !== "normal";
      if (image || !TRANSPARENT.has(style.backgroundColor)) layers.push({ color: style.backgroundColor, image });
    }
    return layers;
  };

  const effectiveOpacity = (element) => {
    let opacity = 1;
    for (let node = element; node; node = node.parentElement) opacity *= parseFloat(getComputedStyle(node).opacity);
    return opacity;
  };

  const hasDirectText = (element) =>
    [...element.childNodes].some((node) => node.nodeType === 3 && node.nodeValue.trim() !== "");

  const directText = (element) =>
    [...element.childNodes]
      .filter((node) => node.nodeType === 3)
      .map((node) => node.nodeValue)
      .join(" ")
      .replace(/\s+/g, " ")
      .trim();

  window.__uxAudit = { TRANSPARENT, isRendered, selectorOf, backgroundLayers, effectiveOpacity, hasDirectText, directText };
}
