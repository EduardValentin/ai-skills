import { createClassifier } from "../model/classify.mjs";
import { stronglyConnected, naturalOrder } from "./cycles.mjs";
import { componentMetrics } from "./metrics.mjs";

export const GRAPH_VERSION = 6;
export const THROUGH_BARREL = "through-barrel";
const FACTS = ["exports", "implements", "signatures", "typeChecks"];

function byText(...keys) {
  return (a, b) => {
    for (const key of keys) {
      const order = a[key].localeCompare(b[key]);
      if (order !== 0) return order;
    }
    return 0;
  };
}

function providedFacts(module, capabilities) {
  return Object.fromEntries(FACTS.map((fact) => [fact, capabilities[fact] ? module[fact] : null]));
}

function buildUnits(model, document) {
  const classify = createClassifier(model);
  return document.modules
    .map((module) => {
      const { component, kind, ring, actors } = classify(module.path);
      return { path: module.path, component, kind, ring, actors, ...providedFacts(module, document.capabilities) };
    })
    .sort(byText("path"));
}

function constructsEdges(document) {
  if (!document.capabilities.constructs) return [];
  const known = new Set(document.modules.map((module) => module.path));
  return document.modules.flatMap((module) =>
    [...new Set(module.constructs.map((constructed) => constructed.path))]
      .filter((target) => known.has(target))
      .map((target) => ({ from: module.path, to: target, kind: "constructs" })),
  );
}

export function ringDirection(rings, fromRing, toRing) {
  const from = rings.indexOf(fromRing);
  const to = rings.indexOf(toRing);
  if (from < 0 || to < 0) return "unknown";
  if (to < from) return "inward";
  return to > from ? "outward" : "same";
}

function describeEdge(edge, unitOf, rings) {
  const from = unitOf.get(edge.from);
  const to = unitOf.get(edge.to);
  const throughBarrel = from?.kind === "barrel" || to?.kind === "barrel";
  return {
    from: edge.from,
    to: edge.to,
    kind: edge.kind,
    symbols: edge.symbols ?? null,
    crossesComponent: (from?.component ?? null) !== (to?.component ?? null),
    direction: throughBarrel ? THROUGH_BARREL : ringDirection(rings, from?.ring ?? null, to?.ring ?? null),
  };
}

function buildEdges(document, units, rings) {
  const unitOf = new Map(units.map((unit) => [unit.path, unit]));
  const listed = document.edges.filter((edge) => edge.to);
  return [...listed, ...constructsEdges(document)]
    .map((edge) => describeEdge(edge, unitOf, rings))
    .sort(byText("from", "to", "kind"));
}

function buildExternals(document) {
  const byName = new Map();
  for (const edge of document.edges.filter((candidate) => candidate.external)) {
    const { name, tag } = edge.external;
    if (!byName.has(name)) byName.set(name, { name, tag, importers: new Set() });
    byName.get(name).importers.add(edge.from);
  }
  return [...byName.values()]
    .map(({ name, tag, importers }) => ({ name, tag, importers: [...importers].sort() }))
    .sort(byText("name"));
}

function buildComponentEdges(units, edges) {
  const componentOf = new Map(units.map((unit) => [unit.path, unit.component]));
  const grouped = new Map();
  for (const edge of edges) {
    const from = componentOf.get(edge.from) ?? null;
    const to = componentOf.get(edge.to) ?? null;
    if (!from || !to || from === to) continue;
    const key = JSON.stringify([from, to]);
    if (!grouped.has(key)) grouped.set(key, { from, to, modules: new Set() });
    grouped.get(key).modules.add(edge.from);
  }
  return [...grouped.values()]
    .map(({ from, to, modules }) => ({ from, to, modules: modules.size }))
    .sort((a, b) => naturalOrder(a.from, b.from) || naturalOrder(a.to, b.to));
}

function buildCycles(units, edges, componentEdges, model) {
  return {
    modules: stronglyConnected(units.map((unit) => unit.path), edges.map((edge) => [edge.from, edge.to])),
    components: stronglyConnected(
      model.components.map((component) => component.name),
      componentEdges.map((edge) => [edge.from, edge.to]),
    ),
  };
}

export function buildGraph(model, document) {
  const units = buildUnits(model, document);
  const edges = buildEdges(document, units, model.rings);
  const componentEdges = buildComponentEdges(units, edges);
  return {
    version: GRAPH_VERSION,
    capabilities: document.capabilities,
    rings: model.rings,
    units,
    edges,
    externals: buildExternals(document),
    components: componentMetrics(units, edges, model.components, model.thresholds),
    componentEdges,
    cycles: buildCycles(units, edges, componentEdges, model),
    uncovered: units.filter((unit) => unit.component === null || unit.kind === null).map((unit) => unit.path),
    warnings: [...document.warnings],
  };
}
