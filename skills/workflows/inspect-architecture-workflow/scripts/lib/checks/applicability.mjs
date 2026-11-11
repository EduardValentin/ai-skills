import { JUDGMENTS } from "./judgments.mjs";
import { ruleNumber } from "./rule-titles.mjs";
import { statusForRule } from "./status.mjs";

export const NO_ADDITIONS = { components: [], ports: [], componentEdges: [], externals: [] };

function componentsWithUnits(graph) {
  return new Set(graph.components.filter((component) => component.units > 0).map((component) => component.name));
}

function edgeName(edge) {
  return `${edge.from} -> ${edge.to}`;
}

function addedPorts(model, baseGraph, graph, renames) {
  const before = new Set(baseGraph.units.map((unit) => unit.path));
  const after = new Set(graph.units.map((unit) => unit.path));
  const renamed = new Set(renames.values());
  return model.ports
    .filter((port) => after.has(port.path) && !before.has(port.path) && !renamed.has(port.path))
    .map((port) => port.at);
}

export function changeAdditions({ model, baseGraph, graph, renames }) {
  const baseComponents = componentsWithUnits(baseGraph);
  const baseEdges = new Set(baseGraph.componentEdges.map(edgeName));
  const baseExternals = new Set(baseGraph.externals.map((external) => external.name));
  return {
    components: [...componentsWithUnits(graph)].filter((name) => !baseComponents.has(name)),
    ports: addedPorts(model, baseGraph, graph, renames),
    componentEdges: graph.componentEdges.filter((edge) => !baseEdges.has(edgeName(edge))),
    externals: graph.externals.map((external) => external.name).filter((name) => !baseExternals.has(name)),
  };
}

function spreadReasons(components) {
  if (components.length < 2) return [];
  return [`the change touches ${components.length} components: ${components.join(", ")}`];
}

function uncoveredReasons(uncovered) {
  if (uncovered.length === 0) return [];
  return [`the change touches files the model does not cover: ${uncovered.join(", ")}`];
}

export function reviewReasons({ components, uncovered, additions }) {
  return [
    ...spreadReasons(components),
    ...additions.components.map((name) => `the change adds component ${name}`),
    ...additions.ports.map((at) => `the change adds port ${at}`),
    ...additions.componentEdges.map((edge) => `the change adds the component edge ${edgeName(edge)}`),
    ...additions.externals.map((name) => `the change adds external ${name}`),
    ...uncoveredReasons(uncovered),
  ];
}

function unitTargets(units) {
  return units
    .filter((unit) => unit.kind)
    .flatMap((unit) => [
      { kind: unit.kind, component: unit.component },
      ...(unit.kind === "test" ? [{ kind: "test-suite", component: unit.component }] : []),
    ]);
}

function componentTargets(additions) {
  const names = [...additions.components, ...additions.componentEdges.flatMap((edge) => [edge.from, edge.to])];
  return [...new Set(names)].map((name) => ({ kind: "component", component: name }));
}

export function judgmentTargets({ units, additions }) {
  return [...unitTargets(units), ...componentTargets(additions)];
}

function rulesInScope(model, judgment, targets) {
  const matching = targets.filter((target) => judgment.targets.includes(target.kind));
  return judgment.rules.filter((rule) =>
    matching.some((target) => statusForRule(model, rule, target.component) !== "off"),
  );
}

export function judgmentScope(model, targets) {
  const byGroup = new Map();
  for (const judgment of JUDGMENTS) {
    const rules = rulesInScope(model, judgment, targets);
    if (rules.length === 0) continue;
    if (!byGroup.has(judgment.group)) byGroup.set(judgment.group, { judgments: [], rules: new Set() });
    const entry = byGroup.get(judgment.group);
    entry.judgments.push(judgment.id);
    for (const rule of rules) entry.rules.add(rule);
  }
  return [...byGroup].map(([group, entry]) => ({
    group,
    judgments: entry.judgments,
    rules: [...entry.rules].sort((a, b) => ruleNumber(a) - ruleNumber(b)),
  }));
}
