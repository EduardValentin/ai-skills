import { DEFAULT_KINDS } from "../model/defaults.mjs";
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

export function plainAdditions(additions) {
  return { ...additions, componentEdges: additions.componentEdges.map(edgeName) };
}

const ROLES_STANDING_IN = new Set(["policy", "detail", "wiring"]);

function defaultKindsLike(model, kind) {
  if (Object.hasOwn(DEFAULT_KINDS, kind)) return [kind];
  const role = model.kinds[kind]?.role;
  if (!ROLES_STANDING_IN.has(role)) return [];
  return Object.keys(DEFAULT_KINDS).filter((candidate) => DEFAULT_KINDS[candidate].role === role);
}

function targetsOfUnit(model, unit) {
  const kinds = defaultKindsLike(model, unit.kind);
  const suite = unit.kind === "test" ? ["test-suite"] : [];
  return [...kinds, ...suite].map((kind) => ({ kind, component: unit.component }));
}

function unitTargets(model, units) {
  return units.filter((unit) => unit.kind).flatMap((unit) => targetsOfUnit(model, unit));
}

const TOUCHED_UNIT = "touched-unit";
const UNIT_KINDS = Object.keys(DEFAULT_KINDS);

function touchedUnitTargets(units) {
  return units.map((unit) => ({ kind: TOUCHED_UNIT, component: unit.component ?? null }));
}

function addedComponentNames(additions) {
  return [...additions.components, ...additions.componentEdges.flatMap((edge) => [edge.from, edge.to])];
}

function componentTargets({ components, additions, everyComponent = false }) {
  const names = everyComponent ? components : addedComponentNames(additions);
  return [...new Set(names)].map((name) => ({ kind: "component", component: name }));
}

const PLAN_TARGETS = [{ kind: "plan", component: null }];

export function judgmentTargets(model, scope) {
  return [
    ...unitTargets(model, scope.units),
    ...touchedUnitTargets(scope.units),
    ...componentTargets(scope),
    ...(scope.plan ? PLAN_TARGETS : []),
  ];
}

const KNOB = /\{([A-Za-z]+)\}/g;

function conditionFor(model, judgment) {
  return judgment.condition.replace(KNOB, (knob, name) => String(model.thresholds[name] ?? knob));
}

function judgmentEntry(model, judgment) {
  return { id: judgment.id, targets: judgment.targets, condition: conditionFor(model, judgment) };
}

function judgesEveryUnit(judgment) {
  return judgment.group === "cross-cutting" && UNIT_KINDS.every((kind) => judgment.targets.includes(kind));
}

function appliesTo(judgment, target) {
  if (target.kind === TOUCHED_UNIT) return judgesEveryUnit(judgment);
  return judgment.targets.includes(target.kind);
}

function rulesInScope(model, judgment, targets) {
  const matching = targets.filter((target) => appliesTo(judgment, target));
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
    entry.judgments.push(judgmentEntry(model, judgment));
    for (const rule of rules) entry.rules.add(rule);
  }
  return [...byGroup].map(([group, entry]) => ({
    group,
    judgments: entry.judgments,
    rules: [...entry.rules].sort((a, b) => ruleNumber(a) - ruleNumber(b)),
  }));
}
