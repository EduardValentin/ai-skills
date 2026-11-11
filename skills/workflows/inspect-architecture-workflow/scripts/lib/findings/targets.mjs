const EDGE_SEPARATOR = " -> ";
const PORT_SEPARATOR = "#";

function partsOf(target) {
  return target.split(EDGE_SEPARATOR).map((part) => part.split(PORT_SEPARATOR)[0]);
}

function recognizeEdge(target, units, components) {
  const parts = target.split(EDGE_SEPARATOR);
  if (parts.length !== 2) return null;
  const [from, to] = parts;
  if (units.has(from) && units.has(to)) {
    return { kind: "edge", units: parts, components: [], edge: { level: "unit", from, to } };
  }
  if (components.has(from) && components.has(to)) {
    return { kind: "edge", units: [], components: parts, edge: { level: "component", from, to } };
  }
  return null;
}

function recognizePort(target, units) {
  const [path, symbol] = target.split(PORT_SEPARATOR);
  if (!symbol || !units.has(path)) return null;
  return { kind: "port", units: [path], components: [], edge: null };
}

export function recognizeTarget(graph, target) {
  const units = new Set(graph.units.map((unit) => unit.path));
  const components = new Set(graph.components.map((component) => component.name));
  if (target.includes(EDGE_SEPARATOR)) return recognizeEdge(target, units, components);
  if (target.includes(PORT_SEPARATOR)) return recognizePort(target, units);
  if (units.has(target)) return { kind: "unit", units: [target], components: [], edge: null };
  if (components.has(target)) return { kind: "component", units: [], components: [target], edge: null };
  return null;
}

export function componentOfTarget(graph, target) {
  const [first] = partsOf(target);
  const unit = graph.units.find((candidate) => candidate.path === first);
  if (unit) return unit.component;
  return graph.components.some((component) => component.name === first) ? first : null;
}

export function isInScope(scope, target) {
  if (!scope) return true;
  const units = new Set(scope.units);
  const components = new Set(scope.components);
  return partsOf(target).some((part) => units.has(part) || components.has(part));
}
