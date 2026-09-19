// Inject unchanged into the prototype page (a React development build), then
// evaluate globalThis.parityFindReactRoots(componentNames) with the names
// passed as a serialized argument.

(() => {
  "use strict";

  const FIBER_KEY_PREFIX = "__reactFiber$";

  function fiberOf(element) {
    const key = Object.keys(element).find((name) => name.startsWith(FIBER_KEY_PREFIX));
    return key ? element[key] : null;
  }

  function componentName(type) {
    if (typeof type === "function") return type.displayName || type.name || "";
    if (type && typeof type === "object") {
      if (typeof type.displayName === "string" && type.displayName) return type.displayName;
      if (type.type) return componentName(type.type);
      if (type.render) return componentName(type.render);
    }
    return "";
  }

  function owningNames(fiber) {
    const names = [];
    const seen = new Set();
    let current = fiber ? fiber.return : null;
    while (current && !seen.has(current)) {
      seen.add(current);
      const name = componentName(current.type);
      if (name) names.push(name);
      current = current.return;
    }
    return names;
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

  function selectorFromBody(element) {
    const segments = [];
    let current = element;
    while (current && current !== document.body) {
      segments.unshift(pathSegment(current));
      current = current.parentElement;
    }
    return ["body", ...segments].join(" > ");
  }

  function summaryOf(element) {
    const rect = element.getBoundingClientRect();
    return {
      tag: element.tagName.toLowerCase(),
      role: element.getAttribute("role") || "",
      name: element.getAttribute("aria-label") || "",
      width: rect.width,
      height: rect.height,
    };
  }

  function outermost(elements) {
    return elements.filter((element) => !elements.some((other) => other !== element && other.contains(element)));
  }

  function parityFindReactRoots(componentNames) {
    const wanted = new Set(Array.isArray(componentNames) ? componentNames : []);
    const found = new Map();
    for (const name of wanted) found.set(name, []);
    let sawFiber = false;
    for (const element of document.querySelectorAll("*")) {
      const fiber = fiberOf(element);
      if (!fiber) continue;
      sawFiber = true;
      for (const name of owningNames(fiber)) {
        if (wanted.has(name) && !found.get(name).includes(element)) found.get(name).push(element);
      }
    }
    if (!sawFiber) return { error: "no-react-fibers" };
    const roots = {};
    for (const [name, elements] of found) {
      roots[name] = outermost(elements).map((element) => ({ selector: selectorFromBody(element), summary: summaryOf(element) }));
    }
    return { roots };
  }

  globalThis.parityFindReactRoots = parityFindReactRoots;
})();
